from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json
from database import get_db
from models import Chart, ChartStatus, Specialty, Difficulty
from schemas import BulkUploadResult
from services.chart_service import next_chart_number, ingest_file, log_audit

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/bulk", response_model=List[BulkUploadResult])
def bulk_upload(
    files: List[UploadFile] = File(...),
    metadata: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        meta_list = json.loads(metadata)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    if len(files) != len(meta_list):
        raise HTTPException(status_code=400, detail="Files and metadata count mismatch")

    results: List[BulkUploadResult] = []

    for upload_file, meta in zip(files, meta_list):
        filename = upload_file.filename or "unknown"
        try:
            specialty = Specialty(meta["specialty"])
            difficulty = Difficulty(meta["difficulty"])
            category = meta["category"].strip()
            uploaded_by = meta.get("uploaded_by", "Unknown").strip()
            rationale = meta.get("rationale")

            chart_number = next_chart_number(db, specialty)

            chart = Chart(
                chart_number=chart_number,
                specialty=specialty,
                category=category,
                difficulty=difficulty,
                rationale=rationale,
                uploaded_by=uploaded_by,
                status=ChartStatus.ACTIVE,
            )
            db.add(chart)
            db.flush()

            file_bytes = upload_file.file.read()
            ingest_file(db, chart.id, filename, file_bytes, uploaded_by)
            log_audit(db, chart.id, "UPLOAD", uploaded_by, f"Original file: {filename}")
            db.commit()

            results.append(BulkUploadResult(
                filename=filename,
                chart_number=chart_number,
                status="success",
                message=f"Uploaded as {chart_number}",
            ))

        except Exception as e:
            db.rollback()
            results.append(BulkUploadResult(
                filename=filename,
                chart_number=None,
                status="error",
                message=str(e),
            ))

    return results


@router.post("/{chart_id}/add-files")
def add_files_to_chart(
    chart_id: int,
    files: List[UploadFile] = File(...),
    uploaded_by: str = Form(...),
    db: Session = Depends(get_db),
):
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    current_max = max((f.page_order for f in chart.files), default=-1)
    total_added = 0

    for upload_file in files:
        filename = upload_file.filename or "unknown"
        file_bytes = upload_file.file.read()
        pages = ingest_file(db, chart_id, filename, file_bytes, uploaded_by, page_order_start=current_max + 1)
        current_max += pages
        total_added += pages

    log_audit(db, chart_id, "ADD_FILES", uploaded_by, f"{len(files)} file(s), {total_added} pages added")
    db.commit()

    return {"message": f"{total_added} page(s) added to {chart.chart_number}"}
