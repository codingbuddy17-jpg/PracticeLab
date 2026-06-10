from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional, List
from database import get_db
from models import Chart, ChartStatus, Specialty, Difficulty
from schemas import ChartOut, ChartWithRationale, ChartUpdate, SearchParams
from services.chart_service import get_chart_pages, increment_view, log_audit
from config import settings

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/search", response_model=dict)
async def search_charts(
    q: Optional[str] = None,
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: ChartStatus = ChartStatus.ACTIVE,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chart).where(Chart.status == status)

    if q:
        q_upper = q.upper()
        stmt = stmt.where(
            or_(
                Chart.chart_number.ilike(f"%{q}%"),
                Chart.category.ilike(f"%{q}%"),
            )
        )
    if specialty:
        stmt = stmt.where(Chart.specialty == specialty)
    if category:
        stmt = stmt.where(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        stmt = stmt.where(Chart.difficulty == difficulty)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.order_by(Chart.chart_number).offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [ChartOut.model_validate(c) for c in results],
    }


@router.get("/categories", response_model=List[str])
async def get_categories(
    specialty: Optional[Specialty] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chart.category, func.count(Chart.id)).group_by(Chart.category)
    if specialty:
        stmt = stmt.where(Chart.specialty == specialty)
    stmt = stmt.order_by(func.count(Chart.id).desc())
    rows = (await db.execute(stmt)).all()
    return [r[0] for r in rows]


@router.get("/{chart_id}", response_model=ChartOut)
async def get_chart(chart_id: int, db: AsyncSession = Depends(get_db)):
    chart = await _get_or_404(chart_id, db)
    return ChartOut.model_validate(chart)


@router.get("/{chart_id}/pages")
async def get_chart_pages_endpoint(
    chart_id: int,
    viewer: str = Query(default="anonymous"),
    db: AsyncSession = Depends(get_db),
):
    chart = await _get_or_404(chart_id, db)
    await increment_view(db, chart_id)
    await db.commit()
    pages = await get_chart_pages(chart)
    return {"chart_number": chart.chart_number, "pages": pages}


@router.get("/{chart_id}/trainer", response_model=ChartWithRationale)
async def get_chart_trainer(chart_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Chart).where(Chart.id == chart_id)
    chart = (await db.execute(stmt)).scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return ChartWithRationale.model_validate(chart)


@router.patch("/{chart_id}", response_model=ChartOut)
async def update_chart(
    chart_id: int,
    payload: ChartUpdate,
    actor: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    chart = await _get_or_404(chart_id, db)
    changes = []
    if payload.category is not None:
        changes.append(f"category: {chart.category} → {payload.category}")
        chart.category = payload.category
    if payload.difficulty is not None:
        changes.append(f"difficulty: {chart.difficulty} → {payload.difficulty}")
        chart.difficulty = payload.difficulty
    if payload.rationale is not None:
        chart.rationale = payload.rationale
        changes.append("rationale updated")

    if changes:
        await log_audit(db, chart_id, "UPDATE", actor, "; ".join(changes))

    await db.commit()
    await db.refresh(chart)
    return ChartOut.model_validate(chart)


@router.post("/{chart_id}/retire")
async def retire_chart(
    chart_id: int,
    actor: str = Query(...),
    passphrase: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    chart = await _get_or_404(chart_id, db)

    if chart.uploaded_by != actor:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid master admin passphrase")

    chart.status = ChartStatus.RETIRED
    await log_audit(db, chart_id, "RETIRE", actor)
    await db.commit()
    return {"message": f"Chart {chart.chart_number} retired"}


@router.post("/{chart_id}/restore")
async def restore_chart(
    chart_id: int,
    actor: str = Query(...),
    passphrase: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chart).where(Chart.id == chart_id)
    chart = (await db.execute(stmt)).scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    if chart.uploaded_by != actor:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid master admin passphrase")

    chart.status = ChartStatus.ACTIVE
    await log_audit(db, chart_id, "RESTORE", actor)
    await db.commit()
    return {"message": f"Chart {chart.chart_number} restored"}


async def _get_or_404(chart_id: int, db: AsyncSession) -> Chart:
    from sqlalchemy.orm import selectinload
    stmt = select(Chart).options(selectinload(Chart.files)).where(
        Chart.id == chart_id, Chart.status == ChartStatus.ACTIVE
    )
    chart = (await db.execute(stmt)).scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart
