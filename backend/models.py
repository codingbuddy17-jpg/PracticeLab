from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, func
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


class ChartSequence(Base):
    """Tracks the last used sequence number per specialty prefix."""
    __tablename__ = "chart_sequences"

    prefix = Column(String(10), primary_key=True)
    last_number = Column(Integer, default=0, nullable=False)
