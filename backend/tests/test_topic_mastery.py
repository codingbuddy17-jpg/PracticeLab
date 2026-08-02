"""
Topic Mastery (/analytics/by-category).

Topics are free text typed at chart upload, and they repeat across specialties
that are graded against different pass marks. Both facts drive what this
endpoint has to do: fold spellings of one topic together, and refuse to claim a
single pass mark for a topic that spans specialties.
"""
import pytest

from models import Chart, Batch, Specialty, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/by-category"


def _chart(db, n, cat="Sepsis", sp=Specialty.IP_DRG):
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


def _result(db, b, c, score, coder="Asha R", emp="E1"):
    db.add(GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                         specialty=c.specialty, total_score=score,
                         pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL))
    db.commit()


class TestTopicGrouping:
    def test_spellings_of_one_topic_are_one_row(self, client, db):
        """
        "Sepsis", "sepsis" and "Sepsis " were three topics, each with a third of
        the attempts and its own average — so a topic could look both strong and
        weak on the same screen.
        """
        b = _batch(db, "B1")
        for n, cat in (("IP1", "Sepsis"), ("IP2", "sepsis"), ("IP3", "Sepsis ")):
            _result(db, b, _chart(db, n, cat), 60)
        team = client.get(URL).json()["team"]
        assert len(team) == 1
        assert team[0]["attempt_count"] == 3

    def test_the_displayed_label_stays_human(self, client, db):
        b = _batch(db, "B2")
        _result(db, b, _chart(db, "IP4", "Acute MI"), 90)
        assert client.get(URL).json()["team"][0]["category"] == "Acute MI"


class TestPassMark:
    def test_a_single_specialty_topic_carries_its_pass_mark(self, client, db):
        b = _batch(db, "B3", sp=Specialty.SDS)
        _result(db, b, _chart(db, "SDS1", "Endoscopy", Specialty.SDS), 85)
        assert client.get(URL).json()["team"][0]["pass_threshold"] == 90

    def test_a_topic_spanning_specialties_reports_no_single_mark(self, client, db):
        """
        "Sepsis" exists in IP-DRG (80) and SDS (90). Picking either would colour
        half the work against a bar that does not apply to it.
        """
        b1, b2 = _batch(db, "IP B"), _batch(db, "SDS B", sp=Specialty.SDS)
        _result(db, b1, _chart(db, "IP5", "Sepsis"), 85)
        _result(db, b2, _chart(db, "SDS2", "Sepsis", Specialty.SDS), 85, emp="E2")
        row = client.get(URL).json()["team"][0]
        assert row["pass_threshold"] is None
        assert set(row["specialties"]) == {"IP-DRG", "SDS"}


class TestCoderIdentity:
    def test_the_heatmap_does_not_split_a_coder_across_spellings(self, client, db):
        """Keyed on the typed name, one person entered two ways became two
        rows, each holding half their work."""
        b = _batch(db, "B4")
        _result(db, b, _chart(db, "IP6", "Sepsis"), 90, coder="Asha R", emp="E1")
        _result(db, b, _chart(db, "IP7", "Sepsis"), 50, coder="asha  r", emp="E1")
        rows = client.get(URL).json()["coder_category"]
        assert len(rows) == 1
        assert rows[0]["attempt_count"] == 2
        assert rows[0]["avg_score"] == 70.0
        assert rows[0]["emp_id"] == "E1"

    def test_team_coder_count_uses_the_same_identity(self, client, db):
        b = _batch(db, "B5")
        _result(db, b, _chart(db, "IP8", "Sepsis"), 90, coder="Asha R", emp="E1")
        _result(db, b, _chart(db, "IP9", "Sepsis"), 90, coder="asha  r", emp="E1")
        assert client.get(URL).json()["team"][0]["coder_count"] == 1


class TestScope:
    """The tab ignored the page scope switch, so it could show batch-and-direct
    figures while the three tabs before it showed batch-only."""

    @pytest.fixture()
    def mixed(self, db):
        formal, direct = _batch(db, "Formal"), _batch(db, "Direct", direct=True)
        _result(db, formal, _chart(db, "IPF", "Sepsis"), 100)
        _result(db, direct, _chart(db, "IPD", "Sepsis"), 0)
        return formal, direct

    def test_formal_keeps_the_documented_split(self, client, mixed):
        """Team is batch work; a coder's own row still covers everything."""
        body = client.get(URL).json()
        assert body["team"][0]["avg_score"] == 100.0
        assert body["coder_category"][0]["attempt_count"] == 2

    def test_direct_applies_to_both(self, client, mixed):
        body = client.get(URL, params={"scope": "direct"}).json()
        assert body["team"][0]["avg_score"] == 0.0
        assert body["coder_category"][0]["attempt_count"] == 1

    def test_all_applies_to_both(self, client, mixed):
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["team"][0]["avg_score"] == 50.0
        assert body["team"][0]["attempt_count"] == 2

    def test_the_note_describes_the_scope_in_force(self, client, mixed):
        assert "formal batches only" in client.get(URL).json()["coder_scope_note"]
        assert "direct assignments only" in client.get(URL, params={"scope": "direct"}).json()["coder_scope_note"]

    def test_a_bad_scope_is_rejected(self, client):
        assert client.get(URL, params={"scope": "sideways"}).status_code == 400


class TestPassRate:
    def test_pass_rate_is_reported_and_declared_chart_based(self, client, db):
        b = _batch(db, "B6")
        _result(db, b, _chart(db, "IPA", "Sepsis"), 90)
        _result(db, b, _chart(db, "IPB", "Sepsis"), 10)
        row = client.get(URL).json()["team"][0]
        assert row["pass_rate"] == 50.0
        assert row["pass_rate_basis"] == "chart"


class TestSpecialtyDeepDive:
    """
    A specialty picker on this tab is not a convenience. Topic names repeat
    across specialties graded to different pass marks, so comparing every topic
    at once compares figures measured on different scales.
    """

    @pytest.fixture()
    def two_specialties(self, db):
        ip = _batch(db, "IP B")
        sds = _batch(db, "SDS B", sp=Specialty.SDS)
        _result(db, ip, _chart(db, "IPX", "Sepsis"), 85)
        _result(db, sds, _chart(db, "SDSX", "Endoscopy", Specialty.SDS), 85, emp="E2")

    def test_narrowing_to_a_specialty_returns_only_its_topics(self, client, two_specialties):
        team = client.get(URL, params={"specialty": "SDS"}).json()["team"]
        assert [t["category"] for t in team] == ["Endoscopy"]

    def test_a_narrowed_topic_carries_a_definite_pass_mark(self, client, two_specialties):
        """Narrowed to one specialty, "mixed" should no longer appear."""
        team = client.get(URL, params={"specialty": "SDS"}).json()["team"]
        assert team[0]["pass_threshold"] == 90

    def test_coder_rows_narrow_with_the_team_rows(self, client, two_specialties):
        body = client.get(URL, params={"specialty": "IP-DRG"}).json()
        assert {r["category"] for r in body["coder_category"]} == {"Sepsis"}


class TestGrowth:
    def test_many_topics_all_come_back_for_the_client_to_page(self, client, db):
        """
        The endpoint returns everything; the tab searches and caps it. Worth
        pinning that the server is not silently truncating as well — two
        independent limits would hide rows nothing accounts for.
        """
        b = _batch(db, "Wide")
        for i in range(40):
            _result(db, b, _chart(db, f"IPW{i}", f"Topic {i:02d}"), 50 + i)
        team = client.get(URL).json()["team"]
        assert len(team) == 40
        assert team[0]["avg_score"] < team[-1]["avg_score"], "weakest first"
