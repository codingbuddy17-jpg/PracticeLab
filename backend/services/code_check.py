"""
Does this code exist?

Shape validation already runs in the frontend — J189 looks like a diagnosis,
0DTJ4ZZ looks like a procedure. Looking like one is not being one: "J18.99" is
a perfectly well-formed string and is not a code, and an answer key carrying it
marks every coder wrong on that line forever, with the graded session as the
only place it ever surfaces.

This is a WARNING and never a refusal. Two honest reasons a real code can be
absent: the loaded edition is older than the key, and the CMS tables may not
have been ingested at all. Refusing an upload over reference data the
deployment may not have would make an optional feature load-bearing.

CPT is not checked. Those descriptions are AMA copyright and this app does not
carry them, so it has no basis on which to call a five-digit numeric code
wrong — and a check that silently passes everything it cannot see would be
worse than no check, because it reads as confirmation.
"""
from typing import Optional

# The most that is useful to report. A file with two hundred unknown codes has
# one problem — the wrong edition, or the wrong column — and listing them all
# buries it.
MAX_REPORTED = 25


# Strings that mean "nothing here". Older answer keys carry these where a
# field was left blank — there is a migration in database.py scrubbing the same
# sentinels out of the JSON. Checking them would report "NONE is not a valid
# modifier", which is true and useless, and would sit at the top of the list
# ahead of the real findings.
_SENTINELS = {"NONE", "NA", "N/A", "NIL", "-", "--", "NULL"}


def _bare(code) -> str:
    text = str(code or "").strip().upper().replace(".", "").replace(" ", "")
    return "" if text in _SENTINELS else text


def _is_cpt(code: str) -> bool:
    """Five digits, or four plus a category modifier letter — AMA's, not ours."""
    return (len(code) == 5
            and (code.isdigit() or (code[:4].isdigit() and code[4].isalpha())))


def code_sets_loaded(db) -> bool:
    try:
        from models import CodeDescription
        return db.query(CodeDescription.id).first() is not None
    except Exception:
        return False


def unknown_codes(db, entries) -> Optional[list]:
    """
    Which of these codes are not in the loaded CMS tables.

    `entries` is an iterable of (label, section, code) — the label being
    whatever identifies the row to the person who uploaded it, usually a chart
    number.

    Returns None when there is nothing to check against, which callers should
    render as "not checked" rather than "all fine". An empty list means checked
    and every code was found; those are different claims and conflating them
    would tell a trainer their file was verified when nothing verified it.
    """
    if not code_sets_loaded(db):
        return None

    from models import CodeDescription, PcsCodeAxis

    wanted = {}
    for label, section, code in entries:
        bare = _bare(code)
        if not bare:
            continue
        sec = (section or "").upper()
        if sec in ("PDX", "SDX"):
            system = "ICD10CM"
        elif sec == "PCS":
            system = "ICD10PCS"
        elif sec == "CPT":
            if _is_cpt(bare):
                continue
            system = "HCPCS"
        elif sec == "MODIFIER":
            if bare.isdigit():      # CPT modifiers are AMA's too
                continue
            system = "HCPCSMOD"
        else:
            continue
        wanted.setdefault((system, bare), []).append(label)

    if not wanted:
        return []

    found = set()
    by_system: dict = {}
    for system, code in wanted:
        by_system.setdefault(system, set()).add(code)
    for system, codes in by_system.items():
        codes = sorted(codes)
        # Chunked: SQLite caps the number of bound parameters, and an answer-key
        # upload can carry a few thousand codes.
        for i in range(0, len(codes), 500):
            chunk = codes[i:i + 500]
            for (code,) in (db.query(CodeDescription.code)
                            .filter(CodeDescription.code_system == system,
                                    CodeDescription.code.in_(chunk)).all()):
                found.add((system, code))

    # PCS gets a second, stricter pass. A code can carry a description and
    # still not be a valid combination, and the tables are the authority on
    # which seven-character strings exist.
    pcs_wanted = sorted(by_system.get("ICD10PCS", set()))
    if pcs_wanted:
        try:
            real = set()
            for i in range(0, len(pcs_wanted), 500):
                chunk = pcs_wanted[i:i + 500]
                real.update(c for (c,) in db.query(PcsCodeAxis.code)
                            .filter(PcsCodeAxis.code.in_(chunk)).all())
            if real or db.query(PcsCodeAxis.code).first() is not None:
                for code in pcs_wanted:
                    if code not in real:
                        found.discard(("ICD10PCS", code))
        except Exception:
            pass

    out = []
    for (system, code), labels in sorted(wanted.items()):
        if (system, code) in found:
            continue
        for label in sorted(set(labels)):
            out.append({"chart": label, "code": code, "system": system})
    return out[:MAX_REPORTED]


def entries_from_key_row(chart_number: str, row: dict):
    """Flatten one parsed answer-key row into (label, section, code) triples."""
    yield (chart_number, "PDx", row.get("pdx_code"))
    for entry in (row.get("sdx") or []):
        if isinstance(entry, dict):
            yield (chart_number, "SDx", entry.get("code"))
    for entry in (row.get("pcs") or []):
        if isinstance(entry, dict):
            yield (chart_number, "PCS", entry.get("code"))
    for entry in (row.get("cpt") or []):
        if isinstance(entry, dict):
            yield (chart_number, "CPT", entry.get("code"))
            for mod in str(entry.get("modifier") or "").replace(",", " ").split():
                yield (chart_number, "Modifier", mod)


def ccmcc_mismatches(db, entries) -> Optional[list]:
    """
    Where a trainer's CC/MCC label disagrees with the MS-DRG manual.

    `entries` is an iterable of (label, code, claimed) — claimed being whatever
    the key says, "CC", "MCC", "-", or blank.

    ONE DIRECTION ONLY, and the asymmetry is the whole design. Whether a
    secondary actually acts as a CC depends on the principal diagnosis: the
    manual's exclusion lists can knock a published CC down to a non-CC on a
    particular chart. So:

    - claimed CC/MCC where the manual lists NEITHER is unambiguously wrong.
      Exclusions only ever remove severity; nothing promotes a code that has
      none.
    - claimed CC where the manual says MCC, or the reverse, is also wrong —
      an exclusion downgrades to non-CC, never between the two levels.
    - claimed nothing where the manual lists a CC or MCC is NOT reported. It
      is very often correct: that is exactly what an exclusion looks like.

    Reporting the third case would bury the first two in false positives on
    every inpatient key, and a warning nobody can trust is worse than none.
    """
    if not code_sets_loaded(db):
        return None

    from models import CodeDescription

    claims = {}
    for label, code, claimed in entries:
        bare = _bare(code)
        stated = str(claimed or "").strip().upper()
        if not bare or stated in ("", "-", "NONE", "N", "NON-CC", "NONCC"):
            continue
        if stated not in ("CC", "MCC"):
            continue
        claims.setdefault(bare, []).append((label, stated))

    if not claims:
        return []

    # Asked ONCE against the whole table, not inferred from the codes in this
    # file. Deriving it from the subset said "no severity data loaded" whenever
    # every code on the key happened to be a non-CC — which is the common case
    # for a short key, and it silently suppressed the check.
    if db.query(CodeDescription.id).filter(
            CodeDescription.code_system == "ICD10CM",
            CodeDescription.cc_mcc_status.isnot(None)).first() is None:
        return None

    published = {}
    codes = sorted(claims)
    for i in range(0, len(codes), 500):
        chunk = codes[i:i + 500]
        for code, status in (db.query(CodeDescription.code,
                                      CodeDescription.cc_mcc_status)
                             .filter(CodeDescription.code_system == "ICD10CM",
                                     CodeDescription.code.in_(chunk)).all()):
            published[code] = (status or "").upper() or None

    out = []
    for code in codes:
        if code not in published:
            continue          # unknown codes are the other check's business
        actual = published[code]
        for label, stated in sorted(set(claims[code])):
            if actual == stated:
                continue
            out.append({"chart": label, "code": code,
                        "claimed": stated, "published": actual or "neither"})
    return out[:MAX_REPORTED]


def ccmcc_from_key_row(chart_number: str, row: dict):
    """(label, code, claimed) for each secondary diagnosis on a key row."""
    for entry in (row.get("sdx") or []):
        if isinstance(entry, dict) and entry.get("code"):
            yield (chart_number, entry.get("code"), entry.get("ccmcc"))
