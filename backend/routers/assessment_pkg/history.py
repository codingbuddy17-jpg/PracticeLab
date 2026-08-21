"""
Assessment history router — list past assessments, delete.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Optional

from database import get_db
from services.randomisation_stats import parse_stats
from models import (
    GeneratedAssessment, GeneratedAssessmentStudent, AssessmentSession,
    AssessmentResponse, AssessmentResult, AssessmentConfig, AssessmentAuditLog,
)
from config import settings

router = APIRouter()


@router.get("/history")
def list_assessment_history(search: Optional[str] = None,
                            page: Optional[int] = Query(default=None, ge=1),
                            page_size: int = Query(default=50, ge=1, le=200),
                            db: Session = Depends(get_db)):
    """
    Every generated assessment, with enough context to act on it.

    The per-assessment lookups used to run inside the loop — one query for the
    first student and one lazy load for the config, per row. That is fine on a
    handful and turns into hundreds of round trips on a year of assessments,
    and it is the same N+1 shape already fixed in the question upload and the
    PracticeLab results.
    """
    import json

    q = db.query(GeneratedAssessment)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        q = q.filter((GeneratedAssessment.assessment_name.ilike(needle)) |
                     (GeneratedAssessment.batch_name.ilike(needle)) |
                     (GeneratedAssessment.generated_by.ilike(needle)))
    total = q.count()
    q = q.order_by(GeneratedAssessment.generated_at.desc())
    if page is not None:
        q = q.offset((page - 1) * page_size).limit(page_size)
    assessments = q.all()
    ids = [a.id for a in assessments] or [-1]

    # One slot per assessment, read in a single pass, for the question count.
    q_counts: Dict[int, int] = {}
    for slot in db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id.in_(ids)
    ).all():
        if slot.assessment_id in q_counts:
            continue
        qs = slot.questions_json
        if isinstance(qs, str):
            try:
                qs = json.loads(qs)
            except Exception:
                qs = []
        q_counts[slot.assessment_id] = len(qs) if isinstance(qs, list) else 0

    # Where each assessment stands, so the list answers "is this one finished?"
    # without opening Sessions to find out.
    status_counts: Dict[int, Dict[str, int]] = {}
    for sess in db.query(AssessmentSession).filter(
        AssessmentSession.assessment_id.in_(ids)
    ).all():
        c = status_counts.setdefault(sess.assessment_id,
                                     {"pending": 0, "in_progress": 0, "submitted": 0, "expired": 0})
        if sess.status in c:
            c[sess.status] += 1

    config_names: Dict[int, str] = {
        c.id: c.name for c in db.query(AssessmentConfig).filter(
            AssessmentConfig.id.in_([a.config_id for a in assessments if a.config_id] or [-1])
        ).all()
    }

    results = []
    for a in assessments:
        counts = status_counts.get(a.id, {"pending": 0, "in_progress": 0, "submitted": 0, "expired": 0})
        results.append({
            "id": a.id,
            "assessment_name": a.assessment_name,
            "config_name": config_names.get(a.config_id) if a.config_id else None,
            "batch_name": a.batch_name,
            "pass_threshold": float(a.pass_threshold) if a.pass_threshold else None,
            "student_count": a.student_count,
            "questions_per_student": q_counts.get(a.id, 0),
            "generated_by": a.generated_by,
            "generated_at": a.generated_at.isoformat() if a.generated_at else None,
            "randomisation_stats": parse_stats(a.randomisation_stats),
            "is_standalone": getattr(a, "is_standalone", False),
            "status_counts": counts,
        })

    if page is not None:
        return {"total": total, "page": page, "page_size": page_size, "results": results}
    return results


@router.delete("/{assessment_id}")
def delete_assessment(
    assessment_id: int,
    passphrase: str = Query(...),
    trainer_name: str = Query(default="Trainer"),
    force: bool = Query(default=False),
    reason: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Delete an assessment and everything under it.

    Refuses by default once anyone has sat it. The passphrase proved who is
    asking; it never established that destroying submitted work was intended,
    and this cascade removes responses, results and sessions permanently —
    coder evidence that cannot be reconstructed.

    `force` with a written reason is the deliberate override, and is recorded.
    """
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    a = db.query(GeneratedAssessment).filter(GeneratedAssessment.id == assessment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")

    all_sessions = db.query(AssessmentSession).filter(
        AssessmentSession.assessment_id == assessment_id).all()
    submitted = sum(1 for s in all_sessions if s.status == "submitted")
    graded = db.query(AssessmentResult).filter(
        AssessmentResult.session_id.in_([s.id for s in all_sessions] or [-1])
    ).count()
    evidence = max(submitted, graded)

    if evidence and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (f"'{a.assessment_name}' has {evidence} completed session(s). "
                            "Deleting removes their answers and scores permanently."),
                "submitted": submitted,
                "graded": graded,
                "requires": "force",
            },
        )
    if evidence and force and len((reason or "").strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail="Deleting completed work needs a written reason.",
        )

    # Delete in FK dependency order: responses → results → sessions → students → assessment
    session_ids = [
        s.id for s in db.query(AssessmentSession.id)
        .filter(AssessmentSession.assessment_id == assessment_id).all()
    ]
    if session_ids:
        db.query(AssessmentResponse).filter(
            AssessmentResponse.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(AssessmentResult).filter(
            AssessmentResult.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(AssessmentSession).filter(
            AssessmentSession.assessment_id == assessment_id
        ).delete(synchronize_session=False)
    db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).delete(synchronize_session=False)
    db.delete(a)

    # Recorded whether or not anything was lost: a deletion nobody can trace is
    # the gap an audit log exists to close.
    db.add(AssessmentAuditLog(
        trainer_name=(trainer_name or "Trainer").strip() or "Trainer",
        action="delete-assessment",
        details=(f"Deleted '{a.assessment_name}' (id {assessment_id}) — "
                 f"{len(all_sessions)} session(s), {evidence} completed."
                 + (f" Forced. Reason: {reason.strip()}" if evidence else "")),
    ))
    db.commit()
    return {"deleted": assessment_id, "sessions_removed": len(all_sessions),
            "completed_removed": evidence}
