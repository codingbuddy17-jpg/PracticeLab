"""Manual rubric grading endpoints for Edits and Denials specialties."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from database import get_db
from models import (
    Batch, BatchChart, BatchCoder, BatchStatus, GradingResult, PassFail,
    Specialty, SubmissionStatus, EDRubricDetail,
)
from .shared import _is_ed

router = APIRouter()

ED_PASS_THRESHOLD = 80  # score must be >= 80 to pass

RATIONALE_SCORES = {
    "acceptable": 5,
    "needs_improvement": 3,  # 2.5 rounded up
    "not_acceptable": 0,
}


def _compute_ed_score(payload: "EDRubricPayload") -> int:
    score = 0
    if payload.review_pass:
        score += 30
    if payload.research_coding_pass:
        score += 10
    if payload.research_payer_pass:
        score += 10
    if payload.research_nuances_pass:
        score += 10
    if payload.resolution_pass:
        score += 35
    score += RATIONALE_SCORES.get(payload.rationale_tier, 0)
    return score


class EDRubricPayload(BaseModel):
    coder_name: str
    chart_id: int
    review_pass: bool
    research_coding_pass: bool
    research_payer_pass: bool
    research_nuances_pass: bool
    resolution_pass: bool
    rationale_tier: str  # "acceptable" | "needs_improvement" | "not_acceptable"
    trainer_note: Optional[str] = None
    graded_by: str
    regrade: bool = False


@router.post("/batches/{batch_id}/grade-ed")
def grade_ed_chart(batch_id: int, payload: EDRubricPayload, db: Session = Depends(get_db)):
    """Submit manual rubric scores for one coder/chart in an E&D batch."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _is_ed(batch.specialty):
        raise HTTPException(status_code=400, detail="This endpoint is only for Edits/Denials batches")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot accept new grades")

    if payload.rationale_tier not in RATIONALE_SCORES:
        raise HTTPException(status_code=422, detail="rationale_tier must be acceptable, needs_improvement, or not_acceptable")

    assignment = (db.query(BatchChart)
                  .filter(BatchChart.batch_id == batch_id,
                          BatchChart.coder_name == payload.coder_name,
                          BatchChart.chart_id == payload.chart_id)
                  .first())
    if not assignment:
        raise HTTPException(status_code=404, detail=f"Chart {payload.chart_id} is not assigned to {payload.coder_name} in this batch")

    existing = (db.query(GradingResult)
                .filter(GradingResult.batch_id == batch_id,
                        GradingResult.coder_name == payload.coder_name,
                        GradingResult.chart_id == payload.chart_id)
                .first())
    if existing and not payload.regrade:
        return {"needs_confirmation": True, "existing_score": existing.total_score}

    total_score = _compute_ed_score(payload)
    pf = PassFail.PASS if total_score >= ED_PASS_THRESHOLD else PassFail.FAIL

    if existing:
        existing.total_score = total_score
        existing.pass_fail = pf
        existing.graded_at = datetime.utcnow()
        result = existing
        if result.ed_rubric:
            rubric = result.ed_rubric
            rubric.review_pass = payload.review_pass
            rubric.research_coding_pass = payload.research_coding_pass
            rubric.research_payer_pass = payload.research_payer_pass
            rubric.research_nuances_pass = payload.research_nuances_pass
            rubric.resolution_pass = payload.resolution_pass
            rubric.rationale_tier = payload.rationale_tier
            rubric.trainer_note = payload.trainer_note
            rubric.graded_by = payload.graded_by
            rubric.graded_at = datetime.utcnow()
        else:
            rubric = EDRubricDetail(
                result_id=result.id,
                review_pass=payload.review_pass,
                research_coding_pass=payload.research_coding_pass,
                research_payer_pass=payload.research_payer_pass,
                research_nuances_pass=payload.research_nuances_pass,
                resolution_pass=payload.resolution_pass,
                rationale_tier=payload.rationale_tier,
                trainer_note=payload.trainer_note,
                graded_by=payload.graded_by,
            )
            db.add(rubric)
    else:
        # Stable identity from the batch roster — see GradingResult.emp_id
        _emp = db.execute(text(
            "SELECT emp_id FROM batch_coders WHERE batch_id=:b AND coder_name=:n "
            "AND emp_id IS NOT NULL AND emp_id != '' LIMIT 1"
        ), {"b": batch_id, "n": payload.coder_name}).fetchone()

        result = GradingResult(
            batch_id=batch_id,
            submission_id=None,
            coder_name=payload.coder_name,
            emp_id=_emp[0] if _emp else None,
            chart_id=payload.chart_id,
            specialty=batch.specialty,
            total_score=total_score,
            pass_fail=pf,
        )
        db.add(result)
        db.flush()
        rubric = EDRubricDetail(
            result_id=result.id,
            review_pass=payload.review_pass,
            research_coding_pass=payload.research_coding_pass,
            research_payer_pass=payload.research_payer_pass,
            research_nuances_pass=payload.research_nuances_pass,
            resolution_pass=payload.resolution_pass,
            rationale_tier=payload.rationale_tier,
            trainer_note=payload.trainer_note,
            graded_by=payload.graded_by,
        )
        db.add(rubric)

    assignment.submission_status = SubmissionStatus.SUBMITTED
    db.commit()

    return {"graded": True, "total_score": total_score, "pass_fail": pf.value}


@router.get("/batches/{batch_id}/ed-grades")
def get_ed_grades(batch_id: int, db: Session = Depends(get_db)):
    """Return all manual rubric grades for an E&D batch, keyed by coder/chart."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _is_ed(batch.specialty):
        raise HTTPException(status_code=400, detail="This endpoint is only for Edits/Denials batches")

    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id)
               .all())

    out = []
    for r in results:
        rubric = r.ed_rubric if hasattr(r, 'ed_rubric') else None
        out.append({
            "result_id": r.id,
            "coder_name": r.coder_name,
            "chart_id": r.chart_id,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail.value if r.pass_fail else None,
            "graded_at": r.graded_at.isoformat() if r.graded_at else None,
            "rubric": {
                "review_pass": rubric.review_pass,
                "research_coding_pass": rubric.research_coding_pass,
                "research_payer_pass": rubric.research_payer_pass,
                "research_nuances_pass": rubric.research_nuances_pass,
                "resolution_pass": rubric.resolution_pass,
                "rationale_tier": rubric.rationale_tier,
                "trainer_note": rubric.trainer_note,
                "graded_by": rubric.graded_by,
            } if rubric else None,
        })
    return out
