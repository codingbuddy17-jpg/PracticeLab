from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from database import get_db
from models import Chart, ChartFile, ChartStatus, Specialty, Difficulty, AnswerKey, GradingResult, ChartFeedback, FeedbackStatus
from schemas import ChartOut, ChartWithRationale, ChartUpdate
from services.chart_service import get_chart_pages, increment_view, log_audit
from services.em_audit_key import chart_ids_with_keys as em_key_chart_ids
from services.storage import open_object
from config import settings

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/stats")
def get_chart_stats(db: Session = Depends(get_db)):
    """Quick stats for the TrainerHome dashboard."""
    total_charts = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE).count()
    open_feedback = db.query(ChartFeedback).filter(ChartFeedback.status == FeedbackStatus.OPEN).count()
    # The names, not just the count. The home page listed them from a
    # hardcoded string that had gone stale — it named ICD-10, which is a code
    # set rather than a specialty, and predated Surgery and ED Single Path.
    spec_rows = (db.query(Chart.specialty, func.count(Chart.id))
                   .filter(Chart.status == ChartStatus.ACTIVE)
                   .group_by(Chart.specialty)
                   .all())
    specialties = sorted(
        [{"specialty": r[0].value, "charts": r[1]} for r in spec_rows if r[0]],
        key=lambda x: -x["charts"])

    # Charts with no answer key cannot be practised on, so this is inventory
    # that looks like capacity until someone tries to build a batch from it.
    from models import AnswerKey
    keyed = (db.query(func.count(func.distinct(AnswerKey.chart_id)))
               .join(Chart, Chart.id == AnswerKey.chart_id)
               .filter(Chart.status == ChartStatus.ACTIVE).scalar() or 0)

    return {
        "total_charts": total_charts,
        "open_feedback": open_feedback,
        "total_specialties": len(specialties),
        "specialties": specialties,
        "charts_with_keys": keyed,
        "charts_without_keys": max(0, total_charts - keyed),
    }


@router.get("/search")
def search_charts(
    q: Optional[str] = None,
    specialty: Optional[Specialty] = None,
    category: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    status: ChartStatus = ChartStatus.ACTIVE,
    answer_key_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    # Difficulty is trainer metadata: it exists so a trainer can match work to a
    # coder's level and build a balanced set. Sent to a coder it either excuses
    # a poor result or seeds doubt about a good one, so it leaves the server
    # only when a trainer screen asks for it — off by default, because the
    # default is what the coder-facing library gets.
    include_trainer_fields: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Chart).filter(Chart.status == status)

    if q:
        query = query.filter(
            or_(Chart.chart_number.ilike(f"%{q}%"), Chart.category.ilike(f"%{q}%"), Chart.alias.ilike(f"%{q}%"))
        )
    if specialty:
        query = query.filter(Chart.specialty == specialty)
    if category:
        query = query.filter(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        query = query.filter(Chart.difficulty == difficulty)
    if answer_key_status in ("with_key", "missing_key"):
        # Both tables, for the same reason as the badge below: filtering on
        # answer_keys alone puts every keyed E/M chart under "Missing".
        em_keyed = em_key_chart_ids(db, [c.id for c in query.with_entities(Chart.id).all()])
        keyed = db.query(AnswerKey.chart_id)
        if answer_key_status == "with_key":
            query = query.filter(or_(Chart.id.in_(keyed),
                                     Chart.id.in_(em_keyed or [-1])))
        else:
            query = query.filter(~Chart.id.in_(keyed),
                                 ~Chart.id.in_(em_keyed or [-1]))

    total = query.count()
    results = query.order_by(Chart.chart_number).offset((page - 1) * page_size).limit(page_size).all()
    page_ids = [c.id for c in results]
    keyed_ids = {
        row[0]
        for row in db.query(AnswerKey.chart_id)
        .filter(AnswerKey.chart_id.in_(page_ids or [-1]))
        .all()
    }
    # E/M and ED Profee keep their key in em_answer_keys — no ORM model, no row
    # in answer_keys — so the join above reports every E/M chart as unkeyed.
    # That told a trainer who had just entered five keys that the library held
    # none of them.
    keyed_ids |= em_key_chart_ids(db, page_ids)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [
            _visible(ChartOut.model_validate(c).model_dump(mode="json"),
                     c.id in keyed_ids, include_trainer_fields)
            for c in results
        ],
    }


def _visible(row: dict, has_key: bool, trainer: bool) -> dict:
    """One chart row, with trainer-only fields dropped unless asked for."""
    row["has_answer_key"] = has_key
    if not trainer:
        row.pop("difficulty", None)
    return row


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


@router.get("/{chart_id}/page/{page_order}")
def proxy_chart_page(chart_id: int, page_order: int, db: Session = Depends(get_db)):
    chart = _get_or_404(chart_id, db)
    file = next((f for f in chart.files if f.page_order == page_order), None)
    if not file:
        raise HTTPException(status_code=404, detail="Page not found")
    # The API fetches from storage and streams the bytes back; the browser
    # never contacts the bucket. That is what lets the bucket stay private,
    # need no CORS, and be reachable only from the backend.
    body, content_type = open_object(file.storage_key)
    return StreamingResponse(body, media_type=content_type, headers={
        "Cache-Control": "private, max-age=3600",
    })


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
    passphrase: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    chart = _get_or_404(chart_id, db)
    if chart.uploaded_by != actor:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid passphrase")
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
    if payload.alias is not None:
        changes.append(f"alias: {chart.alias or '—'} → {payload.alias or '—'}")
        chart.alias = payload.alias or None

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
            raise HTTPException(status_code=403, detail="Invalid passphrase")
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
            raise HTTPException(status_code=403, detail="Invalid passphrase")
    chart.status = ChartStatus.ACTIVE
    log_audit(db, chart_id, "RESTORE", actor)
    db.commit()
    return {"message": f"Chart {chart.chart_number} restored"}


@router.delete("/{chart_id}/purge")
def purge_chart(
    chart_id: int,
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Hard-delete a chart and its associated files.
    Only allowed when the chart has no answer key and no grading history —
    i.e. it was uploaded as a test/placeholder and never used in practice.
    Requires the master admin passphrase.
    """
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    chart = _get_or_404(chart_id, db)

    has_ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    if has_ak:
        raise HTTPException(
            status_code=409,
            detail="Chart has an answer key — delete the answer key first, then purge the chart.",
        )

    graded = db.query(GradingResult).filter(GradingResult.chart_id == chart_id).first()
    if graded:
        raise HTTPException(
            status_code=409,
            detail="Chart has grading history and cannot be purged. Retire it instead.",
        )

    chart_number = chart.chart_number
    db.query(ChartFile).filter(ChartFile.chart_id == chart_id).delete()
    db.delete(chart)
    db.commit()
    return {"message": f"Chart {chart_number} permanently deleted"}


@router.get("/{chart_id}/text-search")
def search_in_chart(
    chart_id: int,
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Return page numbers where the search term appears in extracted text."""
    files = db.query(ChartFile).filter(
        ChartFile.chart_id == chart_id,
        ChartFile.page_text.isnot(None),
        ChartFile.page_text.ilike(f"%{q}%"),
    ).order_by(ChartFile.page_order).all()

    return {
        "query": q,
        "matching_pages": [f.page_order for f in files],
        "total_matches": len(files),
    }


def _get_or_404(chart_id: int, db: Session) -> Chart:
    chart = db.query(Chart).filter(
        Chart.id == chart_id, Chart.status == ChartStatus.ACTIVE
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart
