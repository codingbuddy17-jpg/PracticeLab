"""
By Chart: the inspection view.

Distinct from Chart Signals, which classifies charts so a trainer knows WHICH
to open. This is what you see once you have opened one — the score, the codes
people miss on it, and which coders those were.
"""
import pytest

from models import Chart, Batch, Specialty, GradingResult, GradingFeedback, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/by-chart"


def _chart(db, n, sp=Specialty.IP_DRG, cat="Sepsis"):
    c = Chart(chart_number=n, specialty=sp, category=cat, difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, direct=False):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, b, c, score, coder="A", emp="E1", missed=()):
    r = GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                      specialty=c.specialty, total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    for code in missed:
        db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
                               ak_code=code, coder_code=None, detail=""))
    db.commit()
    return r


class TestChartOwnPassMark:
    def test_each_chart_carries_the_bar_it_is_judged_against(self, client, db):
        """A score is not readable without knowing which threshold applies,
        and the threshold differs by specialty."""
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IPC1"), 85)
        _result(db, b, _chart(db, "SDSC1", Specialty.SDS), 85, emp="E2")
        marks = {r["chart_number"]: r["pass_threshold"] for r in client.get(URL).json()}
        assert marks == {"IPC1": 80, "SDSC1": 90}

    def test_pass_rate_is_reported_alongside_the_average(self, client, db):
        b = _batch(db, "B")
        c = _chart(db, "IPC2")
        _result(db, b, c, 90, emp="E1")
        _result(db, b, c, 10, emp="E2")
        row = client.get(URL).json()[0]
        assert row["avg_score"] == 50.0
        assert row["pass_rate"] == 50.0


class TestScope:
    def test_direct_work_is_excluded_by_default(self, client, db):
        d = _batch(db, "D", direct=True)
        _result(db, d, _chart(db, "IPC3"), 40)
        assert client.get(URL).json() == []

    def test_scope_all_includes_it(self, client, db):
        d = _batch(db, "D", direct=True)
        _result(db, d, _chart(db, "IPC4"), 40)
        assert len(client.get(URL, params={"scope": "all"}).json()) == 1

    def test_a_bad_scope_is_rejected(self, client):
        assert client.get(URL, params={"scope": "sideways"}).status_code == 400


class TestOrdering:
    def test_worst_scoring_first(self, client, db):
        """The tab is opened to find problems, so the problems come first."""
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IPC5"), 95, emp="E1")
        _result(db, b, _chart(db, "IPC6"), 20, emp="E2")
        assert [r["chart_number"] for r in client.get(URL).json()] == ["IPC6", "IPC5"]


class TestChartDetail:
    def test_it_reports_how_many_coders_there_were(self, client, db):
        """
        The panel shows the lowest eight. Without a total, a truncated list
        reads as "eight coders attempted this", which is a different claim.
        """
        b = _batch(db, "B")
        c = _chart(db, "IPC7")
        for i in range(12):
            _result(db, b, c, 40 + i, coder=f"C{i}", emp=f"E{i}")
        body = client.get(f"/practicelab/analytics/chart-detail/IPC7").json()
        assert body["total_coders"] == 12
        assert len(body["coders"]) == 12

    def test_missed_codes_travel_with_each_coder(self, client, db):
        b = _batch(db, "B")
        c = _chart(db, "IPC8")
        _result(db, b, c, 40, missed=("J18.9", "E11.9"))
        body = client.get("/practicelab/analytics/chart-detail/IPC8").json()
        assert set(body["coders"][0]["missed_codes"]) == {"J18.9", "E11.9"}


class TestQueryCount:
    def test_chart_detail_does_not_fire_a_query_per_result(self, client, db):
        """
        It built its own query, so it never picked up the eager loading added
        to the shared base — one query per result, on the endpoint that fires
        every time a row is expanded.
        """
        from sqlalchemy import event
        b = _batch(db, "B")
        c = _chart(db, "IPC9")
        for i in range(20):
            _result(db, b, c, 50, coder=f"C{i}", emp=f"E{i}", missed=("J18.9",))

        engine = db.get_bind()
        n = {"count": 0}

        def _before(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                n["count"] += 1

        event.listen(engine, "before_cursor_execute", _before)
        try:
            assert client.get("/practicelab/analytics/chart-detail/IPC9").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        assert n["count"] < 15, f"{n['count']} queries for 20 results"
