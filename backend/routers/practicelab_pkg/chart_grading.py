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
from .shared import IP_SPECIALTIES, _uses_pointers, _uses_dpo, _is_single_path, _is_dx_only


def _empty_dpo_fields():
    return {
        "dpo_dx_accuracy": None,
        "dpo_poa_accuracy": None,
        "dpo_proc_accuracy": None,
        "dpo_overall_accuracy": None,
        "dpo_dx_correct": None, "dpo_dx_total": None,
        "dpo_poa_correct": None, "dpo_poa_total": None,
        "dpo_proc_correct": None, "dpo_proc_total": None,
    }


def _dpo_fields(dpo, include_poa: bool):
    return {
        "dpo_dx_accuracy": dpo.dx.accuracy,
        "dpo_poa_accuracy": dpo.poa.accuracy if include_poa else None,
        "dpo_proc_accuracy": dpo.proc.accuracy,
        "dpo_overall_accuracy": dpo.overall_accuracy,
        "dpo_dx_correct": dpo.dx.opportunities - dpo.dx.defects,
        "dpo_dx_total": dpo.dx.opportunities,
        "dpo_poa_correct": dpo.poa.opportunities - dpo.poa.defects if include_poa else 0,
        "dpo_poa_total": dpo.poa.opportunities if include_poa else 0,
        "dpo_proc_correct": dpo.proc.opportunities - dpo.proc.defects,
        "dpo_proc_total": dpo.proc.opportunities,
    }


def _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg, edsp_cfg=None):
    """Grade a single chart submission, return (result_kwargs, feedback_items)."""
    is_ip = chart.specialty in IP_SPECIALTIES
    feedback_items = []

    if _is_single_path(chart.specialty):
        from services.grading_engine import (
            grade_ed_single_path, EDSinglePathAnswerKey, EDSinglePathSubmission,
            DEFAULT_EDSP_CFG,
        )
        edsp_cfg = edsp_cfg or DEFAULT_EDSP_CFG
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
        res = grade_ed_single_path(ak, s, edsp_cfg)
        for fb in res.feedback:
            # `detail` carries what the codes alone cannot say: which POA
            # values differed, and how many extra codes were submitted. It was
            # dropped here, so a Wrong_POA finding reached the screen as the
            # same code twice with no indication of what was wrong with it, and
            # an Over_coded finding as two dashes.
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code,
                                   "detail": fb.detail})
        from services.grading_engine import compute_dpo_ed_single_path
        dpo = compute_dpo_ed_single_path(ak, s, edsp_cfg.overcoding_penalty)
        result = {
            "weighted_score": res.total_score,
            "pass_fail": res.pass_fail,
            "facility_level_ok": res.facility_level_ok,
            "profee_level_ok": res.profee_level_ok,
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "cpt_score": res.cpt_score, "pcs_score": None,
        }
        result.update(_dpo_fields(dpo, include_poa=False))
        return result, feedback_items

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
            # `detail` carries what the codes alone cannot say: which POA
            # values differed, and how many extra codes were submitted. It was
            # dropped here, so a Wrong_POA finding reached the screen as the
            # same code twice with no indication of what was wrong with it, and
            # an Over_coded finding as two dashes.
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code,
                                   "detail": fb.detail})
        result = {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "drg_flag": bool(res.drg_flag),
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": res.pcs_score, "cpt_score": None,
        }
        # Gated for the same reason the OP branch below is. Every specialty that
        # reaches here is currently a DPO specialty, so this changes nothing
        # today — but an addition to IP_SPECIALTIES that is not a DPO specialty
        # would otherwise start emitting DPO figures silently.
        if _uses_dpo(chart.specialty):
            dpo = compute_dpo_ip(ak, s, ip_cfg.overcoding_penalty)
            result.update(_dpo_fields(dpo, include_poa=True))
        return result, feedback_items
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
            # `detail` carries what the codes alone cannot say: which POA
            # values differed, and how many extra codes were submitted. It was
            # dropped here, so a Wrong_POA finding reached the screen as the
            # same code twice with no indication of what was wrong with it, and
            # an Over_coded finding as two dashes.
            feedback_items.append({"section": fb.section, "issue": fb.issue_type,
                                   "ak_code": fb.ak_code, "coder_code": fb.coder_code,
                                   "detail": fb.detail})
        result = {
            "weighted_score": pct,
            "pass_fail": "PASS" if passed else "FAIL",
            "pdx_score": res.pdx_score, "sdx_score": res.sdx_score,
            "pcs_score": None, "cpt_score": res.cpt_score,
        }
        if _uses_dpo(chart.specialty):
            dpo = compute_dpo_op(ak, s, op_cfg.overcoding_penalty)
            result.update(_dpo_fields(dpo, include_poa=False))
        else:
            result.update(_empty_dpo_fields())
        return result, feedback_items


# ── Re-grading after an answer key changes ───────────────────────────────────

def chart_regrade_impact(db, chart_id: int) -> dict:
    """
    What would be affected if this chart's answer key changed.

    Shown to the trainer BEFORE they commit an edit — discovering that a key
    change rewrote two closed batches after the fact is much worse than being
    told first.
    """
    from sqlalchemy import text
    from models import GradingResult, Batch, BatchStatus

    rows = (db.query(GradingResult, Batch)
            .join(Batch, GradingResult.batch_id == Batch.id)
            .filter(GradingResult.chart_id == chart_id)
            .all())

    batches, coders, closed, drg_locked = {}, set(), 0, 0
    for gr, b in rows:
        if b.id not in batches:
            batches[b.id] = {"batch_id": b.id, "name": b.name,
                             "status": b.status.value if hasattr(b.status, "value") else str(b.status),
                             "results": 0}
            if b.status == BatchStatus.CLOSED:
                closed += 1
        batches[b.id]["results"] += 1
        coders.add(gr.coder_name)
        # Trainer judgements are not derived from the key and must survive
        if gr.drg_reviewed and gr.drg_override is not None:
            drg_locked += 1

    released = db.execute(text("""
        SELECT COUNT(*) FROM practice_results pr
        JOIN practice_sessions ps ON ps.id = pr.session_id
        WHERE pr.chart_id = :c AND ps.show_results_to_coder = TRUE
    """), {"c": chart_id}).fetchone()
    released_count = (released[0] if released else 0) or 0

    return {
        "total_results": len(rows),
        "coders_affected": len(coders),
        "batches": list(batches.values()),
        "closed_batches": closed,
        "drg_decisions_preserved": drg_locked,
        "released_to_coders": released_count,
        "blocked": closed > 0,
    }


def regrade_chart_everywhere(db, chart_id: int, ip_cfg, op_cfg, edsp_cfg=None,
                             include_closed: bool = False) -> dict:
    """
    Re-grade every submitted practice result for one chart after its key changed.

    Preserves trainer decisions — DRG overrides and ED rubric scores are human
    judgements, not derived from the answer key, so they are restored after the
    automatic pass rather than recomputed.

    Writes through practice_results, which mirrors into grading_results, so
    analytics and both PDF reports pick the new numbers up with no extra work.
    """
    import json
    from sqlalchemy import text
    from models import Chart, AnswerKey, Batch, BatchStatus, GradingResult
    from .practice_sessions import _upsert_practice_result

    chart = db.query(Chart).filter(Chart.id == chart_id).first()
    ak_rec = db.query(AnswerKey).filter(AnswerKey.chart_id == chart_id).first()
    # E/M charts key off em_answer_keys and need the MDM engine, so they have no
    # AnswerKey row and fall out here. Explicit so it reads as intent, not luck.
    if not chart or not ak_rec:
        return {"regraded": 0, "skipped_closed": 0, "sessions": 0, "unsupported_em": True}

    rows = db.execute(text("""
        SELECT ps.id, ps.batch_id, ps.coder_name, ps.specialty
        FROM practice_results pr
        JOIN practice_sessions ps ON ps.id = pr.session_id
        WHERE pr.chart_id = :c AND ps.status = 'submitted'
    """), {"c": chart_id}).fetchall()

    regraded = skipped = 0
    for session_id, batch_id, coder_name, _spec in rows:
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if batch and batch.status == BatchStatus.CLOSED and not include_closed:
            skipped += 1
            continue

        draft = db.execute(text("""
            SELECT pdx_code, pdx_poa, sdx, pcs, cpt, flagged, coder_notes,
                   facility_level, profee_level
            FROM practice_chart_drafts WHERE session_id=:s AND chart_id=:c
        """), {"s": session_id, "c": chart_id}).fetchone()
        if not draft:
            continue

        def _j(v):
            return json.loads(v) if isinstance(v, str) else (v or [])

        class _Entry:
            pass
        entry = _Entry()
        entry.chart_id = chart_id
        entry.pdx_code, entry.pdx_poa = draft[0], draft[1]
        entry.sdx, entry.pcs, entry.cpt = _j(draft[2]), _j(draft[3]), _j(draft[4])
        entry.flagged, entry.coder_notes = draft[5], draft[6]
        entry.facility_level, entry.profee_level = draft[7], draft[8]

        # Snapshot the trainer's decisions before the automatic pass overwrites them
        gr = (db.query(GradingResult)
              .filter(GradingResult.batch_id == batch_id,
                      GradingResult.coder_name == coder_name,
                      GradingResult.chart_id == chart_id).first())
        keep = None
        if gr and gr.drg_reviewed:
            keep = (gr.drg_reviewed, gr.drg_override, gr.drg_reviewed_by, gr.drg_reviewed_at)

        sub_data = {
            "pdx_code": entry.pdx_code or "", "pdx_poa": entry.pdx_poa or "",
            "sdx": entry.sdx, "pcs": entry.pcs, "cpt": entry.cpt,
            "facility_level": entry.facility_level or "",
            "profee_level": entry.profee_level or "",
        }
        result_kwargs, feedback_items = _grade_chart_for_sp(
            chart, ak_rec, sub_data, ip_cfg, op_cfg, edsp_cfg)
        _upsert_practice_result(db, session_id, entry, chart.specialty, graded=True,
                                result_kwargs=result_kwargs, feedback_items=feedback_items,
                                ak_rec=ak_rec)

        if keep:
            gr2 = (db.query(GradingResult)
                   .filter(GradingResult.batch_id == batch_id,
                           GradingResult.coder_name == coder_name,
                           GradingResult.chart_id == chart_id).first())
            if gr2:
                gr2.drg_reviewed, gr2.drg_override, gr2.drg_reviewed_by, gr2.drg_reviewed_at = keep
        regraded += 1

    db.commit()
    return {"regraded": regraded, "skipped_closed": skipped, "sessions": len(rows)}
