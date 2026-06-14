"""Analytics endpoints for PracticeLab."""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer
from database import get_db
from models import Batch, BatchStatus, GradingResult, GradingFeedback, Chart, PassFail, Specialty

router = APIRouter()


def _gr_base(db: Session, from_date: Optional[str], to_date: Optional[str], specialty: Optional[str]):
    q = db.query(GradingResult).filter(GradingResult.total_score.isnot(None))
    if from_date:
        q = q.filter(GradingResult.graded_at >= from_date)
    if to_date:
        q = q.filter(GradingResult.graded_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(GradingResult.specialty == spec)
    return q


def _batch_base(db: Session, from_date: Optional[str], to_date: Optional[str], specialty: Optional[str]):
    q = db.query(Batch)
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
    base = _gr_base(db, from_date, to_date, specialty)
    total_results = base.count()
    passed = base.filter(GradingResult.pass_fail == PassFail.PASS).count()

    b_base = _batch_base(db, from_date, to_date, specialty)
    return {
        "total_batches": b_base.count(),
        "open_batches": b_base.filter(Batch.status == BatchStatus.OPEN).count(),
        "complete_batches": b_base.filter(Batch.status == BatchStatus.CLOSED).count(),
        "total_graded": total_results,
        "total_passed": passed,
        "overall_pass_rate": round(passed / total_results * 100, 1) if total_results else 0,
    }


@router.get("/analytics/by-specialty")
def analytics_by_specialty(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    base = _gr_base(db, from_date, to_date, specialty)
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
    results = _gr_base(db, from_date, to_date, specialty).join(Chart).all()

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
    batches = _batch_base(db, from_date, to_date, specialty).order_by(Batch.created_at.desc()).all()
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
            "chart_count": len(d["scores"]),
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
        }
        for bid, d in batch_scores.items()
    ]


@router.get("/analytics/by-category")
def analytics_by_category(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = _gr_base(db, from_date, to_date, specialty).join(Chart).all()

    if not results:
        return {"team": [], "coder_category": []}

    cat_map: dict = {}
    for r in results:
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

    return {"team": team, "coder_category": coder_category}


@router.get("/analytics/chart-teaching-value")
def analytics_chart_teaching_value(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = _gr_base(db, from_date, to_date, specialty).join(Chart).all()

    if not results:
        return []

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
            chart_map[cn]["error_variety"].add(f.issue_type.value)

    out = []
    for d in chart_map.values():
        avg = round(sum(d["scores"]) / len(d["scores"]), 1)
        pass_rate = round(d["passed"] / d["total"] * 100, 1)
        error_variety = len(d["error_variety"])
        attempts = d["total"]

        if attempts < 2:
            label = "Underused"
        elif avg >= 90:
            label = "Too Easy"
        elif pass_rate <= 40 and error_variety >= 2:
            label = "High Confusion"
        elif 50 <= pass_rate <= 85 and error_variety >= 2 and attempts >= 3:
            label = "High Yield"
        elif pass_rate <= 40:
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
    b_q = db.query(Batch).filter(Batch.status == BatchStatus.CLOSED)
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
                })

    return {
        "batches": [{"id": b.id, "name": b.name, "specialty": b.specialty.value} for b in batches],
        "coders": all_coders,
        "cells": cells,
    }


@router.get("/analytics/chart-detail/{chart_number:path}")
def chart_detail(chart_number: str, db: Session = Depends(get_db)):
    results = (db.query(GradingResult)
               .join(Chart, GradingResult.chart_id == Chart.id)
               .filter(Chart.chart_number == chart_number,
                       GradingResult.total_score.isnot(None))
               .all())
    coders = []
    for r in results:
        missed = [f.ak_code for f in r.feedback if f.issue_type.value == "Missed" and f.ak_code]
        coders.append({
            "coder_name": r.coder_name,
            "batch_name": r.batch.name if r.batch else None,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail.value if r.pass_fail else None,
            "missed_codes": missed[:5],
        })
    return {
        "chart_number": chart_number,
        "coders": sorted(coders, key=lambda x: x["total_score"] or 0),
    }
