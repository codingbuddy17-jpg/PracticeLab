"""Scoring config and answer key endpoints."""
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Chart, ChartStatus, Specialty, AnswerKey, ScoringConfig, Batch, SelfPracticeSubmission
from services.excel_service import (
    generate_answer_key_template, generate_coder_list_template,
    parse_answer_key_upload, parse_coder_list,
)
from .shared import MASTER_PASSPHRASE

router = APIRouter()


def _parse_chart_specialty(specialty: Optional[str]) -> Optional[Specialty]:
    if not specialty:
        return None
    try:
        return Specialty(specialty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid specialty: {specialty}") from exc


# ── Coder list ────────────────────────────────────────────────────────────────

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


# ── Scoring config ────────────────────────────────────────────────────────────

def _get_or_default(db: Session, specialty_type: str):
    return db.query(ScoringConfig).filter(ScoringConfig.specialty_type == specialty_type).first()


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
    specialty_type: str
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
    if not payload.weighted_enabled and not payload.dpo_enabled:
        raise HTTPException(status_code=400, detail="At least one scoring method must be enabled")
    row.weighted_enabled = payload.weighted_enabled
    row.dpo_enabled = payload.dpo_enabled
    row.dpo_pass_threshold = payload.dpo_pass_threshold
    row.updated_by = payload.updated_by
    db.commit()
    return {"message": f"{stype} scoring config updated"}


# ── Answer keys ───────────────────────────────────────────────────────────────

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
    file_bytes = file.file.read()
    try:
        rows = parse_answer_key_upload(file_bytes, specialty)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

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
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    if not ak:
        raise HTTPException(status_code=404, detail="Answer key not found")
    db.delete(ak)
    db.commit()
    return {"message": "Answer key deleted"}


class ResetPayload(BaseModel):
    passphrase: str
    confirm: str  # must equal "RESET_ALL_DATA"


@router.post("/admin/reset-data")
def reset_all_data(payload: ResetPayload, db: Session = Depends(get_db)):
    """
    Wipe all batches (cascades to grading results, feedback, allocations)
    and all self-practice submissions. Charts, answer keys, scoring config
    and the coder list are preserved.
    """
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    if payload.confirm != "RESET_ALL_DATA":
        raise HTTPException(status_code=400, detail="confirm field must equal 'RESET_ALL_DATA'")

    sp_count = db.query(SelfPracticeSubmission).count()
    batch_count = db.query(Batch).count()

    db.query(SelfPracticeSubmission).delete(synchronize_session=False)
    db.query(Batch).delete(synchronize_session=False)
    db.commit()

    return {
        "message": "Reset complete. Charts, answer keys, and scoring config are intact.",
        "batches_deleted": batch_count,
        "self_practice_submissions_deleted": sp_count,
    }


@router.get("/answer-key/list")
def list_answer_keys(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    """Return every chart that has an answer key, with metadata for the admin list view."""
    q = db.query(AnswerKey, Chart).join(Chart, Chart.id == AnswerKey.chart_id)
    spec = _parse_chart_specialty(specialty)
    if spec:
        q = q.filter(Chart.specialty == spec)
    rows = q.order_by(Chart.chart_number).all()
    return [
        {
            "chart_id": chart.id,
            "chart_number": chart.chart_number,
            "specialty": chart.specialty.value,
            "category": chart.category,
            "entered_by": ak.entered_by,
            "created_at": ak.created_at.isoformat() if ak.created_at else None,
        }
        for ak, chart in rows
    ]


@router.get("/answer-key/missing")
def list_charts_without_keys(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    """Return active charts that have no answer key — purge candidates during testing."""
    from models import GradingResult
    q = (db.query(Chart)
         .filter(Chart.status == ChartStatus.ACTIVE)
         .outerjoin(AnswerKey, AnswerKey.chart_id == Chart.id)
         .filter(AnswerKey.id == None))  # noqa: E711
    spec = _parse_chart_specialty(specialty)
    if spec:
        q = q.filter(Chart.specialty == spec)
    charts = q.order_by(Chart.chart_number).all()
    result = []
    for c in charts:
        has_grading = db.query(GradingResult).filter(GradingResult.chart_id == c.id).first() is not None
        result.append({
            "chart_id": c.id,
            "chart_number": c.chart_number,
            "specialty": c.specialty.value,
            "category": c.category,
            "can_purge": not has_grading,
        })
    return result


@router.get("/answer-key/status")
def get_answer_key_status(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE)
    spec = _parse_chart_specialty(specialty)
    if spec:
        q = q.filter(Chart.specialty == spec)
    total = q.count()
    with_key = q.join(AnswerKey, AnswerKey.chart_id == Chart.id).count()
    return {"total_charts": total, "with_answer_key": with_key, "without_answer_key": total - with_key}
