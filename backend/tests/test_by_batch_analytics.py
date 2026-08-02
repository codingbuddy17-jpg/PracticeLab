"""
The By Batch trend.

Two things here are easy to get wrong and impossible to see from the screen:
a batch appears on this tab because it has GRADED RESULTS, not because it was
closed; and the rows are filtered on when the batch was created while the
numbers describe when the work was graded. Both are pinned below.
"""
from datetime import datetime

import pytest

from models import Chart, Batch, Specialty, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/by-batch"


def _chart(db, number, specialty=Specialty.IP_DRG):
    c = Chart(chart_number=number, specialty=specialty, category="Sepsis",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, status=BatchStatus.OPEN, direct=False):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=status, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, batch, chart, coder, emp, score):
    db.add(GradingResult(batch_id=batch.id, coder_name=coder, emp_id=emp,
                         chart_id=chart.id, specialty=chart.specialty,
                         total_score=score,
                         pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL))
    db.commit()


class TestWhichBatchesAppear:
    def test_an_open_batch_with_results_appears(self, client, db):
        """
        The empty state used to tell trainers to CLOSE a batch to populate this
        tab. Closing has nothing to do with it — this is the proof.
        """
        b = _batch(db, "Still Open", status=BatchStatus.OPEN)
        _result(db, b, _chart(db, "IP800"), "A", "E1", 90)
        assert [r["batch_name"] for r in client.get(URL).json()] == ["Still Open"]

    def test_a_closed_batch_with_no_results_does_not(self, client, db):
        _batch(db, "Closed Empty", status=BatchStatus.CLOSED)
        assert client.get(URL).json() == []

    def test_ungraded_results_do_not_make_a_batch_appear(self, client, db):
        """A submission with no score yet is not a graded result."""
        b = _batch(db, "Awaiting Grading")
        db.add(GradingResult(batch_id=b.id, coder_name="A", emp_id="E1",
                             chart_id=_chart(db, "IP801").id, specialty=Specialty.IP_DRG,
                             total_score=None, pass_fail=None))
        db.commit()
        assert client.get(URL).json() == []


class TestCounts:
    def test_coder_count_uses_emp_id_not_the_typed_name(self, client, db):
        """
        emp_id is the coder identity everywhere else — the directory, the
        specialty profile, GradingResult itself. This endpoint counted distinct
        NAMES, so one person entered two ways doubled the column.
        """
        b = _batch(db, "Spellings")
        _result(db, b, _chart(db, "IP810"), "Asha R", "E1", 90)
        _result(db, b, _chart(db, "IP811"), "asha  r", "E1", 70)
        row = client.get(URL).json()[0]
        assert row["coder_count"] == 1, "one person, two spellings"
        assert row["chart_count"] == 2

    def test_chart_count_is_distinct_charts_not_results(self, client, db):
        """Two coders on one chart is one chart, two results."""
        b = _batch(db, "Shared Chart")
        c = _chart(db, "IP820")
        _result(db, b, c, "A", "E1", 90)
        _result(db, b, c, "B", "E2", 60)
        row = client.get(URL).json()[0]
        assert row["chart_count"] == 1
        assert row["graded_count"] == 2
        assert row["coder_count"] == 2

    def test_pass_rate_is_declared_chart_based(self, client, db):
        """
        Same key, different population from the batch RESULTS screen, which
        reports a per-coder rate. One coder, two charts, one passed: this
        endpoint must say 50%, not 100%.
        """
        b = _batch(db, "Basis")
        _result(db, b, _chart(db, "IP830"), "A", "E1", 90)
        _result(db, b, _chart(db, "IP831"), "A", "E1", 10)
        row = client.get(URL).json()[0]
        assert row["pass_rate"] == 50.0
        assert row["pass_rate_basis"] == "chart"


class TestDates:
    def test_both_dates_are_returned(self, client, db):
        """
        Rows are FILTERED on created_at while the scores describe graded_at.
        Both are exposed so the UI can label the difference rather than let one
        date stand in for the other.
        """
        b = _batch(db, "Dated")
        _result(db, b, _chart(db, "IP840"), "A", "E1", 90)
        r = db.query(GradingResult).one()
        r.graded_at = datetime(2026, 7, 1, 9, 0)
        b.created_at = datetime(2026, 1, 5, 9, 0)
        db.commit()
        row = client.get(URL).json()[0]
        assert row["created_at"].startswith("2026-01-05")
        assert row["last_graded_at"].startswith("2026-07-01")

    def test_the_filter_narrows_on_created_at(self, client, db):
        """
        Documented, not accidental: a batch created in January whose work was
        graded in July is OUT of a July range. Changing this to graded_at would
        make a batch half-appear whenever its results straddled a boundary.
        """
        b = _batch(db, "Jan Batch")
        _result(db, b, _chart(db, "IP850"), "A", "E1", 90)
        r = db.query(GradingResult).one()
        r.graded_at = datetime(2026, 7, 1, 9, 0)
        b.created_at = datetime(2026, 1, 5, 9, 0)
        db.commit()
        assert client.get(URL, params={"from_date": "2026-06-01", "to_date": "2026-08-01"}).json() == []
        assert len(client.get(URL, params={"from_date": "2026-01-01", "to_date": "2026-02-01"}).json()) == 1


class TestScope:
    def test_direct_rows_are_flagged_so_the_ui_can_reword(self, client, db):
        d = _batch(db, "One Off", direct=True)
        _result(db, d, _chart(db, "IP860"), "A", "E1", 90)
        rows = client.get(URL, params={"scope": "direct"}).json()
        assert rows[0]["is_direct_assignment"] is True

    def test_chronological_order_for_the_trend_line(self, client, db):
        """The chart plots these in order — reversing it inverts every trend."""
        for name, day in (("Second", 2), ("First", 1), ("Third", 3)):
            b = _batch(db, name)
            _result(db, b, _chart(db, f"IP87{day}"), "A", "E1", 90)
            b.created_at = datetime(2026, 3, day, 9, 0)
            db.commit()
        assert [r["batch_name"] for r in client.get(URL).json()] == ["First", "Second", "Third"]
