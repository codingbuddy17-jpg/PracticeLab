"""
In-browser practice session endpoints.
Handles token generation, session start, per-chart save, submit, and
trainer-facing submission review.
"""
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Chart, AnswerKey, Batch, BatchCoder, BatchChart,
    BatchAllocationCycle, Submission, GradingResult,
    GradingFeedback, ScoringConfig, Specialty,
)
from services.grading_engine import (
    grade_ip, grade_op, finalize_ip_score, cfg_from_db,
    IPAnswerKey, OPAnswerKey, IPSubmission, OPSubmission,
    DEFAULT_IP_CFG, DEFAULT_OP_CFG,
)
from .shared import _is_ip, _is_ed, MASTER_PASSPHRASE
from .self_practice import _grade_chart_for_sp

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _gen_token() -> str:
    prefix = "PRC"
    part1 = "".join(random.choices(string.ascii_uppercase, k=4))
    part2 = "".join(random.choices(string.digits, k=4))
    return f"{prefix}-{part1}{part2}"


def _specialty_type(specialty: Specialty) -> str:
    return "IP" if _is_ip(specialty) else "OP"


# ── Pydantic models ───────────────────────────────────────────────────────────

class GeneratePracticeTokens(BaseModel):
    batch_id: int
    cycle_id: Optional[int] = None
    show_results_to_coder: bool = False


class ChartCodeEntry(BaseModel):
    chart_id: int
    # IP / OP fields
    pdx_code: Optional[str] = None
    pdx_poa: Optional[str] = None
    sdx: list[dict] = []
    pcs: list[dict] = []
    cpt: list[dict] = []
    # E&D fields
    ed_review: Optional[str] = None
    ed_research: Optional[str] = None
    ed_resolution: Optional[str] = None
    ed_rationale: Optional[str] = None
    # common
    flagged: bool = False
    coder_notes: Optional[str] = None


class SaveChartDraft(BaseModel):
    entries: list[ChartCodeEntry]


class SubmitPracticeSession(BaseModel):
    entries: list[ChartCodeEntry]


# ── Token generation (trainer) ────────────────────────────────────────────────

@router.post("/practice-sessions/generate-tokens")
def generate_practice_tokens(payload: GeneratePracticeTokens, db: Session = Depends(get_db)):
    """
    Generate one practice token per coder in a batch (for the latest cycle,
    or a specific cycle_id). Tokens are stored as rows in practice_sessions.
    Idempotent — existing tokens for the same batch/cycle are returned as-is.
    """
    batch = db.query(Batch).filter(Batch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Determine cycle
    if payload.cycle_id:
        cycle = db.query(BatchAllocationCycle).filter(
            BatchAllocationCycle.id == payload.cycle_id,
            BatchAllocationCycle.batch_id == payload.batch_id,
        ).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found")
    else:
        cycle = db.query(BatchAllocationCycle).filter(
            BatchAllocationCycle.batch_id == payload.batch_id
        ).order_by(BatchAllocationCycle.cycle_number.desc()).first()
        if not cycle:
            raise HTTPException(status_code=400, detail="No allocation cycle found — run allocation first")

    # Get coders from this cycle's assignments
    assignments = db.query(BatchChart).filter(
        BatchChart.batch_id == payload.batch_id,
        BatchChart.cycle_id == cycle.id,
    ).all()

    if not assignments:
        raise HTTPException(
            status_code=400,
            detail="No charts are assigned in this cycle. Run allocation first, then generate tokens."
        )

    coder_charts: dict[str, list[int]] = {}
    for a in assignments:
        coder_charts.setdefault(a.coder_name, []).append(a.chart_id)

    specialty_val = batch.specialty.value if hasattr(batch.specialty, 'value') else str(batch.specialty)

    from sqlalchemy import text
    import json
    tokens = []
    for coder_name, chart_ids in coder_charts.items():
        # Check if token already exists for this batch/cycle/coder
        existing = db.execute(text(
            "SELECT id, token FROM practice_sessions "
            "WHERE batch_id=:b AND cycle_id=:c AND coder_name=:n LIMIT 1"
        ), {"b": payload.batch_id, "c": cycle.id, "n": coder_name}).fetchone()

        if existing:
            tokens.append({"coder_name": coder_name, "token": existing[1], "reused": True})
            continue

        token = _gen_token()
        # ensure uniqueness
        while db.execute(text("SELECT 1 FROM practice_sessions WHERE token=:t"), {"t": token}).fetchone():
            token = _gen_token()

        db.execute(text("""
            INSERT INTO practice_sessions
              (batch_id, cycle_id, coder_name, specialty, token,
               chart_ids, show_results_to_coder, status, created_at)
            VALUES
              (:b, :c, :n, :sp, :t, :ci, :sr, 'pending', CURRENT_TIMESTAMP)
        """), {
            "b": payload.batch_id,
            "c": cycle.id,
            "n": coder_name,
            "sp": specialty_val,
            "t": token,
            "ci": json.dumps(chart_ids),
            "sr": payload.show_results_to_coder,
        })
        tokens.append({"coder_name": coder_name, "token": token, "reused": False})

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Token generation failed: {exc}")

    return {"tokens": tokens, "batch_id": payload.batch_id, "cycle_id": cycle.id}


# ── Coder-facing: get session info by token ───────────────────────────────────

@router.get("/practice-sessions/by-token/{token}")
def get_practice_session(token: str, db: Session = Depends(get_db)):
    """Return session info for a coder — charts list, specialty, status."""
    from sqlalchemy import text
    import json

    sess = db.execute(text(
        "SELECT id, batch_id, coder_name, specialty, chart_ids, "
        "show_results_to_coder, status FROM practice_sessions WHERE token=:t"
    ), {"t": token}).fetchone()

    if not sess:
        raise HTTPException(status_code=404, detail="Invalid or expired practice token")

    sess_id, batch_id, coder_name, specialty, chart_ids_raw, show_results, status = sess

    if status == "submitted":
        # Check if results should be shown
        if show_results:
            results = _build_coder_results(sess_id, db)
            return {
                "session_id": sess_id, "status": "submitted",
                "coder_name": coder_name, "specialty": specialty,
                "show_results": True, "results": results,
            }
        return {"session_id": sess_id, "status": "submitted", "show_results": False,
                "coder_name": coder_name, "specialty": specialty}

    chart_ids = json.loads(chart_ids_raw) if isinstance(chart_ids_raw, str) else chart_ids_raw

    # Load chart details
    charts = []
    for cid in chart_ids:
        chart = db.query(Chart).filter(Chart.id == cid).first()
        if chart:
            charts.append({
                "chart_id": chart.id,
                "chart_number": chart.chart_number,
                "description": chart.description or "",
                "specialty": chart.specialty.value if chart.specialty else specialty,
                "category": chart.category or "",
                "difficulty": chart.difficulty.value if chart.difficulty else "",
            })

    # Load any saved drafts for this session
    drafts = db.execute(text(
        "SELECT chart_id, pdx_code, pdx_poa, sdx, pcs, cpt, "
        "ed_review, ed_research, ed_resolution, ed_rationale, flagged, coder_notes "
        "FROM practice_chart_drafts WHERE session_id=:s"
    ), {"s": sess_id}).fetchall()

    draft_map = {}
    for d in drafts:
        import json as _json
        draft_map[d[0]] = {
            "pdx_code": d[1], "pdx_poa": d[2],
            "sdx": _json.loads(d[3]) if isinstance(d[3], str) else (d[3] or []),
            "pcs": _json.loads(d[4]) if isinstance(d[4], str) else (d[4] or []),
            "cpt": _json.loads(d[5]) if isinstance(d[5], str) else (d[5] or []),
            "ed_review": d[6], "ed_research": d[7],
            "ed_resolution": d[8], "ed_rationale": d[9],
            "flagged": bool(d[10]), "coder_notes": d[11],
        }

    return {
        "session_id": sess_id,
        "coder_name": coder_name,
        "specialty": specialty,
        "status": status,
        "show_results": bool(show_results),
        "charts": charts,
        "drafts": draft_map,
    }


# ── Coder-facing: save draft (auto-save) ──────────────────────────────────────

@router.post("/practice-sessions/{session_id}/save-draft")
def save_draft(session_id: int, payload: SaveChartDraft, db: Session = Depends(get_db)):
    """Upsert per-chart code drafts for a session (called on every chart navigation)."""
    from sqlalchemy import text
    import json

    sess = db.execute(text(
        "SELECT status FROM practice_sessions WHERE id=:s"
    ), {"s": session_id}).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess[0] == "submitted":
        raise HTTPException(status_code=400, detail="Session already submitted")

    # Update session status to in_progress
    db.execute(text(
        "UPDATE practice_sessions SET status='in_progress' WHERE id=:s AND status='pending'"
    ), {"s": session_id})

    for entry in payload.entries:
        existing = db.execute(text(
            "SELECT id FROM practice_chart_drafts WHERE session_id=:s AND chart_id=:c"
        ), {"s": session_id, "c": entry.chart_id}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE practice_chart_drafts SET
                  pdx_code=:pdx, pdx_poa=:poa, sdx=:sdx, pcs=:pcs, cpt=:cpt,
                  ed_review=:er, ed_research=:eres, ed_resolution=:erl, ed_rationale=:era,
                  flagged=:fl, coder_notes=:cn, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=:s AND chart_id=:c
            """), {
                "pdx": entry.pdx_code, "poa": entry.pdx_poa,
                "sdx": json.dumps(entry.sdx), "pcs": json.dumps(entry.pcs),
                "cpt": json.dumps(entry.cpt),
                "er": entry.ed_review, "eres": entry.ed_research,
                "erl": entry.ed_resolution, "era": entry.ed_rationale,
                "fl": entry.flagged, "cn": entry.coder_notes,
                "s": session_id, "c": entry.chart_id,
            })
        else:
            db.execute(text("""
                INSERT INTO practice_chart_drafts
                  (session_id, chart_id, pdx_code, pdx_poa, sdx, pcs, cpt,
                   ed_review, ed_research, ed_resolution, ed_rationale,
                   flagged, coder_notes, updated_at)
                VALUES (:s, :c, :pdx, :poa, :sdx, :pcs, :cpt,
                        :er, :eres, :erl, :era, :fl, :cn, CURRENT_TIMESTAMP)
            """), {
                "s": session_id, "c": entry.chart_id,
                "pdx": entry.pdx_code, "poa": entry.pdx_poa,
                "sdx": json.dumps(entry.sdx), "pcs": json.dumps(entry.pcs),
                "cpt": json.dumps(entry.cpt),
                "er": entry.ed_review, "eres": entry.ed_research,
                "erl": entry.ed_resolution, "era": entry.ed_rationale,
                "fl": entry.flagged, "cn": entry.coder_notes,
            })

    db.commit()
    return {"saved": len(payload.entries)}


# ── Coder-facing: final submit ────────────────────────────────────────────────

@router.post("/practice-sessions/{session_id}/submit")
def submit_practice_session(session_id: int, payload: SubmitPracticeSession, db: Session = Depends(get_db)):
    """
    Final submission — saves all entries, runs grading engine per chart,
    stores results. Coder sees only completion message unless show_results=True.
    """
    from sqlalchemy import text
    import json

    sess = db.execute(text(
        "SELECT id, batch_id, coder_name, specialty, show_results_to_coder, status "
        "FROM practice_sessions WHERE id=:s"
    ), {"s": session_id}).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess[5] == "submitted":
        raise HTTPException(status_code=400, detail="Already submitted")

    sess_id, batch_id, coder_name, specialty_str, show_results, _ = sess
    specialty = Specialty(specialty_str)

    # Save final drafts
    for entry in payload.entries:
        existing = db.execute(text(
            "SELECT id FROM practice_chart_drafts WHERE session_id=:s AND chart_id=:c"
        ), {"s": session_id, "c": entry.chart_id}).fetchone()
        if existing:
            db.execute(text("""
                UPDATE practice_chart_drafts SET
                  pdx_code=:pdx, pdx_poa=:poa, sdx=:sdx, pcs=:pcs, cpt=:cpt,
                  ed_review=:er, ed_research=:eres, ed_resolution=:erl, ed_rationale=:era,
                  flagged=:fl, coder_notes=:cn, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=:s AND chart_id=:c
            """), {
                "pdx": entry.pdx_code, "poa": entry.pdx_poa,
                "sdx": json.dumps(entry.sdx), "pcs": json.dumps(entry.pcs),
                "cpt": json.dumps(entry.cpt),
                "er": entry.ed_review, "eres": entry.ed_research,
                "erl": entry.ed_resolution, "era": entry.ed_rationale,
                "fl": entry.flagged, "cn": entry.coder_notes,
                "s": session_id, "c": entry.chart_id,
            })
        else:
            db.execute(text("""
                INSERT INTO practice_chart_drafts
                  (session_id, chart_id, pdx_code, pdx_poa, sdx, pcs, cpt,
                   ed_review, ed_research, ed_resolution, ed_rationale,
                   flagged, coder_notes, updated_at)
                VALUES (:s, :c, :pdx, :poa, :sdx, :pcs, :cpt,
                        :er, :eres, :erl, :era, :fl, :cn, CURRENT_TIMESTAMP)
            """), {
                "s": session_id, "c": entry.chart_id,
                "pdx": entry.pdx_code, "poa": entry.pdx_poa,
                "sdx": json.dumps(entry.sdx), "pcs": json.dumps(entry.pcs),
                "cpt": json.dumps(entry.cpt),
                "er": entry.ed_review, "eres": entry.ed_research,
                "erl": entry.ed_resolution, "era": entry.ed_rationale,
                "fl": entry.flagged, "cn": entry.coder_notes,
            })

    is_ed_batch = _is_ed(specialty)

    if is_ed_batch:
        # E&D: store text responses, no auto-grading — goes to trainer rubric queue
        for entry in payload.entries:
            _upsert_ed_practice_result(db, session_id, entry, specialty)
    else:
        # IP / OP: auto-grade against answer key
        ip_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "IP").first()
        op_cfg_row = db.query(ScoringConfig).filter(ScoringConfig.specialty_type == "OP").first()
        ip_cfg = cfg_from_db(ip_cfg_row) if ip_cfg_row else DEFAULT_IP_CFG
        op_cfg = cfg_from_db(op_cfg_row) if op_cfg_row else DEFAULT_OP_CFG

        for entry in payload.entries:
            chart = db.query(Chart).filter(Chart.id == entry.chart_id).first()
            if not chart:
                continue
            ak_rec = db.query(AnswerKey).filter(AnswerKey.chart_id == entry.chart_id).first()
            if not ak_rec:
                _upsert_practice_result(db, session_id, entry, specialty, graded=False)
                continue
            sub_data = {
                "pdx_code": entry.pdx_code or "",
                "pdx_poa": entry.pdx_poa or "",
                "sdx": entry.sdx, "pcs": entry.pcs, "cpt": entry.cpt,
            }
            result_kwargs, feedback_items = _grade_chart_for_sp(chart, ak_rec, sub_data, ip_cfg, op_cfg)
            _upsert_practice_result(db, session_id, entry, specialty, graded=True,
                                    result_kwargs=result_kwargs, feedback_items=feedback_items,
                                    ak_rec=ak_rec)

    # Mark submitted
    db.execute(text(
        "UPDATE practice_sessions SET status='submitted', submitted_at=CURRENT_TIMESTAMP WHERE id=:s"
    ), {"s": session_id})
    db.commit()

    # E&D never auto-shows results — always goes to trainer review
    if show_results and not is_ed_batch:
        results = _build_coder_results(session_id, db)
        return {"submitted": True, "show_results": True, "results": results}

    return {"submitted": True, "show_results": False, "is_ed": is_ed_batch}


def _upsert_ed_practice_result(db, session_id, entry, specialty):
    """Store E&D text responses — no auto-grading, ed_scored=False."""
    from sqlalchemy import text

    existing = db.execute(text(
        "SELECT id FROM practice_results WHERE session_id=:s AND chart_id=:c"
    ), {"s": session_id, "c": entry.chart_id}).fetchone()

    vals = {
        "s": session_id, "c": entry.chart_id, "sp": specialty.value,
        "er": entry.ed_review, "eres": entry.ed_research,
        "erl": entry.ed_resolution, "era": entry.ed_rationale,
    }
    if existing:
        db.execute(text("""
            UPDATE practice_results SET
              specialty=:sp, ed_review=:er, ed_research=:eres,
              ed_resolution=:erl, ed_rationale=:era, ed_scored=FALSE
            WHERE session_id=:s AND chart_id=:c
        """), vals)
    else:
        db.execute(text("""
            INSERT INTO practice_results
              (session_id, chart_id, specialty,
               ed_review, ed_research, ed_resolution, ed_rationale, ed_scored)
            VALUES (:s, :c, :sp, :er, :eres, :erl, :era, FALSE)
        """), vals)


def _upsert_practice_result(db, session_id, entry, specialty, graded=False,
                            result_kwargs=None, feedback_items=None, ak_rec=None):
    from sqlalchemy import text
    import json

    existing = db.execute(text(
        "SELECT id FROM practice_results WHERE session_id=:s AND chart_id=:c"
    ), {"s": session_id, "c": entry.chart_id}).fetchone()

    if graded and result_kwargs:
        r = result_kwargs
        fb = feedback_items or []
        pdx_ak = ak_rec.pdx_code if ak_rec else None
        pdx_ok = (entry.pdx_code or "").strip().upper().replace(".", "") == \
                 (pdx_ak or "").strip().upper().replace(".", "") if pdx_ak else None
        vals = {
            "s": session_id, "c": entry.chart_id, "sp": specialty.value,
            "tot": r.get("weighted_score"), "pf": r.get("pass_fail"),
            "drg_f": False,
            "fb": json.dumps(fb),
            "pdx_sub": entry.pdx_code, "pdx_ak": pdx_ak, "pdx_ok": pdx_ok,
            "sdx_sub": json.dumps(entry.sdx),
            "sdx_ak": json.dumps(ak_rec.sdx or []) if ak_rec else "[]",
            "pcs_sub": json.dumps(entry.pcs),
            "pcs_ak": json.dumps(ak_rec.pcs or []) if ak_rec else "[]",
            "cpt_sub": json.dumps(entry.cpt),
            "cpt_ak": json.dumps(ak_rec.cpt or []) if ak_rec else "[]",
        }
    else:
        vals = {
            "s": session_id, "c": entry.chart_id, "sp": specialty.value,
            "tot": None, "pf": None, "drg_f": False, "fb": "[]",
            "pdx_sub": entry.pdx_code, "pdx_ak": None, "pdx_ok": None,
            "sdx_sub": json.dumps(entry.sdx), "sdx_ak": "[]",
            "pcs_sub": json.dumps(entry.pcs), "pcs_ak": "[]",
            "cpt_sub": json.dumps(entry.cpt), "cpt_ak": "[]",
        }

    if existing:
        db.execute(text("""
            UPDATE practice_results SET
              specialty=:sp, total_score=:tot, pass_fail=:pf, drg_flag=:drg_f,
              feedback=:fb, pdx_submitted=:pdx_sub, pdx_answer_key=:pdx_ak, pdx_correct=:pdx_ok,
              sdx_submitted=:sdx_sub, sdx_answer_key=:sdx_ak,
              pcs_submitted=:pcs_sub, pcs_answer_key=:pcs_ak,
              cpt_submitted=:cpt_sub, cpt_answer_key=:cpt_ak
            WHERE session_id=:s AND chart_id=:c
        """), vals)
    else:
        db.execute(text("""
            INSERT INTO practice_results
              (session_id, chart_id, specialty, total_score, pass_fail, drg_flag,
               feedback, pdx_submitted, pdx_answer_key, pdx_correct,
               sdx_submitted, sdx_answer_key,
               pcs_submitted, pcs_answer_key,
               cpt_submitted, cpt_answer_key)
            VALUES
              (:s, :c, :sp, :tot, :pf, :drg_f, :fb,
               :pdx_sub, :pdx_ak, :pdx_ok,
               :sdx_sub, :sdx_ak, :pcs_sub, :pcs_ak, :cpt_sub, :cpt_ak)
        """), vals)


def _build_coder_results(session_id: int, db) -> list:
    from sqlalchemy import text
    import json

    rows = db.execute(text("""
        SELECT pr.chart_id, c.chart_number, c.description,
               pr.specialty, pr.total_score, pr.pass_fail, pr.drg_flag,
               pr.pdx_submitted, pr.pdx_answer_key, pr.pdx_correct,
               pr.sdx_submitted, pr.sdx_answer_key,
               pr.pcs_submitted, pr.pcs_answer_key,
               pr.cpt_submitted, pr.cpt_answer_key,
               pr.feedback, pcd.flagged, pcd.coder_notes,
               pr.ed_review, pr.ed_research, pr.ed_resolution, pr.ed_rationale,
               pr.ed_scored, pr.ed_review_pass, pr.ed_research_coding_pass,
               pr.ed_research_payer_pass, pr.ed_research_nuances_pass,
               pr.ed_resolution_pass, pr.ed_rationale_tier, pr.ed_trainer_note
        FROM practice_results pr
        JOIN charts c ON c.id = pr.chart_id
        LEFT JOIN practice_chart_drafts pcd
          ON pcd.session_id=pr.session_id AND pcd.chart_id=pr.chart_id
        WHERE pr.session_id=:s
        ORDER BY c.chart_number
    """), {"s": session_id}).fetchall()

    def _j(v): return json.loads(v) if isinstance(v, str) else (v or [])
    def _b(v): return bool(v) if v is not None else None

    results = []
    for r in rows:
        results.append({
            "chart_id": r[0], "chart_number": r[1], "description": r[2],
            "specialty": r[3], "total_score": r[4], "pass_fail": r[5],
            "drg_flag": bool(r[6]),
            "pdx_submitted": r[7], "pdx_answer_key": r[8],
            "pdx_correct": _b(r[9]),
            "sdx_submitted": _j(r[10]), "sdx_answer_key": _j(r[11]),
            "pcs_submitted": _j(r[12]), "pcs_answer_key": _j(r[13]),
            "cpt_submitted": _j(r[14]), "cpt_answer_key": _j(r[15]),
            "feedback": _j(r[16]),
            "flagged": bool(r[17]) if r[17] is not None else False,
            "coder_notes": r[18],
            "ed_review": r[19], "ed_research": r[20],
            "ed_resolution": r[21], "ed_rationale": r[22],
            "ed_scored": bool(r[23]) if r[23] is not None else False,
            "ed_review_pass": _b(r[24]), "ed_research_coding_pass": _b(r[25]),
            "ed_research_payer_pass": _b(r[26]), "ed_research_nuances_pass": _b(r[27]),
            "ed_resolution_pass": _b(r[28]),
            "ed_rationale_tier": r[29], "ed_trainer_note": r[30],
        })
    return results


# ── Trainer-facing: list sessions for a batch ────────────────────────────────

@router.get("/practice-sessions/batch/{batch_id}")
def list_practice_sessions(batch_id: int, cycle_id: Optional[int] = None, db: Session = Depends(get_db)):
    from sqlalchemy import text

    q = "SELECT id, coder_name, specialty, token, status, submitted_at, show_results_to_coder " \
        "FROM practice_sessions WHERE batch_id=:b"
    params: dict = {"b": batch_id}
    if cycle_id:
        q += " AND cycle_id=:c"
        params["c"] = cycle_id
    q += " ORDER BY coder_name"

    rows = db.execute(text(q), params).fetchall()
    return {"sessions": [
        {
            "session_id": r[0], "coder_name": r[1], "specialty": r[2],
            "token": r[3], "status": r[4],
            "submitted_at": r[5].isoformat() if r[5] else None,
            "show_results_to_coder": bool(r[6]),
        }
        for r in rows
    ]}


# ── Trainer-facing: view one coder's submission ───────────────────────────────

@router.get("/practice-sessions/{session_id}/review")
def trainer_review_session(session_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import text

    sess = db.execute(text(
        "SELECT coder_name, specialty, status, submitted_at FROM practice_sessions WHERE id=:s"
    ), {"s": session_id}).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    results = _build_coder_results(session_id, db)
    return {
        "session_id": session_id,
        "coder_name": sess[0], "specialty": sess[1],
        "status": sess[2],
        "submitted_at": sess[3].isoformat() if sess[3] else None,
        "charts": results,
    }


# ── Trainer-facing: batch grid view ──────────────────────────────────────────

@router.get("/practice-sessions/batch/{batch_id}/grid")
def batch_practice_grid(batch_id: int, cycle_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Returns a grid: coders × charts with per-cell scores.
    Also returns insight lines derived from the grid.
    """
    from sqlalchemy import text
    import json

    q = ("SELECT ps.id, ps.coder_name, ps.status, ps.submitted_at "
         "FROM practice_sessions ps WHERE ps.batch_id=:b")
    params: dict = {"b": batch_id}
    if cycle_id:
        q += " AND ps.cycle_id=:c"
        params["c"] = cycle_id

    sessions = db.execute(text(q), params).fetchall()
    if not sessions:
        return {"coders": [], "charts": [], "grid": [], "insights": []}

    submitted = [s for s in sessions if s[2] == "submitted"]
    all_chart_ids: set[int] = set()
    coder_results: dict[str, dict] = {}

    for sess in submitted:
        sess_id, coder_name = sess[0], sess[1]
        rows = db.execute(text(
            "SELECT pr.chart_id, c.chart_number, pr.total_score, pr.pass_fail, pr.drg_flag "
            "FROM practice_results pr JOIN charts c ON c.id=pr.chart_id WHERE pr.session_id=:s"
        ), {"s": sess_id}).fetchall()
        coder_results[coder_name] = {}
        for r in rows:
            all_chart_ids.add(r[0])
            coder_results[coder_name][r[0]] = {
                "chart_number": r[1], "total_score": r[2],
                "pass_fail": r[3], "drg_flag": bool(r[4]),
                "session_id": sess_id,
            }

    # Build ordered chart list
    chart_order = []
    for cid in sorted(all_chart_ids):
        chart = db.query(Chart).filter(Chart.id == cid).first()
        if chart:
            chart_order.append({"chart_id": cid, "chart_number": chart.chart_number,
                                 "description": chart.description or ""})

    # Build grid rows
    grid = []
    for sess in sessions:
        sess_id, coder_name, status, submitted_at = sess
        row = {
            "coder_name": coder_name, "status": status,
            "session_id": sess_id,
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "charts": {},
        }
        if coder_name in coder_results:
            scores = [v["total_score"] for v in coder_results[coder_name].values() if v["total_score"] is not None]
            row["avg_score"] = round(sum(scores) / len(scores), 1) if scores else None
            row["charts"] = coder_results[coder_name]
        else:
            row["avg_score"] = None
        grid.append(row)

    # ── Insights ─────────────────────────────────────────────────────────────
    insights = []
    if submitted:
        # Most missed chart
        chart_fails: dict[int, int] = {}
        chart_attempts: dict[int, int] = {}
        for coder_name, charts in coder_results.items():
            for cid, v in charts.items():
                chart_attempts[cid] = chart_attempts.get(cid, 0) + 1
                if v["pass_fail"] == "FAIL" or (v["total_score"] is not None and v["total_score"] < 80):
                    chart_fails[cid] = chart_fails.get(cid, 0) + 1

        if chart_fails:
            worst_cid = max(chart_fails, key=lambda k: chart_fails[k])
            worst_chart = next((c for c in chart_order if c["chart_id"] == worst_cid), None)
            if worst_chart:
                total = chart_attempts.get(worst_cid, 1)
                insights.append(
                    f"{worst_chart['chart_number']} is the most missed chart "
                    f"({chart_fails[worst_cid]}/{total} coders failed)"
                )

        # Weakest coder
        coder_avgs = [(r["coder_name"], r["avg_score"]) for r in grid if r.get("avg_score") is not None]
        if coder_avgs:
            weakest = min(coder_avgs, key=lambda x: x[1])
            charts_failed = sum(
                1 for v in coder_results.get(weakest[0], {}).values()
                if v["total_score"] is not None and v["total_score"] < 80
            )
            total_charts = len(coder_results.get(weakest[0], {}))
            insights.append(
                f"{weakest[0]} has the lowest average ({weakest[1]}%) — "
                f"{charts_failed}/{total_charts} charts below 80%"
            )

        # DRG flag count
        drg_flags = sum(
            1 for charts in coder_results.values()
            for v in charts.values() if v.get("drg_flag")
        )
        if drg_flags:
            insights.append(f"{drg_flags} DRG flag{'s' if drg_flags != 1 else ''} pending trainer review")

        # Pending submissions
        pending = len([s for s in sessions if s[2] != "submitted"])
        if pending:
            insights.append(f"{pending} coder{'s' if pending != 1 else ''} yet to submit")

    return {
        "sessions": [{"session_id": s[0], "coder_name": s[1], "status": s[2]} for s in sessions],
        "charts": chart_order,
        "grid": grid,
        "insights": insights,
    }


# ── Trainer-facing: score E&D practice chart ─────────────────────────────────

ED_RUBRIC_WEIGHTS = {
    "review_pass": 30,
    "research_coding_pass": 10,
    "research_payer_pass": 10,
    "research_nuances_pass": 10,
    "resolution_pass": 35,
}
ED_RATIONALE_SCORES = {"acceptable": 5, "needs_improvement": 3, "not_acceptable": 0}
ED_PASS_THRESHOLD = 80


class EDPracticeScore(BaseModel):
    review_pass: bool
    research_coding_pass: bool
    research_payer_pass: bool
    research_nuances_pass: bool
    resolution_pass: bool
    rationale_tier: str  # acceptable | needs_improvement | not_acceptable
    trainer_note: Optional[str] = None
    graded_by: str


@router.post("/practice-sessions/{session_id}/chart/{chart_id}/score-ed")
def score_ed_practice_chart(
    session_id: int, chart_id: int,
    payload: EDPracticeScore, db: Session = Depends(get_db)
):
    """Trainer scores one E&D chart in a practice session using the rubric."""
    from sqlalchemy import text

    sess = db.execute(text(
        "SELECT specialty, status FROM practice_sessions WHERE id=:s"
    ), {"s": session_id}).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _is_ed(Specialty(sess[0])):
        raise HTTPException(status_code=400, detail="Rubric scoring only applies to E&D sessions")

    score = sum(v for k, v in ED_RUBRIC_WEIGHTS.items() if getattr(payload, k))
    score += ED_RATIONALE_SCORES.get(payload.rationale_tier, 0)
    pf = "PASS" if score >= ED_PASS_THRESHOLD else "FAIL"

    existing = db.execute(text(
        "SELECT id FROM practice_results WHERE session_id=:s AND chart_id=:c"
    ), {"s": session_id, "c": chart_id}).fetchone()

    vals = {
        "s": session_id, "c": chart_id, "tot": score, "pf": pf,
        "rp": payload.review_pass, "rcp": payload.research_coding_pass,
        "rpp": payload.research_payer_pass, "rnp": payload.research_nuances_pass,
        "resp": payload.resolution_pass, "rt": payload.rationale_tier,
        "tn": payload.trainer_note, "gb": payload.graded_by,
    }

    if existing:
        db.execute(text("""
            UPDATE practice_results SET
              total_score=:tot, pass_fail=:pf, ed_scored=TRUE,
              ed_review_pass=:rp, ed_research_coding_pass=:rcp,
              ed_research_payer_pass=:rpp, ed_research_nuances_pass=:rnp,
              ed_resolution_pass=:resp, ed_rationale_tier=:rt,
              ed_trainer_note=:tn, ed_graded_by=:gb
            WHERE session_id=:s AND chart_id=:c
        """), vals)
    else:
        db.execute(text("""
            INSERT INTO practice_results
              (session_id, chart_id, ed_scored, total_score, pass_fail,
               ed_review_pass, ed_research_coding_pass, ed_research_payer_pass,
               ed_research_nuances_pass, ed_resolution_pass,
               ed_rationale_tier, ed_trainer_note, ed_graded_by)
            VALUES (:s, :c, TRUE, :tot, :pf, :rp, :rcp, :rpp, :rnp, :resp, :rt, :tn, :gb)
        """), vals)

    db.commit()
    return {"scored": True, "total_score": score, "pass_fail": pf}
