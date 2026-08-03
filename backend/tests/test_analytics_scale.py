"""
Analytics query counts.

The endpoints on this page load results and then walk r.feedback, r.chart and
r.batch on each one. Lazily that is a query PER RESULT — invisible at a few
hundred rows and the first thing to fall over at scale. These tests count the
SQL actually issued, because nothing about the response shows the difference.
"""
import pytest
from sqlalchemy import event

from models import Chart, Batch, Specialty, GradingResult, GradingFeedback, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus


@pytest.fixture()
def counting(db):
    """Count SELECTs issued while the block runs."""
    engine = db.get_bind()
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    yield counter
    event.remove(engine, "before_cursor_execute", _before)


@pytest.fixture()
def many_results(db):
    """40 graded charts, each with feedback — enough for N+1 to show."""
    b = Batch(name="Scale", specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
              created_by="t", charts_per_coder=1, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    for i in range(40):
        c = Chart(chart_number=f"IPS{i:03d}", specialty=Specialty.IP_DRG,
                  category=f"Topic {i % 5}", difficulty=Difficulty.BEGINNER,
                  status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
        db.add(c); db.commit()
        r = GradingResult(batch_id=b.id, coder_name=f"Coder {i % 4}", emp_id=f"E{i % 4}",
                          chart_id=c.id, specialty=Specialty.IP_DRG, total_score=40 + i,
                          pass_fail=PassFail.PASS if i > 20 else PassFail.FAIL)
        db.add(r); db.commit()
        for j in range(3):
            db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
                                   ak_code=f"J{j}8.9", coder_code=None, detail=""))
        db.commit()
    return b


# Generous ceiling: the point is that it does not grow with the row count.
# Unbatched, 40 results walking three relationships would be ~120 extra.
QUERY_CEILING = 25


class TestQueriesDoNotGrowWithRows:
    def test_chart_signals(self, client, many_results, counting):
        counting["n"] = 0
        assert client.get("/practicelab/analytics/chart-teaching-value").status_code == 200
        assert counting["n"] < QUERY_CEILING, f"{counting['n']} queries for 40 results"

    def test_topic_mastery(self, client, many_results, counting):
        counting["n"] = 0
        assert client.get("/practicelab/analytics/by-category").status_code == 200
        assert counting["n"] < QUERY_CEILING, f"{counting['n']} queries for 40 results"

    def test_by_chart(self, client, many_results, counting):
        counting["n"] = 0
        assert client.get("/practicelab/analytics/by-chart").status_code == 200
        assert counting["n"] < QUERY_CEILING, f"{counting['n']} queries for 40 results"

    def test_coder_summary(self, client, many_results, counting):
        counting["n"] = 0
        r = client.get("/practicelab/analytics/coder-summary", params={"coder_name": "Coder 0"})
        assert r.status_code == 200
        assert counting["n"] < QUERY_CEILING, f"{counting['n']} queries"


class TestResponsesAreStillCorrect:
    """Eager loading must not change what comes back."""

    def test_chart_signals_covers_every_chart(self, client, many_results):
        rows = client.get("/practicelab/analytics/chart-teaching-value").json()
        assert len(rows) == 40

    def test_feedback_still_reaches_the_error_variety_count(self, client, many_results):
        rows = client.get("/practicelab/analytics/chart-teaching-value").json()
        assert all(r["error_variety"] == 3 for r in rows), "3 distinct missed codes each"
