"""Analytics endpoints for PracticeLab."""
import io
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func, Integer, text
from database import get_db
from models import Batch, BatchCoder, BatchStatus, GradingResult, GradingFeedback, Chart, PassFail, Specialty, ScoringConfig
from services.pdf_report_service import generate_coder_report_pdf
from .shared import _uses_dpo
from services.download_headers import content_disposition

router = APIRouter()


def _with_details(q):
    """
    Load the relationships these endpoints walk, in bulk.

    Every analytics endpoint here iterates r.feedback, r.chart and r.batch.
    Lazily, that is one query PER RESULT — at 20,000 graded charts the teaching
    signals endpoint fired ~60,000 queries to answer one request. Invisible at
    a few hundred results and the first thing to fall over at scale.

    selectinload for the collection (one extra query for all of them),
    joinedload for the many-to-ones (folded into the same query).
    """
    return q.options(
        selectinload(GradingResult.feedback),
        joinedload(GradingResult.chart),
        joinedload(GradingResult.batch),
    )


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


def _pass_thresholds(db) -> dict:
    """
    Pass threshold per specialty, resolved from the scoring configs.

    The frontend used to hardcode which specialties were "OP-like" to pick a
    colour threshold, and that list silently went stale when Surgery and
    ED Single Path were added — both were graded against the IP threshold (80)
    instead of OP (90). Deriving it here means the list cannot drift again.
    """
    from .shared import _is_ip, _is_single_path, _is_ed
    from .em_grading import _is_em

    def _cfg(stype, default):
        row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == stype).first()
        return (row.pass_threshold or default) if row else default

    ip, op, edsp = _cfg("IP", 80), _cfg("OP", 90), _cfg("EDSP", 90)
    em = 80
    try:
        row = db.execute(text("SELECT pass_threshold FROM em_scoring_configs WHERE id=1")).fetchone()
        if row and row[0]:
            em = row[0]
    except Exception:
        pass

    out = {}
    for s in Specialty:
        if _is_ed(s):
            continue                     # rubric-graded, no numeric threshold
        if _is_ip(s):
            out[s.value] = ip
        elif _is_single_path(s):
            out[s.value] = edsp
        elif _is_em(s):
            out[s.value] = em
        else:
            out[s.value] = op
    return out


@router.get("/analytics/overview")
def analytics_overview(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    scope=formal (default) — batch work only, the team view.
    scope=direct          — direct assignments only.
    scope=all             — both.

    Direct assignments were excluded with no way to see them, so anyone who
    practised only that way was invisible here and the numbers looked short
    with nothing explaining why. The default is unchanged; the other two are
    opt-in, because mixing one-off charts into batch trends by default would
    make the trend line mean something different.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")

    base = _gr_base(db, from_date, to_date, specialty,
                    exclude_direct=(scope == "formal"))
    if scope == "direct":
        base = base.join(Batch, GradingResult.batch_id == Batch.id).filter(
            Batch.is_direct_assignment == True)
    total_results = base.count()
    passed = base.filter(GradingResult.pass_fail == PassFail.PASS).count()

    b_base = db.query(Batch)
    if scope == "formal":
        b_base = b_base.filter(Batch.is_direct_assignment == False)
    elif scope == "direct":
        b_base = b_base.filter(Batch.is_direct_assignment == True)
    if from_date:
        b_base = b_base.filter(Batch.created_at >= from_date)
    if to_date:
        b_base = b_base.filter(Batch.created_at <= to_date + "T23:59:59")
    if specialty:
        _s = next((s for s in Specialty if s.value == specialty), None)
        if _s:
            b_base = b_base.filter(Batch.specialty == _s)

    # ── Which specialties are getting practice, and which are going wrong ────
    # Two different questions that look alike:
    #
    #   Practice volume answers "where is the training effort going" — a
    #   specialty nobody practises is a coverage gap, and it will never appear
    #   in any performance view precisely because it has no results.
    #
    #   Error density answers "where is it going wrong". It must be per chart:
    #   ranking specialties by raw error count ranks them by how much they were
    #   practised, so the "cleanest" specialty is usually the one nobody
    #   touched. Specialties under a minimum volume are excluded from the
    #   best/worst pick rather than winning on a handful of charts.
    MIN_CHARTS_TO_RANK = 5

    vol_rows = (base.with_entities(GradingResult.specialty,
                                   func.count(GradingResult.id).label("n"))
                    .group_by(GradingResult.specialty).all())
    practised = [{"specialty": r.specialty.value, "charts": r.n} for r in vol_rows if r.specialty]
    practised.sort(key=lambda x: -x["charts"])

    err_rows = (base.join(GradingFeedback, GradingFeedback.result_id == GradingResult.id)
                    .with_entities(GradingResult.specialty,
                                   func.count(GradingFeedback.id).label("n"))
                    .group_by(GradingResult.specialty).all())
    err_by_spec = {r.specialty.value: r.n for r in err_rows if r.specialty}

    density = sorted(
        [{"specialty": p["specialty"], "charts": p["charts"],
          "errors": err_by_spec.get(p["specialty"], 0),
          "errors_per_chart": round(err_by_spec.get(p["specialty"], 0) / p["charts"], 2)}
         for p in practised if p["charts"] >= MIN_CHARTS_TO_RANK],
        key=lambda x: -x["errors_per_chart"])

    # A specialty with charts in the library but NO graded work is the coverage
    # gap worth surfacing — it is invisible everywhere else by definition.
    from models.charts import ChartStatus as _CS
    lib_specs = {r[0].value for r in db.query(Chart.specialty)
                 .filter(Chart.status == _CS.ACTIVE).distinct().all() if r[0]}
    untouched = sorted(lib_specs - {p["specialty"] for p in practised})

    ip_cfg = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
    op_cfg = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()

    return {
        "total_batches": b_base.count(),
        "open_batches": b_base.filter(Batch.status == BatchStatus.OPEN).count(),
        "complete_batches": b_base.filter(Batch.status == BatchStatus.CLOSED).count(),
        "total_graded": total_results,
        "total_passed": passed,
        "overall_pass_rate": round(passed / total_results * 100, 1) if total_results else 0,
        "pass_rate_basis": "chart",
        "ip_pass_threshold": (ip_cfg.pass_threshold or 80) if ip_cfg else 80,
        "op_pass_threshold": (op_cfg.pass_threshold or 90) if op_cfg else 90,
        # Per-specialty, so nothing downstream has to guess which are OP-like
        "pass_thresholds": _pass_thresholds(db),
        # The two tiles are filtered on DIFFERENT dates — batch counts on when
        # the batch was created, grading counts on when it was graded. Stated so
        # the UI can label them rather than leaving the mismatch to be inferred.
        "most_practised": practised[0] if practised else None,
        "least_practised": practised[-1] if len(practised) > 1 else None,
        "most_errors": density[0] if density else None,
        "least_errors": density[-1] if len(density) > 1 else None,
        "untouched_specialties": untouched,
        "min_charts_to_rank": MIN_CHARTS_TO_RANK,
        "batch_date_field": "created_at",
        "graded_date_field": "graded_at",
        "scope": scope,
    }


@router.get("/analytics/by-specialty")
def analytics_by_specialty(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    # Must honour the same scope as /overview — the Needs-attention banner is
    # rendered from this, so a mismatched scope would contradict the tiles.
    base = _gr_base(db, from_date, to_date, specialty,
                    exclude_direct=(scope == "formal"))
    if scope == "direct":
        base = base.join(Batch, GradingResult.batch_id == Batch.id).filter(
            Batch.is_direct_assignment == True)
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
            # CHART pass rate — what share of graded charts passed. Batch
            # summaries report a CODER pass rate under the same key.
            "pass_rate": round(float(r.passed or 0) / r.total * 100, 1) if r.total else 0,
            "pass_rate_basis": "chart",
        }
        for r in rows
    ]


def _key_counts(db, spec: Specialty) -> dict:
    """
    How many ACTIVE charts in this specialty are ready to practise.

    "Ready" means a complete answer key exists — a chart without one cannot be
    graded, so it is inventory, not capacity. Which table holds the key depends
    on the specialty: E/M and ED Profee use em_answer_keys, everything else
    answer_keys, and the rubric ED specialties have no key at all.
    """
    from .shared import _is_ed
    from .em_grading import _is_em
    from models import AnswerKey
    from models.charts import ChartStatus

    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE,
                               Chart.specialty == spec)
    total = q.count()
    if _is_ed(spec):
        return {"total_charts": total, "practice_ready": total,
                "awaiting_key": 0, "uses_answer_keys": False}
    if _is_em(spec):
        ready = db.execute(text(
            "SELECT COUNT(*) FROM em_answer_keys k JOIN charts c ON c.id = k.chart_id "
            "WHERE c.specialty = :s AND c.status = :st"
        ), {"s": spec.name, "st": ChartStatus.ACTIVE.name}).scalar() or 0
    else:
        ready = q.join(AnswerKey, AnswerKey.chart_id == Chart.id).count()
    return {"total_charts": total, "practice_ready": ready,
            "awaiting_key": max(0, total - ready), "uses_answer_keys": True}


@router.get("/analytics/specialty-profile")
def specialty_profile(
    specialty: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    scope: str = "formal",
    well_cleared_at: int = 70, struggling_below: int = 50, min_attempts: int = 3,
    db: Session = Depends(get_db),
):
    """
    Everything about ONE specialty in one place — the thing Tab 2 could not do.

    The bar chart answers "which specialty is weakest"; it cannot answer "what
    is the state of IP-DRG". That needs library inventory, participation and
    outcome side by side, plus where this specialty sits against the others —
    a rank is the only figure here that a per-specialty view cannot compute
    for itself.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")
    spec = next((s for s in Specialty if s.value == specialty), None)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown specialty: {specialty}")

    def _scoped(sp: Optional[str]):
        q = _gr_base(db, from_date, to_date, sp, exclude_direct=(scope == "formal"))
        if scope == "direct":
            q = q.join(Batch, GradingResult.batch_id == Batch.id).filter(
                Batch.is_direct_assignment == True)
        return q

    results = _scoped(specialty).all()
    thresholds = _pass_thresholds(db)
    pass_threshold = thresholds.get(spec.value)

    total = len(results)
    passed = sum(1 for r in results if r.pass_fail == PassFail.PASS)
    avg_score = round(sum(r.total_score for r in results) / total, 1) if total else 0.0

    # Per coder: identity is emp_id where present, else the name (same rule as
    # the coder directory — two spellings of one person must not become two).
    coders: dict[str, list] = {}
    for r in results:
        coders.setdefault(r.emp_id or r.coder_name, []).append(r)
    # A coder "clears" by passing MORE THAN HALF their charts. This is the same
    # majority rule batch results use; it is not an average-score comparison.
    cleared = sum(1 for rs in coders.values()
                  if sum(1 for r in rs if r.pass_fail == PassFail.PASS) > len(rs) / 2)

    # Per chart, so "where are people struggling" is about charts, not coders.
    per_chart: dict[int, list] = {}
    for r in results:
        per_chart.setdefault(r.chart_id, []).append(r)
    chart_rows = []
    for cid, rs in per_chart.items():
        ch = rs[0].chart
        p = sum(1 for r in rs if r.pass_fail == PassFail.PASS)
        chart_rows.append({
            "chart_number": ch.chart_number if ch else str(cid),
            "category": ch.category if ch else None,
            "attempts": len(rs),
            "pass_rate": round(p / len(rs) * 100, 1),
            "avg_score": round(sum(r.total_score for r in rs) / len(rs), 1),
        })
    # Charts with one or two attempts swing between 0% and 100% on a single
    # result, so they are counted but never labelled well-cleared or struggling.
    rated = [c for c in chart_rows if c["attempts"] >= min_attempts]
    well = [c for c in rated if c["pass_rate"] >= well_cleared_at]
    struggling = sorted([c for c in rated if c["pass_rate"] < struggling_below],
                        key=lambda c: c["pass_rate"])

    # Rank against the other specialties under the same scope and filters.
    peers = []
    for row in _scoped(None).with_entities(
            GradingResult.specialty,
            func.count(GradingResult.id).label("n"),
            func.avg(GradingResult.total_score).label("avg"),
            func.sum(func.cast(GradingResult.pass_fail == PassFail.PASS, Integer)).label("p"),
    ).group_by(GradingResult.specialty).all():
        peers.append({"specialty": row.specialty.value,
                      "avg_score": round(float(row.avg or 0), 1),
                      "pass_rate": round(float(row.p or 0) / row.n * 100, 1) if row.n else 0.0})

    def _rank(key):
        ordered = sorted(peers, key=lambda p: p[key], reverse=True)
        for i, p in enumerate(ordered, 1):
            if p["specialty"] == spec.value:
                return i
        return None

    missed = Counter()
    for r in results:
        for f in r.feedback:
            if f.issue_type.value == "Missed" and f.ak_code:
                missed[f.ak_code] += 1

    return {
        "specialty": spec.value,
        "scope": scope,
        "pass_threshold": pass_threshold,
        "library": _key_counts(db, spec),
        "activity": {
            "attempts": total,
            "coders": len(coders),
            "charts_attempted": len(per_chart),
        },
        "performance": {
            "avg_score": avg_score,
            "chart_pass_rate": round(passed / total * 100, 1) if total else 0.0,
            "coder_clear_rate": round(cleared / len(coders) * 100, 1) if coders else 0.0,
            "coders_cleared": cleared,
            "pass_rate_basis": "chart",
            "clear_rate_basis": "coder",
            "coder_clear_rule": "majority of charts passed",
        },
        "standing": {
            "peers": len(peers),
            "rank_by_avg_score": _rank("avg_score"),
            "rank_by_pass_rate": _rank("pass_rate"),
            "peer_avg_score": round(sum(p["avg_score"] for p in peers) / len(peers), 1) if peers else None,
            "peer_pass_rate": round(sum(p["pass_rate"] for p in peers) / len(peers), 1) if peers else None,
        },
        "charts": {
            "rated": len(rated),
            "well_cleared": len(well),
            "struggling": len(struggling),
            "low_sample": len(chart_rows) - len(rated),
            "well_cleared_at": well_cleared_at,
            "struggling_below": struggling_below,
            "min_attempts": min_attempts,
            "struggling_list": struggling[:10],
        },
        "top_missed_codes": [{"code": c, "count": n} for c, n in missed.most_common(5)],
    }


@router.get("/analytics/by-chart")
def analytics_by_chart(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    Every attempted chart, worst first — the inspection view.

    Distinct from Chart Signals, which classifies charts so you know WHICH to
    look at. This one is what you open once you know: the score, the codes
    people miss on it, and which coders those were.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")
    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                                     exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    thresholds = _pass_thresholds(db)

    chart_map: dict[int, dict] = {}
    for r in results:
        cid = r.chart_id
        if cid not in chart_map:
            chart_map[cid] = {
                "chart_number": r.chart.chart_number,
                "specialty": r.chart.specialty.value,
                "category": r.chart.category,
                "scores": [], "missed": {}, "passed": 0,
            }
        chart_map[cid]["scores"].append(r.total_score)
        if r.pass_fail and r.pass_fail.value == "PASS":
            chart_map[cid]["passed"] += 1
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
            "pass_rate": round(d["passed"] / len(d["scores"]) * 100, 1),
            # The bar this chart is judged against, so a score is readable
            # without knowing the specialty's threshold by heart.
            "pass_threshold": thresholds.get(d["specialty"]),
            "top_missed": sorted(d["missed"].items(), key=lambda x: -x[1])[:5],
        }
        for d in sorted(chart_map.values(), key=lambda x: sum(x["scores"]) / len(x["scores"]))
    ]


@router.get("/analytics/by-batch")
def analytics_by_batch(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    q = _batch_base(db, from_date, to_date, specialty)
    if scope != "formal":
        # _batch_base hard-excludes direct assignments; rebuild without that
        q = db.query(Batch)
        if scope == "direct":
            q = q.filter(Batch.is_direct_assignment == True)
        if from_date:
            q = q.filter(Batch.created_at >= from_date)
        if to_date:
            q = q.filter(Batch.created_at <= to_date + "T23:59:59")
        if specialty:
            _s = next((s for s in Specialty if s.value == specialty), None)
            if _s:
                q = q.filter(Batch.specialty == _s)
    batches = q.order_by(Batch.created_at.asc()).all()
    out = []
    for b in batches:
        results = [r for r in b.results if r.total_score is not None]
        if not results:
            continue
        scores = [r.total_score for r in results]
        passed = sum(1 for r in results if r.pass_fail == PassFail.PASS)
        graded = [r.graded_at for r in results if r.graded_at]
        out.append({
            "batch_id": b.id,
            "batch_name": b.name,
            "specialty": b.specialty.value,
            "is_direct_assignment": bool(b.is_direct_assignment),
            "created_at": b.created_at.isoformat() if b.created_at else None,
            # The two dates this row lives under, both returned so the UI never
            # has to imply that one stands for the other: rows are FILTERED on
            # created_at and the work happened on graded_at.
            "last_graded_at": max(graded).isoformat() if graded else None,
            # emp_id is the coder identity everywhere else — the directory, the
            # deep dive, GradingResult itself. Counting distinct NAMES here made
            # "Asha R" and "asha  r" two coders and inflated the column.
            "coder_count": len({r.emp_id or r.coder_name for r in results}),
            "chart_count": len({r.chart_id for r in results}),
            "graded_count": len(results),
            "avg_score": round(sum(scores) / len(scores), 1),
            # CHART pass rate — the share of graded charts that passed. The
            # batch RESULTS screen reports a CODER pass rate under this key.
            "pass_rate": round(passed / len(results) * 100, 1),
            "pass_rate_basis": "chart",
        })
    return out


@router.get("/analytics/by-batch.xlsx")
def analytics_by_batch_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    specialty: Optional[str] = None, scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    The By Batch table as Excel — same rows, same filters, same scope.

    Distinct from the batch-list export, which is the roster view (coders,
    cycles, status — how a batch was SET UP). This is the performance view
    (scores, pass rates — how it WENT), and it inherits this tab's scope switch
    and date range rather than the list panel's status tabs.
    """
    from services.excel_service import export_batch_analytics
    from services.download_headers import content_disposition

    rows = analytics_by_batch(from_date, to_date, specialty, scope, db)
    thresholds = _pass_thresholds(db)

    out = []
    for r in rows:
        pt = thresholds.get(r["specialty"])
        out.append({
            "batch_name": r["batch_name"],
            "type": "Direct" if r.get("is_direct_assignment") else "Batch",
            "specialty": r["specialty"],
            "created_at": (r["created_at"] or "")[:10],
            "coder_count": r["coder_count"],
            "chart_count": r["chart_count"],
            "graded_count": r["graded_count"],
            "pass_threshold": pt,
            "avg_score": r["avg_score"],
            "pass_rate": r["pass_rate"],
            # Precomputed so the spreadsheet carries the same judgement the
            # screen shows, rather than leaving the reader to reapply a rule
            # that differs by specialty.
            "below_target": "Yes" if (pt is not None and r["avg_score"] < pt) or r["pass_rate"] < 70 else "",
            "last_graded_at": (r.get("last_graded_at") or "")[:10],
        })

    return StreamingResponse(
        io.BytesIO(export_batch_analytics(out)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Batch_Performance.xlsx", "Batch_Performance.xlsx"),
    )


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
                "is_direct": bool(getattr(r.batch, "is_direct_assignment", False)),
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
    # build_coder_summary walks feedback, chart and batch on every row.
    results = _with_details(q).all()
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
                "is_direct": bool(getattr(r.batch, "is_direct_assignment", False)),
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
            # A coder view mixes formal batches with one-off direct
            # assignments by design. Without this the two are indistinguishable
            # in the history, and a run of direct work reads as batch work.
            "is_direct_assignment": d["is_direct"],
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

    # ── What this coder actually works on ────────────────────────────────────
    # Reports headed "All practice & batch work" said nothing a reader could
    # use. What they need is WHICH specialties, because that is what the scores
    # in the report are scores in.
    spec_counts = Counter(r.specialty.value for r in scored if r.specialty)
    specialty_mix = [{"specialty": sp, "charts": n} for sp, n in spec_counts.most_common()]

    graded_dates = [r.graded_at for r in results if r.graded_at]
    last_activity = max(graded_dates).isoformat() if graded_dates else None

    # PCS and CPT are different code sets, and a trainer reads "Procedure
    # accuracy" as whichever their specialty uses. Name it when unambiguous.
    ip_specs = {"IP-DRG"}
    mix = set(spec_counts)
    if mix and mix <= ip_specs:
        proc_label = "PCS accuracy"
    elif mix and not (mix & ip_specs):
        proc_label = "CPT accuracy"
    else:
        proc_label = "Procedure accuracy (PCS + CPT)"

    return {
        "specialty_mix": specialty_mix,
        "last_activity": last_activity,
        "proc_label": proc_label,
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
        headers=content_disposition(f"{coder_name}_Performance_Report.pdf", "Coder_Report.pdf"),
    )


@router.get("/analytics/by-category")
def analytics_by_category(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    Topic mastery: how the team and each coder perform per chart topic.

    Honours the page scope switch, which it previously ignored — so this tab
    could show batch-and-direct figures while the three tabs before it showed
    batch-only, with nothing on screen explaining the disagreement.

    Under `formal` the long-standing split is preserved: team averages are
    batch work (direct assignments are one-offs and would dilute a team
    figure), while coder rows cover everything a coder did. Choosing `direct`
    or `all` applies to both, because at that point the trainer has asked for a
    specific population and the split would override their choice.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")

    results = _with_details(_gr_base(db, from_date, to_date, specialty)).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    if not results:
        return {"team": [], "coder_category": [], "scope": scope}

    if scope == "formal":
        team_results = [r for r in results if not r.batch.is_direct_assignment]
    else:
        team_results = results

    def _topic_key(name: str) -> str:
        """
        Topics are free text typed at chart upload, so "Sepsis", "sepsis" and
        "Sepsis " are one topic that would otherwise be reported as three —
        each with a fraction of the attempts and its own average.
        """
        return (name or "").strip().casefold()

    thresholds = _pass_thresholds(db)

    cat_map: dict = {}
    for r in team_results:
        key = _topic_key(r.chart.category)
        if key not in cat_map:
            cat_map[key] = {"label": (r.chart.category or "").strip(), "scores": [],
                            "passed": 0, "total": 0, "coders": set(), "specialties": set()}
        cat_map[key]["scores"].append(r.total_score)
        cat_map[key]["total"] += 1
        # emp_id is the coder identity everywhere else; counting names here made
        # one person entered two ways look like two coders on the topic.
        cat_map[key]["coders"].add(r.emp_id or r.coder_name)
        cat_map[key]["specialties"].add(r.chart.specialty.value)
        if r.pass_fail and r.pass_fail.value == "PASS":
            cat_map[key]["passed"] += 1

    def _topic_threshold(specialties: set):
        """A topic spanning specialties has no single pass mark; say so rather
        than picking one and colouring against a bar that does not apply."""
        marks = {thresholds.get(s) for s in specialties} - {None}
        return marks.pop() if len(marks) == 1 else None

    team = sorted([
        {
            "category": d["label"],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "pass_rate": round(d["passed"] / d["total"] * 100, 1),
            "pass_rate_basis": "chart",
            "attempt_count": d["total"],
            "coder_count": len(d["coders"]),
            "specialties": sorted(d["specialties"]),
            "pass_threshold": _topic_threshold(d["specialties"]),
        }
        for d in cat_map.values()
    ], key=lambda x: x["avg_score"])

    coder_cat: dict = {}
    for r in results:
        key = (r.emp_id or r.coder_name, _topic_key(r.chart.category))
        if key not in coder_cat:
            coder_cat[key] = {"name": r.coder_name, "emp_id": r.emp_id,
                              "label": (r.chart.category or "").strip(),
                              "scores": [], "passed": 0, "total": 0,
                              "specialties": set()}
        coder_cat[key]["scores"].append(r.total_score)
        coder_cat[key]["total"] += 1
        coder_cat[key]["specialties"].add(r.chart.specialty.value)
        if r.pass_fail and r.pass_fail.value == "PASS":
            coder_cat[key]["passed"] += 1

    coder_category = [
        {
            "coder_name": d["name"],
            "emp_id": d["emp_id"],
            "category": d["label"],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "pass_rate": round(d["passed"] / d["total"] * 100, 1),
            "attempt_count": d["total"],
            "pass_threshold": _topic_threshold(d["specialties"]),
            "specialties": sorted(d["specialties"]),
        }
        for d in coder_cat.values()
    ]

    return {
        "team": team,
        "coder_category": coder_category,
        "scope": scope,
        "coder_scope_note": (
            "Coder rows include direct assignments and standalone grades. "
            "Team averages reflect formal batches only."
            if scope == "formal" else
            f"Both team and coder rows cover {'direct assignments only' if scope == 'direct' else 'batches and direct assignments'}."
        ),
    }


# What a teaching label means, in one place, so the UI describes the rule that
# actually ran rather than a remembered version of it.
TEACHING_MIN_ATTEMPTS = 2          # below this, one result decides the label
TEACHING_YIELD_MIN_ATTEMPTS = 3
TEACHING_FAIL_SHARE = 50           # share of attempts passing, NOT a score
TEACHING_STRONG_SHARE = 80


@router.get("/analytics/chart-teaching-value")
def analytics_chart_teaching_value(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    Which charts are worth teaching with, from what coders actually did on them.

    Two things this gets right that it previously did not:

    ONE THRESHOLD PER CHART, not one per request. The rule used to pick a
    single IP-or-OP threshold for the whole response based on whether ANY
    IP result was present — so in an all-specialty view every SDS and Surgery
    chart was labelled against IP's 80 when their own bar is 90. A chart's
    label is now decided by its own specialty's pass mark.

    SHARES COMPARED TO SHARES. "How many attempts passed" is a population
    figure; the pass threshold is a per-chart score. The old rule compared them
    directly (`pass_rate <= tv_threshold`), which is the same units error that
    coloured healthy specialties red on the Overview tab — it just labelled
    charts instead of colouring them.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")

    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                            exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    if not results:
        return []

    thresholds = _pass_thresholds(db)

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

        # This chart's own pass mark, not the request's.
        pt = thresholds.get(d["specialty"]) or 80
        too_easy_at = pt + max(5, (100 - pt) // 2)

        if attempts < TEACHING_MIN_ATTEMPTS:
            label = "Underused"
        elif avg >= too_easy_at:
            label = "Too Easy"
        elif pass_rate < TEACHING_FAIL_SHARE and error_variety >= 3:
            label = "High Confusion"
        elif (TEACHING_FAIL_SHARE <= pass_rate <= TEACHING_STRONG_SHARE
              and error_variety >= 2 and attempts >= TEACHING_YIELD_MIN_ATTEMPTS):
            label = "High Yield"
        elif pass_rate < TEACHING_FAIL_SHARE:
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
            # The bar this chart was judged against, so the UI can colour and
            # explain it without re-deriving a rule it might get wrong.
            "pass_threshold": pt,
            "too_easy_at": too_easy_at,
        })

    # Ordered by what a trainer should look at first. Alphabetical put
    # "High Confusion" above "High Yield" for no reason beyond the letter C.
    priority = {"High Confusion": 0, "High Fail": 1, "High Yield": 2,
                "Standard": 3, "Too Easy": 4, "Underused": 5}
    return sorted(out, key=lambda x: (priority.get(x["teaching_label"], 9), -x["attempt_count"]))


@router.get("/analytics/error-analysis")
def analytics_error_analysis(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal", section: Optional[str] = None, issue_type: Optional[str] = None,
    code_search: Optional[str] = None, pattern: Optional[str] = None,
    include_scattered: bool = False,
    limit: int = 200, offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Errors as the unit, not coders or charts.

    Every other tab is keyed on a THING — a coder, a chart, a batch, a topic —
    and reports errors as an attribute of it. That answers "how did X do" and
    cannot answer "what is this team getting wrong", because the same mistake
    is scattered across every row that happened to contain it.

    The figure this exists for is CONCENTRATION. A code missed forty times is
    meaningless on its own:

      40 misses by 1 coder   -> coaching. One person has a habit.
      40 misses by 20 coders -> curriculum. The team was never taught it.
      40 misses on 1 chart   -> the chart or its answer key is the problem.

    Same count, three different actions. So every row carries how many distinct
    coders and charts it touches, and a concentration ratio that says which of
    the three it is.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")

    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                                     exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    items = []
    for r in results:
        for f in r.feedback:
            if section and f.section.value != section:
                continue
            if issue_type and f.issue_type.value != issue_type:
                continue
            items.append((r, f))

    total = len(items)
    if not total:
        return {"total_errors": 0, "graded_charts": len(results), "by_issue_type": [],
                "by_section": [], "codes": [], "trend": [], "scope": scope}

    def _share(n):
        return round(n / total * 100, 1)

    by_issue = Counter(f.issue_type.value for _, f in items)
    by_section = Counter(f.section.value for _, f in items)

    # ── Per code ─────────────────────────────────────────────────────────────
    codes: dict = {}
    for r, f in items:
        code = f.ak_code or f.coder_code
        if not code:
            continue
        d = codes.setdefault(code, {
            "code": code, "count": 0, "coders": set(), "charts": set(),
            "specialties": set(), "sections": Counter(), "issues": Counter(),
            "last_seen": None,
        })
        d["count"] += 1
        d["coders"].add(r.emp_id or r.coder_name)
        d["charts"].add(r.chart.chart_number if r.chart else r.chart_id)
        if r.specialty:
            d["specialties"].add(r.specialty.value)
        d["sections"][f.section.value] += 1
        d["issues"][f.issue_type.value] += 1
        if r.graded_at and (d["last_seen"] is None or r.graded_at > d["last_seen"]):
            d["last_seen"] = r.graded_at

    def _verdict(d):
        """Which of the three problems this is — the point of the whole tab."""
        n_coders, n_charts = len(d["coders"]), len(d["charts"])
        if n_coders == 1 and d["count"] >= 3:
            return "One coder", "Repeated by a single coder — coaching, not curriculum"
        if n_charts == 1 and n_coders >= 3:
            return "One chart", "Many coders miss it on the same chart — check that chart's answer key"
        if n_coders >= 3 and n_charts >= 2:
            return "Team-wide", "Missed by several coders across several charts — a teaching gap"
        return "Scattered", "Too few occurrences to call a pattern yet"

    code_rows = []
    for d in codes.values():
        label, why = _verdict(d)
        code_rows.append({
            "code": d["code"],
            "count": d["count"],
            "coders_affected": len(d["coders"]),
            "charts_affected": len(d["charts"]),
            "specialties": sorted(d["specialties"]),
            "top_section": d["sections"].most_common(1)[0][0],
            "issue_breakdown": [{"type": t, "count": c} for t, c in d["issues"].most_common()],
            # Errors per coder: high means concentrated in few people.
            "per_coder": round(d["count"] / len(d["coders"]), 1) if d["coders"] else 0,
            "pattern": label,
            "pattern_reason": why,
            "last_seen": d["last_seen"].isoformat() if d["last_seen"] else None,
        })
    code_rows.sort(key=lambda x: -x["count"])

    # ── Which code rows come back ────────────────────────────────────────────
    # This list grows with every graded chart and never shrinks — a code missed
    # once a year ago is still a row. It used to be truncated at 200 with the
    # client searching inside that slice, so a code ranked 250th was both
    # unreachable and unfindable, and the count on screen described the slice
    # rather than the data.
    #
    # Search and pattern therefore run HERE, before the cut.
    filtered = code_rows
    # "Scattered" means too few occurrences to call a pattern — by definition
    # the rows a trainer cannot act on. They are most of the list on real data
    # and none of the decisions, so they are held back rather than dropped, and
    # the count is always reported.
    #
    # Searching or picking a pattern is an explicit request, so neither is
    # overruled: looking up a code and being told it does not exist — because
    # it happened twice — would be worse than a long list.
    scattered_count = sum(1 for c in code_rows if c["pattern"] == "Scattered")
    asked_for_specifics = bool(pattern) or bool(code_search and code_search.strip())
    if not include_scattered and not asked_for_specifics:
        filtered = [c for c in filtered if c["pattern"] != "Scattered"]
    if code_search and code_search.strip():
        term = code_search.strip().lower()
        filtered = [c for c in filtered if term in c["code"].lower()]
    if pattern:
        filtered = [c for c in filtered if c["pattern"] == pattern]

    # Default 200, as before server-side paging existed. Paging down to 25 per
    # request made every "Load more" a round trip that could fail quietly and
    # look like a shorter list — the search and filter now run here, which was
    # the actual point, and the page size does not need to be small to get it.
    matching_codes = len(filtered)
    limit = max(1, min(limit, 500))
    page = filtered[offset:offset + limit]

    # Counts for the pattern chips, over the whole set rather than the page —
    # a chip reading "Team-wide (3)" when there are 40 would be a lie.
    pattern_counts = Counter(c["pattern"] for c in code_rows)

    # ── Trend by month, so "are we fixing it" is answerable ──────────────────
    months: dict = {}
    for r, f in items:
        if not r.graded_at:
            continue
        key = r.graded_at.strftime("%Y-%m")
        months.setdefault(key, Counter())[f.issue_type.value] += 1

    # Charts graded per month, so the trend can be a RATE. A raw count rises
    # when practice volume rises — a team doubling its practice while halving
    # its error rate would show a flat line and read as no progress.
    month_charts: Counter = Counter()
    for r in results:
        if r.graded_at:
            month_charts[r.graded_at.strftime("%Y-%m")] += 1

    trend = [{"month": m,
              "total": sum(c.values()),
              "charts": month_charts.get(m, 0),
              "errors_per_chart": round(sum(c.values()) / month_charts[m], 2)
                                  if month_charts.get(m) else None,
              **{t: c.get(t, 0) for t in by_issue}}
             for m, c in sorted(months.items())]

    # ── Coverage ─────────────────────────────────────────────────────────────
    # This tab reads grading_feedback. E/M and ED Profee emit free-text issue
    # strings that do not map to the IssueType/GradingSection enums, so those
    # rows are skipped when practice results are mirrored — they live on in
    # practice_results.feedback and the E/M breakdown endpoint instead. Rubric
    # specialties (Edits, Denials) produce no code-level feedback at all.
    #
    # The tab therefore under-reports for those specialties, and a silent
    # under-report is worse than a gap: "no errors in E/M" reads as a clean
    # specialty. Counted and stated rather than left to be discovered.
    covered: dict = {}
    for r in results:
        if not r.specialty:
            continue
        sp = r.specialty.value
        c = covered.setdefault(sp, {"specialty": sp, "graded": 0, "with_feedback": 0})
        c["graded"] += 1
        if r.feedback:
            c["with_feedback"] += 1
    coverage = sorted(covered.values(), key=lambda x: x["specialty"])
    for c in coverage:
        c["represented"] = c["with_feedback"] > 0
    not_represented = [c["specialty"] for c in coverage if not c["represented"]]

    # ── Per specialty ────────────────────────────────────────────────────────
    # Raw error counts rank specialties by how much they were PRACTISED, so the
    # "cleanest" specialty is usually just the one nobody touched. Density —
    # errors per graded chart — is the comparable figure, and specialties under
    # a minimum volume are excluded from best/worst rather than winning by
    # having done almost nothing.
    spec_errors: Counter = Counter()
    for r, f in items:
        if r.specialty:
            spec_errors[r.specialty.value] += 1
    spec_charts: Counter = Counter()
    for r in results:
        if r.specialty:
            spec_charts[r.specialty.value] += 1

    MIN_CHARTS_TO_RANK = 5
    by_specialty = sorted(
        [{"specialty": sp,
          "errors": spec_errors.get(sp, 0),
          "charts": n,
          "errors_per_chart": round(spec_errors.get(sp, 0) / n, 2),
          "rankable": n >= MIN_CHARTS_TO_RANK}
         for sp, n in spec_charts.items()],
        key=lambda x: -x["errors_per_chart"])
    rankable = [x for x in by_specialty if x["rankable"]]
    worst_specialty = rankable[0] if rankable else None
    best_specialty = rankable[-1] if len(rankable) > 1 else None

    # ── Commentary ───────────────────────────────────────────────────────────
    # Written here rather than left to be inferred from four charts. Each line
    # names a finding AND what it implies, because "SDx is 62% of errors" is a
    # fact and "teach SDx capture next" is the decision it supports. Only
    # findings that clear a threshold appear — commentary that always says
    # something says nothing.
    notes = []

    top_section = by_section.most_common(1)[0] if by_section else None
    if top_section and _share(top_section[1]) >= 40:
        notes.append({
            "kind": "focus",
            "text": f"{top_section[0]} accounts for {_share(top_section[1])}% of all errors "
                    f"({top_section[1]} of {total}). One section dominating this heavily usually "
                    f"means a single teachable rule, not broad weakness.",
        })

    top_issue = by_issue.most_common(1)[0] if by_issue else None
    if top_issue and _share(top_issue[1]) >= 50:
        label = top_issue[0].replace("_", " ").lower()
        implication = {
            "missed": "coders are under-coding — the gap is recall, not judgement",
            "over coded": "coders are adding codes the record does not support — the gap is restraint",
            "wrong code": "the right concept is being found but the wrong code chosen — specificity drills",
            "wrong pointer": "linkage is the problem, not code selection",
            "wrong poa": "POA assignment specifically — a narrow, very teachable rule",
            "wrong modifier": "modifier rules specifically — a narrow, very teachable rule",
        }.get(label, "worth a targeted session")
        notes.append({
            "kind": "focus",
            "text": f"{_share(top_issue[1])}% of errors are \"{label}\" — {implication}.",
        })

    team_wide = [c for c in code_rows if c["pattern"] == "Team-wide"][:3]
    if team_wide:
        names = ", ".join(c["code"] for c in team_wide)
        notes.append({
            "kind": "curriculum",
            "text": f"Team-wide gaps: {names}. Several coders miss these across several charts, "
                    f"so they are curriculum items — a session on these reaches everyone at once.",
        })

    key_suspects = [c for c in code_rows if c["pattern"] == "One chart" and c["count"] >= 3][:3]
    if key_suspects:
        names = ", ".join(f"{c['code']}" for c in key_suspects)
        notes.append({
            "kind": "key",
            "text": f"Check the answer keys behind {names}. Each is missed by several coders on a "
                    f"single chart, which more often means the key is arguable than that everyone "
                    f"forgot the same code in the same place.",
        })

    coaching = [c for c in code_rows if c["pattern"] == "One coder" and c["count"] >= 3][:3]
    if coaching:
        notes.append({
            "kind": "coaching",
            "text": f"{len(coaching)} code(s) are repeated by one coder each "
                    f"({', '.join(c['code'] for c in coaching)}). These are 1:1 coaching items — "
                    f"teaching them to the room would waste everyone else's time.",
        })

    if len(trend) >= 3:
        # Rate where we have it, count only as a fallback — a team doubling its
        # practice while halving its error rate shows a rising raw count.
        rated = [t for t in trend if t["errors_per_chart"] is not None]
        use_rate = len(rated) >= 3
        series = rated if use_rate else trend
        key = "errors_per_chart" if use_rate else "total"
        unit = "per chart" if use_rate else "errors"
        first, last = series[0][key], series[-1][key]
        if last <= first * 0.7:
            notes.append({"kind": "good",
                          "text": f"Errors are falling — {first} {unit} in {series[0]['month']} to "
                                  f"{last} in {series[-1]['month']}. Whatever changed is working."})
        elif last >= first * 1.3:
            notes.append({"kind": "warn",
                          "text": f"Errors are rising — {first} {unit} in {series[0]['month']} to "
                                  f"{last} in {series[-1]['month']}."
                                  + ("" if use_rate else " This is a raw count, so check whether "
                                     "practice volume simply grew.")})

    # Pareto, not a fixed count. "Codes seen 5+ times" is a threshold that
    # dissolves with volume — at scale almost every code clears it and the line
    # becomes "180 codes account for 97% of errors", which is true, useless and
    # says nothing a trainer can act on. How many codes it takes to reach HALF
    # the errors stays meaningful at any size.
    if len(code_rows) >= 5:
        running, head = 0, 0
        for c in code_rows:                      # already sorted by count desc
            running += c["count"]
            head += 1
            if running >= total / 2:
                break
        head_share = round(head / len(code_rows) * 100)
        if head_share <= 40:
            notes.append({
                "kind": "focus",
                "text": f"{head} of {len(code_rows)} codes ({head_share}%) account for half of "
                        f"every error recorded. The rest is a long tail — work down from the top "
                        f"of the list rather than across it.",
            })
        else:
            notes.append({
                "kind": "info",
                "text": f"Errors are spread evenly — it takes {head} of {len(code_rows)} codes to "
                        f"reach half the total, so there is no short list to fix. Expect broad "
                        f"revision rather than a targeted session.",
            })

    # ── Specialty nuance ─────────────────────────────────────────────────────
    # Without this the commentary reads as if the team has one error profile.
    # It usually does not: a "team-wide gap" that lives entirely inside one
    # specialty is a session for that group, not for everyone.
    if not_represented:
        notes.insert(0, {
            "kind": "warn",
            "text": f"{', '.join(not_represented)} produce no code-level feedback, so they are "
                    f"absent from everything below. Read '0 errors' there as 'not measured here', "
                    f"not as clean work — use the E/M MDM tab or the batch report for those.",
        })

    if specialty:
        notes.insert(0, {
            "kind": "info",
            "text": f"Filtered to {specialty}. Every figure and finding below describes "
                    f"{specialty} only — clear the specialty filter above to compare across the team.",
        })
    elif len(rankable) >= 2:
        hi, lo = rankable[0], rankable[-1]
        gap = None
        if lo["errors_per_chart"] == 0 and hi["errors_per_chart"] > 0:
            # The starkest case, and the one a divide-by-zero guard written as
            # a gate would have skipped: one specialty clean, another not.
            gap = (f"{lo['specialty']} has no recorded errors at all over "
                   f"{lo['charts']} graded charts, while {hi['specialty']} carries "
                   f"{hi['errors_per_chart']} per chart")
        elif lo["errors_per_chart"] > 0 and hi["errors_per_chart"] >= lo["errors_per_chart"] * 2:
            ratio = round(hi["errors_per_chart"] / lo["errors_per_chart"], 1)
            gap = (f"{hi['specialty']} carries {ratio}x the error density of "
                   f"{lo['specialty']} ({hi['errors_per_chart']} vs "
                   f"{lo['errors_per_chart']} per chart)")

        if gap:
            notes.append({
                "kind": "focus",
                "text": f"{gap}. Treat these as separate training problems — a single team "
                        f"session would be aimed at the wrong half of the room.",
            })
        elif hi["errors_per_chart"] > 0:
            notes.append({
                "kind": "info",
                "text": f"Error density is even across specialties ({lo['errors_per_chart']}–"
                        f"{hi['errors_per_chart']} per chart), so the gaps below are team-wide "
                        f"rather than specialty-specific.",
            })

    # A code confined to one specialty is a specialty session, not a team one —
    # and the pattern label alone cannot tell you which.
    if not specialty:
        confined = [c for c in code_rows[:20]
                    if c["count"] >= 4 and len(c["specialties"]) == 1
                    and c["pattern"] in ("Team-wide", "One chart")]
        if confined:
            grouped: dict = {}
            for c in confined[:5]:
                grouped.setdefault(c["specialties"][0], []).append(c["code"])
            bits = "; ".join(f"{sp}: {', '.join(cs)}" for sp, cs in grouped.items())
            notes.append({
                "kind": "curriculum",
                "text": f"Some gaps sit inside a single specialty — {bits}. Those are sessions for "
                        f"that group rather than the whole team.",
            })

    # ── Rank and cap ────────────────────────────────────────────────────────
    # Every rule is independent, so with heavy data most of them fire at once
    # and eleven lines of advice becomes wallpaper — the reader skims it and
    # acts on none of it. Ordered by what a trainer would act on FIRST, and cut
    # to six, with the rest returned so nothing is lost.
    ACTION_ORDER = {
        "info": 0,          # scope statements: what am I even looking at
        "curriculum": 1,    # reaches the most people per session
        "key": 2,           # cheap to check, and invalidates other findings
        "coaching": 3,      # one person at a time
        "warn": 4,
        "focus": 5,
        "good": 6,
    }
    notes.sort(key=lambda n: ACTION_ORDER.get(n["kind"], 9))
    MAX_NOTES = 6
    extra_notes = notes[MAX_NOTES:]
    notes = notes[:MAX_NOTES]

    if not notes:
        notes.append({"kind": "info",
                      "text": "No dominant pattern yet — errors are spread thinly across codes, "
                              "sections and coders. More graded work will sharpen this."})

    return {
        "total_errors": total,
        "graded_charts": len(results),
        "commentary": notes,
        "commentary_more": extra_notes,
        "coverage": coverage,
        "not_represented": not_represented,
        "by_specialty": by_specialty,
        "worst_specialty": worst_specialty,
        "best_specialty": best_specialty,
        "min_charts_to_rank": MIN_CHARTS_TO_RANK,
        # Errors per graded chart — the one figure that says whether things are
        # improving without needing to know how much practice happened.
        "errors_per_chart": round(total / len(results), 2) if results else 0,
        "by_issue_type": [{"type": t, "count": c, "pct": _share(c)}
                          for t, c in by_issue.most_common()],
        "by_section": [{"section": sec, "count": c, "pct": _share(c)}
                       for sec, c in by_section.most_common()],
        "codes": page,
        # Three different totals, all of them needed: every distinct code seen,
        # how many match the current search/pattern, and how many are on this
        # page. Collapsing them is how "Showing 25 of 25" appears over a
        # thousand codes.
        "total_codes": len(code_rows),
        "matching_codes": matching_codes,
        "scattered_codes": scattered_count,
        "scattered_hidden": (not include_scattered) and not asked_for_specifics,
        "returned_codes": len(page),
        "pattern_counts": dict(pattern_counts),
        "trend": trend,
        "scope": scope,
    }


@router.get("/analytics/error-analysis.xlsx")
def error_analysis_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal", section: Optional[str] = None, issue_type: Optional[str] = None,
    code_search: Optional[str] = None, pattern: Optional[str] = None,
    include_scattered: bool = False,
    db: Session = Depends(get_db),
):
    """
    The whole analysis, not the page.

    Same filters as the screen — including the specialty filter, so an export
    taken while looking at SDS describes SDS. The paging is deliberately not
    inherited: 25 codes is a screenful, and the reason to take this to Excel is
    to work through the list.
    """
    from services.excel_service import export_error_analysis
    from services.download_headers import content_disposition

    data = analytics_error_analysis(
        from_date=from_date, to_date=to_date, specialty=specialty, scope=scope,
        section=section, issue_type=issue_type, code_search=code_search,
        pattern=pattern, include_scattered=include_scattered,
        limit=500, offset=0, db=db,
    )

    # The per-code drilldown — who missed it and where. On screen this opens
    # one code at a time, so the export was carrying the verdict without the
    # evidence behind it: a sheet saying "Team-wide" with no way to see which
    # team. Built once here rather than per code, since doing it per code
    # would be one pass over every result for each of two hundred codes.
    wanted = {c["code"] for c in data.get("codes") or []}
    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                                     exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    per_coder: dict = {}
    per_chart: dict = {}
    for r in results:
        for f in r.feedback:
            code = f.ak_code or f.coder_code
            if code not in wanted:
                continue
            if section and f.section.value != section:
                continue
            if issue_type and f.issue_type.value != issue_type:
                continue
            ck = (code, r.emp_id or r.coder_name)
            d = per_coder.setdefault(ck, {"code": code, "coder_name": r.coder_name,
                                          "emp_id": r.emp_id, "count": 0, "charts": set()})
            d["count"] += 1
            d["charts"].add(r.chart.chart_number if r.chart else "")

            hk = (code, r.chart.chart_number if r.chart else "—")
            e = per_chart.setdefault(hk, {"code": code,
                                          "chart_number": r.chart.chart_number if r.chart else "—",
                                          "specialty": r.specialty.value if r.specialty else None,
                                          "category": r.chart.category if r.chart else None,
                                          "count": 0, "coders": set()})
            e["count"] += 1
            e["coders"].add(r.emp_id or r.coder_name)

    data["code_coders"] = sorted(
        [{**{k: v for k, v in d.items() if k != "charts"}, "charts": len(d["charts"])}
         for d in per_coder.values()],
        key=lambda x: (x["code"], -x["count"]))
    data["code_charts"] = sorted(
        [{**{k: v for k, v in e.items() if k != "coders"}, "coders": len(e["coders"])}
         for e in per_chart.values()],
        key=lambda x: (x["code"], -x["count"]))
    name = f"Error_Analysis{'_' + specialty.replace('/', '-') if specialty else ''}.xlsx"
    return StreamingResponse(
        io.BytesIO(export_error_analysis(data)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition(name, "Error_Analysis.xlsx"),
    )


MIN_CHARTS_FOR_CODER_RANK = 5


@router.get("/analytics/error-coders")
def analytics_error_coders(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal", top_n: int = 5,
    db: Session = Depends(get_db),
):
    """
    Coders ranked by ERROR DENSITY, with advice drawn from how their profile
    differs from the team's.

    Ranked on errors per graded chart, not raw errors: a raw count ranks people
    by how much they practised, so the "cleanest" coder is whoever did least.
    Anyone under five graded charts is excluded from both ends rather than
    topping a list on three charts.

    The advice rests on one comparison. A coder failing at what everyone fails
    at needs the session everyone is getting; a coder failing at something the
    team handles fine needs a conversation. Same error count, different action —
    the concentration idea from the code table, turned around to point at a
    person instead of a code.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")

    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                                     exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]
    if not results:
        # Same shape when empty — a caller should not need to check which keys
        # exist before reading them.
        return {"top": [], "bottom": [], "coders": [], "team": None,
                "ranked_coders": 0, "excluded_thin": 0,
                "min_charts": MIN_CHARTS_FOR_CODER_RANK, "scope": scope}

    team_errors = sum(len(r.feedback) for r in results)
    team_charts = len(results)
    team_rate = round(team_errors / team_charts, 2) if team_charts else 0
    team_sections: Counter = Counter()
    team_codes: Counter = Counter()
    for r in results:
        for f in r.feedback:
            team_sections[f.section.value] += 1
            code = f.ak_code or f.coder_code
            if code:
                team_codes[code] += 1

    coders: dict = {}
    for r in results:
        cid = r.emp_id or r.coder_name
        d = coders.setdefault(cid, {
            "coder_id": cid, "coder_name": r.coder_name, "emp_id": r.emp_id,
            "charts": 0, "errors": 0, "sections": Counter(), "issues": Counter(),
            "codes": Counter(), "months": {}, "specialties": set(),
        })
        d["charts"] += 1
        d["errors"] += len(r.feedback)
        if r.specialty:
            d["specialties"].add(r.specialty.value)
        if r.graded_at:
            m = d["months"].setdefault(r.graded_at.strftime("%Y-%m"), {"errors": 0, "charts": 0})
            m["errors"] += len(r.feedback)
            m["charts"] += 1
        for f in r.feedback:
            d["sections"][f.section.value] += 1
            d["issues"][f.issue_type.value] += 1
            code = f.ak_code or f.coder_code
            if code:
                d["codes"][code] += 1

    def _advice(d, rate):
        """What to actually do about this coder, and why."""
        out = []
        # Their worst section, compared with how the team fares there. Only a
        # gap the team does NOT share is a coaching item.
        if d["sections"]:
            sec, n = d["sections"].most_common(1)[0]
            mine = n / d["errors"] if d["errors"] else 0
            theirs = team_sections.get(sec, 0) / team_errors if team_errors else 0
            if mine >= 0.4 and mine >= theirs * 1.5:
                out.append({
                    "kind": "coaching",
                    "text": f"{round(mine * 100)}% of their errors are in {sec}, against "
                            f"{round(theirs * 100)}% for the team. That is their own gap, not the "
                            f"room's — worth a session on {sec} specifically.",
                })
            elif mine >= 0.4:
                out.append({
                    "kind": "curriculum",
                    "text": f"Their errors concentrate in {sec} ({round(mine * 100)}%), and so do "
                            f"the team's ({round(theirs * 100)}%). They are struggling with what "
                            f"everyone struggles with — the team session covers this.",
                })

        # Codes they own: a large share of every team sighting is theirs.
        signature = []
        for code, n in d["codes"].most_common(8):
            total_seen = team_codes.get(code, 0)
            if n >= 2 and total_seen and n / total_seen >= 0.6:
                signature.append((code, n, total_seen))
        if signature:
            bits = ", ".join(f"{c} ({n} of {t} team-wide)" for c, n, t in signature[:3])
            out.append({
                "kind": "coaching",
                "text": f"Codes mostly missed by them alone: {bits}. Nobody else is finding these "
                        f"difficult, so a 1:1 will land better than a session.",
            })

        if rate <= team_rate * 0.5 and d["errors"] > 0:
            out.append({
                "kind": "good",
                "text": f"At {rate} errors per chart against a team average of {team_rate}, they are "
                        f"a candidate for peer teaching rather than coaching.",
            })
        elif d["errors"] == 0:
            out.append({
                "kind": "good",
                "text": f"No recorded errors across {d['charts']} graded charts.",
            })

        if not out:
            out.append({
                "kind": "info",
                "text": f"No distinctive pattern — their errors look like the team's, spread across "
                        f"{len(d['sections'])} sections. Track rather than intervene.",
            })
        return out

    # Rank on the cheap figures FIRST, then build the expensive ones only for
    # the cards that will actually be shown. Advice, per-coder trends and code
    # lists were computed for every coder to render ten of them — at a thousand
    # coders that is a thousand analyses and most of a megabyte on the wire,
    # all of it discarded by the UI.
    def _rate(d):
        return round(d["errors"] / d["charts"], 2) if d["charts"] else 0

    ranked_light = sorted(
        [d for d in coders.values() if d["charts"] >= MIN_CHARTS_FOR_CODER_RANK],
        key=_rate)
    top_n = max(1, min(top_n, 20))
    n = top_n if len(ranked_light) >= top_n * 2 else max(1, len(ranked_light) // 2)
    wanted = ranked_light[:n] + (ranked_light[-n:] if len(ranked_light) > 1 else [])
    wanted_ids = {d["coder_id"] for d in wanted}

    rows = []
    for d in coders.values():
        if d["coder_id"] not in wanted_ids:
            continue
        rate = round(d["errors"] / d["charts"], 2) if d["charts"] else 0
        trend = [{"month": m, "errors": v["errors"], "charts": v["charts"],
                  "errors_per_chart": round(v["errors"] / v["charts"], 2) if v["charts"] else None}
                 for m, v in sorted(d["months"].items())]
        # Direction over the coder's own history, so "improving" means improving
        # for them rather than relative to anyone else.
        direction = None
        if len(trend) >= 2:
            first, last = trend[0]["errors_per_chart"], trend[-1]["errors_per_chart"]
            if first is not None and last is not None:
                if last <= first * 0.7:
                    direction = "improving"
                elif last >= first * 1.3:
                    direction = "worsening"
                else:
                    direction = "steady"
        rows.append({
            "coder_id": d["coder_id"], "coder_name": d["coder_name"], "emp_id": d["emp_id"],
            "charts": d["charts"], "errors": d["errors"], "errors_per_chart": rate,
            "vs_team": round(rate - team_rate, 2),
            "specialties": sorted(d["specialties"]),
            "top_sections": [{"section": s, "count": n} for s, n in d["sections"].most_common(3)],
            "top_issues": [{"type": t, "count": n} for t, n in d["issues"].most_common(3)],
            "top_codes": [{"code": c, "count": n} for c, n in d["codes"].most_common(5)],
            "trend": trend,
            "direction": direction,
            "rankable": d["charts"] >= MIN_CHARTS_FOR_CODER_RANK,
            "advice": _advice(d, rate),
        })

    # Below twice the list size the two ends would overlap, and a coder shown
    # as both best and worst is worse than a short list. n was chosen above,
    # where the ranking happened.
    by_rate = sorted(rows, key=lambda r: r["errors_per_chart"])

    return {
        # "Top" is fewest errors per chart. Deliberately not "highest score" —
        # that is the Coder Profile tab's question, and this one is about
        # errors.
        "top": by_rate[:n],
        # One coder is a record, not a ranking — there is no contrast to draw.
        "bottom": list(reversed(by_rate[-n:])) if len(by_rate) > 1 else [],
        # Everyone rankable, so a caller wanting one coder need not guess which
        # end they landed on.
        # The enriched rows actually returned — the two ends, not everyone.
        # Ranking happens over every coder; only these carry advice and trends.
        "coders": by_rate,
        "team": {"errors_per_chart": team_rate, "charts": team_charts, "errors": team_errors},
        "ranked_coders": len(ranked_light),
        "excluded_thin": len(coders) - len(ranked_light),
        "min_charts": MIN_CHARTS_FOR_CODER_RANK,
        "scope": scope,
    }


@router.get("/analytics/error-detail")
def analytics_error_detail(
    code: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """Who missed this code, on which charts — the drilldown behind a row."""
    scope = (scope or "formal").lower()
    results = _with_details(_gr_base(db, from_date, to_date, specialty,
                                     exclude_direct=(scope == "formal"))).join(Chart).all()
    if scope == "direct":
        results = [r for r in results if r.batch and r.batch.is_direct_assignment]

    by_coder: dict = {}
    by_chart: dict = {}
    for r in results:
        for f in r.feedback:
            if (f.ak_code or f.coder_code) != code:
                continue
            cid = r.emp_id or r.coder_name
            c = by_coder.setdefault(cid, {"coder_name": r.coder_name, "emp_id": r.emp_id,
                                          "count": 0, "charts": set()})
            c["count"] += 1
            c["charts"].add(r.chart.chart_number if r.chart else "")
            ch = r.chart.chart_number if r.chart else "—"
            d = by_chart.setdefault(ch, {"chart_number": ch, "count": 0, "coders": set(),
                                         "specialty": r.specialty.value if r.specialty else None,
                                         "category": r.chart.category if r.chart else None})
            d["count"] += 1
            d["coders"].add(cid)

    return {
        "code": code,
        "coders": sorted([{"coder_name": v["coder_name"], "emp_id": v["emp_id"],
                           "count": v["count"], "charts": len(v["charts"])}
                          for v in by_coder.values()], key=lambda x: -x["count"]),
        "charts": sorted([{"chart_number": v["chart_number"], "count": v["count"],
                           "coders": len(v["coders"]), "specialty": v["specialty"],
                           "category": v["category"]}
                          for v in by_chart.values()], key=lambda x: -x["count"]),
    }


@router.get("/analytics/coder-matrix")
def analytics_coder_matrix(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal", group_by: str = "specialty",
    limit: int = 25, offset: int = 0, sort: str = "recent",
    search: Optional[str] = None, below_target_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    Coders down, one KIND of thing across.

    That is the constraint the column axis has to satisfy, and appending a
    "Direct work" column to a row of batches broke it: a batch is an EVENT
    (one specialty, one time window, one closed set) while direct work is a
    BUCKET (cumulative, possibly several specialties). Side by side they look
    comparable and are not, and no column label fixes that.

    So the axis is chosen rather than mixed:

      group_by=specialty  DEFAULT. Columns are specialties — buckets. Every
                          column is the same kind of thing, cells are directly
                          comparable, and direct assignments belong naturally
                          because a specialty bucket does not care which route
                          the work arrived by. It is also the only axis with a
                          natural ceiling: ten specialties, ever.

      group_by=batch      Columns are closed formal batches — events. Useful
                          for "how did the last few waves go", and readable
                          for about that long: batch columns grow without
                          limit, so the client windows them to the latest N.
                          Direct work has no comparable column here, so it is
                          excluded and the amount excluded is reported.
    """
    scope = (scope or "formal").lower()
    if scope not in ("formal", "direct", "all"):
        raise HTTPException(status_code=400, detail="scope must be formal, direct or all")
    group_by = (group_by or "specialty").lower()
    if group_by not in ("batch", "specialty"):
        raise HTTPException(status_code=400, detail="group_by must be batch or specialty")

    thresholds = _pass_thresholds(db)
    spec_filter = next((sp for sp in Specialty if sp.value == specialty), None) if specialty else None

    if group_by == "specialty":
        # Buckets: any graded work, scoped. A specialty column is not a
        # completed set, so "closed batches only" would just discard current
        # information for no gain in comparability.
        q = _gr_base(db, from_date, to_date, specialty,
                     exclude_direct=(scope == "formal"))
        if scope == "direct":
            q = q.join(Batch, GradingResult.batch_id == Batch.id).filter(
                Batch.is_direct_assignment == True)
        results = q.all()
        excluded_direct = 0
        seen = []
        for r in results:
            sp = r.specialty.value if r.specialty else "-"
            if sp not in seen:
                seen.append(sp)
        columns = [{"id": sp, "name": sp, "specialty": sp,
                    "pass_threshold": thresholds.get(sp),
                    "is_direct": False, "closed_at": None}
                   for sp in sorted(seen)]

        def col_of(r):
            return r.specialty.value if r.specialty else "-"
    else:
        # Events: closed formal batches only, so each column is finished and
        # comparable with the ones beside it.
        b_q = db.query(Batch).filter(Batch.status == BatchStatus.CLOSED,
                                     Batch.is_direct_assignment == False)
        if from_date:
            b_q = b_q.filter(Batch.closed_at >= from_date)
        if to_date:
            b_q = b_q.filter(Batch.closed_at <= to_date + "T23:59:59")
        if spec_filter:
            b_q = b_q.filter(Batch.specialty == spec_filter)
        batches = b_q.order_by(Batch.created_at).all()
        batch_ids = [b.id for b in batches]
        results = ([] if not batch_ids else
                   db.query(GradingResult)
                     .filter(GradingResult.batch_id.in_(batch_ids),
                             GradingResult.total_score.isnot(None))
                     .all())
        # Closed is not the same as graded. A batch can be closed with nothing
        # graded in it, and that produced a column of dashes taking a column's
        # width to say nothing — the more of them, the further the columns that
        # DO carry results get pushed off screen.
        graded_ids = {r.batch_id for r in results}
        rostered = dict(db.query(BatchCoder.batch_id, func.count(BatchCoder.id))
                          .filter(BatchCoder.batch_id.in_(batch_ids))
                          .group_by(BatchCoder.batch_id).all()) if batch_ids else {}
        graded_coders = {}
        for r in results:
            graded_coders.setdefault(r.batch_id, set()).add(r.emp_id or r.coder_name)

        columns = [{"id": b.id, "name": b.name, "specialty": b.specialty.value,
                    "pass_threshold": thresholds.get(b.specialty.value),
                    "is_direct": False,
                    # Coverage, so a half-graded column is not read as a batch
                    # where most coders scored nothing. A blank cell means
                    # "not graded", which is not the same as "did badly".
                    "graded_coders": len(graded_coders.get(b.id, ())),
                    "rostered_coders": rostered.get(b.id, 0),
                    "closed_at": b.closed_at.isoformat() if b.closed_at else None}
                   for b in batches if b.id in graded_ids]
        skipped_ungraded = len(batches) - len(columns)

        def col_of(r):
            return r.batch_id

        # Reported, not rendered: direct work has no comparable column here.
        d_q = (db.query(GradingResult)
               .join(Batch, GradingResult.batch_id == Batch.id)
               .filter(Batch.is_direct_assignment == True,
                       GradingResult.total_score.isnot(None)))
        if spec_filter:
            d_q = d_q.filter(GradingResult.specialty == spec_filter)
        excluded_direct = d_q.count()

    def _cid(r):
        return r.emp_id or r.coder_name

    cell_map: dict = {}
    display_name: dict = {}
    emp_of: dict = {}
    for r in results:
        cid = _cid(r)
        display_name.setdefault(cid, r.coder_name)
        if r.emp_id:
            emp_of[cid] = r.emp_id
        key = (cid, col_of(r))
        if key not in cell_map:
            cell_map[key] = {"scores": [], "passed": 0, "total": 0}
        cell_map[key]["scores"].append(r.total_score)
        cell_map[key]["total"] += 1
        if r.pass_fail and r.pass_fail.value == "PASS":
            cell_map[key]["passed"] += 1

    # ── Which coders come back ───────────────────────────────────────────────
    # The grid used to receive EVERY coder and page them in the browser, which
    # is not paging — a thousand rows still crossed the wire and were held in
    # memory before 25 of them were drawn.
    #
    # Default order is most recent activity, not alphabetical: the first
    # screenful should be the people who have been working, and alphabetical
    # makes the first 25 an accident of surnames.
    last_seen: dict = {}
    for r in results:
        cid = _cid(r)
        if r.graded_at and (cid not in last_seen or r.graded_at > last_seen[cid]):
            last_seen[cid] = r.graded_at

    # Search and the below-target filter decide WHICH coders qualify, so they
    # have to run before paging — filtering a page would only ever search the
    # 25 rows already on screen.
    ordered = list(display_name)
    if search and search.strip():
        term = search.strip().lower()
        ordered = [cid for cid in ordered
                   if term in display_name[cid].lower()
                   or term in str(emp_of.get(cid, "")).lower()]
    if below_target_only:
        col_mark = {c["id"]: c["pass_threshold"] for c in columns}
        def _below(cid):
            for col in columns:
                d = cell_map.get((cid, col["id"]))
                pt = col_mark.get(col["id"])
                if d and pt is not None and (sum(d["scores"]) / len(d["scores"])) < pt:
                    return True
            return False
        ordered = [cid for cid in ordered if _below(cid)]
    if sort == "name":
        ordered.sort(key=lambda cid: display_name[cid].lower())
    else:
        # Anyone with no graded_at sorts last rather than first.
        ordered.sort(key=lambda cid: (last_seen.get(cid) is not None, last_seen.get(cid)),
                     reverse=True)

    total_coders = len(ordered)
    limit = max(1, min(limit, 200))          # a page, not an accidental dump
    all_coders = ordered[offset:offset + limit]
    shown = set(all_coders)

    coder_emp_ids: dict = {cid: emp_of[cid] for cid in all_coders if cid in emp_of}
    missing = [cid for cid in all_coders if cid not in coder_emp_ids]
    if missing:
        names = [display_name[c] for c in missing]
        for name, emp_id in (db.query(BatchCoder.coder_name, BatchCoder.emp_id)
                              .filter(BatchCoder.coder_name.in_(names))
                              .order_by(BatchCoder.id.desc())
                              .all()):
            for cid in missing:
                if display_name[cid] == name and cid not in coder_emp_ids and emp_id:
                    coder_emp_ids[cid] = emp_id

    cells = []
    for coder in all_coders:
        for col in columns:
            data = cell_map.get((coder, col["id"]))
            if data:
                cells.append({
                    "coder_id": coder,
                    "coder_name": display_name[coder],
                    "batch_id": col["id"],
                    "avg_score": round(sum(data["scores"]) / len(data["scores"]), 1),
                    "pass_rate": round(data["passed"] / data["total"] * 100, 1),
                    "charts_passed": data["passed"],
                    "chart_count": data["total"],
                    "score_sum": sum(data["scores"]),
                })

    if group_by == "specialty":
        note = ("Columns are specialties, so every column is the same kind of thing. "
                + {"formal": "Batch work only.",
                   "direct": "Direct assignments only.",
                   "all": "Batch work and direct assignments together."}[scope])
    else:
        note = "Columns are closed formal batches that have graded results."
        if skipped_ungraded:
            note += f" {skipped_ungraded} closed batch(es) with nothing graded are not shown."
        if excluded_direct:
            note += (f" {excluded_direct} graded direct-assignment charts have no comparable column here; "
                     "group by specialty to include them.")

    return {
        "batches": columns,
        "group_by": group_by,
        "coders": all_coders,
        "total_coders": total_coders,
        "returned_coders": len(all_coders),
        "sort": sort,
        "coder_last_activity": {cid: last_seen[cid].isoformat()
                                for cid in all_coders if cid in last_seen},
        "coder_names": {cid: display_name[cid] for cid in all_coders},
        "coder_emp_ids": coder_emp_ids,
        "cells": cells,
        "scope": scope,
        "excluded_direct_results": excluded_direct,
        "scope_note": note,
    }

@router.get("/analytics/chart-signals.xlsx")
def chart_signals_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """
    Every chart with its signal — the curriculum-planning sheet.

    A list rather than a grid, because that is what it is: one row per chart.
    The screen pages these 24 at a time; building a practice pack means having
    all of them in front of you at once.
    """
    from services.excel_service import export_chart_signals
    from services.download_headers import content_disposition

    rows = analytics_chart_teaching_value(from_date=from_date, to_date=to_date,
                                          specialty=specialty, scope=scope, db=db)
    payload = export_chart_signals(rows)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Chart_Signals.xlsx", "Chart_Signals.xlsx"),
    )


@router.get("/analytics/coder-matrix.xlsx")
def coder_matrix_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal", group_by: str = "specialty",
    search: Optional[str] = None, below_target_only: bool = False, sort: str = "recent",
    db: Session = Depends(get_db),
):
    """
    The whole grid, not the page.

    The screen shows about fourteen columns and a page of rows because that is
    what stays readable; this exists for the other question — the full picture,
    every coder against every column. So it takes the same filters and the same
    axis, and deliberately ignores the paging.
    """
    from services.excel_service import export_grid
    from services.download_headers import content_disposition

    data = analytics_coder_matrix(
        from_date=from_date, to_date=to_date, specialty=specialty,
        scope=scope, group_by=group_by, limit=200, offset=0,
        search=search, below_target_only=below_target_only, sort=sort, db=db,
    )

    by_coder: dict = {}
    for c in data["cells"]:
        by_coder.setdefault(c["coder_id"], {})[c["batch_id"]] = c

    rows = []
    for cid in data["coders"]:
        cells = by_coder.get(cid, {})
        charts = sum(c["chart_count"] for c in cells.values())
        score_sum = sum(c["score_sum"] for c in cells.values())
        rows.append({
            "label": data["coder_names"].get(cid, cid),
            "sub": data["coder_emp_ids"].get(cid),
            "values": {bid: c["avg_score"] for bid, c in cells.items()},
            "overall": round(score_sum / charts, 1) if charts else None,
        })

    columns = [{"key": c["id"], "label": c["name"],
                "sub": (f"pass {c['pass_threshold']}%" if c.get("pass_threshold") else None)}
               for c in data["batches"]]

    title = "By Specialty" if group_by == "specialty" else "By Batch"
    payload = export_grid(f"Coder Matrix {title}", "Coder", columns, rows)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition(f"Coder_Matrix_{title.replace(' ', '_')}.xlsx",
                                    "Coder_Matrix.xlsx"),
    )


@router.get("/analytics/topic-heatmap.xlsx")
def topic_heatmap_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None, specialty: Optional[str] = None,
    scope: str = "formal",
    db: Session = Depends(get_db),
):
    """Coder x Topic, the whole grid — the on-screen heatmap caps its columns."""
    from services.excel_service import export_grid
    from services.download_headers import content_disposition

    data = analytics_by_category(from_date=from_date, to_date=to_date,
                                 specialty=specialty, scope=scope, db=db)
    topics = [t["category"] for t in data["team"]]
    columns = [{"key": t["category"], "label": t["category"],
                "sub": (f"pass {t['pass_threshold']}%" if t.get("pass_threshold") else "mixed")}
               for t in data["team"]]

    by_coder: dict = {}
    for r in data["coder_category"]:
        cid = r.get("emp_id") or r["coder_name"]
        by_coder.setdefault(cid, {"name": r["coder_name"], "emp": r.get("emp_id"), "v": {}})
        by_coder[cid]["v"][r["category"]] = r

    rows = []
    for cid, d in sorted(by_coder.items(), key=lambda kv: kv[1]["name"].lower()):
        charts = sum(x["attempt_count"] for x in d["v"].values())
        total = sum(x["avg_score"] * x["attempt_count"] for x in d["v"].values())
        rows.append({
            "label": d["name"], "sub": d["emp"],
            "values": {t: d["v"][t]["avg_score"] for t in topics if t in d["v"]},
            "overall": round(total / charts, 1) if charts else None,
        })

    payload = export_grid("Coder x Topic", "Coder", columns, rows)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Coder_Topic_Matrix.xlsx", "Coder_Topic_Matrix.xlsx"),
    )


@router.get("/analytics/chart-detail/{chart_number:path}")
def chart_detail(chart_number: str, db: Session = Depends(get_db)):
    # This walks r.feedback and r.batch on every row. Built its own query, so
    # it never picked up the eager loading added to _gr_base — one query per
    # result, on the endpoint that fires every time a chart row is expanded.
    results = _with_details(
        db.query(GradingResult)
          .join(Chart, GradingResult.chart_id == Chart.id)
          .join(Batch, GradingResult.batch_id == Batch.id)
          .filter(Chart.chart_number == chart_number,
                  GradingResult.total_score.isnot(None),
                  Batch.is_direct_assignment == False)
    ).all()
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
        "total_coders": len(coders),
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


@router.get("/analytics/coder-performance.xlsx")
def coder_performance_export(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    specialty: Optional[str] = None, coder_name: Optional[str] = None,
    emp_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Coder performance: one row per graded chart, every dimension a column.

    The PDF answers "how is this coder doing"; this answers "let me slice it
    myself" — across coders, batches, categories and time, which nothing else
    exposes.

    Direct assignments are INCLUDED, because this is a coder-level view, but
    carry an "Assignment Type" column so the trainer can exclude them in the
    spreadsheet rather than having that decided for them.
    """
    from services.excel_service import export_coder_performance

    q = (db.query(GradingResult)
         .join(Batch, GradingResult.batch_id == Batch.id)
         .join(Chart, GradingResult.chart_id == Chart.id)
         .filter(GradingResult.total_score.isnot(None)))
    if from_date:
        q = q.filter(GradingResult.graded_at >= from_date)
    if to_date:
        q = q.filter(GradingResult.graded_at <= to_date + "T23:59:59")
    if specialty:
        spec = next((s for s in Specialty if s.value == specialty), None)
        if spec:
            q = q.filter(GradingResult.specialty == spec)
    if coder_name or emp_id:
        q = _coder_filter(q, coder_name, emp_id)

    results = q.order_by(GradingResult.coder_name, GradingResult.graded_at).all()

    def _d(dt):
        return dt.strftime("%Y-%m-%d") if dt else None

    rows, feedback_rows = [], []
    for r in results:
        base = {
            "coder_name": r.coder_name,
            "emp_id": r.emp_id or "",
            "batch_name": r.batch.name if r.batch else "",
            "assignment_type": ("Direct" if (r.batch and r.batch.is_direct_assignment)
                                else "Batch"),
            "batch_date": _d(r.batch.created_at) if r.batch else None,
            "chart_number": r.chart.chart_number if r.chart else "",
            "specialty": r.specialty.value if r.specialty else "",
            "category": r.chart.category if r.chart else "",
            "difficulty": (r.chart.difficulty.value
                           if r.chart and r.chart.difficulty else ""),
            "graded_on": _d(r.graded_at),
        }
        rows.append({
            **base,
            "total_score": r.total_score,
            "pass_fail": r.pass_fail.value if r.pass_fail else "",
            "pdx_score": r.pdx_score, "sdx_score": r.sdx_score,
            "pcs_score": r.pcs_score, "cpt_score": r.cpt_score,
            "drg_score": r.drg_score,
            "dpo_dx": r.dpo_dx_accuracy, "dpo_poa": r.dpo_poa_accuracy,
            "dpo_proc": r.dpo_proc_accuracy, "dpo_overall": r.dpo_overall_accuracy,
        })
        for f in r.feedback:
            feedback_rows.append({
                **{k: base[k] for k in ("coder_name", "emp_id", "batch_name",
                                        "chart_number", "specialty", "category")},
                "section": f.section.value if f.section else "",
                "issue_type": f.issue_type.value if f.issue_type else "",
                "ak_code": f.ak_code or "", "coder_code": f.coder_code or "",
                "detail": f.detail or "",
            })

    data = export_coder_performance(rows, feedback_rows)
    bits = ["CoderPerformance"]
    if coder_name:
        bits.append(coder_name.replace(" ", "_"))
    if from_date or to_date:
        bits.append(f"{from_date or 'start'}_to_{to_date or 'today'}")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("_".join(bits) + ".xlsx", "Coder_Performance.xlsx"),
    )
