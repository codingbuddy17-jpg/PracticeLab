"""
Assessment generation router.
Implements stratified, LRU-ordered, per-student shuffled assessment generation.
"""
import random
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import AssessmentQuestion, AssessmentConfig, GeneratedAssessment, GeneratedAssessmentStudent

router = APIRouter()


class SpecialtyMixItem(BaseModel):
    specialty: str
    pct: float
    topic_filter: str = ""


class DifficultyMix(BaseModel):
    easy: float
    medium: float
    hard: float


class GenerateRequest(BaseModel):
    assessment_name: str
    student_count: int
    total_questions: int
    specialty_mix: List[SpecialtyMixItem]
    difficulty_mode: str = "auto"   # "auto" | "manual"
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
    deficit = 0

    for diff, need, bucket in [
        ("Easy", easy_n, by_diff["Easy"]),
        ("Medium", medium_n + deficit, by_diff["Medium"]),
        ("Hard", hard_n, by_diff["Hard"]),
    ]:
        available = bucket[:need + deficit] if diff != "Easy" else bucket[:need]
        shortfall = (need if diff == "Easy" else need + deficit) - len(available)
        picks.extend(available)
        deficit = max(0, shortfall)

    # If still short (total pool is smaller), just pad with whatever is left
    if len(picks) < target:
        used_ids = {q.id for q in picks}
        remainder = [q for q in pool if q.id not in used_ids]
        picks.extend(remainder[: target - len(picks)])

    return picks[:target]


def _shuffle_options(q: AssessmentQuestion) -> Dict[str, Any]:
    """
    Return a dict with shuffled A/B/C/D options and the new correct answer letter.
    """
    orig_options = {
        "A": q.option_a,
        "B": q.option_b,
        "C": q.option_c,
        "D": q.option_d,
    }
    correct_text = orig_options[q.correct_answer]

    letters = ["A", "B", "C", "D"]
    texts = [q.option_a, q.option_b, q.option_c, q.option_d]
    _shuffle(texts)

    new_options = dict(zip(letters, texts))
    new_correct = next(letter for letter, text in new_options.items() if text == correct_text)

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
    # Validate specialty_mix sums to 1.0 ± 0.01
    total_pct = sum(item.pct for item in req.specialty_mix)
    if abs(total_pct - 1.0) > 0.01:
        raise HTTPException(status_code=400, detail=f"specialty_mix percentages must sum to 1.0, got {total_pct:.3f}")

    if req.difficulty_mode == "manual":
        if not req.difficulty_mix:
            raise HTTPException(status_code=400, detail="difficulty_mix required when difficulty_mode is manual")
        dm_sum = req.difficulty_mix.easy + req.difficulty_mix.medium + req.difficulty_mix.hard
        if abs(dm_sum - 1.0) > 0.01:
            raise HTTPException(status_code=400, detail=f"difficulty_mix must sum to 1.0, got {dm_sum:.3f}")

    if req.student_count < 1:
        raise HTTPException(status_code=400, detail="student_count must be >= 1")
    if req.total_questions < 1:
        raise HTTPException(status_code=400, detail="total_questions must be >= 1")

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
            q = q.filter(AssessmentQuestion.topic.ilike(f"%{item.topic_filter}%"))

        pool: List[AssessmentQuestion] = q.all()

        # LRU sort: oldest last_used_at first, nulls first
        pool.sort(key=lambda x: (x.last_used_at is not None, x.last_used_at or datetime.min))

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
            student_count=req.student_count,
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
        student_count=req.student_count,
        generated_by=req.generated_by,
    )
    db.add(assessment)
    db.flush()

    # Generate per-student shuffled question sets
    student_summaries = []
    for i in range(req.student_count):
        student_label = f"Student_{i + 1:02d}"
        student_questions = list(combined)
        _shuffle(student_questions)
        shuffled_with_options = [_shuffle_options(q) for q in student_questions]

        student_row = GeneratedAssessmentStudent(
            assessment_id=assessment.id,
            student_label=student_label,
            questions_json=shuffled_with_options,
        )
        db.add(student_row)
        student_summaries.append(student_label)

    db.commit()

    return {
        "assessment_id": assessment.id,
        "assessment_name": req.assessment_name,
        "student_count": req.student_count,
        "total_questions": len(combined),
        "students": student_summaries,
        "config_id": config_id,
        "generated_at": now.isoformat(),
    }
