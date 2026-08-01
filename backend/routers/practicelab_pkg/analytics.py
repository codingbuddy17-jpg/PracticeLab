"""Analytics endpoints for PracticeLab."""
import io
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer
from database import get_db
from models import Batch, BatchCoder, BatchStatus, GradingResult, GradingFeedback, Chart, PassFail, Specialty, ScoringConfig
from services.pdf_report_service import generate_coder_report_pdf
from .shared import _uses_dpo

router = APIRouter()


def _gr_base(db: Session, from_date: Optional[str], to_date: Optional[str], specialty: Optional[str], exclude_direct: bool = False):
    q = db.query(GradingResult).filter(GradingResult.total_score.isnot(None))
    if from_date:
        q = q.filter(GradingResult.graded_at >= from_date)
    if to_date:
        q = q.filter(GradingResult.graded_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(GradingResult.specialty == spec)
    if exclude_direct:
        q = q.join(Batch, GradingResult.batch_id == Batch.id).filter(Batch.is_direct_assignment == False)
    return q


def _batch_base(db: Session, from_date: Optional[str], to_date: Optional[str], specialty: Optional[str]):
    """Team/batch-level aggregates always exclude direct assignments — those are
    tracked separately (see Direct Assignments list) and shouldn't dilute formal
    batch counts or trends. Coder-level views intentionally do NOT use this filter."""
    q = db.query(Batch).filter(Batch.is_direct_assignment == False)
    if from_date:
        q = q.filter(Batch.created_at >= from_date)
    if to_date:
        q = q.filter(Batch.created_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(Batch.specialty == spec)
    return q


@router.get("/analytics/overview")
def analytics_overview(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    base = _gr_base(db, from_date, to_date, specialty, exclude_direct=True)
    total_results = base.count()
    passed = base.filter(GradingResult.pass_fail == PassFail.PASS).count()

    b_base = _batch_base(db, from_date, to_date, specialty)

    ip_cfg = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()

    return {
        "total_batches": b_base.count(),
        "open_batches": b_base.filter(Batch.status == BatchStatus.OPEN).count(),
        "complete_batches": b_base.filter(Batch.status == BatchStatus.CLOSED).count(),
        "total_graded": total_results,
        "total_passed": passed,
        "overall_pass_rate": round(passed / total_results * 100, 1) if total_results else 0,
        "ip_pass_threshold": (ip_cfg.pass_threshold or 80) if ip_cfg else 80,
        "op_pass_threshold": (op_cfg.pass_threshold or 90) if op_cfg else 90,
    }


@router.get("/analytics/by-specialty")
def analytics_by_specialty(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    base = _gr_base(db, from_date, to_date, specialty, exclude_direct=True)
    rows = (base.with_entities(
                GradingResult.specialty,
                func.count(GradingResult.id).label("total"),
                func.avg(GradingResult.total_score).label("avg_score"),
                func.sum(func.cast(GradingResult.pass_fail == PassFail.PASS, Integer)).label("passed"),
            )
            .group_by(GradingResult.specialty)
            .all())
    return [
        {
            "specialty": r.specialty.value,
            "total": r.total,
            "avg_score": round(float(r.avg_score or 0), 1),
            "pass_rate": round(float(r.passed or 0) / r.total * 100, 1) if r.total else 0,
        }
        for r in rows
    ]


@router.get("/analytics/by-chart")
def analytics_by_chart(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = _gr_base(db, from_date, to_date, specialty, exclude_direct=True).join(Chart).all()

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
def analytics_by_batch(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    batches = _batch_base(db, from_date, to_date, specialty).order_by(Batch.created_at.asc()).all()
    out = []
    for b in batches:
        results = [r for r in b.results if r.total_score is not None]
        if not results:
            continue
        scores = [r.total_score for r in results]
        passed = sum(1 for r in results if r.pass_fail == PassFail.PASS)
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


def _coder_filter(q, coder_name: Optional[str], emp_id: Optional[str]):
    """
    Identify a coder by emp_id when we have one, otherwise by name.

    emp_id is the stable identity — names are free text, so variants fork one
    person's history and duplicates merge two people. Name is kept as a fallback
    for coders enrolled without an ID.
    """
    if emp_id:
        return q.filter(GradingResult.emp_id == emp_id)
    return q.filter(GradingResult.coder_name == coder_name)


@router.get("/analytics/coder-trend")
def coder_trend(
    coder_name: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    emp_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = (db.query(GradingResult)
         .filter(GradingResult.total_score.isnot(None))
         .join(Batch)
         .order_by(Batch.created_at))
    q = _coder_filter(q, coder_name, emp_id)
    if from_date:
        q = q.filter(GradingResult.graded_at >= from_date)
    if to_date:
        q = q.filter(GradingResult.graded_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(GradingResult.specialty == spec)
    results = q.all()

    batch_scores: dict[int, dict] = {}
    for r in results:
        bid = r.batch_id
        if bid not in batch_scores:
            batch_scores[bid] = {
                "batch_name": r.batch.name,
                "specialty": r.batch.specialty.value if r.batch.specialty else None,
                "created_at": r.batch.created_at.isoformat() if r.batch.created_at else None,
                "scores": [],
                "passed": 0,
            }
        batch_scores[bid]["scores"].append(r.total_score)
        if r.pass_fail and r.pass_fail.value == "PASS":
            batch_scores[bid]["passed"] += 1

    return [
        {
            "batch_id": bid,
            "batch_name": d["batch_name"],
            "specialty": d["specialty"],
            "created_at": d["created_at"],
            "chart_count": len(d["scores"]),
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "charts_passed": d["passed"],
        }
        for bid, d in batch_scores.items()
    ]


@router.get("/analytics/coder-summary")
def coder_summary(
    coder_name: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    emp_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Full coder profile across all batches — cumulative weighted + DPO scores, category breakdown, batch history."""
    q = (db.query(GradingResult)
         .join(Batch).join(Chart, GradingResult.chart_id == Chart.id)
         .order_by(Batch.created_at))
    q = _coder_filter(q, coder_name, emp_id)
    if from_date:
        q = q.filter(GradingResult.graded_at >= from_date)
    if to_date:
        q = q.filter(GradingResult.graded_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(GradingResult.specialty == spec)
    results = q.all()
    return build_coder_summary(results, coder_name, db)


def build_coder_summary(results, coder_name: str, db: Session):
    """
    Aggregate a list of GradingResult rows into the coder profile shape.

    Split out from the endpoint so session-scoped reports can reuse the exact
    same aggregation over a differently-filtered row set.
    """
    if not results:
        return None

    # Prefer the id carried on the results themselves; only fall back to the
    # roster lookup for rows written before emp_id existed on GradingResult.
    emp_id = next((r.emp_id for r in results if r.emp_id), None)
    if not emp_id:
        emp_id_row = (db.query(BatchCoder.emp_id)
                      .filter(BatchCoder.coder_name == coder_name,
                              BatchCoder.emp_id.isnot(None), BatchCoder.emp_id != "")
                      .order_by(BatchCoder.id.desc())
                      .first())
        emp_id = emp_id_row[0] if emp_id_row else None

    # ── Cumulative weighted ──────────────────────────────────────────────────
    scored = [r for r in results if r.total_score is not None]
    total_charts = len(scored)
    charts_passed = sum(1 for r in scored if r.pass_fail and r.pass_fail.value == "PASS")
    weighted_accuracy = round(sum(r.total_score for r in scored) / len(scored), 1) if scored else None

    # ── Cumulative DPO (sum counts, not avg-of-avgs) ────────────────────────
    dx_correct = dx_total = poa_correct = poa_total = proc_correct = proc_total = 0
    drg_correct = drg_total = 0
    has_dpo = False
    for r in results:
        batch = getattr(r, "batch", None)
        dpo_allowed = bool(
            batch
            and getattr(batch, "use_dpo", False)
            and _uses_dpo(getattr(batch, "specialty", None))
        )
        if not dpo_allowed:
            continue
        if r.dpo_dx_total is not None:
            has_dpo = True
            dx_correct += r.dpo_dx_correct or 0
            dx_total += r.dpo_dx_total
        if r.dpo_poa_total is not None:
            poa_correct += r.dpo_poa_correct or 0
            poa_total += r.dpo_poa_total
        if r.dpo_proc_total is not None:
            proc_correct += r.dpo_proc_correct or 0
            proc_total += r.dpo_proc_total
        if getattr(r, "specialty", None) == Specialty.IP_DRG and r.drg_score is not None:
            drg_correct += 1 if (r.drg_score or 0) > 0 else 0
            drg_total += 1

    def _acc(c, t): return round(c / t * 100, 1) if t else None

    cumulative_dpo = {
        "dx_accuracy": _acc(dx_correct, dx_total),
        "poa_accuracy": _acc(poa_correct, poa_total),
        "proc_accuracy": _acc(proc_correct, proc_total),
        "drg_accuracy": _acc(drg_correct, drg_total),
        "overall_accuracy": _acc(dx_correct + poa_correct + proc_correct, dx_total + poa_total + proc_total),
    } if has_dpo else None

    # ── Error pattern across all of this coder's work ───────────────────────
    all_feedback = [f for r in results for f in r.feedback]
    total_fb = len(all_feedback)
    issue_counts = Counter(f.issue_type.value for f in all_feedback)
    missed_counts = Counter(f.ak_code for f in all_feedback if f.issue_type.value == "Missed" and f.ak_code)
    error_pattern = {
        "by_issue_type": [
            {"type": t, "count": c, "pct": round(c / total_fb * 100, 1) if total_fb else 0}
            for t, c in sorted(issue_counts.items(), key=lambda x: -x[1])
        ],
        "top_missed_codes": [{"code": c, "count": n} for c, n in missed_counts.most_common(5)],
    }

    # ── Per-category breakdown ───────────────────────────────────────────────
    cat_map: dict[str, dict] = {}
    for r in scored:
        cat = r.chart.category
        if cat not in cat_map:
            cat_map[cat] = {"scores": [], "passed": 0}
        cat_map[cat]["scores"].append(r.total_score)
        if r.pass_fail and r.pass_fail.value == "PASS":
            cat_map[cat]["passed"] += 1

    by_category = sorted([
        {
            "category": cat,
            "charts": len(d["scores"]),
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "pass_rate": round(d["passed"] / len(d["scores"]) * 100, 1),
        }
        for cat, d in cat_map.items()
    ], key=lambda x: -x["avg_score"])

    # ── Per-batch history ────────────────────────────────────────────────────
    batch_map: dict[int, dict] = {}
    for r in results:
        bid = r.batch_id
        if bid not in batch_map:
            batch_map[bid] = {
                "batch_id": bid,
                "batch_name": r.batch.name,
                "specialty": r.batch.specialty.value,
                "created_at": r.batch.created_at.isoformat() if r.batch.created_at else None,
                "scores": [],
                "passed": 0,
            }
        if r.total_score is not None:
            batch_map[bid]["scores"].append(r.total_score)
            if r.pass_fail and r.pass_fail.value == "PASS":
                batch_map[bid]["passed"] += 1

    batches = [
        {
            "batch_id": d["batch_id"],
            "batch_name": d["batch_name"],
            "specialty": d["specialty"],
            "created_at": d["created_at"],
            "chart_count": len(d["scores"]),
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else None,
            "charts_passed": d["passed"],
        }
        for d in batch_map.values()
    ]

    # Pass threshold from active scoring config (IP if any IP result exists, else OP)
    has_ip = any(r.specialty and r.specialty.value == "IP-DRG" for r in results)
    cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == ("IP" if has_ip else "OP")).first()
    pass_threshold = (cfg_row.pass_threshold or 80) if cfg_row else 80

    return {
        "coder_name": coder_name,
        "emp_id": emp_id,
        "total_charts": total_charts,
        "charts_scored": len(scored),
        "charts_passed": charts_passed,
        "weighted_accuracy": weighted_accuracy,
        "cumulative_dpo": cumulative_dpo,
        "by_category": by_category,
        "batches": batches,
        "error_pattern": error_pattern,
        "pass_threshold": pass_threshold,
    }


@router.get("/analytics/coder-report.pdf")
def coder_report_pdf(
    coder_name: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    emp_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    summary = coder_summary(coder_name, from_date, to_date, specialty, emp_id, db)
    if not summary:
        raise HTTPException(status_code=404, detail="No data for this coder")

    team_base = _gr_base(db, from_date, to_date, specialty, exclude_direct=True)
    team_scores = [r.total_score for r in team_base.all()]
    team_avg_score = round(sum(team_scores) / len(team_scores), 1) if team_scores else None

    if from_date or to_date:
        period_label = f"Period: {from_date or 'start'} to {to_date or 'today'}"
    else:
        period_label = "Period: All time"
    if specialty:
        period_label += f"  |  Specialty: {specialty}"

    pdf_bytes = generate_coder_report_pdf(coder_name, summary, team_avg_score=team_avg_score,
                                          period_label=period_label)
    safe_name = coder_name.replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_Performance_Report.pdf"},
    )


@router.get("/analytics/by-category")
def analytics_by_category(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = _gr_base(db, from_date, to_date, specialty).join(Chart).all()

    if not results:
        return {"team": [], "coder_category": []}

    # Team-level aggregate excludes direct assignments; coder-level (below) includes
    # everything, since a coder's record should reflect all their work regardless of source.
    team_results = [r for r in results if not r.batch.is_direct_assignment]

    cat_map: dict = {}
    for r in team_results:
        cat = r.chart.category
        if cat not in cat_map:
            cat_map[cat] = {"scores": [], "passed": 0, "total": 0, "coders": set(), "specialties": set()}
        cat_map[cat]["scores"].append(r.total_score)
        cat_map[cat]["total"] += 1
        cat_map[cat]["coders"].add(r.coder_name)
        cat_map[cat]["specialties"].add(r.chart.specialty.value)
        if r.pass_fail and r.pass_fail.value == "PASS":
            cat_map[cat]["passed"] += 1

    team = sorted([
        {
            "category": cat,
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "pass_rate": round(d["passed"] / d["total"] * 100, 1),
            "attempt_count": d["total"],
            "coder_count": len(d["coders"]),
            "specialties": list(d["specialties"]),
        }
        for cat, d in cat_map.items()
    ], key=lambda x: x["avg_score"])

    coder_cat: dict = {}
    for r in results:
        key = (r.coder_name, r.chart.category)
        if key not in coder_cat:
            coder_cat[key] = {"scores": [], "passed": 0, "total": 0}
        coder_cat[key]["scores"].append(r.total_score)
        coder_cat[key]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            coder_cat[key]["passed"] += 1

    coder_category = [
        {
            "coder_name": k[0],
            "category": k[1],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "pass_rate": round(d["passed"] / d["total"] * 100, 1),
            "attempt_count": d["total"],
        }
        for k, d in coder_cat.items()
    ]

    return {
        "team": team,
        "coder_category": coder_category,
        "coder_scope_note": "Coder rows include direct assignments and standalone grades. Team averages reflect formal batches only.",
    }


@router.get("/analytics/chart-teaching-value")
def analytics_chart_teaching_value(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = _gr_base(db, from_date, to_date, specialty, exclude_direct=True).join(Chart).all()

    if not results:
        return []

    # Use specialty-appropriate pass threshold for teaching value labels
    has_ip = any(r.specialty and r.specialty.value == "IP-DRG" for r in results)
    spec_type = "IP" if (has_ip and not specialty) or (specialty and specialty == "IP-DRG") else "OP"
    tv_cfg = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == spec_type).first()
    tv_threshold = (tv_cfg.pass_threshold or 80) if tv_cfg else 80

    chart_map: dict = {}
    for r in results:
        cn = r.chart.chart_number
        if cn not in chart_map:
            chart_map[cn] = {
                "chart_number": cn,
                "specialty": r.chart.specialty.value,
                "category": r.chart.category,
                "difficulty": r.chart.difficulty.value,
                "scores": [], "passed": 0, "total": 0,
                "error_variety": set(),
            }
        chart_map[cn]["scores"].append(r.total_score)
        chart_map[cn]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            chart_map[cn]["passed"] += 1
        for f in r.feedback:
            if f.issue_type.value == "Missed" and f.ak_code:
                chart_map[cn]["error_variety"].add(f.ak_code)

    out = []
    for d in chart_map.values():
        avg = round(sum(d["scores"]) / len(d["scores"]), 1)
        pass_rate = round(d["passed"] / d["total"] * 100, 1)
        error_variety = len(d["error_variety"])
        attempts = d["total"]

        high_cutoff = tv_threshold + max(5, (100 - tv_threshold) // 2)
        low_cutoff = tv_threshold * 60 // 100  # ~60% of threshold = fail zone
        if attempts < 2:
            label = "Underused"
        elif avg >= high_cutoff:
            label = "Too Easy"
        elif pass_rate < low_cutoff and error_variety >= 3:
            label = "High Confusion"
        elif low_cutoff <= pass_rate <= tv_threshold and error_variety >= 2 and attempts >= 3:
            label = "High Yield"
        elif pass_rate < low_cutoff:
            label = "High Fail"
        else:
            label = "Standard"

        out.append({
            "chart_number": d["chart_number"],
            "specialty": d["specialty"],
            "category": d["category"],
            "difficulty": d["difficulty"],
            "avg_score": avg,
            "pass_rate": pass_rate,
            "attempt_count": attempts,
            "error_variety": error_variety,
            "teaching_label": label,
        })

    return sorted(out, key=lambda x: (x["teaching_label"], -x["attempt_count"]))


@router.get("/analytics/coder-matrix")
def analytics_coder_matrix(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    b_q = db.query(Batch).filter(Batch.status == BatchStatus.CLOSED, Batch.is_direct_assignment == False)
    if from_date:
        b_q = b_q.filter(Batch.closed_at >= from_date)
    if to_date:
        b_q = b_q.filter(Batch.closed_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            b_q = b_q.filter(Batch.specialty == spec)
    batches = b_q.order_by(Batch.created_at).all()

    if not batches:
        return {"batches": [], "coders": [], "cells": []}

    batch_ids = [b.id for b in batches]
    results = (db.query(GradingResult)
               .filter(GradingResult.batch_id.in_(batch_ids),
                       GradingResult.total_score.isnot(None))
               .all())

    cell_map: dict = {}
    for r in results:
        key = (r.coder_name, r.batch_id)
        if key not in cell_map:
            cell_map[key] = {"scores": [], "passed": 0, "total": 0}
        cell_map[key]["scores"].append(r.total_score)
        cell_map[key]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            cell_map[key]["passed"] += 1

    all_coders = sorted(set(r.coder_name for r in results))

    coder_emp_ids: dict[str, str] = {}
    for name, emp_id in (db.query(BatchCoder.coder_name, BatchCoder.emp_id)
                          .filter(BatchCoder.coder_name.in_(all_coders))
                          .order_by(BatchCoder.id.desc())
                          .all()):
        if name not in coder_emp_ids and emp_id:
            coder_emp_ids[name] = emp_id

    cells = []
    for coder in all_coders:
        for b in batches:
            data = cell_map.get((coder, b.id))
            if data:
                cells.append({
                    "coder_name": coder,
                    "batch_id": b.id,
                    "avg_score": round(sum(data["scores"]) / len(data["scores"]), 1),
                    "pass_rate": round(data["passed"] / data["total"] * 100, 1),
                    "chart_count": data["total"],
                    "score_sum": sum(data["scores"]),
                })

    return {
        "batches": [{"id": b.id, "name": b.name, "specialty": b.specialty.value, "closed_at": b.closed_at.isoformat() if b.closed_at else None} for b in batches],
        "coders": all_coders,
        "coder_emp_ids": coder_emp_ids,
        "cells": cells,
    }


@router.get("/analytics/chart-detail/{chart_number:path}")
def chart_detail(chart_number: str, db: Session = Depends(get_db)):
    results = (db.query(GradingResult)
               .join(Chart, GradingResult.chart_id == Chart.id)
               .join(Batch, GradingResult.batch_id == Batch.id)
               .filter(Chart.chart_number == chart_number,
                       GradingResult.total_score.isnot(None),
                       Batch.is_direct_assignment == False)
               .all())
    coders = []
    for r in results:
        missed = [f.ak_code for f in r.feedback if f.issue_type.value == "Missed" and f.ak_code]
        coders.append({
            "coder_name": r.coder_name,
            "batch_name": r.batch.name if r.batch else None,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail.value if r.pass_fail else None,
            "missed_codes": missed,
        })
    return {
        "chart_number": chart_number,
        "coders": sorted(coders, key=lambda x: x["total_score"] or 0),
    }


@router.get("/coders")
def list_coders(
    q: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Searchable coder directory.

    Built from BOTH the batch roster and graded results, so it includes coders
    who only appear in open batches or direct assignments — the coder-matrix
    endpoint the picker used before is restricted to CLOSED, non-direct batches,
    so those people were simply unselectable.

    Also far cheaper: coder-matrix computes an N x M grid of every result just to
    yield a name list.
    """
    people: dict = {}

    def _key(name: str, emp: Optional[str]) -> str:
        # emp_id is the identity when present; name only as a fallback
        return f"E:{emp}" if emp else f"N:{(name or '').strip().lower()}"

    for name, emp in (db.query(BatchCoder.coder_name, BatchCoder.emp_id)
                      .filter(BatchCoder.coder_name.isnot(None)).all()):
        k = _key(name, emp)
        people.setdefault(k, {"coder_name": name, "emp_id": emp or None,
                              "result_count": 0, "last_activity": None,
                              "name_variants": set()})
        people[k]["name_variants"].add(name)

    rows = (db.query(GradingResult.coder_name, GradingResult.emp_id,
                     func.count(GradingResult.id).label("n"),
                     func.max(GradingResult.graded_at).label("last"))
            .group_by(GradingResult.coder_name, GradingResult.emp_id).all())
    for name, emp, n, last in rows:
        k = _key(name, emp)
        rec = people.setdefault(k, {"coder_name": name, "emp_id": emp or None,
                                    "result_count": 0, "last_activity": None,
                                    "name_variants": set()})
        rec["result_count"] += n or 0
        rec["name_variants"].add(name)
        if last and (rec["last_activity"] is None or last > rec["last_activity"]):
            rec["last_activity"] = last
        if emp and not rec["emp_id"]:
            rec["emp_id"] = emp

    out = []
    for rec in people.values():
        variants = sorted(v for v in rec["name_variants"] if v)
        out.append({
            "coder_name": rec["coder_name"],
            "emp_id": rec["emp_id"],
            "result_count": rec["result_count"],
            "last_activity": rec["last_activity"].isoformat() if rec["last_activity"] else None,
            # Surfaced so a trainer can SEE that one person is spelled two ways
            # rather than silently getting a split history.
            "name_variants": variants if len(variants) > 1 else [],
        })

    if q:
        needle = q.strip().lower()
        out = [c for c in out
               if needle in (c["coder_name"] or "").lower()
               or needle in (c["emp_id"] or "").lower()]

    out.sort(key=lambda c: (-c["result_count"], (c["coder_name"] or "").lower()))
    return {"coders": out[:max(1, min(limit, 500))], "total": len(out)}
