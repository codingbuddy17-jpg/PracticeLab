"""Batch CRUD, allocation cycles, and Excel export endpoints."""
import io
import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from database import get_db
from models import (
    Chart, ChartStatus, Specialty, Difficulty, AnswerKey,
    Batch, BatchCoder, BatchChart, BatchStatus, BatchAllocationCycle,
    GradingResult, SubmissionStatus,
)
from services.excel_service import generate_coder_sheet, generate_batch_zip
from services.randomisation_stats import compute_randomisation_stats
from config import settings
from .shared import MASTER_PASSPHRASE, _is_ip, _is_ed

router = APIRouter()

OPEN_BATCH_SOFT_LIMIT = 3


class CoderEntry(BaseModel):
    name: str
    emp_id: str


class BatchCreate(BaseModel):
    name: str
    specialty: str
    categories: list[str] = []
    difficulties: list[str] = []
    charts_per_coder: int = 5
    coders: list[CoderEntry]
    created_by: str
    use_weighted: bool = True
    use_dpo: bool = False
    is_direct_assignment: bool = False


class AllocationRun(BaseModel):
    charts_per_coder: Optional[int] = None
    manual_chart_ids: list[int] = []
    run_by: str
    notes: Optional[str] = None
    exclude_coders: list[str] = []


class BatchClose(BaseModel):
    closed_by: str


class BatchForceClose(BaseModel):
    closed_by: str
    passphrase: str
    reason: str


class BatchNoteAdd(BaseModel):
    text: str
    author: str


@router.post("/batches")
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    """Create an open batch with coders. Chart allocation is a separate step (run-allocation)."""
    try:
        specialty = Specialty(payload.specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid specialty: {payload.specialty}")

    if not payload.use_weighted and not payload.use_dpo:
        raise HTTPException(status_code=400, detail="At least one scoring method must be selected")

    if not payload.coders:
        raise HTTPException(status_code=400, detail="At least one coder is required")

    seen_names: set[str] = set()
    seen_emp_ids: set[str] = set()
    unique_coders, skipped_duplicates = [], []
    for coder in payload.coders:
        name = coder.name.strip()
        emp_id = (coder.emp_id or "").strip()
        if not name or name in seen_names or (emp_id and emp_id in seen_emp_ids):
            if name:
                skipped_duplicates.append(name)
            continue
        unique_coders.append((name, emp_id))
        seen_names.add(name)
        if emp_id:
            seen_emp_ids.add(emp_id)

    if not unique_coders:
        raise HTTPException(status_code=400, detail="At least one coder with a valid name is required")

    warning = None
    if not payload.is_direct_assignment:
        open_count = (db.query(Batch)
                      .filter(Batch.created_by == payload.created_by, Batch.status == BatchStatus.OPEN,
                              Batch.is_direct_assignment == False)
                      .count())
        if open_count >= OPEN_BATCH_SOFT_LIMIT:
            warning = f"You already have {open_count} open batch(es). Consider closing completed ones."

    batch = Batch(
        name=payload.name,
        specialty=specialty,
        categories=payload.categories,
        difficulties=payload.difficulties,
        charts_per_coder=payload.charts_per_coder,
        created_by=payload.created_by,
        status=BatchStatus.OPEN,
        use_weighted=payload.use_weighted,
        use_dpo=payload.use_dpo,
        is_direct_assignment=payload.is_direct_assignment,
        notes=[],
        tags=[],
    )
    db.add(batch)
    db.flush()

    for name, emp_id in unique_coders:
        db.add(BatchCoder(batch_id=batch.id, coder_name=name, emp_id=emp_id))

    db.commit()
    return {"batch_id": batch.id, "name": batch.name, "warning": warning, "skipped_duplicates": skipped_duplicates}


class AddCoders(BaseModel):
    coders: list[CoderEntry]


@router.post("/batches/{batch_id}/coders")
def add_coders_to_batch(batch_id: int, payload: AddCoders, db: Session = Depends(get_db)):
    """Add one or more coders to an open batch between allocation cycles."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Cannot add coders to a closed batch")

    existing_names = {c.coder_name for c in batch.coders}
    existing_emp_ids = {c.emp_id for c in batch.coders if c.emp_id}
    added, skipped = [], []
    for coder in payload.coders:
        name = coder.name.strip()
        emp_id = (coder.emp_id or "").strip()
        if not name:
            continue
        if name in existing_names or (emp_id and emp_id in existing_emp_ids):
            skipped.append(name)
        else:
            db.add(BatchCoder(batch_id=batch_id, coder_name=name, emp_id=emp_id))
            added.append(name)
            existing_names.add(name)  # prevent duplicates within same request
            if emp_id:
                existing_emp_ids.add(emp_id)

    db.commit()
    return {"added": added, "skipped_duplicates": skipped}


@router.post("/batches/{batch_id}/run-allocation")
def run_allocation(batch_id: int, payload: AllocationRun, db: Session = Depends(get_db)):
    """Run a new allocation cycle for an open batch. Excludes charts already assigned in prior cycles."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot run allocation")

    all_coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    if not all_coders:
        raise HTTPException(status_code=400, detail="No coders in this batch")
    excluded = {n.strip().lower() for n in payload.exclude_coders}
    coders = [c for c in all_coders if c.coder_name.strip().lower() not in excluded]
    if not coders:
        raise HTTPException(status_code=400, detail="All coders are excluded — uncheck at least one coder")

    charts_per_coder = payload.charts_per_coder or batch.charts_per_coder
    if charts_per_coder < 1:
        raise HTTPException(status_code=400, detail="charts_per_coder must be at least 1")

    specialty = batch.specialty

    existing = db.query(BatchChart).filter(BatchChart.batch_id == batch_id).all()
    assigned_per_coder: dict[str, set] = {}
    for a in existing:
        assigned_per_coder.setdefault(a.coder_name, set()).add(a.chart_id)

    if payload.manual_chart_ids:
        pool = (db.query(Chart)
                .filter(Chart.id.in_(payload.manual_chart_ids),
                        Chart.status == ChartStatus.ACTIVE,
                        Chart.specialty == specialty)
                .all())
        if not pool:
            raise HTTPException(status_code=400, detail="None of the selected charts are active or match this batch's specialty.")
    else:
        q = (db.query(Chart)
             .filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == specialty))

        if batch.categories:
            q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in batch.categories]))

        if batch.difficulties:
            diffs = []
            for d in batch.difficulties:
                try:
                    diffs.append(Difficulty(d))
                except ValueError:
                    pass
            if diffs:
                q = q.filter(Chart.difficulty.in_(diffs))

        pool = q.all()

    if not pool:
        raise HTTPException(status_code=400, detail="No active charts match the batch pool filters.")

    cycle_number = len(batch.allocation_cycles) + 1
    cycle = BatchAllocationCycle(
        batch_id=batch_id,
        cycle_number=cycle_number,
        run_by=payload.run_by,
        charts_per_coder=charts_per_coder,
        notes=payload.notes,
    )
    db.add(cycle)
    db.flush()

    assigned_counts = {}
    pool_warnings = []
    coder_chart_sets: dict[str, set] = {}   # for randomisation stats

    for coder in coders:
        already = assigned_per_coder.get(coder.coder_name, set())
        if payload.manual_chart_ids:
            available = [c for c in pool if c.id not in already]
            if not available:
                pool_warnings.append(f"{coder.coder_name}: all selected charts already assigned — skipped")
                continue
            random.shuffle(available)
            assigned = available[:charts_per_coder]
        else:
            available = [c for c in pool if c.id not in already]
            pool_size = len(available)
            if pool_size == 0:
                pool_warnings.append(f"{coder.coder_name}: pool exhausted (all charts previously assigned)")
                continue
            if pool_size < charts_per_coder:
                pool_warnings.append(
                    f"{coder.coder_name}: only {pool_size} chart(s) available in pool "
                    f"(requested {charts_per_coder}) — assigning all available"
                )
            shuffled = available.copy()
            random.shuffle(shuffled)
            assigned = shuffled[:charts_per_coder]  # never exceed available pool

        for chart in assigned:
            db.add(BatchChart(
                batch_id=batch_id,
                cycle_id=cycle.id,
                coder_name=coder.coder_name,
                chart_id=chart.id,
                submission_status=SubmissionStatus.PENDING,
            ))

        assigned_counts[coder.coder_name] = len(assigned)
        coder_chart_sets[coder.coder_name] = {c.id for c in assigned}

    # Compute and persist randomisation stats for this cycle
    rand_stats = compute_randomisation_stats(coder_chart_sets, len(pool))
    cycle.randomisation_stats = rand_stats

    db.commit()
    return {
        "cycle_id": cycle.id,
        "cycle_number": cycle_number,
        "assigned": assigned_counts,
        "warnings": pool_warnings,
        "randomisation_stats": rand_stats,
    }


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, payload: BatchClose, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is already closed")

    pending_submissions = (db.query(BatchChart)
                           .filter(BatchChart.batch_id == batch_id,
                                   BatchChart.submission_status == SubmissionStatus.PENDING)
                           .count())
    pending_drg = 0
    if _is_ip(batch.specialty):
        pending_drg = (db.query(GradingResult)
                       .filter(GradingResult.batch_id == batch_id,
                               GradingResult.drg_flag == True,
                               GradingResult.drg_reviewed == False)
                       .count())

    blockers = []
    if pending_submissions:
        blockers.append(f"{pending_submissions} chart(s) still pending submission")
    if pending_drg:
        blockers.append(f"{pending_drg} DRG review(s) unresolved")
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={"reason": "Cannot close batch — grading incomplete", "blockers": blockers},
        )

    batch.status = BatchStatus.CLOSED
    batch.closed_at = datetime.utcnow()
    batch.closed_by = payload.closed_by
    db.commit()
    return {"message": "Batch closed", "batch_id": batch_id}


@router.post("/batches/{batch_id}/force-close")
def force_close_batch(batch_id: int, payload: BatchForceClose, db: Session = Depends(get_db)):
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is already closed")
    batch.status = BatchStatus.CLOSED
    batch.closed_at = datetime.utcnow()
    batch.closed_by = payload.closed_by
    batch.force_closed = True
    batch.force_close_reason = payload.reason
    db.commit()
    return {"message": "Batch force-closed", "batch_id": batch_id}


@router.post("/batches/{batch_id}/notes")
def add_batch_note(batch_id: int, payload: BatchNoteAdd, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    notes = list(batch.notes or [])
    notes.append({"text": payload.text, "author": payload.author, "ts": datetime.utcnow().isoformat()})
    batch.notes = notes
    db.commit()
    return {"notes": batch.notes}


@router.get("/admin/open-batches")
def admin_open_batches(passphrase: str = Query(...), db: Session = Depends(get_db)):
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    batches = db.query(Batch).filter(Batch.status == BatchStatus.OPEN).order_by(Batch.created_at).all()
    now = datetime.utcnow()
    return [
        {
            "id": b.id,
            "name": b.name,
            "specialty": b.specialty.value,
            "created_by": b.created_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "days_open": (now - b.created_at.replace(tzinfo=None)).days if b.created_at else 0,
            "coder_count": len(b.coders),
            "allocation_cycles": len(b.allocation_cycles),
            "total_assigned": len(b.chart_assignments),
            "graded_count": db.query(GradingResult).filter(GradingResult.batch_id == b.id).count(),
        }
        for b in batches
    ]


@router.get("/batches/chart-search")
def chart_search_for_manual(
    specialty: str,
    q: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid specialty: {specialty}")

    query = (db.query(Chart)
             .filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == spec))

    if q:
        query = query.filter(Chart.chart_number.ilike(f"%{q}%"))
    if category:
        query = query.filter(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        try:
            query = query.filter(Chart.difficulty == Difficulty(difficulty))
        except ValueError:
            pass

    charts = query.order_by(Chart.chart_number).limit(100).all()
    return [
        {"id": c.id, "chart_number": c.chart_number, "specialty": c.specialty.value,
         "category": c.category, "difficulty": c.difficulty.value}
        for c in charts
    ]


@router.get("/batches/pool-preview")
def pool_preview(
    specialty: str,
    categories: Optional[str] = None,
    difficulties: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid specialty")

    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == spec)

    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        if cats:
            q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in cats]))

    if difficulties:
        diffs_raw = [d.strip() for d in difficulties.split(",") if d.strip()]
        diffs = []
        for d in diffs_raw:
            try:
                diffs.append(Difficulty(d))
            except ValueError:
                pass
        if diffs:
            q = q.filter(Chart.difficulty.in_(diffs))

    total = q.count()

    # E&D specialties don't use answer keys — skip that count entirely
    if _is_ed(spec):
        return {"total_matching": total, "with_answer_key": None}

    q_keyed = q.join(AnswerKey, AnswerKey.chart_id == Chart.id)
    return {
        "total_matching": total,
        "with_answer_key": q_keyed.count(),
    }


@router.get("/batches")
def list_batches(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    direct_only: bool = False,
    db: Session = Depends(get_db),
):
    if direct_only:
        q = db.query(Batch).filter(Batch.is_direct_assignment.is_(True))
    else:
        q = db.query(Batch).filter(Batch.is_direct_assignment.isnot(True))
    if status:
        q = q.filter(Batch.status == status)
    if specialty:
        try:
            q = q.filter(Batch.specialty == Specialty(specialty))
        except ValueError:
            pass
    batches = q.order_by(Batch.created_at.desc()).all()
    now = datetime.utcnow()
    return [
        {
            "id": b.id, "name": b.name, "specialty": b.specialty.value,
            "charts_per_coder": b.charts_per_coder, "status": b.status.value,
            "created_by": b.created_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "coder_count": len(b.coders),
            "allocation_cycles": len(b.allocation_cycles),
            "days_open": (now - b.created_at.replace(tzinfo=None)).days if b.created_at and b.status == BatchStatus.OPEN else None,
            "closed_at": b.closed_at.isoformat() if b.closed_at else None,
            "force_closed": b.force_closed,
            "tags": b.tags or [],
            "is_direct_assignment": b.is_direct_assignment,
        }
        for b in batches
    ]


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    assignments = (db.query(BatchChart)
                   .filter(BatchChart.batch_id == batch_id)
                   .join(Chart, Chart.id == BatchChart.chart_id).all())

    coder_map: dict[str, list] = {}
    for a in assignments:
        coder_map.setdefault(a.coder_name, []).append({
            "chart_id": a.chart_id,
            "chart_number": a.chart.chart_number,
            "specialty": a.chart.specialty.value,
            "category": a.chart.category,
            "difficulty": a.chart.difficulty.value,
            "submission_status": a.submission_status.value,
        })

    now = datetime.utcnow()
    cycles = db.query(BatchAllocationCycle).filter(BatchAllocationCycle.batch_id == batch_id).order_by(BatchAllocationCycle.cycle_number).all()

    pending_submissions_count = sum(1 for a in assignments if a.submission_status == SubmissionStatus.PENDING)
    pending_drg_count = 0
    if _is_ip(batch.specialty):
        pending_drg_count = (db.query(GradingResult)
                             .filter(GradingResult.batch_id == batch_id,
                                     GradingResult.drg_flag == True,
                                     GradingResult.drg_reviewed == False)
                             .count())

    return {
        "id": batch.id, "name": batch.name, "specialty": batch.specialty.value,
        "categories": batch.categories, "difficulties": batch.difficulties,
        "charts_per_coder": batch.charts_per_coder, "status": batch.status.value,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "use_weighted": getattr(batch, "use_weighted", True),
        "use_dpo": getattr(batch, "use_dpo", False),
        "closed_at": batch.closed_at.isoformat() if batch.closed_at else None,
        "closed_by": batch.closed_by,
        "force_closed": batch.force_closed,
        "force_close_reason": batch.force_close_reason,
        "days_open": (now - batch.created_at.replace(tzinfo=None)).days if batch.created_at and batch.status == BatchStatus.OPEN else None,
        "notes": batch.notes or [],
        "tags": batch.tags or [],
        "pending_submissions": pending_submissions_count,
        "pending_drg_review": pending_drg_count,
        "allocation_cycles": [
            {
                "id": c.id, "cycle_number": c.cycle_number,
                "run_at": c.run_at.isoformat() if c.run_at else None,
                "run_by": c.run_by,
                "charts_per_coder": c.charts_per_coder,
                "notes": c.notes,
                "assigned_count": sum(
                    1 for a in assignments
                    if a.cycle_id == c.id or (a.cycle_id is None and c.cycle_number == 1)
                ),
                "randomisation_stats": c.randomisation_stats,
            }
            for c in cycles
        ],
        "coders": [{"name": c.coder_name, "emp_id": c.emp_id or "",
                    "excel_generated": c.excel_generated_at is not None,
                    "charts": coder_map.get(c.coder_name, [])} for c in coders],
    }


def _build_excel_zip(batch: Batch, coders, assignments, label: str, db: Session):
    """Build a ZIP of per-coder assessment sheets from a list of assignments."""
    coder_charts: dict[str, list] = {}
    for a in assignments:
        chart_url = f"{settings.FRONTEND_URL}/chart/{a.chart.chart_number}" if hasattr(settings, "FRONTEND_URL") else ""
        coder_charts.setdefault(a.coder_name, []).append({
            "chart_number": a.chart.chart_number,
            "specialty": a.chart.specialty.value,
            "category": a.chart.category,
            "difficulty": a.chart.difficulty.value,
            "chart_url": chart_url,
        })

    coder_map = {c.coder_name: c for c in coders}
    coder_files = []
    for coder_name, charts in coder_charts.items():
        coder = coder_map.get(coder_name)
        emp = (coder.emp_id or "").replace(" ", "_") if coder else ""
        excel_bytes = generate_coder_sheet(coder_name, label, charts, emp_id=emp)
        safe_name = coder_name.replace(" ", "_")
        filename = f"{emp}_{safe_name}_Assessment.xlsx" if emp else f"{safe_name}_Assessment.xlsx"
        coder_files.append((filename, excel_bytes))
        if coder:
            coder.excel_generated_at = datetime.utcnow()

    db.commit()
    return generate_batch_zip(coder_files)


@router.get("/batches/{batch_id}/generate-excel")
def generate_excel(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    assignments = db.query(BatchChart).filter(BatchChart.batch_id == batch_id).join(Chart).all()
    zip_bytes = _build_excel_zip(batch, coders, assignments, batch.name, db)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={batch.name.replace(' ','_')}_All_Assessments.zip"},
    )


@router.get("/batches/{batch_id}/cycles/{cycle_id}/generate-excel")
def generate_cycle_excel(batch_id: int, cycle_id: int, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    cycle = db.query(BatchAllocationCycle).filter(
        BatchAllocationCycle.id == cycle_id,
        BatchAllocationCycle.batch_id == batch_id
    ).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    assignments = db.query(BatchChart).filter(
        BatchChart.batch_id == batch_id,
        BatchChart.cycle_id == cycle_id
    ).join(Chart).all()
    label = f"{batch.name} — Cycle {cycle.cycle_number}"
    zip_bytes = _build_excel_zip(batch, coders, assignments, label, db)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={batch.name.replace(' ','_')}_Cycle{cycle.cycle_number}_Assessments.zip"},
    )
