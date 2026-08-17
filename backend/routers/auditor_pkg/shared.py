"""Shared helpers for the auditor sub-routers."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import settings
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
}

# Which actions each section allows. PDx is single-valued: it can be wrong, but
# it cannot be absent or removed, so Revise is the only thing to do to it.
ACTIONS_BY_SECTION = {
    "PDx": ["Revise"],
    "SDx": ["Add", "Revise", "Delete"],
    "PCS": ["Add", "Revise", "Delete"],
    "CPT": ["Add", "Revise", "Delete"],
}

# Which line fields a Revise may touch, per section. Modifiers, POA and
# pointers are FIELDS ON A LINE, not sections of their own — revising one is a
# Revise on that line, which keeps the section list short while still recording
# exactly what was wrong.
FIELDS_BY_SECTION = {
    Specialty.IP_DRG: {"PDx": ["code", "poa"], "SDx": ["code", "poa"],
                       "PCS": ["code"]},
    Specialty.ANCILLARY: {"PDx": ["code"], "SDx": ["code"]},
}
_DEFAULT_FIELDS = {"PDx": ["code"], "SDx": ["code"],
                   "CPT": ["code", "modifier"]}

QUERY_SPECIALTIES = {Specialty.IP_DRG}


def sections_for(specialty: Specialty) -> list[str]:
    return SECTIONS_BY_SPECIALTY.get(specialty, ["PDx", "SDx", "CPT"])


def fields_for(specialty: Specialty) -> dict:
    return FIELDS_BY_SECTION.get(specialty, _DEFAULT_FIELDS)


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


def mutation_config(db: Session) -> MutationConfig:
    return MutationConfig.from_db(load_config(db))


def chart_pool(db: Session, batch: AuditBatch) -> list[Chart]:
    """
    Charts eligible for this batch.

    A chart with no answer key is excluded rather than assigned clean: there is
    no truth to plant errors in and nothing to audit against, so including it
    would hand the auditor a chart that can only ever score as restraint.
    """
    q = (db.query(Chart)
         .join(AnswerKey, AnswerKey.chart_id == Chart.id)
         .filter(Chart.specialty == batch.specialty,
                 Chart.status == "Active"))
    if batch.categories:
        q = q.filter(Chart.category.in_(batch.categories))
    if batch.difficulties:
        q = q.filter(Chart.difficulty.in_(batch.difficulties))
    return q.all()


def sets_by_chart(db: Session, chart_ids: list[int]) -> dict[int, list[AuditKeySet]]:
    if not chart_ids:
        return {}
    rows = (db.query(AuditKeySet)
            .filter(AuditKeySet.chart_id.in_(chart_ids))
            .order_by(AuditKeySet.id)
            .all())
    out: dict[int, list[AuditKeySet]] = {}
    for row in rows:
        out.setdefault(row.chart_id, []).append(row)
    return out
