"""Audit scoring and mutation configuration — one row, passphrase-gated."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import AuditScoringConfig
from services.audit_mutation import MUTATION_KINDS
from .shared import AUDITABLE_SPECIALTIES, form_spec, load_config, require_passphrase

router = APIRouter()

MIX_FIELDS = [f for _kind, f in MUTATION_KINDS]


class ConfigUpdate(BaseModel):
    add_weight: Optional[int] = None
    revise_weight: Optional[int] = None
    delete_weight: Optional[int] = None
    over_call_revenue_pct: Optional[int] = None
    over_call_non_revenue_pct: Optional[int] = None
    revenue_elements: Optional[list[str]] = None
    query_missed_pct: Optional[int] = None
    query_unnecessary_pct: Optional[int] = None
    pass_threshold: Optional[int] = None
    min_opportunities_for_verdict: Optional[int] = None
    max_auto_plantings: Optional[int] = None
    max_section_share: Optional[int] = None
    ccmcc_preference: Optional[int] = None
    mix: Optional[dict] = None
    updated_by: str
    passphrase: str


def _serialise(cfg: AuditScoringConfig) -> dict:
    return {
        "add_weight": cfg.add_weight,
        "revise_weight": cfg.revise_weight,
        "delete_weight": cfg.delete_weight,
        "over_call_revenue_pct": cfg.over_call_revenue_pct,
        "over_call_non_revenue_pct": cfg.over_call_non_revenue_pct,
        "revenue_elements": cfg.revenue_elements or [],
        "query_missed_pct": cfg.query_missed_pct,
        "query_unnecessary_pct": cfg.query_unnecessary_pct,
        "pass_threshold": cfg.pass_threshold,
        "min_opportunities_for_verdict": cfg.min_opportunities_for_verdict,
        "max_auto_plantings": cfg.max_auto_plantings,
        "max_section_share": cfg.max_section_share,
        "ccmcc_preference": cfg.ccmcc_preference,
        "mix": {f: getattr(cfg, f) for f in MIX_FIELDS},
        "mix_total": sum(getattr(cfg, f) or 0 for f in MIX_FIELDS),
        "updated_by": cfg.updated_by,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return _serialise(load_config(db))


@router.put("/config")
def update_config(payload: ConfigUpdate, db: Session = Depends(get_db)):
    """
    Changes apply to audits scored AFTERWARDS. Results already stored keep the
    scores they were given, so tuning a weight can never silently restate a
    closed batch.
    """
    require_passphrase(payload.passphrase, "change audit scoring configuration")
    cfg = load_config(db)

    if payload.mix is not None:
        unknown = set(payload.mix) - set(MIX_FIELDS)
        if unknown:
            raise HTTPException(400, f"Unknown mutation weights: {sorted(unknown)}")
        merged = {f: payload.mix.get(f, getattr(cfg, f)) for f in MIX_FIELDS}
        total = sum(int(v or 0) for v in merged.values())
        if total != 100:
            raise HTTPException(
                400, f"Mutation weights must total 100 — they currently total {total}")
        for f, v in merged.items():
            setattr(cfg, f, int(v or 0))

    weights = [payload.add_weight, payload.revise_weight, payload.delete_weight]
    if any(w is not None for w in weights):
        a = payload.add_weight if payload.add_weight is not None else cfg.add_weight
        r = payload.revise_weight if payload.revise_weight is not None else cfg.revise_weight
        d = payload.delete_weight if payload.delete_weight is not None else cfg.delete_weight
        if a + r + d != 100:
            raise HTTPException(
                400, f"Add, Revise and Delete weights must total 100 — they total {a + r + d}")
        cfg.add_weight, cfg.revise_weight, cfg.delete_weight = a, r, d

    for f in ("over_call_revenue_pct", "over_call_non_revenue_pct",
              "query_missed_pct", "query_unnecessary_pct", "pass_threshold",
              "min_opportunities_for_verdict", "max_auto_plantings",
              "max_section_share", "ccmcc_preference"):
        v = getattr(payload, f)
        if v is not None:
            if v < 0:
                raise HTTPException(400, f"{f} cannot be negative")
            setattr(cfg, f, v)

    if payload.revenue_elements is not None:
        cfg.revenue_elements = payload.revenue_elements

    cfg.updated_by = payload.updated_by
    db.commit()
    db.refresh(cfg)
    return _serialise(cfg)


@router.get("/form-spec")
def get_form_specs():
    """
    What the auditor's panel renders, per specialty.

    Served rather than hardcoded in the frontend so the two cannot drift — the
    sections an auditor reviews and the actions each allows are a property of
    the specialty, decided in one place.
    """
    from models import Specialty
    return {"specialties": [form_spec(s) for s in sorted(
        AUDITABLE_SPECIALTIES, key=lambda x: x.value)]}
