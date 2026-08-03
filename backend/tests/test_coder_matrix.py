"""
Coder Matrix: coders down, closed batches across.

Its whole value is comparing like with like, which makes two things load-
bearing: a coder must be ONE row however their name was typed, and a cell must
be judged against the pass mark of the batch it sits in — the columns can be
different specialties with different bars.
"""
import pytest

from models import Chart, Batch, Specialty, GradingResult, PassFail, BatchCoder
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/coder-matrix"


def _chart(db, n, sp=Specialty.IP_DRG):
    c = Chart(chart_number=n, specialty=sp, category="Sepsis", difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, sp=Specialty.IP_DRG, status=BatchStatus.CLOSED, direct=False):
    from datetime import datetime
    b = Batch(name=name, specialty=sp, status=status, created_by="t", charts_per_coder=1,
              is_direct_assignment=direct, use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    if status == BatchStatus.CLOSED:
        b.closed_at = datetime(2026, 6, 1)
        db.commit()
    return b


def _result(db, b, c, score, coder="Asha R", emp="E1"):
    db.add(GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                         specialty=c.specialty, total_score=score,
                         pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL))
    db.commit()


class TestIdentity:
    def test_one_person_is_one_row(self, client, db):
        """
        Grouped by the typed name, "Asha R" and "asha  r" were two rows, each
        holding part of the history — on a grid that reads as two coders with
        patchy participation rather than one with a full record.
        """
        b1, b2 = _batch(db, "B1"), _batch(db, "B2")
        _result(db, b1, _chart(db, "IPM1"), 90, coder="Asha R", emp="E1")
        _result(db, b2, _chart(db, "IPM2"), 70, coder="asha  r", emp="E1")
        body = client.get(URL).json()
        assert len(body["coders"]) == 1
        assert len(body["cells"]) == 2, "both batches on the one row"

    def test_the_row_still_shows_a_readable_name(self, client, db):
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IPM3"), 90, coder="Asha R", emp="E7")
        body = client.get(URL).json()
        cid = body["coders"][0]
        assert body["coder_names"][cid] == "Asha R"
        assert body["coder_emp_ids"][cid] == "E7"


class TestPerBatchThresholds:
    def test_each_column_carries_its_own_pass_mark(self, client, db):
        """
        Cells were coloured against a hardcoded 80, so an SDS batch showed
        green at 82 when its bar is 90.
        """
        ip = _batch(db, "IP Batch")
        sds = _batch(db, "SDS Batch", sp=Specialty.SDS)
        _result(db, ip, _chart(db, "IPM4"), 82)
        _result(db, sds, _chart(db, "SDSM1", Specialty.SDS), 82, emp="E2", coder="B")
        marks = {b["name"]: b["pass_threshold"] for b in client.get(URL).json()["batches"]}
        assert marks == {"IP Batch": 80, "SDS Batch": 90}


class TestCellContents:
    def test_pass_counts_travel_with_the_score(self, client, db):
        """The endpoint already computed pass_rate; the cell had no way to
        show how many charts that was."""
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IPM5"), 90)
        _result(db, b, _chart(db, "IPM6"), 40)
        cell = client.get(URL).json()["cells"][0]
        assert cell["chart_count"] == 2
        assert cell["charts_passed"] == 1
        assert cell["pass_rate"] == 50.0


class TestScope:
    def test_open_batches_are_excluded(self, client, db):
        b = _batch(db, "Still Open", status=BatchStatus.OPEN)
        _result(db, b, _chart(db, "IPM7"), 90)
        assert client.get(URL).json()["batches"] == []

    def test_direct_assignments_are_excluded(self, client, db):
        b = _batch(db, "Direct", direct=True)
        _result(db, b, _chart(db, "IPM8"), 90)
        assert client.get(URL).json()["batches"] == []

    def test_the_scope_is_stated_in_the_payload(self, client, db):
        """Deliberate exclusion, so it has to be visible rather than inferred."""
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IPM9"), 90)
        note = client.get(URL).json()["scope_note"]
        assert "closed" in note.lower()


class TestDirectAssignments:
    """
    Direct assignments cannot be columns — each is typically one chart for one
    coder, so a column apiece would be hundreds of columns holding one cell.
    Excluding them outright made a coder who works mainly that way look absent
    from the grid with nothing explaining why. They aggregate into one column.
    """

    @pytest.fixture()
    def mixed(self, db):
        formal = _batch(db, "Formal")
        direct = _batch(db, "One Off", direct=True, status=BatchStatus.OPEN)
        _result(db, formal, _chart(db, "IPD1"), 90)
        _result(db, direct, _chart(db, "IPD2"), 40)
        _result(db, direct, _chart(db, "IPD3"), 60)
        return formal, direct

    def test_the_default_view_says_what_it_is_hiding(self, client, mixed):
        body = client.get(URL).json()
        assert body["excluded_direct_results"] == 2
        assert "not shown" in body["scope_note"]

    def test_scope_all_adds_one_aggregated_column(self, client, mixed):
        cols = client.get(URL, params={"scope": "all"}).json()["batches"]
        assert [c["name"] for c in cols] == ["Formal", "Direct work"]
        assert cols[-1]["is_direct"] is True

    def test_the_direct_column_aggregates_the_whole_history(self, client, mixed):
        body = client.get(URL, params={"scope": "all"}).json()
        cell = next(c for c in body["cells"] if c["batch_id"] == -1)
        assert cell["chart_count"] == 2, "both direct charts in one cell"
        assert cell["avg_score"] == 50.0

    def test_a_coder_with_only_direct_work_still_appears(self, client, db):
        """The case that made this worth fixing."""
        d = _batch(db, "Direct Only", direct=True, status=BatchStatus.OPEN)
        _result(db, d, _chart(db, "IPD9"), 70, coder="Direct Only Coder", emp="E9")
        assert client.get(URL).json()["coders"] == []
        body = client.get(URL, params={"scope": "all"}).json()
        assert len(body["coders"]) == 1

    def test_mixed_specialty_direct_work_gets_no_single_pass_mark(self, client, db):
        d = _batch(db, "D", direct=True, status=BatchStatus.OPEN)
        _result(db, d, _chart(db, "IPD5"), 85)
        _result(db, d, _chart(db, "SDSD1", Specialty.SDS), 85)
        col = next(c for c in client.get(URL, params={"scope": "all"}).json()["batches"]
                   if c["is_direct"])
        assert col["pass_threshold"] is None
