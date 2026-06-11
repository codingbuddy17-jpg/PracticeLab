from sqlalchemy.orm import Session
from sqlalchemy import select, update
from models import Chart, ChartFile, ChartSequence, AuditLog, ChartStatus, Specialty, SPECIALTY_PREFIX
from services.storage import upload_bytes, get_presigned_url
from services.file_processor import process_file


def detect_specialty_from_prefix(filename: str):
    stem = filename.rsplit(".", 1)[0].upper()
    for prefix in sorted(SPECIALTY_PREFIX.keys(), key=len, reverse=True):
        if stem.startswith(prefix):
            return SPECIALTY_PREFIX[prefix]
    return None


def next_chart_number(db: Session, specialty: Specialty) -> str:
    from models import PREFIX_FOR_SPECIALTY
    prefix = PREFIX_FOR_SPECIALTY[specialty]

    seq = db.query(ChartSequence).filter(ChartSequence.prefix == prefix).with_for_update().first()

    if seq is None:
        seq = ChartSequence(prefix=prefix, last_number=1)
        db.add(seq)
        number = 1
    else:
        seq.last_number += 1
        number = seq.last_number

    db.flush()
    return f"{prefix}{number:03d}"


def ingest_file(
    db: Session,
    chart_id: int,
    filename: str,
    file_bytes: bytes,
    uploaded_by: str,
    page_order_start: int = 0,
) -> int:
    pages = process_file(filename, file_bytes)
    total = len(pages)

    for i, (png_bytes, mime) in enumerate(pages):
        key = f"charts/{chart_id}/{page_order_start + i:04d}_{filename}.png"
        upload_bytes(key, png_bytes, mime)

        cf = ChartFile(
            chart_id=chart_id,
            storage_key=key,
            original_filename=filename,
            page_order=page_order_start + i,
            total_pages=total,
            uploaded_by=uploaded_by,
        )
        db.add(cf)

    db.flush()
    return total


def get_chart_pages(chart: Chart) -> list:
    return [
        {"page": f.page_order, "url": get_presigned_url(f.storage_key)}
        for f in chart.files
    ]


def log_audit(db: Session, chart_id: int, action: str, actor: str, details: str = None):
    log = AuditLog(chart_id=chart_id, action=action, actor=actor, details=details)
    db.add(log)
    db.flush()


def increment_view(db: Session, chart_id: int):
    db.query(Chart).filter(Chart.id == chart_id).update(
        {Chart.view_count: Chart.view_count + 1}
    )
