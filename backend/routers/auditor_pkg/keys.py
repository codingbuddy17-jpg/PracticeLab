"""
Audit key sets — the permanent, trainer-authored planting library.

A set records what the AUDITOR must find, not what the system should break.
That direction matters: it is the same shape the generator emits and the same
shape an auditor's own findings take, so scoring never has to translate
between two vocabularies, and a trainer authoring a set is writing the answer
rather than the sabotage.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import AnswerKey, AuditKeySet, Chart
from services.audit_allocation import apply_manual_set
from .shared import (
    AUDITABLE_SPECIALTIES, QUERY_SPECIALTIES, form_spec, require_passphrase,
)

router = APIRouter()

VALID_ACTIONS = {"Add", "Revise", "Delete"}
VALID_SECTIONS = {"PDx", "SDx", "PCS", "CPT"}


class Mutation(BaseModel):
    section: str
    action: str
    field: Optional[str] = None
    line: Optional[int] = None
    claim_value: Optional[str] = None
    correct_value: Optional[str] = None
    poa: Optional[str] = None
    ccmcc: Optional[str] = None
    drg_impacting: bool = False


class KeySetPayload(BaseModel):
    name: str
    mutations: list[Mutation] = []
    query_expected: Optional[bool] = None
    query_rationale: Optional[str] = None
    always_plant: bool = False
    notes: Optional[str] = None
    authored_by: str
    passphrase: str


def _validate(chart: Chart, mutations: list[Mutation]) -> None:
    for i, m in enumerate(mutations, start=1):
        where = f"error {i}"
        if m.section not in VALID_SECTIONS:
            raise HTTPException(400, f"{where}: unknown section {m.section!r}")
        if m.action not in VALID_ACTIONS:
            raise HTTPException(400, f"{where}: unknown action {m.action!r}")
        # PDx is single-valued — it can be wrong, but it cannot be absent or
        # removed, so there is nothing to Add or Delete.
        if m.section == "PDx" and m.action != "Revise":
            raise HTTPException(
                400, f"{where}: PDx can only be revised, not {m.action.lower()}ed")
        if m.action == "Add" and not (m.correct_value or "").strip():
            raise HTTPException(400, f"{where}: an Add needs the code the auditor must add")
        if m.action == "Delete" and not (m.claim_value or "").strip():
            raise HTTPException(400, f"{where}: a Delete needs the spurious code to introduce")
        if m.action == "Revise" and not (m.claim_value or "").strip():
            raise HTTPException(
                400, f"{where}: a Revise needs the wrong value to put on the claim")
        if m.action == "Revise" and m.section != "PDx" and m.line is None:
            raise HTTPException(400, f"{where}: a Revise needs the line to change")


def _serialise(row: AuditKeySet, chart: Optional[Chart] = None) -> dict:
    return {
        "id": row.id,
        "chart_id": row.chart_id,
        "chart_number": chart.chart_number if chart else None,
        "name": row.name,
        "mutations": row.mutations or [],
        "planting_count": len(row.mutations or []),
        "query_expected": row.query_expected,
        "query_rationale": row.query_rationale,
        "always_plant": bool(row.always_plant),
        "notes": row.notes,
        "authored_by": row.authored_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/keys/chart/{chart_id}")
def list_sets_for_chart(chart_id: int, db: Session = Depends(get_db)):
    """
    Every authored set for one chart, alongside the answer key they are
    written against and the form spec for the chart's specialty.
    """
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(404, "Chart not found")
    key = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    rows = (db.query(AuditKeySet)
            .filter(AuditKeySet.chart_id == chart_id)
            .order_by(AuditKeySet.id).all())
    return {
        "chart_id": chart.id,
        "chart_number": chart.chart_number,
        "specialty": chart.specialty.value,
        "auditable": chart.specialty in AUDITABLE_SPECIALTIES,
        "supports_query": chart.specialty in QUERY_SPECIALTIES,
        "has_answer_key": key is not None,
        "answer_key": None if key is None else {
            "pdx_code": key.pdx_code, "pdx_poa": key.pdx_poa,
            "sdx": key.sdx or [], "pcs": key.pcs or [], "cpt": key.cpt or [],
        },
        "form": form_spec(chart.specialty),
        "sets": [_serialise(r, chart) for r in rows],
    }


@router.get("/keys/status")
def key_status(specialty: str = Query(...), db: Session = Depends(get_db)):
    """
    Curation coverage for one specialty.

    Charts with no ANSWER key are counted separately rather than lumped in with
    the uncurated ones: those are not a curation gap a trainer can close here,
    they are a chart-library gap, and mixing them makes the to-do list look
    bigger than the work actually available.
    """
    charts = (db.query(Chart)
              .filter(Chart.specialty == specialty, Chart.status == "Active").all())
    chart_ids = [c.id for c in charts]
    keyed = {k.chart_id for k in db.query(AnswerKey.chart_id).filter(
        AnswerKey.chart_id.in_(chart_ids)).all()} if chart_ids else set()
    curated = {k.chart_id for k in db.query(AuditKeySet.chart_id).filter(
        AuditKeySet.chart_id.in_(chart_ids)).all()} if chart_ids else set()

    auditable = keyed
    return {
        "specialty": specialty,
        "total_charts": len(charts),
        "auditable": len(auditable),
        "curated": len(auditable & curated),
        "uncurated": len(auditable - curated),
        "no_answer_key": len(set(chart_ids) - keyed),
    }


@router.get("/keys/uncurated")
def uncurated_charts(specialty: str = Query(...),
                     limit: int = Query(200, le=500),
                     db: Session = Depends(get_db)):
    """
    Charts that could carry authored errors but do not yet — the curation
    to-do list. They still get audited; the system generates their errors.
    """
    curated = {k.chart_id for k in db.query(AuditKeySet.chart_id).all()}
    rows = (db.query(Chart)
            .join(AnswerKey, AnswerKey.chart_id == Chart.id)
            .filter(Chart.specialty == specialty, Chart.status == "Active")
            .order_by(Chart.chart_number).limit(limit + len(curated)).all())
    out = [c for c in rows if c.id not in curated][:limit]
    return {"charts": [{
        "chart_id": c.id, "chart_number": c.chart_number,
        "category": c.category,
        "difficulty": c.difficulty.value if c.difficulty else None,
    } for c in out]}


@router.get("/keys")
def list_sets(specialty: Optional[str] = None,
              limit: int = Query(200, le=500),
              db: Session = Depends(get_db)):
    """The library at a glance — which charts have been curated, and how much."""
    q = db.query(AuditKeySet, Chart).join(Chart, Chart.id == AuditKeySet.chart_id)
    if specialty:
        q = q.filter(Chart.specialty == specialty)
    rows = q.order_by(Chart.chart_number, AuditKeySet.id).limit(limit).all()
    return {"sets": [_serialise(s, c) for s, c in rows], "count": len(rows)}


@router.post("/keys/chart/{chart_id}")
def create_set(chart_id: int, payload: KeySetPayload, db: Session = Depends(get_db)):
    require_passphrase(payload.passphrase, "author an audit key")
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(404, "Chart not found")
    if chart.specialty not in AUDITABLE_SPECIALTIES:
        raise HTTPException(400, f"{chart.specialty.value} cannot be audited")
    if not db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first():
        raise HTTPException(
            400, "This chart has no answer key — there is no truth to introduce errors into")
    if not (payload.name or "").strip():
        raise HTTPException(400, "Name the set, so it can be told apart from others on this chart")
    if payload.query_expected is not None and chart.specialty not in QUERY_SPECIALTIES:
        raise HTTPException(
            400, f"A physician query determination only applies to "
                 f"{', '.join(s.value for s in QUERY_SPECIALTIES)}")
    _validate(chart, payload.mutations)

    row = AuditKeySet(
        chart_id=chart_id,
        name=payload.name.strip(),
        mutations=[m.model_dump() for m in payload.mutations],
        query_expected=payload.query_expected,
        query_rationale=payload.query_rationale,
        always_plant=payload.always_plant,
        notes=payload.notes,
        authored_by=payload.authored_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialise(row, chart)


@router.put("/keys/{set_id}")
def update_set(set_id: int, payload: KeySetPayload, db: Session = Depends(get_db)):
    """
    Edits apply to FUTURE allocations only. Assignments already made hold a
    frozen copy of their claim and ground truth, so improving the library
    mid-batch never disturbs work in flight or restates a score already given.
    """
    require_passphrase(payload.passphrase, "edit an audit key")
    row = db.query(AuditKeySet).filter(AuditKeySet.id == set_id).first()
    if not row:
        raise HTTPException(404, "Audit key set not found")
    chart = db.query(Chart).filter(Chart.id == row.chart_id).first()
    _validate(chart, payload.mutations)

    row.name = payload.name.strip() or row.name
    row.mutations = [m.model_dump() for m in payload.mutations]
    row.query_expected = payload.query_expected
    row.query_rationale = payload.query_rationale
    row.always_plant = payload.always_plant
    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _serialise(row, chart)


class DeletePayload(BaseModel):
    passphrase: str


@router.post("/keys/{set_id}/delete")
def delete_set(set_id: int, payload: DeletePayload, db: Session = Depends(get_db)):
    require_passphrase(payload.passphrase, "delete an audit key")
    row = db.query(AuditKeySet).filter(AuditKeySet.id == set_id).first()
    if not row:
        raise HTTPException(404, "Audit key set not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": set_id}


class PreviewPayload(BaseModel):
    mutations: list[Mutation] = []


@router.post("/keys/chart/{chart_id}/preview")
def preview_set(chart_id: int, payload: PreviewPayload, db: Session = Depends(get_db)):
    """
    Show the claim a set would produce, without saving it.

    Authoring plantings blind is how a trainer ends up asking an auditor to
    correct a line that is not on their screen. This renders the claim exactly
    as the auditor will see it, beside the findings they are expected to make.
    """
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(404, "Chart not found")
    key = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    if not key:
        raise HTTPException(400, "This chart has no answer key")
    _validate(chart, payload.mutations)

    class _Draft:
        mutations = [m.model_dump() for m in payload.mutations]
        query_expected = None

    claim, truth = apply_manual_set(key, _Draft())
    skipped = len(payload.mutations) - len(truth)
    return {
        "claim": claim,
        "ground_truth": truth,
        "planting_count": len(truth),
        # A planting naming a code that is not on the key is dropped rather
        # than guessed at — the auditor could never score it.
        "skipped": skipped,
        "warning": (f"{skipped} error(s) reference codes that are not on this "
                    f"chart's answer key and were dropped") if skipped else None,
    }


@router.get("/keys/export")
def export_keys(specialty: Optional[str] = None, db: Session = Depends(get_db)):
    """The whole authored library, one row per error."""
    import io
    from fastapi.responses import StreamingResponse
    from services.audit_export import export_key_sets
    from services.download_headers import content_disposition

    q = db.query(AuditKeySet, Chart).join(Chart, Chart.id == AuditKeySet.chart_id)
    if specialty:
        q = q.filter(Chart.specialty == specialty)
    rows = q.order_by(Chart.chart_number, AuditKeySet.id).all()
    data = export_key_sets([_serialise(s, c) for s, c in rows])
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition("Audit_Keys.xlsx", "Audit_Keys.xlsx"))
