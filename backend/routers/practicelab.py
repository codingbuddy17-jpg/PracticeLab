"""
PracticeLab API router — assessment module endpoints.
"""
import random
import io
from collections import Counter
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from pydantic import BaseModel
from database import get_db
from models import (
    Chart, ChartStatus, Specialty, Difficulty,
    AnswerKey, Batch, BatchCoder, BatchChart, BatchStatus, BatchAllocationCycle,
    Submission, GradingResult, GradingFeedback, SubmissionStatus,
    ScoringConfig, SelfPracticeSubmission, SelfPracticeResult,
)
from services.grading_engine import (
    grade_ip, grade_op, finalize_ip_score, cfg_from_db,
    compute_dpo_ip, compute_dpo_op,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
    DEFAULT_IP_CFG, DEFAULT_OP_CFG,
)
from services.excel_service import (
    generate_answer_key_template, generate_coder_sheet,
    generate_batch_zip, parse_answer_key_upload,
    parse_submission, export_batch_results,
    generate_coder_list_template, parse_coder_list,
    generate_self_practice_template,
)
from config import settings

router = APIRouter(prefix="/practicelab", tags=["practicelab"])

MASTER_PASSPHRASE = settings.MASTER_ADMIN_PASSPHRASE

# ── Specialties that use IP scoring ──────────────────────────────────────────

IP_SPECIALTIES = {Specialty.IP_DRG}


def _is_ip(specialty: Specialty) -> bool:
    return specialty in IP_SPECIALTIES


# ── Coder list endpoints ──────────────────────────────────────────────────────

@router.get("/coders/template")
def download_coder_list_template():
    data = generate_coder_list_template()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Coder_List_Template.xlsx"},
    )


@router.post("/coders/parse")
def parse_coder_list_upload(file: UploadFile = File(...)):
    """Parse uploaded coder list Excel, return [{name, emp_id}] for preview before batch creation."""
    try:
        coders = parse_coder_list(file.file.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")
    if not coders:
        raise HTTPException(status_code=400, detail="No valid rows found. Ensure Coder_Name and Emp_ID columns are filled.")
    return coders


# ── Scoring config endpoints ──────────────────────────────────────────────────

def _get_or_default(db: Session, specialty_type: str):
    row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == specialty_type).first()
    return row


@router.get("/config/scoring")
def get_scoring_configs(db: Session = Depends(get_db)):
    ip = _get_or_default(db, "IP")
    op = _get_or_default(db, "OP")
    def _serialize(row, stype):
        if not row:
            return None
        return {
            "specialty_type": stype,
            "pdx_weight": row.pdx_weight,
            "sdx_weight": row.sdx_weight,
            "pcs_weight": row.pcs_weight,
            "drg_weight": row.drg_weight,
            "cpt_weight": row.cpt_weight,
            "pass_threshold": row.pass_threshold,
            "drg_triggers": row.drg_triggers or [],
            "overcoding_penalty": row.overcoding_penalty,
            "weighted_enabled": getattr(row, "weighted_enabled", True),
            "dpo_enabled": getattr(row, "dpo_enabled", True),
            "dpo_pass_threshold": getattr(row, "dpo_pass_threshold", 80.0),
            "updated_by": row.updated_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    return {"IP": _serialize(ip, "IP"), "OP": _serialize(op, "OP")}


class ScoringConfigUpdate(BaseModel):
    specialty_type: str          # "IP" or "OP"
    pdx_weight: int
    sdx_weight: int
    pcs_weight: Optional[int] = None
    drg_weight: Optional[int] = None
    cpt_weight: Optional[int] = None
    pass_threshold: int
    drg_triggers: list[str] = []
    overcoding_penalty: bool = True
    weighted_enabled: bool = True
    dpo_enabled: bool = True
    dpo_pass_threshold: float = 80.0
    passphrase: str
    updated_by: str


@router.put("/config/scoring")
def update_scoring_config(payload: ScoringConfigUpdate, db: Session = Depends(get_db)):
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    stype = payload.specialty_type.upper()
    if stype not in ("IP", "OP"):
        raise HTTPException(status_code=400, detail="specialty_type must be IP or OP")

    # Validate weights sum to 100
    if stype == "IP":
        total = payload.pdx_weight + payload.sdx_weight + (payload.pcs_weight or 0) + (payload.drg_weight or 0)
    else:
        total = payload.pdx_weight + payload.sdx_weight + (payload.cpt_weight or 0)
    if total != 100:
        raise HTTPException(status_code=400, detail=f"Weights must sum to 100, got {total}")

    row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == stype).first()
    if not row:
        row = ScoringConfig(specialty_type=stype)
        db.add(row)

    row.pdx_weight = payload.pdx_weight
    row.sdx_weight = payload.sdx_weight
    row.pcs_weight = payload.pcs_weight
    row.drg_weight = payload.drg_weight
    row.cpt_weight = payload.cpt_weight
    row.pass_threshold = payload.pass_threshold
    row.drg_triggers = payload.drg_triggers
    row.overcoding_penalty = payload.overcoding_penalty
    # Validate method toggles — at least one must remain enabled
    if not payload.weighted_enabled and not payload.dpo_enabled:
        raise HTTPException(status_code=400, detail="At least one scoring method must be enabled")
    row.weighted_enabled = payload.weighted_enabled
    row.dpo_enabled = payload.dpo_enabled
    row.dpo_pass_threshold = payload.dpo_pass_threshold
    row.updated_by = payload.updated_by
    db.commit()
    return {"message": f"{stype} scoring config updated"}


# ── Answer Key endpoints ──────────────────────────────────────────────────────

@router.get("/answer-key/template")
def download_answer_key_template(specialty: str = Query(...)):
    """Download blank answer key Excel template (IP or OP)."""
    is_ip = specialty.upper() in ("IP", "IP-DRG")
    data = generate_answer_key_template("IP" if is_ip else "OP")
    filename = f"{'IP' if is_ip else 'OP'}_AnswerKey_Template.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/answer-key/upload")
def upload_answer_keys(
    file: UploadFile = File(...),
    specialty: str = Form(...),
    entered_by: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Upload a filled answer key Excel file.
    Stores one key per chart number — rejects duplicates unless passphrase provided.
    """
    file_bytes = file.file.read()
    rows = parse_answer_key_upload(file_bytes, specialty)

    stored, skipped, not_found = [], [], []

    for row in rows:
        chart_num = row["chart_number"]
        chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
        if not chart:
            not_found.append(chart_num)
            continue

        existing = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
        if existing:
            skipped.append(chart_num)
            continue

        ak = AnswerKey(
            chart_id=chart.id,
            specialty=chart.specialty,
            pdx_code=row.get("pdx_code", ""),
            pdx_poa=row.get("pdx_poa", ""),
            sdx=row.get("sdx", []),
            pcs=row.get("pcs", []),
            cpt=row.get("cpt", []),
            entered_by=entered_by,
        )
        db.add(ak)
        stored.append(chart_num)

    db.commit()
    return {"stored": stored, "skipped_duplicates": skipped, "not_found": not_found}


@router.delete("/answer-key/{chart_id}")
def delete_answer_key(
    chart_id: int,
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    """Delete an answer key — requires master admin passphrase."""
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    if not ak:
        raise HTTPException(status_code=404, detail="Answer key not found")
    db.delete(ak)
    db.commit()
    return {"message": "Answer key deleted"}


@router.get("/answer-key/status")
def get_answer_key_status(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    """Returns count of charts with and without answer keys, by specialty."""
    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE)
    if specialty:
        q = q.filter(Chart.specialty == specialty)
    total = q.count()
    with_key = q.join(AnswerKey, AnswerKey.chart_id == Chart.id).count()
    return {"total_charts": total, "with_answer_key": with_key, "without_answer_key": total - with_key}


# ── Batch endpoints ───────────────────────────────────────────────────────────

OPEN_BATCH_SOFT_LIMIT = 3


class CoderEntry(BaseModel):
    name: str
    emp_id: str


class BatchCreate(BaseModel):
    name: str
    specialty: str
    categories: list[str] = []
    difficulties: list[str] = []
    charts_per_coder: int = 5   # default per cycle
    coders: list[CoderEntry]
    created_by: str
    use_weighted: bool = True
    use_dpo: bool = False


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

    # Soft parallel limit check
    open_count = (db.query(Batch)
                  .filter(Batch.created_by == payload.created_by, Batch.status == BatchStatus.OPEN)
                  .count())
    warning = None
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
        notes=[],
        tags=[],
    )
    db.add(batch)
    db.flush()

    for coder in payload.coders:
        db.add(BatchCoder(batch_id=batch.id, coder_name=coder.name, emp_id=coder.emp_id))

    db.commit()
    return {"batch_id": batch.id, "name": batch.name, "warning": warning}


class AllocationRun(BaseModel):
    charts_per_coder: Optional[int] = None   # defaults to batch.charts_per_coder
    manual_chart_ids: list[int] = []
    run_by: str
    notes: Optional[str] = None


@router.post("/batches/{batch_id}/run-allocation")
def run_allocation(batch_id: int, payload: AllocationRun, db: Session = Depends(get_db)):
    """Run a new allocation cycle for an open batch. Excludes charts already assigned in prior cycles."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot run allocation")

    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    if not coders:
        raise HTTPException(status_code=400, detail="No coders in this batch")

    charts_per_coder = payload.charts_per_coder or batch.charts_per_coder
    if charts_per_coder < 1:
        raise HTTPException(status_code=400, detail="charts_per_coder must be at least 1")

    specialty = batch.specialty

    # Build per-coder sets of already-assigned chart_ids in this batch
    existing = db.query(BatchChart).filter(BatchChart.batch_id == batch_id).all()
    assigned_per_coder: dict[str, set] = {}
    for a in existing:
        assigned_per_coder.setdefault(a.coder_name, set()).add(a.chart_id)

    # Build chart pool (excluding previously assigned per coder happens inside the loop)
    if payload.manual_chart_ids:
        pool = (db.query(Chart)
                .join(AnswerKey, AnswerKey.chart_id == Chart.id)
                .filter(Chart.id.in_(payload.manual_chart_ids),
                        Chart.status == ChartStatus.ACTIVE)
                .all())
        if not pool:
            raise HTTPException(status_code=400, detail="None of the selected charts have answer keys or are active.")
    else:
        from sqlalchemy import or_
        q = (db.query(Chart)
             .join(AnswerKey, AnswerKey.chart_id == Chart.id)
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
        raise HTTPException(status_code=400, detail="No charts with answer keys match the batch pool filters.")

    # Create cycle record
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

    for coder in coders:
        already = assigned_per_coder.get(coder.coder_name, set())
        if payload.manual_chart_ids:
            # Manual: use exactly the selected charts, skip previously assigned ones
            available = [c for c in pool if c.id not in already]
            if not available:
                pool_warnings.append(f"{coder.coder_name}: all selected charts already assigned — skipped")
                continue
            assigned = available[:charts_per_coder]
        else:
            # Random: exclude already-assigned charts for this coder
            available = [c for c in pool if c.id not in already]
            pool_size = len(available)
            if pool_size == 0:
                pool_warnings.append(f"{coder.coder_name}: pool exhausted (all charts previously assigned)")
                continue
            shuffled = available.copy()
            random.shuffle(shuffled)
            # If pool is smaller than needed, we must wrap around (pool fully used up)
            assigned = (shuffled * ((charts_per_coder // pool_size) + 1))[:charts_per_coder]

        for chart in assigned:
            db.add(BatchChart(
                batch_id=batch_id,
                cycle_id=cycle.id,
                coder_name=coder.coder_name,
                chart_id=chart.id,
                submission_status=SubmissionStatus.PENDING,
            ))

        assigned_counts[coder.coder_name] = len(assigned)

    db.commit()
    return {
        "cycle_id": cycle.id,
        "cycle_number": cycle_number,
        "assigned": assigned_counts,
        "warnings": pool_warnings,
    }


class BatchClose(BaseModel):
    closed_by: str


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, payload: BatchClose, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is already closed")

    # Block close until all assigned charts are submitted and DRG reviews are resolved
    pending_submissions = (db.query(BatchChart)
                           .filter(BatchChart.batch_id == batch_id,
                                   BatchChart.submission_status == SubmissionStatus.PENDING)
                           .count())
    pending_drg = 0
    is_ip = str(batch.specialty.value).startswith("IP")
    if is_ip:
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


class BatchForceClose(BaseModel):
    closed_by: str
    passphrase: str
    reason: str


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


class BatchNoteAdd(BaseModel):
    text: str
    author: str


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
    """Super admin — all open batches across all trainers with allocation cycle counts."""
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
    """Search charts with answer keys for manual batch assignment."""
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid specialty: {specialty}")

    query = (db.query(Chart)
             .join(AnswerKey, AnswerKey.chart_id == Chart.id)
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
    """Live count of matching charts and how many have answer keys."""
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid specialty")

    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == spec)
    q_keyed = q.join(AnswerKey, AnswerKey.chart_id == Chart.id)

    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        if cats:
            from sqlalchemy import or_
            q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in cats]))
            q_keyed = q_keyed.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in cats]))

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
            q_keyed = q_keyed.filter(Chart.difficulty.in_(diffs))

    return {
        "total_matching": q.count(),
        "with_answer_key": q_keyed.count(),
    }


@router.get("/batches")
def list_batches(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Batch)
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
    is_ip = str(batch.specialty.value).startswith("IP")
    pending_drg_count = 0
    if is_ip:
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
                "assigned_count": sum(1 for a in assignments if a.cycle_id == c.id),
            }
            for c in cycles
        ],
        "coders": [{"name": c.coder_name, "emp_id": c.emp_id or "",
                    "excel_generated": c.excel_generated_at is not None,
                    "charts": coder_map.get(c.coder_name, [])} for c in coders],
    }


# ── Excel generation ──────────────────────────────────────────────────────────

def _build_excel_zip(batch: Batch, coders, assignments, label: str, db: Session):
    """Helper: build a ZIP of per-coder assessment sheets from a list of assignments."""
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
    """Download ZIP of all assignments across all cycles for a batch."""
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
    """Download ZIP for a specific allocation cycle (only that cycle's charts)."""
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


# ── Submission upload + grading ───────────────────────────────────────────────

@router.post("/batches/{batch_id}/grade")
def grade_submissions(
    batch_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload returned coder Excel files → auto-grade → store results."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot accept new submissions")

    # Load scoring configs
    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    graded, errors = [], []

    for upload in files:
        filename = upload.filename or "unknown"
        # Derive coder identity from filename.
        # Format is either "{emp_id}_{Name}_Assessment.xlsx" (when emp_id present)
        # or "{Name}_Assessment.xlsx". Look up by emp_id first so we get the exact
        # stored coder_name rather than reconstructing it from the stem.
        stem = filename.replace("_Assessment.xlsx", "")
        parts = stem.split("_", 1)
        coder_name: str = ""
        if len(parts) == 2:
            # Try treating parts[0] as an emp_id
            bc_by_emp = (db.query(BatchCoder)
                         .filter(BatchCoder.batch_id == batch_id,
                                 BatchCoder.emp_id == parts[0])
                         .first())
            if bc_by_emp:
                coder_name = bc_by_emp.coder_name
        if not coder_name:
            # Fall back: whole stem with underscores → spaces
            coder_name = stem.replace("_", " ").strip()

        try:
            file_bytes = upload.file.read()
            chart_submissions = parse_submission(file_bytes)

            for sub_data in chart_submissions:
                chart_num = sub_data["chart_number"]
                chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
                if not chart:
                    errors.append(f"{filename}: chart {chart_num} not found")
                    continue

                ak_rec = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
                if not ak_rec:
                    errors.append(f"{filename}: no answer key for {chart_num}")
                    continue

                # Skip if already graded for this coder+chart in this batch
                existing = (db.query(GradingResult)
                            .filter(GradingResult.batch_id == batch_id,
                                    GradingResult.coder_name == coder_name,
                                    GradingResult.chart_id == chart.id)
                            .first())
                if existing:
                    errors.append(f"{filename}: {chart_num} already graded for {coder_name} — skipped")
                    continue

                # Store submission
                sub = Submission(
                    batch_id=batch_id,
                    coder_name=coder_name,
                    chart_id=chart.id,
                    specialty=chart.specialty,
                    pdx_code=sub_data.get("pdx_code", ""),
                    pdx_poa=sub_data.get("pdx_poa", ""),
                    sdx=sub_data.get("sdx", []),
                    pcs=sub_data.get("pcs", []),
                    cpt=sub_data.get("cpt", []),
                )
                db.add(sub)
                db.flush()

                # Grade
                if _is_ip(chart.specialty):
                    ak = IPAnswerKey(
                        pdx_code=ak_rec.pdx_code or "",
                        pdx_poa=ak_rec.pdx_poa or "",
                        sdx=ak_rec.sdx or [],
                        pcs=ak_rec.pcs or [],
                    )
                    s = IPSubmission(
                        pdx_code=sub_data.get("pdx_code", ""),
                        pdx_poa=sub_data.get("pdx_poa", ""),
                        sdx=sub_data.get("sdx", []),
                        pcs=sub_data.get("pcs", []),
                    )
                    res = grade_ip(ak, s, ip_cfg)
                    gr = GradingResult(
                        batch_id=batch_id,
                        submission_id=sub.id,
                        coder_name=coder_name,
                        chart_id=chart.id,
                        specialty=chart.specialty,
                        pdx_score=res.pdx_score,
                        sdx_score=res.sdx_score,
                        pcs_score=res.pcs_score,
                        drg_flag=res.drg_flag,
                        drg_reviewed=False,
                    )
                else:
                    ak = OPAnswerKey(
                        pdx_code=ak_rec.pdx_code or "",
                        sdx=ak_rec.sdx or [],
                        cpt=ak_rec.cpt or [],
                    )
                    s = OPSubmission(
                        pdx_code=sub_data.get("pdx_code", ""),
                        sdx=sub_data.get("sdx", []),
                        cpt=sub_data.get("cpt", []),
                    )
                    res = grade_op(ak, s, op_cfg)
                    gr = GradingResult(
                        batch_id=batch_id,
                        submission_id=sub.id,
                        coder_name=coder_name,
                        chart_id=chart.id,
                        specialty=chart.specialty,
                        pdx_score=res.pdx_score,
                        sdx_score=res.sdx_score,
                        cpt_score=res.cpt_score,
                        total_score=res.total_score,
                        pass_fail=res.pass_fail,
                        drg_flag=False,
                        drg_reviewed=True,
                    )

                # DPO supplementary accuracy (runs independently of weighted)
                if batch.use_dpo:
                    penalty = (ip_cfg if _is_ip(chart.specialty) else op_cfg).overcoding_penalty
                    if _is_ip(chart.specialty):
                        dpo = compute_dpo_ip(
                            IPAnswerKey(
                                pdx_code=ak_rec.pdx_code or "",
                                pdx_poa=ak_rec.pdx_poa or "",
                                sdx=ak_rec.sdx or [],
                                pcs=ak_rec.pcs or [],
                            ),
                            IPSubmission(
                                pdx_code=sub_data.get("pdx_code", ""),
                                pdx_poa=sub_data.get("pdx_poa", ""),
                                sdx=sub_data.get("sdx", []),
                                pcs=sub_data.get("pcs", []),
                            ),
                            penalty,
                        )
                    else:
                        dpo = compute_dpo_op(
                            OPAnswerKey(
                                pdx_code=ak_rec.pdx_code or "",
                                sdx=ak_rec.sdx or [],
                                cpt=ak_rec.cpt or [],
                            ),
                            OPSubmission(
                                pdx_code=sub_data.get("pdx_code", ""),
                                sdx=sub_data.get("sdx", []),
                                cpt=sub_data.get("cpt", []),
                            ),
                            penalty,
                        )
                    gr.dpo_dx_accuracy = dpo.dx.accuracy
                    gr.dpo_poa_accuracy = dpo.poa.accuracy   # None for OP
                    gr.dpo_proc_accuracy = dpo.proc.accuracy
                    gr.dpo_overall_accuracy = dpo.overall_accuracy

                db.add(gr)
                db.flush()

                for fb in res.feedback:
                    db.add(GradingFeedback(
                        result_id=gr.id,
                        section=fb.section,
                        issue_type=fb.issue_type,
                        ak_code=fb.ak_code,
                        coder_code=fb.coder_code,
                        detail=fb.detail,
                    ))

                # Update submission status — update ALL matching rows in case of edge cases
                (db.query(BatchChart)
                   .filter(BatchChart.batch_id == batch_id,
                           BatchChart.coder_name == coder_name,
                           BatchChart.chart_id == chart.id)
                   .update({"submission_status": SubmissionStatus.SUBMITTED}))

                graded.append(f"{coder_name} / {chart_num}")

        except Exception as e:
            errors.append(f"{filename}: {str(e)}")

    db.commit()
    return {"graded": graded, "errors": errors}


# ── DRG Review endpoints ──────────────────────────────────────────────────────

@router.get("/batches/{batch_id}/drg-review")
def get_drg_review(batch_id: int, db: Session = Depends(get_db)):
    """Return all IP grading results pending DRG review for a batch."""
    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id,
                       GradingResult.drg_flag == True,
                       GradingResult.drg_reviewed == False)
               .join(Chart).all())
    return [
        {
            "result_id": r.id,
            "coder_name": r.coder_name,
            "chart_number": r.chart.chart_number,
            "specialty": r.specialty.value,
            "pdx_score": r.pdx_score,
            "sdx_score": r.sdx_score,
            "pcs_score": r.pcs_score,
            "drg_flag": r.drg_flag,
            "feedback": [
                {"section": f.section.value, "issue_type": f.issue_type.value,
                 "ak_code": f.ak_code, "coder_code": f.coder_code, "detail": f.detail}
                for f in r.feedback
            ],
        }
        for r in results
    ]


class DRGDecision(BaseModel):
    drg_error: bool   # True = DRG error (0 pts), False = DRG correct (40 pts)
    reviewer: str


@router.post("/results/{result_id}/drg-decision")
def submit_drg_decision(result_id: int, payload: DRGDecision, db: Session = Depends(get_db)):
    """Trainer submits DRG review decision for one result row."""
    gr = db.query(GradingResult).filter(GradingResult.id == result_id).first()
    if not gr:
        raise HTTPException(status_code=404, detail="Result not found")
    batch = db.query(Batch).filter(Batch.id == gr.batch_id).first()
    if batch and batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot modify results — batch is closed")

    gr.drg_override = "Y" if payload.drg_error else "N"
    gr.drg_reviewed = True

    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    drg_weight = (ip_cfg_row.drg_weight or 40) if ip_cfg_row else 40
    pass_threshold = (ip_cfg_row.pass_threshold or 80) if ip_cfg_row else 80
    total, pass_fail, drg_score = finalize_ip_score(
        gr.pdx_score, gr.sdx_score, gr.pcs_score or 0, payload.drg_error,
        drg_weight=drg_weight, pass_threshold=pass_threshold,
    )
    gr.drg_score = drg_score
    gr.total_score = total
    gr.pass_fail = pass_fail
    db.commit()

    pending = (db.query(GradingResult)
               .filter(GradingResult.batch_id == gr.batch_id,
                       GradingResult.drg_flag == True,
                       GradingResult.drg_reviewed == False)
               .count())
    db.commit()
    return {"result_id": result_id, "total_score": total, "pass_fail": pass_fail, "pending_drg": pending}


# ── Results and reporting ─────────────────────────────────────────────────────

@router.get("/batches/{batch_id}/results")
def get_batch_results(batch_id: int, db: Session = Depends(get_db)):
    """Full results for a batch — batch summary + per-coder + feedback."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id)
               .join(Chart).all())

    is_ip = _is_ip(batch.specialty)

    use_dpo = getattr(batch, "use_dpo", False)

    # Coder aggregation
    coder_map: dict[str, dict] = {}
    for r in results:
        name = r.coder_name
        if name not in coder_map:
            coder_map[name] = {
                "coder_name": name, "chart_count": 0,
                "pdx_sum": 0, "sdx_sum": 0, "pcs_sum": 0,
                "cpt_sum": 0, "drg_sum": 0, "total_sum": 0,
                "pass_count": 0, "charts": [],
                # DPO accumulators (sum of per-chart accuracy values)
                "dpo_dx_sum": 0, "dpo_dx_cnt": 0,
                "dpo_poa_sum": 0, "dpo_poa_cnt": 0,
                "dpo_proc_sum": 0, "dpo_proc_cnt": 0,
                "dpo_overall_sum": 0, "dpo_overall_cnt": 0,
            }
        d = coder_map[name]
        d["chart_count"] += 1
        d["pdx_sum"] += r.pdx_score or 0
        d["sdx_sum"] += r.sdx_score or 0
        d["pcs_sum"] += r.pcs_score or 0
        d["cpt_sum"] += r.cpt_score or 0
        d["drg_sum"] += r.drg_score or 0
        if r.total_score:
            d["total_sum"] += r.total_score
        if r.pass_fail == "PASS":
            d["pass_count"] += 1
        # DPO roll-up (only average non-None values)
        if r.dpo_dx_accuracy is not None:
            d["dpo_dx_sum"] += r.dpo_dx_accuracy; d["dpo_dx_cnt"] += 1
        if r.dpo_poa_accuracy is not None:
            d["dpo_poa_sum"] += r.dpo_poa_accuracy; d["dpo_poa_cnt"] += 1
        if r.dpo_proc_accuracy is not None:
            d["dpo_proc_sum"] += r.dpo_proc_accuracy; d["dpo_proc_cnt"] += 1
        if r.dpo_overall_accuracy is not None:
            d["dpo_overall_sum"] += r.dpo_overall_accuracy; d["dpo_overall_cnt"] += 1

        d["charts"].append({
            "chart_number": r.chart.chart_number,
            "pdx_score": r.pdx_score,
            "sdx_score": r.sdx_score,
            "pcs_score": r.pcs_score,
            "cpt_score": r.cpt_score,
            "drg_score": r.drg_score,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail,
            "drg_flag": r.drg_flag,
            "drg_reviewed": r.drg_reviewed,
            # DPO per-chart accuracies
            "dpo_dx_accuracy": r.dpo_dx_accuracy,
            "dpo_poa_accuracy": r.dpo_poa_accuracy,
            "dpo_proc_accuracy": r.dpo_proc_accuracy,
            "dpo_overall_accuracy": r.dpo_overall_accuracy,
            "feedback": [
                {"section": f.section.value, "issue_type": f.issue_type.value,
                 "ak_code": f.ak_code, "coder_code": f.coder_code, "detail": f.detail}
                for f in r.feedback
            ],
        })

    def _avg(s, c): return round(s / c, 1) if c else None

    coder_summaries = []
    for d in coder_map.values():
        cnt = d["chart_count"] or 1
        total_avg = round(d["total_sum"] / cnt, 1)
        coder_summaries.append({
            "coder_name": d["coder_name"],
            "chart_count": cnt,
            "avg_pdx": round(d["pdx_sum"] / cnt, 1),
            "avg_sdx": round(d["sdx_sum"] / cnt, 1),
            "avg_pcs": round(d["pcs_sum"] / cnt, 1) if is_ip else None,
            "avg_cpt": round(d["cpt_sum"] / cnt, 1) if not is_ip else None,
            "avg_drg": round(d["drg_sum"] / cnt, 1) if is_ip else None,
            "avg_total": total_avg,
            "pass_fail": "PASS" if d["pass_count"] > cnt / 2 else "FAIL",
            # DPO cumulative accuracy per coding area (None when DPO not used)
            "dpo_dx_accuracy": _avg(d["dpo_dx_sum"], d["dpo_dx_cnt"]),
            "dpo_poa_accuracy": _avg(d["dpo_poa_sum"], d["dpo_poa_cnt"]),
            "dpo_proc_accuracy": _avg(d["dpo_proc_sum"], d["dpo_proc_cnt"]),
            "dpo_overall_accuracy": _avg(d["dpo_overall_sum"], d["dpo_overall_cnt"]),
            "charts": d["charts"],
        })

    # Batch summary
    all_totals = [r.total_score for r in results if r.total_score is not None]
    passed_coders = sum(1 for c in coder_summaries if c["pass_fail"] == "PASS")
    total_coders = len(coder_summaries)

    # Top missed codes
    missed = {}
    for r in results:
        for f in r.feedback:
            if f.issue_type.value == "Missed" and f.ak_code:
                missed[f.ak_code] = missed.get(f.ak_code, 0) + 1
    top_missed = sorted(missed.items(), key=lambda x: -x[1])[:10]

    return {
        "batch_id": batch_id,
        "batch_name": batch.name,
        "specialty": batch.specialty.value,
        "status": batch.status.value,
        "is_ip": is_ip,
        "use_weighted": getattr(batch, "use_weighted", True),
        "use_dpo": use_dpo,
        "batch_summary": {
            "total_coders": total_coders,
            "passed": passed_coders,
            "failed": total_coders - passed_coders,
            "pass_rate": round(passed_coders / total_coders * 100, 1) if total_coders else 0,
            "avg_score": round(sum(all_totals) / len(all_totals), 1) if all_totals else 0,
            "top_missed_codes": [{"code": c, "count": n} for c, n in top_missed],
            "pending_drg_review": sum(1 for r in results if r.drg_flag and not r.drg_reviewed),
        },
        "coder_summaries": coder_summaries,
    }


@router.get("/batches/{batch_id}/results/export")
def export_results(batch_id: int, db: Session = Depends(get_db)):
    """Download batch results as Excel."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id)
               .join(Chart).all())

    rows = []
    for r in results:
        rows.append({
            "coder_name": r.coder_name,
            "chart_number": r.chart.chart_number,
            "specialty": r.specialty.value,
            "pdx_score": r.pdx_score,
            "sdx_score": r.sdx_score,
            "pcs_score": r.pcs_score,
            "cpt_score": r.cpt_score,
            "drg_score": r.drg_score,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail,
            "feedback": [
                {"section": f.section.value, "issue_type": f.issue_type.value,
                 "ak_code": f.ak_code, "coder_code": f.coder_code, "detail": f.detail}
                for f in r.feedback
            ],
        })

    excel_bytes = export_batch_results(batch.name, rows)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={batch.name.replace(' ','_')}_Results.xlsx"},
    )


# ── Batch Insights (A + B) ────────────────────────────────────────────────────

@router.get("/batches/{batch_id}/insights")
def get_batch_insights(batch_id: int, db: Session = Depends(get_db)):
    """Comprehensive post-grading insight summary for a batch."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id,
                       GradingResult.total_score.isnot(None))
               .join(Chart)
               .all())

    if not results:
        return {"has_data": False, "batch_name": batch.name, "specialty": batch.specialty.value}

    is_ip = _is_ip(batch.specialty)
    scores = [r.total_score for r in results]
    n_passed = sum(1 for r in results if r.pass_fail and r.pass_fail.value == "PASS")
    avg_score = round(sum(scores) / len(scores), 1)
    pass_rate = round(n_passed / len(results) * 100, 1)

    # Prior batch of same specialty for delta comparison
    prior = (db.query(Batch)
               .filter(Batch.specialty == batch.specialty,
                       Batch.id != batch_id,
                       Batch.status == BatchStatus.CLOSED)
               .order_by(Batch.created_at.desc())
               .first())
    prior_pass_rate = None
    pass_rate_delta = None
    prior_name = None
    if prior:
        prior_res = [r for r in prior.results if r.total_score is not None and r.pass_fail is not None]
        if prior_res:
            prior_passed = sum(1 for r in prior_res if r.pass_fail.value == "PASS")
            prior_pass_rate = round(prior_passed / len(prior_res) * 100, 1)
            pass_rate_delta = round(pass_rate - prior_pass_rate, 1)
            prior_name = prior.name

    # ── Team-level error patterns (B) ────────────────────────────────────────
    all_fb = [f for r in results for f in r.feedback]
    total_fb = len(all_fb)
    issue_counts = Counter(f.issue_type.value for f in all_fb)
    section_counts = Counter(f.section.value for f in all_fb)
    missed_counts = Counter(f.ak_code for f in all_fb if f.issue_type.value == "Missed" and f.ak_code)

    by_issue_type = [
        {"type": t, "count": c, "pct": round(c / total_fb * 100, 1) if total_fb else 0}
        for t, c in sorted(issue_counts.items(), key=lambda x: -x[1])
    ]
    by_section = [
        {"section": s, "count": c, "pct": round(c / total_fb * 100, 1) if total_fb else 0}
        for s, c in sorted(section_counts.items(), key=lambda x: -x[1])
    ]
    top_missed_codes = [{"code": c, "count": n} for c, n in missed_counts.most_common(7)]

    # ── Category performance (C foundation) ──────────────────────────────────
    cat_map: dict = {}
    for r in results:
        cat = r.chart.category
        if cat not in cat_map:
            cat_map[cat] = {"scores": [], "passed": 0, "total": 0}
        cat_map[cat]["scores"].append(r.total_score)
        cat_map[cat]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            cat_map[cat]["passed"] += 1

    category_performance = sorted([
        {
            "category": cat,
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "attempt_count": d["total"],
            "pass_rate": round(d["passed"] / d["total"] * 100, 1),
        }
        for cat, d in cat_map.items()
    ], key=lambda x: x["avg_score"])

    # ── Chart signals ─────────────────────────────────────────────────────────
    chart_map: dict = {}
    for r in results:
        cn = r.chart.chart_number
        if cn not in chart_map:
            chart_map[cn] = {"category": r.chart.category, "passed": 0, "total": 0}
        chart_map[cn]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            chart_map[cn]["passed"] += 1

    high_fail, all_pass_charts = [], []
    for cn, d in chart_map.items():
        fail_rate = round((d["total"] - d["passed"]) / d["total"] * 100, 1)
        if fail_rate >= 50 and d["total"] >= 2:
            high_fail.append({"chart_number": cn, "category": d["category"], "fail_rate": fail_rate, "coder_count": d["total"]})
        elif d["passed"] == d["total"] and d["total"] >= 2:
            all_pass_charts.append({"chart_number": cn, "category": d["category"], "coder_count": d["total"]})
    high_fail.sort(key=lambda x: -x["fail_rate"])

    # ── Per-coder insights (A + B) ────────────────────────────────────────────
    coder_results: dict = {}
    for r in results:
        cn = r.coder_name
        if cn not in coder_results:
            coder_results[cn] = {"scores": [], "passed": 0, "total": 0, "feedback": [], "section_errors": {}}
        coder_results[cn]["scores"].append(r.total_score)
        coder_results[cn]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            coder_results[cn]["passed"] += 1
        for f in r.feedback:
            coder_results[cn]["feedback"].append(f)
            sec = f.section.value
            coder_results[cn]["section_errors"][sec] = coder_results[cn]["section_errors"].get(sec, 0) + 1

    # Prior-batch scores per coder
    prior_coder_scores: dict = {}
    if prior:
        for r in prior.results:
            if r.total_score is not None:
                prior_coder_scores.setdefault(r.coder_name, []).append(r.total_score)

    coder_insights = []
    for cname, d in sorted(coder_results.items()):
        coder_avg = round(sum(d["scores"]) / len(d["scores"]), 1)
        fb = d["feedback"]
        total_coder_fb = len(fb)
        issue_c = Counter(f.issue_type.value for f in fb)
        error_profile = {
            t: {"count": c, "pct": round(c / total_coder_fb * 100, 1) if total_coder_fb else 0}
            for t, c in sorted(issue_c.items(), key=lambda x: -x[1])
        }
        missed_c = Counter(f.ak_code for f in fb if f.issue_type.value == "Missed" and f.ak_code)
        dominant_weakness = max(d["section_errors"], key=d["section_errors"].get) if d["section_errors"] else None
        prior_scores = prior_coder_scores.get(cname, [])
        prior_avg = round(sum(prior_scores) / len(prior_scores), 1) if prior_scores else None
        score_delta = round(coder_avg - prior_avg, 1) if prior_avg is not None else None

        coder_insights.append({
            "coder_name": cname,
            "total_graded": d["total"],
            "passed": d["passed"],
            "failed": d["total"] - d["passed"],
            "avg_score": coder_avg,
            "vs_team_avg": round(coder_avg - avg_score, 1),
            "prior_avg_score": prior_avg,
            "score_delta": score_delta,
            "dominant_weakness": dominant_weakness,
            "error_profile": error_profile,
            "section_errors": d["section_errors"],
            "top_missed_codes": [c for c, _ in missed_c.most_common(3)],
            "total_feedback_items": total_coder_fb,
        })

    return {
        "has_data": True,
        "batch_name": batch.name,
        "specialty": batch.specialty.value,
        "is_ip": is_ip,
        "batch_summary": {
            "total_graded": len(results),
            "passed": n_passed,
            "failed": len(results) - n_passed,
            "pass_rate": pass_rate,
            "avg_score": avg_score,
            "prior_batch_name": prior_name,
            "prior_batch_pass_rate": prior_pass_rate,
            "pass_rate_delta": pass_rate_delta,
        },
        "team_errors": {
            "total_feedback_items": total_fb,
            "by_issue_type": by_issue_type,
            "by_section": by_section,
            "top_missed_codes": top_missed_codes,
        },
        "category_performance": category_performance,
        "chart_signals": {
            "high_fail": high_fail[:6],
            "all_pass": all_pass_charts[:6],
        },
        "coder_insights": coder_insights,
    }


# ── Analytics endpoints ───────────────────────────────────────────────────────

@router.get("/analytics/overview")
def analytics_overview(db: Session = Depends(get_db)):
    """High-level counts across all batches."""
    total_batches = db.query(Batch).count()
    open_batches = db.query(Batch).filter(Batch.status == BatchStatus.OPEN).count()
    closed_batches = db.query(Batch).filter(Batch.status == BatchStatus.CLOSED).count()
    total_results = db.query(GradingResult).filter(GradingResult.total_score.isnot(None)).count()
    passed = db.query(GradingResult).filter(GradingResult.pass_fail == "PASS").count()
    return {
        "total_batches": total_batches,
        "open_batches": open_batches,
        "complete_batches": closed_batches,   # kept for frontend compat
        "total_graded": total_results,
        "total_passed": passed,
        "overall_pass_rate": round(passed / total_results * 100, 1) if total_results else 0,
    }


@router.get("/analytics/by-specialty")
def analytics_by_specialty(db: Session = Depends(get_db)):
    rows = (db.query(
                GradingResult.specialty,
                func.count(GradingResult.id).label("total"),
                func.avg(GradingResult.total_score).label("avg_score"),
                func.sum(
                    func.cast(GradingResult.pass_fail == "PASS", db.bind.dialect.name == "postgresql" and "int" or "integer")
                ).label("passed"),
            )
            .filter(GradingResult.total_score.isnot(None))
            .group_by(GradingResult.specialty)
            .all())
    return [
        {
            "specialty": r.specialty.value,
            "total": r.total,
            "avg_score": round(float(r.avg_score or 0), 1),
        }
        for r in rows
    ]


@router.get("/analytics/by-chart")
def analytics_by_chart(db: Session = Depends(get_db)):
    """Per-chart difficulty analytics — avg score, attempt count, top missed."""
    results = (db.query(GradingResult)
               .filter(GradingResult.total_score.isnot(None))
               .join(Chart).all())

    chart_map: dict[int, dict] = {}
    for r in results:
        cid = r.chart_id
        if cid not in chart_map:
            chart_map[cid] = {
                "chart_number": r.chart.chart_number,
                "specialty": r.chart.specialty.value,
                "category": r.chart.category,
                "scores": [], "missed": {},
            }
        chart_map[cid]["scores"].append(r.total_score)
        for f in r.feedback:
            if f.issue_type.value == "Missed" and f.ak_code:
                chart_map[cid]["missed"][f.ak_code] = chart_map[cid]["missed"].get(f.ak_code, 0) + 1

    return [
        {
            "chart_number": d["chart_number"],
            "specialty": d["specialty"],
            "category": d["category"],
            "attempt_count": len(d["scores"]),
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "top_missed": sorted(d["missed"].items(), key=lambda x: -x[1])[:5],
        }
        for d in sorted(chart_map.values(), key=lambda x: sum(x["scores"]) / len(x["scores"]))
    ]


@router.get("/analytics/by-batch")
def analytics_by_batch(db: Session = Depends(get_db)):
    batches = db.query(Batch).order_by(Batch.created_at.desc()).all()
    out = []
    for b in batches:
        results = [r for r in b.results if r.total_score is not None]
        if not results:
            continue
        scores = [r.total_score for r in results]
        passed = sum(1 for r in results if r.pass_fail == "PASS")
        out.append({
            "batch_id": b.id,
            "batch_name": b.name,
            "specialty": b.specialty.value,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "coder_count": len(set(r.coder_name for r in results)),
            "avg_score": round(sum(scores) / len(scores), 1),
            "pass_rate": round(passed / len(results) * 100, 1),
        })
    return out


@router.get("/analytics/coder-trend")
def coder_trend(coder_name: str, db: Session = Depends(get_db)):
    """Score trend over time for a specific coder across all batches."""
    results = (db.query(GradingResult)
               .filter(GradingResult.coder_name == coder_name,
                       GradingResult.total_score.isnot(None))
               .join(Batch)
               .order_by(Batch.created_at)
               .all())

    batch_scores: dict[int, dict] = {}
    for r in results:
        bid = r.batch_id
        if bid not in batch_scores:
            batch_scores[bid] = {
                "batch_name": r.batch.name,
                "created_at": r.batch.created_at.isoformat() if r.batch.created_at else None,
                "scores": [],
            }
        batch_scores[bid]["scores"].append(r.total_score)

    return [
        {
            "batch_id": bid,
            "batch_name": d["batch_name"],
            "created_at": d["created_at"],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
        }
        for bid, d in batch_scores.items()
    ]


# ── Self-Practice & Standalone Grading ───────────────────────────────────────

@router.get("/self-practice/template")
def download_self_practice_template():
    data = generate_self_practice_template()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="PracticeLab_SelfPractice_Template.xlsx"'},
    )


def _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg):
    """Grade a single chart submission, return (result_kwargs, feedback_items)."""
    is_ip = chart.specialty in IP_SPECIALTIES
    feedback_items = []

    if is_ip:
        ak = IPAnswerKey(
            pdx_code=ak_rec.pdx_code or "",
            pdx_poa=ak_rec.pdx_poa or "",
            sdx=ak_rec.sdx or [],
            pcs=ak_rec.pcs or [],
        )
        s = IPSubmission(
            pdx_code=sub_data.get("pdx_code", ""),
            pdx_poa=sub_data.get("pdx_poa", ""),
            sdx=sub_data.get("sdx", []),
            pcs=sub_data.get("pcs", []),
        )
        res = grade_ip(ak, s, ip_cfg)
        score = res.pdx_score + res.sdx_score + (res.pcs_score or 0)
        total_possible = ip_cfg.pdx_weight + ip_cfg.sdx_weight + ip_cfg.pcs_weight
        pct = round(score / total_possible * 100) if total_possible else 0
        passed = pct >= ip_cfg.pass_threshold
        for fb in res.feedback:
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code})
        dpo = compute_dpo_ip(ak, s, ip_cfg.overcoding_penalty)
        return {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "dpo_dx_accuracy": dpo.dx.accuracy,
            "dpo_poa_accuracy": dpo.poa.accuracy,
            "dpo_proc_accuracy": dpo.proc.accuracy,
            "dpo_overall_accuracy": dpo.overall_accuracy,
        }, feedback_items
    else:
        ak = OPAnswerKey(
            pdx_code=ak_rec.pdx_code or "",
            sdx=ak_rec.sdx or [],
            cpt=ak_rec.cpt or [],
        )
        s = OPSubmission(
            pdx_code=sub_data.get("pdx_code", ""),
            sdx=sub_data.get("sdx", []),
            cpt=sub_data.get("cpt", []),
        )
        res = grade_op(ak, s, op_cfg)
        score = res.pdx_score + res.sdx_score + (res.cpt_score or 0)
        total_possible = op_cfg.pdx_weight + op_cfg.sdx_weight + op_cfg.cpt_weight
        pct = round(score / total_possible * 100) if total_possible else 0
        passed = pct >= op_cfg.pass_threshold
        for fb in res.feedback:
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code})
        dpo = compute_dpo_op(ak, s, op_cfg.overcoding_penalty)
        return {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "dpo_dx_accuracy": dpo.dx.accuracy,
            "dpo_poa_accuracy": None,
            "dpo_proc_accuracy": dpo.proc.accuracy,
            "dpo_overall_accuracy": dpo.overall_accuracy,
        }, feedback_items


@router.post("/self-practice/submit")
def coder_self_practice_submit(
    coder_name: str = Form(...),
    emp_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Coder uploads completed self-practice sheets. Results held for trainer review."""
    if not coder_name.strip():
        raise HTTPException(400, "Coder name is required")
    if not emp_id.strip():
        raise HTTPException(400, "Emp ID is required")

    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    submission = SelfPracticeSubmission(
        coder_name=coder_name.strip(),
        emp_id=emp_id.strip(),
        source="coder",
        status="pending_review",
    )
    db.add(submission)
    db.flush()

    graded, errors = [], []

    for upload in files:
        try:
            chart_submissions = parse_submission(upload.file.read())
        except Exception as e:
            errors.append(f"{upload.filename}: could not parse — {e}")
            continue

        for sub_data in chart_submissions:
            chart_num = sub_data.get("chart_number", "").strip()
            if not chart_num or chart_num == "CHART_NUMBER":
                errors.append(f"{upload.filename}: tab has no valid chart number — rename tab to e.g. IP002")
                continue
            chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
            if not chart:
                errors.append(f"{chart_num}: chart not found in PracticeLab")
                continue
            ak_rec = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
            if not ak_rec:
                errors.append(f"{chart_num}: no answer key on file — trainer hasn't uploaded it yet")
                continue

            try:
                result_kwargs, feedback_items = _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg)
            except Exception as e:
                errors.append(f"{chart_num}: grading error — {e}")
                continue

            sp_result = SelfPracticeResult(
                submission_id=submission.id,
                chart_id=chart.id,
                chart_number=chart_num,
                specialty=chart.specialty,
                feedback_items=feedback_items,
                **result_kwargs,
            )
            db.add(sp_result)
            graded.append(chart_num)

    db.commit()
    return {
        "submission_id": submission.id,
        "graded": graded,
        "errors": errors,
    }


@router.get("/self-practice/queue")
def get_self_practice_queue(
    status: str = Query(default="pending_review"),
    db: Session = Depends(get_db),
):
    """Trainer view — list self-practice submissions pending review or all."""
    q = db.query(SelfPracticeSubmission).filter(SelfPracticeSubmission.source == "coder")
    if status != "all":
        q = q.filter(SelfPracticeSubmission.status == status)
    submissions = q.order_by(SelfPracticeSubmission.submitted_at.desc()).all()

    return [
        {
            "id": s.id,
            "coder_name": s.coder_name,
            "emp_id": s.emp_id,
            "status": s.status,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "reviewed_by": s.reviewed_by,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "trainer_feedback": s.trainer_feedback,
            "chart_count": len(s.results),
            "results": [
                {
                    "chart_number": r.chart_number,
                    "specialty": r.specialty.value if r.specialty else None,
                    "weighted_score": r.weighted_score,
                    "pass_fail": r.pass_fail.value if r.pass_fail else None,
                    "dpo_dx_accuracy": r.dpo_dx_accuracy,
                    "dpo_poa_accuracy": r.dpo_poa_accuracy,
                    "dpo_proc_accuracy": r.dpo_proc_accuracy,
                    "dpo_overall_accuracy": r.dpo_overall_accuracy,
                    "error_message": r.error_message,
                    "feedback_items": r.feedback_items or [],
                }
                for r in s.results
            ],
        }
        for s in submissions
    ]


class SPReviewPayload(BaseModel):
    trainer_feedback: str = ""
    reviewed_by: str


@router.post("/self-practice/{submission_id}/release")
def release_self_practice(submission_id: int, payload: SPReviewPayload, db: Session = Depends(get_db)):
    """Trainer adds feedback and releases results to coder."""
    sub = db.query(SelfPracticeSubmission).filter(SelfPracticeSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    sub.status = "released"
    sub.trainer_feedback = payload.trainer_feedback
    sub.reviewed_by = payload.reviewed_by
    sub.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Released"}


@router.post("/standalone/grade")
def standalone_grade(
    trainer_name: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Trainer uploads filled answer sheets for immediate grading (no batch needed)."""
    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    all_results = []
    errors = []

    for upload in files:
        filename = upload.filename or "unknown"
        stem = filename.replace("_Assessment.xlsx", "").replace(".xlsx", "")
        coder_name = stem.replace("_", " ").strip()

        try:
            chart_submissions = parse_submission(upload.file.read())
        except Exception as e:
            errors.append(f"{filename}: could not parse — {e}")
            continue

        submission = SelfPracticeSubmission(
            coder_name=coder_name,
            emp_id="",
            source="trainer",
            status="released",
            reviewed_by=trainer_name,
            reviewed_at=datetime.utcnow(),
        )
        db.add(submission)
        db.flush()

        for sub_data in chart_submissions:
            chart_num = sub_data.get("chart_number", "").strip()
            if not chart_num or chart_num == "CHART_NUMBER":
                errors.append(f"{filename}: tab missing chart number")
                continue
            chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
            if not chart:
                errors.append(f"{chart_num}: chart not found")
                continue
            ak_rec = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
            if not ak_rec:
                errors.append(f"{chart_num}: no answer key on file")
                continue

            try:
                result_kwargs, feedback_items = _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg)
            except Exception as e:
                errors.append(f"{chart_num}: grading error — {e}")
                continue

            sp_result = SelfPracticeResult(
                submission_id=submission.id,
                chart_id=chart.id,
                chart_number=chart_num,
                specialty=chart.specialty,
                feedback_items=feedback_items,
                **result_kwargs,
            )
            db.add(sp_result)
            all_results.append({
                "coder_name": coder_name,
                "chart_number": chart_num,
                "feedback_items": feedback_items,
                **result_kwargs,
            })

    db.commit()
    return {"results": all_results, "errors": errors}
