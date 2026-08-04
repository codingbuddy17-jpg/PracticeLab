"""
A direct assignment must list each chart once.

get_batch() builds coder_map from BatchChart rows, then — for direct
assignments only — appends a row per graded practice_result. Both describe the
same coder working the same chart, so every graded direct assignment showed its
charts twice and reported double the work assigned.
"""
from sqlalchemy import text

from conftest import make_chart
from models import Batch, BatchCoder, BatchChart, BatchStatus, SubmissionStatus


def _direct_batch(db, graded: bool, chart_numbers=("IP001",)):
    charts = [make_chart(db, chart_number=n) for n in chart_numbers]
    b = Batch(name="Sepsis remediation", specialty=charts[0].specialty,
              categories=[], difficulties=[], charts_per_coder=len(charts),
              status=BatchStatus.OPEN, created_by="trainer",
              is_direct_assignment=True)
    db.add(b)
    db.flush()
    db.add(BatchCoder(batch_id=b.id, coder_name="Alice"))
    for c in charts:
        db.add(BatchChart(
            batch_id=b.id, coder_name="Alice", chart_id=c.id,
            submission_status=(SubmissionStatus.SUBMITTED if graded
                               else SubmissionStatus.PENDING),
        ))
    db.flush()

    if graded:
        db.execute(text(
            "INSERT INTO practice_sessions (batch_id, coder_name, specialty, token,"
            " chart_ids, status) VALUES (:b,'Alice','IP-DRG','TK-1','[]','submitted')"
        ), {"b": b.id})
        sid = db.execute(text("SELECT id FROM practice_sessions")).fetchone()[0]
        for c in charts:
            db.execute(text(
                "INSERT INTO practice_results (session_id, chart_id, specialty, total_score)"
                " VALUES (:s,:c,'IP-DRG',90)"
            ), {"s": sid, "c": c.id})
    db.commit()
    return b


def _alice(client, batch_id):
    d = client.get(f"/practicelab/batches/{batch_id}").json()
    return [c for c in d["coders"] if c["name"] == "Alice"][0], d


def test_a_graded_chart_appears_once(client, db):
    b = _direct_batch(db, graded=True)
    alice, _ = _alice(client, b.id)
    ids = [c["chart_id"] for c in alice["charts"]]
    assert len(ids) == len(set(ids)) == 1, f"chart listed more than once: {alice['charts']}"


def test_multiple_graded_charts_each_appear_once(client, db):
    b = _direct_batch(db, graded=True, chart_numbers=("IP001", "IP002", "IP003"))
    alice, _ = _alice(client, b.id)
    ids = sorted(c["chart_id"] for c in alice["charts"])
    assert len(ids) == len(set(ids)) == 3


def test_the_graded_row_wins_so_detail_is_not_lost(client, db):
    """
    Deduping must keep the richer row. The BatchChart row carries difficulty;
    the practice_result row carries the submitted status. Neither alone is
    complete, so the merge has to preserve both.
    """
    b = _direct_batch(db, graded=True)
    alice, _ = _alice(client, b.id)
    row = alice["charts"][0]
    assert row["submission_status"] == "Submitted"
    assert row["difficulty"] is not None, "difficulty came from the assignment row"
    assert row["chart_number"] == "IP001"


def test_ungraded_direct_assignment_still_lists_its_charts(client, db):
    b = _direct_batch(db, graded=False)
    alice, _ = _alice(client, b.id)
    assert len(alice["charts"]) == 1
    assert alice["charts"][0]["submission_status"] == "Pending"


def test_direct_graded_count_is_unaffected(client, db):
    b = _direct_batch(db, graded=True, chart_numbers=("IP001", "IP002"))
    _, d = _alice(client, b.id)
    assert d["direct_graded_count"] == 2
