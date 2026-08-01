"""
Diagnosis pointers on professional claims (CMS-1500 Box 24E).

The case that matters most is the last one: pointers are POSITIONAL, so a coder
who orders their diagnoses differently from the key uses a different letter for
the same diagnosis. Comparing letters would mark correct work wrong.
"""
import pytest

from services.grading_engine import (
    grade_op, OPAnswerKey, OPSubmission, DEFAULT_OP_CFG,
    resolve_pointers, claim_dx_list,
)

AK_SDX = [{"code": "N17.9"}, {"code": "J18.9"}]


def _grade(ak_pointers, sub_pointers, sub_sdx=None, check=True):
    ak = OPAnswerKey(pdx_code="A41.9", sdx=AK_SDX,
                     cpt=[{"code": "20610", "modifier": "", "pointers": ak_pointers}])
    sub = OPSubmission(pdx_code="A41.9", sdx=sub_sdx if sub_sdx is not None else AK_SDX,
                       cpt=[{"code": "20610", "modifier": "", "pointers": sub_pointers}])
    return grade_op(ak, sub, DEFAULT_OP_CFG, check_pointers=check)


def _pointer_errors(res):
    return [f for f in res.feedback if f.issue_type == "Wrong_Pointer"]


class TestPointerResolution:
    def test_claim_dx_list_is_pdx_then_secondaries(self):
        assert claim_dx_list("A41.9", AK_SDX) == ["A41.9", "N17.9", "J18.9"]

    def test_letters_map_to_positions(self):
        dx = claim_dx_list("A41.9", AK_SDX)
        assert resolve_pointers(["A"], dx) == {"A419"}
        assert resolve_pointers(["C"], dx) == {"J189"}

    def test_out_of_range_letters_ignored(self):
        assert resolve_pointers(["Z"], claim_dx_list("A41.9", AK_SDX)) == set()

    def test_empty_pointers(self):
        assert resolve_pointers([], ["A41.9"]) == set()
        assert resolve_pointers(None, ["A41.9"]) == set()


class TestPointerScoring:
    def test_matching_pointers_score_full(self):
        res = _grade(["A"], ["A"])
        assert res.cpt_score == 50
        assert _pointer_errors(res) == []

    def test_wrong_pointer_costs_half_the_line(self):
        res = _grade(["A"], ["B"])
        assert res.cpt_score == 25
        assert len(_pointer_errors(res)) == 1

    def test_pointer_order_within_a_line_is_irrelevant(self):
        assert _grade(["A", "B"], ["B", "A"]).cpt_score == 50

    def test_facility_claims_ignore_pointers_entirely(self):
        res = _grade(["A"], [], check=False)
        assert res.cpt_score == 50
        assert _pointer_errors(res) == []

    def test_wrong_cpt_code_loses_the_line_regardless(self):
        ak = OPAnswerKey(pdx_code="A41.9", sdx=AK_SDX,
                         cpt=[{"code": "20610", "modifier": "", "pointers": ["A"]}])
        sub = OPSubmission(pdx_code="A41.9", sdx=AK_SDX,
                           cpt=[{"code": "29881", "modifier": "", "pointers": ["A"]}])
        assert grade_op(ak, sub, DEFAULT_OP_CFG, check_pointers=True).cpt_score == 0

    def test_different_letter_same_diagnosis_is_correct(self):
        """
        Key points B -> sdx[0] = N17.9.
        Coder reversed their secondaries and points C -> sdx[1] = N17.9.
        Same diagnosis, different letter: must earn full credit.
        """
        res = _grade(["B"], ["C"], sub_sdx=[{"code": "J18.9"}, {"code": "N17.9"}])
        assert res.cpt_score == 50, "letter-comparison would wrongly fail this"
        assert _pointer_errors(res) == []

    def test_feedback_names_the_codes_not_the_letters(self):
        detail = _pointer_errors(_grade(["A"], ["B"]))[0].detail
        assert "A41.9" in detail and "N17.9" in detail
