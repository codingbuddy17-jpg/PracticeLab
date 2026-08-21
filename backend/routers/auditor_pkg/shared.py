"""Shared helpers for the auditor sub-routers."""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import settings
from services import em_audit_key
from models import (
    AnswerKey, AuditBatch, AuditKeySet, AuditScoringConfig, BatchStatus, Chart,
    Specialty,
)
from services.audit_mutation import MutationConfig
from services.audit_scoring import ScoringConfig

MASTER_PASSPHRASE = settings.MASTER_ADMIN_PASSPHRASE

# Phase 1. Edits & Denials are rubric-graded with no coded answer key to
# mutate, so they can never be covered by this design. E/M is excluded for a
# different reason: auditing a level and MDM reasoning is a different skill and
# deserves its own interaction, not a squeeze into Add/Revise/Delete.
AUDITABLE_SPECIALTIES = {
    Specialty.IP_DRG,
    Specialty.SDS,
    Specialty.ED_FACILITY,
    Specialty.SURGERY,
    Specialty.ED_SINGLE_PATH,
    Specialty.ANCILLARY,
    # Professional E/M. Audited on the CODE — the level chosen, its modifier,
    # and the diagnoses supporting it — which is what an auditor reviews in
    # practice. The MDM elements behind the level are graded in PracticeLab and
    # are NOT part of the audit form: reviewing 26 attestations is a different
    # job from reviewing a claim, and it is where the variable count explodes.
    #
    # These read the ordinary answer key like every other specialty. The wide
    # em_answer_keys table drives coder grading and is not needed here.
    Specialty.EM,
    Specialty.ED_PROFEE,
}

# Which coding sections an auditor reviews, per specialty — read off the same
# distinctions the coder form already makes, so the two interfaces agree about
# what a chart contains.
SECTIONS_BY_SPECIALTY = {
    Specialty.IP_DRG:         ["PDx", "SDx", "PCS"],
    Specialty.SDS:            ["PDx", "SDx", "CPT"],
    Specialty.ED_FACILITY:    ["PDx", "SDx", "CPT"],
    Specialty.SURGERY:        ["PDx", "SDx", "CPT"],
    Specialty.ED_SINGLE_PATH: ["PDx", "SDx", "CPT"],
    Specialty.ANCILLARY:      ["PDx", "SDx"],
    # The E/M level is a CPT line like any other, which is what lets the level
    # ladder and the 99285/99291 boundary work here with no new machinery.
    # MDM is the reasoning, at the granularity an audit can judge: the three
    # LEVELS, not the twenty-six element ticks behind them. Reviewing every
    # tick is a different job from reviewing a claim, and it is where the
    # variable count explodes.
    Specialty.EM:             ["PDx", "SDx", "CPT", "MDM"],
    Specialty.ED_PROFEE:      ["PDx", "SDx", "CPT", "MDM"],
}

# Which actions each section allows. PDx is single-valued: it can be wrong, but
# it cannot be absent or removed, so Revise is the only thing to do to it.
ACTIONS_BY_SECTION = {
    "PDx": ["Revise"],
    # Single-valued, exactly like PDx: an encounter has one COPA, one Data
    # Review and one Risk. They can be wrong; they cannot be absent or added.
    "MDM": ["Revise"],
    "SDx": ["Add", "Revise", "Delete"],
    "PCS": ["Add", "Revise", "Delete"],
    "CPT": ["Add", "Revise", "Delete"],
}

# Which line fields a Revise may touch, per section. Modifiers, POA and
# pointers are FIELDS ON A LINE, not sections of their own — revising one is a
# Revise on that line, which keeps the section list short while still recording
# exactly what was wrong.
# The MDM section's three fields, and the values each may take. Served rather
# than typed by the auditor: these are a fixed vocabulary, and a free-text box
# would collect "Mod", "moderate" and "MODERATE" as three different answers.
MDM_FIELDS = ["copa", "dr", "risk"]
MDM_LEVELS = ["Minimal", "Low", "Moderate", "High"]
MDM_LABELS = {"copa": "Problems addressed (COPA)",
              "dr": "Data reviewed",
              "risk": "Risk"}


FIELDS_BY_SECTION = {
    Specialty.IP_DRG: {"PDx": ["code", "poa"], "SDx": ["code", "poa"],
                       "PCS": ["code"]},
    Specialty.ANCILLARY: {"PDx": ["code"], "SDx": ["code"]},
    Specialty.EM: {"PDx": ["code"], "SDx": ["code"],
                   "CPT": ["code", "modifier"], "MDM": MDM_FIELDS},
    Specialty.ED_PROFEE: {"PDx": ["code"], "SDx": ["code"],
                          "CPT": ["code", "modifier"], "MDM": MDM_FIELDS},
}
_DEFAULT_FIELDS = {"PDx": ["code"], "SDx": ["code"],
                   "CPT": ["code", "modifier"]}


QUERY_SPECIALTIES = {Specialty.IP_DRG}


def sections_for(specialty: Specialty) -> list[str]:
    return SECTIONS_BY_SPECIALTY.get(specialty, ["PDx", "SDx", "CPT"])


def fields_for(specialty: Specialty) -> dict:
    return FIELDS_BY_SECTION.get(specialty, _DEFAULT_FIELDS)


def sections_for_chart(db, chart, specialty: Specialty) -> list:
    """
    Which sections apply to THIS chart, not merely to its specialty.

    The form spec is served per specialty, but E/M is not uniform: a preventive
    visit, a consult, or a visit levelled by time is not graded on medical
    decision making at all. Asking an auditor to give a verdict on COPA, Data
    Review and Risk for such a chart asks them to judge something that carries
    no weight, against three stored levels that are the derivation's default
    rather than anybody's decision.

    This keys on the CATEGORY, which is a property of the encounter and is
    already plain from the code on the claim. It does not key on whether
    anything was planted, which would be a tell — the module's central rule is
    that a chart renders identically either way, and category is fixed per
    chart in the same way section colour is fixed per section.
    """
    sections = [s["key"] for s in form_spec(specialty)["sections"]]
    if "MDM" not in sections or chart is None:
        return sections

    from routers.practicelab_pkg.em_grading import (category_uses_mdm,
                                                    resolve_category)
    key = audit_key_for(db, chart)
    if key is None:
        # No key yet. Absence is not evidence the chart is preventive, and
        # guessing would hide a section the chart may well be graded on. The
        # trainer key screen shows unkeyed charts, so this path is reached.
        return sections
    category = resolve_category(getattr(key, "em_category", None),
                                getattr(key, "em_code", None))
    method = (getattr(key, "level_method", "MDM") or "MDM").upper()
    if not (category_uses_mdm(category) and method != "TIME"):
        return [s for s in sections if s != "MDM"]
    return sections


def form_spec(specialty: Specialty) -> dict:
    """
    Everything the auditor's panel needs to render itself.

    Structure comes from the specialty and nothing else. A clean chart must
    render identically to a planted one — an empty state drawn differently, or
    a section collapsed because nothing was mutated, turns clean charts into a
    tell and destroys the restraint measurement.
    """
    sections = sections_for(specialty)
    fields = fields_for(specialty)
    return {
        "specialty": specialty.value,
        "sections": [
            {
                "key": s,
                "actions": ACTIONS_BY_SECTION.get(s, ["Add", "Revise", "Delete"]),
                "fields": fields.get(s, _DEFAULT_FIELDS.get(s, ["code"])),
                # Allowed values, where a field has a fixed vocabulary. Served
                # rather than hardcoded in the panel for the same reason the
                # sections are: two lists that must agree will not, and a
                # free-text MDM box would collect "Mod", "moderate" and
                # "MODERATE" as three different answers.
                "field_values": ({f: MDM_LEVELS for f in MDM_FIELDS}
                                 if s == "MDM" else {}),
                "field_labels": MDM_LABELS if s == "MDM" else {},
            }
            for s in sections
        ],
        "supports_query": specialty in QUERY_SPECIALTIES,
    }


def require_passphrase(passphrase: str, action: str = "perform this action") -> None:
    if (passphrase or "").strip() != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail=f"Passphrase required to {action}")


def parse_specialty(value: str) -> Specialty:
    try:
        specialty = Specialty(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid specialty: {value}")
    if specialty not in AUDITABLE_SPECIALTIES:
        raise HTTPException(
            status_code=400,
            detail=(f"{specialty.value} cannot be audited. Edits & Denials are "
                    f"rubric-graded with no coded key to introduce errors into, and "
                    f"E/M needs its own audit design."))
    return specialty


def get_batch_or_404(db: Session, batch_id: int) -> AuditBatch:
    batch = db.query(AuditBatch).filter(AuditBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Audit batch not found")
    return batch


def assert_batch_open(db: Session, batch_id: int, action: str = "modify results") -> None:
    """
    Refuse to mutate a scored result in a closed batch. Closing is the point at
    which results become the record.
    """
    batch = db.query(AuditBatch).filter(AuditBatch.id == batch_id).first()
    if batch and batch.status == BatchStatus.CLOSED:
        raise HTTPException(
            status_code=409,
            detail=f"This audit batch is closed — reopen it to {action}.")


def load_config(db: Session) -> AuditScoringConfig:
    """The single config row, created on first use rather than seeded."""
    cfg = db.query(AuditScoringConfig).filter(AuditScoringConfig.id == 1).first()
    if cfg is None:
        cfg = AuditScoringConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def scoring_config(db: Session) -> ScoringConfig:
    return ScoringConfig.from_db(load_config(db))


def mutation_config(db: Session, specialty: Optional[Specialty] = None) -> MutationConfig:
    cfg = load_config(db)
    out = MutationConfig.from_db(cfg)
    em_only = ("mix_level_shift", "mix_cc_boundary", "mix_mdm_shift")
    if specialty in em_audit_key.EM_KEY_SPECIALTIES:
        from routers.auditor_pkg.config import EM_MIX_DEFAULT, EM_MIX_FIELDS
        stored = getattr(cfg, "em_mutation_mix", None) or {}
        for field in MutationConfig.__dataclass_fields__:
            if field.startswith("mix_") and field != "mix_units":
                setattr(out, field, 0)
        for field in EM_MIX_FIELDS:
            setattr(out, field, int(stored.get(field, EM_MIX_DEFAULT[field]) or 0))
    else:
        for field in em_only:
            setattr(out, field, 0)
    return out


def chart_pool(db: Session, batch: AuditBatch) -> list[Chart]:
    """
    Charts eligible for this batch.

    A chart with no answer key is excluded rather than assigned clean: there is
    no truth to plant errors in and nothing to audit against, so including it
    would hand the auditor a chart that can only ever score as restraint.
    """
    q = db.query(Chart).filter(Chart.specialty == batch.specialty,
                               Chart.status == "Active")
    if batch.categories:
        q = q.filter(Chart.category.in_(batch.categories))
    if batch.difficulties:
        q = q.filter(Chart.difficulty.in_(batch.difficulties))

    # Which table holds this specialty's truth. E/M and ED Profee keep theirs
    # in em_answer_keys — the same table that grades their coders — so that
    # one chart never carries two answers that can drift apart.
    if batch.specialty in EM_KEY_SPECIALTIES:
        charts = q.all()
        keyed = em_audit_key.chart_ids_with_keys(db, [c.id for c in charts])
        return [c for c in charts if c.id in keyed]
    return q.join(AnswerKey, AnswerKey.chart_id == Chart.id).all()


# The specialties whose key lives in em_answer_keys rather than answer_keys.
from services.em_audit_key import EM_KEY_SPECIALTIES  # noqa: E402,F401


def audit_key_for(db: Session, chart):
    """
    The key the auditor should read for one chart.

    One entry point so no caller has to know there are two tables. An E/M key
    comes back adapted into the ordinary shape, carrying its MDM levels; every
    other specialty gets its AnswerKey unchanged.

    None means nobody has authored a key yet, which is a legal state — the
    chart is simply not eligible to be audited.
    """
    if chart is None:
        return None
    if chart.specialty in EM_KEY_SPECIALTIES:
        key = em_audit_key.load(db, chart.id)
        if key is not None:
            # Older databases briefly stored this flag on an ordinary key. New
            # E/M and ED Profee keys store it beside the E/M truth so there is
            # still one active key source.
            ordinary = (db.query(AnswerKey)
                        .filter(AnswerKey.chart_id == chart.id).first())
            key.cc_boundary = getattr(key, "cc_boundary", None) \
                or getattr(ordinary, "cc_boundary", None)
        return key
    return db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()


def sets_by_chart(db: Session, chart_ids: list[int]) -> dict[int, list[AuditKeySet]]:
    if not chart_ids:
        return {}
    charts = {
        c.id: c for c in db.query(Chart).filter(Chart.id.in_(chart_ids)).all()
    }
    keys = {chart_id: audit_key_for(db, chart)
            for chart_id, chart in charts.items()}
    rows = (db.query(AuditKeySet)
            .filter(AuditKeySet.chart_id.in_(chart_ids))
            .order_by(AuditKeySet.id)
            .all())
    out: dict[int, list[AuditKeySet]] = {}
    for row in rows:
        key = keys.get(row.chart_id)
        if key is None:
            continue
        # A coder key can be replaced after a trainer authored audit errors.
        # If that replacement removes or reorders the referenced line, the old
        # version must not be allocated: apply_manual_set would quietly drop the
        # unusable mutation and hand out a different exercise than the trainer
        # wrote. Keep the stored version editable in Audit Keys, but do not
        # treat it as playable.
        from services.audit_allocation import apply_manual_set
        _claim, truth = apply_manual_set(key, row)
        if len(truth) != len(row.mutations or []):
            continue
        out.setdefault(row.chart_id, []).append(row)
    return out
