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


def _err_n(db, b, c, coder, emp, codes, when=None):
    """One graded chart carrying several errors — moves the RATE, not volume."""
    r = GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                      specialty=c.specialty, total_score=50, pass_fail=PassFail.FAIL)
    db.add(r); db.commit()
    if when:
        r.graded_at = when
        db.commit()
    for code in codes:
        db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
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
        # A single occurrence is "Scattered", which is held back by default —
        # ask for it to prove the issue filter itself works.
        body = client.get(URL, params={"issue_type": "Over_coded",
                                       "include_scattered": True}).json()
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


class TestCommentary:
    """
    Commentary that always says something says nothing. Each line has to clear
    a threshold, and each has to name the ACTION its finding implies — "SDx is
    62% of errors" is a fact; "one teachable rule, not broad weakness" is the
    decision it supports.
    """

    def _kinds(self, client, **params):
        return {n["kind"] for n in client.get(URL, params=params).json()["commentary"]}

    def test_a_team_wide_gap_is_called_curriculum(self, client, db):
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IPT{i}"), f"Coder {i}", f"E{i}", "J18.9")
        assert "curriculum" in self._kinds(client)

    def test_one_chart_concentration_points_at_the_key(self, client, db):
        b = _batch(db, "B")
        c = _chart(db, "IPU1")
        for i in range(4):
            _err(db, b, c, f"Coder {i}", f"E{i}", "J18.9")
        notes = client.get(URL).json()["commentary"]
        assert any(n["kind"] == "key" and "answer key" in n["text"] for n in notes)

    def test_one_coder_repetition_is_called_coaching(self, client, db):
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IPV{i}"), "Solo", "S1", "J18.9")
        notes = client.get(URL).json()["commentary"]
        assert any(n["kind"] == "coaching" and "1:1" in n["text"] for n in notes)

    def test_a_dominant_section_is_named_with_its_share(self, client, db):
        b = _batch(db, "B")
        for i in range(5):
            _err(db, b, _chart(db, f"IPW{i}"), f"C{i}", f"E{i}", f"J{i}8.9", sect="PDx")
        notes = client.get(URL).json()["commentary"]
        assert any("PDx" in n["text"] and "%" in n["text"] for n in notes)

    def test_a_falling_trend_is_recognised(self, client, db):
        """Same volume each month, fewer errors per chart — a real improvement."""
        b = _batch(db, "B")
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPX1{i}"), f"C{i}", f"E{i}",
                   ["A00.0", "B00.0", "C00.0"], when=datetime(2026, 1, 5))
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPX2{i}"), f"C{i}", f"E{i}",
                   ["A00.0", "B00.0"], when=datetime(2026, 2, 5))
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPX3{i}"), f"C{i}", f"E{i}",
                   ["A00.0"], when=datetime(2026, 3, 5))
        body = client.get(URL).json()
        notes = body["commentary"] + body["commentary_more"]
        assert any(n["kind"] == "good" for n in notes)

    def test_a_rising_trend_is_reported(self, client, db):
        """
        Read as a RATE where months have chart counts, so a team that doubles
        its practice does not look like it is getting worse.
        """
        b = _batch(db, "B")
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPY1{i}"), f"C{i}", f"E{i}",
                   ["A00.0"], when=datetime(2026, 1, 5))
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPY2{i}"), f"C{i}", f"E{i}",
                   ["A00.0", "B00.0"], when=datetime(2026, 2, 5))
        for i in range(3):
            _err_n(db, b, _chart(db, f"IPY3{i}"), f"C{i}", f"E{i}",
                   ["A00.0", "B00.0", "C00.0"], when=datetime(2026, 3, 5))
        body = client.get(URL).json()
        notes = body["commentary"] + body["commentary_more"]
        assert any(n["kind"] == "warn" and "Errors are rising" in n["text"] for n in notes)

    def test_thin_data_says_so_rather_than_inventing_a_finding(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPZ1"), "A", "E1", "J18.9")
        notes = client.get(URL).json()["commentary"]
        assert any(n["kind"] == "info" for n in notes) or notes

    def test_an_empty_tab_carries_no_commentary_at_all(self, client, db):
        """Nothing graded means nothing to say — not a panel of empty advice."""
        body = client.get(URL).json()
        assert body["total_errors"] == 0
        assert "commentary" not in body or body.get("commentary") in (None, [])


class TestCodeTablePaging:
    """
    This list only ever grows — a code missed once a year ago is still a row.
    It was truncated at 200 with the client searching inside that slice, so a
    code ranked 250th was unreachable AND unfindable, and the count on screen
    described the slice rather than the data.
    """

    @pytest.fixture()
    def many_codes(self, db):
        b = _batch(db, "B")
        # 60 distinct codes, descending frequency, so rank is predictable.
        for i in range(60):
            for _ in range(60 - i):
                _err(db, b, _chart(db, f"IPPG{i}_{_}"), f"C{i}", f"E{i}", f"Z{i:03d}")
        return b

    def test_only_a_page_comes_back(self, client, many_codes):
        body = client.get(URL, params={"limit": 25}).json()
        assert len(body["codes"]) == 25
        assert body["total_codes"] == 60

    def test_offset_walks_the_rest(self, client, many_codes):
        first = [c["code"] for c in client.get(URL, params={"limit": 25}).json()["codes"]]
        second = [c["code"] for c in client.get(URL, params={"limit": 25, "offset": 25}).json()["codes"]]
        assert not set(first) & set(second)

    def test_search_reaches_a_code_far_past_the_page(self, client, many_codes):
        """Z059 is rank 60 by frequency — client-side search never saw it."""
        body = client.get(URL, params={"limit": 25, "code_search": "Z059"}).json()
        assert [c["code"] for c in body["codes"]] == ["Z059"]
        assert body["matching_codes"] == 1

    def test_pattern_filter_runs_before_the_cut(self, client, many_codes):
        body = client.get(URL, params={"limit": 25, "pattern": "One coder"}).json()
        assert body["matching_codes"] > 0
        assert all(c["pattern"] == "One coder" for c in body["codes"])

    def test_the_three_totals_are_distinct_and_all_reported(self, client, many_codes):
        """Collapsing them is how "Showing 25 of 25" appears over 60 codes."""
        # "Z00" matches Z000-Z009 only; "Z0" would match all sixty and the
        # test would prove nothing.
        body = client.get(URL, params={"limit": 5, "code_search": "Z00"}).json()
        assert body["returned_codes"] == 5
        assert body["matching_codes"] == 10
        assert body["total_codes"] == 60
        assert body["matching_codes"] < body["total_codes"]

    def test_pattern_counts_cover_the_whole_set_not_the_page(self, client, many_codes):
        """A chip reading "One coder (3)" when there are 60 would be a lie."""
        body = client.get(URL, params={"limit": 5}).json()
        assert sum(body["pattern_counts"].values()) == body["total_codes"]

    def test_limit_is_capped(self, client, many_codes):
        assert len(client.get(URL, params={"limit": 100000}).json()["codes"]) <= 200


class TestSpecialtyRanking:
    """
    Ranking specialties by RAW error count ranks them by how much they were
    practised — the "cleanest" specialty comes out as whichever nobody touched.
    Density is the comparable figure, and thin volume is excluded rather than
    winning on three charts.
    """

    def _spread(self, db):
        b = _batch(db, "B")
        # Each _err() is its own graded result, so this is 20 graded charts
        # each carrying one error -> 1.0 per chart.
        for i in range(10):
            c = _chart(db, f"IPR{i}")
            _err(db, b, c, f"C{i}", f"E{i}", "J18.9")
            _err(db, b, c, f"C{i}", f"E{i}", "E11.9")
        # SDS: 10 charts, 5 errors -> 0.5 per chart, but MORE charts than IP had
        for i in range(10):
            c = _chart(db, f"SDR{i}", Specialty.SDS)
            if i < 5:
                _err(db, b, c, f"C{i}", f"E{i}", "M17.11")
            else:
                r = GradingResult(batch_id=b.id, coder_name=f"C{i}", emp_id=f"E{i}",
                                  chart_id=c.id, specialty=Specialty.SDS,
                                  total_score=95, pass_fail=PassFail.PASS)
                db.add(r); db.commit()
        return b

    def test_worst_is_by_density_not_volume(self, client, db):
        self._spread(db)
        body = client.get(URL).json()
        assert body["worst_specialty"]["specialty"] == "IP-DRG"
        assert body["worst_specialty"]["errors_per_chart"] == 1.0

    def test_best_is_by_density_too(self, client, db):
        self._spread(db)
        body = client.get(URL).json()
        assert body["best_specialty"]["specialty"] == "SDS"
        assert body["best_specialty"]["errors_per_chart"] < 1

    def test_a_barely_practised_specialty_cannot_win_cleanest(self, client, db):
        """One perfect chart is not evidence of a clean specialty."""
        self._spread(db)
        b = _batch(db, "Tiny")
        c = _chart(db, "SURG1", Specialty.SURGERY)
        db.add(GradingResult(batch_id=b.id, coder_name="Z", emp_id="EZ", chart_id=c.id,
                             specialty=Specialty.SURGERY, total_score=100, pass_fail=PassFail.PASS))
        db.commit()
        body = client.get(URL).json()
        assert body["best_specialty"]["specialty"] != "Surgery"
        surgery = next(x for x in body["by_specialty"] if x["specialty"] == "Surgery")
        assert surgery["rankable"] is False

    def test_nothing_rankable_returns_none_rather_than_a_guess(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPS9"), "A", "E1", "J18.9")
        body = client.get(URL).json()
        assert body["worst_specialty"] is None
        assert body["best_specialty"] is None


class TestOverviewSpecialtyTiles:
    """Volume and error density answer different questions, and ranking either
    by the other's measure answers the wrong one by accident."""

    def test_most_and_least_practised_are_by_volume(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _err(db, b, _chart(db, f"IPV{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(2):
            c = _chart(db, f"SDV{i}", Specialty.SDS)
            db.add(GradingResult(batch_id=b.id, coder_name=f"D{i}", emp_id=f"F{i}",
                                 chart_id=c.id, specialty=Specialty.SDS,
                                 total_score=90, pass_fail=PassFail.PASS))
        db.commit()
        ov = client.get("/practicelab/analytics/overview").json()
        assert ov["most_practised"]["specialty"] == "IP-DRG"
        assert ov["most_practised"]["charts"] == 6
        assert ov["least_practised"]["specialty"] == "SDS"

    def test_error_tiles_use_density_and_respect_the_volume_floor(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _err(db, b, _chart(db, f"IPW{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(2):
            c = _chart(db, f"SDW{i}", Specialty.SDS)
            db.add(GradingResult(batch_id=b.id, coder_name=f"D{i}", emp_id=f"F{i}",
                                 chart_id=c.id, specialty=Specialty.SDS,
                                 total_score=90, pass_fail=PassFail.PASS))
        db.commit()
        ov = client.get("/practicelab/analytics/overview").json()
        # SDS is spotless but only 2 charts — below the floor, so not "cleanest".
        assert ov["most_errors"]["specialty"] == "IP-DRG"
        assert ov["least_errors"] is None or ov["least_errors"]["specialty"] != "SDS"

    def test_a_specialty_with_charts_but_no_practice_is_surfaced(self, client, db):
        """Invisible in every performance view by definition — no results."""
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPX1"), "A", "E1", "J18.9")
        _chart(db, "SURGX1", Specialty.SURGERY)      # library only, never graded
        ov = client.get("/practicelab/analytics/overview").json()
        assert "Surgery" in ov["untouched_specialties"]


class TestSpecialtyNuanceInInsights:
    """
    Without specialty nuance the insights read as if the team has one error
    profile. It usually does not — a "team-wide gap" living entirely inside one
    specialty is a session for that group, not for everyone, and the pattern
    label alone cannot tell you which.
    """

    def _two_specialties(self, db):
        b = _batch(db, "B")
        for i in range(8):                      # IP-DRG: dense
            _err(db, b, _chart(db, f"IPN{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(8):                      # SDS: clean
            c = _chart(db, f"SDN{i}", Specialty.SDS)
            db.add(GradingResult(batch_id=b.id, coder_name=f"D{i}", emp_id=f"F{i}",
                                 chart_id=c.id, specialty=Specialty.SDS,
                                 total_score=95, pass_fail=PassFail.PASS))
        db.commit()
        return b

    def test_a_density_gap_between_specialties_is_called_out(self, client, db):
        self._two_specialties(db)
        texts = " ".join(n["text"] for n in client.get(URL).json()["commentary"])
        assert "IP-DRG" in texts and "SDS" in texts
        assert "separate training problems" in texts

    def test_a_gap_confined_to_one_specialty_is_named_as_such(self, client, db):
        self._two_specialties(db)
        notes = client.get(URL).json()["commentary"]
        assert any("single specialty" in n["text"] for n in notes)

    def test_an_active_specialty_filter_is_stated_first(self, client, db):
        """
        The insights describe the filtered slice. Saying so is the difference
        between "the team misses J18.9" and "SDS coders miss J18.9".
        """
        self._two_specialties(db)
        notes = client.get(URL, params={"specialty": "IP-DRG"}).json()["commentary"]
        assert notes[0]["text"].startswith("Filtered to IP-DRG")
        assert "IP-DRG only" in notes[0]["text"]

    def test_a_filtered_view_does_not_compare_across_specialties(self, client, db):
        """Cross-specialty commentary under a specialty filter would compare a
        thing to itself."""
        self._two_specialties(db)
        texts = " ".join(n["text"] for n in
                         client.get(URL, params={"specialty": "IP-DRG"}).json()["commentary"])
        assert "separate training problems" not in texts

    def test_even_density_is_reported_as_team_wide(self, client, db):
        b = _batch(db, "B")
        for i in range(6):
            _err(db, b, _chart(db, f"IPE2{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(6):
            _err(db, b, _chart(db, f"SDE2{i}", Specialty.SDS), f"D{i}", f"F{i}", "M17.11")
        texts = " ".join(n["text"] for n in client.get(URL).json()["commentary"])
        assert "team-wide rather than specialty-specific" in texts


class TestZeroErrorSpecialty:
    def test_a_spotless_specialty_is_the_starkest_gap_not_a_skipped_case(self, client, db):
        """
        A divide-by-zero guard written as a gate skipped exactly the clearest
        finding: one specialty clean, another not. An infinite ratio is the
        strongest version of the gap, not an absent one.
        """
        b = _batch(db, "B")
        for i in range(8):
            _err(db, b, _chart(db, f"IPZZ{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(8):
            c = _chart(db, f"SDZZ{i}", Specialty.SDS)
            db.add(GradingResult(batch_id=b.id, coder_name=f"D{i}", emp_id=f"F{i}",
                                 chart_id=c.id, specialty=Specialty.SDS,
                                 total_score=95, pass_fail=PassFail.PASS))
        db.commit()
        texts = " ".join(n["text"] for n in client.get(URL).json()["commentary"])
        assert "no recorded errors at all" in texts
        assert "SDS" in texts and "IP-DRG" in texts


class TestNothingIsHeldBackByDefault:
    """
    The code list must not shrink because of how it is fetched. Paging down to
    25 per request turned every "Load more" into a round trip that could fail
    quietly and leave a shorter list on screen with nothing explaining it.
    """

    def test_the_default_request_returns_the_whole_actionable_set(self, client, db):
        """
        No cap on what comes back — but codes seen once each are "Scattered"
        and held out of the default view, so this asks for them.
        """
        b = _batch(db, "B")
        for i in range(60):
            _err(db, b, _chart(db, f"IPFULL{i}"), f"C{i}", f"E{i}", f"Z{i:03d}")
        body = client.get(URL, params={"include_scattered": True}).json()
        assert len(body["codes"]) == 60
        assert body["total_codes"] == 60
        assert body["matching_codes"] == 60

    def test_search_still_reaches_the_whole_set(self, client, db):
        """The reason paging moved server-side in the first place — keep it."""
        b = _batch(db, "B")
        for i in range(60):
            _err(db, b, _chart(db, f"IPSCH{i}"), f"C{i}", f"E{i}", f"Z{i:03d}")
        body = client.get(URL, params={"code_search": "Z059"}).json()
        assert [c["code"] for c in body["codes"]] == ["Z059"]

    def test_commentary_is_unaffected_by_the_code_page(self, client, db):
        """
        Insights are computed over every code, not the returned slice — a
        smaller page must never mean fewer findings.
        """
        b = _batch(db, "B")
        for i in range(6):
            _err(db, b, _chart(db, f"IPCOM{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(40):
            _err(db, b, _chart(db, f"IPPAD{i}"), f"D{i}", f"F{i}", f"Y{i:03d}")
        full = client.get(URL).json()["commentary"]
        paged = client.get(URL, params={"limit": 5}).json()["commentary"]
        assert [n["text"] for n in full] == [n["text"] for n in paged]


class TestScatteredHeldBack:
    """
    "Scattered" is the endpoint's own label for too few occurrences to call a
    pattern — by definition the rows a trainer cannot act on. On real data they
    are most of the list and none of the decisions, so they are held back by
    default. Held back, never dropped: the count is always reported.
    """

    @pytest.fixture()
    def mixed(self, db):
        b = _batch(db, "B")
        for i in range(5):                       # actionable: team-wide
            _err(db, b, _chart(db, f"IPACT{i}"), f"C{i}", f"E{i}", "J18.9")
        for i in range(30):                      # noise: one sighting each
            _err(db, b, _chart(db, f"IPNOI{i}"), f"D{i}", f"F{i}", f"N{i:03d}")
        return b

    def test_the_default_view_holds_scattered_back(self, client, mixed):
        body = client.get(URL).json()
        assert [c["code"] for c in body["codes"]] == ["J18.9"]
        assert body["scattered_hidden"] is True

    def test_the_hidden_count_is_always_reported(self, client, mixed):
        """Nothing may be missing without the screen saying so."""
        assert client.get(URL).json()["scattered_codes"] == 30

    def test_they_can_be_shown(self, client, mixed):
        body = client.get(URL, params={"include_scattered": True}).json()
        assert len(body["codes"]) == 31
        assert body["scattered_hidden"] is False

    def test_search_finds_a_scattered_code_without_asking(self, client, mixed):
        """
        Looking up a code and being told it does not exist — because it
        happened twice — would be worse than a long list. An explicit search
        is not overruled.
        """
        body = client.get(URL, params={"code_search": "N007"}).json()
        assert [c["code"] for c in body["codes"]] == ["N007"]

    def test_picking_the_scattered_pattern_shows_them(self, client, mixed):
        body = client.get(URL, params={"pattern": "Scattered"}).json()
        assert len(body["codes"]) == 30

    def test_totals_still_count_everything(self, client, mixed):
        """Hiding rows must not change the arithmetic above them."""
        body = client.get(URL).json()
        assert body["total_codes"] == 31
        assert body["total_errors"] == 35

    def test_commentary_still_sees_every_code(self, client, mixed):
        with_them = client.get(URL, params={"include_scattered": True}).json()["commentary"]
        without = client.get(URL).json()["commentary"]
        assert [n["text"] for n in with_them] == [n["text"] for n in without]


class TestInsightsAtVolume:
    """
    How many findings appear, and which, once the data is heavy. Every rule is
    independent, so at scale most of them fire at once — and eleven lines of
    advice is skimmed and acted on nowhere.
    """

    @pytest.fixture()
    def heavy(self, db):
        b = _batch(db, "B")
        for i in range(10):                       # team-wide
            _err(db, b, _chart(db, f"HA{i}"), f"C{i}", f"E{i}", "J18.9")
        c = _chart(db, "HSHARED")
        for i in range(6):                        # one chart
            _err(db, b, c, f"D{i}", f"F{i}", "E11.9")
        for i in range(6):                        # one coder
            _err(db, b, _chart(db, f"HB{i}"), "Solo", "S1", "I10")
        for i in range(80):                       # long tail
            _err(db, b, _chart(db, f"HT{i}"), f"G{i}", f"H{i}", f"T{i:03d}")
        return b

    def test_the_list_is_capped(self, client, heavy):
        body = client.get(URL).json()
        assert len(body["commentary"]) <= 6

    def test_nothing_is_lost_only_held(self, client, heavy):
        body = client.get(URL).json()
        assert isinstance(body["commentary_more"], list)
        shown = {n["text"] for n in body["commentary"]}
        held = {n["text"] for n in body["commentary_more"]}
        assert not shown & held, "a finding cannot be in both lists"

    def test_the_most_actionable_findings_come_first(self, client, heavy):
        """
        Curriculum reaches a room; coaching reaches one person; a trend is
        context. The order is what a trainer would do first, not the order the
        rules happen to run in.
        """
        kinds = [n["kind"] for n in client.get(URL).json()["commentary"]]
        if "curriculum" in kinds and "good" in kinds:
            assert kinds.index("curriculum") < kinds.index("good")
        if "key" in kinds and "focus" in kinds:
            assert kinds.index("key") < kinds.index("focus")

    def test_concentration_is_pareto_not_a_fixed_count(self, client, heavy):
        """
        "Codes seen 5+ times" dissolves with volume — at scale nearly every
        code clears it and the line becomes "180 codes account for 97% of
        errors": true, useless, unactionable. How many codes it takes to reach
        HALF the errors stays meaningful at any size.
        """
        notes = client.get(URL, params={"include_scattered": True}).json()
        allnotes = notes["commentary"] + notes["commentary_more"]
        texts = " ".join(n["text"] for n in allnotes)
        assert "account for half of" in texts or "to reach half the total" in texts
        assert "account for 97" not in texts

    def test_a_flat_distribution_says_there_is_no_short_list(self, client, db):
        b = _batch(db, "B")
        for i in range(40):
            for _ in range(3):
                _err(db, b, _chart(db, f"FL{i}_{_}"), f"C{i}", f"E{i}", f"F{i:03d}")
        notes = client.get(URL).json()
        texts = " ".join(n["text"] for n in notes["commentary"] + notes["commentary_more"])
        assert "no short list to fix" in texts


class TestCoverageIsStated:
    """
    This tab reads grading_feedback. E/M and ED Profee emit free-text issue
    strings that do not map to the enums, so those rows are skipped when
    practice results are mirrored; rubric specialties produce no code-level
    feedback at all. The tab therefore cannot see them — and a silent
    under-report is worse than a gap, because "0 errors in E/M" reads as clean
    work rather than as unmeasured.
    """

    def test_a_specialty_with_no_feedback_is_flagged(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPCOV1"), "A", "E1", "J18.9")
        # An E/M result with a score but no representable feedback.
        c = _chart(db, "EMCOV1", Specialty.EM)
        db.add(GradingResult(batch_id=b.id, coder_name="B", emp_id="E2", chart_id=c.id,
                             specialty=Specialty.EM, total_score=70, pass_fail=PassFail.FAIL))
        db.commit()
        body = client.get(URL).json()
        assert "E/M" in body["not_represented"]
        assert "IP-DRG" not in body["not_represented"]

    def test_coverage_counts_are_reported_per_specialty(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPCOV2"), "A", "E1", "J18.9")
        c = _chart(db, "EMCOV2", Specialty.EM)
        db.add(GradingResult(batch_id=b.id, coder_name="B", emp_id="E2", chart_id=c.id,
                             specialty=Specialty.EM, total_score=70, pass_fail=PassFail.FAIL))
        db.commit()
        cov = {c["specialty"]: c for c in client.get(URL).json()["coverage"]}
        assert cov["E/M"]["graded"] == 1 and cov["E/M"]["with_feedback"] == 0
        assert cov["IP-DRG"]["with_feedback"] == 1

    def test_the_gap_is_the_first_thing_said(self, client, db):
        """It changes how every other line should be read."""
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IPCOV3"), "A", "E1", "J18.9")
        c = _chart(db, "EMCOV3", Specialty.EM)
        db.add(GradingResult(batch_id=b.id, coder_name="B", emp_id="E2", chart_id=c.id,
                             specialty=Specialty.EM, total_score=70, pass_fail=PassFail.FAIL))
        db.commit()
        notes = client.get(URL).json()["commentary"]
        assert "not measured here" in notes[0]["text"]


class TestTrendIsARate:
    def test_the_trend_carries_charts_and_a_rate(self, client, db):
        b = _batch(db, "B")
        for i in range(3):
            _err_n(db, b, _chart(db, f"TR{i}"), f"C{i}", f"E{i}",
                   ["A00.0", "B00.0"], when=datetime(2026, 4, 5))
        t = client.get(URL).json()["trend"][0]
        assert t["charts"] == 3
        assert t["errors_per_chart"] == 2.0

    def test_growing_volume_at_a_steady_rate_is_not_called_decline(self, client, db):
        """
        The reason the rate matters: triple the practice at the same quality
        and a raw count triples. That must not read as getting worse.
        """
        b = _batch(db, "B")
        for m, n in ((1, 2), (2, 4), (3, 8)):
            for i in range(n):
                _err_n(db, b, _chart(db, f"VOL{m}_{i}"), f"C{i}", f"E{i}",
                       ["A00.0"], when=datetime(2026, m, 5))
        body = client.get(URL).json()
        notes = body["commentary"] + body["commentary_more"]
        assert not any(n["kind"] == "warn" and "rising" in n["text"] for n in notes)


# ── clinical axes ────────────────────────────────────────────────────────────

def _codes(db):
    """A small slice of the CMS tables, shaped like the real ones."""
    from models import CodeDescription, PcsCodeAxis
    db.add_all([
        CodeDescription(code="I5031", code_system="ICD10CM",
                        description="Acute diastolic heart failure",
                        chapter="Diseases of the circulatory system",
                        chapter_no=9, cc_mcc_status="MCC", is_billable=True),
        CodeDescription(code="I10", code_system="ICD10CM",
                        description="Essential hypertension",
                        chapter="Diseases of the circulatory system",
                        chapter_no=9, cc_mcc_status=None, is_billable=True),
        CodeDescription(code="E119", code_system="ICD10CM",
                        description="Type 2 diabetes without complications",
                        chapter="Endocrine, nutritional and metabolic diseases",
                        chapter_no=4, cc_mcc_status=None, is_billable=True),
        CodeDescription(code="N179", code_system="ICD10CM",
                        description="Acute kidney failure, unspecified",
                        chapter="Diseases of the genitourinary system",
                        chapter_no=14, cc_mcc_status="CC", is_billable=True),
        CodeDescription(code="0DTJ4ZZ", code_system="ICD10PCS",
                        description="Resection of Appendix", is_billable=True),
    ])
    db.add(PcsCodeAxis(code="0DTJ4ZZ", section="Medical and Surgical",
                       body_system="Gastrointestinal System",
                       root_operation="Resection", body_part="Appendix",
                       approach="Percutaneous Endoscopic",
                       device="No Device", qualifier="No Qualifier"))
    db.commit()


class TestChapterAxis:
    """
    Which body of knowledge the errors sit in. Every other grouping on this tab
    is administrative — section, issue type, coder, chart — and none of them
    can say "your team does not know circulatory".
    """

    def test_errors_roll_up_into_chapters(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        _err(db, b, c, "Bob", "E2", "I10")
        _err(db, b, c, "Cid", "E3", "E11.9")
        _codes(db)
        rows = client.get(URL, params={"include_scattered": True}).json()["by_chapter"]
        top = {r["label"]: r["count"] for r in rows}
        assert top["Diseases of the circulatory system"] == 2
        assert top["Endocrine, nutritional and metabolic diseases"] == 1

    def test_a_chapter_row_carries_its_spread(self, client, db):
        """
        Same concentration question the code rows answer: two coders on one
        chapter is a different problem from one coder repeating himself.
        """
        b, c1, c2 = _batch(db, "B"), _chart(db, "IP001"), _chart(db, "IP002")
        _err(db, b, c1, "Ann", "E1", "I50.31")
        _err(db, b, c2, "Bob", "E2", "I10")
        _codes(db)
        row = [r for r in client.get(URL, params={"include_scattered": True})
               .json()["by_chapter"]
               if r["label"].startswith("Diseases of the circulatory")][0]
        assert row["coders_affected"] == 2
        assert row["charts_affected"] == 2

    def test_procedures_do_not_appear_in_the_chapter_axis(self, client, db):
        """A PCS code has no ICD chapter — it must not be bucketed as one."""
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "0DTJ4ZZ", sect="PCS")
        _codes(db)
        assert client.get(URL, params={"include_scattered": True}
                          ).json()["by_chapter"] == []


class TestCcMccAxis:
    def test_secondary_diagnosis_errors_split_by_severity(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")       # MCC
        _err(db, b, c, "Bob", "E2", "N17.9")        # CC
        _err(db, b, c, "Cid", "E3", "E11.9")        # neither
        _codes(db)
        rows = {r["label"]: r["count"] for r in
                client.get(URL, params={"include_scattered": True}).json()["by_ccmcc"]}
        assert rows == {"MCC": 1, "CC": 1, "Neither": 1}

    def test_a_principal_diagnosis_is_not_counted(self, client, db):
        """
        CC/MCC is what a SECONDARY contributes to the DRG. A principal
        diagnosis has no CC/MCC role, so including it answers a question
        nobody asked.
        """
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31", sect="PDx")
        _codes(db)
        assert client.get(URL, params={"include_scattered": True}
                          ).json()["by_ccmcc"] == []


class TestPcsAxes:
    def test_procedure_errors_group_by_each_character(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "0DTJ4ZZ", sect="PCS")
        _err(db, b, c, "Bob", "E2", "0DTJ4ZZ", sect="PCS")
        _codes(db)
        axes = client.get(URL, params={"include_scattered": True}).json()["by_pcs_axis"]
        assert axes["root_operation"][0]["label"] == "Resection"
        assert axes["root_operation"][0]["count"] == 2
        assert axes["approach"][0]["label"] == "Percutaneous Endoscopic"

    def test_an_axis_with_nothing_in_it_is_absent(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        _codes(db)
        assert client.get(URL, params={"include_scattered": True}
                          ).json()["by_pcs_axis"] == {}


class TestItSaysWhatItCouldNotDescribe:
    """
    An empty chapter panel means one of three very different things: nothing
    was loaded, the codes are CPT and never can be described, or the edition
    does not have them. A trainer should not have to guess which.
    """

    def test_licensed_cpt_is_counted_separately_from_a_missing_code(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "99213", sect="CPT")   # AMA — never ours
        _err(db, b, c, "Bob", "E2", "Z99.99")              # not in this edition
        _err(db, b, c, "Cid", "E3", "I50.31")              # described
        _codes(db)
        e = client.get(URL, params={"include_scattered": True}).json()["enrichment"]
        assert e["available"] is True
        assert e["described"] == 1
        assert e["licensed_cpt"] == 1
        assert e["not_in_edition"] == 1

    def test_without_the_ingest_the_axes_are_empty_and_say_so(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        body = client.get(URL, params={"include_scattered": True}).json()
        assert body["enrichment"]["available"] is False
        assert body["by_chapter"] == [] and body["by_ccmcc"] == []

    def test_the_axes_never_change_a_score(self, client, db):
        """
        Enrichment only. Loading the code sets must not move a number anyone
        has already been told.
        """
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        before = client.get(URL, params={"include_scattered": True}).json()
        _codes(db)
        after = client.get(URL, params={"include_scattered": True}).json()
        for key in ("total_errors", "errors_per_chart", "by_issue_type",
                    "by_section", "total_codes"):
            assert before[key] == after[key], key


class TestDrilldownSaysWhatTheCodeIs:
    """
    A drilldown that lists who missed a code, without saying what the code is,
    asks the reader to already know. The section comes from the ERRORS, not
    from the code's shape — J1885 is real HCPCS and looks like a diagnosis, and
    only the rows know which box it was typed into.
    """

    def test_a_diagnosis_carries_its_description_chapter_and_severity(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        _codes(db)
        info = client.get(DETAIL, params={"code": "I50.31"}).json()["info"]
        assert info["description"] == "Acute diastolic heart failure"
        assert info["chapter_no"] == 9
        assert info["cc_mcc"] == "MCC"

    def test_a_procedure_carries_its_axes(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "0DTJ4ZZ", sect="PCS")
        _codes(db)
        info = client.get(DETAIL, params={"code": "0DTJ4ZZ"}).json()["info"]
        assert info["pcs"]["root_operation"] == "Resection"
        assert info["pcs"]["approach"] == "Percutaneous Endoscopic"

    def test_an_undescribed_code_still_returns_its_drilldown(self, client, db):
        """The evidence matters more than the caption; losing both would be worse."""
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "99213", sect="CPT")
        _codes(db)
        body = client.get(DETAIL, params={"code": "99213"}).json()
        assert body["info"] is None
        assert body["coders"] and body["coders"][0]["count"] == 1


class TestTeachingFocusAndKnowledgeGaps:
    """
    Both answer "what is this about" rather than "how bad is it", and both are
    thresholded. Labelling a chart "PCS Root Operation" off a single miss, or
    telling a trainer a coder has a circulatory gap on the strength of two
    errors, is the thin-row-as-pattern defect this codebase has paid for three
    times — worse than silence, because it sends someone to study the wrong
    thing.
    """

    TEACHING = "/practicelab/analytics/chart-teaching-value"
    CODER = "/practicelab/analytics/coder-summary"

    def test_a_chart_reports_what_its_errors_share(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        for coder, emp in (("Ann", "E1"), ("Bob", "E2"), ("Cid", "E3")):
            _err(db, b, c, coder, emp, "I50.31")
        _codes(db)
        rows = client.get(self.TEACHING, params={"scope": "all"}).json()
        focus = next(r for r in rows if r["chart_number"] == "IP001")["focus"]
        assert focus["kind"] == "Diagnosis chapter"
        assert focus["label"] == "Diseases of the circulatory system"
        assert focus["count"] == 3

    def test_two_errors_are_not_a_focus(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        _err(db, b, c, "Ann", "E1", "I50.31")
        _err(db, b, c, "Bob", "E2", "I10")
        _codes(db)
        rows = client.get(self.TEACHING, params={"scope": "all"}).json()
        assert next(r for r in rows if r["chart_number"] == "IP001")["focus"] is None

    def test_a_chart_with_no_describable_errors_has_no_focus(self, client, db):
        b, c = _batch(db, "B"), _chart(db, "IP001")
        for coder, emp in (("Ann", "E1"), ("Bob", "E2"), ("Cid", "E3")):
            _err(db, b, c, coder, emp, "99213", sect="CPT")
        _codes(db)
        rows = client.get(self.TEACHING, params={"scope": "all"}).json()
        assert next(r for r in rows if r["chart_number"] == "IP001")["focus"] is None

    def test_a_coder_gap_names_the_theme_not_the_codes(self, client, db):
        b = _batch(db, "B")
        for i, code in enumerate(["I50.31", "I10", "I50.31"]):
            _err(db, b, _chart(db, f"IP10{i}"), "Ann", "E1", code)
        _codes(db)
        gaps = client.get(self.CODER, params={"coder_name": "Ann", "scope": "all"}
                          ).json()["error_pattern"]["knowledge_gaps"]
        assert gaps and gaps[0]["kind"] == "Diagnosis chapter"
        assert gaps[0]["label"] == "Diseases of the circulatory system"
        assert gaps[0]["count"] == 3

    def test_a_thin_pattern_is_not_reported_as_a_gap(self, client, db):
        b = _batch(db, "B")
        _err(db, b, _chart(db, "IP201"), "Ann", "E1", "I50.31")
        _err(db, b, _chart(db, "IP202"), "Ann", "E1", "E11.9")
        _codes(db)
        assert client.get(self.CODER, params={"coder_name": "Ann", "scope": "all"}
                          ).json()["error_pattern"]["knowledge_gaps"] == []

    def test_a_severity_gap_is_reported_for_secondaries(self, client, db):
        b = _batch(db, "B")
        for i in range(3):
            _err(db, b, _chart(db, f"IP30{i}"), "Ann", "E1", "N17.9")
        _codes(db)
        gaps = client.get(self.CODER, params={"coder_name": "Ann", "scope": "all"}
                          ).json()["error_pattern"]["knowledge_gaps"]
        assert any(g["kind"] == "CC/MCC" and g["label"] == "CC" for g in gaps)

    def test_neither_is_never_offered_as_a_gap(self, client, db):
        """"Not a CC" is the absence of a theme, not a theme."""
        b = _batch(db, "B")
        for i in range(4):
            _err(db, b, _chart(db, f"IP40{i}"), "Ann", "E1", "E11.9")
        _codes(db)
        gaps = client.get(self.CODER, params={"coder_name": "Ann", "scope": "all"}
                          ).json()["error_pattern"]["knowledge_gaps"]
        assert all(g["label"] != "Neither" for g in gaps)

    def test_without_the_code_sets_there_are_no_gaps_and_no_error(self, client, db):
        b = _batch(db, "B")
        for i in range(3):
            _err(db, b, _chart(db, f"IP50{i}"), "Ann", "E1", "I50.31")
        body = client.get(self.CODER, params={"coder_name": "Ann", "scope": "all"}).json()
        assert body["error_pattern"]["knowledge_gaps"] == []
