"""
Assessment export router — PDF test papers, answer keys, summary.
"""
import io
import zipfile
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib import colors

from database import get_db
from models import GeneratedAssessment, GeneratedAssessmentStudent

router = APIRouter()


def _get_assessment_or_404(assessment_id: int, db: Session) -> GeneratedAssessment:
    a = db.query(GeneratedAssessment).filter(GeneratedAssessment.id == assessment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return a


def _build_student_pdf(assessment_name: str, student_label: str, questions: List[Dict[str, Any]]) -> bytes:
    """Build a clean test paper PDF (no answers shown)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#1e1b4b"),
    )
    sub_style = ParagraphStyle(
        "sub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=16,
    )
    q_style = ParagraphStyle(
        "question",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        spaceAfter=4,
        textColor=colors.HexColor("#111827"),
    )
    opt_style = ParagraphStyle(
        "option",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        leftIndent=20,
        spaceAfter=2,
        textColor=colors.HexColor("#374151"),
    )

    story = [
        Paragraph(assessment_name, title_style),
        Paragraph(f"{student_label} &nbsp;|&nbsp; {len(questions)} Questions", sub_style),
    ]

    for i, q in enumerate(questions, start=1):
        story.append(Paragraph(f"<b>{i}.</b> {q['question_text']}", q_style))
        story.append(Paragraph(f"A. {q['option_a']}", opt_style))
        story.append(Paragraph(f"B. {q['option_b']}", opt_style))
        story.append(Paragraph(f"C. {q['option_c']}", opt_style))
        story.append(Paragraph(f"D. {q['option_d']}", opt_style))
        story.append(Spacer(1, 8))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _build_answer_key_pdf(assessment_name: str, students: List[GeneratedAssessmentStudent]) -> bytes:
    """Build consolidated answer key PDF for all students."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        textColor=colors.HexColor("#1e1b4b"),
    )
    student_style = ParagraphStyle(
        "student",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#4f46e5"),
    )

    story = [Paragraph(f"Answer Key — {assessment_name}", title_style)]

    for student in students:
        story.append(Paragraph(student.student_label, student_style))
        questions = student.questions_json
        if isinstance(questions, str):
            import json
            questions = json.loads(questions)

        table_data = [["#", "QID", "Answer", "Specialty", "Topic"]]
        for i, q in enumerate(questions, start=1):
            table_data.append([
                str(i),
                q.get("question_id", ""),
                q.get("correct_answer", ""),
                q.get("specialty", ""),
                q.get("topic", "") or "",
            ])

        tbl = Table(
            table_data,
            colWidths=[0.4 * inch, 1.0 * inch, 0.7 * inch, 1.4 * inch, 2.2 * inch],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("ALIGN", (0, 0), (2, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
        story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return buf.read()


@router.get("/{assessment_id}/export-pdf")
def export_student_pdfs(assessment_id: int, db: Session = Depends(get_db)):
    """Download ZIP of per-student test PDFs (no answers)."""
    assessment = _get_assessment_or_404(assessment_id, db)
    students = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).all()

    if not students:
        raise HTTPException(status_code=404, detail="No student data found for this assessment")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for student in students:
            questions = student.questions_json
            if isinstance(questions, str):
                import json
                questions = json.loads(questions)
            pdf_bytes = _build_student_pdf(assessment.assessment_name, student.student_label, questions)
            filename = f"{student.student_label}_{assessment.assessment_name.replace(' ', '_')}.pdf"
            zf.writestr(filename, pdf_bytes)

    zip_buf.seek(0)
    safe_name = assessment.assessment_name.replace(" ", "_")
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_tests.zip"'},
    )


@router.get("/{assessment_id}/export-answer-key")
def export_answer_key(assessment_id: int, db: Session = Depends(get_db)):
    """Download combined answer key PDF for all students."""
    assessment = _get_assessment_or_404(assessment_id, db)
    students = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).all()

    if not students:
        raise HTTPException(status_code=404, detail="No student data found")

    pdf_bytes = _build_answer_key_pdf(assessment.assessment_name, students)
    safe_name = assessment.assessment_name.replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_answer_key.pdf"'},
    )


@router.get("/{assessment_id}/summary")
def get_assessment_summary(assessment_id: int, db: Session = Depends(get_db)):
    """Return stored assessment data for history/detail view."""
    assessment = _get_assessment_or_404(assessment_id, db)
    students = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.assessment_id == assessment_id
    ).all()

    q_count = 0
    if students:
        first_qs = students[0].questions_json
        if isinstance(first_qs, list):
            q_count = len(first_qs)
        elif isinstance(first_qs, str):
            import json
            try:
                q_count = len(json.loads(first_qs))
            except Exception:
                q_count = 0

    return {
        "id": assessment.id,
        "assessment_name": assessment.assessment_name,
        "student_count": assessment.student_count,
        "generated_by": assessment.generated_by,
        "generated_at": assessment.generated_at.isoformat() if assessment.generated_at else None,
        "config_id": assessment.config_id,
        "questions_per_student": q_count,
        "students": [s.student_label for s in students],
    }
