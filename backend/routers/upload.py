from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from pydantic import BaseModel
from database import get_db
from models import (Chart, ChartFile, ChartStatus, Specialty, Difficulty,
                    ChartSequence, GradingResult)
from schemas import BulkUploadResult
from services.chart_service import next_chart_number, ingest_file, log_audit
from services.storage import delete_object
from models import PREFIX_FOR_SPECIALTY
from config import settings

router = APIRouter(prefix="/upload", tags=["upload"])


class PreviewItem(BaseModel):
    filename: str
    specialty: Specialty


class PreviewResult(BaseModel):
    filename: str
    specialty: str
    assigned_number: str


@router.post("/preview", response_model=List[PreviewResult])
def preview_chart_numbers(items: List[PreviewItem], db: Session = Depends(get_db)):
    """
    Returns what chart numbers will be assigned without committing anything.
    Uses in-memory counters on top of current DB sequence — no DB writes.
    """
    # Load current sequence values from DB
    sequences: dict[str, int] = {}
    all_seqs = db.query(ChartSequence).all()
    for s in all_seqs:
        sequences[s.prefix] = s.last_number

    results = []
    for item in items:
        prefix = PREFIX_FOR_SPECIALTY[item.specialty]
        current = sequences.get(prefix, 0)
        current += 1
        sequences[prefix] = current
        results.append(PreviewResult(
            filename=item.filename,
            specialty=item.specialty.value,
            assigned_number=f"{prefix}{current:03d}",
        ))

    return results


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
            alias = meta.get("alias", "").strip() or None

            chart_number = next_chart_number(db, specialty)

            chart = Chart(
                chart_number=chart_number,
                specialty=specialty,
                category=category,
                difficulty=difficulty,
                rationale=rationale,
                alias=alias,
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
    passphrase: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if chart.uploaded_by != uploaded_by:
        if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
            raise HTTPException(status_code=403, detail="Invalid passphrase")

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


@router.post("/{chart_id}/replace-files")
def replace_chart_files(
    chart_id: int,
    files: List[UploadFile] = File(...),
    uploaded_by: str = Form(...),
    reason: str = Form(...),
    passphrase: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Swap a chart's pages for a corrected copy, keeping everything attached.

    add-files only ever appended, so a chart with a problem could be corrected
    only by leaving the bad pages in place beside the good ones, or by retiring
    it and re-uploading under a new number — which means re-entering the answer
    key and cutting every result loose from the chart they were graded on.

    Replacing keeps the chart number, the answer key, the audit history and
    every grading result. What changes is the images.

    Existing grading results are deliberately NOT blocked. The case this exists
    for is PHI that got through de-identification, where the correction changes
    what is VISIBLE and not the clinical facts the key was written against, so
    past scores remain meaningful. The reason is required and the audit entry
    records how many results already existed, so a replacement explains itself
    to whoever reads the history later.

    The old objects are deleted from storage, which is the point — a chart
    replaced for PHI must not leave the original pages retrievable.
    """
    if not reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to replace chart pages")

    # Always, not only for a chart somebody else uploaded — which is the rule
    # add-files uses. Appending is additive and undoable by deleting what was
    # added; this destroys the only copy of the original pages and cannot be
    # undone by anyone. It is also rare, so the friction is affordable, and it
    # matches purge, the other operation that destroys source material.
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Master admin passphrase required to replace chart pages")

    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    existing = db.query(ChartFile).filter(ChartFile.chart_id == chart_id).all()
    old_ids = {f.id for f in existing}
    old_keys = {f.storage_key for f in existing if f.storage_key}
    old_pages = len(existing)
    # Start above the highest page currently held. ingest_file bakes the page
    # index into the storage key, so starting from a constant meant a second
    # replacement of the same chart, with the same filename, wrote to the keys
    # it was about to delete.
    next_order = max((f.page_order for f in existing), default=-1) + 1
    graded = db.query(GradingResult).filter(
        GradingResult.chart_id == chart_id).count()

    # The new pages are ingested BEFORE the old rows go, so a failure part way
    # through leaves the chart with its original pages rather than none.
    added = 0
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        added += ingest_file(db, chart_id, filename, upload_file.file.read(),
                             uploaded_by, page_order_start=next_order + added)
    if added == 0:
        raise HTTPException(status_code=400, detail="No pages could be read from the upload")

    # Whatever the new pages actually landed on. A key the replacement now uses
    # must never be deleted, however the naming worked out — a stale object
    # costs storage, a row pointing at a deleted object is a broken chart.
    new_keys = {f.storage_key for f in db.query(ChartFile)
                .filter(ChartFile.chart_id == chart_id).all()
                if f.id not in old_ids and f.storage_key}
    stale_keys = old_keys - new_keys

    for row in existing:
        db.delete(row)
    db.flush()

    # Close the gap left by ingesting above the old range.
    for order, row in enumerate(db.query(ChartFile)
                                .filter(ChartFile.chart_id == chart_id)
                                .order_by(ChartFile.page_order).all()):
        row.page_order = order

    log_audit(db, chart_id, "REPLACE_FILES", uploaded_by,
              f"{old_pages} page(s) replaced with {added}; "
              f"{graded} existing grading result(s) kept; reason: {reason.strip()}")
    db.commit()

    # Only once the database is consistent. An orphaned object costs storage;
    # a deleted object with a row still pointing at it is a broken chart.
    for key in stale_keys:
        try:
            delete_object(key)
        except Exception:  # noqa: BLE001 - storage cleanup must not fail the swap
            pass

    return {
        "message": f"{added} page(s) replaced on {chart.chart_number}",
        "pages_removed": old_pages,
        "pages_added": added,
        "grading_results_kept": graded,
    }
