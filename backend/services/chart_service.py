from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from models import Chart, ChartFile, ChartSequence, AuditLog, ChartStatus, Specialty, SPECIALTY_PREFIX
from services.storage import upload_bytes, get_presigned_url
from services.file_processor import process_file
import re


def detect_specialty_from_prefix(filename: str):
    """Detect specialty from filename prefix. Longest prefix match wins."""
    stem = filename.rsplit(".", 1)[0].upper()
    for prefix in sorted(SPECIALTY_PREFIX.keys(), key=len, reverse=True):
        if stem.startswith(prefix):
            return SPECIALTY_PREFIX[prefix]
    return None


async def next_chart_number(db: AsyncSession, specialty: Specialty) -> str:
    from models import PREFIX_FOR_SPECIALTY
    prefix = PREFIX_FOR_SPECIALTY[specialty]

    result = await db.execute(
        select(ChartSequence).where(ChartSequence.prefix == prefix).with_for_update()
    )
    seq = result.scalar_one_or_none()

    if seq is None:
        seq = ChartSequence(prefix=prefix, last_number=1)
        db.add(seq)
        number = 1
    else:
        seq.last_number += 1
        number = seq.last_number

    await db.flush()
    return f"{prefix}{number:03d}"


async def ingest_file(
    db: AsyncSession,
    chart_id: int,
    filename: str,
    file_bytes: bytes,
    uploaded_by: str,
    page_order_start: int = 0,
):
    """Process file → PNG pages → upload to storage → create ChartFile records."""
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

    await db.flush()
    return total


async def get_chart_pages(chart: Chart) -> list:
    """Return list of presigned URLs for all pages of a chart."""
    return [
        {"page": f.page_order, "url": get_presigned_url(f.storage_key)}
        for f in chart.files
    ]


async def log_audit(db: AsyncSession, chart_id: int, action: str, actor: str, details: str = None):
    log = AuditLog(chart_id=chart_id, action=action, actor=actor, details=details)
    db.add(log)
    await db.flush()


async def increment_view(db: AsyncSession, chart_id: int):
    await db.execute(
        update(Chart).where(Chart.id == chart_id).values(view_count=Chart.view_count + 1)
    )
