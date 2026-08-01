"""Self-practice and standalone grading endpoints."""
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Chart, AnswerKey, ScoringConfig, SelfPracticeSubmission, SelfPracticeResult
from services.grading_engine import (
    grade_ip, grade_op, cfg_from_db,
    compute_dpo_ip, compute_dpo_op,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
    DEFAULT_IP_CFG, DEFAULT_OP_CFG,
)
from services.excel_service import parse_submission, generate_self_practice_template
from .shared import IP_SPECIALTIES, _uses_pointers

router = APIRouter()


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
            "drg_flag": bool(res.drg_flag),
            "dpo_dx_accuracy": dpo.dx.accuracy,
            "dpo_poa_accuracy": dpo.poa.accuracy,
            "dpo_proc_accuracy": dpo.proc.accuracy,
            "dpo_overall_accuracy": dpo.overall_accuracy,
            # Raw counts — needed for cumulative DPO rollups (avg-of-avgs is wrong)
            "dpo_dx_correct": dpo.dx.opportunities - dpo.dx.defects,
            "dpo_dx_total": dpo.dx.opportunities,
            "dpo_poa_correct": dpo.poa.opportunities - dpo.poa.defects,
            "dpo_poa_total": dpo.poa.opportunities,
            "dpo_proc_correct": dpo.proc.opportunities - dpo.proc.defects,
            "dpo_proc_total": dpo.proc.opportunities,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": res.pcs_score, "cpt_score": None,
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
        # Professional claims (Surgery, ED Profee, E/M) carry diagnosis pointers
        res = grade_op(ak, s, op_cfg, check_pointers=_uses_pointers(chart.specialty))
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
            # Raw counts — needed for cumulative DPO rollups (avg-of-avgs is wrong)
            "dpo_dx_correct": dpo.dx.opportunities - dpo.dx.defects,
            "dpo_dx_total": dpo.dx.opportunities,
            "dpo_poa_correct": 0, "dpo_poa_total": 0,   # OP has no POA
            "dpo_proc_correct": dpo.proc.opportunities - dpo.proc.defects,
            "dpo_proc_total": dpo.proc.opportunities,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": None, "cpt_score": res.cpt_score,
        }, feedback_items


@router.get("/self-practice/template")
def download_self_practice_template():
    data = generate_self_practice_template()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="PracticeLab_SelfPractice_Template.xlsx"'},
    )


@router.post("/self-practice/submit")
def coder_self_practice_submit(
    coder_name: str = Form(...),
    emp_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not coder_name.strip():
        raise HTTPException(400, "Coder name is required")
    if not emp_id.strip():
        raise HTTPException(400, "Emp ID is required")

    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    graded, errors = [], []
    pending_results = []

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

            pending_results.append((chart, chart_num, result_kwargs, feedback_items))
            graded.append(chart_num)

    if not graded:
        return {"submission_id": None, "graded": [], "errors": errors}

    submission = SelfPracticeSubmission(
        coder_name=coder_name.strip(),
        emp_id=emp_id.strip(),
        source="coder",
        status="pending_review",
    )
    db.add(submission)
    db.flush()

    for chart, chart_num, result_kwargs, feedback_items in pending_results:
        sp_result = SelfPracticeResult(
            submission_id=submission.id,
            chart_id=chart.id,
            chart_number=chart_num,
            specialty=chart.specialty,
            feedback_items=feedback_items,
            **result_kwargs,
        )
        db.add(sp_result)

    db.commit()
    return {"submission_id": submission.id, "graded": graded, "errors": errors}


@router.get("/self-practice/queue")
def get_self_practice_queue(
    status: str = Query(default="pending_review"),
    db: Session = Depends(get_db),
):
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
    sub = db.query(SelfPracticeSubmission).filter(SelfPracticeSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    if sub.source != "coder":
        raise HTTPException(400, "Only coder submissions can be released — trainer standalone grades are not subject to review")
    if sub.status != "pending_review":
        raise HTTPException(409, f"Submission is already '{sub.status}' — cannot release again")
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
