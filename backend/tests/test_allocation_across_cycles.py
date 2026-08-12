"""
Nothing repeats for a coder while anything unseen remains — and running out is
not a reason to stop.

Allocation draws at random, and an unguarded random draw would hand a coder work
they have already done, measuring their memory rather than their coding. Charts
are therefore grouped by how many times THIS coder has had them and taken
least-seen first, so the unseen ones go first every time.

Exhaustion is per coder, not per batch or per group. Alice having seen
everything says nothing about Bob, and one coder running dry never holds up
anyone else. When a coder's own pool is finished the draw recycles rather than
skipping them: a second round from the once-seen charts, a third from the
twice-seen, spread evenly and avoiding any set they have already sat.

Two coders receiving the same chart in one cycle is deliberate — it is the only
way their answers on it can be compared.

Scope pinned below: the guard is batch-scoped. The same coder in a different
batch can be given the same chart again, which is right for a refresher and
wrong for a sequential programme.
"""
import pytest

from models import (
    Batch, BatchChart, BatchCoder, Chart, ChartStatus, Difficulty, Specialty,
)

PASS = "test-passphrase"


@pytest.fixture()
def batch_of(db):
    """A batch with `n` charts in the pool and the given coders."""
    def _make(n_charts=6, coders=("Alice",), specialty=Specialty.SDS):
        for i in range(n_charts):
            db.add(Chart(chart_number=f"C{i:03d}", specialty=specialty, category="Test",
                         difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
                         uploaded_by="t"))
        b = Batch(name="Wave", specialty=specialty, charts_per_coder=2, created_by="t")
        db.add(b)
        db.flush()
        for c in coders:
            db.add(BatchCoder(batch_id=b.id, coder_name=c))
        db.commit()
        return b
    return _make


def _run(client, batch_id, charts_per_coder=2):
    return client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                       json={"charts_per_coder": charts_per_coder, "run_by": "Trainer"})


def _charts_for(db, batch_id, coder):
    return [a.chart_id for a in db.query(BatchChart).filter(
        BatchChart.batch_id == batch_id, BatchChart.coder_name == coder).all()]


# ── the guarantee ────────────────────────────────────────────────────────────

def test_a_second_cycle_never_repeats_a_chart(client, db, batch_of):
    b = batch_of(n_charts=6)
    assert _run(client, b.id).status_code == 200
    first = set(_charts_for(db, b.id, "Alice"))
    assert len(first) == 2

    assert _run(client, b.id).status_code == 200
    db.expire_all()
    everything = _charts_for(db, b.id, "Alice")
    assert len(everything) == len(set(everything)), "a chart was assigned to the same coder twice"
    assert len(everything) == 4


def test_the_guarantee_holds_across_many_cycles(client, db, batch_of):
    """Run the pool down to nothing; every chart must appear exactly once."""
    b = batch_of(n_charts=6)
    for _ in range(3):
        _run(client, b.id)
    db.expire_all()
    got = _charts_for(db, b.id, "Alice")
    assert sorted(got) == sorted(set(got))
    assert len(got) == 6, "the pool should have been exhausted exactly"


def test_an_exhausted_pool_keeps_assigning_rather_than_stopping(client, db, batch_of):
    """
    Running out is not a reason to hand a coder nothing. Once every chart has
    been sat, the draw recycles — a second round from the once-seen charts —
    rather than skipping them and leaving a cycle they cannot work on.
    """
    b = batch_of(n_charts=4)
    _run(client, b.id)
    _run(client, b.id)
    db.expire_all()

    r = _run(client, b.id)
    assert r.status_code == 200
    body = r.json()
    assert body["assigned"].get("Alice") == 2, "the coder was skipped instead of recycled"
    note = body["coder_pool_notes"]["Alice"]
    assert note["state"] == "recycling"
    assert note["round"] == 2
    assert "recycling" in note["message"]


def test_recycling_spreads_evenly_before_anything_comes_round_a_third_time(client, db, batch_of):
    """
    Least-seen first. Everything is sat twice before anything is sat three
    times, so repetition stays as far apart as the pool allows.
    """
    b = batch_of(n_charts=4)
    for _ in range(4):          # 4 cycles x 2 charts = every chart twice
        _run(client, b.id)
    db.expire_all()
    got = _charts_for(db, b.id, "Alice")
    counts = {cid: got.count(cid) for cid in set(got)}
    assert set(counts.values()) == {2}, f"uneven recycling: {counts}"


def test_a_recycled_round_avoids_repeating_a_previous_set(client, db, batch_of):
    """
    The same charts in the same company is where a coder is most likely to be
    recalling rather than coding. Given any alternative, the draw takes it.
    """
    b = batch_of(n_charts=4)
    _run(client, b.id)          # cycle 1: two of four
    _run(client, b.id)          # cycle 2: the other two
    db.expire_all()
    seen_sets = set()
    for a in db.query(BatchChart).filter(BatchChart.batch_id == b.id).all():
        seen_sets.add(a.cycle_id)

    r = _run(client, b.id)      # cycle 3 must recycle
    assert r.json()["coder_pool_notes"]["Alice"]["state"] == "recycling"

    db.expire_all()
    by_cycle = {}
    for a in db.query(BatchChart).filter(BatchChart.batch_id == b.id).all():
        by_cycle.setdefault(a.cycle_id, set()).add(a.chart_id)
    sets = list(by_cycle.values())
    assert len(sets) == len({frozenset(x) for x in sets}), \
        "a recycled cycle reproduced an earlier set while an alternative existed"


def test_a_short_pool_says_how_much_is_left_before_it_recycles(client, db, batch_of):
    b = batch_of(n_charts=3)
    _run(client, b.id, charts_per_coder=2)
    r = _run(client, b.id, charts_per_coder=2)

    note = r.json()["coder_pool_notes"]["Alice"]
    assert note["state"] == "nearly_exhausted"
    assert note["unseen_left"] == 1
    assert "1 unseen chart" in note["message"]
    # Still a full cycle: the one unseen chart plus one repeat, not a short one.
    assert r.json()["assigned"]["Alice"] == 2


def test_a_healthy_pool_says_nothing(client, db, batch_of):
    """A note on every cycle would be noise; it appears when it means something."""
    b = batch_of(n_charts=20)
    r = _run(client, b.id, charts_per_coder=2)
    note = r.json()["coder_pool_notes"]["Alice"]
    assert note["state"] == "healthy"
    assert note["message"] == ""
    assert r.json()["warnings"] == []


def test_one_coder_running_dry_does_not_hold_up_another(client, db, batch_of):
    """
    Exhaustion is per coder. Alice having seen everything says nothing about
    Bob, who joined later and has the whole pool ahead of him.
    """
    b = batch_of(n_charts=4, coders=("Alice",))
    _run(client, b.id)
    _run(client, b.id)          # Alice has now seen all four

    db.add(BatchCoder(batch_id=b.id, coder_name="Bob"))
    db.commit()

    r = _run(client, b.id)
    notes = r.json()["coder_pool_notes"]
    assert notes["Alice"]["state"] == "recycling"
    assert notes["Bob"]["state"] in ("healthy", "running_low", "nearly_exhausted")
    assert notes["Bob"]["unseen_left"] == 4, "Bob was judged against Alice's history"

    db.expire_all()
    bob = _charts_for(db, b.id, "Bob")
    assert len(bob) == len(set(bob)) == 2


def test_the_notes_survive_on_the_cycle(client, db, batch_of):
    """Readable next month, not just in a toast that lasted six seconds."""
    b = batch_of(n_charts=3)
    _run(client, b.id, charts_per_coder=2)
    _run(client, b.id, charts_per_coder=2)
    cycles = client.get(f"/practicelab/batches/{b.id}").json()["allocation_cycles"]
    assert cycles[-1]["coder_pool_notes"]["Alice"]["unseen_left"] == 1


def test_two_coders_may_share_a_chart_in_the_same_cycle(client, db, batch_of):
    """
    Not a bug — it is the only way two coders' answers on the same chart can be
    compared. The uniqueness guarantee is per coder, not per batch.
    """
    b = batch_of(n_charts=2, coders=("Alice", "Bob"))
    _run(client, b.id, charts_per_coder=2)
    db.expire_all()
    assert sorted(_charts_for(db, b.id, "Alice")) == sorted(_charts_for(db, b.id, "Bob"))


def test_each_cycle_records_how_unique_its_draw_was(client, db, batch_of):
    """The evidence a trainer reads later, rather than a toast that vanished."""
    b = batch_of(n_charts=8, coders=("Alice", "Bob"))
    _run(client, b.id, charts_per_coder=2)
    cycles = client.get(f"/practicelab/batches/{b.id}").json()["allocation_cycles"]
    assert cycles[0]["randomisation_stats"] is not None
    assert "per_coder" in cycles[0]["randomisation_stats"]


# ── what the guard does NOT cover ────────────────────────────────────────────

def test_the_guard_is_batch_scoped_not_coder_scoped(client, db, batch_of):
    """
    Pinning a real limitation rather than asserting it away. A coder in a second
    batch can be given a chart they already did in the first — right for a
    refresher, wrong for a sequential programme. If that ever needs to change,
    this test is where the decision gets recorded.
    """
    b1 = batch_of(n_charts=2)
    _run(client, b1.id, charts_per_coder=2)
    first = set(_charts_for(db, b1.id, "Alice"))

    b2 = Batch(name="Wave 2", specialty=Specialty.SDS, charts_per_coder=2, created_by="t")
    db.add(b2)
    db.flush()
    db.add(BatchCoder(batch_id=b2.id, coder_name="Alice"))
    db.commit()
    _run(client, b2.id, charts_per_coder=2)
    db.expire_all()

    assert set(_charts_for(db, b2.id, "Alice")) & first, (
        "cross-batch repeats are currently expected — if this now fails, the "
        "scope of the guard changed and that is a decision worth documenting")
