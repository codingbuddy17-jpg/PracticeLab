"""
Coder-level error analysis: who to coach, who to learn from, and why.

The measure is errors per graded chart. Raw error counts rank people by how
much they practised — the "cleanest" coder would be whoever did least work.

The advice rests on one comparison: a coder failing at what everyone fails at
needs the session everyone is getting; a coder failing at something the team
handles fine needs a conversation. Same error count, different action.
"""
from datetime import datetime

import pytest

from models import Chart, Batch, Specialty, GradingResult, GradingFeedback, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/error-coders"


def _chart(db, n, sp=Specialty.IP_DRG):
    c = Chart(chart_number=n, specialty=sp, category="Sepsis", difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, direct=False):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _graded(db, b, chart, coder, emp, codes=(), sect="SDx", when=None):
    r = GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=chart.id,
                      specialty=chart.specialty, total_score=60, pass_fail=PassFail.FAIL)
    db.add(r); db.commit()
    if when:
        r.graded_at = when
        db.commit()
    for code in codes:
        db.add(GradingFeedback(result_id=r.id, section=sect, issue_type="Missed",
                               ak_code=code, coder_code=None, detail=""))
    db.commit()
    return r


def _by_name(rows):
    return {r["coder_name"]: r for r in rows}


class TestRanking:
    @pytest.fixture()
    def team(self, db):
        b = _batch(db, "B")
        # Clean: 6 charts, no errors. Messy: 6 charts, 2 errors each.
        for i in range(6):
            _graded(db, b, _chart(db, f"CL{i}"), "Clean", "E1")
            _graded(db, b, _chart(db, f"MS{i}"), "Messy", "E2", ["J18.9", "E11.9"])
        return b

    def test_top_is_fewest_errors_per_chart(self, client, team):
        body = client.get(URL).json()
        assert body["top"][0]["coder_name"] == "Clean"
        assert body["top"][0]["errors_per_chart"] == 0

    def test_bottom_is_the_densest(self, client, team):
        body = client.get(URL).json()
        assert body["bottom"][0]["coder_name"] == "Messy"
        assert body["bottom"][0]["errors_per_chart"] == 2.0

    def test_volume_does_not_decide_it(self, client, db):
        """
        Raw counts would rank the busiest coder worst. Twelve errors over
        twelve charts is a better record than four over two.
        """
        b = _batch(db, "B")
        for i in range(12):
            _graded(db, b, _chart(db, f"BUSY{i}"), "Busy", "E1", ["J18.9"])
        for i in range(6):
            _graded(db, b, _chart(db, f"OCC{i}"), "Occasional", "E2",
                    ["J18.9", "E11.9"] if i < 4 else [])
        body = client.get(URL).json()
        assert body["bottom"][0]["coder_name"] == "Occasional"
        assert _by_name(body["coders"])["Busy"]["errors"] == 12

    def test_a_thin_record_is_excluded_from_both_ends(self, client, team, db):
        """Two perfect charts is not evidence of a strong coder."""
        b = _batch(db, "B2")
        _graded(db, b, _chart(db, "TH1"), "Newcomer", "E9")
        _graded(db, b, _chart(db, "TH2"), "Newcomer", "E9")
        body = client.get(URL).json()
        names = {r["coder_name"] for r in body["top"] + body["bottom"]}
        assert "Newcomer" not in names
        assert body["excluded_thin"] == 1

    def test_identity_is_emp_id(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"SP{i}"), "Asha R" if i % 2 else "asha  r", "E1", ["J18.9"])
        body = client.get(URL).json()
        assert len(body["coders"]) == 1
        assert body["coders"][0]["charts"] == 6


class TestAdvice:
    def test_a_gap_the_team_does_not_share_is_coaching(self, client, db):
        """Their weakness, not the room's."""
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"SOLO{i}"), "Solo", "E1", ["J18.9"], sect="PCS")
        for i in range(6):
            _graded(db, b, _chart(db, f"REST{i}"), f"Other {i}", f"E{i+10}", ["A00.0"], sect="SDx")
        row = _by_name(client.get(URL).json()["coders"])["Solo"]
        kinds = [a["kind"] for a in row["advice"]]
        assert "coaching" in kinds
        assert any("their own gap" in a["text"] for a in row["advice"])

    def test_a_gap_the_team_shares_points_at_the_session(self, client, db):
        """Struggling with what everyone struggles with is not a 1:1."""
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"A{i}"), "Alpha", "E1", ["J18.9"], sect="SDx")
            _graded(db, b, _chart(db, f"B{i}"), "Beta", "E2", ["E11.9"], sect="SDx")
        row = _by_name(client.get(URL).json()["coders"])["Alpha"]
        assert any(a["kind"] == "curriculum" for a in row["advice"])

    def test_codes_only_they_miss_are_called_out(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"OWN{i}"), "Owner", "E1", ["Z99.9"], sect="SDx")
        for i in range(6):
            _graded(db, b, _chart(db, f"OTH{i}"), f"Other {i}", f"E{i+10}", ["A00.0"], sect="SDx")
        row = _by_name(client.get(URL).json()["coders"])["Owner"]
        assert any("missed by them alone" in a["text"] for a in row["advice"])

    def test_a_strong_coder_is_offered_as_a_teacher(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"GD{i}"), "Good", "E1")
            _graded(db, b, _chart(db, f"BD{i}"), "Weak", "E2", ["J18.9", "E11.9"])
        row = _by_name(client.get(URL).json()["coders"])["Good"]
        assert any(a["kind"] == "good" for a in row["advice"])

    def test_no_distinctive_pattern_says_track_not_intervene(self, client, db):
        """Advice that always prescribes something is advice nobody trusts."""
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"P{i}"), "Plain", "E1",
                    ["J18.9"] if i < 2 else [], sect="SDx" if i % 2 else "PDx")
            _graded(db, b, _chart(db, f"Q{i}"), "Peer", "E2",
                    ["E11.9"] if i < 2 else [], sect="PDx" if i % 2 else "SDx")
        row = _by_name(client.get(URL).json()["coders"])["Plain"]
        assert row["advice"]


class TestTrend:
    def test_each_coder_carries_their_own_rate_over_time(self, client, db):
        b = _batch(db, "B")
        for i in range(3):
            _graded(db, b, _chart(db, f"T1{i}"), "Learner", "E1",
                    ["A", "B"], when=datetime(2026, 1, 5))
        for i in range(3):
            _graded(db, b, _chart(db, f"T3{i}"), "Learner", "E1",
                    ["A"], when=datetime(2026, 3, 5))
        row = client.get(URL).json()["coders"][0]
        assert [t["errors_per_chart"] for t in row["trend"]] == [2.0, 1.0]
        assert row["direction"] == "improving"

    def test_direction_is_measured_against_their_own_history(self, client, db):
        """Improving means improving for them, not relative to anyone else."""
        b = _batch(db, "B")
        for i in range(3):
            _graded(db, b, _chart(db, f"W1{i}"), "Slipping", "E1", ["A"], when=datetime(2026, 1, 5))
        for i in range(3):
            _graded(db, b, _chart(db, f"W3{i}"), "Slipping", "E1",
                    ["A", "B", "C"], when=datetime(2026, 3, 5))
        assert client.get(URL).json()["coders"][0]["direction"] == "worsening"


class TestScope:
    def test_direct_work_is_excluded_by_default(self, client, db):
        d = _batch(db, "D", direct=True)
        for i in range(6):
            _graded(db, d, _chart(db, f"DR{i}"), "Direct Only", "E1", ["J18.9"])
        assert client.get(URL).json()["coders"] == []
        assert len(client.get(URL, params={"scope": "all"}).json()["coders"]) == 1

    def test_a_bad_scope_is_rejected(self, client):
        assert client.get(URL, params={"scope": "sideways"}).status_code == 400


class TestListShape:
    def test_the_two_ends_never_overlap(self, client, db):
        """A coder shown as both best and worst is worse than a short list."""
        b = _batch(db, "B")
        for c in range(4):
            for i in range(6):
                _graded(db, b, _chart(db, f"OV{c}_{i}"), f"Coder {c}", f"E{c}",
                        ["J18.9"] * c)
        body = client.get(URL).json()
        assert not ({r["coder_id"] for r in body["top"]} &
                    {r["coder_id"] for r in body["bottom"]})

    def test_a_single_ranked_coder_gets_no_bottom_list(self, client, db):
        """One coder is a record, not a ranking."""
        b = _batch(db, "B")
        for i in range(6):
            _graded(db, b, _chart(db, f"SOLO{i}"), "Only", "E1", ["J18.9"])
        body = client.get(URL).json()
        assert len(body["coders"]) == 1
        assert body["bottom"] == []

    def test_the_payload_keeps_its_shape_when_empty(self, client):
        """A caller should not have to check which keys exist."""
        body = client.get(URL).json()
        for k in ("top", "bottom", "coders", "team", "min_charts", "scope"):
            assert k in body

    def test_top_n_is_capped(self, client, db):
        b = _batch(db, "B")
        for c in range(30):
            for i in range(6):
                _graded(db, b, _chart(db, f"CAP{c}_{i}"), f"Coder {c}", f"E{c}", ["J18.9"])
        assert len(client.get(URL, params={"top_n": 9999}).json()["top"]) <= 20
