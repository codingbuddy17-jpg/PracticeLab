"""
A coder never sits the same chart twice in one batch.

Allocation draws at random, and a random draw repeated across cycles would hand
a coder work they have already done — which measures their memory rather than
their coding. The guard is that each coder's available pool excludes everything
already assigned to THEM in this batch, across every cycle, not just the one
being run.

It is deliberately per-coder, not per-batch: two coders receiving the same chart
in the same cycle is normal and useful, because it is the only way their answers
can be compared against each other.

Scope note pinned below: the guard is batch-scoped. The same coder in a
different batch can be given the same chart again, which is correct for a
refresher and wrong for a sequential programme — worth knowing before relying
on it.
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


def test_an_exhausted_pool_warns_rather_than_repeating(client, db, batch_of):
    b = batch_of(n_charts=4)
    _run(client, b.id)
    _run(client, b.id)
    db.expire_all()

    r = _run(client, b.id)
    assert r.status_code == 200
    body = r.json()
    assert body["warnings"], "a cycle that could assign nothing must say so"
    assert any("exhausted" in w.lower() for w in body["warnings"])

    got = _charts_for(db, b.id, "Alice")
    assert len(got) == len(set(got)) == 4, "repeats crept in once the pool ran dry"


def test_a_short_pool_assigns_what_is_left_and_says_so(client, db, batch_of):
    b = batch_of(n_charts=3)
    _run(client, b.id, charts_per_coder=2)
    r = _run(client, b.id, charts_per_coder=2)
    assert any("only 1 chart" in w for w in r.json()["warnings"])
    got = _charts_for(db, b.id, "Alice")
    assert len(got) == len(set(got)) == 3


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
