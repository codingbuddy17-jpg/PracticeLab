"""Analytics endpoints for the Assessment module."""
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentSession, AssessmentResponse, AssessmentResult,
    GeneratedAssessment, GeneratedAssessmentStudent,
)

router = APIRouter()

PASS_THRESHOLD = 90.0


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
def analytics_overview(db: Session = Depends(get_db)):
    """High-level KPIs across all assessments."""
    total_assessments = db.query(GeneratedAssessment).count()

    all_sessions = db.query(AssessmentSession).all()
    total_sessions = len(all_sessions)
    submitted_sessions = [s for s in all_sessions if s.status == "submitted"]
    expired_sessions = [s for s in all_sessions if s.status == "expired"]
    total_submitted = len(submitted_sessions)

    # Pass rate
    results = db.query(AssessmentResult).all()
    passed = sum(1 for r in results if r.score_pct >= PASS_THRESHOLD)
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
        sessions_with_slots = (
            db.query(AssessmentSession)
            .filter(AssessmentSession.id.in_(submitted_session_ids),
                    AssessmentSession.student_slot_id.isnot(None))
            .all()
        )
        slot_ids = list(set(s.student_slot_id for s in sessions_with_slots if s.student_slot_id))
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

    # Per-assessment pass rates for bar chart (last 10 assessments with results)
    assessments = (
        db.query(GeneratedAssessment)
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
        a_passed = sum(1 for r in a_results if r.score_pct >= PASS_THRESHOLD)
        per_assessment.append({
            "assessment_id": a.id,
            "assessment_name": a.assessment_name,
            "pass_rate": round(a_passed / len(a_results) * 100, 1),
            "submitted_count": len(a_results),
        })

    # Unique coders assessed
    unique_coders = len(set(s.coder_name for s in submitted_sessions))

    return {
        "total_assessments": total_assessments,
        "total_sessions": total_sessions,
        "total_submitted": total_submitted,
        "unique_coders_assessed": unique_coders,
        "overall_pass_rate": overall_pass_rate,
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

    # Per-coder table
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
                "pass_fail": "PASS" if r.score_pct >= PASS_THRESHOLD else "FAIL",
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            })
    coder_rows.sort(key=lambda x: -x["score_pct"])

    # Stats
    passed_count = sum(1 for sc in results_list if sc >= PASS_THRESHOLD)
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
    db: Session = Depends(get_db),
):
    """All submitted sessions for a coder across all assessments."""
    q = db.query(AssessmentSession).filter(
        AssessmentSession.coder_name == coder_name,
        AssessmentSession.status == "submitted",
    )
    if employee_id:
        q = q.filter(AssessmentSession.employee_id == employee_id)
    sessions = q.order_by(AssessmentSession.submitted_at.asc()).all()

    if not sessions:
        return None

    # Per-session history
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
            "pass_fail": "PASS" if score >= PASS_THRESHOLD else "FAIL",
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
        "session_history": session_history,
        "score_trend": score_trend,
        "topic_strength": topic_strength,
        "difficulty_breakdown": difficulty_breakdown,
    }


def _build_response_meta(db: Session) -> tuple:
    """
    Build two dicts across ALL submitted sessions:
      qid_specialty: Dict[str, str]  — question_id -> specialty
      qid_topic:     Dict[str, str]  — question_id -> topic
    Returns (qid_specialty, qid_topic, submitted_session_ids)
    """
    submitted_sessions = db.query(AssessmentSession).filter(
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
                qid_specialty[qid] = q.get("specialty", "Unknown")
                qid_topic[qid] = q.get("topic", "Unknown")

    return qid_specialty, qid_topic, submitted_session_ids


@router.get("/analytics/by-specialty")
def analytics_by_specialty(db: Session = Depends(get_db)):
    """Aggregate accuracy and volume metrics grouped by specialty across all assessments."""
    qid_specialty, _qid_topic, submitted_session_ids = _build_response_meta(db)

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
def analytics_by_topic(db: Session = Depends(get_db)):
    """Aggregate accuracy and volume metrics grouped by topic across all assessments."""
    qid_specialty, qid_topic, submitted_session_ids = _build_response_meta(db)

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
