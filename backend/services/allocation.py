"""
Choosing which charts a person gets in one allocation cycle.

Lifted out of the PracticeLab batch router so the Auditor module can use the
same draw. The two modules keep entirely separate storage — a shared batches
table with a mode column would need a filter on every existing query, and one
missed filter mixes audit work into coder analytics — but there is no reason
for two copies of this algorithm to drift apart.

Nothing here touches the database. It takes a pool, a history and a target,
and returns the picks plus a note describing the state of that person's pool.
"""

import random


def draw_for_person(pool, seen_counts: dict, prior_sets: list, want: int):
    """
    Pick one person's charts for one cycle.

    Exhaustion is per PERSON. Alice having seen everything says nothing about
    Bob, so each is drawn against their own history and one running dry never
    holds up anyone else.

    Charts are grouped by how many times THIS person has already had them and
    taken from the least-seen group first, shuffled within each group. That
    gives the guarantee that matters — nothing repeats while anything unseen
    remains — and then, once the pool really is exhausted, keeps going instead
    of stopping: a second round is drawn from the once-seen charts, a third
    from the twice-seen, and so on, so repetition stays as even and as far
    apart as the pool allows.

    A recycled round also avoids reproducing a set the coder has already sat,
    where the pool leaves any alternative — the same charts in the same company
    is the case where someone is most likely to be recalling rather than working.

    Returns (charts, note) where note describes the state of their pool.
    """
    if not pool:
        return [], {"state": "empty", "message": "no charts match the pool filters",
                    "unseen_left": 0, "round": 0}

    tiers: dict[int, list] = {}
    for chart in pool:
        tiers.setdefault(seen_counts.get(chart.id, 0), []).append(chart)
    for group in tiers.values():
        random.shuffle(group)

    unseen = len(tiers.get(0, []))

    def _take():
        out = []
        for level in sorted(tiers):
            if len(out) >= want:
                break
            out.extend(tiers[level][: want - len(out)])
        return out

    assigned = _take()

    # Only a fully recycled draw can repeat a previous set; reshuffle a few
    # times before accepting one. Bounded, because a pool of exactly `want`
    # charts has no alternative to offer and must not spin.
    if assigned and unseen == 0 and prior_sets:
        for _ in range(8):
            if {c.id for c in assigned} not in prior_sets:
                break
            for group in tiers.values():
                random.shuffle(group)
            assigned = _take()

    round_no = min(seen_counts.get(c.id, 0) for c in assigned) + 1 if assigned else 0

    if unseen == 0:
        message = (f"every chart in the pool has been sat — recycling for round {round_no}"
                   if len(pool) > want else
                   f"pool is only {len(pool)} chart(s); the same set repeats each cycle")
        state = "recycling"
    elif unseen < want:
        message = (f"only {unseen} unseen chart(s) left — this cycle repeats "
                   f"{want - unseen} of them")
        state = "nearly_exhausted"
    elif unseen <= want * 2:
        message = f"{unseen} unseen chart(s) left — enough for about "\
                  f"{unseen // want} more cycle(s)"
        state = "running_low"
    else:
        message = ""
        state = "healthy"

    return assigned, {"state": state, "message": message,
                      "unseen_left": unseen, "round": round_no}
