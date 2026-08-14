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

from typing import Optional

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import get_db
from models import AuditBatch, AuditResult, Chart
from .shared import scoring_config

router = APIRouter()


def _rate(found: int, planted: int) -> Optional[float]:
    """None, not zero, when there was nothing to find."""
    return round(found / planted * 100, 2) if planted else None


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


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
                auditor: Optional[str]):
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
    return q


R = AuditResult

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
    verdict = None
    withheld = None
    if opportunities >= cfg.min_opportunities_for_verdict:
        verdict = "PASS" if (audit_accuracy or 0) >= cfg.pass_threshold else "FAIL"
    else:
        withheld = ("indicative only — too few opportunities for a verdict"
                    if opportunities else
                    "restraint measure only — no opportunities yet")

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
        "pass_fail": verdict,
        "verdict_withheld_reason": withheld,
    }


@router.get("/analytics/overview")
def overview(batch_id: Optional[int] = None, specialty: Optional[str] = None,
             auditor: Optional[str] = None,
             db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor)
    body = _roll_sql(db, base, cfg)
    body["auditors"] = base.with_entities(
        func.count(func.distinct(_auditor_key_expr()))).scalar() or 0
    body["batches"] = base.with_entities(
        func.count(func.distinct(AuditResult.batch_id))).scalar() or 0
    body["pass_threshold"] = cfg.pass_threshold
    return body


@router.get("/analytics/by-specialty")
def by_specialty(batch_id: Optional[int] = None, specialty: Optional[str] = None,
                 auditor: Optional[str] = None,
                 db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor)
    specialties = [sp for sp, in base.with_entities(AuditResult.specialty)
                   .group_by(AuditResult.specialty)
                   .order_by(AuditResult.specialty.asc()).all()]
    out = []
    for sp in specialties:
        scoped = _base_query(db, batch_id, sp.value if hasattr(sp, "value") else sp, auditor)
        body = _roll_sql(db, scoped, cfg)
        out.append({
            "specialty": sp.value if hasattr(sp, "value") else sp,
            "auditors": scoped.with_entities(
                func.count(func.distinct(_auditor_key_expr()))).scalar() or 0,
            "batches": scoped.with_entities(
                func.count(func.distinct(AuditResult.batch_id))).scalar() or 0,
            **body,
        })
    out.sort(key=lambda x: (x["audit_accuracy"] if x["audit_accuracy"] is not None else 999,
                            -x["charts"]))
    return {"specialties": out, "pass_threshold": cfg.pass_threshold}


@router.get("/analytics/by-batch")
def by_batch(batch_id: Optional[int] = None, specialty: Optional[str] = None,
             auditor: Optional[str] = None,
             limit: int = Query(100, le=300),
             db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor)
    # One grouped query for the batch ids that actually have results, rather
    # than loading every result and bucketing them in Python.
    ids = [bid for bid, in base.with_entities(AuditResult.batch_id)
           .group_by(AuditResult.batch_id)
           .order_by(AuditResult.batch_id.desc()).limit(limit).all()]
    if not ids:
        return {"batches": []}
    batches = {b.id: b for b in db.query(AuditBatch).filter(AuditBatch.id.in_(ids)).all()}

    out = []
    for bid in ids:
        batch = batches.get(bid)
        scoped = _base_query(db, bid, specialty, auditor)
        out.append({
            "batch_id": bid,
            "name": batch.name if batch else f"Batch {bid}",
            "specialty": batch.specialty.value if batch else None,
            "status": batch.status.value if batch else None,
            "auditors": scoped.with_entities(
                func.count(func.distinct(_auditor_key_expr()))).scalar() or 0,
            **_roll_sql(db, scoped, cfg),
        })
    return {"batches": out}


@router.get("/analytics/by-auditor")
def by_auditor(batch_id: Optional[int] = None, specialty: Optional[str] = None,
               auditor: Optional[str] = None,
               limit: int = Query(200, le=500),
               db: Session = Depends(get_db)):
    """
    One row per auditor, cumulative across everything in scope.

    Component accuracies pool here rather than averaging per-session rates, so
    an auditor who sat one heavy session and one light one is measured on all
    their opportunities rather than on the mean of two percentages.
    """
    cfg = scoring_config(db)
    base = _base_query(db, batch_id, specialty, auditor)
    # Weakest first, decided in SQL so the cap keeps the auditors who most
    # need attention rather than an arbitrary slice.
    keys = base.with_entities(
        AuditResult.emp_id,
        AuditResult.auditor_name,
        func.avg(AuditResult.audit_accuracy).label("avg_accuracy"),
    ).group_by(
        AuditResult.emp_id,
        AuditResult.auditor_name,
    ).order_by(
        func.avg(AuditResult.audit_accuracy).asc()
    ).limit(limit).all()
    out = []
    for emp, name, _avg_accuracy in keys:
        key = f"{emp}||{name}" if emp else name
        scoped = _base_query(db, batch_id, specialty, key)
        out.append({
            "auditor_name": name,
            "emp_id": emp,
            "auditor_key": key,
            "batches": scoped.with_entities(
                func.count(func.distinct(AuditResult.batch_id))).scalar() or 0,
            **_roll_sql(db, scoped, cfg),
        })
    return {"auditors": out, "pass_threshold": cfg.pass_threshold}


@router.get("/analytics/chart-signals")
def chart_signals(batch_id: Optional[int] = None, specialty: Optional[str] = None,
                  auditor: Optional[str] = None,
                  limit: int = Query(200, le=500),
                  db: Session = Depends(get_db)):
    """
    Chart-level QA signals for trainer review.

    This is the auditor version of chart signals: not whether a coding chart is
    difficult, but whether a pre-coded audit chart repeatedly creates misses,
    over-calls, or key-quality conversations.
    """
    base = _base_query(db, batch_id, specialty, auditor)
    rows = (base.join(Chart, Chart.id == AuditResult.chart_id)
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
    out = []
    for r in rows:
        missed = int(r.missed or 0)
        over_calls = int(r.over_calls or 0)
        detected_not_corrected = int(r.detected_not_corrected or 0)
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
            "attempts": int(r.attempts or 0),
            "audit_accuracy": round(float(r.audit_accuracy), 2) if r.audit_accuracy is not None else None,
            "clean_charts": int(r.clean_charts or 0),
            "opportunity_charts": int(r.opportunity_charts or 0),
            "opportunities": int(r.opportunities or 0),
            "missed": missed,
            "over_calls": over_calls,
            "detected_not_corrected": detected_not_corrected,
            "signal": " · ".join(signals),
        })
    return {"charts": out}


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


@router.get("/analytics/detection")
def detection_patterns(batch_id: Optional[int] = None,
                       specialty: Optional[str] = None,
                       auditor: Optional[str] = None,
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
    base = _base_query(db, batch_id, specialty, auditor)
    total_results = base.with_entities(func.count(AuditResult.id)).scalar() or 0
    rows = (base.order_by(AuditResult.id.desc())
            .limit(scan_limit).all())

    by_kind: dict[str, dict] = {}
    by_section: dict[str, dict] = {}
    by_origin: dict[str, dict] = {}
    pcs_chars: dict[str, dict] = {}

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
            planting = entry.get("planting") or {}
            outcome = entry.get("outcome") or "missed"
            kind = planting.get("kind") or planting.get("action") or "unknown"
            bump(by_kind, kind, outcome)
            bump(by_section, f'{planting.get("section", "?")} · {planting.get("action", "?")}', outcome)
            bump(by_origin, "observed" if planting.get("origin") == "observed" else "synthetic", outcome)
            if planting.get("pcs_character"):
                bump(pcs_chars, planting["pcs_character"], outcome)

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

    return {
        "by_kind": kinds,
        "by_section": shape(by_section),
        "by_origin": shape(by_origin, {"observed": "Errors your coders really made",
                                       "synthetic": "System-generated errors"}),
        "pcs_characters": shape(pcs_chars),
        "weakest": weak,
        "total_plantings": sum(c["planted"] for c in by_kind.values()),
        "min_for_pattern": 5,
        "charts_scanned": len(rows),
        "charts_available": int(total_results),
        "truncated": len(rows) < int(total_results),
    }


@router.get("/analytics/export")
def export_analytics_workbook(batch_id: Optional[int] = None,
                              specialty: Optional[str] = None,
                              auditor: Optional[str] = None,
                              db: Session = Depends(get_db)):
    """All four analytics views in one workbook, current filters applied."""
    from services.audit_export import export_analytics
    from services.download_headers import content_disposition

    # Keyword arguments on purpose. These handlers carry paging and scan-limit
    # parameters whose defaults are FastAPI Query objects, so a positional call
    # silently lands the session on the wrong argument.
    data = export_analytics(
        overview(batch_id=batch_id, specialty=specialty, auditor=auditor, db=db),
        by_batch(batch_id=batch_id, specialty=specialty, auditor=auditor, limit=300, db=db)["batches"],
        by_auditor(batch_id=batch_id, specialty=specialty, auditor=auditor, limit=500, db=db)["auditors"],
        detection_patterns(batch_id=batch_id, specialty=specialty, auditor=auditor,
                           scan_limit=20000, db=db),
        by_specialty(batch_id=batch_id, specialty=specialty, auditor=auditor, db=db)["specialties"],
        chart_signals(batch_id=batch_id, specialty=specialty, auditor=auditor, limit=500, db=db)["charts"],
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Audit_Analytics.xlsx", "Audit_Analytics.xlsx"))


@router.get("/analytics/auditor-report.pdf")
def auditor_report_pdf(auditor: str, batch_id: Optional[int] = None,
                       specialty: Optional[str] = None,
                       db: Session = Depends(get_db)):
    from services.download_headers import content_disposition
    from services.pdf_report_service import generate_audit_auditor_report_pdf

    rows = by_auditor(batch_id=batch_id, specialty=specialty, auditor=auditor,
                      limit=1, db=db)["auditors"]
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this auditor")
    auditor_row = rows[0]
    data = {
        "auditor": auditor_row,
        "overview": overview(batch_id=batch_id, specialty=specialty,
                             auditor=auditor, db=db),
        "batches": by_batch(batch_id=batch_id, specialty=specialty,
                            auditor=auditor, limit=300, db=db)["batches"],
        "detection": detection_patterns(batch_id=batch_id, specialty=specialty,
                                        auditor=auditor, scan_limit=20000, db=db),
        "specialty": specialty,
    }
    pdf_bytes = generate_audit_auditor_report_pdf(data)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(
            f"{auditor_row['auditor_name']}_Audit_Performance_Report.pdf",
            "Audit_Performance_Report.pdf"))
