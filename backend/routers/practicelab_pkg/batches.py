"""Batch CRUD, allocation cycles, and Excel export endpoints."""
import io
import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pydantic import BaseModel
from database import get_db
from models import (
    Chart, ChartStatus, Specialty, Difficulty, AnswerKey,
    Batch, BatchCoder, BatchChart, BatchStatus, BatchAllocationCycle,
    GradingResult, SubmissionStatus,
)
from sqlalchemy import text as _text
from services.randomisation_stats import compute_randomisation_stats, parse_stats
from .shared import MASTER_PASSPHRASE, _is_ip, _is_ed, _uses_dpo

router = APIRouter()

OPEN_BATCH_SOFT_LIMIT = 3


class CoderEntry(BaseModel):
    name: str
    emp_id: str


class BatchCreate(BaseModel):
    name: str
    specialty: str
    categories: list[str] = []
    difficulties: list[str] = []
    charts_per_coder: int = 5
    coders: list[CoderEntry]
    created_by: str
    use_weighted: bool = True
    use_dpo: bool = False
    is_direct_assignment: bool = False


class AllocationRun(BaseModel):
    charts_per_coder: Optional[int] = None
    manual_chart_ids: list[int] = []
    run_by: str
    notes: Optional[str] = None
    exclude_coders: list[str] = []


class BatchClose(BaseModel):
    closed_by: str


class BatchForceClose(BaseModel):
    closed_by: str
    passphrase: str
    reason: str


class BatchNoteAdd(BaseModel):
    text: str
    author: str


@router.post("/batches")
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    """Create an open batch with coders. Chart allocation is a separate step (run-allocation)."""
    try:
        specialty = Specialty(payload.specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid specialty: {payload.specialty}")

    use_weighted = payload.use_weighted
    use_dpo = payload.use_dpo
    if not _uses_dpo(specialty):
        use_weighted = True
        use_dpo = False

    if not use_weighted and not use_dpo:
        raise HTTPException(status_code=400, detail="At least one scoring method must be selected")

    if not payload.coders:
        raise HTTPException(status_code=400, detail="At least one coder is required")

    seen_names: set[str] = set()
    seen_emp_ids: set[str] = set()
    unique_coders, skipped_duplicates = [], []
    for coder in payload.coders:
        name = coder.name.strip()
        emp_id = (coder.emp_id or "").strip()
        if not name or name in seen_names or (emp_id and emp_id in seen_emp_ids):
            if name:
                skipped_duplicates.append(name)
            continue
        unique_coders.append((name, emp_id))
        seen_names.add(name)
        if emp_id:
            seen_emp_ids.add(emp_id)

    if not unique_coders:
        raise HTTPException(status_code=400, detail="At least one coder with a valid name is required")

    warning = None
    if not payload.is_direct_assignment:
        open_count = (db.query(Batch)
                      .filter(Batch.created_by == payload.created_by, Batch.status == BatchStatus.OPEN,
                              Batch.is_direct_assignment == False)
                      .count())
        if open_count >= OPEN_BATCH_SOFT_LIMIT:
            warning = f"You already have {open_count} open batch(es). Consider closing completed ones."

    batch = Batch(
        name=payload.name,
        specialty=specialty,
        categories=payload.categories,
        difficulties=payload.difficulties,
        charts_per_coder=payload.charts_per_coder,
        created_by=payload.created_by,
        status=BatchStatus.OPEN,
        use_weighted=use_weighted,
        use_dpo=use_dpo,
        is_direct_assignment=payload.is_direct_assignment,
        notes=[],
        tags=[],
    )
    db.add(batch)
    db.flush()

    for name, emp_id in unique_coders:
        db.add(BatchCoder(batch_id=batch.id, coder_name=name, emp_id=emp_id))

    db.commit()
    return {"batch_id": batch.id, "name": batch.name, "warning": warning, "skipped_duplicates": skipped_duplicates}


class AddCoders(BaseModel):
    coders: list[CoderEntry]


@router.post("/batches/{batch_id}/coders")
def add_coders_to_batch(batch_id: int, payload: AddCoders, db: Session = Depends(get_db)):
    """Add one or more coders to an open batch between allocation cycles."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Cannot add coders to a closed batch")

    existing_names = {c.coder_name for c in batch.coders}
    existing_emp_ids = {c.emp_id for c in batch.coders if c.emp_id}
    added, skipped = [], []
    for coder in payload.coders:
        name = coder.name.strip()
        emp_id = (coder.emp_id or "").strip()
        if not name:
            continue
        if name in existing_names or (emp_id and emp_id in existing_emp_ids):
            skipped.append(name)
        else:
            db.add(BatchCoder(batch_id=batch_id, coder_name=name, emp_id=emp_id))
            added.append(name)
            existing_names.add(name)  # prevent duplicates within same request
            if emp_id:
                existing_emp_ids.add(emp_id)

    db.commit()
    return {"added": added, "skipped_duplicates": skipped}


def _draw_for_coder(pool, seen_counts: dict, prior_sets: list, want: int):
    """
    Pick this coder's charts for one cycle.

    Exhaustion is per COder. Alice having seen everything says nothing about
    Bob, so each coder is drawn against their own history and one running dry
    never holds up anyone else.

    Charts are grouped by how many times THIS coder has already had them and
    taken from the least-seen group first, shuffled within each group. That
    gives the guarantee that matters — nothing repeats while anything unseen
    remains — and then, once the pool really is exhausted, keeps going instead
    of stopping: a second round is drawn from the once-seen charts, a third
    from the twice-seen, and so on, so repetition stays as even and as far
    apart as the pool allows.

    A recycled round also avoids reproducing a set the coder has already sat,
    where the pool leaves any alternative — the same charts in the same company
    is the case where a coder is most likely to be recalling rather than coding.

    Returns (charts, note) where note describes the state of their pool.
    """
    if not pool:
        return [], {"state": "empty", "message": "no charts match the pool filters",
                    "unseen_left": 0, "round": 0}

    tiers: dict[int, list] = {}
    for chart in pool:
        tiers.setdefault(seen_counts.get(chart.id, 0), []).append(chart)
    for group in tiers.values():
        random.shuffle(group)

    unseen = len(tiers.get(0, []))

    def _take():
        out = []
        for level in sorted(tiers):
            if len(out) >= want:
                break
            out.extend(tiers[level][: want - len(out)])
        return out

    assigned = _take()

    # Only a fully recycled draw can repeat a previous set; reshuffle a few
    # times before accepting one. Bounded, because a pool of exactly `want`
    # charts has no alternative to offer and must not spin.
    if assigned and unseen == 0 and prior_sets:
        for _ in range(8):
            if {c.id for c in assigned} not in prior_sets:
                break
            for group in tiers.values():
                random.shuffle(group)
            assigned = _take()

    round_no = min(seen_counts.get(c.id, 0) for c in assigned) + 1 if assigned else 0

    if unseen == 0:
        message = (f"every chart in the pool has been sat — recycling for round {round_no}"
                   if len(pool) > want else
                   f"pool is only {len(pool)} chart(s); the same set repeats each cycle")
        state = "recycling"
    elif unseen < want:
        message = (f"only {unseen} unseen chart(s) left — this cycle repeats "
                   f"{want - unseen} of them")
        state = "nearly_exhausted"
    elif unseen <= want * 2:
        message = f"{unseen} unseen chart(s) left — enough for about "\
                  f"{unseen // want} more cycle(s)"
        state = "running_low"
    else:
        message = ""
        state = "healthy"

    return assigned, {"state": state, "message": message,
                      "unseen_left": unseen, "round": round_no}


@router.post("/batches/{batch_id}/run-allocation")
def run_allocation(batch_id: int, payload: AllocationRun, db: Session = Depends(get_db)):
    """Run a new allocation cycle for an open batch. Excludes charts already assigned in prior cycles."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.OPEN:
        raise HTTPException(status_code=400, detail="Batch is closed — cannot run allocation")

    all_coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    if not all_coders:
        raise HTTPException(status_code=400, detail="No coders in this batch")
    excluded = {n.strip().lower() for n in payload.exclude_coders}
    coders = [c for c in all_coders if c.coder_name.strip().lower() not in excluded]
    if not coders:
        raise HTTPException(status_code=400, detail="All coders are excluded — uncheck at least one coder")

    charts_per_coder = payload.charts_per_coder or batch.charts_per_coder
    if charts_per_coder < 1:
        raise HTTPException(status_code=400, detail="charts_per_coder must be at least 1")

    specialty = batch.specialty

    existing = db.query(BatchChart).filter(BatchChart.batch_id == batch_id).all()
    # How many times each coder has had each chart, and which sets they were
    # given in which cycle. Counts drive the draw; the sets stop a recycled
    # round handing back an identical selection to one they have already sat.
    seen_count: dict[str, dict] = {}
    prior_sets: dict[str, list] = {}
    _by_cycle: dict[tuple, set] = {}
    for a in existing:
        seen_count.setdefault(a.coder_name, {})
        seen_count[a.coder_name][a.chart_id] = seen_count[a.coder_name].get(a.chart_id, 0) + 1
        _by_cycle.setdefault((a.coder_name, a.cycle_id), set()).add(a.chart_id)
    for (cname, _cyc), chart_set in _by_cycle.items():
        prior_sets.setdefault(cname, []).append(chart_set)

    if payload.manual_chart_ids:
        pool = (db.query(Chart)
                .filter(Chart.id.in_(payload.manual_chart_ids),
                        Chart.status == ChartStatus.ACTIVE,
                        Chart.specialty == specialty)
                .all())
        if not pool:
            raise HTTPException(status_code=400, detail="None of the selected charts are active or match this batch's specialty.")
    else:
        q = (db.query(Chart)
             .filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == specialty))

        if batch.categories:
            q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in batch.categories]))

        if batch.difficulties:
            diffs = []
            for d in batch.difficulties:
                try:
                    diffs.append(Difficulty(d))
                except ValueError:
                    pass
            if diffs:
                q = q.filter(Chart.difficulty.in_(diffs))

        pool = q.all()

    if not pool:
        raise HTTPException(status_code=400, detail="No active charts match the batch pool filters.")

    cycle_number = len(batch.allocation_cycles) + 1
    cycle = BatchAllocationCycle(
        batch_id=batch_id,
        cycle_number=cycle_number,
        run_by=payload.run_by,
        charts_per_coder=charts_per_coder,
        notes=payload.notes,
    )
    db.add(cycle)
    db.flush()

    assigned_counts = {}
    pool_warnings = []
    coder_chart_sets: dict[str, set] = {}   # for randomisation stats

    coder_notes: dict[str, dict] = {}

    for coder in coders:
        counts = seen_count.get(coder.coder_name, {})
        assigned, note = _draw_for_coder(
            pool, counts, prior_sets.get(coder.coder_name, []), charts_per_coder)
        coder_notes[coder.coder_name] = note
        if note["message"]:
            pool_warnings.append(f"{coder.coder_name}: {note['message']}")
        if not assigned:
            continue

        for chart in assigned:
            db.add(BatchChart(
                batch_id=batch_id,
                cycle_id=cycle.id,
                coder_name=coder.coder_name,
                chart_id=chart.id,
                submission_status=SubmissionStatus.PENDING,
            ))

        assigned_counts[coder.coder_name] = len(assigned)
        coder_chart_sets[coder.coder_name] = {c.id for c in assigned}

    # Compute and persist randomisation stats for this cycle
    rand_stats = compute_randomisation_stats(coder_chart_sets, len(pool))
    cycle.randomisation_stats = rand_stats
    # Persisted, not just returned — the toasts that carried these vanish after
    # a few seconds, leaving a short-allocated cycle indistinguishable from a
    # clean one the next time anyone looks at the batch.
    cycle.warnings = pool_warnings or None
    # Persisted with the cycle so "Alice is one cycle from recycling" is still
    # readable next month, rather than living only in a toast.
    cycle.coder_pool_notes = coder_notes or None

    db.commit()
    return {
        "cycle_id": cycle.id,
        "cycle_number": cycle_number,
        "assigned": assigned_counts,
        "warnings": pool_warnings,
        "coder_pool_notes": coder_notes,
        "randomisation_stats": rand_stats,
    }


class BatchReopen(BaseModel):
    reopened_by: str
    passphrase: str
    reason: str = ""


@router.post("/batches/{batch_id}/reopen")
def reopen_batch(batch_id: int, payload: BatchReopen, db: Session = Depends(get_db)):
    """
    Reopen a closed batch.

    Closed batches are frozen — every path that mutates a graded result refuses
    them. force-close exists to close a batch with work outstanding, so without
    a way back that work would be stranded permanently. Gated on the master
    passphrase because reopening makes the record editable again.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status != BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is not closed")
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    if not payload.reopened_by.strip():
        raise HTTPException(status_code=400, detail="reopened_by is required")

    batch.status = BatchStatus.OPEN
    batch.closed_at = None
    batch.closed_by = None
    batch.force_closed = False

    note = f"Reopened by {payload.reopened_by}"
    if payload.reason.strip():
        note += f" — {payload.reason.strip()}"
    notes = list(batch.notes or [])
    notes.append({"text": note, "author": payload.reopened_by,
                  "ts": datetime.utcnow().isoformat()})
    batch.notes = notes

    db.commit()
    return {"reopened": True, "batch_id": batch_id, "status": batch.status.value}


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, payload: BatchClose, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is already closed")

    # What blocks a close is ungraded work, and that is the same question in
    # both flows — so it is asked the same way in both.
    #
    # This used to count BatchChart rows still marked PENDING, and skip the
    # check entirely for direct assignments. Nothing has set that column to
    # SUBMITTED since the offline Excel grading path was removed in July, so
    # every ordinary batch had charts permanently pending and could not be
    # closed at all; only Edits/Denials, whose rubric still writes the column,
    # escaped. The column is a vestige. Graded results are the fact.
    graded_pairs = {
        (r.coder_name, r.chart_id)
        for r in db.query(GradingResult.coder_name, GradingResult.chart_id)
        .filter(GradingResult.batch_id == batch_id,
                GradingResult.total_score.isnot(None)).all()
    }
    ungraded = sum(
        1 for a in db.query(BatchChart).filter(BatchChart.batch_id == batch_id).all()
        if (a.coder_name, a.chart_id) not in graded_pairs
    )
    pending_drg = 0
    if _is_ip(batch.specialty):
        pending_drg = (db.query(GradingResult)
                       .filter(GradingResult.batch_id == batch_id,
                               GradingResult.drg_flag == True,
                               GradingResult.drg_reviewed == False)
                       .count())

    blockers = []
    if ungraded:
        blockers.append(f"{ungraded} assigned chart(s) not yet graded")
    if pending_drg:
        blockers.append(f"{pending_drg} DRG review(s) unresolved")
    if blockers:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close — {'; '.join(blockers)}. "
                   f"Use force-close if this is deliberate.",
        )

    batch.status = BatchStatus.CLOSED
    batch.closed_at = datetime.utcnow()
    batch.closed_by = payload.closed_by
    db.commit()
    return {"message": "Batch closed", "batch_id": batch_id}


@router.post("/batches/{batch_id}/force-close")
def force_close_batch(batch_id: int, payload: BatchForceClose, db: Session = Depends(get_db)):
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == BatchStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Batch is already closed")
    batch.status = BatchStatus.CLOSED
    batch.closed_at = datetime.utcnow()
    batch.closed_by = payload.closed_by
    batch.force_closed = True
    batch.force_close_reason = payload.reason
    db.commit()
    return {"message": "Batch force-closed", "batch_id": batch_id}


@router.post("/batches/{batch_id}/notes")
def add_batch_note(batch_id: int, payload: BatchNoteAdd, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    notes = list(batch.notes or [])
    notes.append({"text": payload.text, "author": payload.author, "ts": datetime.utcnow().isoformat()})
    batch.notes = notes
    db.commit()
    return {"notes": batch.notes}


@router.get("/admin/open-batches")
def admin_open_batches(passphrase: str = Query(...), db: Session = Depends(get_db)):
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    batches = db.query(Batch).filter(Batch.status == BatchStatus.OPEN).order_by(Batch.created_at).all()
    now = datetime.utcnow()
    return [
        {
            "id": b.id,
            "name": b.name,
            "specialty": b.specialty.value,
            "created_by": b.created_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "days_open": (now - b.created_at.replace(tzinfo=None)).days if b.created_at else 0,
            "coder_count": len(b.coders),
            "allocation_cycles": len(b.allocation_cycles),
            "total_assigned": len(b.chart_assignments),
            "graded_count": db.query(GradingResult).filter(GradingResult.batch_id == b.id).count(),
        }
        for b in batches
    ]


@router.get("/batches/chart-search")
def chart_search_for_manual(
    specialty: str,
    q: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid specialty: {specialty}")

    query = (db.query(Chart)
             .filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == spec))

    if q:
        query = query.filter(Chart.chart_number.ilike(f"%{q}%"))
    if category:
        query = query.filter(Chart.category.ilike(f"%{category}%"))
    if difficulty:
        try:
            query = query.filter(Chart.difficulty == Difficulty(difficulty))
        except ValueError:
            pass

    charts = query.order_by(Chart.chart_number).limit(100).all()
    return [
        {"id": c.id, "chart_number": c.chart_number, "specialty": c.specialty.value,
         "category": c.category, "difficulty": c.difficulty.value}
        for c in charts
    ]


@router.get("/batches/pool-preview")
def pool_preview(
    specialty: str,
    categories: Optional[str] = None,
    difficulties: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        spec = Specialty(specialty)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid specialty")

    q = db.query(Chart).filter(Chart.status == ChartStatus.ACTIVE, Chart.specialty == spec)

    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        if cats:
            q = q.filter(or_(*[Chart.category.ilike(f"%{c}%") for c in cats]))

    if difficulties:
        diffs_raw = [d.strip() for d in difficulties.split(",") if d.strip()]
        diffs = []
        for d in diffs_raw:
            try:
                diffs.append(Difficulty(d))
            except ValueError:
                pass
        if diffs:
            q = q.filter(Chart.difficulty.in_(diffs))

    total = q.count()

    # E&D specialties don't use answer keys — skip that count entirely
    if _is_ed(spec):
        return {"total_matching": total, "with_answer_key": None}

    q_keyed = q.join(AnswerKey, AnswerKey.chart_id == Chart.id)
    return {
        "total_matching": total,
        "with_answer_key": q_keyed.count(),
    }


@router.get("/batches")
def list_batches(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    direct_only: bool = False,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    response: Response = None,
    db: Session = Depends(get_db),
):
    """
    Newest first, optionally searched and paged.

    search and limit are opt-in so existing callers are unaffected. The total
    before paging comes back in X-Total-Count, because a page of results cannot
    tell you how many there were — and a "Load more" button that cannot say
    what is left is a button you have to click to learn anything.
    """
    if direct_only:
        q = db.query(Batch).filter(Batch.is_direct_assignment.is_(True))
    else:
        q = db.query(Batch).filter(Batch.is_direct_assignment.isnot(True))
    if status:
        q = q.filter(Batch.status == status)
    if specialty:
        try:
            q = q.filter(Batch.specialty == Specialty(specialty))
        except ValueError:
            pass
    if search and search.strip():
        # Server-side so a few letters find a batch anywhere in the history,
        # not just one that happens to be on the page already loaded.
        term = f"%{search.strip().lower()}%"
        q = q.filter(or_(func.lower(Batch.name).like(term),
                         func.lower(Batch.created_by).like(term)))

    # id breaks the tie. created_at alone is not a total order — batches created
    # in the same second (a bulk set-up) came back in whatever order the DB
    # felt like, which under paging can show one row twice and hide another.
    q = q.order_by(Batch.created_at.desc(), Batch.id.desc())
    if response is not None:
        response.headers["X-Total-Count"] = str(q.count())
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    if limit is not None:
        q = q.offset(offset).limit(limit)
    batches = q.all()

    # Graded counts for the page in ONE query. Reading len(b.results) per row
    # would lazy-load every result set on a list screen that never shows them —
    # 25 extra queries a page, growing with the batch.
    ids = [b.id for b in batches]
    graded_counts: dict[int, int] = {}
    if ids:
        graded_counts = dict(
            db.query(GradingResult.batch_id, func.count(GradingResult.id))
              .filter(GradingResult.batch_id.in_(ids),
                      GradingResult.total_score.isnot(None))
              .group_by(GradingResult.batch_id)
              .all()
        )

    now = datetime.utcnow()
    return [
        {
            "id": b.id, "name": b.name, "specialty": b.specialty.value,
            "charts_per_coder": b.charts_per_coder, "status": b.status.value,
            "created_by": b.created_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "coder_count": len(b.coders),
            "allocation_cycles": len(b.allocation_cycles),
            "days_open": (now - b.created_at.replace(tzinfo=None)).days if b.created_at and b.status == BatchStatus.OPEN else None,
            "closed_at": b.closed_at.isoformat() if b.closed_at else None,
            "force_closed": b.force_closed,
            "tags": b.tags or [],
            "is_direct_assignment": b.is_direct_assignment,
            # Drives whether a performance report can be offered at all. A
            # report over zero graded results is an empty document, so the UI
            # disables the button rather than producing one.
            "graded_count": graded_counts.get(b.id, 0),
        }
        for b in batches
    ]


@router.get("/batches/export.xlsx")
def export_batch_list_xlsx(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    The batch list panel, as an Excel file.

    Distinct from the coder-performance export on purpose. That one is
    long format — one row per graded RESULT — which is right for
    slicing performance and wrong for "give me the list I am looking at". This
    is one row per batch, the columns on screen.

    It honours the panel's filters but NOT its paging: you are looking at a
    page because the screen is finite, not because you wanted 25 of 340 in a
    spreadsheet. Batches and direct assignments come back together, as the
    panel merges them, with a Type column to tell them apart.

    Registered above /batches/{batch_id} — FastAPI matches in order, and a
    parameterised route declared first swallows its static siblings.
    """
    from services.excel_service import export_batch_list

    q = db.query(Batch)
    if status:
        q = q.filter(Batch.status == status)
    if specialty:
        try:
            q = q.filter(Batch.specialty == Specialty(specialty))
        except ValueError:
            pass
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.filter(or_(func.lower(Batch.name).like(term),
                         func.lower(Batch.created_by).like(term)))
    batches = q.order_by(Batch.created_at.desc(), Batch.id.desc()).all()

    ids = [b.id for b in batches]
    graded_counts: dict[int, int] = {}
    if ids:
        graded_counts = dict(
            db.query(GradingResult.batch_id, func.count(GradingResult.id))
              .filter(GradingResult.batch_id.in_(ids),
                      GradingResult.total_score.isnot(None))
              .group_by(GradingResult.batch_id)
              .all()
        )

    now = datetime.utcnow()
    rows = [{
        "name": b.name,
        "type": "Direct" if b.is_direct_assignment else "Batch",
        "specialty": b.specialty.value,
        "status": b.status.value,
        "coder_count": len(b.coders),
        "charts_per_coder": b.charts_per_coder,
        "cycles": len(b.allocation_cycles),
        "graded_count": graded_counts.get(b.id, 0),
        "days_open": ((now - b.created_at.replace(tzinfo=None)).days
                      if b.created_at and b.status == BatchStatus.OPEN else None),
        "created_by": b.created_by,
        "created_at": b.created_at.strftime("%Y-%m-%d") if b.created_at else None,
        "closed_at": b.closed_at.strftime("%Y-%m-%d") if b.closed_at else None,
    } for b in batches]

    data = export_batch_list(rows)
    stamp = now.strftime("%Y%m%d")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Batch_List_{stamp}.xlsx"'},
    )


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    coders = db.query(BatchCoder).filter(BatchCoder.batch_id == batch_id).all()
    assignments = (db.query(BatchChart)
                   .filter(BatchChart.batch_id == batch_id)
                   .join(Chart, Chart.id == BatchChart.chart_id).all())

    # cycle_id -> {coder_name: token}. One query rather than one per cycle: a
    # batch that has run a dozen cycles would otherwise pay a round trip each.
    tokens_by_cycle: dict[int, dict] = {}
    for _cid, _cname, _tok in db.execute(_text(
        "SELECT cycle_id, coder_name, token FROM practice_sessions WHERE batch_id = :b"
    ), {"b": batch_id}).fetchall():
        if _cid is not None:
            tokens_by_cycle.setdefault(_cid, {})[_cname] = _tok

    coder_map: dict[str, list] = {}
    for a in assignments:
        coder_map.setdefault(a.coder_name, []).append({
            "chart_id": a.chart_id,
            "chart_number": a.chart.chart_number,
            "specialty": a.chart.specialty.value,
            "category": a.chart.category,
            "difficulty": a.chart.difficulty.value,
            "submission_status": a.submission_status.value,
        })

    now = datetime.utcnow()
    cycles = db.query(BatchAllocationCycle).filter(BatchAllocationCycle.batch_id == batch_id).order_by(BatchAllocationCycle.cycle_number).all()

    pending_submissions_count = sum(1 for a in assignments if a.submission_status == SubmissionStatus.PENDING)
    pending_drg_count = 0
    if _is_ip(batch.specialty):
        pending_drg_count = (db.query(GradingResult)
                             .filter(GradingResult.batch_id == batch_id,
                                     GradingResult.drg_flag == True,
                                     GradingResult.drg_reviewed == False)
                             .count())

    # For direct assignments: build coder_map from practice sessions + results
    direct_graded_count = 0
    if batch.is_direct_assignment:
        graded_rows = db.execute(_text("""
            SELECT ps.coder_name, pr.chart_id, c.chart_number, c.category, pr.specialty, pr.total_score
            FROM practice_results pr
            JOIN practice_sessions ps ON pr.session_id = ps.id
            JOIN charts c ON c.id = pr.chart_id
            WHERE ps.batch_id = :b AND pr.total_score IS NOT NULL
        """), {"b": batch_id}).fetchall()
        direct_graded_count = len(graded_rows)
        for gr in graded_rows:
            coder_name, chart_id = gr[0], gr[1]
            rows = coder_map.setdefault(coder_name, [])
            # A direct assignment already has a BatchChart row for this coder and
            # chart — the practice result describes the SAME work, not a second
            # chart. Appending it listed every graded chart twice and doubled the
            # assigned count. Merge onto the existing row instead, so the
            # assignment's detail (difficulty) and the result's status both
            # survive.
            existing = next((r for r in rows if r["chart_id"] == chart_id), None)
            if existing:
                existing["submission_status"] = "Submitted"
                continue
            rows.append({
                "chart_id": chart_id,
                "chart_number": gr[2],
                "specialty": gr[4] if isinstance(gr[4], str) else (gr[4].value if gr[4] else None),
                "category": gr[3],
                "difficulty": None,
                "submission_status": "Submitted",
            })

    return {
        "id": batch.id, "name": batch.name, "specialty": batch.specialty.value,
        "categories": batch.categories, "difficulties": batch.difficulties,
        "charts_per_coder": batch.charts_per_coder, "status": batch.status.value,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "use_weighted": getattr(batch, "use_weighted", True),
        "use_dpo": bool(getattr(batch, "use_dpo", False) and _uses_dpo(batch.specialty)),
        "closed_at": batch.closed_at.isoformat() if batch.closed_at else None,
        "closed_by": batch.closed_by,
        "force_closed": batch.force_closed,
        "force_close_reason": batch.force_close_reason,
        "days_open": (now - batch.created_at.replace(tzinfo=None)).days if batch.created_at and batch.status == BatchStatus.OPEN else None,
        "notes": batch.notes or [],
        "tags": batch.tags or [],
        "pending_submissions": pending_submissions_count,
        "pending_drg_review": pending_drg_count,
        "is_direct_assignment": bool(batch.is_direct_assignment),
        "direct_graded_count": direct_graded_count,
        "allocation_cycles": [
            {
                "id": c.id, "cycle_number": c.cycle_number,
                "run_at": c.run_at.isoformat() if c.run_at else None,
                "run_by": c.run_by,
                "charts_per_coder": c.charts_per_coder,
                "notes": c.notes,
                "assigned_count": sum(
                    1 for a in assignments
                    if a.cycle_id == c.id or (a.cycle_id is None and c.cycle_number == 1)
                ),
                "randomisation_stats": parse_stats(c.randomisation_stats),
                "warnings": c.warnings or [],
                # The access code each coder got FOR THIS CYCLE. Sessions are
                # already keyed by cycle, so a coder running cycle 2 has a
                # different code from the one they used for cycle 1 — reading
                # them off the codes panel, which lists the latest cycle, is how
                # a trainer hands someone the wrong one.
                "coder_tokens": tokens_by_cycle.get(c.id, {}),
                "coder_pool_notes": c.coder_pool_notes or {},
            }
            for c in cycles
        ],
        "coders": [{"name": c.coder_name, "emp_id": c.emp_id or "",
                    "charts": coder_map.get(c.coder_name, [])} for c in coders],
    }
