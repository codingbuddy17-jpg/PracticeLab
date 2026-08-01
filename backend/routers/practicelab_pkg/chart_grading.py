"""
Per-chart grading for in-browser practice sessions.

Lifted out of self_practice.py when that module was retired — the function was
never self-practice-specific, it just happened to live there, and
practice_sessions.py depends on it for every submit and re-grade.
"""
from dataclasses import replace

from services.grading_engine import (
    grade_ip, grade_op,
    compute_dpo_ip, compute_dpo_op,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
)
from .shared import IP_SPECIALTIES, _uses_pointers, _is_single_path, _is_dx_only


def _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg):
    """Grade a single chart submission, return (result_kwargs, feedback_items)."""
    is_ip = chart.specialty in IP_SPECIALTIES
    feedback_items = []

    if _is_single_path(chart.specialty):
        from services.grading_engine import (
            grade_ed_single_path, EDSinglePathAnswerKey, EDSinglePathSubmission,
            DEFAULT_EDSP_CFG,
        )
        ak = EDSinglePathAnswerKey(
            pdx_code=ak_rec.pdx_code or "",
            sdx=ak_rec.sdx or [],
            cpt=ak_rec.cpt or [],
            facility_level=ak_rec.facility_level or "",
            profee_level=ak_rec.profee_level or "",
        )
        s = EDSinglePathSubmission(
            pdx_code=sub_data.get("pdx_code", ""),
            sdx=sub_data.get("sdx", []),
            cpt=sub_data.get("cpt", []),
            facility_level=sub_data.get("facility_level", "") or "",
            profee_level=sub_data.get("profee_level", "") or "",
        )
        res = grade_ed_single_path(ak, s, DEFAULT_EDSP_CFG)
        for fb in res.feedback:
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code})
        return {
            "weighted_score": res.total_score,
            "pass_fail": res.pass_fail,
            "facility_level_ok": res.facility_level_ok,
            "profee_level_ok": res.profee_level_ok,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "cpt_score": res.cpt_score, "pcs_score": None,
        }, feedback_items

    if is_ip:
        ak = IPAnswerKey(
            pdx_code=ak_rec.pdx_code or "",
            pdx_poa=ak_rec.pdx_poa or "",
            sdx=ak_rec.sdx or [],
            pcs=ak_rec.pcs or [],
        )
        s = IPSubmission(
            pdx_code=sub_data.get("pdx_code", ""),
            pdx_poa=sub_data.get("pdx_poa", ""),
            sdx=sub_data.get("sdx", []),
            pcs=sub_data.get("pcs", []),
        )
        res = grade_ip(ak, s, ip_cfg)
        score = res.pdx_score + res.sdx_score + (res.pcs_score or 0)
        total_possible = ip_cfg.pdx_weight + ip_cfg.sdx_weight + ip_cfg.pcs_weight
        pct = round(score / total_possible * 100) if total_possible else 0
        passed = pct >= ip_cfg.pass_threshold
        for fb in res.feedback:
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code})
        dpo = compute_dpo_ip(ak, s, ip_cfg.overcoding_penalty)
        return {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "drg_flag": bool(res.drg_flag),
            "dpo_dx_accuracy": dpo.dx.accuracy,
            "dpo_poa_accuracy": dpo.poa.accuracy,
            "dpo_proc_accuracy": dpo.proc.accuracy,
            "dpo_overall_accuracy": dpo.overall_accuracy,
            # Raw counts — needed for cumulative DPO rollups (avg-of-avgs is wrong)
            "dpo_dx_correct": dpo.dx.opportunities - dpo.dx.defects,
            "dpo_dx_total": dpo.dx.opportunities,
            "dpo_poa_correct": dpo.poa.opportunities - dpo.poa.defects,
            "dpo_poa_total": dpo.poa.opportunities,
            "dpo_proc_correct": dpo.proc.opportunities - dpo.proc.defects,
            "dpo_proc_total": dpo.proc.opportunities,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": res.pcs_score, "cpt_score": None,
        }, feedback_items
    else:
        ak = OPAnswerKey(
            pdx_code=ak_rec.pdx_code or "",
            sdx=ak_rec.sdx or [],
            cpt=ak_rec.cpt or [],
        )
        s = OPSubmission(
            pdx_code=sub_data.get("pdx_code", ""),
            sdx=sub_data.get("sdx", []),
            cpt=sub_data.get("cpt", []),
        )
        # Diagnosis-only work (ancillary/radiology — CPTs are auto-coded upstream)
        # must not borrow the OP config: grade_op awards the FULL cpt_weight when
        # the key has no CPTs and the coder entered none, which would hand every
        # chart a free 50-point floor and make the pass threshold meaningless.
        # Renormalise onto Dx alone instead.
        dx_only = _is_dx_only(chart.specialty)
        if dx_only:
            op_cfg = replace(op_cfg, pdx_weight=50, sdx_weight=50, cpt_weight=0)

        # Professional claims (Surgery, ED Profee, E/M) carry diagnosis pointers
        res = grade_op(ak, s, op_cfg, check_pointers=_uses_pointers(chart.specialty))
        score = res.pdx_score + res.sdx_score + (res.cpt_score or 0)
        total_possible = op_cfg.pdx_weight + op_cfg.sdx_weight + op_cfg.cpt_weight
        pct = round(score / total_possible * 100) if total_possible else 0
        passed = pct >= op_cfg.pass_threshold
        for fb in res.feedback:
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code})
        dpo = compute_dpo_op(ak, s, op_cfg.overcoding_penalty)
        return {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "dpo_dx_accuracy": dpo.dx.accuracy,
            "dpo_poa_accuracy": None,
            "dpo_proc_accuracy": dpo.proc.accuracy,
            "dpo_overall_accuracy": dpo.overall_accuracy,
            # Raw counts — needed for cumulative DPO rollups (avg-of-avgs is wrong)
            "dpo_dx_correct": dpo.dx.opportunities - dpo.dx.defects,
            "dpo_dx_total": dpo.dx.opportunities,
            "dpo_poa_correct": 0, "dpo_poa_total": 0,   # OP has no POA
            "dpo_proc_correct": dpo.proc.opportunities - dpo.proc.defects,
            "dpo_proc_total": dpo.proc.opportunities,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": None, "cpt_score": res.cpt_score,
        }, feedback_items
