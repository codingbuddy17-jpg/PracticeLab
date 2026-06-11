"""
PracticeLab API router — assessment module endpoints.
"""
import random
import io
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
    AnswerKey, Batch, BatchCoder, BatchChart, BatchStatus,
    Submission, GradingResult, GradingFeedback, SubmissionStatus,
    ScoringConfig,
)
from services.grading_engine import (
    grade_ip, grade_op, finalize_ip_score, cfg_from_db,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
    DEFAULT_IP_CFG, DEFAULT_OP_CFG,
)
from services.excel_service import (
    generate_answer_key_template, generate_coder_sheet,
    generate_batch_zip, parse_answer_key_upload,
    parse_submission, export_batch_results,
    generate_coder_list_template, parse_coder_list,
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

class CoderEntry(BaseModel):
    name: str
    emp_id: str


class BatchCreate(BaseModel):
    name: str
    specialty: str
    categories: list[str] = []
    difficulties: list[str] = []
    charts_per_coder: int
    coders: list[CoderEntry]
    created_by: str


@router.post("/batches")
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    """Create batch, randomize chart assignments per coder."""
    try:
        specialty = Specialty(payload.specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid specialty: {payload.specialty}")

    # Build chart pool
    q = (db.query(Chart)
         .join(AnswerKey, AnswerKey.chart_id == Chart.id)
         .filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == specialty))

    if payload.categories:
        from sqlalchemy import or_
        q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in payload.categories]))

    if payload.difficulties:
        diffs = []
        for d in payload.difficulties:
            try:
                diffs.append(Difficulty(d))
            except ValueError:
                pass
        if diffs:
            q = q.filter(Chart.difficulty.in_(diffs))

    pool = q.all()
    pool_size = len(pool)

    if pool_size == 0:
        raise HTTPException(status_code=400, detail="No charts with answer keys match the selected filters.")

    if payload.charts_per_coder < 1:
        raise HTTPException(status_code=400, detail="charts_per_coder must be at least 1")

    # Create batch record
    batch = Batch(
        name=payload.name,
        specialty=specialty,
        categories=payload.categories,
        difficulties=payload.difficulties,
        charts_per_coder=payload.charts_per_coder,
        created_by=payload.created_by,
        status=BatchStatus.ACTIVE,
    )
    db.add(batch)
    db.flush()

    # Assign charts — Fisher-Yates shuffle per coder
    for coder in payload.coders:
        coder_name = coder.name
        shuffled = pool.copy()
        random.shuffle(shuffled)
        assigned = (shuffled * ((payload.charts_per_coder // pool_size) + 1))[:payload.charts_per_coder]

        coder_rec = BatchCoder(batch_id=batch.id, coder_name=coder_name, emp_id=coder.emp_id)
        db.add(coder_rec)

        for chart in assigned:
            db.add(BatchChart(
                batch_id=batch.id,
                coder_name=coder_name,
                chart_id=chart.id,
                submission_status=SubmissionStatus.PENDING,
            ))

    db.commit()
    return {"batch_id": batch.id, "name": batch.name, "pool_size": pool_size}


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
    return [
        {
            "id": b.id, "name": b.name, "specialty": b.specialty.value,
            "charts_per_coder": b.charts_per_coder, "status": b.status.value,
            "created_by": b.created_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "coder_count": len(b.coders),
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

    return {
        "id": batch.id, "name": batch.name, "specialty": batch.specialty.value,
        "categories": batch.categories, "difficulties": batch.difficulties,
        "charts_per_coder": batch.charts_per_coder, "status": batch.status.value,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "coders": [{"name": c.coder_name, "emp_id": c.emp_id or "",
                    "excel_generated": c.excel_generated_at is not None,
                    "charts": coder_map.get(c.coder_name, [])} for c in coders],
    }


# ── Excel generation ──────────────────────────────────────────────────────────

@router.get("/batches/{batch_id}/generate-excel")
def generate_excel(batch_id: int, db: Session = Depends(get_db)):
    """Generate coder answer sheet ZIP for a batch."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    assignments = (db.query(BatchChart)
                   .filter(BatchChart.batch_id == batch_id)
                   .join(Chart).all())

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

    coder_files = []
    for coder in coders:
        charts = coder_charts.get(coder.coder_name, [])
        excel_bytes = generate_coder_sheet(coder.coder_name, batch.name, charts, emp_id=coder.emp_id or "")
        emp = (coder.emp_id or "").replace(" ", "_")
        safe_name = coder.coder_name.replace(" ", "_")
        filename = f"{emp}_{safe_name}_Assessment.xlsx" if emp else f"{safe_name}_Assessment.xlsx"
        coder_files.append((filename, excel_bytes))
        coder.excel_generated_at = datetime.utcnow()

    db.commit()

    zip_bytes = generate_batch_zip(coder_files)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={batch.name.replace(' ','_')}_Assessments.zip"},
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

                # Update submission status
                bc = (db.query(BatchChart)
                      .filter(BatchChart.batch_id == batch_id,
                              BatchChart.coder_name == coder_name,
                              BatchChart.chart_id == chart.id)
                      .first())
                if bc:
                    bc.submission_status = SubmissionStatus.SUBMITTED

                graded.append(f"{coder_name} / {chart_num}")

        except Exception as e:
            errors.append(f"{filename}: {str(e)}")

    db.commit()

    # Update batch status
    if graded:
        has_ip_pending = (db.query(GradingResult)
                          .filter(GradingResult.batch_id == batch_id,
                                  GradingResult.drg_flag == True,
                                  GradingResult.drg_reviewed == False)
                          .count()) > 0
        batch.status = BatchStatus.GRADING if has_ip_pending else BatchStatus.COMPLETE
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

    # Check if all DRG reviews done for this batch
    pending = (db.query(GradingResult)
               .filter(GradingResult.batch_id == gr.batch_id,
                       GradingResult.drg_flag == True,
                       GradingResult.drg_reviewed == False)
               .count())
    if pending == 0:
        batch = db.query(Batch).filter(Batch.id == gr.batch_id).first()
        if batch:
            batch.status = BatchStatus.COMPLETE
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
            "feedback": [
                {"section": f.section.value, "issue_type": f.issue_type.value,
                 "ak_code": f.ak_code, "coder_code": f.coder_code, "detail": f.detail}
                for f in r.feedback
            ],
        })

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


# ── Analytics endpoints ───────────────────────────────────────────────────────

@router.get("/analytics/overview")
def analytics_overview(db: Session = Depends(get_db)):
    """High-level counts across all batches."""
    total_batches = db.query(Batch).count()
    complete = db.query(Batch).filter(Batch.status == BatchStatus.COMPLETE).count()
    total_results = db.query(GradingResult).filter(GradingResult.total_score.isnot(None)).count()
    passed = db.query(GradingResult).filter(GradingResult.pass_fail == "PASS").count()
    return {
        "total_batches": total_batches,
        "complete_batches": complete,
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
    batches = db.query(Batch).filter(Batch.status == BatchStatus.COMPLETE).order_by(Batch.created_at.desc()).all()
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
