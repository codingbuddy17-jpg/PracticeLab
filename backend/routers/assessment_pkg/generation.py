"""
Assessment generation router.
Implements stratified, LRU-ordered, per-coder shuffled assessment generation.
Coders and session tokens are created in the same transaction as generation.
"""
import random
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentQuestion, AssessmentConfig,
    GeneratedAssessment, GeneratedAssessmentStudent,
    AssessmentSession,
)

router = APIRouter()

SESSION_EXPIRY_HOURS = 8


def _make_token(db: Session) -> str:
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):
        token = "ASM-" + "".join(random.choices(chars, k=8))
        if not db.query(AssessmentSession).filter(AssessmentSession.session_token == token).first():
            return token
    raise RuntimeError("Could not generate unique token")


class SpecialtyMixItem(BaseModel):
    specialty: str
    pct: float
    topic_filter: str = ""


class DifficultyMix(BaseModel):
    easy: float
    medium: float
    hard: float


class CoderItem(BaseModel):
    coder_name: str
    employee_id: Optional[str] = None


class GenerateRequest(BaseModel):
    assessment_name: str
    batch_name: Optional[str] = None
    coders: List[CoderItem]          # replaces student_count
    duration_minutes: int = 60       # per-session time limit
    total_questions: int
    specialty_mix: List[SpecialtyMixItem]
    difficulty_mode: str = "auto"    # "auto" | "manual"
    difficulty_mix: Optional[DifficultyMix] = None
    generated_by: str
    save_config: bool = True
    config_name: Optional[str] = None


def _shuffle(lst: list) -> list:
    """Fisher-Yates in-place shuffle, return same list."""
    for i in range(len(lst) - 1, 0, -1):
        j = random.randint(0, i)
        lst[i], lst[j] = lst[j], lst[i]
    return lst


def _stratified_pick(pool: List[AssessmentQuestion], target: int, difficulty_ratios: Dict[str, float]) -> List[AssessmentQuestion]:
    """
    Pick `target` questions from pool using stratified difficulty ratios.
    Uses cascade overflow: if a difficulty bucket runs short, the deficit
    cascades to Medium then Hard then Easy.
    """
    by_diff: Dict[str, List[AssessmentQuestion]] = {"Easy": [], "Medium": [], "Hard": []}
    for q in pool:
        if q.difficulty in by_diff:
            by_diff[q.difficulty].append(q)

    easy_n = round(target * difficulty_ratios.get("easy", 0))
    medium_n = round(target * difficulty_ratios.get("medium", 0))
    hard_n = target - easy_n - medium_n  # absorb rounding

    picks: List[AssessmentQuestion] = []
    accumulated_deficit = 0

    for diff, base_need, bucket in [
        ("Easy", easy_n, by_diff["Easy"]),
        ("Medium", medium_n, by_diff["Medium"]),
        ("Hard", hard_n, by_diff["Hard"]),
    ]:
        need = base_need + accumulated_deficit
        available = bucket[:need]
        shortfall = need - len(available)
        picks.extend(available)
        accumulated_deficit = max(0, shortfall)

    # If still short (total pool is smaller), just pad with whatever is left
    if len(picks) < target:
        used_ids = {q.id for q in picks}
        remainder = [q for q in pool if q.id not in used_ids]
        picks.extend(remainder[: target - len(picks)])

    return picks[:target]


def _shuffle_options(q: AssessmentQuestion) -> Dict[str, Any]:
    """
    Return a dict with options and the correct answer letter.
    If q.shuffle_options is False, options are kept in original A/B/C/D order.
    """
    if q.shuffle_options:
        correct_text = {
            "A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d,
        }[q.correct_answer]

        texts = [q.option_a, q.option_b, q.option_c, q.option_d]
        _shuffle(texts)

        letters = ["A", "B", "C", "D"]
        new_options = dict(zip(letters, texts))
        new_correct = next(letter for letter, text in new_options.items() if text == correct_text)
    else:
        new_options = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
        new_correct = q.correct_answer

    return {
        "question_id": q.question_id,
        "specialty": q.specialty,
        "question_text": q.question_text,
        "option_a": new_options["A"],
        "option_b": new_options["B"],
        "option_c": new_options["C"],
        "option_d": new_options["D"],
        "correct_answer": new_correct,
        "difficulty": q.difficulty,
        "topic": q.topic,
        "question_type": q.question_type,
    }


@router.get("/pool-preview")
def pool_preview(
    specialty: str = Query(..., description="Comma-separated specialty names"),
    topic_filter: Optional[str] = Query(default=None, description="Comma-separated per-specialty topic filters (matched by position)"),
    db: Session = Depends(get_db),
):
    specialties = [s.strip() for s in specialty.split(",") if s.strip()]
    topic_filters = [t.strip() for t in (topic_filter or "").split(",")] if topic_filter else []

    results = []
    for i, sp in enumerate(specialties):
        tf = topic_filters[i] if i < len(topic_filters) else ""
        q = db.query(
            AssessmentQuestion.difficulty,
            func.count(AssessmentQuestion.id),
        ).filter(
            AssessmentQuestion.specialty == sp,
            AssessmentQuestion.status == "Active",
        )
        if tf:
            q = q.filter(AssessmentQuestion.topic.ilike(f"%{tf}%"))
        rows = q.group_by(AssessmentQuestion.difficulty).all()
        counts = {"Easy": 0, "Medium": 0, "Hard": 0}
        for diff, cnt in rows:
            if diff in counts:
                counts[diff] = cnt
        results.append({
            "specialty": sp,
            "active_count": sum(counts.values()),
            "easy": counts["Easy"],
            "medium": counts["Medium"],
            "hard": counts["Hard"],
        })
    return results


@router.post("/generate")
def generate_assessment(req: GenerateRequest, db: Session = Depends(get_db)):
    # Validate
    total_pct = sum(item.pct for item in req.specialty_mix)
    if abs(total_pct - 1.0) > 0.01:
        raise HTTPException(status_code=400, detail=f"specialty_mix percentages must sum to 1.0, got {total_pct:.3f}")

    if req.difficulty_mode == "manual":
        if not req.difficulty_mix:
            raise HTTPException(status_code=400, detail="difficulty_mix required when difficulty_mode is manual")
        dm_sum = req.difficulty_mix.easy + req.difficulty_mix.medium + req.difficulty_mix.hard
        if abs(dm_sum - 1.0) > 0.01:
            raise HTTPException(status_code=400, detail=f"difficulty_mix must sum to 1.0, got {dm_sum:.3f}")

    coders = [c for c in req.coders if c.coder_name.strip()]
    if not coders:
        raise HTTPException(status_code=400, detail="At least one coder is required")
    if req.total_questions < 1:
        raise HTTPException(status_code=400, detail="total_questions must be >= 1")
    if req.duration_minutes < 5 or req.duration_minutes > 480:
        raise HTTPException(status_code=400, detail="duration_minutes must be between 5 and 480")

    # Build combined question list for all specialties
    combined: List[AssessmentQuestion] = []
    specialty_count = len(req.specialty_mix)

    for idx, item in enumerate(req.specialty_mix):
        # Last specialty absorbs remainder
        if idx == specialty_count - 1:
            target_count = req.total_questions - len(combined)
        else:
            target_count = round(req.total_questions * item.pct)

        # Fetch active questions for this specialty
        q = db.query(AssessmentQuestion).filter(
            AssessmentQuestion.specialty == item.specialty,
            AssessmentQuestion.status == "Active",
        )
        if item.topic_filter:
            topics = [t.strip() for t in item.topic_filter.split(",") if t.strip()]
            if len(topics) == 1:
                q = q.filter(AssessmentQuestion.topic.ilike(f"%{topics[0]}%"))
            elif topics:
                from sqlalchemy import or_
                q = q.filter(or_(*[AssessmentQuestion.topic.ilike(f"%{t}%") for t in topics]))

        pool: List[AssessmentQuestion] = q.all()

        # LRU sort: oldest last_used_at first, nulls first
        _epoch = datetime.min.replace(tzinfo=timezone.utc)
        pool.sort(key=lambda x: (x.last_used_at is not None, x.last_used_at or _epoch))

        # Compute difficulty ratios
        if req.difficulty_mode == "auto":
            total_pool = len(pool)
            if total_pool == 0:
                ratios = {"easy": 0.33, "medium": 0.34, "hard": 0.33}
            else:
                easy_c = sum(1 for q2 in pool if q2.difficulty == "Easy")
                medium_c = sum(1 for q2 in pool if q2.difficulty == "Medium")
                hard_c = sum(1 for q2 in pool if q2.difficulty == "Hard")
                ratios = {
                    "easy": easy_c / total_pool,
                    "medium": medium_c / total_pool,
                    "hard": hard_c / total_pool,
                }
        else:
            ratios = {
                "easy": req.difficulty_mix.easy,
                "medium": req.difficulty_mix.medium,
                "hard": req.difficulty_mix.hard,
            }

        picked = _stratified_pick(pool, target_count, ratios)
        combined.extend(picked)

    if not combined:
        raise HTTPException(status_code=400, detail="No questions available for the requested specialty/topic mix")

    # Update last_used_at on all selected questions
    now = datetime.now(timezone.utc)
    used_ids = [q.id for q in combined]
    db.query(AssessmentQuestion).filter(AssessmentQuestion.id.in_(used_ids)).update(
        {"last_used_at": now}, synchronize_session=False
    )

    # Save config if requested
    config_id = None
    if req.save_config:
        cfg = AssessmentConfig(
            name=req.config_name or req.assessment_name,
            total_questions=req.total_questions,
            student_count=len(coders),
            specialty_mix=[item.dict() for item in req.specialty_mix],
            difficulty_mode=req.difficulty_mode,
            difficulty_mix=req.difficulty_mix.dict() if req.difficulty_mix else None,
            created_by=req.generated_by,
        )
        db.add(cfg)
        db.flush()
        config_id = cfg.id

    # Save GeneratedAssessment
    assessment = GeneratedAssessment(
        config_id=config_id,
        assessment_name=req.assessment_name,
        batch_name=req.batch_name,
        student_count=len(coders),
        generated_by=req.generated_by,
    )
    db.add(assessment)
    db.flush()

    # Generate one shuffled question set per coder + mint session token
    expires_at = now + timedelta(hours=SESSION_EXPIRY_HOURS)
    sessions_created = []

    for coder in coders:
        student_questions = list(combined)
        _shuffle(student_questions)
        shuffled_with_options = [_shuffle_options(q) for q in student_questions]

        student_row = GeneratedAssessmentStudent(
            assessment_id=assessment.id,
            student_label=coder.coder_name.strip(),
            questions_json=shuffled_with_options,
        )
        db.add(student_row)
        db.flush()

        token = _make_token(db)
        session = AssessmentSession(
            session_token=token,
            assessment_id=assessment.id,
            student_slot_id=student_row.id,
            coder_name=coder.coder_name.strip(),
            employee_id=coder.employee_id.strip() if coder.employee_id else None,
            duration_minutes=req.duration_minutes,
            expires_at=expires_at,
            status="pending",
        )
        db.add(session)
        sessions_created.append({
            "coder_name": coder.coder_name.strip(),
            "employee_id": coder.employee_id,
            "session_token": token,
        })

    db.commit()

    return {
        "assessment_id": assessment.id,
        "assessment_name": req.assessment_name,
        "coder_count": len(coders),
        "total_questions": len(combined),
        "duration_minutes": req.duration_minutes,
        "expires_at": expires_at.isoformat(),
        "sessions": sessions_created,
        "config_id": config_id,
        "generated_at": now.isoformat(),
    }
