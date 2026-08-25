"""
Batch-loading the allocation inputs must not change what allocation is given.

Allocation used to issue one query per chart twice over — load_observations for
every chart in the pool, and sets_by_chart calling audit_key_for for every
chart. A 120-chart pool meant 242 sequential round trips before a single
assignment was built. Both are free against a local SQLite file and cost
seconds against a remote database, which is the whole reason they survived.

Only the FETCHING changed. These assert that the data handed to the allocator
is the same, which is the claim that matters — allocation itself is not
deterministic run to run, so comparing allocation OUTPUT proves nothing. That
was measured: three runs of identical code on identical input produced 39, 37
and 38 plantings.

The pool below is deliberately mixed. E/M charts take the branch that still
does a per-chart lookup, because their key lives in a table with no ORM model;
charts with no key at all must be omitted by both, not defaulted.
"""
from models import (AnswerKey, AuditKeySet, Chart, ChartStatus, Difficulty,
                    Specialty)
from routers.auditor_pkg.shared import sets_by_chart, audit_key_for
from services.audit_observations import load_observations, load_observations_bulk


def _pool(db, n=30):
    made = []
    for i in range(n):
        spec = Specialty.EM if i % 7 == 0 else Specialty.IP_DRG
        c = Chart(chart_number="BL%04d" % i, specialty=spec, category="Cardio",
                  difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
                  uploaded_by="t")
        db.add(c); db.flush(); made.append(c)
        if i % 5 == 0:
            continue                      # no key at all
        db.add(AnswerKey(chart_id=c.id, specialty=spec, pdx_code="J18.9", pdx_poa="Y",
                         sdx=[{"code": "E11.9", "poa": "Y", "ccmcc": "CC"}],
                         pcs=[{"code": "0DTJ0ZZ"}], cpt=[], entered_by="t"))
        db.flush()
        if i % 3 == 0:
            db.add(AuditKeySet(chart_id=c.id, name="v1", mutations=[], authored_by="t"))
    db.commit()
    return made


def test_the_pool_is_actually_mixed(db):
    """Guards the guard — a pool of one shape would prove very little."""
    made = _pool(db)
    specs = {c.specialty for c in made}
    assert Specialty.EM in specs and Specialty.IP_DRG in specs
    keyed = {k.chart_id for k in db.query(AnswerKey).all()}
    assert any(c.id not in keyed for c in made), "no unkeyed chart in the pool"


def test_sets_by_chart_matches_a_per_chart_lookup(db):
    made = _pool(db)
    ids = [c.id for c in made]
    charts = {c.id: c for c in made}

    # The shape sets_by_chart replaced: audit_key_for once per chart.
    per_chart = {cid: audit_key_for(db, chart) for cid, chart in charts.items()}
    batched = sets_by_chart(db, ids)

    for cid, sets in batched.items():
        assert per_chart.get(cid) is not None, (
            "chart %d has sets returned but no key — the batched lookup and the "
            "per-chart lookup disagree about which charts have a key" % cid)
    # Every chart with both a key and an authored set must appear.
    have_sets = {s.chart_id for s in db.query(AuditKeySet).all()}
    expected = {cid for cid in ids if per_chart.get(cid) is not None and cid in have_sets}
    assert set(batched) == expected


def test_bulk_observations_match_the_per_chart_loader(db):
    made = _pool(db)
    ids = [c.id for c in made]
    keys = {k.chart_id: k for k in db.query(AnswerKey).all()}

    one_at_a_time = {c.id: load_observations(db, c.id, keys.get(c.id))
                     for c in made if keys.get(c.id)}
    in_one_query = load_observations_bulk(db, ids, keys)

    assert set(one_at_a_time) == set(in_one_query), "different charts covered"
    for cid in one_at_a_time:
        assert ([str(x) for x in one_at_a_time[cid]]
                == [str(x) for x in in_one_query[cid]]), "chart %d differs" % cid


def test_the_bulk_loader_really_is_one_query(db):
    """The point of the change. Without this it could silently regress."""
    from sqlalchemy import event
    made = _pool(db)
    keys = {k.chart_id: k for k in db.query(AnswerKey).all()}
    # Touch every key first. The commit inside _pool expires them, and the
    # reload that follows would otherwise be counted against the loader — an
    # artefact of the fixture, not of the code under test.
    for k in keys.values():
        _ = k.sdx

    reads = []
    bind = db.get_bind()

    @event.listens_for(bind, "before_cursor_execute")
    def _count(conn, cursor, statement, *a, **k):
        if "practice_results" in statement:
            reads.append(statement)

    try:
        load_observations_bulk(db, [c.id for c in made], keys)
    finally:
        event.remove(bind, "before_cursor_execute", _count)

    assert len(reads) == 1, (
        "expected ONE practice_results query for the whole pool, got %d — "
        "the N+1 is back" % len(reads))
