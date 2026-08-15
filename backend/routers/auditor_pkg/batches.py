"""
Audit batches and allocation cycles.

Allocation is where the whole design meets: charts are drawn least-seen-first,
a clean quota is taken off the top, each remaining chart resolves to a stored
set or the generator, and every result is materialised and frozen. Nothing
downstream re-derives a claim.
"""

import math
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AnswerKey, AuditAllocationCycle, AuditAssignment, AuditBatch,
    AuditBatchAuditor, AuditResult, AuditSession, AuditSource, BatchStatus,
    Chart,
)
from services.allocation import draw_for_person
from services.audit_observations import load_observations, summarise
from services.audit_allocation import (
    assign_intents, build_assignment, build_corpus, new_token, resolve_quotas,
    resolve_source,
)
from services.audit_mutation import TYPICAL_ERRORS_PER_OPPORTUNITY_CHART
from .shared import (
    chart_pool, get_batch_or_404, mutation_config, parse_specialty,
    require_passphrase, scoring_config, sets_by_chart,
)

router = APIRouter()

ALLOCATION_MODES = {"auto", "guided", "manual"}
MIN_CHARTS_SUGGESTED = 5


def _verdict_reach_note(charts: int, quota_clean: Optional[int],
                        clean_share: int, cfg) -> str:
    """
    Whether this batch can reach a pass/fail verdict, said in the units the
    rule actually uses.

    A verdict needs `min_opportunities_for_verdict` OPPORTUNITIES — individual
    errors introduced — not a number of charts. Clean charts carry none, so a
    chart count alone never answered the question. The old wording named the
    right consequence against the wrong number, and worse, vanished at 5
    charts while still being true.

    Both figures are estimates: the per-chart error budget scales with how many
    codes a chart has and nothing has been drawn yet, so this says "roughly"
    and "around" rather than promising.
    """
    if charts < 1:
        return ""
    # From the intended SHARE, not a rounded count, so the suggested chart
    # count does not wobble as the typed number changes.
    clean_fraction = (quota_clean / charts) if quota_clean is not None \
        else (clean_share / 100)
    clean_fraction = min(max(clean_fraction, 0.0), 0.9)
    per_chart = TYPICAL_ERRORS_PER_OPPORTUNITY_CHART * (1 - clean_fraction)
    if per_chart <= 0:
        return ""

    expect = round(charts * per_chart)
    need = cfg.min_opportunities_for_verdict
    if expect >= need:
        return ""
    reach = max(charts + 1, math.ceil(need / per_chart))
    return (f"{charts} {'chart' if charts == 1 else 'charts'} per auditor yields roughly "
            f"{expect} {'opportunity' if expect == 1 else 'opportunities'}. "
            f"A pass/fail verdict needs {need}, so this batch will report scores "
            f"without one — around {reach} charts would reach it. Scores, "
            f"findings and every analytics figure still work; only the verdict "
            f"is held back.")


class AuditorEntry(BaseModel):
    name: str
    emp_id: str = ""


class BatchCreate(BaseModel):
    name: str
    specialty: str
    categories: list[str] = []
    difficulties: list[str] = []
    charts_per_auditor: int = 5
    auditors: list[AuditorEntry]
    created_by: str
    allocation_mode: str = "guided"
    quota_clean: Optional[int] = None
    quota_manual: Optional[int] = None
    quota_auto: Optional[int] = None
    clean_share: int = 50
    difficulty_tier: Optional[str] = None
    show_results_to_auditor: bool = False


class AllocationRun(BaseModel):
    charts_per_auditor: Optional[int] = None
    run_by: str
    exclude_auditors: list[str] = []
    manual_chart_ids: list[int] = []


@router.post("/batches")
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    specialty = parse_specialty(payload.specialty)
    mode = (payload.allocation_mode or "guided").lower()
    if mode not in ALLOCATION_MODES:
        raise HTTPException(400, f"allocation_mode must be one of {sorted(ALLOCATION_MODES)}")
    if payload.charts_per_auditor < 1:
        raise HTTPException(400, "charts_per_auditor must be at least 1")
    if not 0 <= payload.clean_share <= 100:
        raise HTTPException(400, "clean_share must be between 0 and 100")

    if mode in ("guided", "manual"):
        quotas = [payload.quota_clean, payload.quota_manual, payload.quota_auto]
        if any(q is not None for q in quotas):
            clean, manual, auto = (max(0, q or 0) for q in quotas)
            total = clean + manual + auto
            if total > payload.charts_per_auditor:
                raise HTTPException(
                    400,
                    f"Those add up to {total} charts but each auditor gets "
                    f"{payload.charts_per_auditor}. The clean quota is filled "
                    f"first, so the rest would be silently dropped.")
            # A session of nothing but clean charts measures restraint and
            # nothing else — it cannot report detection at all. The clean-share
            # path already guarantees one opportunity chart by flooring; an
            # explicit quota must not be a way around that.
            if clean >= payload.charts_per_auditor:
                raise HTTPException(
                    400,
                    f"{clean} clean of {payload.charts_per_auditor} leaves nothing "
                    f"to find. Keep at least one chart carrying errors, or the "
                    f"session can only measure whether they left it alone.")

    seen_emp = set()
    auditors, skipped = [], []
    for a in payload.auditors:
        name, emp = a.name.strip(), (a.emp_id or "").strip()
        if not name or not emp or emp in seen_emp:
            skipped.append(f"{name or 'Unnamed'}{f' ({emp})' if emp else ''}")
            continue
        auditors.append((name, emp))
        seen_emp.add(emp)
    if not auditors:
        raise HTTPException(400, "At least one auditor with a valid name and Emp ID is required")

    batch = AuditBatch(
        name=payload.name, specialty=specialty,
        categories=payload.categories, difficulties=payload.difficulties,
        charts_per_auditor=payload.charts_per_auditor,
        allocation_mode=mode,
        quota_clean=payload.quota_clean, quota_manual=payload.quota_manual,
        quota_auto=payload.quota_auto, clean_share=payload.clean_share,
        difficulty_tier=payload.difficulty_tier,
        show_results_to_auditor=payload.show_results_to_auditor,
        created_by=payload.created_by, status=BatchStatus.OPEN,
        notes=[], tags=[],
    )
    db.add(batch)
    db.flush()
    for name, emp in auditors:
        db.add(AuditBatchAuditor(batch_id=batch.id, auditor_name=name, emp_id=emp))
    db.commit()

    warning = None
    if payload.charts_per_auditor < MIN_CHARTS_SUGGESTED:
        # A warning, not a block — a short spot check is legitimate.
        warning = _verdict_reach_note(
            payload.charts_per_auditor, payload.quota_clean,
            payload.clean_share, scoring_config(db)) or None
    return {"batch_id": batch.id, "name": batch.name,
            "skipped_duplicates": skipped, "warning": warning}


@router.get("/batches")
def list_batches(status: Optional[str] = None,
                 search: Optional[str] = None,
                 limit: int = Query(50, le=200),
                 offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)):
    """
    Paged, and counted in SQL.

    This used to load every auditor, assignment and result row in the database
    and tally them in Python — three full table scans to render a list of
    names. It is fine at a dozen batches and quietly fatal at a thousand.
    """
    q = db.query(AuditBatch)
    if search:
        q = q.filter(AuditBatch.name.ilike(f"%{search.strip()}%"))
    # Counts come from the whole filtered set, not the page. Counting loaded
    # rows told a trainer there were no closed batches whenever the closed ones
    # happened to fall past the first page.
    status_counts = dict(q.with_entities(AuditBatch.status, func.count())
                         .group_by(AuditBatch.status).all())
    if status:
        q = q.filter(AuditBatch.status == status)
    total = q.count()
    batches = q.order_by(AuditBatch.id.desc()).limit(limit).offset(offset).all()
    ids = [b.id for b in batches]

    def _counts(model, column):
        if not ids:
            return {}
        rows = (db.query(column, func.count())
                .filter(column.in_(ids)).group_by(column).all())
        return {bid: n for bid, n in rows}

    auditor_counts = _counts(AuditBatchAuditor, AuditBatchAuditor.batch_id)
    assigned_counts = _counts(AuditAssignment, AuditAssignment.batch_id)
    scored_counts = _counts(AuditResult, AuditResult.batch_id)

    now = datetime.utcnow()

    def _days_open(b: AuditBatch):
        """
        How long an open batch has been sitting. The list groups by age and
        flags anything stale, so a batch nobody finished does not simply
        scroll away.
        """
        if not b.created_at or b.status != BatchStatus.OPEN:
            return None
        return (now - b.created_at.replace(tzinfo=None)).days

    return {"batches": [{
        "id": b.id, "name": b.name, "specialty": b.specialty.value,
        "status": b.status.value, "created_by": b.created_by,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "closed_at": b.closed_at.isoformat() if b.closed_at else None,
        "days_open": _days_open(b),
        "charts_per_auditor": b.charts_per_auditor,
        "allocation_mode": b.allocation_mode,
        "auditors": auditor_counts.get(b.id, 0),
        "assigned": assigned_counts.get(b.id, 0),
        "scored": scored_counts.get(b.id, 0),
    } for b in batches],
        "total": total, "limit": limit, "offset": offset,
        "counts": {
            "open": status_counts.get(BatchStatus.OPEN, 0),
            "closed": status_counts.get(BatchStatus.CLOSED, 0),
            "all": sum(status_counts.values()),
        }}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = get_batch_or_404(db, batch_id)
    auditors = (db.query(AuditBatchAuditor)
                .filter(AuditBatchAuditor.batch_id == batch_id).all())
    cycles = (db.query(AuditAllocationCycle)
              .filter(AuditAllocationCycle.batch_id == batch_id)
              .order_by(AuditAllocationCycle.cycle_number).all())
    assignments = (db.query(AuditAssignment, Chart)
                   .join(Chart, Chart.id == AuditAssignment.chart_id)
                   .filter(AuditAssignment.batch_id == batch_id).all())
    result_rows = db.query(AuditResult).filter(AuditResult.batch_id == batch_id).all()
    result_assignment_ids = {r.assignment_id for r in result_rows if r.assignment_id}
    result_legacy = {(r.auditor_name, r.chart_id): r for r in result_rows}
    sessions = (db.query(AuditSession)
                .filter(AuditSession.batch_id == batch_id).all())
    name_counts: dict[str, int] = {}
    for a in auditors:
        name_counts[a.auditor_name] = name_counts.get(a.auditor_name, 0) + 1

    by_auditor: dict[str, list] = {}
    for a, chart in assignments:
        key = _auditor_display(a.auditor_name, a.emp_id,
                               show_emp=name_counts.get(a.auditor_name, 0) > 1)
        scored = a.id in result_assignment_ids or (
            not result_assignment_ids and (a.auditor_name, a.chart_id) in result_legacy)
        by_auditor.setdefault(key, []).append({
            "assignment_id": a.id, "chart_id": a.chart_id,
            "auditor_name": a.auditor_name, "emp_id": a.emp_id,
            "chart_number": chart.chart_number, "category": chart.category,
            "cycle_id": a.cycle_id,
            # Trainer-side vocabulary only. The auditor is never told which
            # type a chart is, before or after — charts recycle, and a labelled
            # clean chart is an answer key if they meet it again.
            "source": a.source.value,
            "planting_count": len(a.ground_truth or []),
            "query_expected": a.query_expected,
            "opened": a.opened_at is not None,
            "scored": scored,
        })

    pending_scoring = sum(1 for a, _c in assignments
                          if a.id not in result_assignment_ids
                          and (result_assignment_ids
                               or (a.auditor_name, a.chart_id) not in result_legacy))
    return {
        "id": batch.id, "name": batch.name, "specialty": batch.specialty.value,
        "status": batch.status.value, "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "closed_at": batch.closed_at.isoformat() if batch.closed_at else None,
        "closed_by": batch.closed_by,
        "charts_per_auditor": batch.charts_per_auditor,
        "allocation_mode": batch.allocation_mode,
        "clean_share": batch.clean_share,
        "quota_clean": batch.quota_clean, "quota_manual": batch.quota_manual,
        "quota_auto": batch.quota_auto,
        "difficulty_tier": batch.difficulty_tier,
        "show_results_to_auditor": bool(batch.show_results_to_auditor),
        "categories": batch.categories or [], "difficulties": batch.difficulties or [],
        "auditors": [{"name": a.auditor_name, "emp_id": a.emp_id} for a in auditors],
        "assignments": by_auditor,
        "pending_scoring": pending_scoring,
        "tokens_by_cycle": _tokens_by_cycle(sessions),
        "allocation_cycles": [{
            "id": c.id, "cycle_number": c.cycle_number,
            "run_at": c.run_at.isoformat() if c.run_at else None,
            "run_by": c.run_by, "charts_allocated": c.charts_allocated,
            "pool_notes": c.pool_notes or [],
        } for c in cycles],
    }


def _tokens_by_cycle(sessions) -> dict:
    out: dict[str, list] = {}
    for s in sessions:
        out.setdefault(str(s.cycle_id), []).append({
            "auditor_name": s.auditor_name, "token": s.token,
            "emp_id": s.emp_id,
            "status": s.status, "session_id": s.id,
        })
    return out


@router.post("/batches/{batch_id}/run-allocation")
def run_allocation(batch_id: int, payload: AllocationRun, db: Session = Depends(get_db)):
    """
    Draw charts, build claims, freeze them, and issue an access code each.

    The order is deliberate: the clean quota comes off the top BEFORE any
    chart is checked for a stored set, so a curated chart is sometimes handed
    over untouched. If clean were a fixed subset of charts, auditors would
    learn which numbers to skim.
    """
    batch = get_batch_or_404(db, batch_id)
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(400, "Audit batch is closed — cannot run allocation")

    all_auditors = (db.query(AuditBatchAuditor)
                    .filter(AuditBatchAuditor.batch_id == batch_id).all())
    if not all_auditors:
        raise HTTPException(400, "No auditors in this batch")
    excluded = {n.strip().lower() for n in payload.exclude_auditors}
    auditors = [a for a in all_auditors
                if _auditor_key(a.auditor_name, a.emp_id).lower() not in excluded
                and a.auditor_name.strip().lower() not in excluded
                and (a.emp_id or "").strip().lower() not in excluded]
    if not auditors:
        raise HTTPException(400, "All auditors are excluded")

    want = payload.charts_per_auditor or batch.charts_per_auditor
    if want < 1:
        raise HTTPException(400, "charts_per_auditor must be at least 1")

    pool = chart_pool(db, batch)
    if payload.manual_chart_ids:
        allowed = set(payload.manual_chart_ids)
        picked = [c for c in pool if c.id in allowed]
        # A chart the trainer picked that is not in the pool was excluded for a
        # reason — retired, wrong specialty, or no answer key. Saying so beats
        # allocating a shorter list than they asked for without comment.
        missing = allowed - {c.id for c in picked}
        if missing:
            names = {c.id: c.chart_number for c in db.query(Chart).filter(
                Chart.id.in_(missing)).all()}
            notes_prefix = ", ".join(names.get(i, str(i)) for i in sorted(missing))
            raise HTTPException(
                400,
                f"These charts cannot be audited in this batch: {notes_prefix}. "
                f"A chart must be active, in this specialty, and have an answer "
                f"key before errors can be introduced into it.")
        pool = picked
    if not pool:
        raise HTTPException(
            400, "No charts match this batch's filters that also have an answer key")

    existing = (db.query(AuditAssignment)
                .filter(AuditAssignment.batch_id == batch_id).all())
    seen_counts: dict[str, dict] = {}
    prior_sets: dict[str, list] = {}
    by_cycle: dict[tuple, set] = {}
    # How many cycles each chart has already been handed out in. Drives which
    # authored version the next encounter produces — see resolve_source.
    chart_uses: dict[int, set] = {}
    for a in existing:
        key = _auditor_key(a.auditor_name, a.emp_id)
        chart_uses.setdefault(a.chart_id, set()).add(a.cycle_id)
        seen_counts.setdefault(key, {})
        seen_counts[key][a.chart_id] = seen_counts[key].get(a.chart_id, 0) + 1
        by_cycle.setdefault((key, a.cycle_id), set()).add(a.chart_id)
    for (key, _cycle), ids in by_cycle.items():
        prior_sets.setdefault(key, []).append(ids)

    last = (db.query(AuditAllocationCycle)
            .filter(AuditAllocationCycle.batch_id == batch_id)
            .order_by(AuditAllocationCycle.cycle_number.desc()).first())
    cycle_number = (last.cycle_number + 1) if last else 1
    cycle = AuditAllocationCycle(
        batch_id=batch_id, cycle_number=cycle_number, run_by=payload.run_by,
        charts_allocated=0, pool_notes=[])
    db.add(cycle)
    db.flush()

    keys = {k.chart_id: k for k in db.query(AnswerKey).filter(
        AnswerKey.chart_id.in_([c.id for c in pool])).all()}
    corpus = build_corpus(db.query(AnswerKey).filter(
        AnswerKey.specialty == batch.specialty).all())
    mcfg = mutation_config(db)
    all_sets = sets_by_chart(db, [c.id for c in pool])

    # What real coders actually got wrong on these charts, diffed against the
    # CURRENT answer key so a key that has since been corrected cannot
    # resurrect a stale "error". Harvested once per cycle rather than per
    # auditor — the observations are a property of the chart.
    observed = {c.id: load_observations(db, c.id, keys.get(c.id))
                for c in pool if keys.get(c.id)}

    total, notes, issued = 0, [], []
    for auditor in auditors:
        auditor_key = _auditor_key(auditor.auditor_name, auditor.emp_id)
        counts = seen_counts.get(auditor_key, {})
        drawn, note = draw_for_person(
            pool, counts, prior_sets.get(auditor_key, []), want)
        if note.get("message"):
            notes.append(f"{_auditor_display(auditor.auditor_name, auditor.emp_id)}: {note['message']}")
        if not drawn:
            continue

        quotas = resolve_quotas(
            batch.allocation_mode, len(drawn), batch.clean_share,
            batch.quota_clean, batch.quota_manual, batch.quota_auto)
        # Which POSITIONS get which treatment is random; how many is not. The
        # quota guarantees the mix a coin flip would only approximate — and
        # that now covers the authored/generated split, not just clean.
        rng = random.Random(f"{batch_id}:{cycle_number}:{auditor_key}")
        intents, quota_notes = assign_intents(drawn, quotas, all_sets, rng)
        for msg in quota_notes:
            notes.append(f"{_auditor_display(auditor.auditor_name, auditor.emp_id)}: {msg}")

        for idx, chart in enumerate(drawn):
            # Version follows the chart's own use count, so it is the same for
            # every auditor in this cycle and different from last encounter.
            intent = intents[idx]
            source, key_set = resolve_source(
                chart.id, intent == "clean",
                all_sets if intent != "auto" else {},
                len(chart_uses.get(chart.id, ())))
            built = build_assignment(
                chart, keys.get(chart.id), source, key_set,
                cycle_number=cycle_number, cfg=mcfg, corpus=corpus,
                tier=batch.difficulty_tier,
                observations=observed.get(chart.id))
            db.add(AuditAssignment(
                batch_id=batch_id, cycle_id=cycle.id,
                auditor_name=auditor.auditor_name, emp_id=auditor.emp_id,
                specialty=chart.specialty,
                **built))
            total += 1

        session = AuditSession(
            batch_id=batch_id, cycle_id=cycle.id,
            auditor_name=auditor.auditor_name, emp_id=auditor.emp_id,
            specialty=batch.specialty, token=new_token(),
            chart_ids=[c.id for c in drawn], status="in_progress",
            show_results_to_auditor=bool(batch.show_results_to_auditor))
        db.add(session)
        issued.append({"auditor_name": auditor.auditor_name, "emp_id": auditor.emp_id,
                       "token": session.token,
                       "charts": len(drawn)})

    cycle.charts_allocated = total
    cycle.pool_notes = notes
    db.commit()
    return {"cycle_id": cycle.id, "cycle_number": cycle_number,
            "charts_allocated": total, "pool_notes": notes, "access_codes": issued}


@router.get("/batches/{batch_id}/plantings")
def review_plantings(batch_id: int, auditor: Optional[str] = None,
                     limit: int = Query(100, le=500),
                     offset: int = Query(0, ge=0),
                     include_claim: bool = False,
                     db: Session = Depends(get_db)):
    """
    What was planted, for the trainer, after allocation has run.

    This is the QA step that replaced a mandatory pre-release preview: see
    everything, and regenerate anything that looks wrong before the auditor
    opens it.
    """
    get_batch_or_404(db, batch_id)
    q = (db.query(AuditAssignment, Chart)
         .join(Chart, Chart.id == AuditAssignment.chart_id)
         .filter(AuditAssignment.batch_id == batch_id))
    if auditor:
        key_emp, key_name = _split_auditor_key(auditor)
        if key_emp:
            q = q.filter(AuditAssignment.emp_id == key_emp)
        elif key_name:
            q = q.filter(or_(AuditAssignment.emp_id == key_name,
                             AuditAssignment.auditor_name == key_name))
    total = q.count()
    rows = (q.order_by(AuditAssignment.auditor_name, Chart.chart_number)
            .limit(limit).offset(offset).all())
    # The claim is the heaviest thing on the row and the screen does not render
    # it — a batch of 500 assignments was shipping 500 full claims to draw a
    # list of summaries.
    return {"total": total, "limit": limit, "offset": offset,
            "plantings": [{
        "assignment_id": a.id, "auditor_name": a.auditor_name, "emp_id": a.emp_id,
        "chart_id": a.chart_id, "chart_number": c.chart_number,
        "source": a.source.value, "set_id": a.set_id, "seed": a.seed,
        "query_expected": a.query_expected,
        "opened": a.opened_at is not None,
        "locked": a.opened_at is not None,
        "ground_truth": a.ground_truth or [],
        **({"claim": a.claim or {}} if include_claim else {}),
    } for a, c in rows]}


class RegeneratePayload(BaseModel):
    run_by: str = "Trainer"


@router.post("/assignments/{assignment_id}/regenerate")
def regenerate_assignment(assignment_id: int, payload: RegeneratePayload,
                          db: Session = Depends(get_db)):
    """
    Reroll one assignment's plantings — the escape hatch for a claim that
    looks wrong.

    Allowed only until the auditor opens it. After that the claim is what they
    saw, and changing it would rewrite the question after the answer.
    """
    a = db.query(AuditAssignment).filter(AuditAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, "Assignment not found")
    if a.opened_at is not None:
        raise HTTPException(
            409, "The auditor has already opened this chart — its claim is now the record")
    batch = get_batch_or_404(db, a.batch_id)
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(409, "This audit batch is closed")

    chart = db.query(Chart).filter(Chart.id == a.chart_id).first()
    key = db.query(AnswerKey).filter(AnswerKey.chart_id == a.chart_id).first()
    if not key:
        raise HTTPException(400, "This chart has no answer key")

    corpus = build_corpus(db.query(AnswerKey).filter(
        AnswerKey.specialty == batch.specialty).all())
    # A different seed, or the reroll returns exactly what it replaced.
    a.seed = (a.seed or 0) + 7919
    from services.audit_mutation import generate
    claim, truth = generate(key, chart.specialty, seed=a.seed,
                            cfg=mutation_config(db), corpus=corpus,
                            tier=batch.difficulty_tier)
    a.claim, a.ground_truth = claim, truth
    a.source = AuditSource.AUTO
    a.set_id = None
    db.commit()
    return {"regenerated": True, "assignment_id": a.id,
            "planting_count": len(truth), "seed": a.seed}


@router.get("/batches/{batch_id}/export")
def export_batch(batch_id: int, db: Session = Depends(get_db)):
    """Per-chart scores and the findings behind them, as Excel."""
    import io
    from fastapi.responses import StreamingResponse
    from services.audit_export import export_batch_results
    from services.audit_scoring import score_session
    from services.download_headers import content_disposition
    from routers.auditor_pkg.sessions import _score_from_row, _session_summary
    from .shared import scoring_config

    batch = get_batch_or_404(db, batch_id)
    rows = (db.query(AuditResult, Chart)
            .join(Chart, Chart.id == AuditResult.chart_id)
            .filter(AuditResult.batch_id == batch_id)
            .order_by(AuditResult.auditor_name, Chart.chart_number).all())

    charts = [{
        "auditor_name": r.auditor_name, "emp_id": r.emp_id,
        "chart_number": c.chart_number, "is_clean": r.is_clean,
        "audit_accuracy": r.audit_accuracy,
        "add_found": r.add_found, "add_planted": r.add_planted,
        "add_accuracy": r.add_accuracy,
        "revise_found": r.revise_found, "revise_planted": r.revise_planted,
        "revise_accuracy": r.revise_accuracy,
        "delete_found": r.delete_found, "delete_planted": r.delete_planted,
        "delete_accuracy": r.delete_accuracy,
        "drg_impacting_found": r.drg_impacting_found,
        "drg_impacting_planted": r.drg_impacting_planted,
        "over_calls": r.over_calls, "over_call_tier": r.over_call_tier,
        "over_call_deduction": r.over_call_deduction,
        "query_expected": r.query_expected, "query_flagged": r.query_flagged,
        "query_correct": r.query_correct,
        "detected_not_corrected": r.detected_not_corrected,
        "outcomes": r.feedback or [],
    } for r, c in rows]

    summary = _session_summary(score_session(
        [_score_from_row(r) for r, _c in rows], scoring_config(db)))
    data = export_batch_results(batch.name, charts, summary)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition(f"{batch.name}_Audit_Results.xlsx",
                                    "Audit_Results.xlsx"))


@router.get("/batches/{batch_id}/report.pdf")
def batch_report_pdf(batch_id: int, db: Session = Depends(get_db)):
    """Audit batch performance report, as PDF."""
    import io
    from fastapi.responses import StreamingResponse
    from services.download_headers import content_disposition
    from services.pdf_report_service import generate_audit_batch_report_pdf
    from routers.auditor_pkg.analytics import (
        by_auditor, detection_patterns, overview,
    )

    batch = get_batch_or_404(db, batch_id)
    summary = overview(batch_id=batch_id, db=db)
    if not summary.get("charts"):
        raise HTTPException(status_code=404, detail="No scored audit results yet for this batch")
    data = {
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "specialty": batch.specialty.value,
            "status": batch.status.value,
        },
        "overview": summary,
        "auditors": by_auditor(batch_id=batch_id, limit=500, db=db)["auditors"],
        "detection": detection_patterns(batch_id=batch_id, scan_limit=20000, db=db),
    }
    pdf_bytes = generate_audit_batch_report_pdf(data)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(f"{batch.name}_Audit_Batch_Report.pdf",
                                    "Audit_Batch_Report.pdf"))


class BatchClose(BaseModel):
    closed_by: str


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, payload: BatchClose, db: Session = Depends(get_db)):
    batch = get_batch_or_404(db, batch_id)
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(400, "Already closed")
    result_rows = db.query(AuditResult).filter(AuditResult.batch_id == batch_id).all()
    scored_assignment_ids = {r.assignment_id for r in result_rows if r.assignment_id}
    scored_legacy = {(r.auditor_name, r.chart_id) for r in result_rows}
    outstanding = [a for a in db.query(AuditAssignment).filter(
        AuditAssignment.batch_id == batch_id).all()
        if a.id not in scored_assignment_ids
        and (scored_assignment_ids
             or (a.auditor_name, a.chart_id) not in scored_legacy)]
    if outstanding:
        raise HTTPException(
            400, f"{len(outstanding)} assigned chart(s) have not been submitted yet")
    batch.status = BatchStatus.CLOSED
    batch.closed_at = datetime.utcnow()
    batch.closed_by = payload.closed_by
    db.commit()
    return {"closed": True, "batch_id": batch_id}


class BatchReopen(BaseModel):
    reopened_by: str
    passphrase: str


@router.post("/batches/{batch_id}/reopen")
def reopen_batch(batch_id: int, payload: BatchReopen, db: Session = Depends(get_db)):
    require_passphrase(payload.passphrase, "reopen an audit batch")
    batch = get_batch_or_404(db, batch_id)
    batch.status = BatchStatus.OPEN
    batch.closed_at = None
    batch.closed_by = None
    db.commit()
    return {"reopened": True, "batch_id": batch_id}


def _auditor_key(name: str, emp_id: Optional[str]) -> str:
    emp = (emp_id or "").strip()
    return emp or name.strip()


def _auditor_display(name: str, emp_id: Optional[str], show_emp: bool = True) -> str:
    emp = (emp_id or "").strip()
    return f"{name} ({emp})" if emp and show_emp else name


def _split_auditor_key(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not raw:
        return None, None
    if "||" in raw:
        emp, name = raw.split("||", 1)
        return emp or None, name or None
    text = raw.strip()
    return None, text or None
