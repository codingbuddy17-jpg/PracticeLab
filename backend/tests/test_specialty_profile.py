"""
The single-specialty deep dive behind Tab 2.

It is the only place that puts library capacity, participation and outcome in
one payload, so the things worth pinning are the ones that come from combining
them: readiness counts charts with a key (and knows which table the key lives
in), a coder "clears" by a majority rule rather than an average, and a chart is
only called easy or hard once enough people have attempted it.
"""
from datetime import datetime

import pytest

from models import Chart, Batch, Specialty, AnswerKey, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/specialty-profile"


def _chart(db, number, specialty=Specialty.IP_DRG, key=False):
    c = Chart(chart_number=number, specialty=specialty, category="Sepsis",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    if key:
        db.add(AnswerKey(chart_id=c.id, specialty=specialty, pdx_code="J18.9",
                         sdx=[], pcs=[], cpt=[], entered_by="t"))
        db.commit()
    return c


def _batch(db, name, direct=False):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
              created_by="t", charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, batch, chart, coder, emp, score):
    db.add(GradingResult(batch_id=batch.id, coder_name=coder, emp_id=emp,
                         chart_id=chart.id, specialty=chart.specialty,
                         total_score=score,
                         pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL))
    db.commit()


def test_unknown_specialty_404s(client):
    assert client.get(URL, params={"specialty": "Cardiology"}).status_code == 404


def test_bad_scope_400s(client):
    assert client.get(URL, params={"specialty": "IP-DRG", "scope": "sideways"}).status_code == 400


class TestLibrary:
    def test_ready_counts_only_charts_with_a_key(self, client, db):
        _chart(db, "IP700", key=True)
        _chart(db, "IP701", key=True)
        _chart(db, "IP702", key=False)
        lib = client.get(URL, params={"specialty": "IP-DRG"}).json()["library"]
        assert lib == {"total_charts": 3, "practice_ready": 2,
                       "awaiting_key": 1, "uses_answer_keys": True}

    def test_em_keys_live_in_their_own_table(self, client, db):
        """Counting answer_keys for E/M reported 0 ready however many existed."""
        _chart(db, "EM700", Specialty.EM)
        lib = client.get(URL, params={"specialty": "E/M"}).json()["library"]
        assert lib["total_charts"] == 1
        assert lib["practice_ready"] == 0, "no em_answer_key was created"

    def test_rubric_specialty_needs_no_key(self, client, db):
        """Edits/Denials are rubric-graded, so every chart is ready as it stands.
        (_is_ed is Edits/Denials, NOT Emergency Department — ED Facility does
        use answer keys.)"""
        _chart(db, "EDT700", Specialty.EDITS)
        lib = client.get(URL, params={"specialty": "Edits"}).json()["library"]
        assert lib["uses_answer_keys"] is False
        assert lib["awaiting_key"] == 0
        assert lib["practice_ready"] == 1

    def test_a_specialty_nobody_has_practised_still_reports(self, client, db):
        """
        The selector offers every specialty, not just graded ones — "12 charts
        ready and nobody has touched them" is exactly what a trainer opens this
        for. It must not divide by zero on the way to saying so.
        """
        _chart(db, "SDS770", Specialty.SDS, key=True)
        body = client.get(URL, params={"specialty": "SDS"}).json()
        assert body["library"]["practice_ready"] == 1
        assert body["activity"] == {"attempts": 0, "coders": 0, "charts_attempted": 0}
        assert body["performance"]["avg_score"] == 0.0
        assert body["performance"]["coder_clear_rate"] == 0.0
        assert body["charts"]["struggling_list"] == []
        assert body["standing"]["rank_by_avg_score"] is None, "unranked, not ranked last"

    def test_retired_charts_are_not_capacity(self, client, db):
        c = _chart(db, "IP703", key=True)
        c.status = ChartStatus.RETIRED
        db.commit()
        assert client.get(URL, params={"specialty": "IP-DRG"}).json()["library"]["total_charts"] == 0


class TestOutcome:
    def test_coder_clear_rate_is_a_majority_rule_not_an_average(self, client, db):
        """
        One coder, three charts, two passed. Their AVERAGE (60) is well under
        the 80 pass mark, yet they cleared — because clearing means passing
        more charts than not. The two figures disagree by design, so the
        payload names the rule it used.
        """
        b = _batch(db, "B1")
        for n, score in (("IP710", 90), ("IP711", 90), ("IP712", 0)):
            _result(db, b, _chart(db, n, key=True), "Asha R", "E1", score)
        body = client.get(URL, params={"specialty": "IP-DRG"}).json()
        perf = body["performance"]
        assert perf["coder_clear_rate"] == 100.0
        assert perf["chart_pass_rate"] == pytest.approx(66.7, abs=0.1)
        assert perf["avg_score"] == 60.0
        assert perf["coder_clear_rule"] == "majority of charts passed"

    def test_emp_id_is_the_coder_identity(self, client, db):
        """Two spellings of one person must not become two coders."""
        b = _batch(db, "B2")
        _result(db, b, _chart(db, "IP720", key=True), "Asha R", "E1", 90)
        _result(db, b, _chart(db, "IP721", key=True), "asha  r", "E1", 90)
        assert client.get(URL, params={"specialty": "IP-DRG"}).json()["activity"]["coders"] == 1


class TestChartDifficulty:
    def test_thinly_attempted_charts_are_not_rated(self, client, db):
        """A chart failed once is 0% passed — that is noise, not a hard chart."""
        b = _batch(db, "B3")
        _result(db, b, _chart(db, "IP730", key=True), "A", "E1", 0)
        charts = client.get(URL, params={"specialty": "IP-DRG"}).json()["charts"]
        assert charts["low_sample"] == 1
        assert charts["struggling"] == 0
        assert charts["struggling_list"] == []

    def test_a_genuinely_hard_chart_is_listed(self, client, db):
        b = _batch(db, "B4")
        hard = _chart(db, "IP731", key=True)
        for i, emp in enumerate(("E1", "E2", "E3")):
            _result(db, b, hard, f"C{i}", emp, 20)
        charts = client.get(URL, params={"specialty": "IP-DRG"}).json()["charts"]
        assert charts["struggling"] == 1
        assert charts["struggling_list"][0]["chart_number"] == "IP731"
        assert charts["struggling_list"][0]["attempts"] == 3


class TestScope:
    def test_formal_excludes_direct_and_all_includes_it(self, client, db):
        formal, direct = _batch(db, "F"), _batch(db, "D", direct=True)
        _result(db, formal, _chart(db, "IP740", key=True), "A", "E1", 100)
        _result(db, direct, _chart(db, "IP741", key=True), "A", "E1", 0)

        base = {"specialty": "IP-DRG"}
        assert client.get(URL, params=base).json()["activity"]["attempts"] == 1
        assert client.get(URL, params={**base, "scope": "direct"}).json()["activity"]["attempts"] == 1
        both = client.get(URL, params={**base, "scope": "all"}).json()
        assert both["activity"]["attempts"] == 2
        assert both["performance"]["avg_score"] == 50.0

    def test_library_is_the_same_whatever_the_scope(self, client, db):
        """Inventory is not scoped work — charts exist regardless of how they were assigned."""
        _chart(db, "IP750", key=True)
        counts = {s: client.get(URL, params={"specialty": "IP-DRG", "scope": s}).json()["library"]
                  for s in ("formal", "direct", "all")}
        assert len({c["total_charts"] for c in counts.values()}) == 1


class TestDateFilter:
    """
    The date range at the top of Analytics is a real filter here, not decoration
    — it narrows on graded_at. Worth pinning because it reaches the outcome
    figures and deliberately does NOT reach the library counts.
    """

    @pytest.fixture()
    def spread(self, db):
        b = _batch(db, "Spread")
        old = _chart(db, "IP780", key=True)
        new = _chart(db, "IP781", key=True)
        _result(db, b, old, "A", "E1", 100)
        _result(db, b, new, "B", "E2", 0)
        rows = db.query(GradingResult).order_by(GradingResult.id).all()
        rows[0].graded_at = datetime(2026, 1, 15, 10, 0)
        rows[1].graded_at = datetime(2026, 6, 15, 10, 0)
        db.commit()
        return b

    def test_range_narrows_the_specialty_table(self, client, spread):
        rows = client.get("/practicelab/analytics/by-specialty",
                          params={"from_date": "2026-01-01", "to_date": "2026-03-01"}).json()
        ip = next(r for r in rows if r["specialty"] == "IP-DRG")
        assert ip["total"] == 1
        assert ip["avg_score"] == 100.0, "the June result must be outside the range"

    def test_range_narrows_the_profile(self, client, spread):
        body = client.get(URL, params={"specialty": "IP-DRG",
                                       "from_date": "2026-05-01", "to_date": "2026-07-01"}).json()
        assert body["activity"]["attempts"] == 1
        assert body["activity"]["coders"] == 1
        assert body["performance"]["avg_score"] == 0.0

    def test_to_date_includes_the_whole_day(self, client, spread):
        """A result graded at 10:00 must not fall outside a range ending that day."""
        body = client.get(URL, params={"specialty": "IP-DRG",
                                       "from_date": "2026-06-15", "to_date": "2026-06-15"}).json()
        assert body["activity"]["attempts"] == 1

    def test_library_ignores_the_date_range(self, client, spread):
        """Inventory is not dated work — a chart does not stop existing because
        the range excludes the day someone was graded on it."""
        body = client.get(URL, params={"specialty": "IP-DRG",
                                       "from_date": "2026-01-01", "to_date": "2026-01-02"}).json()
        assert body["library"]["total_charts"] == 2
        assert body["activity"]["attempts"] == 0


class TestStanding:
    def test_rank_is_against_the_other_specialties(self, client, db):
        b = _batch(db, "B5")
        _result(db, b, _chart(db, "IP760", key=True), "A", "E1", 40)
        sds = _chart(db, "SDS760", Specialty.SDS, key=True)
        _result(db, b, sds, "A", "E1", 95)
        body = client.get(URL, params={"specialty": "IP-DRG"}).json()
        assert body["standing"]["peers"] == 2
        assert body["standing"]["rank_by_avg_score"] == 2, "40 is behind 95"
        assert body["standing"]["peer_avg_score"] == 67.5
