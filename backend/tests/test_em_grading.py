"""
E/M grading — time-based levelling, the submission field bridge, and the
Reasoning Accuracy weighting.

Two of these pin defects found in review that had been silently wrong in
production, so they assert the *magnitude*, not just that a number exists.
"""
import pytest

from routers.practicelab_pkg.em_grading import (
    grade_em_chart, time_supports_code, EM_TIME_BANDS,
)

CFG = {
    "line1_weight": 70.0, "line2_weight": 30.0,
    "em_level_weight": 23.33, "cpt_weight": 23.33, "dx_weight": 23.34,
    "copa_weight": 10.0, "dr_weight": 10.0, "risk_weight": 10.0,
    "pass_threshold": 80.0, "overcoding_penalty": True,
}

BASE_AK = {
    "em_code": "99214", "patient_type": "ESTABLISHED",
    "dx_codes": '["E11.9"]', "procedure_cpts": "[]",
    "copa_level": "Moderate", "dr_level": "Moderate", "risk_level": "Moderate",
    "copa_chronic_exacerbation": 1, "dr_order_tests": 1, "risk_prescription_drug_mgmt": 1,
}
BASE_SUB = {
    "sub_em_code": "99214", "sub_patient_type": "ESTABLISHED",
    "sub_dx_codes": '["E11.9"]', "sub_procedure_cpts": "[]",
    "sub_copa_chronic_exacerbation": 1, "sub_dr_order_tests": 1,
    "sub_risk_prescription_drug_mgmt": 1,
}


def grade(ak_extra=None, sub_extra=None):
    return grade_em_chart({**BASE_AK, **(ak_extra or {})},
                          {**BASE_SUB, **(sub_extra or {})}, CFG, True)


def reasoning(res):
    return res["reasoning_accuracy_total"]


class TestReasoningAccuracyWeighting:
    def test_reasoning_never_exceeds_its_weight(self):
        """
        Regression: _element_score counted every field where key and submission
        agreed, including all the both-zero ones, while dividing by only the
        non-zero key elements. COPA alone returned 100 against a weight of 10
        and Reasoning came out at 280/30.
        """
        assert reasoning(grade()) == 30.0

    def test_missing_all_elements_scores_zero_reasoning(self):
        res = grade(sub_extra={"sub_copa_chronic_exacerbation": 0,
                               "sub_dr_order_tests": 0,
                               "sub_risk_prescription_drug_mgmt": 0})
        assert reasoning(res) == 0.0


class TestSubmissionFieldBridge:
    """
    The coder form stores em_dx / em_cpt; the grader reads sub_dx_codes /
    sub_procedure_cpts. Without the bridge both arrive empty and every coder
    silently loses the whole Dx + CPT weight (~47 of 100).
    """

    def test_dx_and_cpt_score_when_present(self):
        ak = {"procedure_cpts": '["20610:RT"]', "dx_codes": '["E11.9","I10"]'}
        sub = {"sub_procedure_cpts": '["20610:RT"]', "sub_dx_codes": '["E11.9","I10"]'}
        res = grade(ak, sub)
        assert res["dx_score"] > 23
        assert res["cpt_score"] > 23

    def test_absent_fields_lose_the_full_weight(self):
        ak = {"procedure_cpts": '["20610:RT"]', "dx_codes": '["E11.9","I10"]'}
        sub = {"sub_procedure_cpts": "[]", "sub_dx_codes": "[]"}
        res = grade(ak, sub)
        assert res["dx_score"] == 0 and res["cpt_score"] == 0


class TestTimeBands:
    def test_established_bands_match_ama(self):
        assert EM_TIME_BANDS["99214"] == (30, 39)
        assert EM_TIME_BANDS["99213"] == (20, 29)

    def test_in_band(self):
        assert time_supports_code(35, "99214")

    def test_out_of_band(self):
        assert not time_supports_code(40, "99214")

    def test_ed_codes_have_no_time_option(self):
        assert not time_supports_code(35, "99283")

    def test_junk_input(self):
        assert not time_supports_code(None, "99214")
        assert not time_supports_code("abc", "99214")


class TestLevellingMethod:
    def test_mdm_key_mdm_coder_is_unchanged(self):
        res = grade()
        assert reasoning(res) == 30.0
        assert not res["method_mismatch"]

    def test_time_key_time_coder_in_band(self):
        res = grade({"level_method": "TIME", "total_time": 35},
                    {"sub_level_method": "TIME", "sub_total_time": 35})
        assert reasoning(res) == 30.0
        assert res["time_ok"]
        assert res["em_level_score"] > 0

    def test_time_key_time_coder_out_of_band_is_halved(self):
        res = grade({"level_method": "TIME", "total_time": 35},
                    {"sub_level_method": "TIME", "sub_total_time": 12})
        assert reasoning(res) == 15.0
        assert not res["time_ok"]

    def test_method_mismatch_keeps_the_level_and_loses_reasoning(self):
        """The case the product owner asked about explicitly."""
        res = grade({"level_method": "TIME", "total_time": 35},
                    {"sub_level_method": "MDM"})
        assert res["em_level_score"] > 0, "right code by the wrong route still scores the code"
        assert reasoning(res) == 0.0
        assert res["method_mismatch"]
        assert 65 <= res["total_score"] <= 72

    def test_mismatch_is_symmetric(self):
        res = grade(sub_extra={"sub_level_method": "TIME", "sub_total_time": 35})
        assert res["em_level_score"] > 0
        assert reasoning(res) == 0.0
        assert res["method_mismatch"]

    def test_wrong_code_by_the_right_method_still_loses_the_level(self):
        res = grade({"level_method": "TIME", "total_time": 35},
                    {"sub_level_method": "TIME", "sub_total_time": 35,
                     "sub_em_code": "99212"})
        assert res["em_level_score"] == 0
        assert reasoning(res) == 30.0


class TestPatientType:
    def test_mismatch_zeroes_the_level(self):
        res = grade(sub_extra={"sub_patient_type": "NEW"})
        assert res["em_level_score"] == 0
        assert res["patient_type_mismatch"]

    def test_na_on_the_key_skips_the_check(self):
        res = grade({"patient_type": "NA"}, {"sub_patient_type": "NEW"})
        assert res["em_level_score"] > 0
        assert not res["patient_type_mismatch"]


class TestSubmissionDictHelper:
    """The single bridge used by both submit and re-grade."""

    def test_maps_em_dx_and_em_cpt(self):
        from routers.practicelab_pkg.practice_sessions import _em_submission_dict
        out = _em_submission_dict({
            "em_code": "99214",
            "em_dx": [{"code": "E11.9"}, {"code": "I10"}],
            "em_cpt": [{"code": "20610", "modifier": "RT"}, {"code": "93000", "modifier": ""}],
        })
        assert out["sub_dx_codes"] == ["E11.9", "I10"]
        # AK stores "code:modifier"; bare code when there is no modifier
        assert out["sub_procedure_cpts"] == ["20610:RT", "93000"]
        assert out["sub_em_code"] == "99214"

    def test_handles_empty_and_junk(self):
        from routers.practicelab_pkg.practice_sessions import _em_submission_dict
        out = _em_submission_dict({"em_dx": [], "em_cpt": [{"code": "", "modifier": "X"}]})
        assert out["sub_dx_codes"] == []
        assert out["sub_procedure_cpts"] == []

    def test_none_blob(self):
        from routers.practicelab_pkg.practice_sessions import _em_submission_dict
        out = _em_submission_dict(None)
        assert out["sub_dx_codes"] == [] and out["sub_procedure_cpts"] == []
