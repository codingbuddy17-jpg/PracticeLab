"""
Assessment Question Bank router.
Handles upload, listing, editing, status changes, template download, pool preview.
"""
import io
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from database import get_db
from models import AssessmentQuestion
from config import settings

router = APIRouter()

SPECIALTY_PREFIX = {
    "ICD10CM": "ICDX",
    "Surgery": "SURG",
    "ED Facility": "EDFC",
    "ED Profee": "EDPF",
    "Ancillary": "ANCL",
    "IP-DRG": "IPDR",
    "E&M": "EMC",
    "E&M - Multispecialty": "EMMS",
    "IVR": "IVR",
    "Anesthesia": "ANES",
}

VALID_SPECIALTIES = set(SPECIALTY_PREFIX.keys())
VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}
VALID_ANSWERS = {"A", "B", "C", "D"}
VALID_TYPES = {"Conceptual", "Scenario", "Rule-based"}

TEMPLATE_HEADERS = [
    "Question_ID", "Question_Text", "Option_A", "Option_B", "Option_C", "Option_D",
    "Correct_Answer", "Difficulty", "Topic", "Question_Type", "Active_Status",
]

SAMPLE_ROWS: dict = {
    "ICD10CM": [
        ["", "A patient is diagnosed with Type 2 diabetes mellitus with diabetic chronic kidney disease, stage 3. What is the correct ICD-10-CM code?",
         "E11.22", "E11.65", "E13.22", "E11.29", "A", "Easy", "Diabetes", "Conceptual", "Active"],
        ["", "Acute appendicitis without abscess, without peritonitis. Select the correct code.",
         "K35.80", "K35.2", "K37", "K35.89", "A", "Easy", "Abdominal", "Conceptual", "Active"],
        ["", "A patient has essential hypertension and chronic kidney disease stage 3. How should this be coded?",
         "I12.9 and N18.3", "I10 and N18.3", "I12.9 alone", "I10 alone", "A", "Medium", "Cardiovascular", "Rule-based", "Active"],
    ],
    "Surgery": [
        ["", "Which CPT code represents a laparoscopic appendectomy?",
         "44970", "44950", "44960", "44979", "A", "Easy", "Laparoscopic", "Conceptual", "Active"],
        ["", "Open repair of initial inguinal hernia, reducible, patient age 5 years or older. Correct CPT?",
         "49505", "49500", "49507", "49520", "A", "Medium", "Hernia", "Conceptual", "Active"],
        ["", "Arthroscopic partial medial meniscectomy, right knee. CPT code?",
         "29881", "29880", "29882", "29876", "A", "Medium", "Orthopedic", "Conceptual", "Active"],
    ],
}

DEFAULT_SAMPLE = [
    ["", "Sample question text — replace with your question.",
     "Option A text", "Option B text", "Option C text", "Option D text",
     "A", "Medium", "General", "Conceptual", "Active"],
    ["", "Another sample question demonstrating the format.",
     "First choice", "Second choice", "Third choice", "Fourth choice",
     "B", "Easy", "General", "Scenario", "Active"],
    ["", "Hard difficulty rule-based sample question.",
     "Answer option A", "Answer option B", "Answer option C", "Answer option D",
     "C", "Hard", "Guidelines", "Rule-based", "Active"],
]


def _next_qid(db: Session, specialty: str) -> str:
    prefix = SPECIALTY_PREFIX.get(specialty, "QST")
    pattern = f"{prefix}-%"
    rows = db.query(AssessmentQuestion.question_id).filter(
        AssessmentQuestion.question_id.like(pattern)
    ).all()
    max_num = 0
    for (qid,) in rows:
        m = re.search(r"-(\d+)$", qid)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{prefix}-{max_num + 1:03d}"


@router.get("/questions/stats")
def question_stats(db: Session = Depends(get_db)):
    """Per-specialty active/inactive/total counts."""
    rows = db.query(
        AssessmentQuestion.specialty,
        AssessmentQuestion.status,
        func.count(AssessmentQuestion.id),
    ).group_by(AssessmentQuestion.specialty, AssessmentQuestion.status).all()

    agg: dict = {}
    for specialty, status, cnt in rows:
        if specialty not in agg:
            agg[specialty] = {"specialty": specialty, "total": 0, "active": 0, "inactive": 0}
        agg[specialty]["total"] += cnt
        if status == "Active":
            agg[specialty]["active"] += cnt
        else:
            agg[specialty]["inactive"] += cnt

    return list(agg.values())


@router.get("/questions/template")
def download_template(specialty: str = Query(default="ICD10CM")):
    """Download blank xlsx template with 3 sample rows for the given specialty."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Questions"

    header_fill = PatternFill("solid", fgColor="4F46E5")
    header_font = Font(bold=True, color="FFFFFF")

    for col_idx, header in enumerate(TEMPLATE_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    samples = SAMPLE_ROWS.get(specialty, DEFAULT_SAMPLE)
    for row_idx, row_data in enumerate(samples, start=2):
        for col_idx, val in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=val)

    # Column widths
    widths = [15, 60, 30, 30, 30, 30, 14, 12, 20, 15, 14]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"assessment_template_{specialty.replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/questions/pool-summary")
def pool_summary(specialty: str = Query(...), db: Session = Depends(get_db)):
    """Public stats — topic and difficulty counts for a specialty, no question content."""
    filters = [
        AssessmentQuestion.specialty == specialty,
        AssessmentQuestion.status == "Active",
    ]
    total_active = db.query(func.count(AssessmentQuestion.id)).filter(*filters).scalar() or 0

    by_topic = db.query(
        AssessmentQuestion.topic,
        func.count(AssessmentQuestion.id),
    ).filter(*filters).group_by(AssessmentQuestion.topic).all()

    by_diff = db.query(
        AssessmentQuestion.difficulty,
        func.count(AssessmentQuestion.id),
    ).filter(*filters).group_by(AssessmentQuestion.difficulty).all()

    return {
        "specialty": specialty,
        "total_active": total_active,
        "by_topic": sorted(
            [{"topic": t or "Uncategorized", "count": c} for t, c in by_topic],
            key=lambda x: -x["count"],
        ),
        "by_difficulty": {d: c for d, c in by_diff},
    }


@router.get("/questions/export")
def export_questions(
    specialty: str = Query(...),
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    """Passphrase-protected XLSX export of full question bank for a specialty."""
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    qs = db.query(AssessmentQuestion).filter(
        AssessmentQuestion.specialty == specialty,
    ).order_by(AssessmentQuestion.question_id).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Questions"

    header_fill = PatternFill("solid", fgColor="4F46E5")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx, h in enumerate(TEMPLATE_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, q in enumerate(qs, start=2):
        row_vals = [
            q.question_id, q.question_text,
            q.option_a, q.option_b, q.option_c, q.option_d,
            q.correct_answer, q.difficulty, q.topic or "",
            q.question_type, q.status,
        ]
        for col_idx, val in enumerate(row_vals, start=1):
            ws.cell(row=row_idx, column=col_idx, value=val)

    widths = [15, 60, 30, 30, 30, 30, 14, 12, 20, 15, 14]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"questions_{specialty.replace(' ', '_').replace('&', 'and')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/questions/pool-preview")
def pool_preview(
    specialty: str = Query(...),
    topic_filter: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return available counts broken down by difficulty for one specialty."""
    q = db.query(
        AssessmentQuestion.difficulty,
        func.count(AssessmentQuestion.id),
    ).filter(
        AssessmentQuestion.specialty == specialty,
        AssessmentQuestion.status == "Active",
    )
    if topic_filter:
        q = q.filter(AssessmentQuestion.topic.ilike(f"%{topic_filter}%"))
    rows = q.group_by(AssessmentQuestion.difficulty).all()

    counts = {"Easy": 0, "Medium": 0, "Hard": 0}
    for diff, cnt in rows:
        if diff in counts:
            counts[diff] = cnt

    return {
        "specialty": specialty,
        "active_count": sum(counts.values()),
        "easy": counts["Easy"],
        "medium": counts["Medium"],
        "hard": counts["Hard"],
    }


@router.get("/questions")
def list_questions(
    specialty: Optional[str] = Query(default=None),
    difficulty: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AssessmentQuestion)
    if specialty:
        q = q.filter(AssessmentQuestion.specialty == specialty)
    if difficulty:
        q = q.filter(AssessmentQuestion.difficulty == difficulty)
    if status:
        q = q.filter(AssessmentQuestion.status == status)
    if topic:
        q = q.filter(AssessmentQuestion.topic.ilike(f"%{topic}%"))
    if search:
        q = q.filter(AssessmentQuestion.question_text.ilike(f"%{search}%"))

    total = q.count()
    items = q.order_by(AssessmentQuestion.question_id).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [_q_out(item) for item in items],
    }


@router.post("/questions/upload")
def upload_questions(
    specialty: str = Form(...),
    uploaded_by: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload .xlsx of questions for one specialty. Upserts by question_id."""
    if specialty not in VALID_SPECIALTIES:
        raise HTTPException(status_code=400, detail=f"Unknown specialty: {specialty}")

    try:
        contents = file.file.read()
        wb = openpyxl.load_workbook(io.BytesIO(contents))
        ws = wb.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    headers = [str(ws.cell(row=1, column=c).value or "").strip() for c in range(1, ws.max_column + 1)]

    def col(name: str) -> Optional[int]:
        try:
            return headers.index(name) + 1
        except ValueError:
            return None

    col_map = {h: col(h) for h in TEMPLATE_HEADERS}
    missing = [h for h in ["Question_Text", "Option_A", "Option_B", "Option_C", "Option_D", "Correct_Answer", "Difficulty"] if not col_map.get(h)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing}")

    stored: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for row_idx in range(2, ws.max_row + 1):
        def cell_val(col_name: str) -> str:
            c = col_map.get(col_name)
            if c is None:
                return ""
            v = ws.cell(row=row_idx, column=c).value
            return str(v).strip() if v is not None else ""

        q_text = cell_val("Question_Text")
        if not q_text:
            continue

        correct = cell_val("Correct_Answer").upper()
        if correct not in VALID_ANSWERS:
            errors.append(f"Row {row_idx}: invalid Correct_Answer '{correct}'")
            continue

        difficulty = cell_val("Difficulty").capitalize()
        if difficulty == "":
            difficulty = "Medium"
        if difficulty not in VALID_DIFFICULTIES:
            errors.append(f"Row {row_idx}: invalid Difficulty '{difficulty}'")
            continue

        q_type = cell_val("Question_Type")
        if q_type not in VALID_TYPES:
            q_type = "Conceptual"

        active_status = cell_val("Active_Status")
        status = "Active" if active_status.lower() in ("", "active", "1", "yes", "true") else "Inactive"

        qid = cell_val("Question_ID")
        if not qid:
            qid = _next_qid(db, specialty)

        topic = cell_val("Topic") or None

        existing = db.query(AssessmentQuestion).filter(AssessmentQuestion.question_id == qid).first()
        if existing:
            existing.question_text = q_text
            existing.option_a = cell_val("Option_A")
            existing.option_b = cell_val("Option_B")
            existing.option_c = cell_val("Option_C")
            existing.option_d = cell_val("Option_D")
            existing.correct_answer = correct
            existing.difficulty = difficulty
            existing.topic = topic
            existing.question_type = q_type
            existing.status = status
            existing.uploaded_by = uploaded_by
            stored.append(qid)
        else:
            aq = AssessmentQuestion(
                question_id=qid,
                specialty=specialty,
                question_text=q_text,
                option_a=cell_val("Option_A"),
                option_b=cell_val("Option_B"),
                option_c=cell_val("Option_C"),
                option_d=cell_val("Option_D"),
                correct_answer=correct,
                difficulty=difficulty,
                topic=topic,
                question_type=q_type,
                status=status,
                uploaded_by=uploaded_by,
            )
            db.add(aq)
            stored.append(qid)

    db.commit()
    return {"stored": len(stored), "stored_ids": stored, "skipped": len(skipped), "errors": errors}


@router.put("/questions/{question_id}/status")
def update_question_status(
    question_id: str,
    status: str = Query(...),
    updated_by: str = Query(...),
    db: Session = Depends(get_db),
):
    q = db.query(AssessmentQuestion).filter(AssessmentQuestion.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if status not in {"Active", "Inactive"}:
        raise HTTPException(status_code=400, detail="status must be Active or Inactive")
    q.status = status
    db.commit()
    return {"question_id": question_id, "status": status}


@router.put("/questions/{question_id}")
def update_question(
    question_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    q = db.query(AssessmentQuestion).filter(AssessmentQuestion.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    allowed = {"question_text", "option_a", "option_b", "option_c", "option_d",
               "correct_answer", "difficulty", "topic", "question_type"}
    for key, val in payload.items():
        if key in allowed:
            setattr(q, key, val)

    db.commit()
    return _q_out(q)


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: str,
    passphrase: str = Query(...),
    db: Session = Depends(get_db),
):
    if passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    q = db.query(AssessmentQuestion).filter(AssessmentQuestion.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(q)
    db.commit()
    return {"deleted": question_id}


def _q_out(q: AssessmentQuestion) -> dict:
    return {
        "id": q.id,
        "question_id": q.question_id,
        "specialty": q.specialty,
        "question_text": q.question_text,
        "option_a": q.option_a,
        "option_b": q.option_b,
        "option_c": q.option_c,
        "option_d": q.option_d,
        "correct_answer": q.correct_answer,
        "difficulty": q.difficulty,
        "topic": q.topic,
        "question_type": q.question_type,
        "status": q.status,
        "last_used_at": q.last_used_at.isoformat() if q.last_used_at else None,
        "uploaded_by": q.uploaded_by,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }
