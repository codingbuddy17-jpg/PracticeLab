"""
Teaching Value: which charts are worth teaching with.

Two rules here are easy to get subtly wrong and impossible to see from the
screen: every chart must be judged against ITS OWN specialty's pass mark, and
"how many attempts passed" is a share that must never be compared to a score.
"""
import pytest

from models import Chart, Batch, Specialty, GradingResult, GradingFeedback, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/chart-teaching-value"


def _chart(db, n, sp=Specialty.IP_DRG, cat="Sepsis"):
    c = Chart(chart_number=n, specialty=sp, category=cat, difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, direct=False, sp=Specialty.IP_DRG):
    b = Batch(name=name, specialty=sp, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, b, c, score, emp="E1", missed=()):
    r = GradingResult(batch_id=b.id, coder_name=f"C{emp}", emp_id=emp, chart_id=c.id,
                      specialty=c.specialty, total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    for code in missed:
        db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
                               ak_code=code, coder_code=None, detail=""))
    db.commit()
    return r


def _label(client, number, **params):
    rows = client.get(URL, params=params).json()
    return next(r["teaching_label"] for r in rows if r["chart_number"] == number)


class TestPerChartThreshold:
    """
    The rule used to pick ONE threshold for the whole response: if any IP
    result was present, every chart — SDS, Surgery, E/M — was judged against
    IP's 80. In a mixed view that silently mislabelled everything non-IP.
    """

    def test_an_sds_chart_is_judged_against_the_sds_mark(self, client, db):
        b = _batch(db, "SDS B", sp=Specialty.SDS)
        c = _chart(db, "SDS900", Specialty.SDS)
        for e in ("E1", "E2", "E3"):
            _result(db, b, c, 92, emp=e)
        # 92 clears IP's "too easy" cutoff of 90 but not SDS's 95.
        assert _label(client, "SDS900") != "Too Easy"

    def test_an_ip_chart_at_the_same_score_is_too_easy(self, client, db):
        b = _batch(db, "IP B")
        c = _chart(db, "IP900")
        for e in ("E1", "E2", "E3"):
            _result(db, b, c, 92, emp=e)
        assert _label(client, "IP900") == "Too Easy"

    def test_a_mixed_view_does_not_leak_one_threshold_onto_the_other(self, client, db):
        """Both charts present, each keeping its own verdict."""
        ip_b, sds_b = _batch(db, "IP"), _batch(db, "SDS", sp=Specialty.SDS)
        ip_c, sds_c = _chart(db, "IP901"), _chart(db, "SDS901", Specialty.SDS)
        for e in ("E1", "E2", "E3"):
            _result(db, ip_b, ip_c, 92, emp=e)
            _result(db, sds_b, sds_c, 92, emp=e)
        assert _label(client, "IP901") == "Too Easy"
        assert _label(client, "SDS901") != "Too Easy"

    def test_the_bar_used_is_reported(self, client, db):
        b = _batch(db, "B", sp=Specialty.SDS)
        c = _chart(db, "SDS902", Specialty.SDS)
        for e in ("E1", "E2"):
            _result(db, b, c, 50, emp=e)
        row = next(r for r in client.get(URL).json() if r["chart_number"] == "SDS902")
        assert row["pass_threshold"] == 90
        assert row["too_easy_at"] == 95


class TestShareVersusScore:
    """
    "How many attempts passed" is a population share. The pass threshold is a
    per-chart score. The old rule compared them directly, so raising a
    specialty's score threshold moved the boundary between High Yield and
    Standard — two quantities that have nothing to do with each other.
    """

    def test_high_yield_boundaries_are_shares(self, client, db):
        from routers.practicelab_pkg.analytics import (
            TEACHING_FAIL_SHARE, TEACHING_STRONG_SHARE)
        assert (TEACHING_FAIL_SHARE, TEACHING_STRONG_SHARE) == (50, 80)

    def test_a_chart_most_people_fail_with_varied_errors_is_confusion(self, client, db):
        b = _batch(db, "B")
        c = _chart(db, "IP910")
        for e in ("E1", "E2", "E3", "E4"):
            _result(db, b, c, 30, emp=e, missed=("J18.9", "E11.9", "I10"))
        assert _label(client, "IP910") == "High Confusion"

    def test_the_same_failure_rate_with_one_repeated_miss_is_high_fail(self, client, db):
        """Confusion means variety; a shared blind spot is difficulty."""
        b = _batch(db, "B")
        c = _chart(db, "IP911")
        for e in ("E1", "E2", "E3", "E4"):
            _result(db, b, c, 30, emp=e, missed=("J18.9",))
        assert _label(client, "IP911") == "High Fail"


class TestUnderused:
    def test_one_attempt_is_not_enough_to_judge(self, client, db):
        b = _batch(db, "B")
        _result(db, b, _chart(db, "IP920"), 10)
        assert _label(client, "IP920") == "Underused"


class TestScope:
    def test_direct_assignments_are_excluded_by_default(self, client, db):
        d = _batch(db, "D", direct=True)
        c = _chart(db, "IP930")
        for e in ("E1", "E2"):
            _result(db, d, c, 40, emp=e)
        assert client.get(URL).json() == []

    def test_scope_all_includes_them(self, client, db):
        d = _batch(db, "D", direct=True)
        c = _chart(db, "IP931")
        for e in ("E1", "E2"):
            _result(db, d, c, 40, emp=e)
        rows = client.get(URL, params={"scope": "all"}).json()
        assert [r["chart_number"] for r in rows] == ["IP931"]

    def test_a_bad_scope_is_rejected(self, client):
        assert client.get(URL, params={"scope": "sideways"}).status_code == 400


class TestOrdering:
    def test_most_actionable_labels_come_first(self, client, db):
        """
        Alphabetical put High Confusion above High Yield for no reason beyond
        the letter C, and Too Easy above Underused for the same non-reason.
        """
        b = _batch(db, "B")
        easy = _chart(db, "IP940")
        conf = _chart(db, "IP941")
        for e in ("E1", "E2", "E3"):
            _result(db, b, easy, 95, emp=e)
            _result(db, b, conf, 20, emp=e, missed=("A", "B", "C"))
        labels = [r["teaching_label"] for r in client.get(URL).json()]
        assert labels.index("High Confusion") < labels.index("Too Easy")
