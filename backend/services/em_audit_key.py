"""
An E/M answer key, in the shape the auditor already understands.

The auditor reads `answer_keys` — pdx, sdx, pcs, cpt. E/M charts do not have
one: their truth lives in `em_answer_keys`, a wide table of element ticks whose
three derived levels and coded lines are what an audit actually reviews.

Rather than teach every caller about a second table, this adapts one into the
other. An E/M key comes back looking like any other key, plus the three MDM
levels — so allocation, mutation and scoring keep working unchanged, and only
the places that care about reasoning have to know the difference.

**Why not ask trainers for a second key.** They could author an ordinary answer
key for an E/M chart as well; nothing forbids it. But then one chart carries two
truths, and the first time anyone edits one they disagree — silently, with the
coder graded against one and the auditor against the other.

The levels are NOT recomputed here. They are derived when the key is authored
(`copa_level_override or derive_copa_level(...)`) and stored, along with a flag
saying whether the trainer overrode the derivation. Deriving them again would
be a second implementation of the 2-of-3 tables, free to drift.
"""
from typing import Optional

from sqlalchemy import text

from models import Specialty

# The specialties whose answer key lives in em_answer_keys rather than
# answer_keys. Defined here rather than in either router package, because both
# the coder side and the auditor side need it and neither should import the
# other.
EM_KEY_SPECIALTIES = {Specialty.EM, Specialty.ED_PROFEE}

# The columns an audit needs. The other ~26 element ticks are what the COACHING
# module grades; an auditor reviews the levels those ticks produced.
_COLUMNS = ("chart_id", "em_code", "em_modifier", "level_method",
            "em_category", "dx_codes", "procedure_cpts",
            "copa_level", "dr_level", "risk_level",
            "copa_level_overridden", "dr_level_overridden",
            "risk_level_overridden")


class EmAuditKey:
    """
    An E/M key wearing the ordinary key's clothes.

    `sdx` and `cpt` are plain lists of dicts exactly as `AnswerKey` holds them,
    so `claim_from_key` and every mutation reads them without knowing.
    """

    def __init__(self, row: dict):
        self._row = row
        self.em_code = (row.get("em_code") or "").strip()
        self.level_method = (row.get("level_method") or "MDM").strip().upper()
        self.em_category = (row.get("em_category") or "").strip().lower()
        codes = _as_list(row.get("dx_codes"))
        # First diagnosis is the principal; the rest are secondaries. E/M keys
        # store one ordered list, and the order IS the sequencing.
        self.pdx_code = codes[0] if codes else None
        self.pdx_poa = ""          # POA is an inpatient concept
        self.sdx = [{"code": c, "poa": "", "ccmcc": ""} for c in codes[1:]]
        self.pcs = []              # professional claims carry no PCS
        self.cpt = _em_lines(row)
        self.cc_boundary = None    # set from the chart's own flag by the caller
        self.mdm = {
            "copa": (row.get("copa_level") or "") or None,
            "dr": (row.get("dr_level") or "") or None,
            "risk": (row.get("risk_level") or "") or None,
        }
        # Which levels the trainer set by hand rather than accepting the
        # derivation. A judgement call they disagreed with the table about —
        # which is exactly where planting an error asks a real question.
        self.mdm_overridden = {
            "copa": bool(row.get("copa_level_overridden")),
            "dr": bool(row.get("dr_level_overridden")),
            "risk": bool(row.get("risk_level_overridden")),
        }

    @property
    def has_mdm(self) -> bool:
        return any(self.mdm.values())


def _as_list(raw) -> list:
    import json
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw or "[]")
        except Exception:
            return []
    out = []
    for item in items:
        code = item.get("code") if isinstance(item, dict) else item
        if code and str(code).strip():
            out.append(str(code).strip())
    return out


def _em_lines(row: dict) -> list:
    """
    The E/M level first, then any office procedures.

    The level leads because it is the line an audit is about; the ladder and
    the 99285/99291 boundary both look for it, and a stable order keeps a
    seeded draw reproducible.
    """
    import json
    lines = []
    code = (row.get("em_code") or "").strip()
    if code:
        lines.append({"code": code,
                      "modifier": (row.get("em_modifier") or "").strip(),
                      "units": 1})
    raw = row.get("procedure_cpts")
    try:
        procs = raw if isinstance(raw, list) else json.loads(raw or "[]")
    except Exception:
        procs = []
    for p in procs:
        if isinstance(p, dict) and (p.get("code") or "").strip():
            lines.append({"code": str(p["code"]).strip(),
                          "modifier": str(p.get("modifier") or "").strip(),
                          "units": p.get("units") or 1})
        elif isinstance(p, str) and p.strip():
            lines.append({"code": p.strip(), "modifier": "", "units": 1})
    return lines


def load(db, chart_id: int) -> Optional[EmAuditKey]:
    """
    The E/M key for one chart, or None.

    Raw SQL because `em_answer_keys` has no ORM model — it is one of the
    raw-DDL tables. Missing entirely is a legal state: it means nobody has
    authored an E/M key for this chart yet.
    """
    try:
        row = db.execute(
            text("SELECT %s FROM em_answer_keys WHERE chart_id = :c"
                 % ", ".join(_COLUMNS)), {"c": chart_id}).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return EmAuditKey(dict(zip(_COLUMNS, row)))


def chart_ids_with_keys(db, chart_ids) -> set:
    """Which of these charts have an E/M key, for eligibility checks."""
    ids = [int(c) for c in (chart_ids or [])]
    if not ids:
        return set()
    try:
        # Chunked and inlined as parameters: SQLite caps bound parameters, and
        # a pool query can carry a few hundred charts.
        found = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            names = ", ".join(":c%d" % n for n in range(len(chunk)))
            rows = db.execute(
                text("SELECT chart_id FROM em_answer_keys WHERE chart_id IN (%s)"
                     % names),
                {"c%d" % n: v for n, v in enumerate(chunk)}).fetchall()
            found.update(r[0] for r in rows)
        return found
    except Exception:
        return set()
