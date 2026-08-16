"""
What a code says.

Two shapes, because the screens ask two different questions. A chart arrives
with a dozen codes already on it and wants them all described at once; a coder
typing a code wants the few that start with what they have typed so far.

Nothing here writes. The tables are reference data loaded by
scripts/ingest_code_sets.py, and an empty table is a legal state — the app ran
without descriptions before this existed and must keep working if nobody has
run the ingest yet. Every endpoint returns what it can and says nothing about
what it cannot find, rather than erroring.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import CodeDescription, PcsCodeAxis

router = APIRouter(prefix="/codes", tags=["codes"])

# The systems this app carries. CPT is absent on purpose: AMA copyright,
# licensed per user, and this repository is public.
SYSTEMS = ("ICD10CM", "ICD10PCS", "HCPCS")

# A section maps to the code system its codes belong to, so callers can ask in
# the vocabulary the form already speaks rather than translating.
SECTION_SYSTEM = {"PDX": "ICD10CM", "SDX": "ICD10CM",
                  "PCS": "ICD10PCS", "CPT": "HCPCS"}


def _bare(code: str) -> str:
    """Codes are stored and compared without the decimal point."""
    return (code or "").strip().upper().replace(".", "")


def _system_for(section: Optional[str], system: Optional[str]) -> Optional[str]:
    if system and system.upper() in SYSTEMS:
        return system.upper()
    return SECTION_SYSTEM.get((section or "").upper())


@router.get("/describe")
def describe(codes: str = Query(..., description="comma separated"),
             system: Optional[str] = None,
             section: Optional[str] = None,
             db: Session = Depends(get_db)):
    """
    Describe many codes in one request.

    A claim carries ten or twenty codes and every one of them wants a
    description, so this takes the lot. Twenty round trips to render one chart
    would be a poor trade for a caption.

    Unknown codes are simply absent from the reply. A code the app has never
    heard of is not an error — it may be from an edition nobody has loaded, and
    the screen should render the code alone rather than fail.
    """
    wanted = [_bare(c) for c in codes.split(",") if _bare(c)]
    if not wanted:
        return {"descriptions": {}}
    wanted = wanted[:200]

    q = db.query(CodeDescription).filter(CodeDescription.code.in_(wanted))
    resolved = _system_for(section, system)
    if resolved:
        q = q.filter(CodeDescription.code_system == resolved)

    out: dict = {}
    for row in q.all():
        # Without a system filter a code could match twice. First wins, and
        # the systems do not overlap in practice.
        out.setdefault(row.code, {
            "code": row.code,
            "system": row.code_system,
            "description": row.description,
            "short_description": row.short_description,
            "chapter": row.chapter,
            "chapter_no": row.chapter_no,
            "billable": row.is_billable,
        })
    return {"descriptions": out, "asked": len(wanted), "found": len(out)}


@router.get("/search")
def search(prefix: str = Query(..., min_length=2),
           system: Optional[str] = None,
           section: Optional[str] = None,
           limit: int = Query(10, le=25),
           db: Session = Depends(get_db)):
    """
    Codes beginning with what has been typed.

    PREFIX only, deliberately. Completing a code someone has already started
    saves typing; searching descriptions would answer the coding question
    itself, which is the thing a graded session is trying to measure. If a
    description search is ever wanted it belongs on a separate screen, not
    behind the box where the answer goes.

    Billable codes first: a category heading is not something anyone codes to,
    so it is poor autocomplete even though it is a real row.
    """
    stem = _bare(prefix)
    if len(stem) < 2:
        return {"matches": []}

    q = db.query(CodeDescription).filter(CodeDescription.code.like(f"{stem}%"))
    resolved = _system_for(section, system)
    if resolved:
        q = q.filter(CodeDescription.code_system == resolved)

    rows = (q.order_by(CodeDescription.is_billable.desc(),
                       CodeDescription.code.asc())
            .limit(limit).all())
    return {"matches": [{
        "code": r.code,
        "system": r.code_system,
        "description": r.description,
        "billable": r.is_billable,
    } for r in rows]}


@router.get("/pcs/{code}")
def pcs_axes(code: str, db: Session = Depends(get_db)):
    """
    An ICD-10-PCS code broken into its seven characters.

    Presence here is also validity: PCS is only real in the combinations the
    CMS tables define, so a code absent from this table does not exist however
    well-formed it looks.
    """
    row = db.query(PcsCodeAxis).filter(PcsCodeAxis.code == _bare(code)).first()
    if not row:
        return {"code": _bare(code), "valid": False}
    return {
        "code": row.code, "valid": True,
        "section": row.section, "body_system": row.body_system,
        "root_operation": row.root_operation, "body_part": row.body_part,
        "approach": row.approach, "device": row.device,
        "qualifier": row.qualifier,
    }


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """
    What is loaded, so a trainer can tell whether the ingest has been run
    rather than concluding the descriptions feature is broken.
    """
    from models import CodeSetVersion
    rows = (db.query(CodeSetVersion)
            .order_by(CodeSetVersion.loaded_at.desc()).all())
    seen: dict = {}
    for r in rows:
        seen.setdefault(r.code_system, {
            "code_system": r.code_system, "edition": r.edition,
            "row_count": r.row_count,
            "loaded_at": r.loaded_at.isoformat() if r.loaded_at else None,
        })
    return {"loaded": list(seen.values()), "any": bool(seen)}
