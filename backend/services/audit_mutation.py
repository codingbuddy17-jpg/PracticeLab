"""
Turn an answer key into a plausibly flawed claim, plus the ground truth.

The whole design rests on one idea: random-but-valid mutation produces claims
no coder would ever generate, so auditors learn to spot the generator instead
of learning the job. Every weight and constraint here is modelled on real audit
observations —

  * ~80% of real audit findings are missed codes
  * 90-95% of secondary-diagnosis findings are missing SDx; coders rush that
    section
  * surgical charts needing several CPTs commonly lose one or two
  * modifiers are either missing or wrong

Deliberately a pure function of (key, config, seed). No database, no clock, no
global random state — so the same seed always rebuilds the same claim, which is
what makes a disputed finding reproducible months later.

The corpus of real codes used for substitutions and insertions is passed in
rather than queried, for the same reason.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from models.charts import Specialty


# ── what counts as a procedure section, per specialty ────────────────────────

_IP_SPECIALTIES = {Specialty.IP_DRG}
_NO_UNITS = {Specialty.IP_DRG}

# ICD-10-PCS uses digits and a restricted letter set — vowels are excluded so a
# code can never spell a word.
PCS_ALPHABET = "0123456789BCDFGHJKLMNPQRSTVWXYZ"

# Character positions worth mutating, 0-indexed. Position 0 (section) and 1
# (body system) are excluded: changing them produces a code from a completely
# different chapter, which reads as a typo rather than a coding decision.
PCS_MUTABLE_POSITIONS = {
    2: "root operation",
    3: "body part",
    4: "approach",
    5: "device",
    6: "qualifier",
}

# Every mutation kind the generator can draw, with the config field holding its
# weight. Order is fixed so a seed reproduces the same draw across releases.
MUTATION_KINDS = [
    ("omit_sdx",         "mix_omit_sdx"),
    ("omit_proc",        "mix_omit_proc"),
    ("modifier_missing", "mix_modifier_missing"),
    ("modifier_wrong",   "mix_modifier_wrong"),
    ("substitute",       "mix_substitute"),
    ("substitute_pcs",   "mix_substitute_pcs"),
    ("swap_pdx",         "mix_swap_pdx"),
    ("units",            "mix_units"),
    ("poa",              "mix_poa"),
    ("spurious",         "mix_spurious"),
]

# Difficulty shifts the weights; it never changes the rules.
TIER_MULTIPLIERS = {
    "foundational": {"omit_sdx": 1.5, "omit_proc": 1.5, "spurious": 1.3,
                     "swap_pdx": 0.2, "substitute": 0.4, "substitute_pcs": 0.4,
                     "poa": 0.5},
    "intermediate": {},
    "advanced":     {"omit_sdx": 0.6, "omit_proc": 0.7, "swap_pdx": 2.0,
                     "substitute": 2.0, "substitute_pcs": 2.0,
                     "modifier_wrong": 1.5, "poa": 1.5},
}


@dataclass
class MutationConfig:
    """Plain-data view of AuditScoringConfig, so the engine needs no ORM."""
    mix_omit_sdx: int = 35
    mix_omit_proc: int = 18
    mix_modifier_missing: int = 8
    mix_modifier_wrong: int = 7
    mix_substitute: int = 7
    mix_substitute_pcs: int = 5
    mix_swap_pdx: int = 5
    mix_units: int = 3
    mix_poa: int = 2
    mix_spurious: int = 10
    max_auto_plantings: int = 10
    # How much of a chart's budget prefers real coder mistakes over
    # synthetic ones, where any have been observed. 100 means take as
    # many as the chart offers; synthetic still fills whatever is left.
    observed_share_pct: int = 100
    max_section_share: int = 30
    ccmcc_preference: int = 3

    @classmethod
    def from_db(cls, row) -> "MutationConfig":
        if row is None:
            return cls()
        return cls(**{f: getattr(row, f, getattr(cls, f))
                      for f in cls.__dataclass_fields__})


@dataclass
class Corpus:
    """
    Real codes drawn from the existing answer keys, used to make wrong codes
    plausible. Empty is legal — the generator falls back to structural
    mutation and simply draws fewer substitutions.
    """
    dx_codes: list[str] = field(default_factory=list)
    pcs_codes: list[str] = field(default_factory=list)
    cpt_codes: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)

    def dx_family(self, code: str, prefix_len: int = 3) -> list[str]:
        """
        Codes sharing the first few characters. ICD-10 groups by prefix, so
        these are the confusions coders actually make — E11.9 for E11.22 —
        and it needs no hierarchy data, just the codes already on hand.
        """
        head = _bare(code)[:prefix_len]
        if not head:
            return []
        return [c for c in self.dx_codes
                if _bare(c).startswith(head) and _bare(c) != _bare(code)]


def _bare(code: Optional[str]) -> str:
    return (code or "").strip().upper().replace(".", "")


def _is_ip(specialty: Specialty) -> bool:
    return specialty in _IP_SPECIALTIES


def _uses_units(specialty: Specialty) -> bool:
    return specialty not in _NO_UNITS


def _is_drg_impacting(section: str, entry: Optional[dict]) -> bool:
    """
    Mirrors the rule already in grading_engine: only PDx, a CC/MCC secondary
    and PCS can move the DRG. Used to report DRG-impacting recall separately
    rather than blending severity into one weighted figure.
    """
    if section in ("PDx", "PCS"):
        return True
    if section == "SDx" and entry:
        return str(entry.get("ccmcc") or "").upper() in ("CC", "MCC")
    return False


# ── the claim ────────────────────────────────────────────────────────────────

def claim_from_key(key) -> dict:
    """
    The correct claim, before anything is broken. A clean assignment is
    exactly this and nothing else — which is why a clean chart needs no
    special rendering: a clean claim is just a correct one.
    """
    return {
        "pdx_code": getattr(key, "pdx_code", None) or "",
        "pdx_poa": getattr(key, "pdx_poa", None) or "",
        "sdx": copy.deepcopy(getattr(key, "sdx", None) or []),
        "pcs": copy.deepcopy(getattr(key, "pcs", None) or []),
        "cpt": copy.deepcopy(getattr(key, "cpt", None) or []),
        "facility_level": getattr(key, "facility_level", None) or "",
        "profee_level": getattr(key, "profee_level", None) or "",
    }


def total_codes(claim: dict) -> int:
    n = 1 if claim.get("pdx_code") else 0
    return n + len(claim.get("sdx") or []) + len(claim.get("pcs") or []) \
             + len(claim.get("cpt") or [])


def planting_budget(claim: dict, cfg: MutationConfig, rng: random.Random) -> int:
    """
    How many errors this chart can carry without ceasing to look like a claim.

    Scaled by total codes rather than fixed: a chart with twelve secondaries
    can lose three without comment, a chart with two cannot lose one. Capped
    at max_auto_plantings — a chart needs 30-40 codes to reach 10, so the cap
    binds rarely, which is the intent.

    No ceiling applies to MANUAL plantings; this governs generation only.
    """
    n = total_codes(claim)
    if n <= 0:
        return 0
    ceiling = max(1, min(cfg.max_auto_plantings, int(n * cfg.max_section_share / 100)))
    low = 1 if n < 8 else 2
    return rng.randint(min(low, ceiling), ceiling)


# ── feasibility ──────────────────────────────────────────────────────────────

def _feasible(kind: str, claim: dict, specialty: Specialty, corpus: Corpus) -> bool:
    """
    Whether a chart can carry this mutation at all. A kind that is not feasible
    surrenders its weight to the kinds that are — the same renormalisation the
    E/M scoring already does within a line.
    """
    sdx = claim.get("sdx") or []
    pcs = claim.get("pcs") or []
    cpt = claim.get("cpt") or []
    procs = pcs + cpt

    if kind == "omit_sdx":
        # Never empty a section: a claim with no secondaries at all is not a
        # flawed claim, it is a broken one.
        return len(sdx) >= 2
    if kind == "omit_proc":
        return len(procs) >= 2
    if kind in ("modifier_missing", "modifier_wrong"):
        return any((c.get("modifier") or "").strip() for c in cpt)
    if kind == "substitute":
        # Corpus-aware on purpose. A chart whose codes have no prefix siblings
        # in the library cannot carry this mutation, and saying so here lets
        # the weight redistribute — otherwise the draw keeps picking a kind
        # that always fails and the effective mix drifts away from the config.
        return any(corpus.dx_family(s.get("code"), 3) for s in sdx)
    if kind == "substitute_pcs":
        # Its own kind rather than a fallback inside substitute. As a fallback
        # it was unreachable: diagnosis substitution nearly always succeeded
        # first, so the single-character PCS mutation — the most realistic
        # procedure error there is — effectively never fired.
        return any((p.get("code") or "").strip() for p in pcs)
    if kind == "swap_pdx":
        # Gated on a healthy SDx list, and the swap draws from the first few —
        # that is where a plausible principal candidate actually sits.
        return bool(claim.get("pdx_code")) and len(sdx) >= 3
    if kind == "units":
        return _uses_units(specialty) and bool(cpt)
    if kind == "poa":
        return _is_ip(specialty) and bool(claim.get("pdx_poa") or
                                          any(s.get("poa") for s in sdx))
    if kind == "spurious":
        # Always possible — you can always add a code that should not be there.
        # So it never renormalises out, and it grows on sparse charts.
        return True
    return False


def _weights(claim: dict, specialty: Specialty, corpus: Corpus,
             cfg: MutationConfig, tier: Optional[str]) -> dict[str, float]:
    mult = TIER_MULTIPLIERS.get((tier or "").lower(), {})
    out: dict[str, float] = {}
    for kind, field_name in MUTATION_KINDS:
        if not _feasible(kind, claim, specialty, corpus):
            continue
        w = float(getattr(cfg, field_name, 0)) * mult.get(kind, 1.0)
        if w > 0:
            out[kind] = w
    return out


# ── individual mutations ─────────────────────────────────────────────────────

def _pick_sdx_index(sdx: list[dict], rng: random.Random, cfg: MutationConfig,
                    used: set, prefer_ccmcc: bool = True) -> Optional[int]:
    """
    Choose which secondary to break, weighting CC/MCC-bearing codes heavily.

    Not exclusively, though — an auditor who learns that only CC/MCC codes ever
    go missing has learned the generator rather than the job.
    """
    candidates = [i for i in range(len(sdx)) if ("SDx", i) not in used]
    if not candidates:
        return None
    if not prefer_ccmcc:
        return rng.choice(candidates)
    weights = []
    for i in candidates:
        cc = str((sdx[i] or {}).get("ccmcc") or "").upper()
        weights.append(float(cfg.ccmcc_preference) if cc in ("CC", "MCC") else 1.0)
    return rng.choices(candidates, weights=weights, k=1)[0]


def _mutate_pcs_code(code: str, corpus: Corpus, rng: random.Random) -> tuple[str, str]:
    """
    Change exactly one character of an ICD-10-PCS code.

    PCS is positional, so a single-character change is both structurally valid
    and a genuine real-world confusion — Excision for Resection, the wrong body
    part, open versus percutaneous. Prefers a character seen in another real
    code at the same position, falling back to the alphabet.

    Returns (mutated_code, what_changed).
    """
    original = (code or "").strip().upper()
    positions = [p for p in sorted(PCS_MUTABLE_POSITIONS) if p < len(original)]
    if not positions:
        return original, "code"
    pos = rng.choice(positions)

    siblings = {c.strip().upper()[pos]
                for c in corpus.pcs_codes
                if len(c.strip()) > pos
                and c.strip().upper()[:3] == original[:3]
                and c.strip().upper()[pos] != original[pos]}
    pool = sorted(siblings) or [ch for ch in PCS_ALPHABET if ch != original[pos]]
    replacement = rng.choice(pool)
    mutated = original[:pos] + replacement + original[pos + 1:]
    return mutated, PCS_MUTABLE_POSITIONS[pos]


def _substitute_dx(code: str, corpus: Corpus, rng: random.Random) -> Optional[str]:
    """A sibling from the same ICD-10 prefix family, if the corpus has one."""
    family = corpus.dx_family(code, 4) or corpus.dx_family(code, 3)
    return rng.choice(sorted(set(family))) if family else None


def _spurious_dx(claim: dict, corpus: Corpus, rng: random.Random) -> Optional[str]:
    """A real code from another chart — plausible for the specialty, wrong here."""
    present = {_bare(claim.get("pdx_code"))} | {
        _bare(s.get("code")) for s in (claim.get("sdx") or [])}
    pool = sorted({c for c in corpus.dx_codes if _bare(c) not in present})
    return rng.choice(pool) if pool else None


# ── the generator ────────────────────────────────────────────────────────────

def generate(key, specialty: Specialty, seed: int,
             cfg: Optional[MutationConfig] = None,
             corpus: Optional[Corpus] = None,
             tier: Optional[str] = None,
             budget: Optional[int] = None,
             observations: Optional[list] = None) -> tuple[dict, list[dict]]:
    """
    Build a flawed claim and the ground truth for it.

    Returns (claim, ground_truth). Ground truth is a list of what the auditor
    must do, in the same {section, action, ...} shape their own findings take,
    so scoring is a comparison rather than a translation.

    `observations` are mistakes real coders made on this chart. Where they
    exist they are planted FIRST, because a demonstrated error beats a guessed
    one — and the auditor is then learning to catch what their own colleagues
    actually get wrong. Synthetic mutation fills whatever budget is left, so a
    chart with two observations and a budget of four still varies.

    Which observations get picked is seeded, so a chart with more candidates
    than budget plants a different subset each cycle rather than repeating.

    An empty ground truth is a legal, ordinary outcome — a chart the budget
    could not safely break. Callers that need a guaranteed-clean chart should
    not call this at all; they should stamp the assignment CLEAN.
    """
    cfg = cfg or MutationConfig()
    corpus = corpus or Corpus()
    rng = random.Random(seed)

    claim = claim_from_key(key)
    if total_codes(claim) == 0:
        return claim, []

    want = budget if budget is not None else planting_budget(claim, cfg, rng)
    ground_truth: list[dict] = []
    # One mutation per line: two on the same line make the correct finding
    # ambiguous and the scoring arbitrary.
    used: set = set()

    if observations and cfg.observed_share_pct > 0:
        room = max(1, round(want * cfg.observed_share_pct / 100))
        _plant_observed(observations, claim, room, rng, used, ground_truth)

    attempts = 0
    while len(ground_truth) < want and attempts < want * 8:
        attempts += 1
        weights = _weights(claim, specialty, corpus, cfg, tier)
        if not weights:
            break
        kinds = sorted(weights)
        kind = rng.choices(kinds, weights=[weights[k] for k in kinds], k=1)[0]
        entry = _apply(kind, claim, specialty, corpus, cfg, rng, used, ground_truth)
        if entry:
            ground_truth.append(entry)

    return claim, ground_truth


def _plant_observed(observations, claim: dict, room: int, rng: random.Random,
                    used: set, emitted: list[dict]) -> None:
    """
    Plant real coder mistakes, weighted so a trend outranks a one-off.

    A single coder missing one code is a data point, not a pattern — it might
    just be someone having a bad afternoon. It stays a legitimate candidate,
    but two or more coders making the same mistake is what earns extra weight.

    Drawn without replacement and seeded, so a chart carrying ten observations
    plants a different subset each cycle instead of the same ten every time.
    """
    pool = list(observations)
    while pool and len(emitted) < room:
        weights = [getattr(o, "weight", 1.0) for o in pool]
        pick = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        obs = pool.pop(pick)
        record = _apply_instruction(obs.as_instruction(), claim, used, emitted)
        if record:
            emitted.append(record)


def _apply_instruction(instr: dict, claim: dict, used: set,
                       emitted: list[dict]) -> Optional[dict]:
    """
    Apply one concrete planting instruction and return its ground-truth record.

    The instruction says what the AUDITOR must do, so it is played backwards
    into the claim: an Add means the code is removed from what they will see, a
    Delete means one is inserted. Returns None where the chart cannot carry it
    — a code already gone, a line already touched, a section that would empty.
    """
    section = instr.get("section")
    action = instr.get("action")
    rows = {"SDx": claim.setdefault("sdx", []),
            "PCS": claim.setdefault("pcs", []),
            "CPT": claim.setdefault("cpt", [])}.get(section)

    if section == "PDx":
        if action != "Revise" or ("PDx", 0) in used:
            return None
        fld = instr.get("field") or "code"
        column = "pdx_poa" if fld == "poa" else "pdx_code"
        correct = instr.get("correct_value") or claim.get(column)
        claim[column] = instr.get("claim_value")
        used.add(("PDx", 0))
        return {**instr, "kind": "observed", "line": 0, "field": fld,
                "correct_value": correct, "drg_impacting": True}

    if rows is None:
        return None

    if action == "Add":
        # Never empty a section: a claim with no secondaries at all is not a
        # flawed claim, it is a broken one.
        if len(rows) < 2:
            return None
        want = _bare(instr.get("correct_value") or instr.get("code"))
        idx = next((i for i, r in enumerate(rows) if _bare(r.get("code")) == want), None)
        if idx is None or (section, idx) in used:
            return None
        removed = rows.pop(idx)
        _shift_used(used, section, idx, emitted)
        return {**instr, "kind": "observed", "action": "Add",
                "correct_value": removed.get("code"), "entry": removed,
                "drg_impacting": _is_drg_impacting(section, removed)}

    if action == "Delete":
        code = instr.get("claim_value") or instr.get("code")
        if not code:
            return None
        at = rng_free_index(rows, used, section)
        if at is None:
            return None
        rows.insert(at, {"code": code, "poa": instr.get("poa", ""),
                         "ccmcc": instr.get("ccmcc", "-")})
        _unshift_used(used, section, at, emitted)
        used.add((section, at))
        return {**instr, "kind": "observed", "action": "Delete", "line": at,
                "claim_value": code, "drg_impacting": False}

    if action == "Revise":
        fld = instr.get("field") or "code"
        want = _bare(instr.get("code"))
        idx = next((i for i, r in enumerate(rows) if _bare(r.get("code")) == want), None)
        if idx is None or (section, idx) in used:
            return None
        correct = instr.get("correct_value")
        if correct in (None, ""):
            correct = rows[idx].get(fld)
        rows[idx] = dict(rows[idx], **{fld: instr.get("claim_value")})
        used.add((section, idx))
        return {**instr, "kind": "observed", "line": idx, "field": fld,
                "claim_value": instr.get("claim_value"), "correct_value": correct,
                "drg_impacting": _is_drg_impacting(section, rows[idx])}

    return None


def rng_free_index(rows: list, used: set, section: str) -> Optional[int]:
    """First insertion point that does not land on an already-touched line."""
    for at in range(len(rows) + 1):
        if (section, at) not in used:
            return at
    return None


def _apply(kind: str, claim: dict, specialty: Specialty, corpus: Corpus,
           cfg: MutationConfig, rng: random.Random, used: set,
           emitted: list[dict]) -> Optional[dict]:
    """
    Apply one mutation in place and return its ground-truth record, or None if
    this chart could not carry it after all.
    """
    sdx = claim.setdefault("sdx", [])
    pcs = claim.setdefault("pcs", [])
    cpt = claim.setdefault("cpt", [])

    if kind == "omit_sdx":
        if len(sdx) < 2:
            return None
        i = _pick_sdx_index(sdx, rng, cfg, used)
        if i is None:
            return None
        removed = sdx.pop(i)
        _shift_used(used, "SDx", i, emitted)
        return {
            "kind": kind, "section": "SDx", "action": "Add",
            "correct_value": removed.get("code"),
            "entry": removed,
            "drg_impacting": _is_drg_impacting("SDx", removed),
        }

    if kind == "omit_proc":
        section, rows = ("PCS", pcs) if len(pcs) >= 2 else ("CPT", cpt)
        if len(rows) < 2:
            return None
        candidates = [i for i in range(len(rows)) if (section, i) not in used]
        if not candidates:
            return None
        i = rng.choice(candidates)
        removed = rows.pop(i)
        _shift_used(used, section, i, emitted)
        return {
            "kind": kind, "section": section, "action": "Add",
            "correct_value": removed.get("code"),
            "entry": removed,
            "drg_impacting": section == "PCS",
        }

    if kind in ("modifier_missing", "modifier_wrong"):
        candidates = [i for i, c in enumerate(cpt)
                      if (c.get("modifier") or "").strip() and ("CPT", i) not in used]
        if not candidates:
            return None
        i = rng.choice(candidates)
        current = (cpt[i].get("modifier") or "").strip()
        if kind == "modifier_missing":
            new = ""
        else:
            pool = sorted({m for m in corpus.modifiers if m and m != current}) or \
                   [m for m in ("59", "51", "25", "26", "76", "LT", "RT") if m != current]
            new = rng.choice(pool)
        cpt[i]["modifier"] = new
        used.add(("CPT", i))
        return {
            "kind": kind, "section": "CPT", "action": "Revise", "field": "modifier",
            "line": i, "code": cpt[i].get("code"),
            "claim_value": new, "correct_value": current,
            "drg_impacting": True,
        }

    if kind == "substitute":
        # Prefix-family confusion — E11.9 for E11.22. The commonest real
        # substitution, and it needs no hierarchy data.
        i = _pick_sdx_index(sdx, rng, cfg, used)
        if i is None:
            return None
        original = sdx[i].get("code")
        replacement = _substitute_dx(original, corpus, rng)
        if not replacement:
            return None
        sdx[i] = dict(sdx[i], code=replacement)
        used.add(("SDx", i))
        return {
            "kind": kind, "section": "SDx", "action": "Revise",
            "field": "code", "line": i,
            "claim_value": replacement, "correct_value": original,
            "drg_impacting": _is_drg_impacting("SDx", sdx[i]),
        }

    if kind == "substitute_pcs":
        # One character of a 7-character positional code. Structurally valid
        # and a genuine confusion: Excision for Resection, the wrong body part,
        # open versus percutaneous.
        pidx = [i for i in range(len(pcs)) if ("PCS", i) not in used]
        if not pidx:
            return None
        i = rng.choice(pidx)
        original = pcs[i].get("code")
        mutated, changed = _mutate_pcs_code(original, corpus, rng)
        if not mutated or mutated == (original or "").strip().upper():
            return None
        pcs[i] = dict(pcs[i], code=mutated)
        used.add(("PCS", i))
        return {
            "kind": kind, "section": "PCS", "action": "Revise",
            "field": "code", "line": i, "pcs_character": changed,
            "claim_value": mutated, "correct_value": original,
            "drg_impacting": True,
        }

    if kind == "swap_pdx":
        if not claim.get("pdx_code") or len(sdx) < 3:
            return None
        # Draw from the first few secondaries — a plausible principal candidate
        # sits there. Swapping with the ninth produces a claim that is obviously
        # wrong rather than arguably wrong, which teaches nothing.
        head = [i for i in range(min(3, len(sdx))) if ("SDx", i) not in used]
        if not head or ("PDx", 0) in used:
            return None
        i = rng.choice(head)
        old_pdx, old_poa = claim["pdx_code"], claim.get("pdx_poa") or ""
        promoted = sdx[i]
        claim["pdx_code"] = promoted.get("code")
        claim["pdx_poa"] = promoted.get("poa") or old_poa
        sdx[i] = dict(promoted, code=old_pdx, poa=old_poa)
        used.add(("PDx", 0))
        used.add(("SDx", i))
        # ONE finding, not two. An auditor thinks "wrong principal diagnosis",
        # and on IP-DRG it is the single most valuable catch.
        return {
            "kind": kind, "section": "PDx", "action": "Revise", "field": "code",
            "line": 0, "swapped_with_line": i,
            "claim_value": claim["pdx_code"], "correct_value": old_pdx,
            "drg_impacting": True,
        }

    if kind == "units":
        candidates = [i for i in range(len(cpt)) if ("CPT", i) not in used]
        if not candidates:
            return None
        i = rng.choice(candidates)
        current = str(cpt[i].get("units") or 1)
        try:
            base = max(1, int(current))
        except (TypeError, ValueError):
            base = 1
        new = base + rng.choice([1, 1, 2]) if base < 3 else max(1, base - 1)
        cpt[i] = dict(cpt[i], units=new)
        used.add(("CPT", i))
        return {
            "kind": kind, "section": "CPT", "action": "Revise", "field": "units",
            "line": i, "code": cpt[i].get("code"),
            "claim_value": str(new), "correct_value": current,
            "drg_impacting": True,
        }

    if kind == "poa":
        # Prefer a CC/MCC-bearing secondary: a POA flip there can strip the
        # code's severity contribution entirely.
        candidates = [i for i in range(len(sdx))
                      if (sdx[i] or {}).get("poa") and ("SDx", i) not in used]
        if candidates:
            i = _pick_sdx_index([sdx[j] for j in candidates], rng, cfg, set())
            i = candidates[i] if i is not None else rng.choice(candidates)
            current = str(sdx[i].get("poa") or "Y").upper()
            new = "N" if current == "Y" else "Y"
            sdx[i] = dict(sdx[i], poa=new)
            used.add(("SDx", i))
            return {
                "kind": kind, "section": "SDx", "action": "Revise", "field": "poa",
                "line": i, "code": sdx[i].get("code"),
                "claim_value": new, "correct_value": current,
                "drg_impacting": _is_drg_impacting("SDx", sdx[i]),
            }
        if claim.get("pdx_poa") and ("PDx", 0) not in used:
            current = str(claim["pdx_poa"]).upper()
            new = "N" if current == "Y" else "Y"
            claim["pdx_poa"] = new
            used.add(("PDx", 0))
            return {
                "kind": kind, "section": "PDx", "action": "Revise", "field": "poa",
                "line": 0, "claim_value": new, "correct_value": current,
                "drg_impacting": True,
            }
        return None

    if kind == "spurious":
        code = _spurious_dx(claim, corpus, rng)
        if not code:
            return None
        entry = {"code": code, "poa": "Y" if _is_ip(specialty) else "", "ccmcc": "-"}
        # Insert at a varied position — an error always appended to the end
        # teaches the generator rather than the job.
        at = rng.randint(0, len(sdx))
        sdx.insert(at, entry)
        _unshift_used(used, "SDx", at, emitted)
        used.add(("SDx", at))
        return {
            "kind": kind, "section": "SDx", "action": "Delete",
            "line": at, "claim_value": code,
            "drg_impacting": False,
        }

    return None


def _shift_used(used: set, section: str, removed_index: int,
                emitted: Optional[list[dict]] = None) -> None:
    """
    Keep line numbers valid after a removal shifts the list up.

    Both the touched-line set AND any ground truth already emitted have to
    move. Missing the second is a silent corruption: an earlier finding would
    keep pointing at line 5 while its code had slid to line 4, and every such
    finding would score as a miss no matter what the auditor did.
    """
    moved = {(s, i - 1) if s == section and i > removed_index else (s, i)
             for (s, i) in used if not (s == section and i == removed_index)}
    used.clear()
    used.update(moved)
    for rec in (emitted or []):
        if rec.get("section") == section and isinstance(rec.get("line"), int) \
                and rec["line"] > removed_index:
            rec["line"] -= 1
        if section == "SDx" and isinstance(rec.get("swapped_with_line"), int) \
                and rec["swapped_with_line"] > removed_index:
            rec["swapped_with_line"] -= 1


def _unshift_used(used: set, section: str, inserted_index: int,
                  emitted: Optional[list[dict]] = None) -> None:
    """Keep line numbers valid after an insertion shifts the list down."""
    moved = {(s, i + 1) if s == section and i >= inserted_index else (s, i)
             for (s, i) in used}
    used.clear()
    used.update(moved)
    for rec in (emitted or []):
        if rec.get("section") == section and isinstance(rec.get("line"), int) \
                and rec["line"] >= inserted_index:
            rec["line"] += 1
        if section == "SDx" and isinstance(rec.get("swapped_with_line"), int) \
                and rec["swapped_with_line"] >= inserted_index:
            rec["swapped_with_line"] += 1
