"""
Assessment history router — list past assessments, delete.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from services.randomisation_stats import parse_stats
from models import GeneratedAssessment, GeneratedAssessmentStudent, AssessmentSession, AssessmentResponse, AssessmentResult
from config import settings

router = APIRouter()


@router.get("/history")
def list_assessment_history(db: Session = Depends(get_db)):
    """List all generated assessments with summary info."""
    assessments = db.query(GeneratedAssessment).order_by(
        GeneratedAssessment.generated_at.desc()
    ).all()

    results = []
    for a in assessments:
        # Get question count from first student
        first_student = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.assessment_id == a.id
        ).first()
        q_count = 0
        if first_student:
            qs = first_student.questions_json
            if isinstance(qs, list):
                q_count = len(qs)
            elif isinstance(qs, str):
                import json
                try:
                    q_count = len(json.loads(qs))
                except Exception:
                    q_count = 0

        config_name = None
        if a.config:
            config_name = a.config.name

        results.append({
            "id": a.id,
            "assessment_name": a.assessment_name,
            "config_name": config_name,
            "student_count": a.student_count,
            "questions_per_student": q_count,
            "generated_by": a.generated_by,
            "generated_at": a.generated_at.isoformat() if a.generated_at else None,
            "randomisation_stats": parse_stats(a.randomisation_stats),
            "is_standalone": getattr(a, "is_standalone", False),
        })

    return results


@router.delete("/{assessment_id}")
def delete_assessment(
    assessment_id: int,
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    """Hard-delete an assessment and all student records."""
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    a = db.query(GeneratedAssessment).filter(GeneratedAssessment.id == assessment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")

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
    db.commit()
    return {"deleted": assessment_id}
