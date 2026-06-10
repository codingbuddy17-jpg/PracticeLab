from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import io
import openpyxl
from fastapi.responses import StreamingResponse
from database import get_db
from models import Chart, ChartStatus, Specialty, Difficulty

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    active = (await db.execute(
        select(func.count(Chart.id)).where(Chart.status == ChartStatus.ACTIVE)
    )).scalar()
    retired = (await db.execute(
        select(func.count(Chart.id)).where(Chart.status == ChartStatus.RETIRED)
    )).scalar()
    return {"active": active, "retired": retired, "total": active + retired}


@router.get("/charts")
async def get_report(
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: Optional[ChartStatus] = None,
    uploaded_by: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chart)
    stmt = _apply_filters(stmt, specialty, category, difficulty, status, uploaded_by, date_from, date_to)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.order_by(Chart.chart_number).offset((page - 1) * page_size).limit(page_size)
    charts = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [_chart_row(c) for c in charts],
    }


@router.get("/export")
async def export_report(
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: Optional[ChartStatus] = None,
    uploaded_by: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chart)
    stmt = _apply_filters(stmt, specialty, category, difficulty, status, uploaded_by, date_from, date_to)
    stmt = stmt.order_by(Chart.chart_number)
    charts = (await db.execute(stmt)).scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Charts"
    headers = ["Chart Number", "Specialty", "Category", "Difficulty", "Status", "Uploaded By", "Upload Date", "View Count"]
    ws.append(headers)

    for c in charts:
        ws.append([
            c.chart_number,
            c.specialty.value,
            c.category,
            c.difficulty.value,
            c.status.value,
            c.uploaded_by,
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
async def get_analytics(db: AsyncSession = Depends(get_db)):
    most_viewed = (await db.execute(
        select(Chart.chart_number, Chart.specialty, Chart.category, Chart.view_count)
        .where(Chart.status == ChartStatus.ACTIVE)
        .order_by(Chart.view_count.desc())
        .limit(10)
    )).all()

    least_viewed = (await db.execute(
        select(Chart.chart_number, Chart.specialty, Chart.category, Chart.view_count)
        .where(Chart.status == ChartStatus.ACTIVE)
        .order_by(Chart.view_count.asc())
        .limit(10)
    )).all()

    by_specialty = (await db.execute(
        select(Chart.specialty, func.count(Chart.id), func.sum(Chart.view_count))
        .where(Chart.status == ChartStatus.ACTIVE)
        .group_by(Chart.specialty)
    )).all()

    return {
        "most_viewed": [{"chart_number": r[0], "specialty": r[1], "category": r[2], "views": r[3]} for r in most_viewed],
        "least_viewed": [{"chart_number": r[0], "specialty": r[1], "category": r[2], "views": r[3]} for r in least_viewed],
        "by_specialty": [{"specialty": r[0], "chart_count": r[1], "total_views": r[2] or 0} for r in by_specialty],
    }


def _apply_filters(stmt, specialty, category, difficulty, status, uploaded_by, date_from, date_to):
    if specialty:
        stmt = stmt.where(Chart.specialty == specialty)
    if category:
        stmt = stmt.where(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        stmt = stmt.where(Chart.difficulty == difficulty)
    if status:
        stmt = stmt.where(Chart.status == status)
    if uploaded_by:
        stmt = stmt.where(Chart.uploaded_by.ilike(f"%{uploaded_by}%"))
    if date_from:
        stmt = stmt.where(Chart.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Chart.created_at <= date_to)
    return stmt


def _chart_row(c: Chart) -> dict:
    return {
        "id": c.id,
        "chart_number": c.chart_number,
        "specialty": c.specialty.value,
        "category": c.category,
        "difficulty": c.difficulty.value,
        "status": c.status.value,
        "uploaded_by": c.uploaded_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "view_count": c.view_count,
    }
