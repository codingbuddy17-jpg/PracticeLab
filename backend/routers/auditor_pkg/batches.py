"""
Audit batches and allocation cycles.

Allocation is where the whole design meets: charts are drawn least-seen-first,
a clean quota is taken off the top, each remaining chart resolves to a stored
set or the generator, and every result is materialised and frozen. Nothing
downstream re-derives a claim.
"""

import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
    build_assignment, build_corpus, new_token, resolve_quotas, resolve_source,
)
from .shared import (
    chart_pool, get_batch_or_404, mutation_config, parse_specialty,
    require_passphrase, sets_by_chart,
)

router = APIRouter()

ALLOCATION_MODES = {"auto", "guided", "manual"}
MIN_CHARTS_SUGGESTED = 5


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

    seen_names, seen_emp = set(), set()
    auditors, skipped = [], []
    for a in payload.auditors:
        name, emp = a.name.strip(), (a.emp_id or "").strip()
        if not name or name in seen_names or (emp and emp in seen_emp):
            if name:
                skipped.append(name)
            continue
        auditors.append((name, emp))
        seen_names.add(name)
        if emp:
            seen_emp.add(emp)
    if not auditors:
        raise HTTPException(400, "At least one auditor with a valid name is required")

    batch = AuditBatch(
        name=payload.name, specialty=specialty,
        categories=payload.categories, difficulties=payload.difficulties,
        charts_per_auditor=payload.charts_per_auditor,
        allocation_mode=mode,
        quota_clean=payload.quota_clean, quota_manual=payload.quota_manual,
        quota_auto=payload.quota_auto, clean_share=payload.clean_share,
        difficulty_tier=payload.difficulty_tier,
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
        # A warning, not a block — a two-chart spot check is legitimate, it
        # just cannot carry a verdict.
        warning = (f"{payload.charts_per_auditor} charts per auditor is below the "
                   f"suggested {MIN_CHARTS_SUGGESTED}; a session this short will "
                   f"report a score but withhold a pass/fail verdict.")
    return {"batch_id": batch.id, "name": batch.name,
            "skipped_duplicates": skipped, "warning": warning}


@router.get("/batches")
def list_batches(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(AuditBatch)
    if status:
        q = q.filter(AuditBatch.status == status)
    batches = q.order_by(AuditBatch.id.desc()).all()
    ids = [b.id for b in batches]

    auditor_counts, assigned_counts, scored_counts = {}, {}, {}
    if ids:
        for bid, in db.query(AuditBatchAuditor.batch_id).filter(
                AuditBatchAuditor.batch_id.in_(ids)).all():
            auditor_counts[bid] = auditor_counts.get(bid, 0) + 1
        for bid, in db.query(AuditAssignment.batch_id).filter(
                AuditAssignment.batch_id.in_(ids)).all():
            assigned_counts[bid] = assigned_counts.get(bid, 0) + 1
        for bid, in db.query(AuditResult.batch_id).filter(
                AuditResult.batch_id.in_(ids)).all():
            scored_counts[bid] = scored_counts.get(bid, 0) + 1

    return {"batches": [{
        "id": b.id, "name": b.name, "specialty": b.specialty.value,
        "status": b.status.value, "created_by": b.created_by,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "charts_per_auditor": b.charts_per_auditor,
        "allocation_mode": b.allocation_mode,
        "auditors": auditor_counts.get(b.id, 0),
        "assigned": assigned_counts.get(b.id, 0),
        "scored": scored_counts.get(b.id, 0),
    } for b in batches]}


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
    results = {(r.auditor_name, r.chart_id): r
               for r in db.query(AuditResult).filter(AuditResult.batch_id == batch_id).all()}
    sessions = (db.query(AuditSession)
                .filter(AuditSession.batch_id == batch_id).all())

    by_auditor: dict[str, list] = {}
    for a, chart in assignments:
        by_auditor.setdefault(a.auditor_name, []).append({
            "assignment_id": a.id, "chart_id": a.chart_id,
            "chart_number": chart.chart_number, "category": chart.category,
            "cycle_id": a.cycle_id,
            # Trainer-side vocabulary only. The auditor is never told which
            # type a chart is, before or after — charts recycle, and a labelled
            # clean chart is an answer key if they meet it again.
            "source": a.source.value,
            "planting_count": len(a.ground_truth or []),
            "query_expected": a.query_expected,
            "opened": a.opened_at is not None,
            "scored": (a.auditor_name, a.chart_id) in results,
        })

    pending_scoring = sum(1 for a, _c in assignments
                          if (a.auditor_name, a.chart_id) not in results)
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
    auditors = [a for a in all_auditors if a.auditor_name.strip().lower() not in excluded]
    if not auditors:
        raise HTTPException(400, "All auditors are excluded")

    want = payload.charts_per_auditor or batch.charts_per_auditor
    if want < 1:
        raise HTTPException(400, "charts_per_auditor must be at least 1")

    pool = chart_pool(db, batch)
    if payload.manual_chart_ids:
        allowed = set(payload.manual_chart_ids)
        pool = [c for c in pool if c.id in allowed]
    if not pool:
        raise HTTPException(
            400, "No charts match this batch's filters that also have an answer key")

    existing = (db.query(AuditAssignment)
                .filter(AuditAssignment.batch_id == batch_id).all())
    seen_counts: dict[str, dict] = {}
    prior_sets: dict[str, list] = {}
    seen_set_ids: dict[str, set] = {}
    by_cycle: dict[tuple, set] = {}
    for a in existing:
        seen_counts.setdefault(a.auditor_name, {})
        seen_counts[a.auditor_name][a.chart_id] = \
            seen_counts[a.auditor_name].get(a.chart_id, 0) + 1
        if a.set_id:
            seen_set_ids.setdefault(a.auditor_name, set()).add(a.set_id)
        by_cycle.setdefault((a.auditor_name, a.cycle_id), set()).add(a.chart_id)
    for (name, _cycle), ids in by_cycle.items():
        prior_sets.setdefault(name, []).append(ids)

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
        counts = seen_counts.get(auditor.auditor_name, {})
        drawn, note = draw_for_person(
            pool, counts, prior_sets.get(auditor.auditor_name, []), want)
        if note.get("message"):
            notes.append(f"{auditor.auditor_name}: {note['message']}")
        if not drawn:
            continue

        quotas = resolve_quotas(
            batch.allocation_mode, len(drawn), batch.clean_share,
            batch.quota_clean, batch.quota_manual, batch.quota_auto)
        # Which POSITIONS come up clean is random; how many is not. The quota
        # guarantees the mix a coin flip would only approximate.
        rng = random.Random(f"{batch_id}:{cycle_number}:{auditor.auditor_name}")
        positions = list(range(len(drawn)))
        rng.shuffle(positions)
        clean_positions = set(positions[:min(quotas.clean, len(drawn))])

        seen_sets = seen_set_ids.get(auditor.auditor_name, set())
        for idx, chart in enumerate(drawn):
            source, key_set = resolve_source(
                chart.id, idx in clean_positions, all_sets, seen_sets, rng)
            built = build_assignment(
                chart, keys.get(chart.id), source, key_set,
                cycle_number=cycle_number, cfg=mcfg, corpus=corpus,
                tier=batch.difficulty_tier,
                observations=observed.get(chart.id))
            if key_set is not None:
                seen_sets.add(key_set.id)
            db.add(AuditAssignment(
                batch_id=batch_id, cycle_id=cycle.id,
                auditor_name=auditor.auditor_name, specialty=chart.specialty,
                **built))
            total += 1

        session = AuditSession(
            batch_id=batch_id, cycle_id=cycle.id,
            auditor_name=auditor.auditor_name, emp_id=auditor.emp_id,
            specialty=batch.specialty, token=new_token(),
            chart_ids=[c.id for c in drawn], status="in_progress")
        db.add(session)
        issued.append({"auditor_name": auditor.auditor_name, "token": session.token,
                       "charts": len(drawn)})

    cycle.charts_allocated = total
    cycle.pool_notes = notes
    db.commit()
    return {"cycle_id": cycle.id, "cycle_number": cycle_number,
            "charts_allocated": total, "pool_notes": notes, "access_codes": issued}


@router.get("/batches/{batch_id}/plantings")
def review_plantings(batch_id: int, auditor: Optional[str] = None,
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
        q = q.filter(AuditAssignment.auditor_name == auditor)
    rows = q.order_by(AuditAssignment.auditor_name, Chart.chart_number).all()
    return {"plantings": [{
        "assignment_id": a.id, "auditor_name": a.auditor_name,
        "chart_id": a.chart_id, "chart_number": c.chart_number,
        "source": a.source.value, "set_id": a.set_id, "seed": a.seed,
        "query_expected": a.query_expected,
        "opened": a.opened_at is not None,
        "locked": a.opened_at is not None,
        "ground_truth": a.ground_truth or [],
        "claim": a.claim or {},
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


class BatchClose(BaseModel):
    closed_by: str


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, payload: BatchClose, db: Session = Depends(get_db)):
    batch = get_batch_or_404(db, batch_id)
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(400, "Already closed")
    scored = {(r.auditor_name, r.chart_id) for r in
              db.query(AuditResult).filter(AuditResult.batch_id == batch_id).all()}
    outstanding = [a for a in db.query(AuditAssignment).filter(
        AuditAssignment.batch_id == batch_id).all()
        if (a.auditor_name, a.chart_id) not in scored]
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
