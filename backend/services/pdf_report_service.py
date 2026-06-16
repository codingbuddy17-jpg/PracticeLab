"""PDF report generation for PracticeLab — coder performance and batch performance reports."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)

INDIGO = colors.HexColor("#4f46e5")
INDIGO_DARK = colors.HexColor("#312e81")
GREEN = colors.HexColor("#16a34a")
GREEN_BG = colors.HexColor("#f0fdf4")
GREEN_BORDER = colors.HexColor("#bbf7d0")
AMBER = colors.HexColor("#d97706")
AMBER_BG = colors.HexColor("#fff7ed")
AMBER_BORDER = colors.HexColor("#fed7aa")
RED = colors.HexColor("#dc2626")
RED_BG = colors.HexColor("#fff5f5")
RED_BORDER = colors.HexColor("#fecaca")
GRAY = colors.HexColor("#6b7280")
GRAY_LIGHT = colors.HexColor("#f9fafb")
BORDER = colors.HexColor("#e5e7eb")

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title", parent=styles["Title"], textColor=INDIGO_DARK, fontSize=20, spaceAfter=2)
SUBTITLE = ParagraphStyle("Subtitle", parent=styles["Normal"], textColor=GRAY, fontSize=11, spaceAfter=14)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#111111"), fontSize=13, spaceBefore=14, spaceAfter=6)
NORMAL = ParagraphStyle("NormalSm", parent=styles["Normal"], fontSize=10)
SMALL_GRAY = ParagraphStyle("SmallGray", parent=styles["Normal"], fontSize=8, textColor=GRAY)


def _score_color(score):
    if score is None:
        return colors.HexColor("#111111")
    if score >= 90:
        return GREEN
    if score >= 80:
        return AMBER
    return RED


def _score_cell(score, suffix="%"):
    if score is None:
        return Paragraph("—", NORMAL)
    style = ParagraphStyle("score", parent=NORMAL, textColor=_score_color(score), fontName="Helvetica-Bold")
    return Paragraph(f"{score}{suffix}", style)


def _stat_row(stats: list[tuple[str, str]]) -> Table:
    """stats: list of (value, label) tuples rendered as boxed stat cards."""
    value_style = ParagraphStyle("statValue", parent=styles["Normal"], fontSize=18, fontName="Helvetica-Bold", alignment=1, textColor=colors.HexColor("#111111"))
    label_style = ParagraphStyle("statLabel", parent=styles["Normal"], fontSize=8, alignment=1, textColor=GRAY)
    col_width = 7.0 * inch / len(stats)
    inner = []
    for v, l in stats:
        cell_table = Table([[Paragraph(v, value_style)], [Paragraph(l, label_style)]], colWidths=[col_width])
        cell_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        inner.append(cell_table)
    wrapper = Table([inner], colWidths=[col_width] * len(stats))
    wrapper.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    return wrapper


def _ranked_box(title: str, items: list, color, bg, border, empty_msg: str, row_fn) -> Table:
    title_style = ParagraphStyle("boxTitle", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold", textColor=color)
    rows = [[Paragraph(title.upper(), title_style)]]
    if not items:
        rows.append([Paragraph(empty_msg, ParagraphStyle("empty", parent=NORMAL, textColor=GREEN, fontName="Helvetica-Bold"))])
    else:
        for i, item in enumerate(items):
            rows.append([row_fn(i, item)])
    t = Table(rows, colWidths=[3.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.75, border),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _two_col(left: Table, right: Table) -> Table:
    t = Table([[left, right]], colWidths=[3.5 * inch, 3.5 * inch])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _data_table(header: list, rows: list, col_widths: list) -> Table:
    header_style = ParagraphStyle("th", parent=NORMAL, fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)
    data = [[Paragraph(h, header_style) for h in header]] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), GRAY_LIGHT))
    t.setStyle(TableStyle(style))
    return t


def _header(elements, title, subtitle_lines):
    elements.append(Paragraph(title, TITLE))
    for line in subtitle_lines:
        elements.append(Paragraph(line, SUBTITLE))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=INDIGO, spaceAfter=10))


def _footer_note(elements):
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    elements.append(Paragraph(f"Generated by PracticeLab on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", SMALL_GRAY))


def generate_coder_report_pdf(coder_name: str, summary: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    elements = []

    _header(elements, "Coder Performance Report", [f"Coder: {coder_name}"])

    stats = [
        (str(summary.get("total_charts", 0)), "Charts Completed"),
        (str(summary.get("charts_passed", 0)), "Charts Passed"),
    ]
    if summary.get("weighted_accuracy") is not None:
        stats.append((f"{summary['weighted_accuracy']}%", "Weighted Accuracy"))
    dpo = summary.get("cumulative_dpo")
    if dpo and dpo.get("overall_accuracy") is not None:
        stats.append((f"{dpo['overall_accuracy']}%", "Overall DPO"))
    elements.append(_stat_row(stats))

    if dpo and any(dpo.get(k) is not None for k in ("dx_accuracy", "poa_accuracy", "proc_accuracy")):
        elements.append(Paragraph("DPO Breakdown", H2))
        dpo_rows = []
        for label, key in [("Diagnosis (Dx)", "dx_accuracy"), ("POA", "poa_accuracy"), ("Procedure (PCS/CPT)", "proc_accuracy")]:
            if dpo.get(key) is not None:
                dpo_rows.append([Paragraph(label, NORMAL), _score_cell(dpo[key])])
        elements.append(_data_table(["Section", "Accuracy"], dpo_rows, [4 * inch, 2 * inch]))

    cats = summary.get("by_category") or []
    if cats:
        elements.append(Paragraph("Category Performance", H2))
        cat_rows = [[Paragraph(c["category"], NORMAL), Paragraph(str(c["charts"]), NORMAL), _score_cell(c["avg_score"])] for c in cats]
        elements.append(_data_table(["Category", "Charts", "Avg Score"], cat_rows, [3.5 * inch, 1.5 * inch, 1.5 * inch]))

        weak = [c for c in cats if c["avg_score"] < 90]
        strong = [c for c in cats if c["avg_score"] >= 90]
        top3 = strong[:3]
        bottom3 = list(reversed(weak[-3:])) if weak else []
        elements.append(Spacer(1, 10))
        left = _ranked_box("Top Categories", top3, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                            lambda i, c: Paragraph(f"{c['category']} — {c['charts']} charts — <b>{c['avg_score']}%</b>", NORMAL))
        right = _ranked_box("Needs Work", bottom3, AMBER if bottom3 else GREEN, AMBER_BG if bottom3 else GREEN_BG, AMBER_BORDER if bottom3 else GREEN_BORDER,
                             "None — every category is at or above 90%",
                             lambda i, c: Paragraph(f"{c['category']} — {c['charts']} charts — <b>{c['avg_score']}%</b>", NORMAL))
        elements.append(_two_col(left, right))

    batches = summary.get("batches") or []
    if batches:
        elements.append(Paragraph("Batch History", H2))
        b_rows = []
        for b in batches:
            date_str = b["created_at"][:10] if b.get("created_at") else "—"
            passed_str = f"{b['charts_passed']}/{b.get('chart_count', '?')}" if b.get("charts_passed") is not None else "—"
            b_rows.append([
                Paragraph(b["batch_name"], NORMAL), Paragraph(b.get("specialty") or "—", NORMAL),
                Paragraph(date_str, NORMAL), Paragraph(str(b.get("chart_count", "—")), NORMAL),
                _score_cell(b.get("avg_score")), Paragraph(passed_str, NORMAL),
            ])
        elements.append(_data_table(
            ["Batch", "Specialty", "Date", "Charts", "Avg Score", "Passed"],
            b_rows, [1.8 * inch, 1.1 * inch, 0.9 * inch, 0.7 * inch, 0.9 * inch, 0.8 * inch],
        ))

    _footer_note(elements)
    doc.build(elements)
    return buf.getvalue()


def generate_batch_report_pdf(insights: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    elements = []
    bs = insights["batch_summary"]

    _header(elements, "Batch Performance Report", [
        f"Batch: {insights['batch_name']}  |  Specialty: {insights['specialty']}",
    ])

    stats = [
        (str(bs["n_coders"]), "Coders"),
        (str(bs["total_graded"]), "Total Charts Coded"),
        (f"{bs['pass_rate']}%", "Pass Rate"),
        (f"{bs['avg_score']}%", "Avg Score"),
        (str(bs["passed"]), "Passed"),
        (str(bs["failed"]), "Failed"),
    ]
    elements.append(_stat_row(stats))

    if bs.get("highest_score") is not None:
        elements.append(Spacer(1, 10))
        hi_names = ", ".join(bs["highest_score_coders"])
        lo_names = ", ".join(bs["lowest_score_coders"])
        callout_style = ParagraphStyle("callout", parent=NORMAL, fontSize=10)
        rows = [[
            Paragraph(f"<b>Highest score:</b> <font color='#16a34a'><b>{bs['highest_score']}%</b></font> — {hi_names}", callout_style),
        ], [
            Paragraph(f"<b>Lowest score:</b> <font color='#dc2626'><b>{bs['lowest_score']}%</b></font> — {lo_names}", callout_style),
        ]]
        t = Table(rows, colWidths=[7 * inch])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        elements.append(t)

    sd = insights.get("score_distribution") or []
    if sd:
        elements.append(Paragraph("Score Distribution (cumulative chart-weighted score)", H2))
        sd_rows = []
        for b in sd:
            style = ParagraphStyle("sd", parent=NORMAL, textColor=colors.HexColor(b["color"]), fontName="Helvetica-Bold")
            sd_rows.append([Paragraph(b["label"], style), Paragraph(str(b["count"]), NORMAL), Paragraph(", ".join(b["coders"]), NORMAL)])
        elements.append(_data_table(["Score Range", "Coders", "Names"], sd_rows, [1.2 * inch, 1 * inch, 4.8 * inch]))

    top_p = insights.get("top_performers") or []
    bottom_p = insights.get("bottom_performers") or []
    elements.append(Paragraph("Coder Performance", H2))
    left = _ranked_box("Top Performers", top_p, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {c['coder_name']} — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Needs Attention", bottom_p, AMBER if bottom_p else GREEN, AMBER_BG if bottom_p else GREEN_BG, AMBER_BORDER if bottom_p else GREEN_BORDER,
                         "None — every coder is at or above 90%",
                         lambda i, c: Paragraph(f"#{i+1} {c['coder_name']} — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    top_c = insights.get("top_categories") or []
    bottom_c = insights.get("bottom_categories") or []
    elements.append(Paragraph("Category Performance", H2))
    left = _ranked_box("Top Categories", top_c, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {c['category']} ({c['attempt_count']}) — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Bottom Categories", bottom_c, RED if bottom_c else GREEN, RED_BG if bottom_c else GREEN_BG, RED_BORDER if bottom_c else GREEN_BORDER,
                         "None — every category is at or above 90%",
                         lambda i, c: Paragraph(f"#{i+1} {c['category']} ({c['attempt_count']}) — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    top_ch = insights.get("top_charts") or []
    bottom_ch = insights.get("bottom_charts") or []
    elements.append(Paragraph("Chart Performance", H2))
    left = _ranked_box("Top Charts", top_ch, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {c['chart_number']} ({c['category']}) — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Bottom Charts", bottom_ch, RED if bottom_ch else GREEN, RED_BG if bottom_ch else GREEN_BG, RED_BORDER if bottom_ch else GREEN_BORDER,
                         "None — every chart is at or above 90%",
                         lambda i, c: Paragraph(f"#{i+1} {c['chart_number']} ({c['category']}) — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    te = insights.get("team_errors") or {}
    if te.get("top_missed_codes"):
        elements.append(Paragraph("Top Missed Codes (team-wide)", H2))
        mc_rows = [[Paragraph(m["code"], NORMAL), Paragraph(f"missed {m['count']}×", NORMAL)] for m in te["top_missed_codes"]]
        elements.append(_data_table(["Code", "Frequency"], mc_rows, [3 * inch, 3 * inch]))

    _footer_note(elements)
    doc.build(elements)
    return buf.getvalue()
