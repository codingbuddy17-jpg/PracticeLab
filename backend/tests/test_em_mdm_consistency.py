"""
Whether a coder's own reasoning supports the level they chose.

TRAINER-SIDE ONLY, computed after grading. In front of a coder mid-session it
would be self-defeating — they would nudge one element until the warning
stopped, and the measurement would become "can you satisfy a validator" rather
than "can you code". These tests pin the maths; nothing here reaches the
coder's form.

It costs no marks. COPA, Data Review, Risk and the E/M level are each scored
already, so getting the elements right and the level wrong has already lost the
level's marks. What this adds is the PATTERN and its direction: consistently
coding above what the elements support is upcoding drift, consistently below is
undercoding, and they need opposite conversations.
"""
import pytest

from routers.practicelab_pkg.em_grading import (derive_mdm_level,
                                                em_code_to_level)


class TestTheTwoOfThreeRule:
    """
    The AMA rule: the overall level is the SECOND-LOWEST of the three
    components — two of the three must reach it.
    """

    def test_three_matching_components_give_that_level(self):
        assert derive_mdm_level("Moderate", "Moderate", "Moderate") == "Moderate"

    def test_two_of_three_carry_the_level(self):
        """Low, Moderate, Moderate -> Moderate. Two reached it."""
        assert derive_mdm_level("Low", "Moderate", "Moderate") == "Moderate"

    def test_one_high_component_does_not_lift_the_level(self):
        """
        The single most common misreading of the rule. One High among two Lows
        is still Low — the second-lowest decides.
        """
        assert derive_mdm_level("Low", "Low", "High") == "Low"

    def test_the_lowest_component_does_not_drag_it_down_either(self):
        assert derive_mdm_level("Minimal", "High", "High") == "High"


class TestConsistency:
    """
    Comparing what the coder's elements imply against the level their code
    carries. The direction is the finding, not the mismatch.
    """

    def _verdict(self, copa, dr, risk, code):
        from routers.practicelab_pkg.em_grading import _LEVEL_ORDER
        implied = derive_mdm_level(copa, dr, risk)
        chosen = em_code_to_level(code)
        if not implied or not chosen:
            return None
        if implied == chosen:
            return "consistent"
        return ("above" if _LEVEL_ORDER.get(chosen, 0) > _LEVEL_ORDER.get(implied, 0)
                else "below")

    def test_elements_and_code_agreeing_is_consistent(self):
        assert self._verdict("Moderate", "Moderate", "Moderate", "99214") == "consistent"

    def test_coding_above_what_the_elements_support(self):
        """Upcoding drift: Low reasoning, High code."""
        assert self._verdict("Low", "Low", "Low", "99215") == "above"

    def test_coding_below_what_the_elements_support(self):
        """Undercoding: the work was documented and not billed for."""
        assert self._verdict("High", "High", "High", "99212") == "below"

    def test_a_code_with_no_mdm_level_is_not_judged(self):
        """
        99211 is a nurse visit and carries no MDM level. None means "cannot be
        judged", which must never be counted as consistent.
        """
        assert em_code_to_level("99211") is None
        assert self._verdict("Low", "Low", "Low", "99211") is None

    def test_the_ed_codes_are_levelled_too(self):
        assert em_code_to_level("99285") == "High"
        assert self._verdict("High", "High", "High", "99285") == "consistent"


class TestItStaysOutOfTheCodersWay:
    """
    The rule this feature is governed by. If any of these ever fail, the check
    has leaked into the working form and the measurement is compromised.
    """

    def test_the_coder_form_does_not_import_the_rule(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
               / "pages" / "PracticeSession.tsx").read_text()
        for name in ("deriveMdmLevel", "mdm_consistency", "mdm_implied"):
            assert name not in src, \
                f"{name} reached the coder's form — this must stay trainer-side"

    def test_the_session_api_does_not_ship_it(self):
        """
        The coder's own session payload must not carry the verdict either, or
        it is one console open away from being visible.
        """
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "routers" / "practicelab_pkg" / "practice_sessions.py").read_text()
        i = src.index("def _em_breakdown")
        # The verdict is computed inside the analytics breakdown only.
        assert "mdm_consistency" in src[i:], "the verdict moved out of analytics"
