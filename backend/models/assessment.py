from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Boolean, ForeignKey, func, JSON
from sqlalchemy.orm import relationship
import enum
from database import Base


class AssessmentSpecialty(str, enum.Enum):
    ICD10CM = "ICD10CM"
    SURGERY = "Surgery"
    ED_FACILITY = "ED Facility"
    ED_PROFEE = "ED Profee"
    ANCILLARY = "Ancillary"
    IP_DRG = "IP-DRG"
    EM = "E&M"
    EM_MULTI = "E&M - Multispecialty"
    IVR = "IVR"
    ANESTHESIA = "Anesthesia"


class QuestionDifficulty(str, enum.Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class QuestionType(str, enum.Enum):
    CONCEPTUAL = "Conceptual"
    SCENARIO = "Scenario"
    RULE_BASED = "Rule-based"


class QuestionStatus(str, enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id = Column(Integer, primary_key=True)
    question_id = Column(String(20), unique=True, nullable=False, index=True)
    specialty = Column(String(50), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    correct_answer = Column(String(1), nullable=False)
    difficulty = Column(String(10), nullable=False)
    topic = Column(String(100), nullable=True)
    question_type = Column(String(20), nullable=False, default="Conceptual")
    status = Column(String(10), nullable=False, default="Active")
    shuffle_options = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AssessmentConfig(Base):
    __tablename__ = "assessment_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    total_questions = Column(Integer, nullable=False)
    student_count = Column(Integer, nullable=False, default=1)
    specialty_mix = Column(JSON, nullable=False)
    difficulty_mode = Column(String(10), nullable=False, default="auto")
    difficulty_mix = Column(JSON, nullable=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assessments = relationship("GeneratedAssessment", back_populates="config")


class GeneratedAssessment(Base):
    __tablename__ = "generated_assessments"

    id = Column(Integer, primary_key=True)
    config_id = Column(Integer, ForeignKey("assessment_configs.id"), nullable=True)
    assessment_name = Column(String(200), nullable=False)
    batch_name = Column(String(100), nullable=True)
    student_count = Column(Integer, nullable=False)
    generated_by = Column(String(100), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    randomisation_stats = Column(JSON, nullable=True)
    is_standalone = Column(Boolean, default=False, nullable=False)
    # The bar THIS assessment is judged against. Was a module constant of 90,
    # which is a punishing mark for MCQs and invisible to the trainer setting
    # the paper. Different assessments legitimately have different bars.
    pass_threshold = Column(Integer, nullable=True)

    config = relationship("AssessmentConfig", back_populates="assessments")
    students = relationship("GeneratedAssessmentStudent", back_populates="assessment", cascade="all, delete-orphan")


class GeneratedAssessmentStudent(Base):
    __tablename__ = "generated_assessment_students"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("generated_assessments.id"), nullable=False)
    student_label = Column(String(50), nullable=False)
    questions_json = Column(JSON, nullable=False)

    assessment = relationship("GeneratedAssessment", back_populates="students")


class AssessmentAuditLog(Base):
    __tablename__ = "assessment_audit_log"

    id = Column(Integer, primary_key=True)
    trainer_name = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    specialty = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AssessmentSession(Base):
    """One session = one coder taking one generated assessment."""
    __tablename__ = "assessment_sessions"

    id = Column(Integer, primary_key=True)
    session_token = Column(String(20), unique=True, nullable=False, index=True)
    assessment_id = Column(Integer, ForeignKey("generated_assessments.id"), nullable=False)
    coder_name = Column(String(100), nullable=False)
    employee_id = Column(String(50), nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    student_slot_id = Column(Integer, ForeignKey("generated_assessment_students.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    time_limit_ends_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    auto_submitted = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    last_saved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    responses = relationship("AssessmentResponse", back_populates="session", cascade="all, delete-orphan")
    result = relationship("AssessmentResult", back_populates="session", uselist=False, cascade="all, delete-orphan")


class AssessmentResponse(Base):
    """One row per question answered by a coder — upserted on each answer selection."""
    __tablename__ = "assessment_responses"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assessment_sessions.id"), nullable=False)
    question_index = Column(Integer, nullable=False)
    question_id = Column(String(20), nullable=False)
    selected_answer = Column(String(1), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    # A trainer's verdict, overriding the automatic one. NULL means "not
    # overridden" — deliberately tri-state, so an override to False is
    # distinguishable from never having been touched. The original is_correct
    # is left alone so the correction is auditable rather than destructive.
    override_is_correct = Column(Boolean, nullable=True)
    override_reason = Column(Text, nullable=True)
    override_by = Column(String(100), nullable=True)
    override_at = Column(DateTime(timezone=True), nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)

    session = relationship("AssessmentSession", back_populates="responses")


class AssessmentResult(Base):
    """Computed once on final submission."""
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assessment_sessions.id"), unique=True, nullable=False)
    total_questions = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    score_pct = Column(Float, nullable=False)
    time_taken_seconds = Column(Integer, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AssessmentSession", back_populates="result")
