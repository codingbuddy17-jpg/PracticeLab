"""
Real coder mistakes, harvested per chart, turned into planting candidates.

Everything else in the mutation engine is an educated guess about what a coder
would get wrong. This is the record of what they actually did — so an auditor
trained on it is learning to catch the errors their own organisation makes,
not the errors a generator imagines.

Two rules that keep it honest:

  * Diff against the CURRENT answer key, never the snapshot stored beside the
    submission. An error observed six months ago was recorded against whatever
    the key said then; if the key has since been corrected, that "error" may
    now be correct, and planting it manufactures a false finding. Diffing
    against today's key invalidates stale observations by construction.
  * One coder making one mistake is a data point, not a pattern. A single
    observation is a fine candidate to plant, but only two or more coders
    making the same mistake earns extra weight — otherwise one careless
    session distorts what the module teaches.

Coverage grows on its own: a chart nobody has coded yields nothing and falls
back to synthetic mutation, and the same chart in a later cycle plants from
whatever has accumulated since.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

# Two coders making the same mistake is a trend; one is an accident.
TREND_THRESHOLD = 2
# How much more likely a trend is to be planted than a one-off.
TREND_MULTIPLIER = 3.0


@dataclass
class Observation:
    """
    One mistake real coders made on one chart, in the same shape a mutation
    takes — so it needs no translation to be planted.
    """
    section: str
    action: str
    field: Optional[str] = None
    code: Optional[str] = None
    claim_value: Optional[str] = None
    correct_value: Optional[str] = None
    coders: int = 0

    @property
    def is_trend(self) -> bool:
        return self.coders >= TREND_THRESHOLD

    @property
    def weight(self) -> float:
        return TREND_MULTIPLIER if self.is_trend else 1.0

    def as_instruction(self) -> dict:
        """The planting instruction: what the auditor will have to do."""
        return {
            "section": self.section,
            "action": self.action,
            "field": self.field,
            "code": self.code,
            "claim_value": self.claim_value,
            "correct_value": self.correct_value,
            "origin": "observed",
            "observed_coders": self.coders,
            "observed_trend": self.is_trend,
        }


def _rows(value: Any) -> list[dict]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    return [r for r in (value or []) if isinstance(r, dict)]


def _bare(code: Any) -> str:
    return str(code or "").strip().upper().replace(".", "")


def _by_code(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        key = _bare(r.get("code"))
        if key and key not in out:
            out[key] = r
    return out


def observations_for_chart(submissions: list[dict], key) -> list[Observation]:
    """
    Diff every submission on this chart against the current answer key.

    `submissions` is a list of dicts with the raw columns from practice_results
    — pdx_submitted, sdx_submitted, pcs_submitted, cpt_submitted. The stored
    *_answer_key snapshots are deliberately ignored.

    Returns one Observation per distinct mistake, counted across coders.
    """
    if key is None:
        return []

    tally: dict[tuple, Observation] = {}

    def note(section, action, *, fld=None, code=None,
             claim_value=None, correct_value=None):
        ident = (section, action, fld, _bare(code),
                 _bare(claim_value), _bare(correct_value))
        obs = tally.get(ident)
        if obs is None:
            obs = Observation(section=section, action=action, field=fld,
                              code=code, claim_value=claim_value,
                              correct_value=correct_value)
            tally[ident] = obs
        obs.coders += 1

    key_pdx = _bare(getattr(key, "pdx_code", None))
    key_sdx = _by_code(_rows(getattr(key, "sdx", None)))
    key_pcs = _by_code(_rows(getattr(key, "pcs", None)))
    key_cpt = _by_code(_rows(getattr(key, "cpt", None)))

    for sub in submissions:
        # ── principal diagnosis ──────────────────────────────────────────────
        sub_pdx = _bare(sub.get("pdx_submitted"))
        if key_pdx and sub_pdx and sub_pdx != key_pdx:
            note("PDx", "Revise", fld="code",
                 claim_value=sub.get("pdx_submitted"),
                 correct_value=getattr(key, "pdx_code", None))

        # ── diagnoses and procedures ─────────────────────────────────────────
        for section, key_rows, column in (
                ("SDx", key_sdx, "sdx_submitted"),
                ("PCS", key_pcs, "pcs_submitted"),
                ("CPT", key_cpt, "cpt_submitted")):
            sub_rows = _by_code(_rows(sub.get(column)))

            for code, key_row in key_rows.items():
                if code not in sub_rows:
                    # The coder missed it, so the auditor must add it back.
                    note(section, "Add", code=key_row.get("code"),
                         correct_value=key_row.get("code"))
                    continue
                _compare_fields(note, section, key_row, sub_rows[code])

            for code, sub_row in sub_rows.items():
                if code not in key_rows:
                    # The coder invented it, so the auditor must delete it.
                    note(section, "Delete", code=sub_row.get("code"),
                         claim_value=sub_row.get("code"))

    return sorted(tally.values(),
                  key=lambda o: (-o.coders, o.section, o.action, str(o.code)))


def _compare_fields(note, section: str, key_row: dict, sub_row: dict) -> None:
    """
    Right code, wrong detail. POA and modifier are fields on a line
    rather than sections of their own, so getting one wrong is a Revise on
    that line — the same shape the auditor's own finding takes.
    """
    for fld in ("poa", "modifier"):
        expected = str(key_row.get(fld) or "").strip().upper()
        actual = str(sub_row.get(fld) or "").strip().upper()
        if not expected and not actual:
            continue
        if expected != actual:
            note(section, "Revise", fld=fld, code=key_row.get("code"),
                 claim_value=sub_row.get(fld) or "",
                 correct_value=key_row.get(fld) or "")


def load_observations_bulk(db, chart_ids, keys) -> dict:
    """
    Observations for many charts in ONE query.

    load_observations below issues a query per chart, and allocation called it
    once per chart in the pool. That is invisible against a local SQLite file
    and expensive against a remote database, where the cost is round trips
    rather than work: a 120-chart pool meant 120 sequential round trips before
    a single assignment was built.

    `keys` maps chart_id -> key. Charts with no key are skipped, as before.
    """
    from sqlalchemy import text

    wanted = [cid for cid in chart_ids if keys.get(cid)]
    if not wanted:
        return {}

    grouped: dict = {cid: [] for cid in wanted}
    # Chunked so a very large pool cannot build an unbounded IN list.
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        placeholders = ", ".join(":c%d" % n for n in range(len(chunk)))
        params = {"c%d" % n: cid for n, cid in enumerate(chunk)}
        rows = db.execute(text("""
            SELECT chart_id, pdx_submitted, sdx_submitted, pcs_submitted, cpt_submitted
            FROM practice_results
            WHERE chart_id IN (%s) AND total_score IS NOT NULL
        """ % placeholders), params).fetchall()
        for r in rows:
            grouped[r[0]].append({
                "pdx_submitted": r[1], "sdx_submitted": r[2],
                "pcs_submitted": r[3], "cpt_submitted": r[4],
            })

    return {cid: observations_for_chart(subs, keys[cid])
            for cid, subs in grouped.items()}


def load_observations(db, chart_id: int, key,
                      exclude_auditor_facing: bool = True) -> list[Observation]:
    """
    Fetch every coder submission for this chart and diff it against the key.

    Reads practice_results directly rather than grading_feedback: the feedback
    table records over-coding as a COUNT ("3 extra code(s) submitted") without
    saying which codes, so a Delete planting cannot be recovered from it. The
    results table stores both sides in full.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT pdx_submitted, sdx_submitted, pcs_submitted, cpt_submitted
        FROM practice_results
        WHERE chart_id = :c AND total_score IS NOT NULL
    """), {"c": chart_id}).fetchall()

    submissions = [{
        "pdx_submitted": r[0], "sdx_submitted": r[1],
        "pcs_submitted": r[2], "cpt_submitted": r[3],
    } for r in rows]
    return observations_for_chart(submissions, key)


def summarise(observations: list[Observation]) -> dict:
    """Coverage figures for the trainer — how much real signal a chart carries."""
    trends = [o for o in observations if o.is_trend]
    return {
        "observations": len(observations),
        "trends": len(trends),
        "max_coders": max((o.coders for o in observations), default=0),
        "by_action": {
            action: sum(1 for o in observations if o.action == action)
            for action in ("Add", "Revise", "Delete")
        },
    }
