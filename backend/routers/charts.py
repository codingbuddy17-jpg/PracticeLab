from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from database import get_db
from models import Chart, ChartStatus, Specialty, Difficulty
from schemas import ChartOut, ChartWithRationale, ChartUpdate
from services.chart_service import get_chart_pages, increment_view, log_audit
from config import settings

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/search")
def search_charts(
    q: Optional[str] = None,
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: ChartStatus = ChartStatus.ACTIVE,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(Chart).filter(Chart.status == status)

    if q:
        query = query.filter(
            or_(Chart.chart_number.ilike(f"%{q}%"), Chart.category.ilike(f"%{q}%"))
        )
    if specialty:
        query = query.filter(Chart.specialty == specialty)
    if category:
        query = query.filter(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        query = query.filter(Chart.difficulty == difficulty)

    total = query.count()
    results = query.order_by(Chart.chart_number).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [ChartOut.model_validate(c) for c in results],
    }


@router.get("/categories")
def get_categories(specialty: Optional[Specialty] = None, db: Session = Depends(get_db)):
    query = db.query(Chart.category, func.count(Chart.id)).group_by(Chart.category)
    if specialty:
        query = query.filter(Chart.specialty == specialty)
    rows = query.order_by(func.count(Chart.id).desc()).all()
    return [r[0] for r in rows]


@router.get("/{chart_id}", response_model=ChartOut)
def get_chart(chart_id: int, db: Session = Depends(get_db)):
    return _get_or_404(chart_id, db)


@router.get("/{chart_id}/pages")
def get_chart_pages_endpoint(
    chart_id: int,
    viewer: str = Query(default="anonymous"),
    db: Session = Depends(get_db),
):
    chart = _get_or_404(chart_id, db)
    increment_view(db, chart_id)
    db.commit()
    pages = get_chart_pages(chart)
    return {"chart_number": chart.chart_number, "pages": pages}


@router.get("/{chart_id}/trainer", response_model=ChartWithRationale)
def get_chart_trainer(chart_id: int, db: Session = Depends(get_db)):
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return ChartWithRationale.model_validate(chart)


@router.patch("/{chart_id}", response_model=ChartOut)
def update_chart(
    chart_id: int,
    payload: ChartUpdate,
    actor: str = Query(...),
    db: Session = Depends(get_db),
):
    chart = _get_or_404(chart_id, db)
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
        log_audit(db, chart_id, "UPDATE", actor, "; ".join(changes))

    db.commit()
    db.refresh(chart)
    return ChartOut.model_validate(chart)


@router.post("/{chart_id}/retire")
def retire_chart(
    chart_id: int,
    actor: str = Query(...),
    passphrase: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    chart = _get_or_404(chart_id, db)
    if chart.uploaded_by != actor:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid master admin passphrase")
    chart.status = ChartStatus.RETIRED
    log_audit(db, chart_id, "RETIRE", actor)
    db.commit()
    return {"message": f"Chart {chart.chart_number} retired"}


@router.post("/{chart_id}/restore")
def restore_chart(
    chart_id: int,
    actor: str = Query(...),
    passphrase: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if chart.uploaded_by != actor:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid master admin passphrase")
    chart.status = ChartStatus.ACTIVE
    log_audit(db, chart_id, "RESTORE", actor)
    db.commit()
    return {"message": f"Chart {chart.chart_number} restored"}


def _get_or_404(chart_id: int, db: Session) -> Chart:
    chart = db.query(Chart).filter(
        Chart.id == chart_id, Chart.status == ChartStatus.ACTIVE
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart
