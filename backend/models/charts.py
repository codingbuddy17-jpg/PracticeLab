from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Enum as SAEnum, func
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
    SURGERY = "Surgery"
    ED_SINGLE_PATH = "ED Single Path"


SPECIALTY_PREFIX = {
    "IP": Specialty.IP_DRG,
    "ED": Specialty.ED_FACILITY,
    "EDP": Specialty.ED_PROFEE,
    "EDSP": Specialty.ED_SINGLE_PATH,
    "SDS": Specialty.SDS,
    "SURG": Specialty.SURGERY,
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
    """
    A de-identified clinical chart that coders practise on.

    The record only; the pages themselves are images in object storage, one
    ChartFile row each. chart_number is the human identifier a trainer and
    coder both use (IP001, SURG042) and is issued per specialty by
    ChartSequence; `id` is what storage keys are built from.

    Retiring a chart sets status rather than deleting the row, so results
    already graded against it keep pointing at something.
    """

    __tablename__ = "charts"

    id = Column(Integer, primary_key=True, index=True)
    chart_number = Column(String(20), unique=True, nullable=False, index=True)
    specialty = Column(SAEnum(Specialty), nullable=False, index=True)
    category = Column(String(200), nullable=False, index=True)
    difficulty = Column(SAEnum(Difficulty), nullable=False, index=True)
    alias = Column(String(100), nullable=True)
    rationale = Column(Text, nullable=True)
    status = Column(SAEnum(ChartStatus), default=ChartStatus.ACTIVE, nullable=False, index=True)
    uploaded_by = Column(String(100), nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    files = relationship("ChartFile", back_populates="chart", cascade="all, delete-orphan", order_by="ChartFile.page_order")
    audit_logs = relationship("AuditLog", back_populates="chart", cascade="all, delete-orphan")


class ChartFile(Base):
    """
    One page of a chart.

    Every upload is converted to one PNG per page and the source file is
    discarded, so these rows and the objects they point at are the only copy
    of chart content in the system.

    storage_key is the object key in the bucket and the sole link between this
    row and its image — a bucket copy that does not preserve keys breaks every
    chart. page_text holds the text extracted during conversion, which is what
    in-chart search reads.
    """

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
    """
    What was done to a chart, by whom.

    Append-only. Covers the actions that change what coders see — upload,
    edit, retire, restore — so a chart that vanished from the library can be
    explained afterwards.
    """

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
    """
    A problem a coder reported with a chart — an unreadable page, a missing
    document, a chart that does not match its stated specialty.

    chart_number is stored alongside chart_id deliberately: feedback outlives
    the chart it refers to, and the number is what a trainer searches by.
    """

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
