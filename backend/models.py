from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, func, JSON
)
from sqlalchemy.orm import relationship
import enum
from database import Base


class Specialty(str, enum.Enum):
    IP_DRG = "IP-DRG"
    ED_FACILITY = "ED Facility"
    ED_PROFEE = "ED Profee"
    SDS = "SDS"
    EDITS = "Edits"
    DENIALS = "Denials"
    ANCILLARY = "Ancillary"
    EM = "E/M"


SPECIALTY_PREFIX = {
    "IP": Specialty.IP_DRG,
    "ED": Specialty.ED_FACILITY,
    "EDP": Specialty.ED_PROFEE,
    "SDS": Specialty.SDS,
    "EDT": Specialty.EDITS,
    "DEN": Specialty.DENIALS,
    "ANC": Specialty.ANCILLARY,
    "EM": Specialty.EM,
}

PREFIX_FOR_SPECIALTY = {v: k for k, v in SPECIALTY_PREFIX.items()}


class Difficulty(str, enum.Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class ChartStatus(str, enum.Enum):
    ACTIVE = "Active"
    RETIRED = "Retired"


class Chart(Base):
    __tablename__ = "charts"

    id = Column(Integer, primary_key=True, index=True)
    chart_number = Column(String(20), unique=True, nullable=False, index=True)
    specialty = Column(SAEnum(Specialty), nullable=False, index=True)
    category = Column(String(200), nullable=False, index=True)
    difficulty = Column(SAEnum(Difficulty), nullable=False, index=True)
    rationale = Column(Text, nullable=True)
    status = Column(SAEnum(ChartStatus), default=ChartStatus.ACTIVE, nullable=False, index=True)
    uploaded_by = Column(String(100), nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    files = relationship("ChartFile", back_populates="chart", cascade="all, delete-orphan", order_by="ChartFile.page_order")
    audit_logs = relationship("AuditLog", back_populates="chart", cascade="all, delete-orphan")


class ChartFile(Base):
    __tablename__ = "chart_files"

    id = Column(Integer, primary_key=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    storage_key = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    page_order = Column(Integer, default=0, nullable=False)
    total_pages = Column(Integer, default=1, nullable=False)
    page_text = Column(Text, nullable=True)
    uploaded_by = Column(String(100), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    chart = relationship("Chart", back_populates="files")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    action = Column(String(50), nullable=False)
    actor = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chart = relationship("Chart", back_populates="audit_logs")


class FeedbackStatus(str, enum.Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"


class ChartFeedback(Base):
    __tablename__ = "chart_feedback"

    id = Column(Integer, primary_key=True, index=True)
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    chart_number = Column(String(20), nullable=False)
    reporter = Column(String(100), nullable=False)
    issues = Column(String(500), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(SAEnum(FeedbackStatus), default=FeedbackStatus.OPEN, nullable=False, index=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChartSequence(Base):
    """Tracks the last used sequence number per specialty prefix."""
    __tablename__ = "chart_sequences"

    prefix = Column(String(10), primary_key=True)
    last_number = Column(Integer, default=0, nullable=False)


# ── PracticeLab Assessment Module ────────────────────────────────────────────

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
    # IP + OP
    pdx_code = Column(String(20), nullable=True)
    pdx_poa = Column(String(5), nullable=True)          # IP only: Y/N/U/W/1
    # JSON arrays:
    # IP sdx: [{code, poa, ccmcc}]   OP sdx: [{code}]
    sdx = Column(JSON, nullable=True, default=list)
    # IP pcs: [{code}]
    pcs = Column(JSON, nullable=True, default=list)
    # OP cpt: [{code, modifier}]
    cpt = Column(JSON, nullable=True, default=list)
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
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(100), nullable=True)
    force_closed = Column(Boolean, default=False, nullable=False)
    force_close_reason = Column(Text, nullable=True)
    notes = Column(JSON, nullable=True, default=list)   # [{text, author, ts}]
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

    batch = relationship("Batch", back_populates="allocation_cycles")
    assignments = relationship("BatchChart", back_populates="cycle")


class BatchCoder(Base):
    __tablename__ = "batch_coders"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    coder_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)
    excel_generated_at = Column(DateTime(timezone=True), nullable=True)

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
    chart_id = Column(Integer, ForeignKey("charts.id"), nullable=False)
    specialty = Column(SAEnum(Specialty), nullable=False)
    pdx_score = Column(Integer, default=0)
    sdx_score = Column(Integer, default=0)
    pcs_score = Column(Integer, nullable=True)    # IP only
    cpt_score = Column(Integer, nullable=True)    # OP only
    drg_score = Column(Integer, nullable=True)    # IP only, null until reviewed
    drg_flag = Column(Boolean, default=False)
    drg_reviewed = Column(Boolean, default=False)
    drg_override = Column(String(5), nullable=True)  # Y/N trainer decision
    total_score = Column(Integer, nullable=True)  # null until finalized
    pass_fail = Column(SAEnum(PassFail), nullable=True)
    graded_at = Column(DateTime(timezone=True), server_default=func.now())
    # DPO supplementary accuracy (null when batch.use_dpo=False)
    dpo_dx_accuracy = Column(Float, nullable=True)    # Dx code accuracy 0–100
    dpo_poa_accuracy = Column(Float, nullable=True)   # POA accuracy 0–100 (IP only)
    dpo_proc_accuracy = Column(Float, nullable=True)  # PCS or CPT accuracy 0–100
    dpo_overall_accuracy = Column(Float, nullable=True)

    batch = relationship("Batch", back_populates="results")
    submission = relationship("Submission", back_populates="result")
    chart = relationship("Chart")
    feedback = relationship("GradingFeedback", back_populates="result", cascade="all, delete-orphan")


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


class SelfPracticeSubmission(Base):
    """Coder-initiated or trainer standalone grading outside of any batch."""
    __tablename__ = "self_practice_submissions"

    id = Column(Integer, primary_key=True, index=True)
    coder_name = Column(String(100), nullable=False)
    emp_id = Column(String(50), nullable=True)
    source = Column(String(20), nullable=False, default="coder")  # 'coder' | 'trainer'
    status = Column(String(20), nullable=False, default="pending_review")  # 'pending_review' | 'released'
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
    Admin-configurable scoring weights per specialty type (IP or OP).
    Grading engine reads this at batch creation time; stored as a snapshot
    on GradingResult so historical results are never affected by config changes.
    """
    __tablename__ = "scoring_configs"

    id = Column(Integer, primary_key=True, index=True)
    specialty_type = Column(String(10), nullable=False, unique=True)  # "IP" or "OP"
    # Weights (must sum to 100)
    pdx_weight = Column(Integer, nullable=False, default=20)
    sdx_weight = Column(Integer, nullable=False, default=20)
    pcs_weight = Column(Integer, nullable=True)   # IP only
    drg_weight = Column(Integer, nullable=True)   # IP only
    cpt_weight = Column(Integer, nullable=True)   # OP only
    pass_threshold = Column(Integer, nullable=False, default=80)
    # DRG flag triggers (IP only) — JSON list of enabled trigger names
    drg_triggers = Column(JSON, nullable=True, default=list)
    # Toggle overcoding penalty
    overcoding_penalty = Column(Boolean, nullable=False, default=True)
    # Method availability toggles (admin-controlled, affect future batches only)
    weighted_enabled = Column(Boolean, nullable=False, default=True)
    dpo_enabled = Column(Boolean, nullable=False, default=True)
    # DPO pass threshold expressed as accuracy % (e.g. 80.0 = pass if overall accuracy ≥ 80%)
    dpo_pass_threshold = Column(Float, nullable=False, default=80.0)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
