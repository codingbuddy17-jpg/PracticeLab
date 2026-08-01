"""
Unit + integration tests for the PracticeLab grading pipeline.
Tests the scoring engine in isolation AND via the grading endpoint
to verify scores are stored correctly.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.grading_engine import (
    grade_ip, grade_op,
    IPAnswerKey, OPAnswerKey,
    IPSubmission, OPSubmission,
    IPScoringCfg, OPScoringCfg,
    finalize_ip_score,
)


# ── Score finalisation ────────────────────────────────────────────────────────

def ip_total(result, cfg=None, drg_error=False):
    """
    IPGradingResult carries component scores only — there is no total on it,
    because the DRG component is a trainer decision made after grading.
    finalize_ip_score() is what combines them.
    """
    cfg = cfg or IPScoringCfg()
    total, pass_fail, _ = finalize_ip_score(
        result.pdx_score, result.sdx_score, result.pcs_score,
        drg_error=drg_error, drg_weight=cfg.drg_weight,
        pass_threshold=cfg.pass_threshold)
    return total, pass_fail


class TestFinalizeIPScore:
    """
    finalize_ip_score(pdx, sdx, pcs, drg_error, drg_weight, pass_threshold)
    -> (total, pass_fail, drg_score)

    These previously called it with drg_flag=/cfg= keywords that have never
    existed, so the whole class errored rather than testing anything.
    """

    def test_perfect(self):
        cfg = IPScoringCfg()
        total, pass_fail, drg_score = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            drg_error=False, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        assert total == 100
        assert pass_fail == "PASS"
        assert drg_score == cfg.drg_weight

    def test_drg_error_zeroes_only_the_drg_component(self):
        cfg = IPScoringCfg()
        with_error, pf_err, drg_err = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            drg_error=True, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        clean, pf_ok, drg_ok = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            drg_error=False, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        assert drg_err == 0 and drg_ok == cfg.drg_weight
        assert with_error == clean - cfg.drg_weight
        assert pf_err == "FAIL" and pf_ok == "PASS"

    def test_all_zero_components(self):
        cfg = IPScoringCfg()
        total, pass_fail, _ = finalize_ip_score(
            0, 0, 0, drg_error=True, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        assert total == 0
        assert pass_fail == "FAIL"

    def test_pass_fail_boundary_is_inclusive(self):
        cfg = IPScoringCfg(pass_threshold=80)
        at_threshold, pf_at, _ = finalize_ip_score(
            40, 40, 0, drg_error=True, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        assert at_threshold == 80 and pf_at == "PASS"

        below, pf_below, _ = finalize_ip_score(
            40, 39, 0, drg_error=True, drg_weight=cfg.drg_weight,
            pass_threshold=cfg.pass_threshold)
        assert below == 79 and pf_below == "FAIL"


# ── IP scoring scenarios ──────────────────────────────────────────────────────

class TestIPScoringScenarios:
    """
    Real-world-style scenarios: each named after the type of coding error.
    """
    BASE_AK = IPAnswerKey(
        pdx_code="J18.9",
        pdx_poa="Y",
        sdx=[
            {"code": "E11.65", "poa": "Y", "ccmcc": "CC"},
            {"code": "I10",    "poa": "Y", "ccmcc": ""},
        ],
        pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
    )

    def test_scenario_wrong_pdx_only(self):
        sub = IPSubmission(
            pdx_code="J96.00", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        assert result.pdx_score == 0
        assert result.sdx_score == IPScoringCfg().sdx_weight
        assert result.pcs_score == IPScoringCfg().pcs_weight
        assert result.drg_flag is True

    def test_scenario_missed_ccmcc_sdx(self):
        """Coder missed the CC-flagged secondary diagnosis."""
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "I10", "poa": "Y"}],  # missed E11.65 (CC)
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        assert result.pdx_score == IPScoringCfg().pdx_weight
        assert result.sdx_score < IPScoringCfg().sdx_weight
        assert result.drg_flag is True  # missing CC triggers DRG flag

    def test_scenario_overcoded_pcs(self):
        """Coder added a PCS code that doesn't exist in answer key."""
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}, {"code": "0DT64ZZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        assert result.pcs_score < IPScoringCfg().pcs_weight

    def test_scenario_poa_mismatch(self):
        """Correct diagnosis but wrong POA flag."""
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="N",  # POA should be Y
            sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        # POA mismatch on PDx typically reduces PDx score or triggers flag
        total, _ = ip_total(result)
        assert total < 100

    def test_scenario_perfect_submission(self):
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        total, pass_fail = ip_total(result)
        assert total == 100
        assert pass_fail == "PASS"
        assert result.drg_flag is False


# ── OP scoring scenarios ──────────────────────────────────────────────────────

class TestOPScoringScenarios:
    BASE_AK = OPAnswerKey(
        pdx_code="M79.3",
        sdx=[{"code": "E11.65"}],
        cpt=[{"code": "20610", "modifier": "RT"}, {"code": "J3301", "modifier": ""}],
    )

    def test_scenario_wrong_cpt_code(self):
        sub = OPSubmission(
            pdx_code="M79.3",
            sdx=[{"code": "E11.65"}],
            cpt=[{"code": "20600", "modifier": "RT"}],  # wrong code
        )
        result = grade_op(self.BASE_AK, sub)
        assert result.cpt_score < OPScoringCfg().cpt_weight

    def test_scenario_missing_modifier(self):
        sub = OPSubmission(
            pdx_code="M79.3",
            sdx=[{"code": "E11.65"}],
            cpt=[{"code": "20610", "modifier": ""},  # missing RT modifier
                 {"code": "J3301", "modifier": ""}],
        )
        result = grade_op(self.BASE_AK, sub)
        # Modifier mismatch should reduce cpt score
        assert result.total_score < 100

    def test_scenario_perfect_op(self):
        sub = OPSubmission(
            pdx_code="M79.3",
            sdx=[{"code": "E11.65"}],
            cpt=[{"code": "20610", "modifier": "RT"}, {"code": "J3301", "modifier": ""}],
        )
        result = grade_op(self.BASE_AK, sub)
        assert result.total_score == 100
        assert result.pass_fail == "PASS"


# ── Custom scoring configuration ──────────────────────────────────────────────

class TestCustomScoringConfig:
    def test_custom_pdx_weight(self):
        """Higher PDx weight → bigger hit when PDx is wrong."""
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code="WRONG", pdx_poa="Y", sdx=[], pcs=[])

        cfg_default = IPScoringCfg()
        cfg_heavy_pdx = IPScoringCfg(pdx_weight=60, sdx_weight=20,
                                      pcs_weight=10, drg_weight=10)

        result_default = grade_ip(ak, sub, cfg=cfg_default)
        result_heavy = grade_ip(ak, sub, cfg=cfg_heavy_pdx)
        total_default, _ = ip_total(result_default, cfg_default)
        total_heavy, _ = ip_total(result_heavy, cfg_heavy_pdx)
        assert total_heavy < total_default

    def test_custom_pass_threshold(self):
        """Higher threshold → harder to pass."""
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y",
                         sdx=[{"code": "E11.65", "poa": "Y", "ccmcc": "CC"}],
                         pcs=[])
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}], pcs=[])

        cfg_easy = IPScoringCfg(pass_threshold=50)
        cfg_hard = IPScoringCfg(pass_threshold=95)

        result_easy = grade_ip(ak, sub, cfg=cfg_easy)
        result_hard = grade_ip(ak, sub, cfg=cfg_hard)

        # DRG error drops the 40-point DRG component, leaving 60 — above the
        # easy threshold (50) and below the hard one (95).
        total_easy, pf_easy = ip_total(result_easy, cfg_easy, drg_error=True)
        total_hard, pf_hard = ip_total(result_hard, cfg_hard, drg_error=True)
        assert total_easy == total_hard == 60
        assert pf_easy == "PASS"
        assert pf_hard == "FAIL"


class TestDRGReviewTriggers:
    """
    A trainer DRG decision is only warranted when the error can actually move
    the DRG: PDx, a CC/MCC secondary, or PCS. A secondary diagnosis that is
    neither CC nor MCC does not change the DRG and must not queue for review.
    """

    AK = IPAnswerKey(
        pdx_code="J18.9", pdx_poa="Y",
        sdx=[{"code": "E11.65", "poa": "Y", "ccmcc": "CC"},
             {"code": "I10", "poa": "Y", "ccmcc": ""}],
        pcs=[{"code": "0BHN3BZ"}],
    )

    def test_clean_submission_does_not_flag(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is False

    def test_missing_non_ccmcc_secondary_does_not_flag(self):
        """I10 carries no CC/MCC — dropping it cannot move the DRG."""
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is False

    def test_extra_non_ccmcc_secondary_does_not_flag(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"},
                                {"code": "Z79.4", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is False

    def test_spurious_sdx_is_not_a_default_trigger(self):
        """
        Previously any SDx added against an empty key flagged for review, even
        though a non-CC/MCC secondary cannot move the DRG — and a coder-invented
        code carries no CC/MCC flag to test against.
        """
        assert "spurious_sdx" not in IPScoringCfg().drg_triggers
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "Z79.4", "poa": "Y"}], pcs=[])
        assert grade_ip(ak, sub).drg_flag is False

    # ── the three that SHOULD flag ──

    def test_wrong_pdx_flags(self):
        sub = IPSubmission(pdx_code="J96.00", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is True

    def test_pdx_poa_error_flags(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="N",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is True

    def test_missing_ccmcc_secondary_flags(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "I10", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}])
        assert grade_ip(self.AK, sub).drg_flag is True

    def test_missing_pcs_flags(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                           pcs=[])
        assert grade_ip(self.AK, sub).drg_flag is True

    def test_extra_pcs_flags(self):
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                           pcs=[{"code": "0BHN3BZ"}, {"code": "3E0336Z"}])
        assert grade_ip(self.AK, sub).drg_flag is True
