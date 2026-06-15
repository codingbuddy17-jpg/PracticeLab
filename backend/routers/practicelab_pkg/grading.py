"""Submission grading, DRG review, results, and insights endpoints."""
import io
from collections import Counter
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import (
    Chart, AnswerKey, Batch, BatchCoder, BatchChart, BatchStatus, BatchAllocationCycle,
    Submission, GradingResult, GradingFeedback, SubmissionStatus, PassFail, ScoringConfig,
)
from services.grading_engine import (
    grade_ip, grade_op, finalize_ip_score, cfg_from_db,
    compute_dpo_ip, compute_dpo_op,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
    DEFAULT_IP_CFG, DEFAULT_OP_CFG,
)
from services.excel_service import parse_submission, export_batch_results
from .shared import _is_ip

router = APIRouter()


@router.post("/batches/{batch_id}/grade")
def grade_submissions(
    batch_id: int,
    files: list[UploadFile] = File(...),
    regrade: bool = False,
    db: Session = Depends(get_db),
):
    """Upload returned coder Excel files → auto-grade → store results.

    If any uploaded sheet has already been graded and regrade=False (default),
    returns needs_confirmation=True with the list of affected coder/chart pairs
    without writing anything.  Re-call with regrade=True to overwrite.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot accept new submissions")

    ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
    ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
    op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

    # ── Pre-flight: detect existing results before writing anything ───────────
    if not regrade:
        conflicts = []
        for upload in files:
            filename = upload.filename or "unknown"
            stem = filename.replace("_Assessment.xlsx", "")
            parts = stem.split("_", 1)
            coder_name: str = ""
            if len(parts) == 2:
                bc_by_emp = (db.query(BatchCoder)
                             .filter(BatchCoder.batch_id == batch_id,
                                     BatchCoder.emp_id == parts[0])
                             .first())
                if bc_by_emp:
                    coder_name = bc_by_emp.coder_name
            if not coder_name:
                coder_name = stem.replace("_", " ").strip()

            try:
                file_bytes = upload.file.read()
                upload._body = file_bytes  # cache so we can re-read below if needed
                chart_submissions = parse_submission(file_bytes)
                for sub_data in chart_submissions:
                    chart = db.query(Chart).filter(
                        Chart.chart_number == sub_data["chart_number"]
                    ).first()
                    if not chart:
                        continue
                    existing = (db.query(GradingResult)
                                .filter(GradingResult.batch_id == batch_id,
                                        GradingResult.coder_name == coder_name,
                                        GradingResult.chart_id == chart.id)
                                .first())
                    if existing:
                        conflicts.append({
                            "coder": coder_name,
                            "chart": sub_data["chart_number"],
                        })
            except Exception:
                pass

        if conflicts:
            return {
                "needs_confirmation": True,
                "conflicts": conflicts,
                "graded": [],
                "errors": [],
            }

    graded, errors = [], []

    for upload in files:
        filename = upload.filename or "unknown"
        stem = filename.replace("_Assessment.xlsx", "")
        parts = stem.split("_", 1)
        coder_name: str = ""
        if len(parts) == 2:
            bc_by_emp = (db.query(BatchCoder)
                         .filter(BatchCoder.batch_id == batch_id,
                                 BatchCoder.emp_id == parts[0])
                         .first())
            if bc_by_emp:
                coder_name = bc_by_emp.coder_name
        if not coder_name:
            coder_name = stem.replace("_", " ").strip()

        try:
            file_bytes = getattr(upload, "_body", None) or upload.file.read()
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

                existing = (db.query(GradingResult)
                            .filter(GradingResult.batch_id == batch_id,
                                    GradingResult.coder_name == coder_name,
                                    GradingResult.chart_id == chart.id)
                            .first())
                if existing:
                    db.query(GradingFeedback).filter(GradingFeedback.result_id == existing.id).delete()
                    db.delete(existing)
                    db.flush()

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
                    ip_total, ip_pass_fail, ip_drg_score = (None, None, None)
                    if not res.drg_flag:
                        ip_total, ip_pass_fail, ip_drg_score = finalize_ip_score(
                            res.pdx_score, res.sdx_score, res.pcs_score,
                            drg_error=False,
                            drg_weight=ip_cfg.drg_weight,
                            pass_threshold=ip_cfg.pass_threshold,
                        )
                    gr = GradingResult(
                        batch_id=batch_id,
                        submission_id=sub.id,
                        coder_name=coder_name,
                        chart_id=chart.id,
                        specialty=chart.specialty,
                        pdx_score=res.pdx_score,
                        sdx_score=res.sdx_score,
                        pcs_score=res.pcs_score,
                        drg_score=ip_drg_score,
                        total_score=ip_total,
                        pass_fail=ip_pass_fail,
                        drg_flag=res.drg_flag,
                        drg_reviewed=not res.drg_flag,
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

                if batch.use_dpo:
                    penalty = (ip_cfg if _is_ip(chart.specialty) else op_cfg).overcoding_penalty
                    if _is_ip(chart.specialty):
                        dpo = compute_dpo_ip(
                            IPAnswerKey(pdx_code=ak_rec.pdx_code or "", pdx_poa=ak_rec.pdx_poa or "", sdx=ak_rec.sdx or [], pcs=ak_rec.pcs or []),
                            IPSubmission(pdx_code=sub_data.get("pdx_code", ""), pdx_poa=sub_data.get("pdx_poa", ""), sdx=sub_data.get("sdx", []), pcs=sub_data.get("pcs", [])),
                            penalty,
                        )
                    else:
                        dpo = compute_dpo_op(
                            OPAnswerKey(pdx_code=ak_rec.pdx_code or "", sdx=ak_rec.sdx or [], cpt=ak_rec.cpt or []),
                            OPSubmission(pdx_code=sub_data.get("pdx_code", ""), sdx=sub_data.get("sdx", []), cpt=sub_data.get("cpt", [])),
                            penalty,
                        )
                    gr.dpo_dx_accuracy = dpo.dx.accuracy
                    gr.dpo_poa_accuracy = dpo.poa.accuracy
                    gr.dpo_proc_accuracy = dpo.proc.accuracy
                    gr.dpo_overall_accuracy = dpo.overall_accuracy
                    # Raw counts for correct cumulative aggregation
                    gr.dpo_dx_correct = dpo.dx.opportunities - dpo.dx.defects
                    gr.dpo_dx_total = dpo.dx.opportunities
                    gr.dpo_poa_correct = dpo.poa.opportunities - dpo.poa.defects
                    gr.dpo_poa_total = dpo.poa.opportunities
                    gr.dpo_proc_correct = dpo.proc.opportunities - dpo.proc.defects
                    gr.dpo_proc_total = dpo.proc.opportunities

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


@router.get("/batches/{batch_id}/drg-review")
def get_drg_review(batch_id: int, db: Session = Depends(get_db)):
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
    drg_error: bool
    reviewer: str


@router.post("/results/{result_id}/drg-decision")
def submit_drg_decision(result_id: int, payload: DRGDecision, db: Session = Depends(get_db)):
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


@router.get("/batches/{batch_id}/results")
def get_batch_results(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id)
               .join(Chart).all())

    is_ip = _is_ip(batch.specialty)
    use_dpo = getattr(batch, "use_dpo", False)

    coder_map: dict[str, dict] = {}
    for r in results:
        name = r.coder_name
        if name not in coder_map:
            coder_map[name] = {
                "coder_name": name, "chart_count": 0,
                "pdx_sum": 0, "sdx_sum": 0, "pcs_sum": 0,
                "cpt_sum": 0, "drg_sum": 0, "total_sum": 0, "total_cnt": 0,
                "pass_count": 0, "charts": [],
                # Raw DPO counts for correct cumulative (sum not avg-of-avgs)
                "dpo_dx_correct": 0, "dpo_dx_total": 0,
                "dpo_poa_correct": 0, "dpo_poa_total": 0,
                "dpo_proc_correct": 0, "dpo_proc_total": 0,
            }
        d = coder_map[name]
        d["chart_count"] += 1
        d["pdx_sum"] += r.pdx_score or 0
        d["sdx_sum"] += r.sdx_score or 0
        d["pcs_sum"] += r.pcs_score or 0
        d["cpt_sum"] += r.cpt_score or 0
        d["drg_sum"] += r.drg_score or 0
        if r.total_score is not None:
            d["total_sum"] += r.total_score
            d["total_cnt"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            d["pass_count"] += 1
        if r.dpo_dx_total is not None:
            d["dpo_dx_correct"] += r.dpo_dx_correct or 0
            d["dpo_dx_total"] += r.dpo_dx_total
        if r.dpo_poa_total is not None:
            d["dpo_poa_correct"] += r.dpo_poa_correct or 0
            d["dpo_poa_total"] += r.dpo_poa_total
        if r.dpo_proc_total is not None:
            d["dpo_proc_correct"] += r.dpo_proc_correct or 0
            d["dpo_proc_total"] += r.dpo_proc_total

        d["charts"].append({
            "chart_number": r.chart.chart_number,
            "category": r.chart.category,
            "specialty": r.chart.specialty.value if r.chart.specialty else None,
            "pdx_score": r.pdx_score,
            "sdx_score": r.sdx_score,
            "pcs_score": r.pcs_score,
            "cpt_score": r.cpt_score,
            "drg_score": r.drg_score,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail,
            "drg_flag": r.drg_flag,
            "drg_reviewed": r.drg_reviewed,
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

    def _dpo_acc(correct, total):
        if not total:
            return None
        return round(correct / total * 100, 1)

    coder_summaries = []
    for d in coder_map.values():
        cnt = d["chart_count"] or 1
        scored_cnt = d["total_cnt"] or 1
        total_avg = round(d["total_sum"] / scored_cnt, 1)

        # Cumulative DPO: sum raw counts then compute accuracy
        dx_acc = _dpo_acc(d["dpo_dx_correct"], d["dpo_dx_total"])
        poa_acc = _dpo_acc(d["dpo_poa_correct"], d["dpo_poa_total"])
        proc_acc = _dpo_acc(d["dpo_proc_correct"], d["dpo_proc_total"])
        total_opp = d["dpo_dx_total"] + d["dpo_poa_total"] + d["dpo_proc_total"]
        total_correct = d["dpo_dx_correct"] + d["dpo_poa_correct"] + d["dpo_proc_correct"]
        overall_acc = _dpo_acc(total_correct, total_opp)

        coder_summaries.append({
            "coder_name": d["coder_name"],
            "chart_count": cnt,
            "charts_scored": d["total_cnt"],
            "charts_passed": d["pass_count"],
            "avg_total": total_avg,
            "pass_fail": "PASS" if d["pass_count"] >= d["total_cnt"] / 2 else "FAIL",
            # Cumulative DPO (correct methodology)
            "cumulative_dpo": {
                "dx_accuracy": dx_acc,
                "poa_accuracy": poa_acc,
                "proc_accuracy": proc_acc,
                "overall_accuracy": overall_acc,
                "dx_correct": d["dpo_dx_correct"], "dx_total": d["dpo_dx_total"],
                "poa_correct": d["dpo_poa_correct"], "poa_total": d["dpo_poa_total"],
                "proc_correct": d["dpo_proc_correct"], "proc_total": d["dpo_proc_total"],
            } if d["dpo_dx_total"] or d["dpo_proc_total"] else None,
            # Keep legacy per-chart DPO fields for existing chart-level display
            "dpo_dx_accuracy": dx_acc,
            "dpo_poa_accuracy": poa_acc,
            "dpo_proc_accuracy": proc_acc,
            "dpo_overall_accuracy": overall_acc,
            "charts": d["charts"],
        })

    all_totals = [r.total_score for r in results if r.total_score is not None]
    passed_coders = sum(1 for c in coder_summaries if c["pass_fail"] == "PASS")
    total_coders = len(coder_summaries)

    missed = {}
    error_type_counts: dict[str, int] = {}
    for r in results:
        for f in r.feedback:
            it = f.issue_type.value
            error_type_counts[it] = error_type_counts.get(it, 0) + 1
            if it == "Missed" and f.ak_code:
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
            "error_type_counts": error_type_counts,
            "pending_drg_review": sum(1 for r in results if r.drg_flag and not r.drg_reviewed),
        },
        "coder_summaries": coder_summaries,
    }


@router.get("/batches/{batch_id}/results/export")
def export_results(batch_id: int, db: Session = Depends(get_db)):
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


@router.get("/batches/{batch_id}/insights")
def get_batch_insights(batch_id: int, db: Session = Depends(get_db)):
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
