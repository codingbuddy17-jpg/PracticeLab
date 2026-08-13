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

from fastapi import APIRouter, Depends, Query
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


def _base_query(db: Session, batch_id: Optional[int], specialty: Optional[str],
                auditor: Optional[str]):
    q = db.query(AuditResult)
    if batch_id:
        q = q.filter(AuditResult.batch_id == batch_id)
    if specialty:
        q = q.filter(AuditResult.specialty == specialty)
    if auditor:
        q = q.filter(AuditResult.auditor_name == auditor)
    return q


def _roll(rows: list[AuditResult], cfg) -> dict:
    """The figures every level of this report shares."""
    if not rows:
        return {"charts": 0, "audit_accuracy": None}

    clean = [r for r in rows if r.is_clean]
    opp = [r for r in rows if not r.is_clean]

    components = {}
    for name in ("add", "revise", "delete"):
        planted = sum(getattr(r, f"{name}_planted") for r in rows)
        found = sum(getattr(r, f"{name}_found") for r in rows)
        components[name] = {"planted": planted, "found": found,
                            "accuracy": _rate(found, planted)}

    drg_planted = sum(r.drg_impacting_planted for r in rows)
    drg_found = sum(r.drg_impacting_found for r in rows)
    scored_q = [r for r in rows if r.query_correct is not None]
    opportunities = sum(r.add_planted + r.revise_planted + r.delete_planted
                        for r in rows)

    audit_accuracy = _avg([r.audit_accuracy for r in rows])
    verdict = None
    withheld = None
    if opportunities >= cfg.min_opportunities_for_verdict:
        verdict = "PASS" if (audit_accuracy or 0) >= cfg.pass_threshold else "FAIL"
    else:
        withheld = ("indicative only — too few opportunities for a verdict"
                    if opportunities else
                    "restraint measure only — no opportunities yet")

    return {
        "charts": len(rows),
        "audit_accuracy": audit_accuracy,
        "audit_accuracy_basis": "average of chart scores",
        # Split because the headline otherwise blends two different skills and
        # hides which one is weak: finding errors, and leaving correct claims
        # alone. A passive auditor scores 100 on one and 0 on the other.
        "clean_charts": len(clean),
        "opportunity_charts": len(opp),
        "clean_accuracy": _avg([r.audit_accuracy for r in clean]),
        "opportunity_accuracy": _avg([r.audit_accuracy for r in opp]),
        "add": components["add"],
        "revise": components["revise"],
        "delete": components["delete"],
        "component_basis": "pooled findings over plantings",
        # Its own number, never blended into the headline as a weight.
        "drg_planted": drg_planted,
        "drg_found": drg_found,
        "drg_accuracy": _rate(drg_found, drg_planted),
        "query_charts": len(scored_q),
        "query_correct": sum(1 for r in scored_q if r.query_correct),
        "query_accuracy": _rate(sum(1 for r in scored_q if r.query_correct), len(scored_q)),
        "over_calls": sum(r.over_calls for r in rows),
        "charts_with_over_calls": sum(1 for r in rows if r.over_calls),
        # Reported, never scored. "Found 4 of 4, corrected 2" and "found 2 of 4"
        # both come out at 50% and are different coaching conversations.
        "detected_not_corrected": sum(r.detected_not_corrected for r in rows),
        "opportunities": opportunities,
        "pass_fail": verdict,
        "verdict_withheld_reason": withheld,
    }


@router.get("/analytics/overview")
def overview(batch_id: Optional[int] = None, specialty: Optional[str] = None,
             db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    rows = _base_query(db, batch_id, specialty, None).all()
    body = _roll(rows, cfg)
    body["auditors"] = len({r.auditor_name for r in rows})
    body["batches"] = len({r.batch_id for r in rows})
    body["pass_threshold"] = cfg.pass_threshold
    return body


@router.get("/analytics/by-batch")
def by_batch(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    cfg = scoring_config(db)
    rows = _base_query(db, None, specialty, None).all()
    batches = {b.id: b for b in db.query(AuditBatch).all()}

    grouped: dict[int, list] = {}
    for r in rows:
        grouped.setdefault(r.batch_id, []).append(r)

    out = []
    for batch_id, group in grouped.items():
        batch = batches.get(batch_id)
        out.append({
            "batch_id": batch_id,
            "name": batch.name if batch else f"Batch {batch_id}",
            "specialty": batch.specialty.value if batch else None,
            "status": batch.status.value if batch else None,
            "auditors": len({r.auditor_name for r in group}),
            **_roll(group, cfg),
        })
    out.sort(key=lambda x: -(x["batch_id"]))
    return {"batches": out}


@router.get("/analytics/by-auditor")
def by_auditor(batch_id: Optional[int] = None, specialty: Optional[str] = None,
               db: Session = Depends(get_db)):
    """
    One row per auditor, cumulative across everything in scope.

    Component accuracies pool here rather than averaging per-session rates, so
    an auditor who sat one heavy session and one light one is measured on all
    their opportunities rather than on the mean of two percentages.
    """
    cfg = scoring_config(db)
    rows = _base_query(db, batch_id, specialty, None).all()

    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r.auditor_name, []).append(r)

    out = []
    for name, group in grouped.items():
        emp = next((r.emp_id for r in group if r.emp_id), None)
        out.append({
            "auditor_name": name,
            "emp_id": emp,
            "batches": len({r.batch_id for r in group}),
            **_roll(group, cfg),
        })
    out.sort(key=lambda x: (x["audit_accuracy"] is None, x["audit_accuracy"] or 0))
    return {"auditors": out, "pass_threshold": cfg.pass_threshold}


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
    rows = _base_query(db, batch_id, specialty, auditor).all()

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
    }
