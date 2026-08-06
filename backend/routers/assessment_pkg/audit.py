"""Assessment audit log — record and retrieve trainer actions."""
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import AssessmentAuditLog
from config import settings

router = APIRouter()


class LogEntry(BaseModel):
    trainer_name: str
    action: str
    specialty: Optional[str] = None
    details: Optional[str] = None


@router.post("/audit/log")
def log_action(entry: LogEntry, db: Session = Depends(get_db)):
    row = AssessmentAuditLog(
        trainer_name=entry.trainer_name,
        action=entry.action,
        specialty=entry.specialty,
        details=entry.details,
    )
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.post("/audit/verify-passphrase")
def verify_passphrase(
    trainer_name: str = Query(...),
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    row = AssessmentAuditLog(
        trainer_name=trainer_name,
        action="view_bank",
        details="Accessed Question Bank",
    )
    db.add(row)
    db.commit()
    return {"ok": True}


@router.get("/audit/logs")
def get_logs(
    passphrase: str = Query(...),
    specialty: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
):
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    q = db.query(AssessmentAuditLog)
    if specialty:
        q = q.filter(AssessmentAuditLog.specialty == specialty)
    rows = q.order_by(AssessmentAuditLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "trainer_name": r.trainer_name,
            "action": r.action,
            "specialty": r.specialty,
            "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
