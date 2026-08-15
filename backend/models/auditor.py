"""
Auditor module — the inverse of the coder workflow.

A chart arrives already coded, with errors planted in it, and the auditor must
find and fix them. Everything here is deliberately separate from the coder
tables: a shared `batches` table with a mode column would need a filter on every
existing query, and one missed filter mixes audit work into coder analytics.
Assessment set the precedent by keeping its own sessions and results, and the
two modules have never contaminated each other's numbers.

What IS shared: charts, answer keys, and the allocation algorithm — logic, not
storage.
"""

from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, func, JSON
)
from sqlalchemy.orm import relationship
import enum

from database import Base
from models.charts import Specialty
from models.practicelab import BatchStatus, PassFail


class AuditSource(str, enum.Enum):
    """
    Where an assignment's claim came from. Stamped at allocation, never
    inferred by counting mutations — a bug that dropped mutations would
    otherwise be indistinguishable from a deliberately clean chart.
    """
    CLEAN = "Clean"     # zero mutations, drawn by the clean quota
    MANUAL = "Manual"   # from a trainer-authored audit key set
    AUTO = "Auto"       # generated at allocation, from a seed


class AuditAction(str, enum.Enum):
    """
    The auditor's vocabulary, and the shape ground truth is stored in. These
    are what auditors actually do to a coded chart, which is why the interface
    and the answer use the same three words.
    """
    ADD = "Add"         # a code was omitted from the claim
    REVISE = "Revise"   # a code or one of its fields is wrong
    DELETE = "Delete"   # a code is on the claim that should not be


class AuditKeySet(Base):
    """
    A trainer-authored set of plantings for one chart — the permanent library
    layer, sitting beside answer_keys.

    A chart may hold several named sets ("IP001 — foundational", "IP001 — DRG
    impact"), so one chart yields several distinct exercises. Editing or
    deleting a set affects future allocations only; assignments already made
    keep their frozen copy.

    mutations is a list in the same shape the generator emits, so scoring and
    the auditor interface never know which produced a given claim:

        {"section": "SDx", "action": "Add",    "correct_value": "N17.9"}
        {"section": "CPT", "action": "Revise", "line": 2, "field": "modifier",
         "claim_value": "59", "correct_value": "51"}
        {"section": "SDx", "action": "Delete", "line": 4, "claim_value": "I10"}

    claim_value is what the flawed claim shows; correct_value is what it should
    be. Named that way rather than was/now because nothing here is temporal —
    both values coexist, one on the claim and one in the truth.

    A set may legitimately carry ZERO mutations while still setting
    query_expected — a correctly coded claim that nonetheless needs a physician
    query. That is a curated clean chart, and it is why "clean" and "manual"
    are not mutually exclusive.
    """

    __tablename__ = "audit_key_sets"

    id = Column(Integer, primary_key=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    mutations = Column(JSON, nullable=False, default=list)
    # IP-DRG only. None means "no query determination authored for this set",
    # which scores as NA rather than as False — the system cannot read whether
    # documentation supported a code, so an unauthored answer is not an answer.
    query_expected = Column(Boolean, nullable=True)
    query_rationale = Column(Text, nullable=True)
    # Exempts this set from the clean quota, so it is always planted when drawn.
    # Use sparingly: curated charts that never come up clean become a tell.
    always_plant = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    authored_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    chart = relationship("Chart")


class AuditBatch(Base):
    """
    A unit of assigned audit work: a set of auditors, a pool of charts, and the
    planting rules to build their claims from.

    Mirrors Batch in shape but never shares its rows. Charts are not assigned
    at creation — that happens per allocation cycle, so a batch can be topped
    up over weeks without an auditor repeating a chart or a mutation set.
    """

    __tablename__ = "audit_batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)
    categories = Column(JSON, nullable=True, default=list)
    difficulties = Column(JSON, nullable=True, default=list)
    charts_per_auditor = Column(Integer, nullable=False, default=5)
    status = Column(SAEnum(BatchStatus), nullable=False, default=BatchStatus.OPEN)

    # How each allocation resolves its chart mix:
    #   auto    — system decides the mix, the charts and the mutations
    #   guided  — trainer sets HOW MANY of each type, system picks WHICH
    #   manual  — trainer picks the charts and their types
    # Guided is the workhorse: a trainer running 8 auditors x 5 charts has an
    # intent but no appetite for picking 40 charts.
    allocation_mode = Column(String(20), nullable=False, default="guided")
    # Guided mode quotas, per auditor. Null in the other modes.
    quota_clean = Column(Integer, nullable=True)
    quota_manual = Column(Integer, nullable=True)
    quota_auto = Column(Integer, nullable=True)
    # Share of charts drawn clean when the system decides the mix. Drawn as a
    # QUOTA rounded down, not a per-chart coin flip: a 50% roll on five charts
    # can land on zero or five clean by chance. Flooring also guarantees at
    # least one opportunity chart per session at any share below 100%.
    # 30, not 50. The pass/fail verdict is decided on the Review Score, whose
    # denominator is every code line — and clean charts are all-correct lines.
    # At a 50% clean share an auditor who flags nothing scores 90.1% and
    # passes; at 30% they score 85.5% and fail, which is the whole point.
    clean_share = Column(Integer, nullable=False, default=30)
    difficulty_tier = Column(String(20), nullable=True)
    # Whether auditors see their own results after submitting. On by default —
    # seeing what you missed is most of the learning — but a trainer recycling
    # a chart may want it off, since the missed-findings list describes what
    # was in that chart. Versions blunt this: a chart met again carries
    # different errors.
    show_results_to_auditor = Column(Boolean, nullable=False, default=False)

    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(100), nullable=True)
    force_closed = Column(Boolean, nullable=False, default=False)
    force_close_reason = Column(Text, nullable=True)
    notes = Column(JSON, nullable=True, default=list)
    tags = Column(JSON, nullable=True, default=list)


class AuditBatchAuditor(Base):
    """One auditor on the roster of one audit batch."""

    __tablename__ = "audit_batch_auditors"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("audit_batches.id"), nullable=False, index=True)
    auditor_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditAllocationCycle(Base):
    """
    One run of the allocator over a batch. Charts are drawn least-seen-first
    per auditor, and the seed for generated mutations is derived from
    (chart, cycle) — so the same chart in a later cycle carries different
    errors without any extra bookkeeping.
    """

    __tablename__ = "audit_allocation_cycles"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("audit_batches.id"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    run_at = Column(DateTime(timezone=True), server_default=func.now())
    run_by = Column(String(100), nullable=True)
    charts_allocated = Column(Integer, nullable=False, default=0)
    pool_notes = Column(JSON, nullable=True, default=list)


class AuditAssignment(Base):
    """
    One chart as one auditor will see it — the frozen layer.

    Both the rendered claim AND the ground truth are written here at
    allocation and never recomputed. Freezing the claim as well as the
    mutation list matters: deriving it later from the answer key would shift
    what the auditor saw if that key were edited in the meantime.

    The precedent is generated_assessment_students.questions_json, which
    freezes each coder's question set so that editing a question afterwards
    cannot change a paper already sat. Same reasoning: scoring never
    re-derives, key edits cannot retroactively change a completed audit, and a
    disputed finding stays reproducible months later.
    """

    __tablename__ = "audit_assignments"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("audit_batches.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("audit_allocation_cycles.id"), nullable=True)
    auditor_name = Column(String(100), nullable=False, index=True)
    emp_id = Column(String(50), nullable=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)

    source = Column(SAEnum(AuditSource), nullable=False)
    set_id = Column(Integer, ForeignKey("audit_key_sets.id"), nullable=True)
    seed = Column(Integer, nullable=True)

    # The claim as presented to the auditor: pdx/sdx/pcs/cpt after mutation.
    claim = Column(JSON, nullable=False, default=dict)
    # What the auditor must find, in the same {section, action, ...} shape.
    # An empty list is a clean chart and is entirely normal.
    ground_truth = Column(JSON, nullable=False, default=list)
    # IP-DRG only, and only where a manual set authored an answer. NULL means
    # NA — not scored, not counted against the auditor.
    query_expected = Column(Boolean, nullable=True)

    # Regeneration is allowed until the auditor opens the chart, then locked.
    opened_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chart = relationship("Chart")


class AuditSession(Base):
    """
    An auditor's working session, reached by access code exactly as a coder
    reaches theirs. The code is the only credential; there is no login.
    """

    __tablename__ = "audit_sessions"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("audit_batches.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("audit_allocation_cycles.id"), nullable=True)
    auditor_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)
    specialty = Column(SAEnum(Specialty), nullable=False)
    token = Column(String(40), nullable=False, unique=True, index=True)
    chart_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="in_progress")
    show_results_to_auditor = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditChartDraft(Base):
    """
    Work in progress on one chart — saved as the auditor types so a lost
    connection costs nothing. Superseded by AuditResult on submit.

    section_verdicts is the gate that makes a blank submission meaningful:
    every section must carry "no changes" or "needs changes" before the chart
    can be submitted, so silence becomes an explicit claim rather than an
    absence.

        {"SDx": "no_changes", "PCS": "needs_changes"}

    findings holds what they actually recorded, in the same shape as ground
    truth so scoring is a comparison rather than a translation.
    """

    __tablename__ = "audit_chart_drafts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("audit_sessions.id"), nullable=False, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    section_verdicts = Column(JSON, nullable=False, default=dict)
    findings = Column(JSON, nullable=False, default=list)
    query_flag = Column(Boolean, nullable=False, default=False)
    query_text = Column(Text, nullable=True)
    auditor_notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditResult(Base):
    """
    The scored outcome for one chart in one session.

    Component accuracies are stored as nullable Floats because NA is a real
    value here, distinct from zero: a chart with no spurious codes planted has
    no Delete accuracy, and its 20% weight redistributes across the components
    that do exist. Writing 0.0 would silently mark the auditor wrong for an
    opportunity that never existed.

    is_clean is stored rather than derived from ground_truth being empty, for
    the same reason AuditAssignment.source is stamped: the two must never be
    told apart by counting rows.
    """

    __tablename__ = "audit_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("audit_sessions.id"), nullable=False, index=True)
    assignment_id = Column(Integer, ForeignKey("audit_assignments.id"), nullable=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("audit_batches.id"), nullable=False, index=True)
    auditor_name = Column(String(100), nullable=False, index=True)
    emp_id = Column(String(50), nullable=True)
    specialty = Column(SAEnum(Specialty), nullable=False)
    is_clean = Column(Boolean, nullable=False, default=False)

    add_planted = Column(Integer, nullable=False, default=0)
    add_found = Column(Integer, nullable=False, default=0)
    add_accuracy = Column(Float, nullable=True)
    revise_planted = Column(Integer, nullable=False, default=0)
    revise_found = Column(Integer, nullable=False, default=0)
    revise_accuracy = Column(Float, nullable=True)
    delete_planted = Column(Integer, nullable=False, default=0)
    delete_found = Column(Integer, nullable=False, default=0)
    delete_accuracy = Column(Float, nullable=True)

    # Findings raised on things that were never planted.
    over_calls = Column(Integer, nullable=False, default=0)
    over_call_tier = Column(String(20), nullable=True)     # revenue | non_revenue
    over_call_deduction = Column(Float, nullable=False, default=0.0)

    query_expected = Column(Boolean, nullable=True)
    query_flagged = Column(Boolean, nullable=True)
    query_correct = Column(Boolean, nullable=True)          # None = NA
    query_deduction = Column(Float, nullable=False, default=0.0)

    # Detected the right line but corrected it wrongly. Not scored — reported,
    # because "found 4 of 4, corrected 2" and "found 2 of 4" both come out at
    # 50% and are entirely different coaching conversations.
    detected_not_corrected = Column(Integer, nullable=False, default=0)
    drg_impacting_planted = Column(Integer, nullable=False, default=0)
    drg_impacting_found = Column(Integer, nullable=False, default=0)

    audit_accuracy = Column(Float, nullable=False, default=0.0)

    # Review scoring — the second scheme, mirroring the coder's DPO columns.
    # Raw counts as well as the percentage, so a cohort pools them instead of
    # averaging averages. The denominator is CODE LINES; POA, modifiers and
    # units are attributes of a line and are reported in review_attributes
    # with their own percentages rather than inflating the total.
    review_total = Column(Integer, nullable=True)
    review_correct = Column(Integer, nullable=True)
    review_score = Column(Float, nullable=True)
    review_sections = Column(JSON, nullable=True)
    review_attributes = Column(JSON, nullable=True)
    pass_fail = Column(SAEnum(PassFail), nullable=True)
    findings = Column(JSON, nullable=True, default=list)
    feedback = Column(JSON, nullable=True, default=list)
    scored_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditScoringConfig(Base):
    """
    Tunable scoring and mutation parameters. One row, id=1.

    Separate from ScoringConfig because nothing overlaps: the coder config
    weights code sections, this one weights auditor ACTIONS and sizes
    deductions. Changes apply to audits scored afterwards; results already
    stored keep the scores they were given, so a config change cannot silently
    restate a closed batch.
    """

    __tablename__ = "audit_scoring_configs"

    id = Column(Integer, primary_key=True, index=True)

    # Component weights. Renormalised over the components a chart actually
    # planted, so a chart with no spurious codes splits Delete's share between
    # Add and Revise rather than penalising an absent opportunity.
    add_weight = Column(Integer, nullable=False, default=40)
    revise_weight = Column(Integer, nullable=False, default=40)
    delete_weight = Column(Integer, nullable=False, default=20)

    # One deduction per chart, sized by the worst category over-called — not
    # per finding. Identical on clean and opportunity charts.
    over_call_revenue_pct = Column(Integer, nullable=False, default=20)
    over_call_non_revenue_pct = Column(Integer, nullable=False, default=5)
    # Which elements count as revenue-impacting. Modifier and units are in by
    # default: a wrong modifier drives denials and wrong units are overbilling.
    revenue_elements = Column(JSON, nullable=False,
                              default=lambda: ["pdx", "ccmcc_sdx", "pcs", "cpt",
                                               "modifier", "units"])

    # Query is binary per chart, so it is a fixed deduction rather than a
    # fourth weighted component — folding a 0-or-100 value into the weighted
    # mean would swing scores violently. Symmetric: wrong in either direction
    # is one error of judgement.
    query_missed_pct = Column(Integer, nullable=False, default=20)
    query_unnecessary_pct = Column(Integer, nullable=False, default=20)

    pass_threshold = Column(Integer, nullable=False, default=90)
    # Pass/fail is withheld below this many opportunities in a session. Chart
    # scores are quantised by planting count, so a verdict on a two-planting
    # session would be noise dressed as judgement.
    min_opportunities_for_verdict = Column(Integer, nullable=False, default=20)
    # The verdict is decided on the Review Score, which has roughly four times
    # the opportunities per chart that detection has. Fifty is about five
    # charts — the same length already suggested at batch creation.
    min_review_opportunities = Column(Integer, nullable=False, default=50)

    # Mutation mix. Must total 100; renormalised per chart over the mutations
    # that chart can actually support.
    mix_omit_sdx = Column(Integer, nullable=False, default=35)
    mix_omit_proc = Column(Integer, nullable=False, default=18)
    mix_modifier_missing = Column(Integer, nullable=False, default=8)
    mix_modifier_wrong = Column(Integer, nullable=False, default=7)
    mix_substitute = Column(Integer, nullable=False, default=7)
    # ICD-10-PCS single-character mutation, weighted separately from diagnosis
    # substitution. As a fallback inside it, this never fired.
    mix_substitute_pcs = Column(Integer, nullable=False, default=5)
    mix_swap_pdx = Column(Integer, nullable=False, default=5)
    mix_units = Column(Integer, nullable=False, default=3)
    mix_poa = Column(Integer, nullable=False, default=2)
    mix_spurious = Column(Integer, nullable=False, default=10)

    # No ceiling applies to manual plantings — a trainer authoring a set has
    # read the chart and has a reason. This caps generation only.
    max_auto_plantings = Column(Integer, nullable=False, default=10)
    # Where real coder mistakes have been observed on a chart, how much of
    # its budget prefers them over synthetic mutation. A demonstrated error
    # beats a guessed one; synthetic fills whatever budget is left over.
    observed_share_pct = Column(Integer, nullable=False, default=100)
    max_section_share = Column(Integer, nullable=False, default=30)
    ccmcc_preference = Column(Integer, nullable=False, default=3)

    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
