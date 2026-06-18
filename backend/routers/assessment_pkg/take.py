"""
Assessment Take router — coder-facing public endpoints.
No authentication required; access is controlled by session token validity.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentSession, AssessmentResponse, AssessmentResult,
    GeneratedAssessmentStudent,
)

router = APIRouter()


def _get_session(token: str, db: Session) -> AssessmentSession:
    s = db.query(AssessmentSession).filter(AssessmentSession.session_token == token).first()
    if not s:
        raise HTTPException(status_code=404, detail="Assessment not found. Check your session ID.")
    return s


def _questions_for_session(session: AssessmentSession, db: Session):
    """
    Return the question list for this session.
    We use the first GeneratedAssessmentStudent row for this assessment as the
    shared question pool — each session gets the same pool since per-student
    shuffling happens at generation time and is stored there.
    Each session coder gets the same question set (already shuffled at generation).
    We use session.id % student_count to assign a student slot, giving variety
    across coders without storing duplicates.
    """
    students = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == session.assessment_id
    ).all()
    if not students:
        raise HTTPException(status_code=404, detail="No questions found for this assessment.")

    # Assign each coder a student slot deterministically by session id
    slot = session.id % len(students)
    qs = students[slot].questions_json
    if isinstance(qs, str):
        qs = json.loads(qs)
    return qs


def _strip_answers(questions: list) -> list:
    """Remove correct_answer from questions before sending to coder."""
    return [
        {k: v for k, v in q.items() if k != "correct_answer"}
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
        raise HTTPException(status_code=410, detail="This assessment has already been submitted.")

    if s.status == "pending" and now > s.expires_at:
        raise HTTPException(
            status_code=410,
            detail="This assessment session has expired. Please contact your trainer."
        )

    questions = _questions_for_session(s, db)
    time_remaining_seconds = None
    if s.status == "in_progress" and s.time_limit_ends_at:
        remaining = (s.time_limit_ends_at - now).total_seconds()
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

    if s.status == "pending" and now > s.expires_at:
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

    time_remaining = max(0, int((s.time_limit_ends_at - now).total_seconds()))

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
    if s.time_limit_ends_at and now > s.time_limit_ends_at:
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

    questions = _questions_for_session(s, db)
    q_map = {q["question_id"]: q["correct_answer"] for q in questions}

    responses = db.query(AssessmentResponse).filter(
        AssessmentResponse.session_id == s.id
    ).all()

    correct = 0
    for r in responses:
        expected = q_map.get(r.question_id)
        r.is_correct = (r.selected_answer == expected) if r.selected_answer and expected else False
        if r.is_correct:
            correct += 1

    total = len(questions)
    score_pct = round((correct / total) * 100, 1) if total > 0 else 0.0
    time_taken = int((now - s.started_at).total_seconds()) if s.started_at else None

    result = AssessmentResult(
        session_id=s.id,
        total_questions=total,
        correct_count=correct,
        score_pct=score_pct,
        time_taken_seconds=time_taken,
    )
    db.add(result)

    s.status = "submitted"
    s.submitted_at = now
    s.auto_submitted = payload.auto_submitted
    db.commit()

    return {
        "submitted": True,
        "auto_submitted": payload.auto_submitted,
        "message": "Your responses have been recorded. Your trainer will share your results.",
    }
