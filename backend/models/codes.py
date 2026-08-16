"""
Reference code sets — ICD-10-CM, ICD-10-PCS and HCPCS Level II.

Published by CMS and NCHS and in the public domain, so they can be ingested and
redistributed. CPT is deliberately absent: it is AMA copyright and licensed per
user, and this repository is public.

These are REFERENCE tables. Nothing here is written by the application at
runtime — they are filled by scripts/ingest_code_sets.py from the CMS files and
replaced wholesale when a new edition is published. Descriptions are looked up,
never copied onto an answer key or a claim: codes get redescribed every October,
and a stored description would freeze at whatever it said the day it was typed.

All new tables, so create_all() builds them and no _add_col migration is
needed — but they are ORM models on purpose. Six tables in this schema exist
only in raw DDL and are invisible to Base.metadata, which is a mess worth not
growing.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Index, Integer, String, Text, func,
)

from database import Base


class CodeSetVersion(Base):
    """
    What edition of each code set is loaded, and when.

    CMS republishes annually with quarterly HCPCS updates, so "which vintage is
    in there" is a question that gets asked. Recording it also makes the ingest
    idempotent: a run whose fingerprint matches what is already loaded can stop
    rather than re-parsing a hundred thousand rows.
    """

    __tablename__ = "code_set_versions"

    id = Column(Integer, primary_key=True, index=True)
    code_system = Column(String(12), nullable=False, index=True)
    edition = Column(String(20), nullable=False)      # e.g. "FY2026"
    source_url = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
    loaded_by = Column(String(100), nullable=True)


class CodeDescription(Base):
    """
    One code and what it means, across all three sets.

    A single table with a code_system discriminator rather than three, because
    every consumer asks the same question — "what does this code say" — and a
    uniform lookup keeps the calling code free of per-system branching.

    chapter and cc_mcc_status are only meaningful for ICD-10-CM and are null
    elsewhere. NA is a real value here as everywhere else in this codebase.
    """

    __tablename__ = "code_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    code_system = Column(String(12), nullable=False)   # ICD10CM · ICD10PCS · HCPCS
    code = Column(String(10), nullable=False)
    description = Column(Text, nullable=False)
    short_description = Column(String(120), nullable=True)

    # ICD-10-CM only.
    chapter = Column(String(90), nullable=True)
    chapter_no = Column(Integer, nullable=True)
    # CC, MCC, or null. Trainer-entered ccmcc on answer keys drives DRG flags
    # for coders and drg_impacting for auditors, so having the published truth
    # to check it against is the point of carrying this.
    cc_mcc_status = Column(String(4), nullable=True)
    # A header code is a category, not something anyone codes to.
    is_billable = Column(Boolean, nullable=False, default=True)

    edition = Column(String(20), nullable=True)


# Lookup is always (system, code); search is by description prefix or text.
Index("ix_code_desc_system_code", CodeDescription.code_system,
      CodeDescription.code, unique=True)
Index("ix_code_desc_code", CodeDescription.code)
Index("ix_code_desc_chapter", CodeDescription.chapter_no)


class PcsCodeAxis(Base):
    """
    An ICD-10-PCS code broken into its seven characters, with each title.

    Two jobs. It names what a code MEANS — the flat description is these seven
    titles joined — and it says which codes EXIST: PCS is only valid in the
    combinations the CMS tables define, so presence here is validity.

    That second job matters for the auditor's error generator. It changes one
    character to make a wrong code, which is structurally valid but may not be
    a real code at all; an auditor spotting "that is not a code" is exercising
    a different skill from spotting the wrong root operation.
    """

    __tablename__ = "pcs_code_axes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(7), nullable=False, unique=True, index=True)

    section = Column(String(60), nullable=True)          # char 1
    body_system = Column(String(90), nullable=True)      # char 2
    root_operation = Column(String(60), nullable=True)   # char 3
    body_part = Column(String(90), nullable=True)        # char 4
    approach = Column(String(60), nullable=True)         # char 5
    device = Column(String(90), nullable=True)           # char 6
    qualifier = Column(String(90), nullable=True)        # char 7

    edition = Column(String(20), nullable=True)


Index("ix_pcs_axes_rootop", PcsCodeAxis.root_operation)
Index("ix_pcs_axes_bodysys", PcsCodeAxis.body_system)


# ── ingested, not yet used ───────────────────────────────────────────────────
#
# Kept from the same CMS download because they cost nothing to parse now and
# would mean revisiting the ingest later. Nothing reads them yet.
#
# cc_exclusions is the one with a use even without a DRG grouper: whether a
# secondary counts as a CC depends on the principal diagnosis, so validating a
# trainer's ccmcc label properly needs it.

class CcExclusion(Base):
    """Principal diagnoses that cancel a secondary's CC/MCC status."""

    __tablename__ = "cc_exclusions"

    id = Column(Integer, primary_key=True, index=True)
    list_id = Column(String(12), nullable=False, index=True)
    pdx_code = Column(String(10), nullable=False, index=True)
    edition = Column(String(20), nullable=True)


class DrgWeight(Base):
    """MS-DRG relative weights and lengths of stay, from IPPS Table 5."""

    __tablename__ = "drg_weights"

    id = Column(Integer, primary_key=True, index=True)
    drg_code = Column(String(5), nullable=False, unique=True, index=True)
    title = Column(Text, nullable=True)
    mdc = Column(String(4), nullable=True)
    drg_type = Column(String(12), nullable=True)      # MED · SURG
    relative_weight = Column(String(12), nullable=True)
    geometric_los = Column(String(12), nullable=True)
    arithmetic_los = Column(String(12), nullable=True)
    edition = Column(String(20), nullable=True)
