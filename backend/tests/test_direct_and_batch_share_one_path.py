"""
A direct assignment is a batch with a different scope, not a different product.

Both flows create through the same endpoint, allocate through the same
endpoint, issue the same access codes, use the same coder form, run the same
grading engine, and write to the same two tables. The only differences that
should survive are the words on the screen and whether the work counts toward
cohort analytics.

What had survived instead was a second read path. Results for a direct
assignment were rebuilt from practice_results by hand, and that hand-built row
hardcoded None for every component score and all four DPO figures — data that
grading_results holds for exactly the same chart. So the same graded work
showed a full breakdown under one flow and blanks under the other.
"""
import pytest

from models import (
    Batch, BatchChart, BatchCoder, Chart, ChartStatus, Difficulty,
    GradingResult, PassFail, Specialty,
)


@pytest.fixture()
def graded(db):
    """
    One chart graded for one coder, in either flow.

    Written straight into grading_results, which is where both flows land: the
    practice grading path mirrors every result there, and historical rows were
    backfilled.
    """
    def _make(direct: bool):
        chart = Chart(chart_number=f"D{int(direct)}01", specialty=Specialty.SDS,
                      category="Test", difficulty=Difficulty.INTERMEDIATE,
                      status=ChartStatus.ACTIVE, uploaded_by="t")
        db.add(chart)
        b = Batch(name=f"{'Direct' if direct else 'Batch'} work", specialty=Specialty.SDS,
                  charts_per_coder=1, created_by="t", is_direct_assignment=direct,
                  use_dpo=True)
        db.add(b)
        db.flush()
        db.add(BatchCoder(batch_id=b.id, coder_name="Alice", emp_id="E1"))
        db.add(BatchChart(batch_id=b.id, coder_name="Alice", chart_id=chart.id))
        db.add(GradingResult(
            batch_id=b.id, submission_id=None, coder_name="Alice", emp_id="E1",
            chart_id=chart.id, specialty=Specialty.SDS,
            pdx_score=20.0, sdx_score=22.0, cpt_score=45.0,
            total_score=87.0, pass_fail=PassFail.PASS,
            dpo_dx_accuracy=91.0, dpo_proc_accuracy=88.0, dpo_overall_accuracy=90.0,
        ))
        db.commit()
        return b
    return _make


def _results(client, batch_id):
    r = client.get(f"/practicelab/batches/{batch_id}/results")
    assert r.status_code == 200, r.text
    return r.json()


# ── the same graded work reads the same either way ───────────────────────────

def test_a_direct_assignment_reports_its_component_scores(client, db, graded):
    """
    The defect the second read path carried: it hardcoded None for every one of
    these, so a direct assignment's Results screen showed a total and nothing
    behind it.
    """
    b = graded(direct=True)
    chart = _results(client, b.id)["coder_summaries"][0]["charts"][0]
    assert chart["pdx_score"] == 20.0
    assert chart["sdx_score"] == 22.0
    assert chart["cpt_score"] == 45.0


def test_a_direct_assignment_reports_its_dpo_accuracy(client, db, graded):
    """
    Same defect, and the reason the per-chart DPO column would have been
    permanently blank for direct work.
    """
    b = graded(direct=True)
    chart = _results(client, b.id)["coder_summaries"][0]["charts"][0]
    assert chart["dpo_overall_accuracy"] == 90.0
    assert chart["dpo_dx_accuracy"] == 91.0


def test_both_flows_return_the_same_shape(client, db, graded):
    direct = _results(client, graded(direct=True).id)
    batch = _results(client, graded(direct=False).id)
    assert set(direct) == set(batch)
    assert set(direct["coder_summaries"][0]) == set(batch["coder_summaries"][0])
    assert set(direct["coder_summaries"][0]["charts"][0]) == \
           set(batch["coder_summaries"][0]["charts"][0])


def test_both_flows_report_the_same_numbers(client, db, graded):
    """Identical work must not read differently because of a flag on the batch."""
    direct = _results(client, graded(direct=True).id)["coder_summaries"][0]
    batch = _results(client, graded(direct=False).id)["coder_summaries"][0]
    for field in ("avg_total", "pass_fail", "chart_count"):
        assert direct.get(field) == batch.get(field), f"{field} differs by flow"


def test_the_flag_still_marks_the_batch(client, db, graded):
    """The distinction survives where it belongs — scope, not data shape."""
    assert _results(client, graded(direct=True).id)["is_direct_assignment"] is True
    assert _results(client, graded(direct=False).id)["is_direct_assignment"] is False


# ── closing ──────────────────────────────────────────────────────────────────

def test_a_batch_closes_once_its_charts_are_graded(client, db, graded):
    """
    The close guard counted BatchChart rows still marked PENDING. Nothing sets
    that column any more outside the Edits/Denials rubric — coding moved to
    in-browser sessions — so an ordinary batch could never satisfy it and could
    never be closed. It is graded work that decides, the same as direct.
    """
    b = graded(direct=False)
    r = client.post(f"/practicelab/batches/{b.id}/close", json={"closed_by": "Trainer"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Batch).filter(Batch.id == b.id).first().status.value == "Closed"


def test_a_batch_with_ungraded_work_still_refuses_to_close(client, db):
    """The guard must keep doing its job, just against the right column."""
    chart = Chart(chart_number="U001", specialty=Specialty.SDS, category="T",
                  difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
                  uploaded_by="t")
    db.add(chart)
    b = Batch(name="Unfinished", specialty=Specialty.SDS, charts_per_coder=1,
              created_by="t")
    db.add(b)
    db.flush()
    db.add(BatchCoder(batch_id=b.id, coder_name="Alice"))
    db.add(BatchChart(batch_id=b.id, coder_name="Alice", chart_id=chart.id))
    db.commit()

    r = client.post(f"/practicelab/batches/{b.id}/close", json={"closed_by": "Trainer"})
    assert r.status_code == 400
    assert "not yet graded" in r.json()["detail"].lower()
