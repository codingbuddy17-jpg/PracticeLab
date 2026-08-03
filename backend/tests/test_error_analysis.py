"""
Error Analysis: errors as the unit.

The figure this tab exists for is CONCENTRATION. A code missed forty times is
meaningless alone — forty by one coder is coaching, forty by twenty coders is
curriculum, forty on one chart is a suspect answer key. Same count, three
different actions, so the tests are mostly about telling them apart.
"""
import pytest
from datetime import datetime

from models import Chart, Batch, Specialty, GradingResult, GradingFeedback, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/error-analysis"
DETAIL = "/practicelab/analytics/error-detail"


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


def _err(db, b, c, coder, emp, code, issue="Missed", sect="SDx", when=None):
    r = GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                      specialty=c.specialty, total_score=50, pass_fail=PassFail.FAIL)
    db.add(r); db.commit()
    if when:
        r.graded_at = when
        db.commit()
    db.add(GradingFeedback(result_id=r.id, section=sect, issue_type=issue,
                           ak_code=code, coder_code=None, detail=""))
    db.commit()
    return r


def _row(client, code, **params):
    rows = client.get(URL, params=params).json()["codes"]
    return next(r for r in rows if r["code"] == code)


class TestConcentration:
    def test_one_coder_repeating_is_coaching(self, client, db):
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IPE{i}"), "Asha R", "E1", "J18.9")
        row = _row(client, "J18.9")
        assert row["coders_affected"] == 1
        assert row["pattern"] == "One coder"

    def test_many_coders_across_charts_is_a_teaching_gap(self, client, db):
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IPF{i}"), f"Coder {i}", f"E{i}", "J18.9")
        row = _row(client, "J18.9")
        assert row["coders_affected"] == 4
        assert row["charts_affected"] == 4
        assert row["pattern"] == "Team-wide"

    def test_many_coders_on_one_chart_points_at_the_key(self, client, db):
        """The same code missed by everyone on ONE chart is a chart problem,
        not a knowledge problem — the distinction the count alone hides."""
        b = _batch(db, "B")
        c = _chart(db, "IPG1")
        for i in range(4):
            _err(db, b, c, f"Coder {i}", f"E{i}", "J18.9")
        row = _row(client, "J18.9")
        assert row["charts_affected"] == 1
        assert row["pattern"] == "One chart"
        assert "answer key" in row["pattern_reason"]

    def test_the_same_count_yields_different_verdicts(self, client, db):
        """Four occurrences either way; only the spread differs."""
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IPH{i}"), "Solo", "S1", "A00.0")
        for i in range(4):
            _err(db, b, _chart(db, f"IPI{i}"), f"Coder {i}", f"E{i}", "B00.0")
        assert _row(client, "A00.0")["count"] == _row(client, "B00.0")["count"] == 4
        assert _row(client, "A00.0")["pattern"] == "One coder"
        assert _row(client, "B00.0")["pattern"] == "Team-wide"

    def test_coder_identity_is_emp_id(self, client, db):
        """Two spellings of one person must not look like a team-wide gap."""
        b = _batch(db, "B")
        for i, name in enumerate(("Asha R", "asha  r", "ASHA R")):
            _err(db, b, _chart(db, f"IPJ{i}"), name, "E1", "J18.9")
        assert _row(client, "J18.9")["coders_affected"] == 1


class TestBreakdowns:
    def test_issue_types_and_sections_are_reported(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPK1"), "A", "E1", "J18.9", issue="Missed", sect="SDx")
        _err(db, b, _chart(db, "IPK2"), "A", "E1", "27447", issue="Over_coded", sect="CPT")
        body = client.get(URL).json()
        assert {d["type"] for d in body["by_issue_type"]} == {"Missed", "Over_coded"}
        assert {d["section"] for d in body["by_section"]} == {"SDx", "CPT"}
        assert sum(d["pct"] for d in body["by_issue_type"]) == pytest.approx(100, abs=0.2)

    def test_every_issue_type_is_counted_not_just_missed(self, client, db):
        """By Chart shows missed codes only; a chart-level error picture that
        ignores over-coding and pointer errors is incomplete."""
        b = _batch(db, "B")
        for issue in ("Missed", "Wrong_Code", "Over_coded", "Wrong_Pointer", "Wrong_POA"):
            _err(db, b, _chart(db, f"IPL{issue}"), "A", "E1", f"X{issue}", issue=issue)
        assert len(client.get(URL).json()["by_issue_type"]) == 5

    def test_errors_per_chart_normalises_for_volume(self, client, db):
        """A raw error count rises just because more practice happened."""
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPM1"), "A", "E1", "J18.9")
        _err(db, b, _chart(db, "IPM2"), "A", "E1", "J18.9")
        assert client.get(URL).json()["errors_per_chart"] == 1.0


class TestFilters:
    def test_filter_by_issue_type(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPN1"), "A", "E1", "J18.9", issue="Missed")
        _err(db, b, _chart(db, "IPN2"), "A", "E1", "27447", issue="Over_coded")
        body = client.get(URL, params={"issue_type": "Over_coded"}).json()
        assert body["total_errors"] == 1
        assert body["codes"][0]["code"] == "27447"

    def test_filter_by_section(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPO1"), "A", "E1", "J18.9", sect="PDx")
        _err(db, b, _chart(db, "IPO2"), "A", "E1", "27447", sect="CPT")
        assert client.get(URL, params={"section": "PDx"}).json()["total_errors"] == 1

    def test_direct_work_is_excluded_by_default(self, client, db):
        d = _batch(db, "D", direct=True)
        _err(db, d, _chart(db, "IPP1"), "A", "E1", "J18.9")
        assert client.get(URL).json()["total_errors"] == 0
        assert client.get(URL, params={"scope": "all"}).json()["total_errors"] == 1


class TestTrend:
    def test_errors_are_grouped_by_month(self, client, db):
        """"Are we fixing it" needs a time axis, not a single number."""
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPQ1"), "A", "E1", "J18.9", when=datetime(2026, 1, 5))
        _err(db, b, _chart(db, "IPQ2"), "A", "E1", "J18.9", when=datetime(2026, 3, 5))
        _err(db, b, _chart(db, "IPQ3"), "A", "E1", "J18.9", when=datetime(2026, 3, 9))
        trend = client.get(URL).json()["trend"]
        assert [t["month"] for t in trend] == ["2026-01", "2026-03"]
        assert [t["total"] for t in trend] == [1, 2]


class TestDrilldown:
    def test_a_code_resolves_to_its_coders_and_charts(self, client, db):
        b = _batch(db, "B")
        c1, c2 = _chart(db, "IPR1"), _chart(db, "IPR2")
        _err(db, b, c1, "Asha R", "E1", "J18.9")
        _err(db, b, c1, "Bob", "E2", "J18.9")
        _err(db, b, c2, "Asha R", "E1", "J18.9")
        body = client.get(DETAIL, params={"code": "J18.9"}).json()
        assert {c["coder_name"] for c in body["coders"]} == {"Asha R", "Bob"}
        top = body["coders"][0]
        assert top["coder_name"] == "Asha R" and top["count"] == 2
        assert body["charts"][0]["chart_number"] == "IPR1"
        assert body["charts"][0]["coders"] == 2


class TestEmpty:
    def test_no_errors_is_not_an_error(self, client, db):
        b = _batch(db, "B")
        c = _chart(db, "IPS1")
        db.add(GradingResult(batch_id=b.id, coder_name="A", emp_id="E1", chart_id=c.id,
                             specialty=Specialty.IP_DRG, total_score=100, pass_fail=PassFail.PASS))
        db.commit()
        body = client.get(URL).json()
        assert body["total_errors"] == 0
        assert body["codes"] == []
