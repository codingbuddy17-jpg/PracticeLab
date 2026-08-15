"""
Score an auditor's findings against the ground truth frozen at allocation.

The shape of this is the point. Findings and ground truth use the same
{section, action, line, field, ...} records, so scoring is a comparison rather
than a translation — and the three components ARE the per-action breakdown, so
a single number cannot hide the thing it most needs to expose.

Why components rather than a flat findings ratio: roughly three quarters of
plantings are omissions, so a flat ratio lets an auditor who only ever hunts
for missing codes score well. Under components that auditor caps at the Add
weight. The blind spot is closed structurally instead of being reported.

Two rules that are easy to get wrong and expensive to get wrong:

  * NA is a real value, distinct from zero. A chart with no spurious codes
    planted has no Delete accuracy, and its weight redistributes. Writing 0.0
    would mark the auditor wrong for an opportunity that never existed.
  * "Identified" means found AND corrected. A finding that reaches the wrong
    corrected code does not fix the claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

REVENUE_ELEMENTS_DEFAULT = ["pdx", "ccmcc_sdx", "pcs", "cpt", "modifier", "units"]


@dataclass
class ScoringConfig:
    """Plain-data view of AuditScoringConfig, so the engine needs no ORM."""
    add_weight: int = 40
    revise_weight: int = 40
    delete_weight: int = 20
    over_call_revenue_pct: int = 20
    over_call_non_revenue_pct: int = 5
    revenue_elements: list = field(default_factory=lambda: list(REVENUE_ELEMENTS_DEFAULT))
    query_missed_pct: int = 20
    query_unnecessary_pct: int = 20
    pass_threshold: int = 90
    min_opportunities_for_verdict: int = 20
    # The verdict is decided on the Review Score, which has roughly four times
    # the opportunities per chart that detection has — about ten codes against
    # two and a half errors. Fifty is therefore about five charts, which is
    # also the suggested session length, so the two finally agree.
    min_review_opportunities: int = 50

    @classmethod
    def from_db(cls, row) -> "ScoringConfig":
        if row is None:
            return cls()
        vals = {}
        for f in cls.__dataclass_fields__:
            v = getattr(row, f, None)
            if v is None:
                continue
            vals[f] = list(v) if f == "revenue_elements" else v
        return cls(**vals)


def _bare(code: Optional[str]) -> str:
    return (code or "").strip().upper().replace(".", "")


def _norm(value: Any) -> str:
    """
    Compare corrected values without punishing formatting. A modifier entered
    as "51" and one stored as "51 " are the same answer; so are E11.9 and E119.
    Units are compared as text because the form yields strings.
    """
    return str(value if value is not None else "").strip().upper().replace(".", "")


# ── matching one finding to one planting ─────────────────────────────────────

def _matches(planting: dict, finding: dict) -> bool:
    """
    Whether a finding addresses this planting at all — location and action,
    before any question of whether the correction is right.

    Add is matched on the CODE rather than a line number: a missing code has no
    line, and the auditor chooses where to put it.
    """
    if (finding.get("section") or "") != (planting.get("section") or ""):
        return False
    if (finding.get("action") or "") != (planting.get("action") or ""):
        return False

    action = planting.get("action")
    if action == "Add":
        return _bare(finding.get("correct_value")) == _bare(planting.get("correct_value"))
    if action == "Delete":
        # Line number OR the code — an auditor deleting the right code from a
        # list they have already edited should not be marked wrong because the
        # index moved under them.
        if finding.get("line") is not None and finding.get("line") == planting.get("line"):
            return True
        return _bare(finding.get("claim_value")) == _bare(planting.get("claim_value"))
    # Revise: same line, and the same field.
    return (finding.get("line") == planting.get("line")
            and (finding.get("field") or "code") == (planting.get("field") or "code"))


def _corrected(planting: dict, finding: dict) -> bool:
    """
    Whether the correction is right. This is the requirement that makes the
    score mean anything: an auditor marking every line wrong has no idea what
    the corrected codes are, so flagging alone earns nothing.

    Delete needs no correction — removing the code IS the correction.
    """
    if planting.get("action") == "Delete":
        return True
    return _norm(finding.get("correct_value")) == _norm(planting.get("correct_value"))


def _element_of(finding: dict) -> str:
    """Which config element a finding touches, for the over-call tier."""
    section = (finding.get("section") or "").upper()
    fld = (finding.get("field") or "code").lower()
    if fld in ("modifier", "units"):
        return fld
    if section == "PDX":
        return "pdx"
    if section == "PCS":
        return "pcs"
    if section == "CPT":
        return "cpt"
    if section == "SDX":
        if fld == "poa":
            cc = str(finding.get("ccmcc") or "").upper()
            return "ccmcc_sdx" if cc in ("CC", "MCC") else "sdx_poa"
        cc = str(finding.get("ccmcc") or "").upper()
        return "ccmcc_sdx" if cc in ("CC", "MCC") else "sdx"
    return "sdx"


# ── the chart score ──────────────────────────────────────────────────────────

@dataclass
class ChartScore:
    is_clean: bool
    add_planted: int = 0
    add_found: int = 0
    add_accuracy: Optional[float] = None
    revise_planted: int = 0
    revise_found: int = 0
    revise_accuracy: Optional[float] = None
    delete_planted: int = 0
    delete_found: int = 0
    delete_accuracy: Optional[float] = None
    over_calls: int = 0
    over_call_tier: Optional[str] = None
    over_call_deduction: float = 0.0
    query_expected: Optional[bool] = None
    query_flagged: Optional[bool] = None
    query_correct: Optional[bool] = None
    query_deduction: float = 0.0
    detected_not_corrected: int = 0
    drg_impacting_planted: int = 0
    drg_impacting_found: int = 0
    base_accuracy: float = 100.0
    audit_accuracy: float = 100.0
    matched: list = field(default_factory=list)
    # Review scoring — every judgement the chart asked for, not just the
    # planted ones. Raw counts so a cohort pools rather than averaging.
    review_total: int = 0
    review_correct: int = 0
    review_score: Optional[float] = None
    review_sections: dict = field(default_factory=dict)
    review_attributes: dict = field(default_factory=dict)

    @property
    def opportunities(self) -> int:
        return self.add_planted + self.revise_planted + self.delete_planted


def score_chart(ground_truth: list[dict], findings: list[dict],
                cfg: Optional[ScoringConfig] = None,
                query_expected: Optional[bool] = None,
                query_flagged: Optional[bool] = None,
                claim: Optional[dict] = None,
                poa_applies: bool = False) -> ChartScore:
    """
    Score one chart.

    A clean chart (empty ground truth) starts at 100 and can only lose ground
    to deductions — it measures restraint, not detection, and contributes no
    component accuracies. Every other chart is the weighted mean of the
    components it actually planted.
    """
    cfg = cfg or ScoringConfig()
    ground_truth = list(ground_truth or [])
    findings = list(findings or [])

    buckets = {"Add": [], "Revise": [], "Delete": []}
    for p in ground_truth:
        buckets.setdefault(p.get("action"), []).append(p)

    used_findings: set[int] = set()
    found = {"Add": 0, "Revise": 0, "Delete": 0}
    detected_not_corrected = 0
    drg_planted = drg_found = 0
    matched: list[dict] = []

    for action in ("Add", "Revise", "Delete"):
        for planting in buckets.get(action, []):
            is_drg = bool(planting.get("drg_impacting"))
            drg_planted += 1 if is_drg else 0
            hit = None
            for idx, f in enumerate(findings):
                if idx in used_findings:
                    continue
                if _matches(planting, f):
                    hit = (idx, f)
                    break
            if hit is None:
                matched.append({"planting": planting, "outcome": "missed"})
                continue
            idx, f = hit
            used_findings.add(idx)
            if _corrected(planting, f):
                found[action] += 1
                drg_found += 1 if is_drg else 0
                matched.append({"planting": planting, "outcome": "correct"})
            else:
                # Reported, never scored. "Found 4 of 4, corrected 2" and
                # "found 2 of 4" both come out at 50% and are entirely
                # different coaching conversations.
                detected_not_corrected += 1
                matched.append({"planting": planting, "outcome": "detected_not_corrected"})

    over = [f for i, f in enumerate(findings) if i not in used_findings]

    score = ChartScore(
        is_clean=not ground_truth,
        add_planted=len(buckets.get("Add", [])), add_found=found["Add"],
        revise_planted=len(buckets.get("Revise", [])), revise_found=found["Revise"],
        delete_planted=len(buckets.get("Delete", [])), delete_found=found["Delete"],
        detected_not_corrected=detected_not_corrected,
        drg_impacting_planted=drg_planted, drg_impacting_found=drg_found,
        over_calls=len(over),
    )

    # Component accuracies — None where nothing of that type was planted.
    for action, weight_field in (("Add", "add"), ("Revise", "revise"), ("Delete", "delete")):
        planted = getattr(score, f"{weight_field}_planted")
        if planted:
            setattr(score, f"{weight_field}_accuracy",
                    round(getattr(score, f"{weight_field}_found") / planted * 100, 2))

    score.base_accuracy = _weighted_base(score, cfg)

    # One deduction per chart, sized by the worst category over-called — not
    # per finding. Identical on clean and opportunity charts.
    if over:
        revenue = set(cfg.revenue_elements or REVENUE_ELEMENTS_DEFAULT)
        tier = "revenue" if any(_element_of(f) in revenue for f in over) else "non_revenue"
        score.over_call_tier = tier
        score.over_call_deduction = float(
            cfg.over_call_revenue_pct if tier == "revenue" else cfg.over_call_non_revenue_pct)

    # Query is binary per chart, so a fixed deduction rather than a fourth
    # weighted component — folding a 0-or-100 value into the weighted mean
    # would swing scores violently. NA where no answer was authored.
    score.query_expected = query_expected
    score.query_flagged = query_flagged
    if query_expected is not None:
        flagged = bool(query_flagged)
        score.query_correct = (flagged == bool(query_expected))
        if not score.query_correct:
            score.query_deduction = float(
                cfg.query_missed_pct if query_expected else cfg.query_unnecessary_pct)

    score.audit_accuracy = round(max(
        0.0, score.base_accuracy - score.over_call_deduction - score.query_deduction), 2)
    score.matched = matched

    # The second scheme. Detection above answers "did you find what was
    # wrong"; this answers "of everything you had to judge, how much did you
    # judge correctly". Both are kept — blending them would hide whichever is
    # weak, which is the same reason clean and opportunity charts are reported
    # apart.
    review = score_review(claim or {}, ground_truth, matched, over, poa_applies)
    score.review_total = review["total"]
    score.review_correct = review["correct"]
    score.review_score = review["score"]
    score.review_sections = review["sections"]
    score.review_attributes = review["attributes"]
    return score


def _weighted_base(score: ChartScore, cfg: ScoringConfig) -> float:
    """
    Weighted mean over the components that exist, renormalised.

    A chart with no spurious codes splits Delete's share between Add and
    Revise rather than penalising an absent opportunity — the same principle
    the E/M scoring already applies within a line.

    A clean chart has no components at all and scores 100: there was nothing
    to find, so nothing was missed.
    """
    parts = [
        (score.add_accuracy, cfg.add_weight),
        (score.revise_accuracy, cfg.revise_weight),
        (score.delete_accuracy, cfg.delete_weight),
    ]
    live = [(acc, w) for acc, w in parts if acc is not None and w > 0]
    if not live:
        return 100.0
    total_weight = sum(w for _acc, w in live)
    if total_weight <= 0:
        return 100.0
    return round(sum(acc * w for acc, w in live) / total_weight, 2)



# ── review scoring ───────────────────────────────────────────────────────────
#
# The second of two schemes, mirroring the coder module, where a weighted score
# and a DPO accuracy have always sat side by side answering different
# questions. Here:
#
#   Detection Score — of the errors introduced, how many were found AND
#                     corrected. Sharp, and the training signal.
#   Review Score    — of every code the auditor had to judge, how many they
#                     judged correctly.
#
# Detection alone made a one-error chart binary: an auditor who correctly
# validated eight of nine codes and missed the ninth scored 0%, which is true
# of their detection and says nothing about the review they actually did.
#
# Review is also far steadier. A chart carries ~2.5 errors but ~10 codes, so a
# six-chart session yields roughly 60 review opportunities against 15
# detection ones — which is why the pass/fail verdict is decided on this one.

# The denominator is CODE LINES. Nothing else.
LINE_SECTIONS = ("PDx", "SDx", "PCS", "CPT")

# Reported with their own percentage, never added to the denominator. POA is
# judged on every diagnosis and modifiers and units on every CPT, but they are
# attributes OF a line, not lines of their own — and they carry a tiny share of
# the introduced errors (POA is 2% of the mix). Counting them as opportunities
# roughly doubled the denominator with judgements that are almost never wrong,
# which pushed a passive auditor who flagged nothing to 94% and let them pass.
ATTRIBUTE_SCORES = {"poa": "POA", "modifier": "Modifier", "units": "Units"}


def _line_key(entry: dict) -> tuple:
    """
    Identifies the LINE a planting or finding concerns.

    A line is one judgement covering its code and its attributes together, so a
    diagnosis with both the wrong code and the wrong POA is one defective line,
    not two. A missing code has no line number — it is keyed on the code that
    should have been there.
    """
    section = entry.get("section")
    if entry.get("action") == "Add" or entry.get("line") is None:
        return (section, "add", str(entry.get("correct_value") or "").upper())
    return (section, "line", entry.get("line"))


def _codes_in(rows) -> int:
    return len([r for r in (rows or []) if str((r or {}).get("code") or "").strip()])


def review_opportunities(claim: dict, ground_truth: list) -> dict:
    """
    One opportunity per code line the auditor had to judge.

    A code ON the claim is a line: keep it, revise it, or delete it. A code
    MISSING from the claim is one too — they were meant to add it — so each Add
    planting contributes a line its section would not otherwise have.
    """
    claim = claim or {}
    opp = {
        "PDx": 1 if str(claim.get("pdx_code") or "").strip() else 0,
        "SDx": _codes_in(claim.get("sdx")),
        "PCS": _codes_in(claim.get("pcs")),
        "CPT": _codes_in(claim.get("cpt")),
    }
    for planting in ground_truth or []:
        if planting.get("action") != "Add":
            continue
        section = planting.get("section")
        if section in opp:
            opp[section] += 1
    return opp


def _attribute_scores(claim: dict, matched: list, over: list,
                      poa_applies: bool) -> dict:
    """
    POA, Modifier and Units as percentages in their own right.

    Reported because they are real, gradeable work — POA is mandatory on
    inpatient diagnoses — but kept out of the chart denominator so they cannot
    dilute it. Each is measured over the lines it could apply to.
    """
    claim = claim or {}
    dx_lines = (1 if str(claim.get("pdx_code") or "").strip() else 0) \
        + _codes_in(claim.get("sdx"))
    cpt_lines = _codes_in(claim.get("cpt"))
    totals = {"POA": dx_lines if poa_applies else 0,
              "Modifier": cpt_lines, "Units": cpt_lines}
    defects = {"POA": 0, "Modifier": 0, "Units": 0}
    for entry in matched or []:
        if entry.get("outcome") == "correct":
            continue
        name = ATTRIBUTE_SCORES.get(
            ((entry.get("planting") or {}).get("field") or "").lower())
        if name:
            defects[name] += 1
    for finding in over or []:
        name = ATTRIBUTE_SCORES.get((finding.get("field") or "").lower())
        if name:
            defects[name] += 1
    out = {}
    for name, total in totals.items():
        if not total:
            continue
        correct = max(0, total - defects[name])
        out[name] = {"total": total, "correct": correct,
                     "score": round(correct / total * 100, 2)}
    return out


def score_review(claim: dict, ground_truth: list, matched: list, over: list,
                 poa_applies: bool) -> dict:
    """
    Per-section and whole-chart review figures.

    Correct and total are kept as raw counts, not just percentages, so a cohort
    pools them rather than averaging averages — the lesson already written into
    the coder's DPO columns.
    """
    opp = review_opportunities(claim, ground_truth)

    # A line is wrong once, however many things are wrong on it.
    wrong: set = set()
    for entry in matched or []:
        if entry.get("outcome") == "correct":
            continue
        wrong.add(_line_key(entry.get("planting") or {}))
    for finding in over or []:
        wrong.add(_line_key(finding or {}))

    defects: dict = {}
    for section, _kind, _ref in list(wrong):
        if section in opp:
            defects[section] = defects.get(section, 0) + 1

    sections, total_opp, total_correct = {}, 0, 0
    for name in LINE_SECTIONS:
        o = opp.get(name, 0)
        if not o:
            continue
        correct = max(0, o - defects.get(name, 0))
        sections[name] = {"total": o, "correct": correct,
                          "score": round(correct / o * 100, 2)}
        total_opp += o
        total_correct += correct
    return {
        "sections": sections,
        "attributes": _attribute_scores(claim, matched, over, poa_applies),
        "total": total_opp,
        "correct": total_correct,
        "score": round(total_correct / total_opp * 100, 2) if total_opp else None,
    }


# ── the session score ────────────────────────────────────────────────────────

@dataclass
class SessionScore:
    charts: int = 0
    clean_charts: int = 0
    opportunity_charts: int = 0
    audit_accuracy: float = 0.0
    clean_accuracy: Optional[float] = None
    opportunity_accuracy: Optional[float] = None
    add_planted: int = 0
    add_found: int = 0
    add_accuracy: Optional[float] = None
    revise_planted: int = 0
    revise_found: int = 0
    revise_accuracy: Optional[float] = None
    delete_planted: int = 0
    delete_found: int = 0
    delete_accuracy: Optional[float] = None
    drg_impacting_planted: int = 0
    drg_impacting_found: int = 0
    drg_accuracy: Optional[float] = None
    query_charts: int = 0
    query_correct: int = 0
    query_accuracy: Optional[float] = None
    over_calls: int = 0
    detected_not_corrected: int = 0
    opportunities: int = 0
    review_total: int = 0
    review_correct: int = 0
    review_score: Optional[float] = None
    review_sections: dict = field(default_factory=dict)
    review_attributes: dict = field(default_factory=dict)
    pass_fail: Optional[str] = None
    verdict_withheld_reason: Optional[str] = None


def score_session(chart_scores: list[ChartScore],
                  cfg: Optional[ScoringConfig] = None) -> SessionScore:
    """
    Roll charts up to a session.

    Two different bases, deliberately, and both must be stated wherever they
    are shown:

      * audit accuracy is the AVERAGE of chart scores, deductions included —
        each chart is one unit of work, which is how coder scoring already
        behaves in this app.
      * component accuracies are POOLED — total found over total planted.
        Averaging per-chart rates would let a chart with one planting count as
        much as a chart with six, which is how a rate quietly starts meaning
        something other than what it says.
    """
    cfg = cfg or ScoringConfig()
    out = SessionScore(charts=len(chart_scores))
    if not chart_scores:
        return out

    clean = [c for c in chart_scores if c.is_clean]
    opp = [c for c in chart_scores if not c.is_clean]
    out.clean_charts, out.opportunity_charts = len(clean), len(opp)

    out.audit_accuracy = round(
        sum(c.audit_accuracy for c in chart_scores) / len(chart_scores), 2)
    if clean:
        out.clean_accuracy = round(sum(c.audit_accuracy for c in clean) / len(clean), 2)
    if opp:
        out.opportunity_accuracy = round(sum(c.audit_accuracy for c in opp) / len(opp), 2)

    for name in ("add", "revise", "delete"):
        planted = sum(getattr(c, f"{name}_planted") for c in chart_scores)
        found = sum(getattr(c, f"{name}_found") for c in chart_scores)
        setattr(out, f"{name}_planted", planted)
        setattr(out, f"{name}_found", found)
        if planted:
            setattr(out, f"{name}_accuracy", round(found / planted * 100, 2))

    out.drg_impacting_planted = sum(c.drg_impacting_planted for c in chart_scores)
    out.drg_impacting_found = sum(c.drg_impacting_found for c in chart_scores)
    if out.drg_impacting_planted:
        out.drg_accuracy = round(
            out.drg_impacting_found / out.drg_impacting_planted * 100, 2)

    scored_queries = [c for c in chart_scores if c.query_correct is not None]
    out.query_charts = len(scored_queries)
    out.query_correct = sum(1 for c in scored_queries if c.query_correct)
    if scored_queries:
        out.query_accuracy = round(out.query_correct / len(scored_queries) * 100, 2)

    out.over_calls = sum(c.over_calls for c in chart_scores)
    out.detected_not_corrected = sum(c.detected_not_corrected for c in chart_scores)
    out.opportunities = sum(c.opportunities for c in chart_scores)

    # POOLED, not averaged. Raw counts add up so a twenty-code chart carries
    # more weight than a five-code one, which is the point — averaging the
    # percentages would make them equal.
    out.review_total = sum(c.review_total for c in chart_scores)
    out.review_correct = sum(c.review_correct for c in chart_scores)
    if out.review_total:
        out.review_score = round(out.review_correct / out.review_total * 100, 2)
    merged: dict = {}
    for c in chart_scores:
        for name, body in (c.review_sections or {}).items():
            acc = merged.setdefault(name, {"total": 0, "correct": 0})
            acc["total"] += body.get("total", 0)
            acc["correct"] += body.get("correct", 0)
    out.review_sections = {
        name: {**acc, "score": round(acc["correct"] / acc["total"] * 100, 2)}
        for name, acc in merged.items() if acc["total"]
    }
    attrs: dict = {}
    for c in chart_scores:
        for name, body in (c.review_attributes or {}).items():
            acc = attrs.setdefault(name, {"total": 0, "correct": 0})
            acc["total"] += body.get("total", 0)
            acc["correct"] += body.get("correct", 0)
    out.review_attributes = {
        name: {**acc, "score": round(acc["correct"] / acc["total"] * 100, 2)}
        for name, acc in attrs.items() if acc["total"]
    }

    # The verdict is decided on the REVIEW score, not detection.
    #
    # Detection is quantised by planting count — a chart with one error can
    # only score 0 or 100 — so a verdict on it was noise until a session ran
    # long enough to be impractical. Review has about four times the
    # opportunities per chart, so a normal session reaches a defensible
    # figure. Detection is still reported beside it and is still the thing
    # that says whether an auditor can find an error at all.
    if out.review_total < cfg.min_review_opportunities:
        out.verdict_withheld_reason = (
            f"indicative only — {out.review_total} codes reviewed, "
            f"{cfg.min_review_opportunities} needed for a verdict"
            if out.review_total else
            "restraint measure only — nothing reviewed in this session")
    else:
        out.pass_fail = "PASS" if (out.review_score or 0) >= cfg.pass_threshold else "FAIL"
    return out
