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
        # Dicts, so diagnosis pointers survive the trip to the grader.
        # normalise_cpts() still accepts the legacy "code:modifier" string form.
        assert out["sub_procedure_cpts"] == [
            {"code": "20610", "modifier": "RT", "pointers": []},
            {"code": "93000", "modifier": "", "pointers": []},
        ]
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


class TestCodesWithoutAnMDMLevel:
    """
    99211 is the nurse-visit code — no MDM requirement, so it has no entry in
    the MDM table and em_code_to_level returns None. A level comparison could
    never succeed, so an exactly-correct 99211 used to score zero.
    """

    def test_99211_has_no_mdm_level(self):
        from routers.practicelab_pkg.em_grading import em_code_to_level
        assert em_code_to_level("99211") is None

    def test_exact_99211_match_still_earns_the_level(self):
        res = grade({"em_code": "99211"}, {"sub_em_code": "99211"})
        assert res["em_level_score"] > 0

    def test_99211_against_a_different_code_does_not(self):
        res = grade({"em_code": "99211"}, {"sub_em_code": "99212"})
        assert res["em_level_score"] == 0

    def test_patient_type_still_gates_it(self):
        res = grade({"em_code": "99211", "patient_type": "ESTABLISHED"},
                    {"sub_em_code": "99211", "sub_patient_type": "NEW"})
        assert res["em_level_score"] == 0


class TestLevelMethodSanitising:
    """ED visit codes have no CPT time band, so a TIME key is unanswerable."""

    def test_ed_code_forced_to_mdm(self):
        from routers.practicelab_pkg.em_grading import _sanitise_level_method
        assert _sanitise_level_method("TIME", "99283") == "MDM"

    def test_office_code_keeps_time(self):
        from routers.practicelab_pkg.em_grading import _sanitise_level_method
        assert _sanitise_level_method("TIME", "99214") == "TIME"

    def test_anything_unrecognised_falls_back_to_mdm(self):
        from routers.practicelab_pkg.em_grading import _sanitise_level_method
        assert _sanitise_level_method(None, "99214") == "MDM"
        assert _sanitise_level_method("nonsense", "99214") == "MDM"


class TestEMProcedurePointers:
    """
    ED Profee and office E/M bill on a CMS-1500, so each procedure line points
    at the diagnoses justifying it. Checked only when the KEY carries pointers,
    so keys written before this exist keep grading exactly as before.
    """

    AK = {"dx_codes": '["E11.9","I10","J45.909"]',
          "procedure_cpts": '[{"code":"20610","modifier":"RT","pointers":["A"]}]'}

    def _sub(self, pointers, dx='["E11.9","I10","J45.909"]'):
        return {"sub_dx_codes": dx,
                "sub_procedure_cpts": [{"code": "20610", "modifier": "RT",
                                        "pointers": pointers}]}

    def test_matching_pointers_score_the_line_in_full(self):
        res = grade(self.AK, self._sub(["A"]))
        assert res["cpt_score"] > 23
        assert res["pointer_errors"] == []

    def test_wrong_pointer_costs_half_the_line(self):
        full = grade(self.AK, self._sub(["A"]))["cpt_score"]
        half = grade(self.AK, self._sub(["B"]))["cpt_score"]
        assert half == pytest.approx(full / 2, abs=0.01)

    def test_wrong_pointer_is_reported(self):
        res = grade(self.AK, self._sub(["B"]))
        assert len(res["pointer_errors"]) == 1
        assert res["pointer_errors"][0]["code"] == "20610"

    def test_different_letter_same_diagnosis_is_correct(self):
        """
        Key points A -> E11.9. Coder reordered their diagnoses so E11.9 is
        third and points C. Same diagnosis: must earn full credit.
        """
        res = grade(self.AK, self._sub(["C"], dx='["I10","J45.909","E11.9"]'))
        assert res["pointer_errors"] == []
        assert res["cpt_score"] > 23

    def test_key_without_pointers_grades_as_before(self):
        ak = {"dx_codes": '["E11.9"]',
              "procedure_cpts": '[{"code":"20610","modifier":"RT","pointers":[]}]'}
        res = grade(ak, {"sub_dx_codes": '["E11.9"]',
                         "sub_procedure_cpts": [{"code": "20610", "modifier": "RT",
                                                 "pointers": ["Z"]}]})
        assert res["pointer_errors"] == []
        assert res["cpt_score"] > 23

    def test_legacy_string_keys_still_parse(self):
        """Older keys stored "code:modifier" strings — no migration was run."""
        from routers.practicelab_pkg.em_grading import normalise_cpts
        assert normalise_cpts('["20610:RT","93000"]') == [
            {"code": "20610", "modifier": "RT", "pointers": []},
            {"code": "93000", "modifier": "", "pointers": []},
        ]

    def test_string_form_can_also_carry_pointers(self):
        """Stored numerically now — coders refer to Dx 1, Dx 2."""
        from routers.practicelab_pkg.em_grading import normalise_cpts
        assert normalise_cpts('["20610:RT:1,2"]') == [
            {"code": "20610", "modifier": "RT", "pointers": ["1", "2"]}]

    def test_legacy_letter_pointers_are_read_as_the_same_positions(self):
        """
        Keys entered before the switch used A-L. They mean the same positions,
        so they normalise to the same list rather than being rejected — a key
        that silently lost its pointers would grade every line as unlinked.
        """
        from routers.practicelab_pkg.em_grading import normalise_cpts
        assert normalise_cpts('["20610:RT:A,B"]') == normalise_cpts('["20610:RT:1,2"]')

    def test_two_digit_pointers_are_not_truncated(self):
        """The old rule kept one character, turning pointer 10 into pointer 1."""
        from routers.practicelab_pkg.em_grading import normalise_cpts
        assert normalise_cpts('["20610::10,11"]')[0]["pointers"] == ["10", "11"]

    def test_wrong_code_loses_the_line_regardless_of_pointers(self):
        res = grade(self.AK, {"sub_dx_codes": '["E11.9"]',
                              "sub_procedure_cpts": [{"code": "99999", "modifier": "RT",
                                                      "pointers": ["A"]}]})
        assert res["cpt_score"] == 0


class TestEMSubmissionCarriesPointers:
    def test_bridge_emits_dicts_with_pointers(self):
        from routers.practicelab_pkg.practice_sessions import _em_submission_dict
        out = _em_submission_dict({
            "em_cpt": [{"code": "20610", "modifier": "RT", "pointers": ["A", "B"]}],
            "em_dx": [{"code": "E11.9"}],
        })
        assert out["sub_procedure_cpts"] == [
            {"code": "20610", "modifier": "RT", "pointers": ["A", "B"]}]


class TestEMModifier:
    """
    Graded exactly like a CPT modifier: the code+modifier PAIR must match, so a
    missing or wrong modifier 25 costs the E/M level component outright.
    """

    def test_matching_modifier_scores(self):
        res = grade({"em_modifier": "25"}, {"sub_em_modifier": "25"})
        assert res["em_level_score"] > 0
        assert not res["modifier_mismatch"]

    def test_missing_modifier_loses_the_level(self):
        res = grade({"em_modifier": "25"}, {"sub_em_modifier": ""})
        assert res["em_level_score"] == 0
        assert res["modifier_mismatch"]

    def test_unexpected_modifier_loses_the_level(self):
        res = grade({"em_modifier": ""}, {"sub_em_modifier": "25"})
        assert res["em_level_score"] == 0
        assert res["modifier_mismatch"]

    def test_both_blank_is_fine(self):
        res = grade()
        assert res["em_level_score"] > 0
        assert not res["modifier_mismatch"]

    def test_multi_modifier_order_and_separator_independent(self):
        """Same normalisation CPT lines get — '25,59' and '59;25' are equal."""
        res = grade({"em_modifier": "25,59"}, {"sub_em_modifier": "59;25"})
        assert res["em_level_score"] > 0

    def test_modifier_typed_into_the_code_cell_is_recovered(self):
        """Coders write '99214-25' with the modifier column blank."""
        res = grade({"em_modifier": "25"},
                    {"sub_em_code": "99214-25", "sub_em_modifier": ""})
        assert res["em_level_score"] > 0

    def test_modifier_mismatch_not_flagged_when_the_code_is_already_wrong(self):
        """Avoid blaming the modifier when the level was lost anyway."""
        res = grade({"em_modifier": "25"},
                    {"sub_em_code": "99212", "sub_em_modifier": ""})
        assert res["em_level_score"] == 0
        assert not res["modifier_mismatch"]
