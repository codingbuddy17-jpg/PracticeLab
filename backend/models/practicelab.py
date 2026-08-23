from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, func, JSON
)
from sqlalchemy.orm import relationship
import enum
from database import Base
from models.charts import Specialty


class BatchStatus(str, enum.Enum):
    OPEN = "Open"
    CLOSED = "Closed"


class SubmissionStatus(str, enum.Enum):
    PENDING = "Pending"
    SUBMITTED = "Submitted"


class PassFail(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class IssueType(str, enum.Enum):
    MISSED = "Missed"
    WRONG_CODE = "Wrong_Code"
    WRONG_POA = "Wrong_POA"
    WRONG_MODIFIER = "Wrong_Modifier"
    WRONG_POINTER = "Wrong_Pointer"   # professional claims: CPT line linked to wrong Dx
    OVER_CODED = "Over_coded"


class GradingSection(str, enum.Enum):
    PDX = "PDx"
    SDX = "SDx"
    PCS = "PCS"
    CPT = "CPT"


class AnswerKey(Base):
    """Master answer key per chart — permanent, one per chart number."""
    __tablename__ = "answer_keys"

    id = Column(Integer, primary_key=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False, unique=True)
    specialty = Column(SAEnum(Specialty), nullable=False)
    pdx_code = Column(String(20), nullable=True)
    pdx_poa = Column(String(5), nullable=True)
    sdx = Column(JSON, nullable=True, default=list)
    pcs = Column(JSON, nullable=True, default=list)
    cpt = Column(JSON, nullable=True, default=list)
    # ED Single Path only — the facility and professional E/M levels are coded
    # together from one chart and frequently diverge, which is the point of
    # single-path training. Null for every other specialty.
    facility_level = Column(String(20), nullable=True)
    profee_level = Column(String(20), nullable=True)
    # Whether this chart sits on the critical care boundary — the 99285 vs
    # 99291 judgement. Set by a trainer who has READ the chart, because nothing
    # else can tell: an answer key says which code is right, not whether the
    # question is a fair one to ask.
    #
    # The auditor generator plants that swap only where this says "borderline".
    # On a chart where critical care is plainly absent the planting is spotted
    # without reading anything, which teaches auditors to distrust the module
    # rather than to audit with it.
    cc_boundary = Column(String(20), nullable=True)
    entered_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    chart = relationship("Chart")


class Batch(Base):
    """
    A unit of assigned coding work: a set of coders, a pool of charts, and the
    scoring rules to grade them by.

    is_direct_assignment distinguishes the two flows a trainer sees. Both
    create, allocate, issue access codes, grade and report through identical
    code; the flag decides only the wording on screen and whether the work
    counts toward cohort analytics. A one-off refresher for a single coder
    should not move a team's averages.

    Charts are not assigned at creation. That happens per allocation cycle, so
    a batch can be topped up over weeks without a coder ever repeating a chart.
    """

    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)
    categories = Column(JSON, nullable=True, default=list)
    difficulties = Column(JSON, nullable=True, default=list)
    charts_per_coder = Column(Integer, nullable=False)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(SAEnum(BatchStatus, native_enum=False), default=BatchStatus.OPEN, nullable=False, index=True)
    use_weighted = Column(Boolean, nullable=False, default=True)
    use_dpo = Column(Boolean, nullable=False, default=False)
    is_direct_assignment = Column(Boolean, nullable=False, default=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(100), nullable=True)
    force_closed = Column(Boolean, default=False, nullable=False)
    force_close_reason = Column(Text, nullable=True)
    notes = Column(JSON, nullable=True, default=list)
    tags = Column(JSON, nullable=True, default=list)

    coders = relationship("BatchCoder", back_populates="batch", cascade="all, delete-orphan")
    chart_assignments = relationship("BatchChart", back_populates="batch", cascade="all, delete-orphan")
    results = relationship("GradingResult", back_populates="batch", cascade="all, delete-orphan")
    allocation_cycles = relationship("BatchAllocationCycle", back_populates="batch", cascade="all, delete-orphan")


class BatchAllocationCycle(Base):
    """One round of chart randomization within an open batch."""
    __tablename__ = "batch_allocation_cycles"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    cycle_number = Column(Integer, nullable=False)
    run_at = Column(DateTime(timezone=True), server_default=func.now())
    run_by = Column(String(100), nullable=False)
    charts_per_coder = Column(Integer, nullable=False)
    notes = Column(String(300), nullable=True)
    randomisation_stats = Column(JSON, nullable=True)
    # Shortfall warnings raised during this allocation. Previously these were
    # only toasts — six seconds and gone — so a trainer who stepped away had no
    # way to discover afterwards that some coders got fewer charts than asked.
    warnings = Column(JSON, nullable=True)
    # Per-coder pool state at the time of this cycle: how many unseen charts
    # they had left, which recycled round they are on, and a sentence saying
    # so. Kept per cycle because a coder's pool empties on their own schedule.
    coder_pool_notes = Column(JSON, nullable=True)

    batch = relationship("Batch", back_populates="allocation_cycles")
    assignments = relationship("BatchChart", back_populates="cycle")


class BatchCoder(Base):
    """
    A coder on a batch's roster.

    emp_id is the stable identity where an organisation issues one; coder_name
    is free text and two people can share it. Reporting keys on emp_id when
    present and falls back to the name, so this row is where that identity is
    captured.
    """

    __tablename__ = "batch_coders"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    coder_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)

    batch = relationship("Batch", back_populates="coders")


class BatchChart(Base):
    """
    One chart assigned to one coder, in one allocation cycle.

    The uniqueness guarantee lives here: allocation excludes every chart a
    coder already has a row for in this batch, so nothing repeats while
    anything unseen remains. Two coders holding the same chart in one cycle is
    intended — it is the only way their answers on it can be compared.

    submission_status is a vestige of the removed offline Excel workflow.
    Nothing sets it to SUBMITTED outside the Edits/Denials rubric path; graded
    work is determined from GradingResult.
    """

    __tablename__ = "batch_charts"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("batch_allocation_cycles.id"), nullable=True)
    coder_name = Column(String(100), nullable=False)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    submission_status = Column(SAEnum(SubmissionStatus), default=SubmissionStatus.PENDING, nullable=False)

    batch = relationship("Batch", back_populates="chart_assignments")
    cycle = relationship("BatchAllocationCycle", back_populates="assignments")
    chart = relationship("Chart")


class Submission(Base):
    """
    A coder's submitted codes for one chart, from the removed offline Excel
    workflow.

    Retained for historical records. Current work is captured by the
    practice-session tables and mirrored into GradingResult; nothing writes
    here any more.
    """

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    coder_name = Column(String(100), nullable=False)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)
    pdx_code = Column(String(20), nullable=True)
    pdx_poa = Column(String(5), nullable=True)
    sdx = Column(JSON, nullable=True, default=list)
    pcs = Column(JSON, nullable=True, default=list)
    cpt = Column(JSON, nullable=True, default=list)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    chart = relationship("Chart")
    result = relationship("GradingResult", back_populates="submission", uselist=False)


class GradingResult(Base):
    """
    The score for one coder on one chart. The reporting table.

    Every analytics endpoint and both PDF reports read this, whichever flow
    produced the work: in-browser practice results are mirrored here as they
    are graded, and historical rows were backfilled. Keyed on
    (batch_id, coder_name, chart_id), so re-grading updates in place.

    Two scoring schemes sit side by side and answer different questions.
    total_score is the weighted score against the configured component
    weights. The dpo_* columns are Diagnosis/POA/Procedure accuracy —
    proportion of codes correct — kept as raw correct/total counts as well as
    percentages so cumulative figures aggregate correctly rather than
    averaging averages.
    """

    __tablename__ = "grading_results"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=True)
    coder_name = Column(String(100), nullable=False)
    # Stable identity. coder_name is free text, so "John Smith" / "john smith" /
    # "Smith, John" fork one person's history and two real people sharing a name
    # merge into one. Analytics prefer emp_id and fall back to the name for rows
    # that predate it or coders enrolled without one.
    emp_id = Column(String(50), nullable=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)
    pdx_score = Column(Integer, default=0)
    sdx_score = Column(Integer, default=0)
    pcs_score = Column(Integer, nullable=True)
    cpt_score = Column(Integer, nullable=True)
    drg_score = Column(Integer, nullable=True)
    drg_flag = Column(Boolean, default=False)
    drg_reviewed = Column(Boolean, default=False)
    drg_override = Column(String(5), nullable=True)
    drg_reviewed_by = Column(String(100), nullable=True)
    drg_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    total_score = Column(Integer, nullable=True)
    pass_fail = Column(SAEnum(PassFail), nullable=True)
    graded_at = Column(DateTime(timezone=True), server_default=func.now())
    dpo_dx_accuracy = Column(Float, nullable=True)
    dpo_poa_accuracy = Column(Float, nullable=True)
    dpo_proc_accuracy = Column(Float, nullable=True)
    dpo_overall_accuracy = Column(Float, nullable=True)
    dpo_dx_correct = Column(Integer, nullable=True)
    dpo_dx_total = Column(Integer, nullable=True)
    dpo_poa_correct = Column(Integer, nullable=True)
    dpo_poa_total = Column(Integer, nullable=True)
    dpo_proc_correct = Column(Integer, nullable=True)
    dpo_proc_total = Column(Integer, nullable=True)

    batch = relationship("Batch", back_populates="results")
    submission = relationship("Submission", back_populates="result")
    chart = relationship("Chart")
    feedback = relationship("GradingFeedback", back_populates="result", cascade="all, delete-orphan")
    ed_rubric = relationship("EDRubricDetail", back_populates="result", uselist=False, cascade="all, delete-orphan")


class GradingFeedback(Base):
    """
    One specific mistake on one graded chart — what the key said, what the
    coder wrote, and which kind of error it was.

    This is what a coder reads to learn from, and what the Error Analysis
    reporting aggregates over. E/M grading emits free-text issues that do not
    map to the IssueType enum; those stay in the practice-result payload and
    are not written here.
    """

    __tablename__ = "grading_feedback"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("grading_results.id"), nullable=False)
    section = Column(SAEnum(GradingSection), nullable=False)
    issue_type = Column(SAEnum(IssueType), nullable=False)
    ak_code = Column(String(50), nullable=True)
    coder_code = Column(String(50), nullable=True)
    # Text, not String(200): this is prose the grader writes, and SQLite does
    # not enforce the length, so the ceiling was invisible until PostgreSQL
    # rejected a row. Today's messages are short ("3 extra code(s) submitted"),
    # which is exactly why a bigger number would only move the day it happens.
    detail = Column(Text, nullable=True)

    result = relationship("GradingResult", back_populates="feedback")


class EDRubricDetail(Base):
    """Per-chart manual rubric grading record for Edits/Denials specialties."""
    __tablename__ = "ed_rubric_details"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("grading_results.id"), nullable=False, unique=True)
    review_pass = Column(Boolean, nullable=False, default=False)
    research_coding_pass = Column(Boolean, nullable=False, default=False)
    research_payer_pass = Column(Boolean, nullable=False, default=False)
    research_nuances_pass = Column(Boolean, nullable=False, default=False)
    resolution_pass = Column(Boolean, nullable=False, default=False)
    rationale_tier = Column(String(20), nullable=False, default="not_acceptable")
    trainer_note = Column(Text, nullable=True)
    graded_by = Column(String(100), nullable=False)
    graded_at = Column(DateTime(timezone=True), server_default=func.now())

    result = relationship("GradingResult", back_populates="ed_rubric")


class SelfPracticeSubmission(Base):
    """Coder-initiated or trainer standalone grading outside of any batch."""
    __tablename__ = "self_practice_submissions"

    id = Column(Integer, primary_key=True, index=True)
    coder_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)
    source = Column(String(20), nullable=False, default="coder")
    status = Column(String(20), nullable=False, default="pending_review")
    trainer_feedback = Column(Text, nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    results = relationship("SelfPracticeResult", back_populates="submission", cascade="all, delete-orphan")


class SelfPracticeResult(Base):
    """Per-chart grading result for a self-practice or standalone submission."""
    __tablename__ = "self_practice_results"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("self_practice_submissions.id"), nullable=False)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=True)
    chart_number = Column(String(20), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=True)
    weighted_score = Column(Integer, nullable=True)
    pass_fail = Column(SAEnum(PassFail), nullable=True)
    dpo_dx_accuracy = Column(Float, nullable=True)
    dpo_poa_accuracy = Column(Float, nullable=True)
    dpo_proc_accuracy = Column(Float, nullable=True)
    dpo_overall_accuracy = Column(Float, nullable=True)
    error_message = Column(String(300), nullable=True)
    feedback_items = Column(JSON, nullable=True, default=list)

    submission = relationship("SelfPracticeSubmission", back_populates="results")
    chart = relationship("Chart")


class ScoringConfig(Base):
    """
    How a specialty type is scored: component weights, pass mark and which
    scoring methods are enabled.

    One row per specialty_type — IP, OP, EDSP — not per specialty. Weights
    must total 100, which the update endpoint enforces.

    Changes apply to gradings performed afterwards. Results already stored
    keep the scores they were given, so a config change cannot silently
    restate a closed batch.
    """

    __tablename__ = "scoring_configs"

    id = Column(Integer, primary_key=True, index=True)
    specialty_type = Column(String(10), nullable=False, unique=True)
    pdx_weight = Column(Integer, nullable=False, default=20)
    sdx_weight = Column(Integer, nullable=False, default=20)
    pcs_weight = Column(Integer, nullable=True)
    drg_weight = Column(Integer, nullable=True)
    cpt_weight = Column(Integer, nullable=True)
    facility_level_weight = Column(Integer, nullable=True)
    profee_level_weight = Column(Integer, nullable=True)
    pass_threshold = Column(Integer, nullable=False, default=80)
    drg_triggers = Column(JSON, nullable=True, default=list)
    overcoding_penalty = Column(Boolean, nullable=False, default=True)
    weighted_enabled = Column(Boolean, nullable=False, default=True)
    dpo_enabled = Column(Boolean, nullable=False, default=True)
    dpo_pass_threshold = Column(Float, nullable=False, default=80.0)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CodingResource(Base):
    """
    A reference link a trainer publishes to coders — guidelines, a coding
    manual, an internal policy page. Display order is manual via sort_order.
    """

    __tablename__ = "coding_resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    url = Column(String(1000), nullable=False)
    created_by = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
