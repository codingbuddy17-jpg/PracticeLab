"""
Scoring and finalisation for assessment sessions.

Finalisation used to live only in the coder-facing submit endpoint, which meant
it happened only if the coder's browser was open to trigger it. A coder who
closed the laptop, lost the network, or simply walked away left an in_progress
session that the trainer's list *displayed* as "auto_submitted" while it was
never scored: no AssessmentResult row, a null score, and an attempt missing
from every analytic and report.

The scoring itself lives here so both paths — the coder pressing Submit and the
server sweeping up sessions whose time ran out — produce identical rows.
"""
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from models import (
    AssessmentSession, AssessmentResponse, AssessmentResult,
    GeneratedAssessmentStudent,
)
from services.timeutil import as_utc, utc_now


def questions_for_session(session: AssessmentSession, db: Session) -> list:
    """This coder's dedicated question set, as served."""
    slot = None
    if session.student_slot_id:
        slot = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.id == session.student_slot_id
        ).first()
    if not slot:
        slot = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.assessment_id == session.assessment_id
        ).first()
    if not slot:
        return []
    qs = slot.questions_json
    return json.loads(qs) if isinstance(qs, str) else (qs or [])


def score_session(session: AssessmentSession, db: Session, questions: Optional[list] = None):
    """
    Grade the saved responses and return (result, correct, total).
    Does not commit — the caller owns the transaction.
    """
    if questions is None:
        questions = questions_for_session(session, db)

    q_map = {q["question_id"]: q["correct_answer"] for q in questions}

    responses = db.query(AssessmentResponse).filter(
        AssessmentResponse.session_id == session.id
    ).all()

    correct = 0
    for r in responses:
        expected = q_map.get(r.question_id)
        r.is_correct = (r.selected_answer == expected) if r.selected_answer and expected else False
        if r.is_correct:
            correct += 1

    total = len(questions)
    now = utc_now()
    started = as_utc(session.started_at)

    result = AssessmentResult(
        session_id=session.id,
        total_questions=total,
        correct_count=correct,
        score_pct=round((correct / total) * 100, 1) if total > 0 else 0.0,
        time_taken_seconds=int((now - started).total_seconds()) if started else None,
    )
    db.add(result)
    return result, correct, total


def finalise_overdue_sessions(db: Session, assessment_id: Optional[int] = None) -> List[int]:
    """
    Score and close every in_progress session whose time limit has passed.

    Idempotent and safe to call from a read path: a session already submitted is
    skipped, so repeated calls converge. Returns the session IDs it closed.

    A session's clock ends when time_limit_ends_at passes, whether or not anyone
    is watching. Deciding that at read time is what keeps a trainer's list, the
    analytics, and the PDF reports telling the same story.
    """
    now = utc_now()
    q = db.query(AssessmentSession).filter(
        AssessmentSession.status == "in_progress",
        AssessmentSession.time_limit_ends_at.isnot(None),
    )
    if assessment_id is not None:
        q = q.filter(AssessmentSession.assessment_id == assessment_id)

    closed: List[int] = []
    for s in q.all():
        if now <= as_utc(s.time_limit_ends_at):
            continue
        already = db.query(AssessmentResult).filter(
            AssessmentResult.session_id == s.id
        ).first()
        if not already:
            score_session(s, db)
        s.status = "submitted"
        # The clock, not the coder, ended this one — record when it actually ran out.
        s.submitted_at = as_utc(s.time_limit_ends_at)
        s.auto_submitted = True
        closed.append(s.id)

    if closed:
        db.commit()
    return closed
