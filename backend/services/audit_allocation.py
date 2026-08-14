"""
Turning a chart pool into audit assignments.

Three decisions per chart, in this order:

  1. Is this one CLEAN? Drawn as a quota, not a per-chart coin flip — a 50%
     roll over five charts lands on zero or five clean about 3% of the time
     each, and an auditor with five clean charts learns nothing that session.
  2. Otherwise, does the chart have a trainer-authored set? Then MANUAL.
  3. Otherwise AUTO — generate from the seed.

The clean roll comes FIRST and applies to any chart, including one with a
hand-authored set. Clean has to be a property of the assignment rather than of
the chart: if it were a fixed subset, auditors would learn which chart numbers
to skim and the restraint measurement would collapse.

Everything is materialised and frozen here. Nothing downstream re-derives a
claim.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from typing import Optional

from models.auditor import AuditSource
from services.audit_mutation import Corpus, MutationConfig, claim_from_key, generate


def new_token(prefix: str = "AUD") -> str:
    """
    An auditor's only credential, and what routes them to the audit session
    rather than the coding one.

    Built exactly like the coder's practice token (`_gen_token` in
    practice_sessions) — four letters, four digits, same length and shape — so
    the two look like one system and an ops team has one format to recognise.
    """
    part1 = "".join(random.choices(string.ascii_uppercase, k=4))
    part2 = "".join(random.choices(string.digits, k=4))
    return f"{prefix}-{part1}{part2}"


def clean_quota(total: int, share_pct: int) -> int:
    """
    How many of this auditor's charts come up clean.

    Rounded DOWN, which has a property worth relying on: for any share below
    100%, flooring always leaves at least one opportunity chart, so no session
    ever measures restraint alone.
    """
    if total <= 0:
        return 0
    share = max(0, min(100, share_pct))
    return min(total, int(total * share / 100))


@dataclass
class Quotas:
    clean: int = 0
    manual: int = 0
    auto: int = 0

    @property
    def total(self) -> int:
        return self.clean + self.manual + self.auto


def resolve_quotas(mode: str, want: int, clean_share: int,
                   quota_clean: Optional[int] = None,
                   quota_manual: Optional[int] = None,
                   quota_auto: Optional[int] = None) -> Quotas:
    """
    How many of each type this auditor gets.

    auto    — the system decides the whole mix
    guided  — the trainer sets HOW MANY of each, the system picks WHICH
    manual  — the trainer picked the charts, so the types came with them

    Guided is the workhorse: a trainer running eight auditors over five charts
    each has an intent but no appetite for choosing forty charts.
    """
    mode = (mode or "guided").lower()
    # Hand-picked honours the numbers too. The trainer has chosen WHICH charts;
    # the mix within them is a separate question, and leaving it on the
    # clean-share default meant the quota boxes were silently ignored the
    # moment someone switched modes.
    if mode in ("guided", "manual") \
            and any(q is not None for q in (quota_clean, quota_manual, quota_auto)):
        q = Quotas(clean=max(0, quota_clean or 0),
                   manual=max(0, quota_manual or 0),
                   auto=max(0, quota_auto or 0))
        # The trainer's numbers are the quota. If they do not add up to the
        # charts being allocated, the remainder goes to auto rather than
        # silently shrinking the allocation.
        if q.total < want:
            q.auto += want - q.total
        return q

    clean = clean_quota(want, clean_share)
    # Everything not clean resolves per chart: a stored set makes it manual,
    # otherwise it generates. So the split between manual and auto is decided
    # by the pool, not by a number here.
    return Quotas(clean=clean, manual=0, auto=want - clean)


def build_corpus(answer_keys) -> Corpus:
    """
    Every code the library already holds, indexed for plausible substitution.

    Drawn from real keys rather than a reference file: a sibling that appears
    on another chart in this specialty is a confusion a coder could actually
    make here, and it costs no new data to obtain.
    """
    dx, pcs, cpt, mods = set(), set(), set(), set()
    for key in answer_keys or []:
        if getattr(key, "pdx_code", None):
            dx.add(str(key.pdx_code).strip())
        for row in (getattr(key, "sdx", None) or []):
            if isinstance(row, dict) and row.get("code"):
                dx.add(str(row["code"]).strip())
        for row in (getattr(key, "pcs", None) or []):
            if isinstance(row, dict) and row.get("code"):
                pcs.add(str(row["code"]).strip())
        for row in (getattr(key, "cpt", None) or []):
            if not isinstance(row, dict):
                continue
            if row.get("code"):
                cpt.add(str(row["code"]).strip())
            if row.get("modifier"):
                mods.add(str(row["modifier"]).strip())
    return Corpus(dx_codes=sorted(dx), pcs_codes=sorted(pcs),
                  cpt_codes=sorted(cpt), modifiers=sorted(mods))


def assignment_seed(chart_id: int, cycle_number: int) -> int:
    """
    Seeded from (chart, cycle) and NOT from the auditor.

    Two auditors given the same chart in one cycle therefore see identical
    errors, which is what makes their work comparable — the only way to measure
    inter-rater reliability at all. The allocator's randomisation already does
    the anti-collusion job. Adding auditor to the seed is the one-line switch
    if that ever needs to change.
    """
    return (chart_id * 1_000_003 + cycle_number * 7_919) % (2 ** 31)


def assign_intents(drawn, quotas, sets_by_chart: dict, rng) -> tuple[list, list]:
    """
    Decide, per drawn chart, whether it comes up clean / authored / generated.

    The quotas the trainer typed were only ever honoured for CLEAN. Everything
    else fell through to "authored if the chart happens to have a version,
    generated otherwise" — so Guided mode told a trainer they were choosing the
    mix while the pool actually chose it.

    A chart with no authored version cannot satisfy the authored quota, so the
    shortfall is reported rather than silently absorbed: a trainer who asked
    for three of their own and got one should be told why.

    Returns (intents, notes) where intents[i] is 'clean' | 'manual' | 'auto'.
    """
    n = len(drawn)
    intents = ["auto"] * n
    notes = []

    def _versions(i):
        return sets_by_chart.get(drawn[i].id) or []

    # A version flagged always-use is not subject to any quota — that is the
    # entire meaning of the flag, and letting a quota override it would make
    # the checkbox a suggestion.
    forced = {i for i in range(n)
              if any(getattr(v, "always_plant", False) for v in _versions(i))}
    for i in forced:
        intents[i] = "manual"

    free = [i for i in range(n) if i not in forced]
    rng.shuffle(free)

    # Never every chart. A session with nothing to find reports restraint and
    # no detection at all, and the flooring in clean_quota exists precisely to
    # prevent that — an explicit quota must not be a way around it. Creation
    # rejects such a quota outright; this holds the line for any other caller.
    clean_n = min(max(0, quotas.clean), len(free))
    if clean_n >= n and n > 0:
        clean_n = n - 1
    for i in free[:clean_n]:
        intents[i] = "clean"

    remaining = free[clean_n:]
    curated = [i for i in remaining if _versions(i)]
    # Charts forced above already count toward what the trainer asked for.
    want_manual = max(0, min(quotas.manual, len(free)) - len(forced))

    for i in curated[:want_manual]:
        intents[i] = "manual"
    short = want_manual - len(curated[:want_manual])
    if short > 0:
        notes.append(
            f"asked for {quotas.manual} chart(s) with your own errors but only "
            f"{len(curated) + len(forced)} of the drawn charts have any "
            f"authored — {short} fell back to system-generated")
    return intents, notes


def resolve_source(chart_id: int, is_clean: bool, sets_by_chart: dict,
                   use_index: int):
    """
    Pick where this assignment's claim comes from, and which version.

    `use_index` is how many times THIS CHART has already been allocated in
    this batch — not the cycle number, and not anything about the auditor.

    Both of those alternatives fail. Keying on the auditor cannot agree across
    a cohort, so four auditors on one chart got three different versions in the
    same sitting. Keying on the cycle number looks right until a chart does not
    appear every cycle: with six charts at two per cycle a chart recycles every
    third cycle, and against three versions that pins it to the same one
    forever — an auditor saw version 2 twice before ever reaching version 3.

    Counting the chart's own uses fixes both. It is chart-scoped, so everyone
    allocated that chart in one cycle lands on the same version; and it
    advances only when the chart is actually handed out, so consecutive
    encounters always differ however many cycles pass between them.

    Versions are ordered by id, so authoring a fourth does not reshuffle which
    version the next encounter produces.
    """
    sets = sorted(sets_by_chart.get(chart_id) or [], key=lambda s: s.id)
    forced = [s for s in sets if getattr(s, "always_plant", False)]
    if is_clean and not forced:
        return AuditSource.CLEAN, None

    pool = forced or sets
    if not pool:
        # No authored version, and the clean roll did not pick this chart.
        return AuditSource.AUTO, None

    return AuditSource.MANUAL, pool[max(0, use_index) % len(pool)]


def build_assignment(chart, key, source: AuditSource, key_set,
                     cycle_number: int, cfg: Optional[MutationConfig] = None,
                     corpus: Optional[Corpus] = None,
                     tier: Optional[str] = None,
                     observations: Optional[list] = None) -> dict:
    """
    Materialise one assignment: the claim as the auditor will see it, and the
    ground truth for it.

    Both are frozen. Deriving the claim later from the answer key would shift
    what the auditor saw if that key were edited in the meantime, and re-running
    the generator would depend on config that may since have been tuned.

    Returns a dict of AuditAssignment column values.
    """
    seed = assignment_seed(chart.id, cycle_number)
    base = {
        "chart_id": chart.id,
        "source": source,
        "set_id": key_set.id if key_set is not None else None,
        "seed": None,
        "query_expected": None,
    }

    if key is None:
        # No answer key means no truth to mutate and nothing to audit against.
        # The caller filters these out of the pool; this is the belt-and-braces.
        return {**base, "source": AuditSource.CLEAN, "claim": {}, "ground_truth": []}

    if source == AuditSource.CLEAN:
        return {**base, "claim": claim_from_key(key), "ground_truth": []}

    if source == AuditSource.MANUAL and key_set is not None:
        claim, truth = apply_manual_set(key, key_set)
        return {**base, "claim": claim, "ground_truth": truth,
                "query_expected": key_set.query_expected}

    # Real coder mistakes on this chart get planted first where any exist; the
    # generator fills the rest of the budget. A chart nobody has coded yet is
    # entirely synthetic, and the same chart in a later cycle plants from
    # whatever has accumulated since.
    claim, truth = generate(key, chart.specialty, seed=seed, cfg=cfg,
                            corpus=corpus, tier=tier, observations=observations)
    return {**base, "seed": seed, "claim": claim, "ground_truth": truth}


def apply_manual_set(key, key_set) -> tuple[dict, list[dict]]:
    """
    Build the claim a trainer's authored set describes.

    The set says what the auditor must DO — Add this code, Revise that field,
    Delete this one — so the claim is the answer key with those instructions
    played backwards: an Add means the code is removed from the claim, a Delete
    means a code is inserted into it.

    Stored sets carry no planting ceiling. A trainer authoring one has read the
    chart and has a reason; the cap governs generation only.
    """
    claim = claim_from_key(key)
    truth: list[dict] = []

    # Deletions of key codes shift indices, so take them from the bottom up and
    # record the line each was at before anything moved.
    adds = [m for m in (key_set.mutations or []) if m.get("action") == "Add"]
    revises = [m for m in (key_set.mutations or []) if m.get("action") == "Revise"]
    deletes = [m for m in (key_set.mutations or []) if m.get("action") == "Delete"]

    for m in revises:
        section, line = m.get("section"), m.get("line")
        rows = _rows(claim, section)
        fld = m.get("field") or "code"
        if section == "PDx":
            current = claim.get("pdx_poa" if fld == "poa" else "pdx_code")
            claim["pdx_poa" if fld == "poa" else "pdx_code"] = m.get("claim_value")
        elif rows is None or line is None or not (0 <= line < len(rows)):
            continue
        else:
            current = rows[line].get(fld)
            rows[line] = dict(rows[line], **{fld: m.get("claim_value")})
        truth.append({**m, "correct_value": m.get("correct_value", current)})

    # An Add means the code is MISSING from the claim: remove it from the copy.
    for m in adds:
        section = m.get("section")
        rows = _rows(claim, section)
        if rows is None:
            continue
        want = _bare(m.get("correct_value"))
        idx = next((i for i, r in enumerate(rows) if _bare(r.get("code")) == want), None)
        if idx is None:
            # The trainer named a code that is not on the key. Recording it
            # anyway would ask the auditor to add something the chart never
            # supported, so it is skipped rather than guessed at.
            continue
        removed = rows.pop(idx)
        _shift(truth, section, idx, -1)
        truth.append({**m, "entry": removed})

    # A Delete means a spurious code IS on the claim: insert it.
    for m in deletes:
        section = m.get("section")
        rows = _rows(claim, section)
        if rows is None:
            continue
        at = m.get("line")
        at = len(rows) if at is None or not (0 <= at <= len(rows)) else at
        rows.insert(at, {"code": m.get("claim_value"), "poa": m.get("poa", ""),
                         "ccmcc": m.get("ccmcc", "-")})
        _shift(truth, section, at, +1)
        truth.append({**m, "line": at})

    return claim, truth


def _rows(claim: dict, section: Optional[str]):
    return {"SDx": claim.get("sdx"), "PCS": claim.get("pcs"),
            "CPT": claim.get("cpt")}.get(section or "")


def _bare(code) -> str:
    return str(code or "").strip().upper().replace(".", "")


def _shift(truth: list[dict], section: str, at: int, delta: int) -> None:
    """
    Keep already-recorded line numbers valid when a later instruction moves
    rows. Missing this points a finding at the wrong line, and it would score
    as a miss whatever the auditor did.
    """
    for rec in truth:
        if rec.get("section") != section or not isinstance(rec.get("line"), int):
            continue
        if delta < 0 and rec["line"] > at:
            rec["line"] += delta
        elif delta > 0 and rec["line"] >= at:
            rec["line"] += delta
