"""
The auditor's own session, and the trainer's view of what came back.

Everything the auditor sees is served from the FROZEN assignment. The claim is
read, never rebuilt — rebuilding it from the answer key would shift what they
were shown if that key were edited mid-session, and re-running the generator
would depend on config that may since have been tuned.

Nothing served to the auditor names the chart's type. Charts recycle through
cycles, so telling someone a chart was clean hands them the answer if they meet
it again.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AuditAssignment, AuditBatch, AuditBatchAuditor, AuditChartDraft,
    AuditResult, AuditSession, Chart, PassFail,
)
from services.audit_scoring import score_chart, score_session
from .shared import (
    QUERY_SPECIALTIES, assert_batch_open, form_spec, scoring_config,
)

router = APIRouter()

VERDICTS = {"no_changes", "needs_changes"}


class Finding(BaseModel):
    section: str
    action: str
    field: Optional[str] = None
    line: Optional[int] = None
    claim_value: Optional[str] = None
    correct_value: Optional[str] = None
    ccmcc: Optional[str] = None


class ChartWork(BaseModel):
    chart_id: int
    section_verdicts: dict = {}
    findings: list[Finding] = []
    query_flag: bool = False
    query_text: Optional[str] = None
    auditor_notes: Optional[str] = None


class SaveDraft(BaseModel):
    charts: list[ChartWork]


class SubmitSession(BaseModel):
    charts: list[ChartWork]


# ── auditor-facing ───────────────────────────────────────────────────────────

@router.get("/sessions/by-token/{token}")
def open_session(token: str, db: Session = Depends(get_db)):
    """
    Open a session by access code — the auditor's only credential.

    Opening a chart LOCKS its claim: a trainer may reroll plantings up to this
    moment and not afterwards, because from here the claim is what the auditor
    saw.
    """
    sess = db.query(AuditSession).filter(AuditSession.token == token.strip()).first()
    if not sess:
        raise HTTPException(404, "Access code not recognised")

    assignments = (db.query(AuditAssignment, Chart)
                   .join(Chart, Chart.id == AuditAssignment.chart_id)
                   .filter(AuditAssignment.batch_id == sess.batch_id,
                           AuditAssignment.cycle_id == sess.cycle_id,
                           AuditAssignment.auditor_name == sess.auditor_name)
                   .order_by(Chart.chart_number).all())

    if sess.status == "in_progress":
        now = datetime.utcnow()
        if sess.started_at is None:
            sess.started_at = now
        for a, _c in assignments:
            if a.opened_at is None:
                a.opened_at = now
        db.commit()

    if sess.status == "submitted":
        return {**_session_header(sess),
                "charts": [], "results": _auditor_results(db, sess)}

    drafts = {d.chart_id: d for d in db.query(AuditChartDraft)
              .filter(AuditChartDraft.session_id == sess.id).all()}

    return {
        **_session_header(sess),
        "form": form_spec(sess.specialty),
        "charts": [{
            "chart_id": a.chart_id,
            "chart_number": chart.chart_number,
            "category": chart.category,
            # The claim as presented. Nothing here says whether anything was
            # planted in it, and the panel must render it identically either
            # way — an empty state drawn differently is a tell.
            "claim": a.claim or {},
            "draft": None if a.chart_id not in drafts else {
                "section_verdicts": drafts[a.chart_id].section_verdicts or {},
                "findings": drafts[a.chart_id].findings or [],
                "query_flag": bool(drafts[a.chart_id].query_flag),
                "query_text": drafts[a.chart_id].query_text,
                "auditor_notes": drafts[a.chart_id].auditor_notes,
            },
        } for a, chart in assignments],
    }


def _session_header(sess: AuditSession) -> dict:
    return {
        "session_id": sess.id,
        "auditor_name": sess.auditor_name,
        "specialty": sess.specialty.value,
        "status": sess.status,
        "supports_query": sess.specialty in QUERY_SPECIALTIES,
        "show_results": bool(sess.show_results_to_auditor),
        "submitted_at": (sess.submitted_at.isoformat()
                         if sess.submitted_at else None),
    }


@router.post("/sessions/{session_id}/save-draft")
def save_draft(session_id: int, payload: SaveDraft, db: Session = Depends(get_db)):
    sess = db.query(AuditSession).filter(AuditSession.id == session_id).first()
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.status == "submitted":
        raise HTTPException(400, "This session has already been submitted")

    for work in payload.charts:
        _upsert_draft(db, session_id, work)
    db.commit()
    return {"saved": len(payload.charts)}


def _upsert_draft(db: Session, session_id: int, work: ChartWork) -> AuditChartDraft:
    row = (db.query(AuditChartDraft)
           .filter(AuditChartDraft.session_id == session_id,
                   AuditChartDraft.chart_id == work.chart_id).first())
    if row is None:
        row = AuditChartDraft(session_id=session_id, chart_id=work.chart_id)
        db.add(row)
    row.section_verdicts = work.section_verdicts or {}
    row.findings = [f.model_dump() for f in work.findings]
    row.query_flag = bool(work.query_flag)
    row.query_text = work.query_text
    row.auditor_notes = work.auditor_notes
    return row


@router.post("/sessions/{session_id}/submit")
def submit_session(session_id: int, payload: SubmitSession, db: Session = Depends(get_db)):
    """
    Score every chart and close the session.

    Section verdicts are required before submission. That is what turns a blank
    chart into an explicit claim — "I reviewed the diagnoses and found nothing"
    — rather than an absence, and an absence cannot be scored.
    """
    sess = db.query(AuditSession).filter(AuditSession.id == session_id).first()
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.status == "submitted":
        raise HTTPException(400, "This session has already been submitted")
    assert_batch_open(db, sess.batch_id, "submit an audit")

    assignments = {a.chart_id: a for a in db.query(AuditAssignment).filter(
        AuditAssignment.batch_id == sess.batch_id,
        AuditAssignment.cycle_id == sess.cycle_id,
        AuditAssignment.auditor_name == sess.auditor_name).all()}

    required = [s["key"] for s in form_spec(sess.specialty)["sections"]]
    work_by_chart = {w.chart_id: w for w in payload.charts}

    incomplete = []
    for chart_id in assignments:
        work = work_by_chart.get(chart_id)
        verdicts = (work.section_verdicts if work else {}) or {}
        missing = [s for s in required if verdicts.get(s) not in VERDICTS]
        if missing:
            incomplete.append({"chart_id": chart_id, "missing_sections": missing})
    if incomplete:
        raise HTTPException(400, {
            "message": "Every section needs a verdict before you can submit",
            "charts": incomplete,
        })

    # A raised query with nothing written is not reviewable — the text IS the
    # query, exactly as on the coder form.
    if sess.specialty in QUERY_SPECIALTIES:
        blank = [w.chart_id for w in payload.charts
                 if w.query_flag and not (w.query_text or "").strip()]
        if blank:
            raise HTTPException(400, {
                "message": "Write your query before submitting",
                "charts": [{"chart_id": c} for c in blank],
            })

    cfg = scoring_config(db)
    emp_id = _emp_id(db, sess)
    chart_scores = []

    for chart_id, assignment in assignments.items():
        work = work_by_chart.get(chart_id)
        if work is not None:
            _upsert_draft(db, session_id, work)
        findings = [f.model_dump() for f in (work.findings if work else [])]
        score = score_chart(
            assignment.ground_truth or [], findings, cfg,
            query_expected=assignment.query_expected,
            query_flagged=bool(work.query_flag) if work else False)
        chart_scores.append(score)
        db.add(_result_row(sess, assignment, score, findings, emp_id))

    session_score = score_session(chart_scores, cfg)
    sess.status = "submitted"
    sess.submitted_at = datetime.utcnow()
    db.commit()

    return {
        "submitted": True,
        "show_results": bool(sess.show_results_to_auditor),
        "summary": _session_summary(session_score),
        "results": _auditor_results(db, sess) if sess.show_results_to_auditor else [],
    }


def _emp_id(db: Session, sess: AuditSession) -> Optional[str]:
    if sess.emp_id:
        return sess.emp_id
    row = (db.query(AuditBatchAuditor)
           .filter(AuditBatchAuditor.batch_id == sess.batch_id,
                   AuditBatchAuditor.auditor_name == sess.auditor_name).first())
    return row.emp_id if row else None


def _result_row(sess, assignment, score, findings, emp_id) -> AuditResult:
    return AuditResult(
        session_id=sess.id, assignment_id=assignment.id,
        chart_id=assignment.chart_id, batch_id=sess.batch_id,
        auditor_name=sess.auditor_name, emp_id=emp_id,
        specialty=sess.specialty, is_clean=score.is_clean,
        add_planted=score.add_planted, add_found=score.add_found,
        add_accuracy=score.add_accuracy,
        revise_planted=score.revise_planted, revise_found=score.revise_found,
        revise_accuracy=score.revise_accuracy,
        delete_planted=score.delete_planted, delete_found=score.delete_found,
        delete_accuracy=score.delete_accuracy,
        over_calls=score.over_calls, over_call_tier=score.over_call_tier,
        over_call_deduction=score.over_call_deduction,
        query_expected=score.query_expected, query_flagged=score.query_flagged,
        query_correct=score.query_correct, query_deduction=score.query_deduction,
        detected_not_corrected=score.detected_not_corrected,
        drg_impacting_planted=score.drg_impacting_planted,
        drg_impacting_found=score.drg_impacting_found,
        audit_accuracy=score.audit_accuracy,
        findings=findings, feedback=score.matched,
    )


def _session_summary(s) -> dict:
    """
    Two bases here, and both are labelled on purpose.

    Audit accuracy AVERAGES chart scores — each chart is one unit of work.
    Component accuracies POOL findings over plantings, because averaging rates
    would let a chart with one planting count as much as a chart with six.
    """
    return {
        "charts": s.charts,
        "audit_accuracy": s.audit_accuracy,
        "audit_accuracy_basis": "average of chart scores",
        "clean_charts": s.clean_charts,
        "opportunity_charts": s.opportunity_charts,
        "clean_accuracy": s.clean_accuracy,
        "opportunity_accuracy": s.opportunity_accuracy,
        "add_accuracy": s.add_accuracy, "add_found": s.add_found,
        "add_planted": s.add_planted,
        "revise_accuracy": s.revise_accuracy, "revise_found": s.revise_found,
        "revise_planted": s.revise_planted,
        "delete_accuracy": s.delete_accuracy, "delete_found": s.delete_found,
        "delete_planted": s.delete_planted,
        "component_basis": "pooled findings over errors introduced",
        "drg_accuracy": s.drg_accuracy,
        "drg_impacting_found": s.drg_impacting_found,
        "drg_impacting_planted": s.drg_impacting_planted,
        "query_accuracy": s.query_accuracy, "query_charts": s.query_charts,
        "query_correct": s.query_correct,
        "over_calls": s.over_calls,
        "detected_not_corrected": s.detected_not_corrected,
        "opportunities": s.opportunities,
        "pass_fail": s.pass_fail,
        "verdict_withheld_reason": s.verdict_withheld_reason,
    }


def _auditor_results(db: Session, sess: AuditSession) -> list[dict]:
    """
    What the auditor sees back.

    Their score and their findings — never the chart's construction. No
    "clean", no "opportunity", no source, no planting count on a chart they got
    right. That vocabulary is trainer-side only.
    """
    rows = (db.query(AuditResult, Chart)
            .join(Chart, Chart.id == AuditResult.chart_id)
            .filter(AuditResult.session_id == sess.id)
            .order_by(Chart.chart_number).all())
    return [{
        "chart_id": r.chart_id, "chart_number": c.chart_number,
        "audit_accuracy": r.audit_accuracy,
        "add_accuracy": r.add_accuracy,
        "revise_accuracy": r.revise_accuracy,
        "delete_accuracy": r.delete_accuracy,
        "missed": [m["planting"] for m in (r.feedback or [])
                   if m.get("outcome") == "missed"],
        "detected_not_corrected": [m["planting"] for m in (r.feedback or [])
                                   if m.get("outcome") == "detected_not_corrected"],
        "over_calls": r.over_calls,
        "query_correct": r.query_correct,
    } for r, c in rows]


# ── trainer-facing ───────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/review")
def review_session(session_id: int, db: Session = Depends(get_db)):
    """
    The trainer's view: everything the auditor saw, everything they recorded,
    and everything that was planted — including the chart types, which is the
    one place that vocabulary belongs.
    """
    sess = db.query(AuditSession).filter(AuditSession.id == session_id).first()
    if not sess:
        raise HTTPException(404, "Session not found")

    results = (db.query(AuditResult, Chart)
               .join(Chart, Chart.id == AuditResult.chart_id)
               .filter(AuditResult.session_id == session_id)
               .order_by(Chart.chart_number).all())
    assignments = {a.chart_id: a for a in db.query(AuditAssignment).filter(
        AuditAssignment.batch_id == sess.batch_id,
        AuditAssignment.cycle_id == sess.cycle_id,
        AuditAssignment.auditor_name == sess.auditor_name).all()}
    drafts = {d.chart_id: d for d in db.query(AuditChartDraft)
              .filter(AuditChartDraft.session_id == session_id).all()}

    charts = []
    for r, c in results:
        a = assignments.get(r.chart_id)
        d = drafts.get(r.chart_id)
        charts.append({
            "chart_id": r.chart_id, "chart_number": c.chart_number,
            "chart_type": "clean" if r.is_clean else "opportunity",
            "source": a.source.value if a else None,
            "audit_accuracy": r.audit_accuracy,
            "add_planted": r.add_planted, "add_found": r.add_found,
            "add_accuracy": r.add_accuracy,
            "revise_planted": r.revise_planted, "revise_found": r.revise_found,
            "revise_accuracy": r.revise_accuracy,
            "delete_planted": r.delete_planted, "delete_found": r.delete_found,
            "delete_accuracy": r.delete_accuracy,
            "over_calls": r.over_calls, "over_call_tier": r.over_call_tier,
            "over_call_deduction": r.over_call_deduction,
            "detected_not_corrected": r.detected_not_corrected,
            "drg_impacting_planted": r.drg_impacting_planted,
            "drg_impacting_found": r.drg_impacting_found,
            "query_expected": r.query_expected, "query_flagged": r.query_flagged,
            "query_correct": r.query_correct,
            "query_text": d.query_text if d else None,
            "auditor_notes": d.auditor_notes if d else None,
            "section_verdicts": (d.section_verdicts if d else {}) or {},
            "ground_truth": (a.ground_truth if a else []) or [],
            "findings": r.findings or [],
            "outcomes": r.feedback or [],
            "claim": (a.claim if a else {}) or {},
        })

    scores = [_score_from_row(r) for r, _c in results]
    return {
        "session_id": sess.id, "auditor_name": sess.auditor_name,
        "emp_id": sess.emp_id, "specialty": sess.specialty.value,
        "status": sess.status,
        "submitted_at": sess.submitted_at.isoformat() if sess.submitted_at else None,
        "summary": _session_summary(score_session(scores, scoring_config(db))),
        "charts": charts,
    }


def _score_from_row(r: AuditResult):
    """Rebuild a ChartScore from a stored result so the roll-up has one code path."""
    from services.audit_scoring import ChartScore
    s = ChartScore(is_clean=bool(r.is_clean))
    s.add_planted, s.add_found, s.add_accuracy = r.add_planted, r.add_found, r.add_accuracy
    s.revise_planted, s.revise_found, s.revise_accuracy = (
        r.revise_planted, r.revise_found, r.revise_accuracy)
    s.delete_planted, s.delete_found, s.delete_accuracy = (
        r.delete_planted, r.delete_found, r.delete_accuracy)
    s.over_calls, s.over_call_tier = r.over_calls, r.over_call_tier
    s.over_call_deduction = r.over_call_deduction or 0.0
    s.query_expected, s.query_flagged = r.query_expected, r.query_flagged
    s.query_correct, s.query_deduction = r.query_correct, r.query_deduction or 0.0
    s.detected_not_corrected = r.detected_not_corrected
    s.drg_impacting_planted = r.drg_impacting_planted
    s.drg_impacting_found = r.drg_impacting_found
    s.audit_accuracy = r.audit_accuracy
    return s
