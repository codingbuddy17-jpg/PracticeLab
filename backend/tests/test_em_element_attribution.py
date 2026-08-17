"""
Which reasoning element drives the level errors.

"The level was wrong" leaves a trainer to guess what to teach. COPA can drive
half a team's level errors while Risk drives a fifth, and the split differs per
team — so the tab has to say which element moved, and which way.

Two different questions, and both are needed:

  element error rate   how often this element is misjudged at all
  attribution          of the charts where the LEVEL was wrong, how often this
                       element was wrong too

They diverge because of the 2-of-3 rule: an element can be misread often and
rarely move the level.
"""
from routers.practicelab_pkg.practice_sessions import (_element_summary,
                                                       _level_error_attribution)


def _chart(copa=None, dr=None, risk=None, level_ok=True):
    return {"copa_delta": copa, "dr_delta": dr, "risk_delta": risk,
            "em_level_match": level_ok}


class TestElementErrorRate:
    def test_it_counts_each_element_apart(self):
        charts = [_chart(copa="over", dr="match", risk="match"),
                  _chart(copa="over", dr="match", risk="under"),
                  _chart(copa="match", dr="match", risk="match")]
        rows = {r["key"]: r for r in _element_summary(charts)}
        assert rows["copa"]["wrong"] == 2
        assert rows["risk"]["wrong"] == 1
        assert rows["dr"]["wrong"] == 0

    def test_the_rate_is_over_charts_where_it_could_be_judged(self):
        """
        A chart the key never levelled is not evidence either way. Counting it
        would make a team look better the more gaps their keys have.
        """
        charts = [_chart(copa="over"), _chart(copa=None), _chart(copa="match")]
        row = {r["key"]: r for r in _element_summary(charts)}["copa"]
        assert row["judged"] == 2
        assert row["error_rate"] == 50.0

    def test_the_lean_names_the_habit(self):
        charts = [_chart(copa="over"), _chart(copa="over"), _chart(copa="under")]
        assert {r["key"]: r for r in _element_summary(charts)}["copa"]["lean"] == "over"

    def test_erring_both_ways_equally_is_not_a_lean(self):
        charts = [_chart(copa="over"), _chart(copa="under")]
        assert {r["key"]: r for r in _element_summary(charts)}["copa"]["lean"] is None

    def test_an_element_nobody_ever_levelled_is_absent(self):
        rows = {r["key"] for r in _element_summary([_chart(copa="over")])}
        assert rows == {"copa"}


class TestAttribution:
    """The "COPA drives half our level errors" figure."""

    def test_it_counts_only_charts_whose_level_was_wrong(self):
        charts = [
            _chart(copa="over", level_ok=False),
            _chart(copa="over", level_ok=True),     # element wrong, level right
        ]
        got = _level_error_attribution(charts)
        assert got["level_errors"] == 1
        assert {r["key"]: r for r in got["elements"]}["copa"]["count"] == 1

    def test_shares_are_of_the_level_errors(self):
        charts = [_chart(copa="over", level_ok=False),
                  _chart(copa="over", level_ok=False),
                  _chart(risk="under", level_ok=False),
                  _chart(risk="under", level_ok=False)]
        rows = {r["key"]: r for r in _level_error_attribution(charts)["elements"]}
        assert rows["copa"]["share"] == 50.0
        assert rows["risk"]["share"] == 50.0

    def test_shares_need_not_sum_to_a_hundred(self):
        """
        Two elements can be wrong on one chart, and one wrong element often
        moves nothing at all. A reader who expects them to add up would think
        the figures were broken.
        """
        charts = [_chart(copa="over", risk="over", level_ok=False)]
        rows = _level_error_attribution(charts)["elements"]
        assert sum(r["share"] for r in rows) == 200.0

    def test_a_level_error_with_sound_reasoning_is_reported_separately(self):
        """
        The elements were all right and the code was still wrong — the coder
        built a correct case and then picked the wrong level. A different
        lesson from misreading the elements, and invisible if only attribution
        were reported.
        """
        charts = [_chart(copa="match", dr="match", risk="match", level_ok=False),
                  _chart(copa="over", level_ok=False)]
        got = _level_error_attribution(charts)
        assert got["reasoning_sound"] == 1
        assert got["reasoning_sound_share"] == 50.0

    def test_no_level_errors_is_a_clean_answer_not_a_crash(self):
        got = _level_error_attribution([_chart(copa="over", level_ok=True)])
        assert got["level_errors"] == 0 and got["elements"] == []


class TestTheRankingIsWorstFirst:
    def test_the_biggest_driver_leads(self):
        charts = ([_chart(risk="over", level_ok=False)] * 3
                  + [_chart(copa="over", level_ok=False)])
        rows = _level_error_attribution(charts)["elements"]
        assert rows[0]["key"] == "risk"
        assert rows[0]["share"] == 75.0
