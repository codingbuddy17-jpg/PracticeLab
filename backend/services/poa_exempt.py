"""
Which ICD-10-CM codes CMS exempts from present-on-admission reporting.

The list is loaded with the code sets (scripts/ingest_code_sets.py stamps
code_descriptions.poa_exempt from the CMS POA exempt file each fiscal year).
NULL there means the list was never loaded — so an empty answer here means
"none known to be exempt", never "confirmed reportable". Every reader treats
it that way: nothing is greyed, skipped or rewritten on a guess.

Used by grading (POA on an exempt code is never a coder error), the auditor's
error generator (never plants a POA error on an exempt code), and the answer
key paths (an exempt code's POA is E).
"""
from typing import Iterable


def _bare(code) -> str:
    return str(code or "").strip().upper().replace(".", "").replace(" ", "")


def exempt_among(db, codes: Iterable) -> frozenset:
    """The bare forms of those codes that are POA exempt. One query."""
    wanted = {_bare(c) for c in codes if _bare(c)}
    if not wanted or db is None:
        return frozenset()
    from models.codes import CodeDescription
    try:
        rows = (db.query(CodeDescription.code)
                .filter(CodeDescription.code_system == "ICD10CM",
                        CodeDescription.code.in_(list(wanted)),
                        CodeDescription.poa_exempt.is_(True))
                .all())
    except Exception:  # noqa: BLE001 — an aid, never a failure
        return frozenset()
    return frozenset(r[0] for r in rows)


def list_loaded(db) -> bool:
    """Whether any POA exempt list has been loaded into this database."""
    from models.codes import CodeDescription
    try:
        return db.query(CodeDescription.id).filter(
            CodeDescription.poa_exempt.isnot(None)).first() is not None
    except Exception:  # noqa: BLE001
        return False


def is_exempt(code, exempt: frozenset) -> bool:
    return _bare(code) in exempt


def _is_ip(specialty) -> bool:
    return getattr(specialty, "value", specialty) == "IP-DRG"


def normalise_key_poa(db, specialty, pdx_code, pdx_poa, sdx, exempt=None):
    """
    An inpatient key's POA, with every exempt code set to E.

    POA is reported only on inpatient claims, so other specialties are
    returned untouched. A trainer never has to look a code up in the CMS
    list: whatever was typed — Y, N, U, W or nothing — an exempt code's POA
    is E. Returns (pdx_poa, sdx, lines_changed).
    """
    if not _is_ip(specialty):
        return pdx_poa, sdx, 0
    sdx = list(sdx or [])
    if exempt is None:
        exempt = exempt_among(db, [pdx_code] + [(r or {}).get("code") for r in sdx])
    if not exempt:
        return pdx_poa, sdx, 0
    changed = 0
    if is_exempt(pdx_code, exempt) and (pdx_poa or "").strip().upper() != "E":
        pdx_poa = "E"
        changed += 1
    out = []
    for r in sdx:
        if isinstance(r, dict) and is_exempt(r.get("code"), exempt) \
                and str(r.get("poa") or "").strip().upper() != "E":
            r = dict(r, poa="E")
            changed += 1
        out.append(r)
    return pdx_poa, out, changed


def correct_existing_keys(db) -> dict:
    """
    One pass over every inpatient answer key, setting E on exempt codes.

    Run by the code-set loader right after it loads the exempt list, which is
    the moment the list becomes known. Keys saved afterwards are corrected on
    save. Commits; returns counts for the loader to print.
    """
    from models import AnswerKey
    if not list_loaded(db):
        return {"keys": 0, "lines": 0, "skipped": "list not loaded"}
    keys = db.query(AnswerKey).filter(AnswerKey.specialty == "IP-DRG").all()
    codes = set()
    for k in keys:
        codes.add(k.pdx_code)
        codes.update((r or {}).get("code") for r in (k.sdx or []))
    exempt = exempt_among(db, codes)
    n_keys = n_lines = 0
    for k in keys:
        poa, sdx, changed = normalise_key_poa(db, k.specialty, k.pdx_code, k.pdx_poa,
                                              k.sdx, exempt)
        if changed:
            k.pdx_poa, k.sdx = poa, sdx
            n_keys += 1
            n_lines += changed
    db.commit()
    return {"keys": n_keys, "lines": n_lines}
