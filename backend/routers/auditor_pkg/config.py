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
EM_MIX_FIELDS = [
    "mix_omit_sdx",
    "mix_omit_proc",
    "mix_modifier_missing",
    "mix_modifier_wrong",
    "mix_substitute",
    "mix_spurious",
    "mix_level_shift",
    "mix_cc_boundary",
    "mix_mdm_shift",
]
EM_MIX_DEFAULT = {
    "mix_omit_sdx": 10,
    "mix_omit_proc": 10,
    "mix_modifier_missing": 5,
    "mix_modifier_wrong": 5,
    "mix_substitute": 5,
    "mix_spurious": 10,
    "mix_level_shift": 25,
    "mix_cc_boundary": 10,
    "mix_mdm_shift": 20,
}
GENERAL_ONLY_ZERO = {"mix_level_shift", "mix_cc_boundary", "mix_mdm_shift"}


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
    observed_share_pct: Optional[int] = None
    detection_weight: Optional[int] = None
    review_weight: Optional[int] = None
    max_auto_plantings: Optional[int] = None
    max_section_share: Optional[int] = None
    ccmcc_preference: Optional[int] = None
    mix: Optional[dict] = None
    em_mix: Optional[dict] = None
    updated_by: str
    passphrase: str


def _general_mix(cfg: AuditScoringConfig) -> dict:
    mix = {f: getattr(cfg, f) for f in MIX_FIELDS}
    for f in GENERAL_ONLY_ZERO:
        mix[f] = 0
    if hasattr(cfg, "mix_units") and int(getattr(cfg, "mix_units") or 0):
        mix["mix_spurious"] = int(mix.get("mix_spurious") or 0) \
            + int(getattr(cfg, "mix_units") or 0)
    return mix


def _em_mix(cfg: AuditScoringConfig) -> dict:
    stored = cfg.em_mutation_mix or {}
    return {f: int((stored or {}).get(f, EM_MIX_DEFAULT[f]) or 0)
            for f in EM_MIX_FIELDS}


def _validate_mix(name: str, incoming: dict, allowed: list[str]) -> dict:
    unknown = set(incoming) - set(allowed) - {"mix_units"}
    if unknown:
        raise HTTPException(400, f"Unknown {name} mutation weights: {sorted(unknown)}")
    cleaned = {f: int(incoming.get(f, 0) or 0) for f in allowed}
    total = sum(cleaned.values())
    if total != 100:
        raise HTTPException(
            400, f"{name} mutation weights must total 100 — they currently total {total}")
    return cleaned


def _serialise(cfg: AuditScoringConfig) -> dict:
    mix = _general_mix(cfg)
    em_mix = _em_mix(cfg)
    return {
        "add_weight": cfg.add_weight,
        "revise_weight": cfg.revise_weight,
        "delete_weight": cfg.delete_weight,
        "over_call_revenue_pct": cfg.over_call_revenue_pct,
        "over_call_non_revenue_pct": cfg.over_call_non_revenue_pct,
        "revenue_elements": [
            e for e in (cfg.revenue_elements or []) if e != "units"
        ],
        "query_missed_pct": cfg.query_missed_pct,
        "query_unnecessary_pct": cfg.query_unnecessary_pct,
        "pass_threshold": cfg.pass_threshold,
        "observed_share_pct": cfg.observed_share_pct,
        "detection_weight": cfg.detection_weight,
        "review_weight": cfg.review_weight,
        "max_auto_plantings": cfg.max_auto_plantings,
        "max_section_share": cfg.max_section_share,
        "ccmcc_preference": cfg.ccmcc_preference,
        "mix": mix,
        "mix_total": sum(mix.values()),
        "em_mix": em_mix,
        "em_mix_total": sum(em_mix.values()),
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
        incoming = {k: v for k, v in payload.mix.items() if k != "mix_units"}
        # Backwards compatibility: old clients sent E/M-only weights in the
        # common mix. Ignore those here; the separate em_mix owns them now.
        incoming = {k: v for k, v in incoming.items() if k not in GENERAL_ONLY_ZERO}
        merged = _general_mix(cfg)
        merged.update(incoming)
        for f in GENERAL_ONLY_ZERO:
            merged[f] = 0
        merged = _validate_mix("General", merged, MIX_FIELDS)
        for f, v in merged.items():
            setattr(cfg, f, int(v or 0))
        if hasattr(cfg, "mix_units"):
            cfg.mix_units = 0

    if payload.em_mix is not None:
        incoming = {k: v for k, v in payload.em_mix.items() if k != "mix_units"}
        merged = _em_mix(cfg)
        merged.update(incoming)
        cfg.em_mutation_mix = _validate_mix("E/M", merged, EM_MIX_FIELDS)

    weights = [payload.add_weight, payload.revise_weight, payload.delete_weight]
    if any(w is not None for w in weights):
        a = payload.add_weight if payload.add_weight is not None else cfg.add_weight
        r = payload.revise_weight if payload.revise_weight is not None else cfg.revise_weight
        d = payload.delete_weight if payload.delete_weight is not None else cfg.delete_weight
        if a + r + d != 100:
            raise HTTPException(
                400, f"Add, Revise and Delete weights must total 100 — they total {a + r + d}")
        cfg.add_weight, cfg.revise_weight, cfg.delete_weight = a, r, d

    # The Audit Score blend, validated the same way the component weights are.
    # Zero on both is not merely nonsense: the blend becomes None, the verdict
    # compares (None or 0) against the threshold, and EVERY auditor silently
    # fails. The labels say %, so they have to total 100.
    if payload.detection_weight is not None or payload.review_weight is not None:
        d = (payload.detection_weight if payload.detection_weight is not None
             else cfg.detection_weight)
        r = (payload.review_weight if payload.review_weight is not None
             else cfg.review_weight)
        if d < 0 or r < 0:
            raise HTTPException(400, "Detection and Review weights cannot be negative")
        if d + r != 100:
            raise HTTPException(
                400, f"Detection and Review weights must total 100 — they total {d + r}")
        cfg.detection_weight, cfg.review_weight = d, r

    for f in ("over_call_revenue_pct", "over_call_non_revenue_pct",
              "query_missed_pct", "query_unnecessary_pct", "pass_threshold",
              "max_auto_plantings", "observed_share_pct",
              "max_section_share", "ccmcc_preference"):
        v = getattr(payload, f)
        if v is not None:
            if v < 0:
                raise HTTPException(400, f"{f} cannot be negative")
            setattr(cfg, f, v)

    if payload.revenue_elements is not None:
        cfg.revenue_elements = [e for e in payload.revenue_elements if e != "units"]

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
