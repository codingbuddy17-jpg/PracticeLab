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
    parse_answer_key_upload, parse_coder_list, export_all_answer_keys,
)
from services.grading_engine import cfg_from_db, DEFAULT_IP_CFG, DEFAULT_OP_CFG
from services.chart_service import log_audit
from .shared import (MASTER_PASSPHRASE, _is_ip, _is_ed, ED_SPECIALTIES,
                     _uses_pointers, _is_single_path, _is_dx_only)

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
    # Professional claims get a Dx-pointer column per CPT line
    try:
        _spec = Specialty(specialty)
        with_pointers = _uses_pointers(_spec)
        single_path = _is_single_path(_spec)
        dx_only = _is_dx_only(_spec)
    except ValueError:
        with_pointers = single_path = dx_only = False
    data = generate_answer_key_template("IP" if is_ip else "OP",
                                        with_pointers=with_pointers,
                                        single_path=single_path, dx_only=dx_only)
    # Name the file after the specialty. Every non-IP template used to download
    # as "OP_AnswerKey_Template.xlsx", so a trainer juggling Surgery, Ancillary
    # and ED Single Path templates had four identically-named files.
    safe = "".join(ch if ch.isalnum() else "_" for ch in specialty).strip("_") or "AnswerKey"
    filename = f"{safe}_AnswerKey_Template.xlsx"
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
    replace: bool = Form(False),
    passphrase: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        spec_enum = Specialty(specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid specialty")
    if _is_ed(spec_enum):
        raise HTTPException(status_code=400, detail="Answer keys are not used for Edits or Denials — grading is performed manually via the rubric.")

    if replace and passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    file_bytes = file.file.read()
    try:
        # parse_answer_key_upload switches layout on the literal "IP"/"OP",
        # so translate from the real specialty rather than trusting the caller.
        rows = parse_answer_key_upload(file_bytes,
                                       "IP" if _is_ip(spec_enum) else "OP",
                                       with_pointers=_uses_pointers(spec_enum),
                                       single_path=_is_single_path(spec_enum),
                                       dx_only=_is_dx_only(spec_enum))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    is_ip_upload = _is_ip(spec_enum)
    stored, replaced, skipped, not_found, wrong_specialty = [], [], [], [], []

    for row in rows:
        chart_num = row["chart_number"]
        chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
        if not chart:
            not_found.append(chart_num)
            continue

        # Exact match, not just IP-vs-OP. Layouts differ per specialty (pointer
        # columns, single-path levels, Dx-only), so an ED Facility file uploaded
        # against Surgery charts would previously be accepted and silently
        # mis-parsed.
        if chart.specialty != spec_enum:
            wrong_specialty.append(chart_num)
            continue

        existing = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
        if existing:
            if replace:
                existing.pdx_code = row.get("pdx_code", "")
                existing.pdx_poa = row.get("pdx_poa", "")
                existing.sdx = row.get("sdx", [])
                existing.pcs = row.get("pcs", [])
                existing.cpt = row.get("cpt", [])
                existing.facility_level = row.get("facility_level") or None
                existing.profee_level = row.get("profee_level") or None
                existing.entered_by = entered_by
                replaced.append(chart_num)
            else:
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
            facility_level=row.get("facility_level") or None,
            profee_level=row.get("profee_level") or None,
            entered_by=entered_by,
        )
        db.add(ak)
        stored.append(chart_num)

    db.commit()
    return {
        "stored": stored, "replaced": replaced, "skipped_duplicates": skipped,
        "not_found": not_found, "wrong_specialty": wrong_specialty,
    }


@router.get("/answer-key/export")
def export_answer_keys(
    passphrase: str = Query(...),
    specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    q = db.query(AnswerKey, Chart).join(Chart, Chart.id == AnswerKey.chart_id)
    spec = _parse_chart_specialty(specialty)
    if spec:
        q = q.filter(Chart.specialty == spec)
    rows = q.order_by(Chart.chart_number).all()
    data = export_all_answer_keys(rows)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=answer_keys_export.xlsx"},
    )


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


# ── In-interface answer key editing ──────────────────────────────────────────

class AnswerKeyPayload(BaseModel):
    pdx_code: str = ""
    pdx_poa: Optional[str] = ""
    sdx: list[dict] = []
    pcs: list[dict] = []
    cpt: list[dict] = []
    facility_level: Optional[str] = None
    profee_level: Optional[str] = None
    entered_by: str
    passphrase: str = ""
    regrade_closed: bool = False   # closed batches are frozen unless forced


@router.get("/answer-key/{chart_id}/detail")
def get_answer_key_detail(chart_id: int, db: Session = Depends(get_db)):
    """Fetch one answer key for in-interface editing."""
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    return {
        "chart_id": chart_id,
        "chart_number": chart.chart_number,
        "specialty": chart.specialty.value,
        "category": chart.category,
        "exists": ak is not None,
        "is_ip": _is_ip(chart.specialty),
        "uses_pointers": _uses_pointers(chart.specialty),
        "single_path": _is_single_path(chart.specialty),
        "pdx_code": ak.pdx_code if ak else "",
        "pdx_poa": ak.pdx_poa if ak else "",
        "sdx": (ak.sdx or []) if ak else [],
        "pcs": (ak.pcs or []) if ak else [],
        "cpt": (ak.cpt or []) if ak else [],
        "facility_level": ak.facility_level if ak else None,
        "profee_level": ak.profee_level if ak else None,
        "entered_by": ak.entered_by if ak else None,
    }


@router.get("/answer-key/{chart_id}/impact")
def get_answer_key_impact(chart_id: int, db: Session = Depends(get_db)):
    """What already-graded work a key change would rewrite. Shown before saving."""
    from .chart_grading import chart_regrade_impact
    return chart_regrade_impact(db, chart_id)


@router.put("/answer-key/{chart_id}")
def upsert_answer_key_inline(chart_id: int, payload: AnswerKeyPayload,
                             db: Session = Depends(get_db)):
    """
    Create or edit one answer key from the interface, then re-grade everything
    already scored against it so reports and analytics stay consistent.

    Editing an existing key requires the master passphrase — the same gate the
    Excel `replace` path uses. Creating a new one does not, since nothing is
    being overwritten.
    """
    from .chart_grading import regrade_chart_everywhere, chart_regrade_impact

    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if _is_ed(chart.specialty):
        raise HTTPException(status_code=400,
                            detail="Edits and Denials are graded by rubric — they have no answer key.")
    if not payload.entered_by.strip():
        raise HTTPException(status_code=400, detail="entered_by is required")

    existing = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    if existing and payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403,
                            detail="Editing an existing answer key requires the master passphrase")

    impact = chart_regrade_impact(db, chart_id) if existing else None
    if existing and impact and impact["closed_batches"] > 0 and not payload.regrade_closed:
        raise HTTPException(
            status_code=409,
            detail=(f"{impact['closed_batches']} closed batch(es) already used this key. "
                    "Re-grading rewrites closed history — resend with regrade_closed=true to proceed."),
        )

    if existing:
        existing.pdx_code = payload.pdx_code
        existing.pdx_poa = payload.pdx_poa or ""
        existing.sdx, existing.pcs, existing.cpt = payload.sdx, payload.pcs, payload.cpt
        existing.facility_level = payload.facility_level or None
        existing.profee_level = payload.profee_level or None
        existing.entered_by = payload.entered_by
    else:
        db.add(AnswerKey(
            chart_id=chart_id, specialty=chart.specialty,
            pdx_code=payload.pdx_code, pdx_poa=payload.pdx_poa or "",
            sdx=payload.sdx, pcs=payload.pcs, cpt=payload.cpt,
            facility_level=payload.facility_level or None,
            profee_level=payload.profee_level or None,
            entered_by=payload.entered_by,
        ))
    db.commit()

    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    regrade = regrade_chart_everywhere(db, chart_id, ip_cfg, op_cfg,
                                       include_closed=payload.regrade_closed)

    log_audit(db, chart_id=chart_id, action="answer_key_saved", actor=payload.entered_by,
              details=(f"{'edited' if existing else 'created'} via interface; "
                      f"re-graded {regrade['regraded']} result(s), "
                      f"skipped {regrade['skipped_closed']} in closed batches"))
    db.commit()

    return {"saved": True, "created": not existing, **regrade}
