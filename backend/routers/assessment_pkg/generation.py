"""
Assessment generation router.
Implements stratified, LRU-ordered, per-coder shuffled assessment generation.
Coders and session tokens are created in the same transaction as generation.
"""
import json
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
from services.randomisation_stats import compute_randomisation_stats

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


class StandaloneQuestion(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str          # A / B / C / D
    difficulty: str = "Medium"  # Easy / Medium / Hard
    topic: str = ""
    shuffle_options: bool = True


class GenerateRequest(BaseModel):
    assessment_name: str
    batch_name: Optional[str] = None
    coders: List[CoderItem]
    duration_minutes: int = 60
    total_questions: int
    specialty_mix: List[SpecialtyMixItem] = []
    difficulty_mode: str = "auto"
    difficulty_mix: Optional[DifficultyMix] = None
    generated_by: str
    save_config: bool = True
    config_name: Optional[str] = None
    randomise: bool = True                                    # per-coder independent sampling
    # Generation refuses a mix it cannot fill. Set this to accept a short paper
    # knowingly, which is a trainer's call to make — but never a silent default.
    allow_short_pool: bool = False
    # The bar this paper is judged against. Omitted means the platform default.
    pass_threshold: Optional[int] = None
    show_results_to_coder: bool = False
    standalone_questions: Optional[List[StandaloneQuestion]] = None  # standalone mode


def _shuffle(lst: list) -> list:
    """Fisher-Yates in-place shuffle, return same list."""
    for i in range(len(lst) - 1, 0, -1):
        j = random.randint(0, i)
        lst[i], lst[j] = lst[j], lst[i]
    return lst


def _per_coder_pool(pool: List[AssessmentQuestion]) -> List[AssessmentQuestion]:
    """
    Return a per-coder randomised copy of the pool.
    Mirrors the VBA approach: Fisher-Yates shuffle first (so questions with the
    same last_used_at are in a different random order each call), then stable
    LRU sort (oldest / never-used first).  This gives each coder a unique random
    draw while still preferring questions that haven't been used recently.
    """
    randomised = list(pool)
    _shuffle(randomised)                                       # random within tiers
    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    randomised.sort(key=lambda x: (x.last_used_at is not None,
                                   x.last_used_at or _epoch))  # LRU priority preserved
    return randomised


def _stratified_pick(pool: List[AssessmentQuestion], target: int, difficulty_ratios: Dict[str, float]) -> List[AssessmentQuestion]:
    """
    Pick `target` questions from pool using stratified difficulty ratios.
    Pool must already be per-coder randomised (call _per_coder_pool first).
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

    # If still short (total pool is smaller), pad with whatever is left
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
    raw = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
    # Only the options this question actually has. A True/False question fills
    # A and B, so shuffling all four would move a blank into a live slot and
    # show the coder an empty choice.
    present = [L for L in "ABCD" if (raw[L] or "").strip()]

    if q.shuffle_options and len(present) > 1:
        correct_text = raw[q.correct_answer]
        texts = [raw[L] for L in present]
        _shuffle(texts)
        new_options = {L: t for L, t in zip(present, texts)}
        new_correct = next(letter for letter, text in new_options.items() if text == correct_text)
    else:
        new_options = {L: raw[L] for L in present}
        new_correct = q.correct_answer

    # Absent options stay absent rather than becoming empty strings, so the
    # coder-facing screen can tell "no such option" from "an option with no text".
    for L in "ABCD":
        new_options.setdefault(L, None)

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
    specialty: List[str] = Query(..., description="One specialty per row, repeated"),
    topic_filter: List[str] = Query(default=[], description="One filter per row, repeated, matched by position"),
    db: Session = Depends(get_db),
):
    """
    What each row of the specialty mix can draw on.

    Repeated parameters rather than one comma-joined string. A row's own topic
    filter may itself list several topics meaning "any of these", so joining
    the rows with commas made the two levels indistinguishable: a row filtering
    "Sepsis, Pneumonia" donated "Pneumonia" to the NEXT specialty and counted
    only Sepsis for itself. The preview then disagreed with the generator about
    whether the pool was sufficient, which is the one thing a preview must
    never do.
    """
    specialties = [s.strip() for s in specialty if s.strip()]
    topic_filters = [t.strip() for t in topic_filter]

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
            topics = [t.strip() for t in tf.split(",") if t.strip()]
            if len(topics) == 1:
                q = q.filter(AssessmentQuestion.topic.ilike(f"%{topics[0]}%"))
            elif topics:
                from sqlalchemy import or_
                q = q.filter(or_(*[AssessmentQuestion.topic.ilike(f"%{t}%") for t in topics]))
        rows = q.group_by(AssessmentQuestion.difficulty).all()
        counts = {"Easy": 0, "Medium": 0, "Hard": 0}
        for diff, cnt in rows:
            if diff in counts:
                counts[diff] = cnt
        # Every topic this specialty actually has, UNFILTERED, so the screen can
        # offer them. A trainer typing a topic from memory has no way to know
        # what the bank calls it — "Sepsis" vs "Sepsis & Shock" returns nothing
        # and looks like an empty pool rather than a spelling mismatch.
        topic_rows = db.query(
            AssessmentQuestion.topic,
            func.count(AssessmentQuestion.id),
        ).filter(
            AssessmentQuestion.specialty == sp,
            AssessmentQuestion.status == "Active",
        ).group_by(AssessmentQuestion.topic).all()

        results.append({
            "specialty": sp,
            "active_count": sum(counts.values()),
            "easy": counts["Easy"],
            "medium": counts["Medium"],
            "hard": counts["Hard"],
            # Alphabetical, not by count: this is a list you scan for a name
            # you already have in mind, and frequency order makes that a hunt.
            "topics": sorted(
                [{"topic": t, "count": c} for t, c in topic_rows if t and t.strip()],
                key=lambda x: x["topic"].casefold(),
            ),
        })
    return results


@router.post("/generate")
def generate_assessment(req: GenerateRequest, db: Session = Depends(get_db)):
    is_standalone = bool(req.standalone_questions)

    # ── Common validation ──────────────────────────────────────────────────────
    coders = [c for c in req.coders if c.coder_name.strip()]
    if not coders:
        raise HTTPException(status_code=400, detail="At least one coder is required")

    # Two coders who share an identity are indistinguishable everywhere
    # downstream: analytics groups on employee id falling back to name, so a
    # repeated pair merges two people's results into one row and neither can be
    # coached from it. Same name with DIFFERENT employee ids is fine — that is
    # two real people.
    seen_keys: Dict[str, str] = {}
    for c in coders:
        name = c.coder_name.strip()
        key = (c.employee_id or "").strip() or name.casefold()
        if key in seen_keys:
            raise HTTPException(
                status_code=400,
                detail=(f"'{name}' appears twice with the same identity. "
                        "Give each coder a distinct employee ID, or remove the duplicate — "
                        "results for repeated coders cannot be told apart afterwards."),
            )
        seen_keys[key] = name

    # A repeated specialty splits one pool across two rows, so each row's
    # shortfall check passes while the pool is drawn from twice.
    if not req.standalone_questions:
        seen_specs = set()
        for item in req.specialty_mix:
            if item.specialty in seen_specs:
                raise HTTPException(
                    status_code=400,
                    detail=(f"'{item.specialty}' appears more than once in the mix. "
                            "Combine them into one row and set its percentage."),
                )
            seen_specs.add(item.specialty)
    if req.total_questions < 1:
        raise HTTPException(status_code=400, detail="total_questions must be >= 1")
    if req.duration_minutes < 5 or req.duration_minutes > 480:
        raise HTTPException(status_code=400, detail="duration_minutes must be between 5 and 480")

    now = datetime.now(timezone.utc)

    # ── Build question pool ────────────────────────────────────────────────────
    if is_standalone:
        # Standalone: use the provided questions directly — never touch the question bank
        if len(req.standalone_questions) < req.total_questions:
            raise HTTPException(
                status_code=400,
                detail=f"Only {len(req.standalone_questions)} standalone questions provided but {req.total_questions} requested"
            )
        # Convert StandaloneQuestion → dict matching _shuffle_options / questions_json shape
        # Standalone questions never enter the bank, so they have no bank ID.
        # They still need one: submit scoring builds a {question_id: answer} map,
        # and a shared null id collapsed every question into a single entry, so
        # each response was graded against whichever question landed last.
        # The index is stable for the life of the assessment, which is all the
        # map and the saved responses require.
        def _sq_to_dict(sq: StandaloneQuestion, idx: int) -> Dict[str, Any]:
            return {
                "question_id": f"SA-{idx + 1:04d}",   # fits question_id String(20)
                "question_text": sq.question_text,
                "option_a": sq.option_a,
                "option_b": sq.option_b,
                "option_c": sq.option_c,
                "option_d": sq.option_d,
                "correct_answer": sq.correct_answer.upper(),
                "difficulty": sq.difficulty,
                "topic": sq.topic,
                "shuffle_options": sq.shuffle_options,
            }
        standalone_pool = [_sq_to_dict(sq, i) for i, sq in enumerate(req.standalone_questions)]
        specialty_pools = None   # not used in standalone path
    else:
        # Standard: validate specialty mix and build DB pools
        total_pct = sum(item.pct for item in req.specialty_mix)
        if abs(total_pct - 1.0) > 0.01:
            raise HTTPException(status_code=400, detail=f"specialty_mix percentages must sum to 1.0, got {total_pct:.3f}")
        if req.difficulty_mode == "manual":
            if not req.difficulty_mix:
                raise HTTPException(status_code=400, detail="difficulty_mix required when difficulty_mode is manual")
            dm_sum = req.difficulty_mix.easy + req.difficulty_mix.medium + req.difficulty_mix.hard
            if abs(dm_sum - 1.0) > 0.01:
                raise HTTPException(status_code=400, detail=f"difficulty_mix must sum to 1.0, got {dm_sum:.3f}")

        _epoch = datetime.min.replace(tzinfo=timezone.utc)
        specialty_pools: List[Dict[str, Any]] = []
        specialty_count = len(req.specialty_mix)

        for idx, item in enumerate(req.specialty_mix):
            target_count = (
                req.total_questions - sum(p["target"] for p in specialty_pools)
                if idx == specialty_count - 1
                else round(req.total_questions * item.pct)
            )
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

            if req.difficulty_mode == "auto":
                total_pool = len(pool)
                ratios: Dict[str, float] = (
                    {"easy": 0.33, "medium": 0.34, "hard": 0.33} if total_pool == 0
                    else {
                        "easy":   sum(1 for q2 in pool if q2.difficulty == "Easy")   / total_pool,
                        "medium": sum(1 for q2 in pool if q2.difficulty == "Medium") / total_pool,
                        "hard":   sum(1 for q2 in pool if q2.difficulty == "Hard")   / total_pool,
                    }
                )
            else:
                ratios = {"easy": req.difficulty_mix.easy, "medium": req.difficulty_mix.medium, "hard": req.difficulty_mix.hard}

            specialty_pools.append({"pool": pool, "target": target_count, "ratios": ratios})

        # Sufficiency, per specialty — not merely "some pool is non-empty".
        # A mix of 50% IP-DRG / 50% E&M with 40 IP-DRG questions and 2 E&M ones
        # passed the old check and quietly produced a paper that was almost all
        # IP-DRG. The trainer only discovered the imbalance after coders sat it.
        shortfalls = [
            {
                "specialty": item.specialty,
                "topic_filter": item.topic_filter or None,
                "requested": p["target"],
                "available": len(p["pool"]),
            }
            for item, p in zip(req.specialty_mix, specialty_pools)
            if len(p["pool"]) < p["target"]
        ]
        if shortfalls and not req.allow_short_pool:
            lines = "; ".join(
                f"{sf['specialty']}"
                + (f" (topic: {sf['topic_filter']})" if sf["topic_filter"] else "")
                + f" needs {sf['requested']} but has {sf['available']}"
                for sf in shortfalls
            )
            raise HTTPException(status_code=400, detail={
                "message": (
                    f"Not enough questions to build this assessment: {lines}. "
                    "Add questions, widen the topic filter, lower the question count, "
                    "or re-submit with allow_short_pool to generate a shorter paper."
                ),
                "shortfalls": shortfalls,
            })

        if not any(p["pool"] for p in specialty_pools):
            raise HTTPException(status_code=400, detail="No questions available for the requested specialty/topic mix")


    # ── Save config (standard mode only) ──────────────────────────────────────
    config_id = None
    if not is_standalone and req.save_config:
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

    # ── Save GeneratedAssessment ───────────────────────────────────────────────
    assessment = GeneratedAssessment(
        config_id=config_id,
        assessment_name=req.assessment_name,
        batch_name=req.batch_name,
        student_count=len(coders),
        generated_by=req.generated_by,
        pass_threshold=req.pass_threshold,
        show_results_to_coder=req.show_results_to_coder,
        is_standalone=is_standalone,
    )
    db.add(assessment)
    db.flush()

    # ── Per-coder question assignment ─────────────────────────────────────────
    expires_at = now + timedelta(hours=SESSION_EXPIRY_HOURS)
    sessions_created = []
    coder_question_sets: Dict[str, set] = {}
    served_question_ids: set = set()   # bank IDs actually assigned, for LRU rotation

    # Shared pool (randomise=False): pick questions once, but shuffle order + options per coder
    shared_pool_base: Optional[List[Any]] = None
    if not req.randomise:
        if is_standalone:
            shared_pool_base = list(standalone_pool[:req.total_questions])
        else:
            shared_combined: List[AssessmentQuestion] = []
            for p in specialty_pools:
                picked = _stratified_pick(p["pool"], p["target"], p["ratios"])
                shared_combined.extend(picked)
            shared_pool_base = shared_combined
            served_question_ids.update(q.id for q in shared_combined)

    for coder in coders:
        if req.randomise:
            if is_standalone:
                # Shuffle the standalone pool independently per coder, slice to total_questions
                coder_pool = list(standalone_pool)
                _shuffle(coder_pool)
                questions_for_coder = coder_pool[:req.total_questions]
                coder_question_sets[coder.coder_name.strip()] = {
                    q["question_id"] for q in questions_for_coder
                }
            else:
                coder_combined: List[AssessmentQuestion] = []
                for p in specialty_pools:
                    coder_pool_db = _per_coder_pool(p["pool"])
                    picked = _stratified_pick(coder_pool_db, p["target"], p["ratios"])
                    coder_combined.extend(picked)
                if not coder_combined:
                    raise HTTPException(status_code=400, detail="No questions available for the requested specialty/topic mix")
                coder_question_sets[coder.coder_name.strip()] = {q.id for q in coder_combined}
                served_question_ids.update(q.id for q in coder_combined)
                _shuffle(coder_combined)
                questions_for_coder = [_shuffle_options(q) for q in coder_combined]
        else:
            # Same question set — but independently shuffle question order and options per coder
            coder_copy = list(shared_pool_base)
            _shuffle(coder_copy)
            if is_standalone:
                questions_for_coder = coder_copy
            else:
                questions_for_coder = [_shuffle_options(q) for q in coder_copy]

        student_row = GeneratedAssessmentStudent(
            assessment_id=assessment.id,
            student_label=coder.coder_name.strip(),
            questions_json=questions_for_coder,
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

    # ── Question rotation ─────────────────────────────────────────────────────
    # Age only the questions a coder actually received. Stamping the whole
    # eligible pool made every question equally "recently used", which is the
    # same as having no rotation at all.
    if served_question_ids:
        db.query(AssessmentQuestion).filter(
            AssessmentQuestion.id.in_(served_question_ids)
        ).update({"last_used_at": now}, synchronize_session=False)

    # ── Randomisation stats ────────────────────────────────────────────────────
    if not req.randomise:
        rand_stats = {"avg_uniqueness_pct": 0.0,
                      "note": "Randomisation disabled — all coders received the same question set"}
    elif coder_question_sets:
        # Measured from the sets actually assigned, standalone included.
        #
        # Standalone used to be handed invented ranges — set(range(i*n, (i+1)*n))
        # per coder — which are disjoint BY CONSTRUCTION. It therefore reported
        # flawless uniqueness for five coders drawing five questions from a pool
        # of six, whose papers are necessarily near-identical. A statistic that
        # cannot report a problem is worse than none, because the trainer
        # believes it.
        pool_size = (len(standalone_pool) if is_standalone
                     else sum(len(p["pool"]) for p in specialty_pools))
        rand_stats = compute_randomisation_stats(coder_question_sets, pool_size)
    else:
        rand_stats = {}
    assessment.randomisation_stats = rand_stats

    db.commit()

    # What each coder was ACTUALLY given. The response reported the number
    # REQUESTED, so a 6-question paper drawn from a pool of 2 came back saying
    # 6 — the trainer sees the size they asked for and hands out a test a third
    # of that length. Reporting the request as the result is the one thing this
    # response must not do.
    def _n(raw):
        try:
            v = json.loads(raw) if isinstance(raw, str) else (raw or [])
            return len(v) if isinstance(v, list) else 0
        except Exception:
            return 0

    served_counts = {_n(st.questions_json) for st in assessment.students} or set()
    actual_questions = min(served_counts) if served_counts else req.total_questions

    warnings: List[str] = []
    if actual_questions < req.total_questions:
        warnings.append(
            f"{req.total_questions} questions requested but the pool held only "
            f"{actual_questions} — each coder received {actual_questions}."
        )

    return {
        "assessment_id": assessment.id,
        "assessment_name": req.assessment_name,
        "coder_count": len(coders),
        "total_questions": actual_questions,
        "requested_questions": req.total_questions,
        "warnings": warnings,
        "duration_minutes": req.duration_minutes,
        "expires_at": expires_at.isoformat(),
        "sessions": sessions_created,
        "config_id": config_id,
        "generated_at": now.isoformat(),
        "randomisation_stats": rand_stats,
        "is_standalone": is_standalone,
    }
