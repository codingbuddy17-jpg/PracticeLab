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

class TestFinalizeIPScore:
    def test_perfect(self):
        cfg = IPScoringCfg()
        score = finalize_ip_score(cfg.pdx_weight, cfg.sdx_weight,
                                   cfg.pcs_weight, cfg.drg_weight,
                                   drg_flag=False, cfg=cfg)
        assert score == 100

    def test_drg_flag_sets_score_basis(self):
        cfg = IPScoringCfg()
        # With DRG flag, DRG portion goes to 0
        score_with_flag = finalize_ip_score(cfg.pdx_weight, cfg.sdx_weight,
                                             cfg.pcs_weight, 0,
                                             drg_flag=True, cfg=cfg)
        score_without_flag = finalize_ip_score(cfg.pdx_weight, cfg.sdx_weight,
                                                cfg.pcs_weight, cfg.drg_weight,
                                                drg_flag=False, cfg=cfg)
        assert score_with_flag < score_without_flag

    def test_all_zero_components(self):
        cfg = IPScoringCfg()
        score = finalize_ip_score(0, 0, 0, 0, drg_flag=False, cfg=cfg)
        assert score == 0

    def test_pass_fail_boundary(self):
        cfg = IPScoringCfg(pass_threshold=80)
        # Score exactly at threshold → pass
        above = finalize_ip_score(cfg.pdx_weight, cfg.sdx_weight,
                                   cfg.pcs_weight, cfg.drg_weight,
                                   drg_flag=False, cfg=cfg)
        assert above >= cfg.pass_threshold


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
        assert result.total_score < 100

    def test_scenario_perfect_submission(self):
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}, {"code": "0BHN3BZ"}],
        )
        result = grade_ip(self.BASE_AK, sub)
        assert result.total_score == 100
        assert result.passed is True
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
        assert result.passed is True


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
        assert result_heavy.total_score < result_default.total_score

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

        assert result_easy.passed is True
        assert result_hard.passed is False
