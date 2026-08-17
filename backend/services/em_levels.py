"""
Which way a level error went.

An E/M level error is not one thing. "Coded 99213, key says 99214" and "coded
99214, key says 99204" are both wrong by one code, and they are different
mistakes with different causes and different money attached:

    upcoded / downcoded   the work was misjudged, on the right ladder
    patient type          the encounter was misread — new billed as
                          established or the reverse, at the same level
    critical care         the hardest question in the ED: does this condition
                          qualify at all, 99285 or 99291

Counting them together says "42 level errors" and nothing a trainer can act on.
Split by direction they are four different conversations.

The direction matters beyond training. Upcoding is what payers audit for, so it
is what people are taught to look for; downcoding is revenue quietly left on
the table and nobody is watching. A team that only ever upcodes and a team that
only ever downcodes have the same error count and opposite problems.

Codes only. Nothing here reads a chart or judges whether critical care was
warranted — it reports that the coder and the key disagree across that
boundary, which is the finding a trainer follows up.
"""
from typing import Optional

# The ladders. A level error moves ALONG one of these; it does not jump between
# them, and a code outside them is not a level at all.
NEW_OFFICE = ["99202", "99203", "99204", "99205"]
EST_OFFICE = ["99211", "99212", "99213", "99214", "99215"]
EMERGENCY = ["99281", "99282", "99283", "99284", "99285"]

# Critical care sits outside the ladders on purpose. It is a different service,
# not a higher rung — which is exactly why the 99285/99291 decision is hard.
CRITICAL_CARE = {"99291", "99292"}

_LADDERS = {
    "new_office": NEW_OFFICE,
    "est_office": EST_OFFICE,
    "emergency": EMERGENCY,
}

# New and established office codes pair off by the level of work: 99203 is the
# new-patient equivalent of 99213. 99211 has no counterpart — a nurse visit has
# no new-patient form — so it is deliberately absent.
_OFFICE_PAIRS = {
    "99202": "99212", "99203": "99213", "99204": "99214", "99205": "99215",
}
_OFFICE_PAIRS.update({v: k for k, v in _OFFICE_PAIRS.items()})


def _norm(code) -> str:
    return str(code or "").strip().upper()


def ladder_of(code: str) -> Optional[str]:
    code = _norm(code)
    for name, rungs in _LADDERS.items():
        if code in rungs:
            return name
    return None


def rung_of(code: str) -> Optional[int]:
    code = _norm(code)
    for rungs in _LADDERS.values():
        if code in rungs:
            return rungs.index(code)
    return None


def classify(coded, expected) -> Optional[dict]:
    """
    How a coded E/M level differs from the key's.

    Returns None when there is nothing to say: the codes agree, neither is a
    level, or they are unrelated services that share no ladder. None is not
    "correct" — it is "this is not a level error", and callers must not count
    it as either.

    Returns {"kind", "direction", "steps"} otherwise, where direction is "up"
    or "down" from the coder's point of view: up means they billed higher than
    the key.
    """
    coded, expected = _norm(coded), _norm(expected)
    if not coded or not expected or coded == expected:
        return None

    coded_cc, expected_cc = coded in CRITICAL_CARE, expected in CRITICAL_CARE

    # ── the critical care boundary ───────────────────────────────────────────
    # The judgement the whole ED module turns on. Reported in both directions
    # because they are opposite failures: overreach is a compliance exposure,
    # missed critical care is revenue nobody notices is gone.
    if coded_cc != expected_cc:
        other = expected if coded_cc else coded
        if ladder_of(other) != "emergency":
            # Critical care against something that is not an ED level is not
            # this question — it is two different services.
            return None
        return {"kind": "critical_care_overreach" if coded_cc
                else "critical_care_missed",
                "direction": "up" if coded_cc else "down", "steps": None}
    if coded_cc and expected_cc:
        # 99291 vs 99292 is a units question, not a level one.
        return None

    coded_ladder, expected_ladder = ladder_of(coded), ladder_of(expected)
    if not coded_ladder or not expected_ladder:
        return None

    # ── same ladder: the work was misjudged ──────────────────────────────────
    if coded_ladder == expected_ladder:
        steps = rung_of(coded) - rung_of(expected)
        return {"kind": "upcoded" if steps > 0 else "downcoded",
                "direction": "up" if steps > 0 else "down",
                "steps": abs(steps)}

    # ── new vs established: the encounter was misread ────────────────────────
    if {coded_ladder, expected_ladder} == {"new_office", "est_office"}:
        # Same level of work, wrong patient type — the pure form of this error.
        if _OFFICE_PAIRS.get(expected) == coded:
            return {"kind": "patient_type", "direction": None, "steps": 0}
        # Wrong patient type AND a different level. The patient type is the
        # more informative half: it explains the ladder, and the level
        # difference is a consequence of being on the wrong one.
        equivalent = _OFFICE_PAIRS.get(coded)
        steps = None
        if equivalent and rung_of(equivalent) is not None:
            steps = rung_of(equivalent) - rung_of(expected)
        return {"kind": "patient_type",
                "direction": None if not steps else ("up" if steps > 0 else "down"),
                "steps": abs(steps) if steps else 0}

    # An office code against an ED code is not a level error — it is the wrong
    # place of service, and saying "downcoded" about it would be nonsense.
    return None


# The labels the screens and exports use, so the vocabulary is written once.
KIND_LABELS = {
    "upcoded": "Upcoded",
    "downcoded": "Downcoded",
    "patient_type": "New vs established",
    "critical_care_overreach": "Critical care not supported",
    "critical_care_missed": "Critical care missed",
}
