"""Submission grading, DRG review, results, and insights endpoints."""
import io
from collections import Counter
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import (
    Chart, Batch, BatchChart, BatchStatus, BatchAllocationCycle,
    Submission, GradingResult, GradingFeedback, PassFail, ScoringConfig,
)
from services.excel_service import export_batch_results
from services.pdf_report_service import generate_batch_report_pdf
from .shared import _is_ip, _uses_dpo
from services.download_headers import content_disposition

router = APIRouter()


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
    if not gr.drg_flag:
        raise HTTPException(status_code=400, detail="This result is not a DRG-flagged case — decision not permitted")
    if gr.drg_reviewed:
        raise HTTPException(status_code=409, detail="DRG decision already recorded for this result — cannot overwrite")
    batch = db.query(Batch).filter(Batch.id == gr.batch_id).first()
    if batch and batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot modify results — batch is closed")

    gr.drg_override = "Y" if payload.drg_error else "N"
    gr.drg_reviewed = True
    gr.drg_reviewed_by = payload.reviewer
    gr.drg_reviewed_at = datetime.utcnow()

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
    from sqlalchemy import text as _text
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # One read path for both flows. Direct assignments used to be rebuilt from
    # practice_results by hand, and that hand-built row hardcoded None for every
    # component score and all four DPO figures — data grading_results holds for
    # exactly the same chart, so identical work showed a full breakdown under
    # one flow and blanks under the other. Every graded result lands in
    # grading_results now, from the practice grading path's mirror and from the
    # historical backfill.
    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id)
               .join(Chart).all())

    is_ip = _is_ip(batch.specialty)
    use_dpo = bool(getattr(batch, "use_dpo", False) and _uses_dpo(batch.specialty))

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
                "drg_correct": 0, "drg_total": 0,
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
        if use_dpo and r.dpo_dx_total is not None:
            d["dpo_dx_correct"] += r.dpo_dx_correct or 0
            d["dpo_dx_total"] += r.dpo_dx_total
        if use_dpo and r.dpo_poa_total is not None:
            d["dpo_poa_correct"] += r.dpo_poa_correct or 0
            d["dpo_poa_total"] += r.dpo_poa_total
        if use_dpo and r.dpo_proc_total is not None:
            d["dpo_proc_correct"] += r.dpo_proc_correct or 0
            d["dpo_proc_total"] += r.dpo_proc_total
        if use_dpo and is_ip and r.drg_score is not None:
            d["drg_correct"] += 1 if (r.drg_score or 0) > 0 else 0
            d["drg_total"] += 1

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
            "drg_reviewed_by": r.drg_reviewed_by,
            "drg_reviewed_at": r.drg_reviewed_at.isoformat() if r.drg_reviewed_at else None,
            "dpo_dx_accuracy": r.dpo_dx_accuracy if use_dpo else None,
            "dpo_poa_accuracy": r.dpo_poa_accuracy if use_dpo else None,
            "dpo_proc_accuracy": r.dpo_proc_accuracy if use_dpo else None,
            "dpo_overall_accuracy": r.dpo_overall_accuracy if use_dpo else None,
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
        drg_acc = _dpo_acc(d["drg_correct"], d["drg_total"])
        total_opp = d["dpo_dx_total"] + d["dpo_poa_total"] + d["dpo_proc_total"]
        total_correct = d["dpo_dx_correct"] + d["dpo_poa_correct"] + d["dpo_proc_correct"]
        overall_acc = _dpo_acc(total_correct, total_opp)

        coder_summaries.append({
            "coder_name": d["coder_name"],
            "chart_count": cnt,
            "charts_scored": d["total_cnt"],
            "charts_passed": d["pass_count"],
            "avg_total": total_avg,
            "pass_fail": "PENDING" if d["total_cnt"] == 0 else ("PASS" if d["pass_count"] > d["total_cnt"] / 2 else "FAIL"),
            # Cumulative DPO (correct methodology)
            "cumulative_dpo": {
                "dx_accuracy": dx_acc,
                "poa_accuracy": poa_acc,
                "proc_accuracy": proc_acc,
                "drg_accuracy": drg_acc,
                "overall_accuracy": overall_acc,
                "dx_correct": d["dpo_dx_correct"], "dx_total": d["dpo_dx_total"],
                "poa_correct": d["dpo_poa_correct"], "poa_total": d["dpo_poa_total"],
                "proc_correct": d["dpo_proc_correct"], "proc_total": d["dpo_proc_total"],
                "drg_correct": d["drg_correct"], "drg_total": d["drg_total"],
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
        # Survives as the one thing the flag still means: which words the screen
        # uses, and whether this work counts toward cohort analytics.
        "is_direct_assignment": bool(batch.is_direct_assignment),
        "use_weighted": getattr(batch, "use_weighted", True),
        "use_dpo": use_dpo,
        "batch_summary": {
            "total_coders": total_coders,
            "passed": passed_coders,
            "failed": total_coders - passed_coders,
            # CODER pass rate — what share of coders passed the batch. Analytics
            # reports a CHART pass rate under the same name, so the basis is
            # stated rather than left to be inferred from context.
            "pass_rate": round(passed_coders / total_coders * 100, 1) if total_coders else 0,
            "pass_rate_basis": "coder",
            # A coder passes the batch by passing MORE THAN HALF their charts —
            # a majority rule, not a score threshold. Stated because it is a
            # third distinct meaning of "pass" and appears nowhere in the UI.
            "coder_pass_rule": "majority of charts passed",
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
        headers=content_disposition(f"{batch.name}_Results.xlsx", "Batch_Results.xlsx"),
    )


@router.get("/batches/{batch_id}/insights")
def get_batch_insights(batch_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import text as _text
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Two result stores. /practice writes practice_results; everything else
    # writes grading_results, and practice work is MIRRORED into the latter.
    # So grading_results is the superset and is tried first — for a direct
    # assignment it yields real ORM rows rather than the shim below, which
    # carries only the handful of fields it was written for.
    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id == batch_id,
                       GradingResult.total_score.isnot(None))
               .join(Chart)
               .all())

    if not results:
        return {"has_data": False, "batch_name": batch.name, "specialty": batch.specialty.value}

    is_ip = _is_ip(batch.specialty)

    # Load configured pass threshold for this specialty
    specialty_type = "IP" if is_ip else "OP"
    cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == specialty_type).first()
    pass_threshold = (cfg_row.pass_threshold or 80) if cfg_row else 80

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

    weak_categories = [c for c in category_performance if c["avg_score"] < pass_threshold]
    strong_categories = [c for c in category_performance if c["avg_score"] >= pass_threshold]
    bottom_categories = weak_categories[:5]
    top_categories = list(reversed(strong_categories[-5:])) if strong_categories else []

    chart_map: dict = {}
    for r in results:
        cn = r.chart.chart_number
        if cn not in chart_map:
            chart_map[cn] = {"category": r.chart.category, "passed": 0, "total": 0, "scores": []}
        chart_map[cn]["total"] += 1
        chart_map[cn]["scores"].append(r.total_score)
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

    chart_performance = sorted([
        {
            "chart_number": cn,
            "category": d["category"],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "attempt_count": d["total"],
        }
        for cn, d in chart_map.items()
    ], key=lambda x: x["avg_score"])
    weak_charts = [c for c in chart_performance if c["avg_score"] < 90]
    strong_charts = [c for c in chart_performance if c["avg_score"] >= 90]
    bottom_charts = weak_charts[:5]
    top_charts = list(reversed(strong_charts[-5:])) if strong_charts else []

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

    n_coders = len(coder_results)
    n_distinct_charts = len(set(r.chart_id for r in results))

    coder_emp_ids = {c.coder_name: c.emp_id for c in batch.coders if c.emp_id}

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
            "emp_id": coder_emp_ids.get(cname),
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

    ranked_coders = sorted(coder_insights, key=lambda x: -x["avg_score"])
    weak_coders = [c for c in ranked_coders if c["avg_score"] < pass_threshold]
    strong_coders = [c for c in ranked_coders if c["avg_score"] >= pass_threshold]
    top_performers = strong_coders[:3]
    bottom_performers = list(reversed(weak_coders[-3:])) if weak_coders else []

    highest_score = max((c["avg_score"] for c in coder_insights), default=None)
    lowest_score = min((c["avg_score"] for c in coder_insights), default=None)
    highest_score_coders = [c["coder_name"] for c in coder_insights if c["avg_score"] == highest_score]
    lowest_score_coders = [c["coder_name"] for c in coder_insights if c["avg_score"] == lowest_score]

    high_threshold = pass_threshold + (100 - pass_threshold) // 2  # midpoint above pass
    score_buckets = [
        {"label": f">{high_threshold}%", "color": "#16a34a", "coders": []},
        {"label": f"{pass_threshold}-{high_threshold}%", "color": "#d97706", "coders": []},
        {"label": f"<{pass_threshold}%", "color": "#dc2626", "coders": []},
    ]
    for c in coder_insights:
        s = c["avg_score"]
        label = f"{c['coder_name']} ({c['emp_id']})" if c.get("emp_id") else c["coder_name"]
        if s > high_threshold:
            score_buckets[0]["coders"].append(label)
        elif s >= pass_threshold:
            score_buckets[1]["coders"].append(label)
        else:
            score_buckets[2]["coders"].append(label)
    score_distribution = [
        {"label": b["label"], "color": b["color"], "count": len(b["coders"]), "coders": b["coders"]}
        for b in score_buckets if len(b["coders"]) > 0
    ]

    return {
        "has_data": True,
        "batch_name": batch.name,
        "specialty": batch.specialty.value,
        "is_ip": is_ip,
        "pass_threshold": pass_threshold,
        "batch_summary": {
            "total_graded": len(results),
            "n_coders": n_coders,
            "n_distinct_charts": n_distinct_charts,
            "passed": n_passed,
            "failed": len(results) - n_passed,
            # CHART basis here — n_passed counts RESULTS. The /results endpoint
            # builds a batch_summary with the SAME field name from a CODER
            # basis, so the two batch screens report different populations.
            "pass_rate": pass_rate,
            "pass_rate_basis": "chart",
            "avg_score": avg_score,
            "prior_batch_name": prior_name,
            "prior_batch_pass_rate": prior_pass_rate,
            "pass_rate_delta": pass_rate_delta,
            "highest_score": highest_score,
            "highest_score_coders": highest_score_coders,
            "lowest_score": lowest_score,
            "lowest_score_coders": lowest_score_coders,
        },
        "team_errors": {
            "total_feedback_items": total_fb,
            "by_issue_type": by_issue_type,
            "by_section": by_section,
            "top_missed_codes": top_missed_codes,
        },
        "category_performance": category_performance,
        "top_categories": top_categories,
        "bottom_categories": bottom_categories,
        "chart_performance": chart_performance,
        "top_charts": top_charts,
        "bottom_charts": bottom_charts,
        "chart_signals": {
            "high_fail": high_fail[:6],
            "all_pass": all_pass_charts[:6],
        },
        "coder_insights": coder_insights,
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
        "score_distribution": score_distribution,
    }


@router.get("/batches/{batch_id}/insights/report.pdf")
def batch_report_pdf(batch_id: int, db: Session = Depends(get_db)):
    insights = get_batch_insights(batch_id, db)
    if not insights.get("has_data"):
        raise HTTPException(status_code=404, detail="No graded results yet for this batch")
    pdf_bytes = generate_batch_report_pdf(insights)
    safe_name = insights["batch_name"].replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(f"{insights['batch_name']}_Batch_Report.pdf", "Batch_Report.pdf"),
    )
