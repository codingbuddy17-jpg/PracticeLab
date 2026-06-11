from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime
import io
import openpyxl
from fastapi.responses import StreamingResponse
from database import get_db
from models import Chart, ChartStatus, Specialty, Difficulty

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    active = db.query(func.count(Chart.id)).filter(Chart.status == ChartStatus.ACTIVE).scalar()
    retired = db.query(func.count(Chart.id)).filter(Chart.status == ChartStatus.RETIRED).scalar()
    return {"active": active, "retired": retired, "total": active + retired}


@router.get("/charts")
def get_report(
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: Optional[ChartStatus] = None,
    uploaded_by: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Chart)
    query = _apply_filters(query, specialty, category, difficulty, status, uploaded_by, date_from, date_to)
    total = query.count()
    charts = query.order_by(Chart.chart_number).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [_chart_row(c) for c in charts],
    }


@router.get("/export")
def export_report(
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: Optional[ChartStatus] = None,
    uploaded_by: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Chart)
    query = _apply_filters(query, specialty, category, difficulty, status, uploaded_by, None, None)
    charts = query.order_by(Chart.chart_number).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Charts"
    ws.append(["Chart Number", "Specialty", "Category", "Difficulty", "Status", "Uploaded By", "Upload Date", "View Count"])

    for c in charts:
        ws.append([
            c.chart_number, c.specialty.value, c.category, c.difficulty.value,
            c.status.value, c.uploaded_by,
            c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
            c.view_count,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=charts_report.xlsx"},
    )


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    most_viewed = db.query(Chart.chart_number, Chart.specialty, Chart.category, Chart.view_count)\
        .filter(Chart.status == ChartStatus.ACTIVE)\
        .order_by(Chart.view_count.desc()).limit(10).all()

    least_viewed = db.query(Chart.chart_number, Chart.specialty, Chart.category, Chart.view_count)\
        .filter(Chart.status == ChartStatus.ACTIVE)\
        .order_by(Chart.view_count.asc()).limit(10).all()

    by_specialty = db.query(Chart.specialty, func.count(Chart.id), func.sum(Chart.view_count))\
        .filter(Chart.status == ChartStatus.ACTIVE)\
        .group_by(Chart.specialty).all()

    return {
        "most_viewed": [{"chart_number": r[0], "specialty": r[1], "category": r[2], "views": r[3]} for r in most_viewed],
        "least_viewed": [{"chart_number": r[0], "specialty": r[1], "category": r[2], "views": r[3]} for r in least_viewed],
        "by_specialty": [{"specialty": r[0], "chart_count": r[1], "total_views": r[2] or 0} for r in by_specialty],
    }


def _apply_filters(query, specialty, category, difficulty, status, uploaded_by, date_from, date_to):
    if specialty:
        query = query.filter(Chart.specialty == specialty)
    if category:
        query = query.filter(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        query = query.filter(Chart.difficulty == difficulty)
    if status:
        query = query.filter(Chart.status == status)
    if uploaded_by:
        query = query.filter(Chart.uploaded_by.ilike(f"%{uploaded_by}%"))
    if date_from:
        query = query.filter(Chart.created_at >= date_from)
    if date_to:
        query = query.filter(Chart.created_at <= date_to)
    return query


def _chart_row(c: Chart) -> dict:
    return {
        "id": c.id, "chart_number": c.chart_number, "specialty": c.specialty.value,
        "category": c.category, "difficulty": c.difficulty.value, "status": c.status.value,
        "uploaded_by": c.uploaded_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "view_count": c.view_count,
    }
