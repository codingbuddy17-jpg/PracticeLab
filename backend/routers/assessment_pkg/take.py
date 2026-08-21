"""
Assessment Take router — coder-facing public endpoints.
No authentication required; access is controlled by session token validity.
"""
import json
from datetime import datetime, timezone
from services.timeutil import as_utc
from services.assessment_scoring import score_session
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentSession, AssessmentResponse, AssessmentResult,
    GeneratedAssessment, GeneratedAssessmentStudent,
)

router = APIRouter()



def _coder_score(s: AssessmentSession, db: Session) -> Optional[dict]:
    """
    The score this coder is allowed to see, or None.

    Gated on the paper's own show_results_to_coder, which is off unless the
    trainer turned it on. Returns the mark and the paper's own bar — never the
    questions, never which ones were wrong: the point of the switch is to hand
    back a result, and an MCQ paper is reused, so the answers are not the
    coder's to keep.
    """
    paper = db.query(GeneratedAssessment).filter(
        GeneratedAssessment.id == s.assessment_id).first()
    if not paper or not paper.show_results_to_coder:
        return None
    res = db.query(AssessmentResult).filter(
        AssessmentResult.session_id == s.id).first()
    if not res:
        return None
    pct = round(res.score_pct, 1)
    # The paper's own bar, not a module constant — see GeneratedAssessment.
    threshold = paper.pass_threshold
    return {
        "score_pct": pct,
        "correct_count": res.correct_count,
        "total_questions": res.total_questions,
        "pass_threshold": threshold,
        # NA, not False, when the paper never set a bar. A missing threshold
        # is an unanswered question, and rendering it as a fail is a lie.
        "passed": None if threshold is None else pct >= threshold,
    }


def _get_session(token: str, db: Session) -> AssessmentSession:
    s = db.query(AssessmentSession).filter(AssessmentSession.session_token == token).first()
    if not s:
        raise HTTPException(status_code=404, detail="Assessment not found. Check your session ID.")
    return s


def _questions_for_session(session: AssessmentSession, db: Session):
    """Return this coder's dedicated shuffled question set via direct slot lookup."""
    if session.student_slot_id:
        slot = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.id == session.student_slot_id
        ).first()
    else:
        # Fallback for sessions created before the slot FK was introduced
        slot = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.assessment_id == session.assessment_id
        ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="No questions found for this assessment.")

    qs = slot.questions_json
    if isinstance(qs, str):
        qs = json.loads(qs)
    return qs


# Fields a coder must never be sent. correct_answer is the obvious one.
# difficulty is trainer metadata: it exists so a trainer can build a balanced
# paper, and telling a coder mid-question that this one is "Hard" invites them
# to second-guess an answer they had right — it grades their nerve rather than
# their coding.
_TRAINER_ONLY_FIELDS = {"correct_answer", "difficulty"}


def _strip_answers(questions: list) -> list:
    """Remove trainer-only fields from questions before sending to the coder."""
    return [
        {k: v for k, v in q.items() if k not in _TRAINER_ONLY_FIELDS}
        for q in questions
    ]


# ── GET /take/{token} ─────────────────────────────────────────────────────────

@router.get("/take/{token}")
def get_session_info(token: str, db: Session = Depends(get_db)):
    """
    Validate token and return session metadata.
    Does NOT start the timer — coder must call /start.
    """
    s = _get_session(token, db)
    now = datetime.now(timezone.utc)

    if s.status == "submitted":
        return {
            "session_token": s.session_token,
            "coder_name": s.coder_name,
            "employee_id": s.employee_id,
            "status": "submitted",
            "duration_minutes": s.duration_minutes,
            "expires_at": s.expires_at.isoformat(),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "time_limit_ends_at": s.time_limit_ends_at.isoformat() if s.time_limit_ends_at else None,
            "time_remaining_seconds": None,
            "total_questions": 0,
            # Re-opening the link after submitting shows the same thing the
            # submit screen did, rather than less.
            "result": _coder_score(s, db),
        }

    if s.status == "pending" and now > as_utc(s.expires_at):
        raise HTTPException(
            status_code=410,
            detail="This assessment session has expired. Please contact your trainer."
        )

    questions = _questions_for_session(s, db)
    time_remaining_seconds = None
    if s.status == "in_progress" and s.time_limit_ends_at:
        remaining = (as_utc(s.time_limit_ends_at) - now).total_seconds()
        time_remaining_seconds = max(0, int(remaining))

    return {
        "session_token": s.session_token,
        "coder_name": s.coder_name,
        "employee_id": s.employee_id,
        "status": s.status,
        "duration_minutes": s.duration_minutes,
        "expires_at": s.expires_at.isoformat(),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "time_limit_ends_at": s.time_limit_ends_at.isoformat() if s.time_limit_ends_at else None,
        "time_remaining_seconds": time_remaining_seconds,
        "total_questions": len(questions),
    }


# ── POST /take/{token}/start ──────────────────────────────────────────────────

@router.post("/take/{token}/start")
def start_session(token: str, db: Session = Depends(get_db)):
    """
    Start the assessment — sets started_at and time_limit_ends_at.
    Idempotent: if already in_progress, returns current state (resume).
    """
    s = _get_session(token, db)
    now = datetime.now(timezone.utc)

    if s.status == "submitted":
        raise HTTPException(status_code=410, detail="Assessment already submitted.")

    if s.status == "pending" and now > as_utc(s.expires_at):
        raise HTTPException(status_code=410, detail="Session expired — cannot start.")

    if s.status == "pending":
        from datetime import timedelta
        s.status = "in_progress"
        s.started_at = now
        s.time_limit_ends_at = now + timedelta(minutes=s.duration_minutes)
        db.commit()

    questions = _questions_for_session(s, db)

    # Load saved answers for resume
    saved = db.query(AssessmentResponse).filter(
        AssessmentResponse.session_id == s.id
    ).all()
    saved_answers = {r.question_index: r.selected_answer for r in saved}

    time_remaining = max(0, int((as_utc(s.time_limit_ends_at) - now).total_seconds()))

    return {
        "session_token": s.session_token,
        "coder_name": s.coder_name,
        "status": s.status,
        "time_remaining_seconds": time_remaining,
        "time_limit_ends_at": s.time_limit_ends_at.isoformat(),
        "questions": _strip_answers(questions),
        "saved_answers": saved_answers,
    }


# ── POST /take/{token}/answer ─────────────────────────────────────────────────

class AnswerPayload(BaseModel):
    question_index: int
    question_id: str
    selected_answer: Optional[str] = None  # None = clear answer


@router.post("/take/{token}/answer")
def save_answer(token: str, payload: AnswerPayload, db: Session = Depends(get_db)):
    """Auto-save a single answer. Upserts so resume always reflects latest state."""
    s = _get_session(token, db)
    now = datetime.now(timezone.utc)

    if s.status != "in_progress":
        raise HTTPException(status_code=400, detail="Session is not in progress.")

    # Enforce time limit
    if s.time_limit_ends_at and now > as_utc(s.time_limit_ends_at):
        raise HTTPException(status_code=410, detail="Time limit exceeded. Assessment will be auto-submitted.")

    existing = db.query(AssessmentResponse).filter(
        AssessmentResponse.session_id == s.id,
        AssessmentResponse.question_index == payload.question_index,
    ).first()

    if existing:
        existing.selected_answer = payload.selected_answer
        existing.answered_at = now
    else:
        db.add(AssessmentResponse(
            session_id=s.id,
            question_index=payload.question_index,
            question_id=payload.question_id,
            selected_answer=payload.selected_answer,
            answered_at=now,
        ))

    s.last_saved_at = now
    db.commit()
    return {"saved": True, "question_index": payload.question_index}


# ── POST /take/{token}/submit ─────────────────────────────────────────────────

class SubmitPayload(BaseModel):
    auto_submitted: bool = False


@router.post("/take/{token}/submit")
def submit_session(token: str, payload: SubmitPayload, db: Session = Depends(get_db)):
    """
    Final submission — compute scores, mark session submitted.
    Called by coder on manual submit OR by frontend timer on auto-submit.
    """
    s = _get_session(token, db)
    now = datetime.now(timezone.utc)

    if s.status == "submitted":
        raise HTTPException(status_code=409, detail="Already submitted.")

    if s.status != "in_progress":
        raise HTTPException(status_code=400, detail="Session is not in progress.")

    # Shared with the overdue sweep so both paths score identically.
    score_session(s, db, _questions_for_session(s, db))

    s.status = "submitted"
    s.submitted_at = now
    s.auto_submitted = payload.auto_submitted
    db.commit()

    result = _coder_score(s, db)
    return {
        "submitted": True,
        "auto_submitted": payload.auto_submitted,
        "result": result,
        "message": ("Your responses have been recorded."
                    if result else
                    "Your responses have been recorded. Your trainer will share your results."),
    }
