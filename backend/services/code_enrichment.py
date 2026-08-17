"""
What a coded error was ABOUT, as opposed to who made it.

Every analytics screen in this application is keyed on a thing — a coder, a
chart, a batch, a topic — and describes errors as an attribute of it. None of
them knows what kind of medicine the codes represent, because the codes are
stored as bare strings. This joins those strings to the CMS reference tables so
the reporting can group by chapter, by CC/MCC severity, and by the seven
characters of a PCS code.

ENRICHMENT ONLY. Nothing here may influence a score. Grading is settled when a
chart is graded, and a re-run of the code-set ingest must never move a number
somebody has already been told. That is also why every function degrades to
empty rather than raising: an environment that has not run the ingest gets
analytics without these axes, not analytics that fail.

Two hazards worth knowing before adding a caller.

**The section spellings differ between modules.** PracticeLab stores
`GradingSection.PDX` — the ENUM NAME is upper-case where the auditor and the
codes API use "PDx". Matching case-sensitively returns zero diagnosis rows and
raises nothing at all, which reads as "no chapters in this data" rather than as
a bug. Everything here folds case.

**Errors are not a denominator.** `grading_feedback` holds only mistakes, so
counts from it are shares OF ERRORS. "40% of errors are Chapter 9" says Chapter
9 is common in these charts, not that it is hard. Anything claiming a RATE must
get its denominator from the full submissions in `practice_results`.
"""
from typing import Iterable, Optional

# Which code system a section's codes belong to. Keyed on the upper-case form
# and looked up that way, so PDx / PDX / pdx all land in the same place.
_SYSTEM_BY_SECTION = {
    "PDX": "ICD10CM",
    "SDX": "ICD10CM",
    "PCS": "ICD10PCS",
    "CPT": "HCPCS",
}

# CPT proper is AMA copyright and absent from this application, so a five-digit
# numeric code on a CPT line can never be described. Level II codes on the same
# line can be, which is why the line is drawn on the code's shape rather than on
# the section.
def is_licensed_cpt(code: str) -> bool:
    """Five digits, or four digits and a category letter — AMA's, not ours."""
    bare = _bare(code)
    return (len(bare) == 5
            and (bare.isdigit() or (bare[:4].isdigit() and bare[4].isalpha())))


def _bare(code) -> str:
    return str(code or "").strip().upper().replace(".", "").replace(" ", "")


def system_for_section(section) -> Optional[str]:
    """The code system a section's codes belong to, case-insensitively."""
    name = getattr(section, "value", section)
    return _SYSTEM_BY_SECTION.get(str(name or "").strip().upper())


def enrich_codes(db, pairs: Iterable) -> dict:
    """
    Describe many (section, code) pairs in one pass.

    Returns {(system, bare_code): {...}} carrying description, chapter,
    cc_mcc_status and — for PCS — the seven axis titles.

    One query per system rather than one per code: a batch export can carry a
    few hundred distinct codes, and this is called from endpoints that already
    walk every result.

    An empty dict means nothing could be described — no ingest, or no
    recognisable codes. Callers render the codes bare, exactly as before.
    """
    wanted: dict = {}
    for section, code in pairs:
        bare = _bare(code)
        if not bare:
            continue
        system = system_for_section(section)
        if not system:
            continue
        if system == "HCPCS" and is_licensed_cpt(bare):
            continue
        wanted.setdefault(system, set()).add(bare)
    if not wanted:
        return {}

    try:
        from models import CodeDescription, PcsCodeAxis
    except Exception:
        return {}

    out: dict = {}
    try:
        for system, codes in wanted.items():
            codes = sorted(codes)
            for i in range(0, len(codes), 500):
                chunk = codes[i:i + 500]
                rows = (db.query(CodeDescription)
                        .filter(CodeDescription.code_system == system,
                                CodeDescription.code.in_(chunk)).all())
                for row in rows:
                    out[(system, row.code)] = {
                        "code": row.code,
                        "system": row.code_system,
                        "description": row.description,
                        "short_description": row.short_description,
                        "chapter": row.chapter,
                        "chapter_no": row.chapter_no,
                        "cc_mcc": row.cc_mcc_status,
                        "billable": row.is_billable,
                    }

        pcs = sorted(wanted.get("ICD10PCS") or [])
        for i in range(0, len(pcs), 500):
            chunk = pcs[i:i + 500]
            for row in (db.query(PcsCodeAxis)
                        .filter(PcsCodeAxis.code.in_(chunk)).all()):
                entry = out.setdefault(("ICD10PCS", row.code), {
                    "code": row.code, "system": "ICD10PCS",
                    "description": None, "short_description": None,
                    "chapter": None, "chapter_no": None,
                    "cc_mcc": None, "billable": True,
                })
                entry["pcs"] = {
                    "section": row.section,
                    "body_system": row.body_system,
                    "root_operation": row.root_operation,
                    "body_part": row.body_part,
                    "approach": row.approach,
                    "device": row.device,
                    "qualifier": row.qualifier,
                }
    except Exception:
        # A schema without the reference tables is a legal state.
        return out

    return out


def lookup(enriched: dict, section, code) -> Optional[dict]:
    """One code out of an enrich_codes() result, by its original spelling."""
    system = system_for_section(section)
    if not system:
        return None
    return enriched.get((system, _bare(code)))


# ── the axes the reporting groups by ─────────────────────────────────────────
#
# Each returns a label or None. None means "this code cannot carry this axis" —
# a procedure has no ICD chapter, an outpatient CPT code has nothing at all —
# and the caller must leave it out rather than bucket it as "Unknown", which
# would put licensed-CPT blindness and genuine gaps in the same pile.

def chapter_label(info: Optional[dict]) -> Optional[str]:
    if not info or not info.get("chapter"):
        return None
    return info["chapter"]


def ccmcc_label(info: Optional[dict]) -> Optional[str]:
    """
    CC, MCC or "Neither" for a diagnosis; None for anything else.

    "Neither" is a real answer for a diagnosis and is reported: a team missing
    mostly non-CC secondaries is a different problem from one missing MCCs, and
    collapsing the first into silence hides half the finding.
    """
    if not info or info.get("system") != "ICD10CM":
        return None
    return (info.get("cc_mcc") or "Neither").upper().replace("NEITHER", "Neither")


def pcs_axis_labels(info: Optional[dict]) -> dict:
    """The seven characters of a PCS code, empty for anything else."""
    if not info or not info.get("pcs"):
        return {}
    return {k: v for k, v in info["pcs"].items() if v}


# A theme has to be a PATTERN, not an incident. Two errors sharing an axis is a
# coincidence at training volumes, and a label that reads as insight and is
# noise is worse than silence — it sends someone to study the wrong thing.
AXIS_MIN = 3


def axis_themes(pairs, enriched: dict, minimum: int = AXIS_MIN,
                top: Optional[int] = None) -> list:
    """
    What a set of (section, code) pairs have in common, ranked.

    One implementation for every caller: the coder's knowledge gaps and chart
    teaching focus, and the auditor's equivalents. The rule for what counts as
    a theme has been re-spelled at each call site before in this codebase, and
    that is how two screens end up disagreeing about the same word.

    Returns [] when nothing clears the bar, which is a real answer — these
    errors do not share a theme.
    """
    counts: dict = {}

    def bump(kind, label):
        if label:
            counts[(kind, label)] = counts.get((kind, label), 0) + 1

    for section, code in pairs:
        info = lookup(enriched, section, code)
        if not info:
            continue
        bump("Diagnosis chapter", chapter_label(info))
        if str(getattr(section, "value", section)).upper() == "SDX":
            severity = ccmcc_label(info)
            # "Neither" is the ABSENCE of a theme, not a theme.
            if severity in ("CC", "MCC"):
                bump("CC/MCC", severity)
        for axis, value in pcs_axis_labels(info).items():
            if axis in ("root_operation", "approach", "device"):
                bump("PCS " + axis.replace("_", " "), value)

    rows = [{"kind": k, "label": v, "count": n}
            for (k, v), n in counts.items() if n >= minimum]
    rows.sort(key=lambda x: -x["count"])
    return rows[:top] if top else rows
