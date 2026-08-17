"""
Auditor analytics.

Not a copy of the coder analytics — the questions are different. Those answer
"which codes do people get wrong"; these answer whether an auditor can find an
error at all, whether they can leave a correct claim alone, and which KINDS of
error slip past a cohort.

Two bases run through everything here, and both are named in the payload
because this codebase has already paid once for a rate that quietly meant
something other than what it said:

  * audit accuracy is AVERAGED over chart scores — one chart, one unit of work
  * component accuracy is POOLED — total found over total planted, so a chart
    with six plantings counts six times as much as a chart with one

NA is a real value throughout. A cohort that has never met a spurious code has
no Delete accuracy, and reporting 0% would say something false about them.
"""

from datetime import datetime, timedelta
from typing import Optional

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import aliased as sa_aliased
from sqlalchemy.orm import Session

from database import get_db
from models import AuditBatch, AuditResult, Chart
from services.code_enrichment import (axis_themes, ccmcc_label, chapter_label,
                                      enrich_codes, lookup)
from services.icd_chapters import chapter_for
from services.audit_scoring import blended_score
from .shared import scoring_config

router = APIRouter()


def _rate(found: int, planted: int) -> Optional[float]:
    """None, not zero, when there was nothing to find."""
    return round(found / planted * 100, 2) if planted else None



def _auditor_key_expr():
    """Stable identity: employee id when present, otherwise the name."""
    return func.coalesce(func.nullif(AuditResult.emp_id, ""), AuditResult.auditor_name)


def _split_auditor_key(auditor: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not auditor:
        return None, None
    if "||" in auditor:
        emp_id, name = auditor.split("||", 1)
        return emp_id or None, name or None
    return None, auditor


def _base_query(db: Session, batch_id: Optional[int], specialty: Optional[str],
                auditor: Optional[str], from_date: Optional[str] = None,
                to_date: Optional[str] = None):
    q = db.query(AuditResult)
    if batch_id:
        q = q.filter(AuditResult.batch_id == batch_id)
    if specialty:
        q = q.filter(AuditResult.specialty == specialty)
    if auditor:
        emp_id, name = _split_auditor_key(auditor)
        if emp_id:
            q = q.filter(AuditResult.emp_id == emp_id)
        else:
            q = q.filter(AuditResult.auditor_name == name)
    if from_date:
        q = q.filter(AuditResult.scored_at >= from_date)
    if to_date:
        q = q.filter(AuditResult.scored_at <= to_date + "T23:59:59")
    return q


R = AuditResult

# Errors introduced that were not found, summed. Used by chart_signals both for
# the per-row figure and for the totals, so the two can never disagree.
_MISSED_EXPR = func.sum(
    (func.coalesce(R.add_planted, 0) - func.coalesce(R.add_found, 0))
    + (func.coalesce(R.revise_planted, 0) - func.coalesce(R.revise_found, 0))
    + (func.coalesce(R.delete_planted, 0) - func.coalesce(R.delete_found, 0)))

# Everything the roll-up needs, as one aggregate row rather than a table load.
_AGGREGATES = [
    func.count(R.id),
    func.avg(R.audit_accuracy),
    func.sum(func.coalesce(R.add_planted, 0)), func.sum(func.coalesce(R.add_found, 0)),
    func.sum(func.coalesce(R.revise_planted, 0)), func.sum(func.coalesce(R.revise_found, 0)),
    func.sum(func.coalesce(R.delete_planted, 0)), func.sum(func.coalesce(R.delete_found, 0)),
    func.sum(func.coalesce(R.drg_impacting_planted, 0)),
    func.sum(func.coalesce(R.drg_impacting_found, 0)),
    func.sum(func.coalesce(R.over_calls, 0)),
    func.sum(func.coalesce(R.detected_not_corrected, 0)),
]


def _blend_expr(cfg):
    """
    The Audit Score as a SQL expression, so a "weakest first" list can be
    ordered by the figure it actually displays.

    Both halves are expressible from stored columns: detection is the average
    of the per-chart scores, review is pooled correct over total. When one half
    is missing the other stands in for it, which is the same renormalisation
    blended_score() does in Python — a cohort with nothing reviewed sorts on
    its detection rather than falling to the bottom on a NULL.

    Ordering by detection while showing the blend is not a cosmetic mismatch:
    these lists are capped, so it decides WHICH rows a trainer ever sees. An
    over-caller with fair detection and poor review would never surface.
    """
    detection = func.avg(R.audit_accuracy)
    review = (func.sum(func.coalesce(R.review_correct, 0)) * 100.0
              / func.nullif(func.sum(func.coalesce(R.review_total, 0)), 0))
    wd, wr = cfg.detection_weight or 0, cfg.review_weight or 0
    if wd + wr <= 0:
        return detection
    return (func.coalesce(detection, review) * wd
            + func.coalesce(review, detection) * wr) / (wd + wr)


def _review_rollup(base) -> dict:
    """
    Review scoring, pooled over everything in scope.

    The chart total comes from plain integer columns so the database does the
    sum. The per-section and per-attribute breakdowns come from the stored JSON
    in one pass — the same single read the old per-section detection rates
    needed, except those had to scan every row's feedback array to find one
    section at a time.

    Pooled, never averaged: a twenty-line chart carries more weight than a
    five-line one, which is the point of counting lines at all.
    """
    total, correct = base.with_entities(
        func.coalesce(func.sum(R.review_total), 0),
        func.coalesce(func.sum(R.review_correct), 0)).one()
    total, correct = int(total or 0), int(correct or 0)

    sections: dict = {}
    attributes: dict = {}
    for secs, attrs in base.with_entities(R.review_sections, R.review_attributes).all():
        for store, blob in ((sections, secs), (attributes, attrs)):
            for name, body in (blob or {}).items():
                acc = store.setdefault(name, {"total": 0, "correct": 0})
                acc["total"] += (body or {}).get("total", 0)
                acc["correct"] += (body or {}).get("correct", 0)

    def _finish(store):
        return {name: {**acc, "score": round(acc["correct"] / acc["total"] * 100, 2)}
                for name, acc in store.items() if acc["total"]}

    return {
        "review_total": total,
        "review_correct": correct,
        "review_score": round(correct / total * 100, 2) if total else None,
        "sections": _finish(sections),
        "attributes": _finish(attributes),
    }



def _score_trend(base, cfg, weeks: int = 12) -> list:
    """
    Audit Score over time, bucketed by WEEK.

    It was drawn from the by-batch list first — batch id order, which is
    creation sequence rather than time and ignored the date filter entirely.
    Then by day, which is honest but sparse: audit sessions do not run daily,
    so the line was a scatter of isolated points with gaps between them.

    Weeks match how the work is actually scheduled, and give each point enough
    charts behind it to mean something.

    The rollup is done here rather than in SQL because week-truncation is not
    portable — Postgres has date_trunc('week'), SQLite does not. The database
    still does the per-row aggregation; this merges at most a few dozen day
    buckets, which is not the "count in Python" trap. Each day contributes its
    SUM and COUNT rather than its average, so a week of one chart cannot
    outweigh a week of thirty.

    Weeks with nothing scored are absent, not zero — an empty week is a week
    nobody worked, and drawing it as a collapse would be a lie.
    """
    day = func.date(R.scored_at)
    rows = (base.with_entities(day.label("day"),
                               func.sum(R.audit_accuracy),
                               func.count(R.id),
                               func.sum(func.coalesce(R.review_correct, 0)),
                               func.sum(func.coalesce(R.review_total, 0)))
            .group_by(day).order_by(day.asc()).all())

    buckets: dict = {}
    for d, det_sum, n, r_correct, r_total in rows:
        try:
            date = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        monday = date - timedelta(days=date.weekday())
        acc = buckets.setdefault(monday, {"det": 0.0, "charts": 0,
                                          "correct": 0, "total": 0})
        acc["det"] += float(det_sum or 0)
        acc["charts"] += int(n or 0)
        acc["correct"] += int(r_correct or 0)
        acc["total"] += int(r_total or 0)

    out = []
    for monday in sorted(buckets)[-weeks:]:
        acc = buckets[monday]
        detection = round(acc["det"] / acc["charts"], 2) if acc["charts"] else None
        review = (round(acc["correct"] / acc["total"] * 100, 2)
                  if acc["total"] else None)
        out.append({
            "date": monday.isoformat(),
            "week_of": monday.isoformat(),
            # The blend the verdict uses, so the line and the headline cannot
            # tell different stories.
            "score": blended_score(detection, review, cfg),
            "detection": detection,
            "review": review,
            "charts": acc["charts"],
        })
    return out


def _session_pass_rate(base, cfg) -> dict:
    """
    Pass rate is a session-level score count, not a chart-level average.

    The Audit Score is recomputed from the stored detection and review pieces
    for each submitted audit session. It deliberately counts scored thin
    sessions too: the overview card answers "how many submitted attempts are
    currently passing?", while pass_fail/verdict_withheld_reason separately
    explains whether the formal verdict gate has enough review volume.
    """
    rows = (base.with_entities(
        R.session_id,
        func.avg(R.audit_accuracy),
        func.sum(func.coalesce(R.review_correct, 0)),
        func.sum(func.coalesce(R.review_total, 0)),
    ).group_by(R.session_id).all())
    passed = eligible = 0
    for _session_id, detection_avg, review_correct, review_total in rows:
        review_total = int(review_total or 0)
        detection = round(float(detection_avg), 2) if detection_avg is not None else None
        review = round(int(review_correct or 0) / review_total * 100, 2) if review_total else None
        score = blended_score(detection, review, cfg)
        if score is None:
            continue
        eligible += 1
        if score >= cfg.pass_threshold:
            passed += 1
    return {
        "pass_count": passed,
        "verdict_count": eligible,
        "pass_rate": _rate(passed, eligible),
    }


def _roll_sql(db: Session, base, cfg) -> dict:
    """
    The figures every level of this report shares, computed in the database.

    This used to load every AuditResult row and sum them in Python — a full
    table scan on each of four endpoints, every time the Analytics tab was
    opened. The numbers are identical; the work moves to where the rows are.
    """
    agg = base.with_entities(*_AGGREGATES).one()
    (charts, avg_acc, add_p, add_f, rev_p, rev_f, del_p, del_f,
     drg_p, drg_f, over_calls, dnc) = agg
    if not charts:
        return {"charts": 0, "audit_accuracy": None}

    clean_n, clean_avg = base.filter(R.is_clean == True).with_entities(   # noqa: E712
        func.count(R.id), func.avg(R.audit_accuracy)).one()
    opp_n, opp_avg = base.filter(R.is_clean == False).with_entities(      # noqa: E712
        func.count(R.id), func.avg(R.audit_accuracy)).one()
    q_total, q_right = base.filter(R.query_correct.isnot(None)).with_entities(
        func.count(R.id),
        func.sum(case((R.query_correct == True, 1), else_=0))).one()  # noqa: E712
    charts_with_over = base.filter(R.over_calls > 0).with_entities(
        func.count(R.id)).scalar() or 0

    components = {
        "add": {"planted": int(add_p or 0), "found": int(add_f or 0),
                "accuracy": _rate(int(add_f or 0), int(add_p or 0))},
        "revise": {"planted": int(rev_p or 0), "found": int(rev_f or 0),
                   "accuracy": _rate(int(rev_f or 0), int(rev_p or 0))},
        "delete": {"planted": int(del_p or 0), "found": int(del_f or 0),
                   "accuracy": _rate(int(del_f or 0), int(del_p or 0))},
    }
    drg_planted, drg_found = int(drg_p or 0), int(drg_f or 0)
    opportunities = components["add"]["planted"] + components["revise"]["planted"] \
        + components["delete"]["planted"]
    audit_accuracy = round(float(avg_acc), 2) if avg_acc is not None else None

    # The verdict is decided on the blended Audit Score. Detection alone is
    # quantised by planting count, while review counts the code lines judged in
    # the chart; the blend keeps both skills visible without overcrowding the
    # overview.
    review = _review_rollup(base)
    audit_score = blended_score(audit_accuracy, review["review_score"], cfg)
    session_verdicts = _session_pass_rate(base, cfg)
    verdict = None
    withheld = None
    if review["review_total"] >= cfg.min_review_opportunities:
        verdict = "PASS" if (audit_score or 0) >= cfg.pass_threshold else "FAIL"
    else:
        withheld = (
            f"{review['review_total']}/{cfg.min_review_opportunities} review lines for verdict"
            if review["review_total"] else
            "restraint measure only — nothing reviewed yet")

    return {
        "charts": int(charts),
        "audit_accuracy": audit_accuracy,
        "audit_accuracy_basis": "average of chart scores",
        # Split because the headline otherwise blends two different skills and
        # hides which one is weak: finding errors, and leaving correct claims
        # alone. A passive auditor scores 100 on one and 0 on the other.
        "clean_charts": int(clean_n or 0),
        "opportunity_charts": int(opp_n or 0),
        "clean_accuracy": round(float(clean_avg), 2) if clean_avg is not None else None,
        "opportunity_accuracy": round(float(opp_avg), 2) if opp_avg is not None else None,
        "add": components["add"],
        "revise": components["revise"],
        "delete": components["delete"],
        "component_basis": "pooled findings over errors introduced",
        # Its own number, never blended into the headline as a weight.
        "drg_planted": drg_planted,
        "drg_found": drg_found,
        "drg_accuracy": _rate(drg_found, drg_planted),
        "query_charts": int(q_total or 0),
        "query_correct": int(q_right or 0),
        "query_accuracy": _rate(int(q_right or 0), int(q_total or 0)),
        "over_calls": int(over_calls or 0),
        "charts_with_over_calls": int(charts_with_over),
        # Reported, never scored. "Found 4 of 4, corrected 2" and "found 2 of 4"
        # both come out at 50% and are different coaching conversations.
        "detected_not_corrected": int(dnc or 0),
        "opportunities": opportunities,
        # Review scoring — the second scheme. Detection above answers "did you
        # find what was wrong"; this answers "of every code line you had to
        # judge, how many did you judge correctly". Both are reported because
        # blending them hides whichever is weak.
        "review_score": review["review_score"],
        "review_total": review["review_total"],
        "review_correct": review["review_correct"],
        "review_basis": "pooled code lines judged correctly",
        # The blended figure the verdict is decided on, with the weights that
        # produced it so a reader can see how it was made.
        "audit_score": audit_score,
        "detection_weight": cfg.detection_weight,
        "review_weight": cfg.review_weight,
        "sections": review["sections"],
        "attributes": review["attributes"],
        # The verdict rule, shipped beside the figure it judges.
        "opportunities_needed": cfg.min_review_opportunities,
        "pass_fail": verdict,
        "verdict_withheld_reason": withheld,
        **session_verdicts,
    }


@router.get("/analytics/overview")
def overview(batch_id: Optional[int] = None, specialty: Optional[str] = None,
             auditor: Optional[str] = None,
             from_date: Optional[str] = None, to_date: Optional[str] = None,
             db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    body = _roll_sql(db, base, cfg)
    body["trend"] = _score_trend(base, cfg)
    body["auditors"] = base.with_entities(
        func.count(func.distinct(_auditor_key_expr()))).scalar() or 0
    body["batches"] = base.with_entities(
        func.count(func.distinct(AuditResult.batch_id))).scalar() or 0
    body["pass_threshold"] = cfg.pass_threshold
    return body


@router.get("/analytics/by-specialty")
def by_specialty(batch_id: Optional[int] = None, specialty: Optional[str] = None,
                 auditor: Optional[str] = None,
                 from_date: Optional[str] = None, to_date: Optional[str] = None,
                 db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    specialties = [sp for sp, in base.with_entities(AuditResult.specialty)
                   .group_by(AuditResult.specialty)
                   .order_by(AuditResult.specialty.asc()).all()]
    out = []
    for sp in specialties:
        scoped = _base_query(db, batch_id, sp.value if hasattr(sp, "value") else sp,
                             auditor, from_date, to_date)
        body = _roll_sql(db, scoped, cfg)
        out.append({
            "specialty": sp.value if hasattr(sp, "value") else sp,
            "auditors": scoped.with_entities(
                func.count(func.distinct(_auditor_key_expr()))).scalar() or 0,
            "batches": scoped.with_entities(
                func.count(func.distinct(AuditResult.batch_id))).scalar() or 0,
            **body,
        })
    out.sort(key=lambda x: (x["audit_score"] if x["audit_score"] is not None else 999,
                            -x["charts"]))
    return {"specialties": out, "pass_threshold": cfg.pass_threshold}


@router.get("/analytics/by-batch")
def by_batch(batch_id: Optional[int] = None, specialty: Optional[str] = None,
             auditor: Optional[str] = None, search: Optional[str] = None,
             from_date: Optional[str] = None, to_date: Optional[str] = None,
             sort: str = "weakest",
             limit: int = Query(100, le=300),
             db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        base = base.join(AuditBatch, AuditBatch.id == AuditResult.batch_id).filter(or_(
            AuditBatch.name.ilike(needle),
            cast(AuditBatch.specialty, String).ilike(needle),
        ))
    # One grouped query for the batch ids that actually have results, rather
    # than loading every result and bucketing them in Python.
    grouped = base.with_entities(
        AuditResult.batch_id,
        func.max(AuditResult.scored_at).label("last_scored"),
        func.count(AuditResult.id).label("charts"),
        func.count(func.distinct(_auditor_key_expr())).label("auditors"),
    ).group_by(AuditResult.batch_id)
    matched = grouped.count()
    if sort == "latest":
        grouped = grouped.order_by(func.max(AuditResult.scored_at).desc(),
                                   AuditResult.batch_id.desc())
    elif sort == "charts":
        grouped = grouped.order_by(func.count(AuditResult.id).desc(),
                                   AuditResult.batch_id.desc())
    elif sort == "auditors":
        grouped = grouped.order_by(func.count(func.distinct(_auditor_key_expr())).desc(),
                                   AuditResult.batch_id.desc())
    else:
        grouped = grouped.order_by(_blend_expr(cfg).asc(), AuditResult.batch_id.desc())
    ids = [bid for bid, *_ in grouped.limit(limit).all()]
    if not ids:
        return {"batches": [], "matched": 0}
    batches = {b.id: b for b in db.query(AuditBatch).filter(AuditBatch.id.in_(ids)).all()}

    out = []
    for bid in ids:
        batch = batches.get(bid)
        scoped = _base_query(db, bid, specialty, auditor, from_date, to_date)
        scored_at = scoped.with_entities(func.max(AuditResult.scored_at)).scalar()
        out.append({
            "batch_id": bid,
            "name": batch.name if batch else f"Batch {bid}",
            "specialty": batch.specialty.value if batch else None,
            "status": batch.status.value if batch else None,
            "scored_at": scored_at.isoformat() if scored_at else None,
            "auditors": scoped.with_entities(
                func.count(func.distinct(_auditor_key_expr()))).scalar() or 0,
            **_roll_sql(db, scoped, cfg),
        })
    return {"batches": out, "matched": matched}


def _auditor_gaps(db, scoped, top: int = 3) -> list:
    """
    The themes among the findings one auditor MISSED.

    Missed only — a planting they caught is not a gap, and mixing the two would
    rank an auditor's strongest area alongside their weakest purely on volume.
    """
    pairs = []
    for r in scoped.all():
        for entry in (r.feedback or []):
            planting = entry.get("planting")
            if not planting:
                continue
            if (entry.get("outcome") or "missed") == "correct":
                continue
            code = planting.get("correct_value")
            if code:
                pairs.append((planting.get("section"), code))
    if not pairs:
        return []
    enriched = enrich_codes(db, pairs)
    return axis_themes(pairs, enriched, top=top) if enriched else []


@router.get("/analytics/by-auditor")
def by_auditor(batch_id: Optional[int] = None, specialty: Optional[str] = None,
               auditor: Optional[str] = None, search: Optional[str] = None,
               from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = Query(200, le=500),
               db: Session = Depends(get_db)):
    """
    One row per auditor, cumulative across everything in scope.

    Component accuracies pool here rather than averaging per-session rates, so
    an auditor who sat one heavy session and one light one is measured on all
    their opportunities rather than on the mean of two percentages.
    """
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    # Search runs HERE, not in the browser. The tab shows twenty rows at most,
    # so filtering a loaded page meant an auditor past the cap could not be
    # found at all — the cap silently became the roster.
    if search:
        needle = f"%{search.strip()}%"
        base = base.filter(
            func.coalesce(AuditResult.auditor_name, "").ilike(needle)
            | func.coalesce(AuditResult.emp_id, "").ilike(needle))
    # Weakest first, decided in SQL so the cap keeps the auditors who most
    # need attention rather than an arbitrary slice.
    grouping = (AuditResult.emp_id, AuditResult.auditor_name)
    matched = base.with_entities(*grouping).group_by(*grouping).count()
    keys = base.with_entities(
        AuditResult.emp_id,
        AuditResult.auditor_name,
        func.avg(AuditResult.audit_accuracy).label("avg_accuracy"),
    ).group_by(
        AuditResult.emp_id,
        AuditResult.auditor_name,
    ).order_by(
        # Weakest first on the Audit Score — the figure the card shows. These
        # lists are capped, so the sort decides who a trainer ever sees.
        _blend_expr(cfg).asc()
    ).limit(limit).all()
    out = []
    for emp, name, _avg_accuracy in keys:
        key = f"{emp}||{name}" if emp else name
        scoped = _base_query(db, batch_id, specialty, key, from_date, to_date)
        out.append({
            "auditor_name": name,
            "emp_id": emp,
            "auditor_key": key,
            "batches": scoped.with_entities(
                func.count(func.distinct(AuditResult.batch_id))).scalar() or 0,
            **_roll_sql(db, scoped, cfg),
            # What this auditor keeps missing, as a theme rather than a list of
            # codes. "Missed SDx" says which box; "circulatory diagnoses, MCC
            # secondaries" is the coaching conversation.
            "knowledge_gaps": _auditor_gaps(db, scoped),
        })
    return {"auditors": out, "matched": matched,
            "pass_threshold": cfg.pass_threshold}


def _chart_focus(db, chart_ids, batch_id, specialty, auditor,
                 from_date, to_date) -> dict:
    """
    The dominant theme among each chart's planted errors.

    A second pass: chart signals is a SQL aggregate and the plantings live in a
    JSON column, so this reads them for the charts on the page only. Returns
    {chart_id: {kind, label, count}} with nothing for charts whose errors share
    no theme, which is the common answer at small volumes and a real one.
    """
    if not chart_ids:
        return {}
    rows = (_base_query(db, batch_id, specialty, auditor, from_date, to_date)
            .filter(AuditResult.chart_id.in_(list(chart_ids))).all())
    pairs_by_chart: dict = {}
    for r in rows:
        for entry in (r.feedback or []):
            planting = entry.get("planting")
            if not planting:
                continue
            code = planting.get("correct_value")
            if code:
                pairs_by_chart.setdefault(r.chart_id, []).append(
                    (planting.get("section"), code))
    if not pairs_by_chart:
        return {}
    enriched = enrich_codes(db, [p for ps in pairs_by_chart.values() for p in ps])
    if not enriched:
        return {}
    out = {}
    for chart_id, pairs in pairs_by_chart.items():
        themes = axis_themes(pairs, enriched)
        if themes:
            out[chart_id] = themes[0]
    return out


@router.get("/analytics/chart-signals")
def chart_signals(batch_id: Optional[int] = None, specialty: Optional[str] = None,
                  auditor: Optional[str] = None, search: Optional[str] = None,
                  from_date: Optional[str] = None, to_date: Optional[str] = None,
                  limit: int = Query(200, le=500),
                  db: Session = Depends(get_db)):
    """
    Chart-level QA signals for trainer review.

    This is the auditor version of chart signals: not whether a coding chart is
    difficult, but whether a pre-coded audit chart repeatedly creates misses,
    over-calls, or key-quality conversations.
    """
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    charted = base.join(Chart, Chart.id == AuditResult.chart_id)
    if search and search.strip():
        needle = f"%{search.strip().lower()}%"
        charted = charted.filter(or_(
            func.lower(Chart.chart_number).like(needle),
            func.lower(Chart.category).like(needle),
            func.lower(cast(AuditResult.specialty, String)).like(needle),
        ))

    rows = (charted
            .with_entities(
                AuditResult.chart_id,
                Chart.chart_number,
                Chart.category,
                AuditResult.specialty,
                func.count(AuditResult.id).label("attempts"),
                func.avg(AuditResult.audit_accuracy).label("audit_accuracy"),
                func.sum(case((AuditResult.is_clean == True, 1), else_=0)).label("clean_charts"),  # noqa: E712
                func.sum(case((AuditResult.is_clean == False, 1), else_=0)).label("opportunity_charts"),  # noqa: E712
                func.sum(func.coalesce(AuditResult.over_calls, 0)).label("over_calls"),
                func.sum(func.coalesce(AuditResult.detected_not_corrected, 0)).label("detected_not_corrected"),
                func.sum(func.coalesce(AuditResult.add_planted, 0)
                         + func.coalesce(AuditResult.revise_planted, 0)
                         + func.coalesce(AuditResult.delete_planted, 0)).label("opportunities"),
                func.sum((func.coalesce(AuditResult.add_planted, 0) - func.coalesce(AuditResult.add_found, 0))
                         + (func.coalesce(AuditResult.revise_planted, 0) - func.coalesce(AuditResult.revise_found, 0))
                         + (func.coalesce(AuditResult.delete_planted, 0) - func.coalesce(AuditResult.delete_found, 0))).label("missed"),
            )
            .group_by(AuditResult.chart_id, Chart.chart_number, Chart.category, AuditResult.specialty)
            .order_by(func.avg(AuditResult.audit_accuracy).asc(), func.count(AuditResult.id).desc())
            .limit(limit).all())

    # Totals come from the whole filtered set, never from the capped page
    # above. Counting the loaded rows is the defect this codebase has already
    # paid for three times: it reads correctly at a dozen charts and silently
    # understates everything past the cap.
    grouped = (charted.with_entities(
        AuditResult.chart_id.label("chart_id"),
        func.count(AuditResult.id).label("attempts"),
        func.sum(func.coalesce(AuditResult.add_planted, 0)
                 + func.coalesce(AuditResult.revise_planted, 0)
                 + func.coalesce(AuditResult.delete_planted, 0)).label("opportunities"),
        _MISSED_EXPR.label("missed"),
        func.sum(func.coalesce(AuditResult.over_calls, 0)).label("over_calls"),
        func.sum(func.coalesce(AuditResult.detected_not_corrected, 0)).label("dnc"),
    ).group_by(AuditResult.chart_id).subquery())

    g = sa_aliased(grouped)
    has_signal = case(
        ((g.c.missed > 0) | (g.c.over_calls > 0) | (g.c.dnc > 0), 1), else_=0)
    total_charts, with_signals = db.query(
        func.count(), func.coalesce(func.sum(has_signal), 0)).select_from(g).one()

    def _top(col):
        row = (db.query(g.c.chart_id, col).select_from(g)
               .order_by(col.desc()).limit(1).first())
        if not row or not row[1]:
            return None
        chart = db.query(Chart).filter(Chart.id == row[0]).first()
        return {"chart_number": chart.chart_number if chart else str(row[0]),
                "count": int(row[1])}

    def _priority(missed: int, over_calls: int, dnc: int,
                  opportunities: int, attempts: int) -> str:
        miss_rate = (missed / opportunities * 100) if opportunities else 0
        overcall_rate = (over_calls / attempts * 100) if attempts else 0
        correction_risk = (dnc / opportunities * 100) if opportunities else 0
        if attempts < 2 and (missed or over_calls or dnc):
            return "Early Signal"
        if correction_risk >= 25:
            return "Correction Risk"
        if overcall_rate >= 25:
            return "Overcall Risk"
        if miss_rate >= 25:
            return "Detection Difficulty"
        if missed or over_calls or dnc:
            return "Monitor"
        return "Stable"

    priority_counts: dict[str, int] = {}
    for attempts, opportunities, missed, over_calls, dnc in db.query(
            g.c.attempts, g.c.opportunities, g.c.missed,
            g.c.over_calls, g.c.dnc).select_from(g).all():
        label = _priority(int(missed or 0), int(over_calls or 0), int(dnc or 0),
                          int(opportunities or 0), int(attempts or 0))
        priority_counts[label] = priority_counts.get(label, 0) + 1
    priority_order = [
        "Correction Risk", "Overcall Risk", "Detection Difficulty",
        "Monitor", "Early Signal", "Stable",
    ]

    totals = {
        "charts_total": int(total_charts or 0),
        "charts_with_signals": int(with_signals or 0),
        "charts_stable": int((total_charts or 0) - (with_signals or 0)),
        "most_missed": _top(g.c.missed),
        "most_over_called": _top(g.c.over_calls),
        "priority_distribution": [
            {"label": label, "count": count}
            for label, count in sorted(
                priority_counts.items(),
                key=lambda item: priority_order.index(item[0])
                if item[0] in priority_order else len(priority_order),
            )
        ],
        "returned": len(rows),
    }

    out = []
    for r in rows:
        missed = int(r.missed or 0)
        over_calls = int(r.over_calls or 0)
        detected_not_corrected = int(r.detected_not_corrected or 0)
        attempts = int(r.attempts or 0)
        opportunities = int(r.opportunities or 0)
        miss_rate = _rate(opportunities - missed, opportunities)
        miss_risk = round(missed / opportunities * 100, 2) if opportunities else None
        overcall_rate = round(over_calls / attempts * 100, 2) if attempts else None
        correction_risk = round(detected_not_corrected / opportunities * 100, 2) if opportunities else None
        risk_rates = [v for v in (miss_risk, overcall_rate, correction_risk) if v is not None]
        stability_score = round(100 - (sum(risk_rates) / len(risk_rates)), 2) if risk_rates else 100.0
        priority = _priority(missed, over_calls, detected_not_corrected, opportunities, attempts)
        signals = []
        if missed:
            signals.append("missed findings")
        if over_calls:
            signals.append("over-calls")
        if detected_not_corrected:
            signals.append("found but corrected wrongly")
        if not signals:
            signals.append("stable")
        out.append({
            "chart_id": r.chart_id,
            "chart_number": r.chart_number,
            "category": r.category,
            "specialty": r.specialty.value if hasattr(r.specialty, "value") else r.specialty,
            "attempts": attempts,
            "confidence": "Established" if attempts >= 3 else "Early",
            "audit_accuracy": round(float(r.audit_accuracy), 2) if r.audit_accuracy is not None else None,
            "clean_charts": int(r.clean_charts or 0),
            "opportunity_charts": int(r.opportunity_charts or 0),
            "opportunities": opportunities,
            "missed": missed,
            "over_calls": over_calls,
            "detected_not_corrected": detected_not_corrected,
            "detection_score": miss_rate,
            "miss_risk": miss_risk,
            "overcall_rate": overcall_rate,
            "correction_risk": correction_risk,
            "signal_load": missed + over_calls + detected_not_corrected,
            "stability_score": stability_score,
            "review_priority": priority,
            "signal": " · ".join(signals),
        })

    # What each chart's planted errors are ABOUT, so a trainer can tell whether
    # it is the right chart to drill a weakness with. Same rule and same
    # threshold as the coder module — a theme, not an incident.
    focus = _chart_focus(db, [c["chart_id"] for c in out],
                         batch_id, specialty, auditor, from_date, to_date)
    for row in out:
        row["focus"] = focus.get(row["chart_id"])
    return {"charts": out, **totals}


KIND_LABELS = {
    "omit_sdx": "Missed secondary diagnosis",
    "omit_proc": "Missed procedure",
    "modifier_missing": "Missing modifier",
    "modifier_wrong": "Wrong modifier",
    "substitute": "Wrong diagnosis (prefix family)",
    "substitute_pcs": "Wrong PCS character",
    "swap_pdx": "Principal/secondary sequencing",
    "units": "Wrong units",
    "poa": "Wrong POA",
    "spurious": "Spurious code",
    "observed": "Real coder mistake",
}


def _section_action_matrix(cells: dict) -> dict:
    """
    Section down, action across — with row and column totals.

    These were flat rows keyed "SDx · Revise", which answers only the question
    it was built for. A trainer's next two questions are "how are we on SDx
    overall?" and "are Revises worse than Deletes everywhere?", and a list of
    compound strings can answer neither. A matrix answers both by being read in
    the other direction, and takes less room than the list it replaces.

    Only sections and actions that actually occur appear, so an outpatient
    cohort shows no PCS row rather than a row of dashes.
    """
    def _cell(c):
        return {**c, "accuracy": _rate(c["found"], c["planted"])}

    def _blank():
        return {"planted": 0, "found": 0, "missed": 0, "detected_not_corrected": 0}

    def _add(into, c):
        for k in ("planted", "found", "missed", "detected_not_corrected"):
            into[k] += c[k]
        return into

    order_s = ["PDx", "SDx", "PCS", "CPT"]
    order_a = ["Add", "Revise", "Delete"]
    sections = [s for s in order_s if any(k[0] == s for k in cells)]
    sections += sorted({k[0] for k in cells} - set(order_s))
    actions = [a for a in order_a if any(k[1] == a for k in cells)]
    actions += sorted({k[1] for k in cells} - set(order_a))

    rows, row_totals, col_totals = {}, {}, {a: _blank() for a in actions}
    grand = _blank()
    for s in sections:
        rows[s] = {}
        total = _blank()
        for a in actions:
            c = cells.get((s, a))
            if not c:
                continue
            rows[s][a] = _cell(c)
            _add(total, c)
            _add(col_totals[a], c)
            _add(grand, c)
        row_totals[s] = _cell(total)
    return {
        "sections": sections,
        "actions": actions,
        "cells": rows,
        "section_totals": row_totals,
        "action_totals": {a: _cell(c) for a, c in col_totals.items()},
        "total": _cell(grand),
    }


def _pcs_axis_map(db, plantings) -> dict:
    """
    Axis titles for every PCS code in this scan, in one query.

    Built per request from the codes actually present rather than held as a
    module global: the table is 79,000 rows, and a request touches a handful.
    Empty when the tables are not loaded, which makes every caller silent.
    """
    codes = {c for p in plantings for c in (_bare_pcs(p.get("correct_value")),
                                            _bare_pcs(p.get("claim_value"))) if c}
    if not codes:
        return {}
    try:
        from models import PcsCodeAxis
        rows = (db.query(PcsCodeAxis)
                .filter(PcsCodeAxis.code.in_(sorted(codes))).all())
    except Exception:
        return {}
    return {r.code: {"body_system": r.body_system,
                     "root_operation": r.root_operation,
                     "approach": r.approach, "device": r.device,
                     "qualifier": r.qualifier, "body_part": r.body_part}
            for r in rows}


def _bump_pcs_axes(axes: dict, confusions: dict, planting: dict,
                   outcome: str, bump, pcs_map: dict) -> None:
    """
    Group a PCS planting by what its characters MEAN.

    Two different things come out of this. The axis buckets say which body
    systems and root operations the misses cluster in, read off the correct
    code. The confusion buckets name the specific swap — both the planted value
    and the right one are real codes, so the difference between them can be
    stated rather than implied.

    Silent when the PCS tables are not loaded, like everything else built on
    the reference data.
    """
    if (planting.get("section") or "") != "PCS":
        return
    correct = pcs_map.get(_bare_pcs(planting.get("correct_value")))
    if not correct:
        return
    for axis in ("body_system", "root_operation", "approach", "device",
                 "qualifier", "body_part"):
        value = correct.get(axis)
        if value:
            bump(axes.setdefault(axis, {}), value, outcome)

    planted = pcs_map.get(_bare_pcs(planting.get("claim_value")))
    if not planted:
        return
    # Exactly the axes that differ. A single-character mutation gives one;
    # an observed error may give more, and naming all of them is honest.
    for axis in ("body_system", "root_operation", "approach", "device",
                 "qualifier", "body_part"):
        was, should = planted.get(axis), correct.get(axis)
        if was and should and was != should:
            label = "%s: %s read as %s" % (
                axis.replace("_", " "), should, was)
            bump(confusions, label, outcome)


def _bare_pcs(code) -> str:
    return str(code or "").strip().upper().replace(" ", "")


@router.get("/analytics/detection")
def detection_patterns(batch_id: Optional[int] = None,
                       specialty: Optional[str] = None,
                       auditor: Optional[str] = None,
                       from_date: Optional[str] = None,
                       to_date: Optional[str] = None,
                       scan_limit: int = Query(5000, le=20000),
                       db: Session = Depends(get_db)):
    """
    Which KINDS of planted error get caught, and which slip past.

    This is the report the coder analytics has no equivalent of, and the reason
    the module is worth something beyond individual scoring: "70% of your
    auditors miss root-operation errors" is a training curriculum writing
    itself.

    Also split by origin, because the comparison is genuinely interesting —
    auditors tend to do better on generated errors than on the ones their own
    coders actually make, and only the second number describes the job.
    """
    # This is the one report that cannot be done in SQL — the outcome of each
    # error lives inside a JSON column. So it is capped, and the payload says
    # how much it looked at rather than implying it read everything.
    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    total_results = base.with_entities(func.count(AuditResult.id)).scalar() or 0
    rows = (base.order_by(AuditResult.id.desc())
            .limit(scan_limit).all())

    by_kind: dict[str, dict] = {}
    by_section: dict[str, dict] = {}
    by_origin: dict[str, dict] = {}
    pcs_chars: dict[str, dict] = {}
    # The VALUES of the seven characters, not just which position changed.
    # "Root operation" says where to look; "Resection read as Excision" is the
    # thing to teach.
    pcs_axes: dict = {}
    pcs_confusions: dict = {}
    # Which BODY of knowledge the error sat in, not which mechanic produced it.
    # "Root operation errors are missed" tells a trainer what to drill;
    # "obstetric diagnoses are missed" tells them who to put on which charts,
    # and the two do not overlap. Chapters come from the code itself, so this
    # costs no query and works whether or not the code sets are loaded.
    by_chapter: dict[str, dict] = {}
    # One query for every PCS code in this scan, before the walk below.
    pcs_map = _pcs_axis_map(db, [e.get("planting") or {} for r in rows
                                 for e in (r.feedback or [])])

    def bump(bucket: dict, key: str, outcome: str) -> None:
        cell = bucket.setdefault(key, {"planted": 0, "found": 0, "missed": 0,
                                       "detected_not_corrected": 0})
        cell["planted"] += 1
        if outcome == "correct":
            cell["found"] += 1
        elif outcome == "detected_not_corrected":
            cell["detected_not_corrected"] += 1
        else:
            cell["missed"] += 1

    for r in rows:
        for entry in (r.feedback or []):
            # feedback now carries over-calls as well as matched plantings.
            # An over-call entry has no "planting", and without this guard it
            # would be counted as a planting of kind "unknown" — inflating
            # total_plantings and depressing every detection rate on the tab.
            planting = entry.get("planting")
            if not planting:
                continue
            outcome = entry.get("outcome") or "missed"
            kind = planting.get("kind") or planting.get("action") or "unknown"
            bump(by_kind, kind, outcome)
            bump(by_section, (planting.get("section") or "?",
                              planting.get("action") or "?"), outcome)
            bump(by_origin, "observed" if planting.get("origin") == "observed" else "synthetic", outcome)
            if planting.get("pcs_character"):
                bump(pcs_chars, planting["pcs_character"], outcome)
            _bump_pcs_axes(pcs_axes, pcs_confusions, planting, outcome,
                           bump, pcs_map)
            if (planting.get("section") or "") in ("PDx", "SDx"):
                # correct_value is the code that SHOULD be there — the chapter
                # of the right answer, not of whatever was planted in its place.
                _no, title = chapter_for(str(planting.get("correct_value") or ""))
                if title:
                    bump(by_chapter, title, outcome)

    def shape(bucket: dict, label_map: Optional[dict] = None) -> list[dict]:
        out = []
        for key, cell in bucket.items():
            out.append({
                "key": key,
                "label": (label_map or {}).get(key, key),
                **cell,
                "accuracy": _rate(cell["found"], cell["planted"]),
            })
        # Worst first — the point of this screen is what to teach next.
        out.sort(key=lambda x: (x["accuracy"] if x["accuracy"] is not None else 999,
                                -x["planted"]))
        return out

    kinds = shape(by_kind, KIND_LABELS)
    # A kind seen twice is not a pattern. Surfaced separately so a trainer does
    # not build a curriculum on a single miss.
    weak = [k for k in kinds if k["planted"] >= 5 and (k["accuracy"] or 0) < 60]
    origins = shape(by_origin, {"observed": "Errors your coders really made",
                                "synthetic": "System-generated errors"})
    section_matrix = _section_action_matrix(by_section)
    total_plantings = sum(c["planted"] for c in by_kind.values())

    notes = []
    if weak:
        top = weak[0]
        notes.append({
            "kind": "focus",
            "text": f"{top['label']} is the weakest repeated pattern: "
                    f"{top['found']}/{top['planted']} caught.",
        })

    missed = sum(c["missed"] for c in by_kind.values())
    if total_plantings and missed / total_plantings >= 0.3:
        notes.append({
            "kind": "coaching",
            "text": f"Auditors missed {missed}/{total_plantings} introduced errors. "
                    "Prioritise detection practice before correction quality.",
        })

    wrong_fix = sum(c["detected_not_corrected"] for c in by_kind.values())
    if total_plantings and wrong_fix / total_plantings >= 0.15:
        notes.append({
            "kind": "coaching",
            "text": f"{wrong_fix} finding(s) were detected but corrected incorrectly. "
                    "These need coding-rule review, not just audit workflow practice.",
        })

    # The heaviest SECTION, read off the matrix's row totals rather than the
    # flat "SDx · Revise" rows this used to sort. A section carrying most of
    # the volume is the drill area whichever action it arrives through.
    row_totals = section_matrix["section_totals"]
    top_section = max(row_totals.items(), key=lambda kv: kv[1]["planted"], default=None)
    if top_section and total_plantings \
            and top_section[1]["planted"] / total_plantings >= 0.4:
        name, cell = top_section
        notes.append({
            "kind": "focus",
            "text": f"{name} carries most of the missed opportunity "
                    f"({cell['planted']} introduced). Treat it as the first drill area.",
        })

    origin_map = {o["key"]: o for o in origins}
    observed = origin_map.get("observed")
    synthetic = origin_map.get("synthetic")
    if observed and synthetic and observed["planted"] >= 5 and synthetic["planted"] >= 5:
        observed_acc = observed["accuracy"] or 0
        synthetic_acc = synthetic["accuracy"] or 0
        if observed_acc + 15 < synthetic_acc:
            notes.append({
                "kind": "warn",
                "text": "Real coder-error patterns are being missed more often than generated errors.",
            })
        elif observed_acc >= synthetic_acc + 15:
            notes.append({
                "kind": "good",
                "text": "Auditors are catching real coder-error patterns better than generated errors.",
            })

    ACTION_ORDER = {"focus": 0, "coaching": 1, "warn": 2, "good": 3, "info": 4}
    notes.sort(key=lambda n: ACTION_ORDER.get(n["kind"], 9))
    extra_notes = notes[4:]
    notes = notes[:4]

    return {
        "by_kind": kinds,
        "section_matrix": section_matrix,
        "by_origin": origins,
        "pcs_characters": shape(pcs_chars),
        # Grouped by the value of each axis on the CORRECT code — what the
        # procedure actually was — so a trainer can see which body systems and
        # root operations the misses cluster in.
        "pcs_axes": {axis: shape(bucket) for axis, bucket in pcs_axes.items()
                     if bucket},
        # And the specific confusions, from diffing the planted code against
        # the right one. Both are real codes, so the difference is nameable.
        "pcs_confusions": shape(pcs_confusions)[:10],
        # Capped: 22 chapters is already a long list and the tail is single
        # plantings, which say nothing. Worst first, so the cap keeps what
        # matters.
        "by_chapter": [c for c in shape(by_chapter) if c["planted"] >= 3][:10],
        "weakest": weak,
        "commentary": notes,
        "commentary_more": extra_notes,
        "total_plantings": total_plantings,
        "min_for_pattern": 5,
        "charts_scanned": len(rows),
        "charts_available": int(total_results),
        "truncated": len(rows) < int(total_results),
    }


@router.get("/analytics/export")
def export_analytics_workbook(batch_id: Optional[int] = None,
                              specialty: Optional[str] = None,
                              auditor: Optional[str] = None,
                              from_date: Optional[str] = None,
                              to_date: Optional[str] = None,
                              db: Session = Depends(get_db)):
    """All four analytics views in one workbook, current filters applied."""
    from services.audit_export import export_analytics
    from services.download_headers import content_disposition

    # Keyword arguments on purpose. These handlers carry paging and scan-limit
    # parameters whose defaults are FastAPI Query objects, so a positional call
    # silently lands the session on the wrong argument.
    data = export_analytics(
        overview(batch_id=batch_id, specialty=specialty, auditor=auditor,
                 from_date=from_date, to_date=to_date, db=db),
        by_batch(batch_id=batch_id, specialty=specialty, auditor=auditor,
                 from_date=from_date, to_date=to_date, limit=300, db=db)["batches"],
        by_auditor(batch_id=batch_id, specialty=specialty, auditor=auditor,
                   from_date=from_date, to_date=to_date, limit=500, db=db)["auditors"],
        detection_patterns(batch_id=batch_id, specialty=specialty, auditor=auditor,
                           from_date=from_date, to_date=to_date, scan_limit=20000, db=db),
        by_specialty(batch_id=batch_id, specialty=specialty, auditor=auditor,
                     from_date=from_date, to_date=to_date, db=db)["specialties"],
        chart_signals(batch_id=batch_id, specialty=specialty, auditor=auditor,
                      from_date=from_date, to_date=to_date, limit=500, db=db)["charts"],
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Audit_Analytics.xlsx", "Audit_Analytics.xlsx"))


@router.get("/analytics/auditor-report.pdf")
def auditor_report_pdf(auditor: str, batch_id: Optional[int] = None,
                       specialty: Optional[str] = None,
                       from_date: Optional[str] = None,
                       to_date: Optional[str] = None,
                       db: Session = Depends(get_db)):
    from services.download_headers import content_disposition
    from services.pdf_report_service import generate_audit_auditor_report_pdf

    rows = by_auditor(batch_id=batch_id, specialty=specialty, auditor=auditor,
                      from_date=from_date, to_date=to_date,
                      limit=1, db=db)["auditors"]
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this auditor")
    auditor_row = rows[0]
    data = {
        "auditor": auditor_row,
        "overview": overview(batch_id=batch_id, specialty=specialty,
                             auditor=auditor, from_date=from_date,
                             to_date=to_date, db=db),
        "batches": by_batch(batch_id=batch_id, specialty=specialty,
                            auditor=auditor, from_date=from_date,
                            to_date=to_date, limit=300, db=db)["batches"],
        "detection": detection_patterns(batch_id=batch_id, specialty=specialty,
                                        auditor=auditor, from_date=from_date,
                                        to_date=to_date, scan_limit=20000, db=db),
        "specialty": specialty,
    }
    pdf_bytes = generate_audit_auditor_report_pdf(data)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(
            f"{auditor_row['auditor_name']}_Audit_Performance_Report.pdf",
            "Audit_Performance_Report.pdf"))


@router.get("/analytics/pattern")
def pattern_detail(kind: Optional[str] = None,
                   section: Optional[str] = None,
                   action: Optional[str] = None,
                   origin: Optional[str] = None,
                   batch_id: Optional[int] = None,
                   specialty: Optional[str] = None,
                   auditor: Optional[str] = None,
                   from_date: Optional[str] = None,
                   to_date: Optional[str] = None,
                   scan_limit: int = Query(5000, le=20000),
                   db: Session = Depends(get_db)):
    """
    One error pattern, drilled: who misses it, on which charts, and whether it
    is getting better.

    Error Patterns could tell a trainer that root-operation errors slip past
    70% of the time and then stopped. The next two questions are always "so
    who?" and "did last month's training work?", and neither had anywhere to
    go — the tab was a diagnosis with no treatment plan.

    Scanned rather than aggregated for the same reason the parent report is:
    the outcome of each error lives inside a JSON array. Same window, same
    cap, and the payload says how much it read.
    """
    if not any((kind, section, action, origin)):
        raise HTTPException(400, "Name a pattern: kind, section, action or origin")

    base = _base_query(db, batch_id, specialty, auditor, from_date, to_date)
    total_results = base.with_entities(func.count(AuditResult.id)).scalar() or 0
    rows = base.order_by(AuditResult.id.desc()).limit(scan_limit).all()

    def _blank():
        return {"planted": 0, "found": 0, "missed": 0, "detected_not_corrected": 0}

    def _matches(planting: dict) -> bool:
        if kind and (planting.get("kind") or planting.get("action")) != kind:
            return False
        if section and planting.get("section") != section:
            return False
        if action and planting.get("action") != action:
            return False
        if origin:
            seen = "observed" if planting.get("origin") == "observed" else "synthetic"
            if seen != origin:
                return False
        return True

    by_auditor: dict = {}
    by_chart: dict = {}
    by_week: dict = {}
    overall = _blank()

    for r in rows:
        key = (r.emp_id or "", r.auditor_name or "")
        when = r.scored_at
        monday = None
        if when is not None:
            d = when.date() if hasattr(when, "date") else None
            if d is not None:
                monday = d - timedelta(days=d.weekday())
        for entry in (r.feedback or []):
            planting = entry.get("planting")
            if not planting or not _matches(planting):
                continue
            outcome = entry.get("outcome") or "missed"
            for bucket in (overall,
                           by_auditor.setdefault(key, _blank()),
                           by_chart.setdefault(r.chart_id, _blank())):
                bucket["planted"] += 1
                if outcome == "correct":
                    bucket["found"] += 1
                elif outcome == "detected_not_corrected":
                    bucket["detected_not_corrected"] += 1
                else:
                    bucket["missed"] += 1
            if monday is not None:
                w = by_week.setdefault(monday, _blank())
                w["planted"] += 1
                if outcome == "correct":
                    w["found"] += 1
                elif outcome == "detected_not_corrected":
                    w["detected_not_corrected"] += 1
                else:
                    w["missed"] += 1

    charts = {c.id: c for c in db.query(Chart).filter(
        Chart.id.in_(list(by_chart) or [-1])).all()} if by_chart else {}

    auditors = [{
        "auditor_key": f"{emp}||{name}" if emp else name,
        "auditor_name": name,
        "emp_id": emp or None,
        **cell,
        "accuracy": _rate(cell["found"], cell["planted"]),
    } for (emp, name), cell in by_auditor.items()]
    # Worst first: this list exists to name who needs the drill.
    auditors.sort(key=lambda a: (a["accuracy"] if a["accuracy"] is not None else 999,
                                 -a["planted"]))

    chart_rows = [{
        "chart_id": cid,
        "chart_number": charts[cid].chart_number if cid in charts else str(cid),
        **cell,
        "accuracy": _rate(cell["found"], cell["planted"]),
    } for cid, cell in by_chart.items()]
    chart_rows.sort(key=lambda c: (c["accuracy"] if c["accuracy"] is not None else 999,
                                   -c["planted"]))

    # Weekly, matching the Overview trend, so the two read the same way.
    trend = [{
        "week_of": monday.isoformat(),
        **by_week[monday],
        "accuracy": _rate(by_week[monday]["found"], by_week[monday]["planted"]),
    } for monday in sorted(by_week)[-12:]]

    # ── which codes this pattern actually involved ───────────────────────────
    #
    # The tab could say root-operation errors slip past 70% of the time and
    # name who missed them, and never say WHICH procedures. A drilldown that
    # cannot be read clinically sends a trainer back to the charts to find out
    # what the pattern was about.
    codes: dict = {}
    for r in rows:
        for entry in (r.feedback or []):
            planting = entry.get("planting")
            if not planting or not _matches(planting):
                continue
            correct = planting.get("correct_value")
            if not correct:
                continue
            cell = codes.setdefault(str(correct), {
                "code": str(correct),
                "planted_as": planting.get("claim_value"),
                "section": planting.get("section"),
                "count": 0, "found": 0})
            cell["count"] += 1
            if (entry.get("outcome") or "missed") == "correct":
                cell["found"] += 1

    described = enrich_codes(db, [(c["section"], c["code"]) for c in codes.values()])
    pcs_map = _pcs_axis_map(db, [{"correct_value": c["code"],
                                  "claim_value": c["planted_as"]}
                                 for c in codes.values()])
    code_rows = []
    for cell in codes.values():
        info = lookup(described, cell["section"], cell["code"])
        axes = pcs_map.get(_bare_pcs(cell["code"])) or {}
        code_rows.append({
            **cell,
            "accuracy": _rate(cell["found"], cell["count"]),
            "description": (info or {}).get("description"),
            "chapter": chapter_label(info),
            # CC/MCC is a secondary-diagnosis concept, as everywhere else.
            "cc_mcc": ccmcc_label(info) if str(cell["section"] or "").upper() == "SDX" else None,
            "pcs": {k: v for k, v in axes.items() if v} or None,
        })
    code_rows.sort(key=lambda c: (c["accuracy"] if c["accuracy"] is not None else 999,
                                  -c["count"]))

    label = KIND_LABELS.get(kind or "", kind) if kind else None
    if not label:
        label = " · ".join(p for p in (section, action) if p) or (origin or "pattern")

    return {
        "label": label,
        "kind": kind, "section": section, "action": action, "origin": origin,
        **overall,
        "accuracy": _rate(overall["found"], overall["planted"]),
        "codes": code_rows[:25],
        "auditors": auditors[:50],
        "charts": chart_rows[:50],
        "trend": trend,
        "charts_scanned": len(rows),
        "charts_available": int(total_results),
        "truncated": len(rows) < int(total_results),
    }
