from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from database import get_db
from models import ChartFeedback, FeedbackStatus, Chart

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    chart_id: int
    reporter: str
    issues: list[str]
    notes: Optional[str] = None


class FeedbackOut(BaseModel):
    id: int
    chart_id: int
    chart_number: str
    reporter: str
    issues: str
    notes: Optional[str]
    status: FeedbackStatus
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("/", response_model=FeedbackOut)
def submit_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)):
    chart = db.query(Chart).filter(Chart.id == payload.chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    feedback = ChartFeedback(
        chart_id=payload.chart_id,
        chart_number=chart.chart_number,
        reporter=payload.reporter.strip() or "Anonymous",
        issues=", ".join(payload.issues),
        notes=payload.notes,
        status=FeedbackStatus.OPEN,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.get("/", response_model=dict)
def get_feedback(
    status: Optional[FeedbackStatus] = None,
    chart_number: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(ChartFeedback)
    if status:
        query = query.filter(ChartFeedback.status == status)
    if chart_number:
        query = query.filter(ChartFeedback.chart_number.ilike(f"%{chart_number}%"))

    total = query.count()
    items = query.order_by(ChartFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "page": page, "results": [FeedbackOut.model_validate(f) for f in items]}


@router.get("/unresolved-count")
def get_unresolved_count(db: Session = Depends(get_db)):
    count = db.query(func.count(ChartFeedback.id)).filter(ChartFeedback.status == FeedbackStatus.OPEN).scalar()
    return {"count": count}


@router.post("/{feedback_id}/resolve")
def resolve_feedback(
    feedback_id: int,
    resolver: str = Query(...),
    db: Session = Depends(get_db),
):
    fb = db.query(ChartFeedback).filter(ChartFeedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    fb.status = FeedbackStatus.RESOLVED
    fb.resolved_by = resolver
    fb.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Marked as resolved"}


@router.post("/{feedback_id}/reopen")
def reopen_feedback(feedback_id: int, db: Session = Depends(get_db)):
    fb = db.query(ChartFeedback).filter(ChartFeedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    fb.status = FeedbackStatus.OPEN
    fb.resolved_by = None
    fb.resolved_at = None
    db.commit()
    return {"message": "Reopened"}
