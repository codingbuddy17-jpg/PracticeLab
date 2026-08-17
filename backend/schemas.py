from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models import Specialty, Difficulty, ChartStatus


class ChartFileOut(BaseModel):
    id: int
    storage_key: str
    original_filename: str
    page_order: int
    total_pages: int
    uploaded_by: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: int
    action: str
    actor: str
    details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ChartOut(BaseModel):
    id: int
    chart_number: str
    alias: Optional[str] = None
    specialty: Specialty
    category: str
    difficulty: Difficulty
    status: ChartStatus
    uploaded_by: str
    view_count: int
    has_answer_key: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime]
    files: List[ChartFileOut] = []

    class Config:
        from_attributes = True


class ChartWithRationale(ChartOut):
    rationale: Optional[str]
    audit_logs: List[AuditLogOut] = []


class ChartUpdate(BaseModel):
    category: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    rationale: Optional[str] = None
    alias: Optional[str] = None


class BulkUploadResult(BaseModel):
    filename: str
    chart_number: Optional[str]
    status: str
    message: str


