"""
Which way an E/M level error went.

"42 level errors" is not actionable. Split by direction it is four different
conversations, and the split is the whole point of this module:

    upcoded      the work was overjudged
    downcoded    underjudged — revenue nobody is watching for
    patient type the encounter was misread, not the work
    critical care the 99285/99291 question, the hardest one in the ED
"""
import pytest

from services.em_levels import classify, ladder_of


class TestSameLadder:
    def test_a_level_above_the_key_is_upcoding(self):
        got = classify("99215", "99214")
        assert got["kind"] == "upcoded" and got["direction"] == "up"
        assert got["steps"] == 1

    def test_a_level_below_the_key_is_downcoding(self):
        got = classify("99213", "99214")
        assert got["kind"] == "downcoded" and got["direction"] == "down"
        assert got["steps"] == 1

    def test_the_distance_is_reported(self):
        """Two rungs out is a different problem from one."""
        assert classify("99215", "99213")["steps"] == 2

    def test_ed_levels_use_their_own_ladder(self):
        got = classify("99285", "99284")
        assert got["kind"] == "upcoded" and got["steps"] == 1

    def test_agreement_is_not_a_finding(self):
        assert classify("99214", "99214") is None


class TestPatientType:
    """
    New billed as established or the reverse. Not a misjudgement of the work —
    a misreading of the encounter, which is a different cause and a different
    fix.
    """

    def test_the_same_level_on_the_wrong_ladder(self):
        got = classify("99204", "99214")
        assert got["kind"] == "patient_type"
        assert got["steps"] == 0

    def test_it_works_in_the_other_direction(self):
        assert classify("99213", "99203")["kind"] == "patient_type"

    def test_wrong_ladder_and_wrong_level_still_reads_as_patient_type(self):
        """
        The patient type explains the ladder; the level difference follows from
        being on the wrong one. Calling it "upcoded" would name the symptom.
        """
        got = classify("99205", "99213")
        assert got["kind"] == "patient_type"
        assert got["steps"] == 2

    def test_the_nurse_visit_has_no_new_patient_form(self):
        """
        99211 pairs with nothing — there is no new-patient nurse visit — so it
        can only ever be an established-ladder finding.
        """
        assert classify("99211", "99212")["kind"] == "downcoded"


class TestCriticalCareBoundary:
    """
    The judgement the ED module turns on: does the condition qualify at all.
    Both directions are reported because they are opposite failures.
    """

    def test_critical_care_where_a_level_five_was_expected(self):
        got = classify("99291", "99285")
        assert got["kind"] == "critical_care_overreach"
        assert got["direction"] == "up"

    def test_a_level_five_where_critical_care_was_expected(self):
        """Revenue quietly left on the table, and nobody is looking for it."""
        got = classify("99285", "99291")
        assert got["kind"] == "critical_care_missed"
        assert got["direction"] == "down"

    def test_the_add_on_against_the_initial_unit_is_not_a_level_error(self):
        """99291 vs 99292 is a units question — a different check entirely."""
        assert classify("99292", "99291") is None

    def test_critical_care_against_an_office_code_is_not_this_finding(self):
        """
        Two different services rather than a boundary call. Reporting it as
        "critical care missed" would put noise beside the real ones.
        """
        assert classify("99291", "99214") is None


class TestItRefusesToGuess:
    def test_an_office_code_against_an_ed_code_is_not_a_direction(self):
        """
        Wrong place of service. Calling it "downcoded" would be nonsense — the
        ladders are not comparable.
        """
        assert classify("99214", "99284") is None

    def test_a_code_that_is_not_a_level_is_ignored(self):
        assert classify("20610", "99214") is None
        assert classify("99214", "36415") is None

    def test_blanks_are_ignored(self):
        assert classify("", "99214") is None
        assert classify("99214", None) is None

    def test_none_means_not_a_level_error_not_correct(self):
        """
        The distinction every caller has to honour: None covers agreement AND
        "this pair says nothing about levelling". Counting it as either would
        be wrong.
        """
        assert classify("99214", "99214") is None      # agreement
        assert classify("20610", "99214") is None      # not a level at all


class TestLadders:
    @pytest.mark.parametrize("code,expected", [
        ("99203", "new_office"), ("99213", "est_office"),
        ("99284", "emergency"), ("99291", None), ("20610", None),
    ])
    def test_a_code_knows_its_ladder(self, code, expected):
        assert ladder_of(code) == expected
