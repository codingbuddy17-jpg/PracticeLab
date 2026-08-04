"""Analytics endpoints for the Assessment module."""
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from datetime import timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentSession, AssessmentResponse, AssessmentResult,
    GeneratedAssessment, GeneratedAssessmentStudent,
)
from services.download_headers import content_disposition


router = APIRouter()

# Fallback only — used for assessments generated before the bar became a
# property of the paper. 90 was the hardcoded value; keeping it means existing
# figures do not move underneath anyone.
DEFAULT_PASS_THRESHOLD = 90.0
PASS_THRESHOLD = DEFAULT_PASS_THRESHOLD          # legacy alias


class AFilters:
    """
    The window a trainer is looking through: a date range and a batch.

    Deliberately NOT a specialty. A paper carries a specialty MIX — a 50/50
    IP-DRG and E&M assessment is not "an IP-DRG assessment", and specialty
    lives per-question inside questions_json rather than on the session, so a
    session-level specialty filter would be both unexpressible in SQL and
    wrong in meaning. The tabs that group BY specialty already answer that
    question at the level where it is well defined: the response.
    """

    def __init__(self, date_from: Optional[str] = None, date_to: Optional[str] = None,
                 batch_name: Optional[str] = None):
        self.date_from = date_from
        self.date_to = date_to
        self.batch_name = batch_name

    @property
    def active(self) -> bool:
        return bool(self.date_from or self.date_to or self.batch_name)


def filters(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    batch_name: Optional[str] = None,
) -> AFilters:
    """FastAPI dependency — one filter contract for every analytics endpoint."""
    return AFilters(date_from, date_to, batch_name)


def _session_q(db: Session, f: AFilters):
    """
    A filtered AssessmentSession query.

    Every analytics endpoint starts here rather than loading the table. The
    overview used to do `db.query(AssessmentSession).all()` and
    `db.query(AssessmentResult).all()`, pulling every session and every result
    into Python to filter them with list comprehensions — no date bound at all.
    That is fine on a few hundred rows and fatal on a year of them, and it is
    why the filters had to be pushed into SQL rather than added on top.
    """
    from datetime import date as date_cls, datetime as dt_cls, timezone

    q = db.query(AssessmentSession)

    if f.batch_name:
        ids = [a.id for a in db.query(GeneratedAssessment.id).filter(
            GeneratedAssessment.batch_name.is_(None) if f.batch_name == "Ungrouped"
            else GeneratedAssessment.batch_name == f.batch_name
        ).all()]
        q = q.filter(AssessmentSession.assessment_id.in_(ids or [-1]))

    # Dated by submission where there is one, falling back to when the session
    # was issued. Filtering on submitted_at alone would drop every pending,
    # expired and abandoned session — precisely the rows completion rate and
    # abandonment exist to count, so the metric would have reported 100%
    # completion for any window.
    when = func.coalesce(AssessmentSession.submitted_at, AssessmentSession.created_at)

    if f.date_from:
        try:
            d = date_cls.fromisoformat(f.date_from)
            q = q.filter(when >= dt_cls(d.year, d.month, d.day, tzinfo=timezone.utc))
        except ValueError:
            pass
    if f.date_to:
        try:
            d = date_cls.fromisoformat(f.date_to)
            # Inclusive of the end date: a trainer picking 1–31 March means all
            # of the 31st, not up to its opening instant.
            q = q.filter(when < dt_cls(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1))
        except ValueError:
            pass
    return q


def _thresholds(db) -> Dict[int, float]:
    """
    Each assessment's own pass mark, by id.

    A single module constant made every paper share one bar, and nothing on
    screen said what it was. Different assessments legitimately differ — a
    refresher and a certification gate are not the same test.
    """
    rows = db.query(GeneratedAssessment.id, GeneratedAssessment.pass_threshold).all()
    return {r[0]: float(r[1]) if r[1] else DEFAULT_PASS_THRESHOLD for r in rows}


def _passed(result, marks: Dict[int, float], session_assessment: Dict[int, int]) -> bool:
    """Did this result clear ITS OWN assessment's bar."""
    aid = session_assessment.get(result.session_id)
    return result.score_pct >= marks.get(aid, DEFAULT_PASS_THRESHOLD)


def coder_key(session) -> str:
    """
    Coder identity: employee id where present, else the typed name.

    The id was already captured at generation and stored on the session — the
    aggregations simply grouped by name, so one person entered two ways counted
    as two coders.
    """
    return (session.employee_id or "").strip() or session.coder_name.strip()


def _parse_questions(questions_json: Any) -> List[Dict]:
    """Parse questions_json field into a list of dicts."""
    if isinstance(questions_json, list):
        return questions_json
    if isinstance(questions_json, str):
        try:
            return json.loads(questions_json)
        except Exception:
            return []
    return []


def _score_band(score: float) -> str:
    if score < 50:
        return "0-49"
    elif score < 60:
        return "50-59"
    elif score < 70:
        return "60-69"
    elif score < 80:
        return "70-79"
    elif score < 90:
        return "80-89"
    return "90-100"


@router.get("/analytics/overview")
def analytics_overview(db: Session = Depends(get_db), f: AFilters = Depends(filters)):
    """High-level KPIs across the selected window."""
    all_sessions = _session_q(db, f).all()
    total_sessions = len(all_sessions)
    submitted_sessions = [s for s in all_sessions if s.status == "submitted"]
    expired_sessions = [s for s in all_sessions if s.status == "expired"]
    total_submitted = len(submitted_sessions)

    # Assessments represented in this window, not every assessment ever made —
    # otherwise the headline count contradicts every figure beside it.
    assessment_ids = sorted({s.assessment_id for s in all_sessions})
    total_assessments = (len(assessment_ids) if f.active
                         else db.query(GeneratedAssessment).count())

    # Pass rate — each result against its own assessment's bar. Scoped to this
    # window's sessions rather than every result in the table.
    session_ids = [s.id for s in all_sessions]
    results = (db.query(AssessmentResult)
               .filter(AssessmentResult.session_id.in_(session_ids)).all()
               if session_ids else [])
    marks = _thresholds(db)
    sess_assessment = {s.id: s.assessment_id for s in all_sessions}
    passed = sum(1 for r in results if _passed(r, marks, sess_assessment))
    overall_pass_rate = round(passed / len(results) * 100, 1) if results else 0.0
    avg_score = round(sum(r.score_pct for r in results) / len(results), 1) if results else 0.0

    # Completion rate = submitted / (submitted + expired + pending/in_progress)
    non_submitted = [s for s in all_sessions if s.status != "submitted"]
    completion_rate = round(total_submitted / total_sessions * 100, 1) if total_sessions else 0.0

    # Auto-submit rate
    auto_submitted_count = sum(1 for s in submitted_sessions if s.auto_submitted)
    auto_submit_rate = round(auto_submitted_count / total_submitted * 100, 1) if total_submitted else 0.0

    # Top 3 specialties by submission count — derive from questions_json of student slots
    # For submitted sessions, find their student slot
    submitted_session_ids = [s.id for s in submitted_sessions]
    specialty_counts: Dict[str, int] = {}
    if submitted_session_ids:
        # The sessions are already loaded; re-querying them by id fetched the
        # same rows a second time.
        slot_ids = list({s.student_slot_id for s in submitted_sessions if s.student_slot_id})
        if slot_ids:
            slots = (
                db.query(GeneratedAssessmentStudent)
                .filter(GeneratedAssessmentStudent.id.in_(slot_ids))
                .all()
            )
            for slot in slots:
                qs = _parse_questions(slot.questions_json)
                for q in qs:
                    sp = q.get("specialty", "Unknown")
                    specialty_counts[sp] = specialty_counts.get(sp, 0) + 1

    top_specialties = sorted(specialty_counts.items(), key=lambda x: -x[1])[:3]

    # Per-assessment pass rates for bar chart (last 10 assessments with results
    # IN THIS WINDOW — an unscoped list would chart papers the rest of the page
    # has filtered out).
    recent_q = db.query(GeneratedAssessment)
    if f.active:
        recent_q = recent_q.filter(GeneratedAssessment.id.in_(assessment_ids or [-1]))
    assessments = (
        recent_q
        .order_by(GeneratedAssessment.generated_at.desc())
        .limit(10)
        .all()
    )
    per_assessment = []
    for a in reversed(assessments):
        a_sessions = [s for s in all_sessions if s.assessment_id == a.id and s.status == "submitted"]
        a_results = [s.result for s in a_sessions if s.result]
        if not a_results:
            continue
        a_passed = sum(1 for r in a_results if r.score_pct >= marks.get(a.id, DEFAULT_PASS_THRESHOLD))
        per_assessment.append({
            "assessment_id": a.id,
            "assessment_name": a.assessment_name,
            "pass_rate": round(a_passed / len(a_results) * 100, 1),
            "submitted_count": len(a_results),
        })

    # Unique coders assessed
    unique_coders = len({coder_key(s) for s in submitted_sessions})

    return {
        "total_assessments": total_assessments,
        "total_sessions": total_sessions,
        "total_submitted": total_submitted,
        "unique_coders_assessed": unique_coders,
        "overall_pass_rate": overall_pass_rate,
        # A pass rate is not readable without its bar, and the bars can differ
        # per assessment — say so rather than implying one number governs all.
        "default_pass_threshold": DEFAULT_PASS_THRESHOLD,
        "pass_thresholds_vary": len({m for m in marks.values()}) > 1,
        "avg_score": avg_score,
        "completion_rate": completion_rate,
        "auto_submit_rate": auto_submit_rate,
        "top_specialties": [{"specialty": s, "count": c} for s, c in top_specialties],
        "per_assessment_pass_rates": per_assessment,
    }


@router.get("/analytics/assessment/{assessment_id}")
def analytics_by_assessment(assessment_id: int, db: Session = Depends(get_db)):
    """Drill-down for a single assessment."""
    assessment = db.query(GeneratedAssessment).filter(
        GeneratedAssessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Metadata from first student slot
    first_slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).first()
    questions_per_student = 0
    if first_slot:
        qs = _parse_questions(first_slot.questions_json)
        questions_per_student = len(qs)

    # All sessions for this assessment
    sessions = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.assessment_id == assessment_id)
        .all()
    )
    submitted_sessions = [s for s in sessions if s.status == "submitted"]
    total_sessions = len(sessions)
    total_submitted = len(submitted_sessions)

    # Completion / auto-submit
    completion_rate = round(total_submitted / total_sessions * 100, 1) if total_sessions else 0.0
    auto_submitted_count = sum(1 for s in submitted_sessions if s.auto_submitted)
    auto_submit_rate = round(auto_submitted_count / total_submitted * 100, 1) if total_submitted else 0.0

    # Per-coder table. One assessment, so one bar for the whole view.
    mark = float(assessment.pass_threshold) if assessment.pass_threshold else DEFAULT_PASS_THRESHOLD
    coder_rows: List[Dict] = []
    results_list: List[float] = []
    for s in submitted_sessions:
        r = s.result
        if r:
            results_list.append(r.score_pct)
            coder_rows.append({
                "coder_name": s.coder_name,
                "employee_id": s.employee_id,
                "score_pct": round(r.score_pct, 1),
                "correct_count": r.correct_count,
                "total_questions": r.total_questions,
                "time_taken_seconds": r.time_taken_seconds,
                "status": s.status,
                "auto_submitted": s.auto_submitted,
                "pass_fail": "PASS" if r.score_pct >= mark else "FAIL",
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            })
    coder_rows.sort(key=lambda x: -x["score_pct"])

    # Stats
    passed_count = sum(1 for sc in results_list if sc >= mark)
    pass_rate = round(passed_count / len(results_list) * 100, 1) if results_list else 0.0
    avg_score = round(sum(results_list) / len(results_list), 1) if results_list else 0.0
    min_score = round(min(results_list), 1) if results_list else 0.0
    max_score = round(max(results_list), 1) if results_list else 0.0

    # Score distribution
    bands = {"0-49": 0, "50-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    for sc in results_list:
        bands[_score_band(sc)] += 1
    score_distribution = [{"band": k, "count": v} for k, v in bands.items()]

    # Build question accuracy map
    # question_id -> {correct: int, total: int, topic: str, difficulty: str, question_text: str}
    q_meta: Dict[str, Dict] = {}

    # Gather question metadata from all student slots of this assessment
    all_slots = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).all()
    for slot in all_slots:
        qs = _parse_questions(slot.questions_json)
        for q in qs:
            qid = q.get("question_id", "")
            if qid and qid not in q_meta:
                q_meta[qid] = {
                    "question_id": qid,
                    "question_text": q.get("question_text", ""),
                    "topic": q.get("topic", "Unknown"),
                    "difficulty": q.get("difficulty", "Unknown"),
                    "correct": 0,
                    "total": 0,
                }

    # Aggregate responses
    submitted_session_ids = [s.id for s in submitted_sessions]
    if submitted_session_ids:
        responses = (
            db.query(AssessmentResponse)
            .filter(AssessmentResponse.session_id.in_(submitted_session_ids))
            .all()
        )
        for resp in responses:
            qid = resp.question_id
            if qid not in q_meta:
                q_meta[qid] = {
                    "question_id": qid,
                    "question_text": "",
                    "topic": "Unknown",
                    "difficulty": "Unknown",
                    "correct": 0,
                    "total": 0,
                }
            if resp.is_correct is not None:
                q_meta[qid]["total"] += 1
                if resp.is_correct:
                    q_meta[qid]["correct"] += 1

    question_accuracy = []
    for qid, d in q_meta.items():
        acc = round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else None
        question_accuracy.append({
            "question_id": qid,
            "question_text": d["question_text"],
            "topic": d["topic"],
            "difficulty": d["difficulty"],
            "accuracy_pct": acc,
            "correct": d["correct"],
            "total": d["total"],
        })
    # Sort most-missed first (None accuracy = no responses = put last)
    question_accuracy.sort(key=lambda x: (x["accuracy_pct"] is None, x["accuracy_pct"] if x["accuracy_pct"] is not None else 999))

    # Topic breakdown
    topic_map: Dict[str, Dict] = {}
    for q in question_accuracy:
        t = q["topic"]
        if t not in topic_map:
            topic_map[t] = {"accuracies": [], "count": 0}
        topic_map[t]["count"] += 1
        if q["accuracy_pct"] is not None:
            topic_map[t]["accuracies"].append(q["accuracy_pct"])
    topic_breakdown = sorted([
        {
            "topic": t,
            "question_count": d["count"],
            "avg_accuracy": round(sum(d["accuracies"]) / len(d["accuracies"]), 1) if d["accuracies"] else None,
        }
        for t, d in topic_map.items()
    ], key=lambda x: (x["avg_accuracy"] is None, x["avg_accuracy"] if x["avg_accuracy"] is not None else 999))

    # Difficulty calibration
    difficulty_expected = {"Easy": 85.0, "Medium": 70.0, "Hard": 55.0}
    diff_map: Dict[str, List[float]] = {}
    for q in question_accuracy:
        d = q["difficulty"]
        if q["accuracy_pct"] is not None:
            diff_map.setdefault(d, []).append(q["accuracy_pct"])
    difficulty_calibration = []
    for diff, expected in difficulty_expected.items():
        accs = diff_map.get(diff, [])
        actual = round(sum(accs) / len(accs), 1) if accs else None
        difficulty_calibration.append({
            "difficulty": diff,
            "expected_accuracy": expected,
            "actual_accuracy": actual,
            "question_count": len(accs),
        })

    # Duration from sessions
    duration_minutes = sessions[0].duration_minutes if sessions else None

    return {
        "assessment_id": assessment_id,
        "assessment_name": assessment.assessment_name,
        "generated_by": assessment.generated_by,
        "generated_at": assessment.generated_at.isoformat() if assessment.generated_at else None,
        "total_questions": questions_per_student,
        "duration_minutes": duration_minutes,
        "total_sessions": total_sessions,
        "total_submitted": total_submitted,
        "completion_rate": completion_rate,
        "auto_submit_rate": auto_submit_rate,
        "pass_rate": pass_rate,
        # The bar this paper was judged against. A pass rate cannot be read
        # without it, and the UI was assuming a fixed 90.
        "pass_threshold": mark,
        "avg_score": avg_score,
        "min_score": min_score,
        "max_score": max_score,
        "score_distribution": score_distribution,
        "coder_rows": coder_rows,
        "question_accuracy": question_accuracy,
        "topic_breakdown": topic_breakdown,
        "difficulty_calibration": difficulty_calibration,
    }


@router.get("/analytics/coder")
def analytics_coder(
    coder_name: str,
    employee_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exclude_session_ids: Optional[str] = None,
    batch_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """All submitted sessions for a coder across all assessments.

    date_from / date_to: ISO date strings (YYYY-MM-DD) — filter by submitted_at.
    exclude_session_ids: comma-separated session IDs to exclude from aggregation.
    batch_name: restrict to one batch. Without it this is a career history, which
        is right for a coder's own report and wrong for cohort evidence — a batch
        ZIP that carries every coder's whole past cannot be read as that batch's
        result. Pass "Ungrouped" for assessments with no batch.
    """
    from datetime import date as date_cls
    q = db.query(AssessmentSession).filter(
        AssessmentSession.coder_name == coder_name,
        AssessmentSession.status == "submitted",
    )
    if employee_id:
        q = q.filter(AssessmentSession.employee_id == employee_id)
    if batch_name:
        ids = [a.id for a in db.query(GeneratedAssessment).filter(
            GeneratedAssessment.batch_name.is_(None) if batch_name == "Ungrouped"
            else GeneratedAssessment.batch_name == batch_name
        ).all()]
        q = q.filter(AssessmentSession.assessment_id.in_(ids or [-1]))
    if date_from:
        try:
            dt_from = date_cls.fromisoformat(date_from)
            from datetime import datetime as dt_cls, timezone
            q = q.filter(AssessmentSession.submitted_at >= dt_cls(dt_from.year, dt_from.month, dt_from.day, tzinfo=timezone.utc))
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = date_cls.fromisoformat(date_to)
            from datetime import datetime as dt_cls, timezone, timedelta
            q = q.filter(AssessmentSession.submitted_at < dt_cls(dt_to.year, dt_to.month, dt_to.day, tzinfo=timezone.utc) + timedelta(days=1))
        except ValueError:
            pass
    sessions = q.order_by(AssessmentSession.submitted_at.asc()).all()

    # Apply client-side session exclusion after DB fetch
    if exclude_session_ids:
        excl = set()
        for part in exclude_session_ids.split(","):
            part = part.strip()
            if part.isdigit():
                excl.add(int(part))
        sessions = [s for s in sessions if s.id not in excl]

    if not sessions:
        return None

    # Per-session history. A coder's assessments can carry different bars, so
    # each row is judged against its own paper rather than one global mark.
    ch_marks = _thresholds(db)
    session_history: List[Dict] = []
    scores: List[float] = []
    times: List[int] = []
    for s in sessions:
        r = s.result
        if not r:
            continue
        a = db.query(GeneratedAssessment).filter(GeneratedAssessment.id == s.assessment_id).first()
        score = round(r.score_pct, 1)
        scores.append(score)
        if r.time_taken_seconds:
            times.append(r.time_taken_seconds)
        session_history.append({
            "session_id": s.id,
            "assessment_id": s.assessment_id,
            "assessment_name": a.assessment_name if a else "Unknown",
            "score_pct": score,
            "correct_count": r.correct_count,
            "total_questions": r.total_questions,
            "time_taken_seconds": r.time_taken_seconds,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            # The bar this particular paper set. Rows in one coder's history can
            # carry different bars, so colouring them all against one is wrong.
            "pass_threshold": ch_marks.get(s.assessment_id, DEFAULT_PASS_THRESHOLD),
            "pass_fail": ("PASS" if score >= ch_marks.get(s.assessment_id, DEFAULT_PASS_THRESHOLD)
                          else "FAIL"),
            "auto_submitted": s.auto_submitted,
        })

    # Summary stats
    total_taken = len(session_history)
    passed_count = sum(1 for sh in session_history if sh["pass_fail"] == "PASS")
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    pass_rate = round(passed_count / total_taken * 100, 1) if total_taken else 0.0
    best_score = round(max(scores), 1) if scores else 0.0
    worst_score = round(min(scores), 1) if scores else 0.0
    avg_time = round(sum(times) / len(times)) if times else None

    # Topic strength/weakness
    session_ids = [s.id for s in sessions]
    responses = (
        db.query(AssessmentResponse)
        .filter(AssessmentResponse.session_id.in_(session_ids))
        .all()
    )

    # Build topic map from question metadata
    q_topic: Dict[str, str] = {}
    q_difficulty: Dict[str, str] = {}
    assessment_ids = list(set(s.assessment_id for s in sessions))
    for aid in assessment_ids:
        slots = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.assessment_id == aid
        ).all()
        for slot in slots:
            qs = _parse_questions(slot.questions_json)
            for q_item in qs:
                qid = q_item.get("question_id", "")
                if qid:
                    q_topic[qid] = q_item.get("topic", "Unknown")
                    q_difficulty[qid] = q_item.get("difficulty", "Unknown")

    topic_acc: Dict[str, Dict] = {}
    diff_acc: Dict[str, Dict] = {}
    for resp in responses:
        if resp.is_correct is None:
            continue
        qid = resp.question_id
        topic = q_topic.get(qid, "Unknown")
        diff = q_difficulty.get(qid, "Unknown")

        topic_acc.setdefault(topic, {"correct": 0, "total": 0})
        topic_acc[topic]["total"] += 1
        if resp.is_correct:
            topic_acc[topic]["correct"] += 1

        diff_acc.setdefault(diff, {"correct": 0, "total": 0})
        diff_acc[diff]["total"] += 1
        if resp.is_correct:
            diff_acc[diff]["correct"] += 1

    topic_strength = sorted([
        {
            "topic": t,
            "accuracy_pct": round(d["correct"] / d["total"] * 100, 1) if d["total"] else None,
            "correct": d["correct"],
            "total": d["total"],
        }
        for t, d in topic_acc.items()
    ], key=lambda x: -(x["accuracy_pct"] or 0))

    difficulty_breakdown = []
    for diff in ["Easy", "Medium", "Hard"]:
        d = diff_acc.get(diff, {"correct": 0, "total": 0})
        difficulty_breakdown.append({
            "difficulty": diff,
            "accuracy_pct": round(d["correct"] / d["total"] * 100, 1) if d["total"] else None,
            "correct": d["correct"],
            "total": d["total"],
        })

    # Score trend
    score_trend = [
        {
            "submitted_at": sh["submitted_at"],
            "score_pct": sh["score_pct"],
            "assessment_name": sh["assessment_name"],
        }
        for sh in session_history
        if sh["submitted_at"]
    ]

    return {
        "coder_name": coder_name,
        "employee_id": sessions[0].employee_id if sessions else None,
        "total_assessments_taken": total_taken,
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "best_score": best_score,
        "worst_score": worst_score,
        "avg_time_seconds": avg_time,
        # The bar for the trend line. A coder's papers can carry different
        # bars, so say when they do rather than drawing one line as if it
        # governed every point.
        "default_pass_threshold": DEFAULT_PASS_THRESHOLD,
        "pass_thresholds_vary": len({
            ch_marks.get(s_.assessment_id, DEFAULT_PASS_THRESHOLD) for s_ in sessions
        }) > 1,
        "session_history": session_history,
        "score_trend": score_trend,
        "topic_strength": topic_strength,
        "difficulty_breakdown": difficulty_breakdown,
    }


def _build_response_meta(db: Session, f: Optional[AFilters] = None) -> tuple:
    """
    Build two dicts across the submitted sessions IN THE SELECTED WINDOW:
      qid_specialty: Dict[str, str]  — question_id -> specialty
      qid_topic:     Dict[str, str]  — question_id -> topic
    Returns (qid_specialty, qid_topic, submitted_session_ids)
    """
    base = _session_q(db, f) if f else db.query(AssessmentSession)
    submitted_sessions = base.filter(
        AssessmentSession.status == "submitted"
    ).all()
    submitted_session_ids = [s.id for s in submitted_sessions]

    # Collect unique slot ids to avoid re-parsing the same slot multiple times
    slot_ids = list(set(
        s.student_slot_id for s in submitted_sessions if s.student_slot_id
    ))
    slots = (
        db.query(GeneratedAssessmentStudent)
        .filter(GeneratedAssessmentStudent.id.in_(slot_ids))
        .all()
    ) if slot_ids else []

    qid_specialty: Dict[str, str] = {}
    qid_topic: Dict[str, str] = {}
    for slot in slots:
        qs = _parse_questions(slot.questions_json)
        for q in qs:
            qid = q.get("question_id", "")
            if qid:
                qid_specialty[qid] = q.get("specialty", "") or "Unknown"
                qid_topic[qid] = q.get("topic", "") or "Unknown"

    # sessions without a direct slot FK — fall back to assessment_id lookup
    sessions_without_slot = [s for s in submitted_sessions if not s.student_slot_id]
    fallback_assessment_ids = list(set(s.assessment_id for s in sessions_without_slot))
    if fallback_assessment_ids:
        fallback_slots = (
            db.query(GeneratedAssessmentStudent)
            .filter(GeneratedAssessmentStudent.assessment_id.in_(fallback_assessment_ids))
            .all()
        )
        for slot in fallback_slots:
            qs = _parse_questions(slot.questions_json)
            for q in qs:
                qid = q.get("question_id", "")
                if qid and qid not in qid_specialty:
                    qid_specialty[qid] = q.get("specialty", "") or "Unknown"
                    qid_topic[qid] = q.get("topic", "") or "Unknown"

    return qid_specialty, qid_topic, submitted_session_ids


@router.get("/analytics/by-specialty")
def analytics_by_specialty(db: Session = Depends(get_db), f: AFilters = Depends(filters)):
    """Aggregate accuracy and volume metrics grouped by specialty across all assessments."""
    qid_specialty, _qid_topic, submitted_session_ids = _build_response_meta(db, f)

    if not submitted_session_ids:
        return {"specialties": []}

    responses = (
        db.query(AssessmentResponse)
        .filter(AssessmentResponse.session_id.in_(submitted_session_ids))
        .all()
    )

    # Per-specialty accumulators
    spec_map: Dict[str, Dict] = {}
    for resp in responses:
        if resp.is_correct is None:
            continue
        sp = qid_specialty.get(resp.question_id, "Unknown")
        if sp not in spec_map:
            spec_map[sp] = {"correct": 0, "total": 0, "coders": set()}
        spec_map[sp]["total"] += 1
        if resp.is_correct:
            spec_map[sp]["correct"] += 1
        spec_map[sp]["coders"].add(resp.session_id)

    specialties = []
    for sp, d in spec_map.items():
        acc = round(d["correct"] / d["total"] * 100, 1) if d["total"] else None
        specialties.append({
            "specialty": sp,
            "accuracy_pct": acc,
            "correct": d["correct"],
            "total_responses": d["total"],
            "coder_count": len(d["coders"]),
        })

    specialties.sort(key=lambda x: -(x["accuracy_pct"] or 0))
    return {"specialties": specialties}


@router.get("/analytics/by-topic")
def analytics_by_topic(db: Session = Depends(get_db), f: AFilters = Depends(filters)):
    """Aggregate accuracy and volume metrics grouped by topic across all assessments."""
    qid_specialty, qid_topic, submitted_session_ids = _build_response_meta(db, f)

    if not submitted_session_ids:
        return {"topics": []}

    responses = (
        db.query(AssessmentResponse)
        .filter(AssessmentResponse.session_id.in_(submitted_session_ids))
        .all()
    )

    # Per-topic accumulators (also track specialty for context)
    topic_map: Dict[str, Dict] = {}
    for resp in responses:
        if resp.is_correct is None:
            continue
        tp = qid_topic.get(resp.question_id, "Unknown")
        sp = qid_specialty.get(resp.question_id, "Unknown")
        if tp not in topic_map:
            topic_map[tp] = {"correct": 0, "total": 0, "coders": set(), "specialties": set()}
        topic_map[tp]["total"] += 1
        if resp.is_correct:
            topic_map[tp]["correct"] += 1
        topic_map[tp]["coders"].add(resp.session_id)
        topic_map[tp]["specialties"].add(sp)

    topics = []
    for tp, d in topic_map.items():
        acc = round(d["correct"] / d["total"] * 100, 1) if d["total"] else None
        topics.append({
            "topic": tp,
            "accuracy_pct": acc,
            "correct": d["correct"],
            "total_responses": d["total"],
            "coder_count": len(d["coders"]),
            "specialties": sorted(d["specialties"]),
        })

    topics.sort(key=lambda x: -(x["accuracy_pct"] or 0))
    return {"topics": topics}


@router.get("/analytics/by-batch")
def analytics_by_batch(db: Session = Depends(get_db)):
    assessments = db.query(GeneratedAssessment).order_by(GeneratedAssessment.generated_at.desc()).all()
    all_results = db.query(AssessmentResult).all()
    result_map = {r.session_id: r for r in all_results}
    all_sessions = db.query(AssessmentSession).all()

    marks = _thresholds(db)
    batch_map: Dict[str, Dict] = {}
    for a in assessments:
        batch_key = a.batch_name or "Ungrouped"
        if batch_key not in batch_map:
            batch_map[batch_key] = {"assessments": [], "all_scores": [], "all_passes": [], "coders": set()}

        a_mark = marks.get(a.id, DEFAULT_PASS_THRESHOLD)
        a_sessions = [s for s in all_sessions if s.assessment_id == a.id and s.status == "submitted"]
        a_scores, a_passes = [], []
        for s in a_sessions:
            r = result_map.get(s.id)
            if r:
                a_scores.append(r.score_pct)
                # A batch can span assessments with different bars, so the pass
                # flag has to travel with the score — a bare list of numbers
                # cannot be re-judged later against one mark without lying.
                a_passes.append(r.score_pct >= a_mark)
                batch_map[batch_key]["coders"].add(coder_key(s))

        a_pass_rate = round(sum(a_passes) / len(a_passes) * 100, 1) if a_passes else None
        a_avg = round(sum(a_scores) / len(a_scores), 1) if a_scores else None
        batch_map[batch_key]["all_scores"].extend(a_scores)
        batch_map[batch_key].setdefault("all_passes", []).extend(a_passes)
        batch_map[batch_key]["assessments"].append({
            "assessment_id": a.id,
            "assessment_name": a.assessment_name,
            "generated_at": a.generated_at.isoformat() if a.generated_at else None,
            "submitted_count": len(a_scores),
            "pass_rate": a_pass_rate,
            "avg_score": a_avg,
        })

    batches = []
    for batch_name, d in batch_map.items():
        scores = d["all_scores"]
        batches.append({
            "batch_name": batch_name,
            "assessment_count": len(d["assessments"]),
            "total_coders": len(d["coders"]),
            "submitted_count": len(scores),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "pass_rate": (round(sum(d.get("all_passes", [])) / len(d["all_passes"]) * 100, 1)
                          if d.get("all_passes") else None),
            "assessments": d["assessments"],
        })

    batches.sort(key=lambda b: b["batch_name"] == "Ungrouped")  # Ungrouped last
    return {"batches": batches}


@router.get("/analytics/batch-drill/{batch_name}")
def analytics_batch_drill(batch_name: str, db: Session = Depends(get_db)):
    actual_batch = None if batch_name == "Ungrouped" else batch_name
    if actual_batch:
        assessments = db.query(GeneratedAssessment).filter(GeneratedAssessment.batch_name == actual_batch).all()
    else:
        assessments = db.query(GeneratedAssessment).filter(GeneratedAssessment.batch_name.is_(None)).all()

    if not assessments:
        raise HTTPException(status_code=404, detail="Batch not found")

    assessment_ids = [a.id for a in assessments]
    sessions = db.query(AssessmentSession).filter(
        AssessmentSession.assessment_id.in_(assessment_ids),
        AssessmentSession.status == "submitted"
    ).order_by(AssessmentSession.submitted_at.asc()).all()

    session_ids = [s.id for s in sessions]
    responses = db.query(AssessmentResponse).filter(AssessmentResponse.session_id.in_(session_ids)).all()
    results = db.query(AssessmentResult).filter(AssessmentResult.session_id.in_(session_ids)).all()
    result_map = {r.session_id: r for r in results}

    # Build qid→topic/specialty map
    slot_ids = list(set(s.student_slot_id for s in sessions if s.student_slot_id))
    slots = db.query(GeneratedAssessmentStudent).filter(GeneratedAssessmentStudent.id.in_(slot_ids)).all() if slot_ids else []
    fallback_slots = db.query(GeneratedAssessmentStudent).filter(GeneratedAssessmentStudent.assessment_id.in_(assessment_ids)).all()

    qid_topic: Dict[str, str] = {}
    qid_specialty: Dict[str, str] = {}
    for slot in list(slots) + list(fallback_slots):
        for q in _parse_questions(slot.questions_json):
            qid = q.get("question_id", "")
            if qid and qid not in qid_topic:
                qid_topic[qid] = q.get("topic", "") or "Unknown"
                qid_specialty[qid] = q.get("specialty", "") or "Unknown"

    # coder → topic accuracy
    coder_topic: Dict[str, Dict[str, Dict]] = {}
    coder_sessions: Dict[str, List] = {}

    session_map = {s.id: s for s in sessions}
    for resp in responses:
        if resp.is_correct is None:
            continue
        s = session_map.get(resp.session_id)
        if not s:
            continue
        coder = coder_key(s)
        topic = qid_topic.get(resp.question_id, "Unknown")
        coder_topic.setdefault(coder, {}).setdefault(topic, {"correct": 0, "total": 0})
        coder_topic[coder][topic]["total"] += 1
        if resp.is_correct:
            coder_topic[coder][topic]["correct"] += 1

    for s in sessions:
        r = result_map.get(s.id)
        if r:
            coder_sessions.setdefault(coder_key(s), []).append({
                "score_pct": r.score_pct,
                "submitted_at": r.submitted_at,
                "assessment_name": next((a.assessment_name for a in assessments if a.id == s.assessment_id), ""),
            })

    # All topics in this batch
    all_topics = sorted(set(qid_topic.values()))

    # Coder matrix rows
    coder_rows = []
    for coder, topic_data in coder_topic.items():
        row: Dict[str, Any] = {"coder_name": coder, "topics": {}}
        for topic in all_topics:
            d = topic_data.get(topic)
            row["topics"][topic] = round(d["correct"] / d["total"] * 100, 1) if d and d["total"] else None

        sess_list = coder_sessions.get(coder, [])
        if sess_list:
            sess_list_sorted = sorted(sess_list, key=lambda x: x["submitted_at"] or "")
            row["latest_score"] = round(sess_list_sorted[-1]["score_pct"], 1)
            row["first_score"] = round(sess_list_sorted[0]["score_pct"], 1)
            row["delta"] = round(row["latest_score"] - row["first_score"], 1) if len(sess_list_sorted) > 1 else None
            row["assessment_count"] = len(sess_list_sorted)
        else:
            row["latest_score"] = None
            row["first_score"] = None
            row["delta"] = None
            row["assessment_count"] = 0
        coder_rows.append(row)

    coder_rows.sort(key=lambda x: -(x["latest_score"] or 0))

    # Topic summary
    topic_summary = []
    for topic in all_topics:
        corrects, totals = 0, 0
        for coder, td in coder_topic.items():
            d = td.get(topic)
            if d:
                corrects += d["correct"]
                totals += d["total"]
        acc = round(corrects / totals * 100, 1) if totals else None
        topic_summary.append({
            "topic": topic,
            "accuracy_pct": acc,
            "correct": corrects,
            "total": totals,
        })

    weak_topics = [t for t in topic_summary if t["accuracy_pct"] is not None and t["accuracy_pct"] < 80]
    strong_topics = [t for t in topic_summary if t["accuracy_pct"] is not None and t["accuracy_pct"] >= 90]
    weak_topics.sort(key=lambda x: x["accuracy_pct"])
    strong_topics.sort(key=lambda x: -(x["accuracy_pct"] or 0))

    all_scores = [result_map[s.id].score_pct for s in sessions if s.id in result_map]
    # This view spans assessments, so each score keeps the bar it was judged on.
    topic_marks = _thresholds(db)
    all_passes = [result_map[s.id].score_pct >= topic_marks.get(s.assessment_id, DEFAULT_PASS_THRESHOLD)
                  for s in sessions if s.id in result_map]

    return {
        "batch_name": batch_name,
        "assessment_count": len(assessments),
        "total_coders": len(coder_topic),
        "submitted_count": len(session_ids),
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        "pass_rate": (round(sum(all_passes) / len(all_passes) * 100, 1)
                      if all_passes else None),
        "all_topics": all_topics,
        "coder_rows": coder_rows,
        "topic_summary": topic_summary,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "assessments": [{"id": a.id, "name": a.assessment_name, "generated_at": a.generated_at.isoformat() if a.generated_at else None} for a in assessments],
    }


@router.get("/analytics/coder-report.pdf")
def assessment_coder_report_pdf(
    coder_name: str,
    employee_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exclude_session_ids: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    import io
    data = analytics_coder(
        coder_name=coder_name,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        exclude_session_ids=exclude_session_ids,
        db=db,
    )
    if not data:
        raise HTTPException(status_code=404, detail="No assessment history found for this coder.")
    from services.pdf_report_service import generate_assessment_coder_report_pdf
    pdf_bytes = generate_assessment_coder_report_pdf(coder_name, data)
    safe_name = coder_name.replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(f"{safe_name}_Assessment_Report.pdf", "Assessment_Report.pdf"),
    )


@router.get("/analytics/batch-report.pdf")
def assessment_batch_report_pdf(batch_name: str, db: Session = Depends(get_db)):
    from fastapi.responses import StreamingResponse
    import io
    data = analytics_batch_drill(batch_name=batch_name, db=db)
    from services.pdf_report_service import generate_assessment_batch_report_pdf
    pdf_bytes = generate_assessment_batch_report_pdf(data)
    safe_name = batch_name.replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=content_disposition(f"{safe_name}_Batch_Report.pdf", "Assessment_Batch_Report.pdf"),
    )


@router.get("/analytics/batch-coder-reports.zip")
def assessment_batch_coder_reports_zip(batch_name: str, db: Session = Depends(get_db)):
    """Download a ZIP of individual coder PDF reports for every coder in a batch."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from services.pdf_report_service import generate_assessment_coder_report_pdf

    # Resolve batch to assessment IDs (mirrors analytics_batch_drill logic)
    actual_batch = None if batch_name == "Ungrouped" else batch_name
    if actual_batch:
        assessments = db.query(GeneratedAssessment).filter(
            GeneratedAssessment.batch_name == actual_batch
        ).all()
    else:
        assessments = db.query(GeneratedAssessment).filter(
            GeneratedAssessment.batch_name.is_(None)
        ).all()

    if not assessments:
        raise HTTPException(status_code=404, detail="Batch not found")

    assessment_ids = [a.id for a in assessments]
    sessions = db.query(AssessmentSession).filter(
        AssessmentSession.assessment_id.in_(assessment_ids),
        AssessmentSession.status == "submitted",
    ).all()

    # Identify by (name, employee_id): two coders sharing a name are two people,
    # and merging them into one PDF misattributes both.
    coders = sorted(
        {(s.coder_name, s.employee_id) for s in sessions},
        key=lambda c: (c[0], c[1] or ""),   # employee_id is nullable; None won't sort against str
    )
    if not coders:
        raise HTTPException(status_code=404, detail="No submitted sessions found in this batch.")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for coder_name, employee_id in coders:
            data = analytics_coder(
                coder_name=coder_name,
                employee_id=employee_id,
                batch_name=batch_name,
                db=db,
            )
            if not data:
                continue
            pdf_bytes = generate_assessment_coder_report_pdf(coder_name, data)
            safe_name = coder_name.replace(" ", "_")
            suffix = f"_{employee_id}" if employee_id else ""
            zf.writestr(f"{safe_name}{suffix}_Assessment_Report.pdf", pdf_bytes)

    zip_buf.seek(0)
    safe_batch = batch_name.replace(" ", "_").replace("/", "-")
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers=content_disposition(f"{safe_batch}_Coder_Reports.zip", "Coder_Reports.zip"),
    )


@router.get("/analytics/coder-matrix")
def analytics_coder_matrix(db: Session = Depends(get_db), f: AFilters = Depends(filters)):
    qid_specialty, _qid_topic, submitted_session_ids = _build_response_meta(db, f)
    if not submitted_session_ids:
        return {"coders": [], "specialties": []}

    sessions = db.query(AssessmentSession).filter(
        AssessmentSession.id.in_(submitted_session_ids)
    ).all()
    responses = db.query(AssessmentResponse).filter(
        AssessmentResponse.session_id.in_(submitted_session_ids)
    ).all()
    results = db.query(AssessmentResult).filter(
        AssessmentResult.session_id.in_(submitted_session_ids)
    ).all()

    session_map = {s.id: s for s in sessions}
    result_map = {r.session_id: r for r in results}

    # coder → specialty → {correct, total}
    coder_spec: Dict[str, Dict[str, Dict]] = {}
    coder_overall: Dict[str, List[float]] = {}

    for resp in responses:
        if resp.is_correct is None:
            continue
        s = session_map.get(resp.session_id)
        if not s:
            continue
        sp = qid_specialty.get(resp.question_id, "Unknown")
        coder_spec.setdefault(s.coder_name, {}).setdefault(sp, {"correct": 0, "total": 0})
        coder_spec[s.coder_name][sp]["total"] += 1
        if resp.is_correct:
            coder_spec[s.coder_name][sp]["correct"] += 1

    for s in sessions:
        r = result_map.get(s.id)
        if r:
            coder_overall.setdefault(s.coder_name, []).append(r.score_pct)

    all_specialties = sorted(set(sp for c in coder_spec.values() for sp in c.keys()))

    coders = []
    for coder, spec_data in coder_spec.items():
        row: Dict[str, Any] = {"coder_name": coder, "specialties": {}}
        for sp in all_specialties:
            d = spec_data.get(sp)
            row["specialties"][sp] = round(d["correct"] / d["total"] * 100, 1) if d and d["total"] else None
        scores = coder_overall.get(coder, [])
        row["avg_score"] = round(sum(scores) / len(scores), 1) if scores else None
        row["assessments_taken"] = len(scores)
        coders.append(row)

    coders.sort(key=lambda x: -(x["avg_score"] or 0))
    return {"coders": coders, "specialties": all_specialties}
