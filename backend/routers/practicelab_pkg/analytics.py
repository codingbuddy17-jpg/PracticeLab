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
    db: Session = Depends(get_db),
):
    results = _with_details(_gr_base(db, from_date, to_date, specialty, exclude_direct=True)).join(Chart).all()

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
