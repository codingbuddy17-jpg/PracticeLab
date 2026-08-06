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
    entered_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    chart = relationship("Chart")


class Batch(Base):
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

    batch = relationship("Batch", back_populates="allocation_cycles")
    assignments = relationship("BatchChart", back_populates="cycle")


class BatchCoder(Base):
    __tablename__ = "batch_coders"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    coder_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)

    batch = relationship("Batch", back_populates="coders")


class BatchChart(Base):
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
    __tablename__ = "grading_feedback"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("grading_results.id"), nullable=False)
    section = Column(SAEnum(GradingSection), nullable=False)
    issue_type = Column(SAEnum(IssueType), nullable=False)
    ak_code = Column(String(50), nullable=True)
    coder_code = Column(String(50), nullable=True)
    detail = Column(String(200), nullable=True)

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
    __tablename__ = "coding_resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    url = Column(String(1000), nullable=False)
    created_by = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
