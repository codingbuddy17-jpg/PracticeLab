"""PDF report generation for PracticeLab — coder performance and batch performance reports.

Theme: R1 Blue (#003DA5) on a warm cream page background, consistent grid
widths throughout, and an auto-generated executive-summary verdict line at
the top of each report so a leadership reader gets the headline in one glance.
"""
import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    KeepInFrame, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Circle, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker

# ── Theme ──────────────────────────────────────────────────────────────────
R1_BLUE = colors.HexColor("#003DA5")
R1_BLUE_DARK = colors.HexColor("#002B75")
R1_BLUE_LIGHT = colors.HexColor("#E6ECF9")
CREAM = colors.HexColor("#FBF7EE")
CREAM_PANEL = colors.HexColor("#FFFFFF")

GREEN = colors.HexColor("#1A7A4C")
GREEN_BG = colors.HexColor("#EAF6EE")
GREEN_BORDER = colors.HexColor("#BFE3CC")
AMBER = colors.HexColor("#B5760A")
AMBER_BG = colors.HexColor("#FCF1DC")
AMBER_BORDER = colors.HexColor("#F0D9A8")
RED = colors.HexColor("#B23A33")
RED_BG = colors.HexColor("#FBEAE8")
RED_BORDER = colors.HexColor("#EBC2BD")
GRAY = colors.HexColor("#6B6457")
GRAY_LIGHT = colors.HexColor("#F4F0E6")
BORDER = colors.HexColor("#DDD6C5")

PAGE_W, PAGE_H = letter
MARGIN = 0.6 * inch
CONTENT_W = PAGE_W - 2 * MARGIN
COL_GAP = 0.22 * inch
HALF_W = (CONTENT_W - COL_GAP) / 2

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title", parent=styles["Title"], textColor=R1_BLUE_DARK, fontName="Helvetica-Bold", fontSize=21, spaceAfter=2, leading=24)
SUBTITLE = ParagraphStyle("Subtitle", parent=styles["Normal"], textColor=GRAY, fontSize=10.5, spaceAfter=12)
EYEBROW = ParagraphStyle("Eyebrow", parent=styles["Normal"], textColor=R1_BLUE, fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=R1_BLUE_DARK, fontName="Helvetica-Bold", fontSize=12.5, spaceBefore=16, spaceAfter=2, leading=15)
NORMAL = ParagraphStyle("NormalSm", parent=styles["Normal"], fontSize=9.5, leading=13)
SMALL_GRAY = ParagraphStyle("SmallGray", parent=styles["Normal"], fontSize=8, textColor=GRAY)
VERDICT_TEXT = ParagraphStyle("Verdict", parent=styles["Normal"], fontSize=11, leading=15, fontName="Helvetica-Bold")


def _score_color(score, pass_threshold: int = 80):
    if score is None:
        return colors.HexColor("#1a1a1a")
    low = round(pass_threshold * 0.75)
    if score >= pass_threshold:
        return GREEN
    if score >= low:
        return AMBER
    return RED


def _coder_label(c: dict) -> str:
    """coder_name, suffixed with (Emp ID) when available."""
    return f"{c['coder_name']} ({c['emp_id']})" if c.get("emp_id") else c["coder_name"]


def _short_label(text, max_len: int = 28) -> str:
    text = str(text or "")
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0].rstrip(".,;: ") + "…"


def _score_cell(score, suffix="%", pass_threshold: int = 80):
    if score is None:
        return Paragraph("—", NORMAL)
    style = ParagraphStyle("score", parent=NORMAL, textColor=_score_color(score, pass_threshold), fontName="Helvetica-Bold")
    return Paragraph(f"{score}{suffix}", style)


def _donut_chart(buckets: list[dict], size=150) -> Drawing:
    """buckets: [{label, count, color}, ...] — color is a '#rrggbb' string."""
    d = Drawing(size, size)
    pie = Pie()
    pie.x = 5
    pie.y = 5
    pie.width = size - 10
    pie.height = size - 10
    pie.data = [b["count"] for b in buckets]
    pie.labels = None
    pie.slices.strokeWidth = 1
    pie.slices.strokeColor = CREAM_PANEL
    pie.sideLabels = False
    for i, b in enumerate(buckets):
        pie.slices[i].fillColor = colors.HexColor(b["color"])
    d.add(pie)
    cx, cy = pie.x + pie.width / 2, pie.y + pie.height / 2
    hole_r = pie.width * 0.38
    d.add(Circle(cx, cy, hole_r, fillColor=CREAM_PANEL, strokeColor=None))
    return d


def _category_bar_chart(rows: list[dict], label_key: str, score_key: str = "avg_score", width=CONTENT_W) -> Drawing:
    """Horizontal bar chart, one bar per row, color-coded green/amber/red by score."""
    n = len(rows)
    height = max(60, n * 20 + 30)
    label_col_w = 130
    d = Drawing(width, height)
    chart = HorizontalBarChart()
    chart.x = label_col_w
    chart.y = 12
    chart.width = width - label_col_w - 40
    chart.height = height - 24
    chart.data = [[r[score_key] for r in rows]]
    chart.categoryAxis.categoryNames = [_short_label(r[label_key]) for r in rows]
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 25
    chart.valueAxis.labels.fontSize = 7
    chart.bars.strokeColor = None
    chart.barLabels.fontSize = 7.5
    chart.barLabels.nudge = 9
    chart.barLabelFormat = "%0.0f%%"
    chart.barWidth = 10
    for i, r in enumerate(rows):
        chart.bars[(0, i)].fillColor = _score_color(r[score_key])
    d.add(chart)
    return d


def _trend_line_chart(points: list[tuple], width=CONTENT_W, height=170) -> Drawing:
    """points: [(label, value), ...] in chronological order."""
    n = len(points)
    d = Drawing(width, height)
    lp = LinePlot()
    lp.x = 45
    lp.y = 36
    lp.width = width - 65
    lp.height = height - 56
    lp.data = [[(i, v) for i, (_, v) in enumerate(points)]]
    lp.lines[0].strokeColor = R1_BLUE
    lp.lines[0].strokeWidth = 2.2
    lp.lines[0].symbol = makeMarker("FilledCircle")
    lp.lines[0].symbol.size = 4.5
    lp.lines[0].symbol.fillColor = R1_BLUE
    lp.xValueAxis.valueMin = -0.4
    lp.xValueAxis.valueMax = max(n - 1, 1) + 0.4
    lp.xValueAxis.visible = 0
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = 100
    lp.yValueAxis.valueSteps = [0, 25, 50, 75, 100]
    lp.yValueAxis.labels.fontSize = 7.5
    d.add(lp)
    label_style = ParagraphStyle("trendLabel", parent=NORMAL, fontSize=6.8, alignment=1, textColor=GRAY)
    for i, (label, _) in enumerate(points):
        px = lp.x + (lp.width * (i / max(n - 1, 1))) if n > 1 else lp.x + lp.width / 2
        d.add(String(px, 10, label[:10], fontSize=6.8, fillColor=GRAY, textAnchor="middle"))
    return d


def _section_heading(elements, text):
    elements.append(Paragraph(text, H2))
    elements.append(HRFlowable(width="100%", thickness=1, color=R1_BLUE_LIGHT, spaceBefore=2, spaceAfter=8))


def _draw_background(c, _doc):
    c.saveState()
    c.setFillColor(CREAM)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.restoreState()


# Above this many cards in one row, each card is too narrow for its label and
# KeepInFrame starts shrinking the text — which is why the boxes ended up with
# visibly different font sizes rather than overflowing outright.
MAX_STATS_PER_ROW = 4


def _stat_row(stats: list[tuple[str, str]], per_row: int = MAX_STATS_PER_ROW):
    """
    Boxed stat cards, evenly sized, spanning CONTENT_W.

    Wraps onto multiple rows rather than squeezing everything onto one. The
    batch report passes six — "TOTAL CHARTS CODED" in a 1.1-inch card had to be
    shrunk to fit, and since shrink is per-card, adjacent boxes ended up at
    different font sizes. Balanced across rows (6 -> 3+3, not 4+2) so every
    card on the page stays the same width.
    """
    if len(stats) > per_row:
        n_rows = -(-len(stats) // per_row)          # ceil
        base, extra = divmod(len(stats), n_rows)
        chunks, i = [], 0
        for r in range(n_rows):
            size = base + (1 if r < extra else 0)
            chunks.append(stats[i:i + size])
            i += size
        stacked = []
        for j, chunk in enumerate(chunks):
            if j:
                stacked.append(Spacer(1, 6))
            stacked.append(_stat_row(chunk, per_row))
        return KeepTogether(stacked)
    value_style = ParagraphStyle("statValue", parent=styles["Normal"], fontSize=18, leading=21, fontName="Helvetica-Bold", alignment=1, textColor=R1_BLUE_DARK)
    label_style = ParagraphStyle("statLabel", parent=styles["Normal"], fontSize=7.4, leading=8.2, alignment=1, textColor=GRAY, fontName="Helvetica-Bold")
    n = len(stats)
    gap = 0.12 * inch
    card_height = 0.74 * inch
    card_width = (CONTENT_W - gap * (n - 1)) / n

    row_cells, col_widths = [], []
    for i, (v, l) in enumerate(stats):
        content = KeepInFrame(
            card_width - 10,
            card_height - 10,
            [Paragraph(v, value_style), Spacer(1, 2), Paragraph(l.upper(), label_style)],
            mode="shrink",
            hAlign="CENTER",
            vAlign="MIDDLE",
        )
        row_cells.append(content)
        col_widths.append(card_width)
        if i < n - 1:
            row_cells.append("")
            col_widths.append(gap)

    wrapper = Table([row_cells], colWidths=col_widths, rowHeights=[card_height])
    style = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for col in range(0, len(col_widths), 2):
        style.extend([
            ("BOX", (col, 0), (col, 0), 0.75, BORDER),
            ("BACKGROUND", (col, 0), (col, 0), CREAM_PANEL),
        ])
    wrapper.setStyle(TableStyle(style))
    return wrapper


def _truncate(text: str, max_len: int = 108) -> str:
    """Cap verdict detail text to a length that reliably fits one line at
    CONTENT_W with the NORMAL style — keeps every executive-summary box the
    same height instead of growing whenever a verdict appends extra context
    (weakest-area note, trend delta, etc)."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0].rstrip(".,;: ") + "…"


def _verdict_box(headline: str, detail: str, color, bg, border) -> Table:
    detail = _truncate(detail)
    eyebrow_style = ParagraphStyle("verdictEyebrow", parent=EYEBROW, textColor=color)
    detail_style = ParagraphStyle("verdictDetail", parent=NORMAL, textColor=colors.HexColor("#33312b"))
    headline_style = ParagraphStyle("verdictHeadline", parent=VERDICT_TEXT, textColor=color)
    rows = [
        [Paragraph("EXECUTIVE SUMMARY", eyebrow_style)],
        [Paragraph(headline, headline_style)],
        [Paragraph(detail, detail_style)],
    ]
    t = Table(rows, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, border),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
        ("TOPPADDING", (0, 2), (-1, 2), 0), ("BOTTOMPADDING", (0, 2), (-1, 2), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t


def _ranked_box(title: str, items: list, color, bg, border, empty_msg: str, row_fn, width=HALF_W) -> Table:
    title_style = ParagraphStyle("boxTitle", parent=EYEBROW, textColor=color)
    rows = [[Paragraph(title.upper(), title_style)]]
    if not items:
        rows.append([Paragraph(empty_msg, ParagraphStyle("empty", parent=NORMAL, textColor=GREEN, fontName="Helvetica-Bold"))])
    else:
        for i, item in enumerate(items[:4]):
            rows.append([row_fn(i, item)])
    while len(rows) < 5:
        rows.append([Paragraph(" ", NORMAL)])
    row_heights = [0.28 * inch] + [0.30 * inch] * (len(rows) - 1)
    fixed_rows = [[KeepInFrame(width - 24, row_heights[i] - 4, [cell], mode="shrink")]
                  for i, (cell,) in enumerate(rows)]
    t = Table(fixed_rows, colWidths=[width], rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.75, border),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _two_col(left: Table, right: Table) -> Table:
    t = Table([[left, right]], colWidths=[HALF_W, HALF_W])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), COL_GAP),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _data_table(header: list, rows: list, col_fracs: list, width=CONTENT_W) -> Table:
    """col_fracs: relative widths (e.g. [2, 1, 1]) summing proportionally to `width`.
    Pass width=HALF_W when this table will sit inside a _two_col() half — otherwise
    it sizes itself for the full page width and overflows/corrupts when squeezed."""
    total = sum(col_fracs)
    col_widths = [width * f / total for f in col_fracs]
    header_style = ParagraphStyle("th", parent=NORMAL, fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)
    data = [[Paragraph(h, header_style) for h in header]] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), R1_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 1), (-1, -1), CREAM_PANEL),
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
    elements.append(HRFlowable(width="100%", thickness=2, color=R1_BLUE, spaceAfter=12))


def _footer_note(elements):
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    elements.append(Paragraph(f"Generated by PracticeLab on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", SMALL_GRAY))


def _doc(buf):
    return SimpleDocTemplate(buf, pagesize=letter, topMargin=MARGIN, bottomMargin=MARGIN,
                              leftMargin=MARGIN, rightMargin=MARGIN)


def _coder_verdict(summary: dict, pass_threshold: int = 80):
    score = summary.get("weighted_accuracy")
    source = "grading score"
    if score is None and summary.get("cumulative_dpo"):
        score = summary["cumulative_dpo"].get("overall_accuracy")
        source = "overall accuracy (DPO)"
    cats = summary.get("by_category") or []
    weakest = min(cats, key=lambda c: c["avg_score"]) if cats else None
    weak_note = f" Weakest area: {weakest['category']} at {weakest['avg_score']}%." if weakest and weakest["avg_score"] < pass_threshold else ""

    ready_threshold = pass_threshold + max(5, (100 - pass_threshold) // 2)
    low_threshold = round(pass_threshold * 0.75)

    if score is None:
        return ("NO SCORED CHARTS YET", "This coder has not completed any graded charts in the selected period.", GRAY, GRAY_LIGHT, BORDER)
    if score >= ready_threshold:
        return ("READY", f"Performing at {score}% {source} — at or above the {ready_threshold}% production-ready standard.{weak_note}", GREEN, GREEN_BG, GREEN_BORDER)
    if score >= pass_threshold:
        return ("ON TRACK", f"{score}% {source} — meets the {pass_threshold}% pass threshold.{weak_note}", AMBER, AMBER_BG, AMBER_BORDER)
    if score >= low_threshold:
        return ("NEEDS COACHING", f"{score}% {source} is below the {pass_threshold}% target — recommend a focused review session.{weak_note}", AMBER, AMBER_BG, AMBER_BORDER)
    return ("AT RISK", f"{score}% {source} reflects significant gaps — recommend structured retraining before further assignments.{weak_note}", RED, RED_BG, RED_BORDER)


def _batch_verdict(bs: dict, pass_threshold: int = 80):
    pr = bs["pass_rate"]
    delta = bs.get("pass_rate_delta")
    trend = ""
    if delta is not None:
        trend = f" ({'+' if delta > 0 else ''}{delta}% vs prior batch)"
    acceptable_floor = round(pass_threshold * 0.75)
    if pr >= pass_threshold:
        return ("STRONG", f"{pr}% pass rate{trend} meets or exceeds the {pass_threshold}% target.", GREEN, GREEN_BG, GREEN_BORDER)
    if pr >= acceptable_floor:
        return ("ACCEPTABLE", f"{pr}% pass rate{trend} is within range, with room to improve.", AMBER, AMBER_BG, AMBER_BORDER)
    if pr >= 50:
        return ("BELOW TARGET", f"{pr}% pass rate{trend} is under the {acceptable_floor}% floor — recommend a retraining session before the next cycle.", RED, RED_BG, RED_BORDER)
    return ("CRITICAL", f"{pr}% pass rate{trend} indicates the majority of charts failed — immediate intervention recommended.", RED, RED_BG, RED_BORDER)


def generate_coder_report_pdf(coder_name: str, summary: dict, team_avg_score: Optional[float] = None,
                              period_label: Optional[str] = None,
                              scope_label: Optional[str] = None) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf)
    elements = []

    emp_id = summary.get("emp_id")
    coder_subtitle = f"Coder: {coder_name}  |  Emp ID: {emp_id}" if emp_id else f"Coder: {coder_name}"
    # Always state the scope — a filtered report must not be mistakable for a
    # cumulative one once it leaves the app.
    # "All practice & batch work" told a reader nothing they could use — it is
    # true of every report this function has ever produced. What matters is
    # WHICH specialties, because that is what the scores in here are scores in.
    mix = summary.get("specialty_mix") or []
    if mix:
        shown = " · ".join(f"{m['specialty']} {m['charts']} chart{'s' if m['charts'] != 1 else ''}"
                           for m in mix[:4])
        if len(mix) > 4:
            shown += f" · +{len(mix) - 4} more"
        default_scope = f"Specialties: {shown}"
    else:
        default_scope = "Scope: batch and direct-assignment work"
    subtitles = [coder_subtitle, scope_label or default_scope]
    if summary.get("last_activity"):
        subtitles.append(f"Last graded: {summary['last_activity'][:10]}")
    if period_label:
        subtitles.append(period_label)
    _header(elements, "Coder Performance Report", subtitles)

    pt = summary.get("pass_threshold", 80)
    headline, detail, color, bg, border = _coder_verdict(summary, pass_threshold=pt)
    elements.append(_verdict_box(headline, detail, color, bg, border))
    elements.append(Spacer(1, 12))

    stats = [
        (str(summary.get("total_charts", 0)), "Charts Completed"),
        (str(summary.get("charts_passed", 0)), "Charts Passed"),
    ]
    if summary.get("weighted_accuracy") is not None:
        stats.append((f"{summary['weighted_accuracy']}%", "Grading Score"))
    dpo = summary.get("cumulative_dpo")
    if dpo and dpo.get("overall_accuracy") is not None:
        stats.append((f"{dpo['overall_accuracy']}%", "Overall accuracy (DPO)"))
    if team_avg_score is not None:
        stats.append((f"{team_avg_score}%", "Team Avg (Benchmark)"))
    elements.append(_stat_row(stats))

    if team_avg_score is not None and summary.get("weighted_accuracy") is not None:
        diff = round(summary["weighted_accuracy"] - team_avg_score, 1)
        diff_hex = "#1A7A4C" if diff > 0 else "#B23A33" if diff < 0 else "#6B6457"
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(
            f"vs team average ({team_avg_score}%, formal batches): "
            f"<font color='{diff_hex}'><b>{'+' if diff > 0 else ''}{diff} points</b></font>",
            ParagraphStyle("benchline", parent=NORMAL, textColor=colors.HexColor("#33312b"))
        ))

    batches = summary.get("batches") or []
    trend_points = [(b["created_at"][:10] if b.get("created_at") else b["batch_name"], b["avg_score"]) for b in batches if b.get("avg_score") is not None]
    if len(trend_points) >= 2:
        _section_heading(elements, "Grading Score Trend")
        elements.append(_trend_line_chart(trend_points))

    if dpo and any(dpo.get(k) is not None for k in ("dx_accuracy", "proc_accuracy", "drg_accuracy")):
        _section_heading(elements, "Accuracy (DPO) Breakdown")
        dpo_rows = []
        # PCS and CPT are different code sets; a generic "Procedure accuracy"
        # reads as whichever the trainer's specialty uses, which is a guess.
        proc_label = summary.get("proc_label") or "Procedure accuracy"
        for label, key in [("Diagnosis accuracy", "dx_accuracy"), (proc_label, "proc_accuracy"), ("DRG accuracy", "drg_accuracy")]:
            if dpo.get(key) is not None:
                dpo_rows.append([Paragraph(label, NORMAL), _score_cell(dpo[key], pass_threshold=pt)])
        elements.append(_data_table(["Element", "Accuracy"], dpo_rows, [3, 1]))

    ep = summary.get("error_pattern") or {}
    if ep.get("by_issue_type"):
        _section_heading(elements, "Error Pattern")
        issue_rows = [[Paragraph(e["type"].replace("_", " "), NORMAL), Paragraph(str(e["count"]), NORMAL), Paragraph(f"{e['pct']}%", NORMAL)] for e in ep["by_issue_type"]]
        if ep.get("top_missed_codes"):
            left = _data_table(["Issue Type", "Count", "Share"], issue_rows, [2, 1, 1], width=HALF_W)
            mc_rows = [[Paragraph(m["code"], NORMAL), Paragraph(f"{m['count']}×", NORMAL)] for m in ep["top_missed_codes"]]
            right = _data_table(["Top Missed Codes", "Frequency"], mc_rows, [2, 1], width=HALF_W)
            elements.append(_two_col(left, right))
        else:
            elements.append(_data_table(["Issue Type", "Count", "Share"], issue_rows, [2, 1, 1]))

    cats = summary.get("by_category") or []
    if cats:
        _section_heading(elements, "Category Performance")
        elements.append(_category_bar_chart(sorted(cats, key=lambda c: c["avg_score"]), label_key="category"))
        elements.append(Spacer(1, 6))
        cat_rows = [[Paragraph(c["category"], NORMAL), Paragraph(str(c["charts"]), NORMAL), _score_cell(c["avg_score"], pass_threshold=pt)] for c in cats]
        elements.append(_data_table(["Category", "Charts", "Avg Grading Score"], cat_rows, [3, 1, 1]))

        weak = [c for c in cats if c["avg_score"] < pt]
        strong = [c for c in cats if c["avg_score"] >= pt]
        top3 = strong[:3]
        bottom3 = list(reversed(weak[-3:])) if weak else []
        elements.append(Spacer(1, 10))
        left = _ranked_box("Top Categories", top3, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                            lambda i, c: Paragraph(f"{c['category']} — {c['charts']} charts — <b>{c['avg_score']}%</b>", NORMAL))
        right = _ranked_box("Needs Work", bottom3, AMBER if bottom3 else GREEN, AMBER_BG if bottom3 else GREEN_BG, AMBER_BORDER if bottom3 else GREEN_BORDER,
                             f"None — every category is at or above {pt}%",
                             lambda i, c: Paragraph(f"{c['category']} — {c['charts']} charts — <b>{c['avg_score']}%</b>", NORMAL))
        elements.append(_two_col(left, right))

    if batches:
        _section_heading(elements, "Batch History")
        b_rows = []
        for b in batches:
            date_str = b["created_at"][:10] if b.get("created_at") else "—"
            passed_str = f"{b['charts_passed']}/{b.get('chart_count', '?')}" if b.get("charts_passed") is not None else "—"
            b_rows.append([
                Paragraph(b["batch_name"], NORMAL), Paragraph(b.get("specialty") or "—", NORMAL),
                Paragraph(date_str, NORMAL), Paragraph(str(b.get("chart_count", "—")), NORMAL),
                _score_cell(b.get("avg_score"), pass_threshold=pt), Paragraph(passed_str, NORMAL),
            ])
        elements.append(_data_table(
            ["Batch", "Specialty", "Date", "Charts", "Avg Grading Score", "Passed"],
            b_rows, [2.2, 1.3, 1.1, 0.8, 1.1, 0.9],
        ))

    _footer_note(elements)
    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    return buf.getvalue()


def generate_batch_report_pdf(insights: dict) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf)
    elements = []
    bs = insights["batch_summary"]

    pt = insights.get("pass_threshold", 80)
    # State the bar the scores in here are judged against. Without it a reader
    # has to know the specialty's threshold to tell a good report from a bad
    # one, and the thresholds differ by specialty.
    subtitles = [f"Batch: {insights['batch_name']}  |  Specialty: {insights['specialty']}",
                 f"Pass mark: {pt}% per chart"]
    if insights.get("is_direct_assignment"):
        subtitles[0] += "  |  Direct assignment"
    _header(elements, "Batch Performance Report", subtitles)
    headline, detail, color, bg, border = _batch_verdict(bs, pass_threshold=pt)
    elements.append(_verdict_box(headline, detail, color, bg, border))
    elements.append(Spacer(1, 12))

    stats = [
        (str(bs["n_coders"]), "Coders"),
        (str(bs["total_graded"]), "Total Charts Coded"),
        (f"{bs['pass_rate']}%", "Chart Pass Rate"),
        (f"{bs['avg_score']}%", "Avg Grading Score"),
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
            Paragraph(f"<b>Highest score:</b> <font color='#1A7A4C'><b>{bs['highest_score']}%</b></font> — {hi_names}", callout_style),
        ], [
            Paragraph(f"<b>Lowest score:</b> <font color='#B23A33'><b>{bs['lowest_score']}%</b></font> — {lo_names}", callout_style),
        ]]
        t = Table(rows, colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CREAM_PANEL),
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ]))
        elements.append(t)

    if bs.get("prior_batch_name"):
        elements.append(Spacer(1, 6))
        delta = bs.get("pass_rate_delta") or 0
        delta_hex = "#1A7A4C" if delta > 0 else "#B23A33" if delta < 0 else "#6B6457"
        trend_label = "↑ improving" if delta > 0 else "↓ declining" if delta < 0 else "→ flat"
        elements.append(Paragraph(
            f"vs prior batch ({bs['prior_batch_name']}, {bs['prior_batch_pass_rate']}% chart pass rate): "
            f"<font color='{delta_hex}'><b>{'+' if delta > 0 else ''}{delta}% — {trend_label}</b></font>",
            ParagraphStyle("trendline", parent=NORMAL, textColor=colors.HexColor("#33312b"))
        ))

    sd = insights.get("score_distribution") or []
    if sd:
        _section_heading(elements, "Score Distribution (cumulative chart-weighted score)")
        donut = _donut_chart(sd)
        legend_rows = []
        for b in sd:
            style = ParagraphStyle("sdLegend", parent=NORMAL, textColor=colors.HexColor(b["color"]), fontName="Helvetica-Bold")
            legend_rows.append([Paragraph(f"● {b['count']} coder{'s' if b['count'] != 1 else ''} scored {b['label']}", style)])
        legend = Table(legend_rows, colWidths=[CONTENT_W - 170])
        legend.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
        combo = Table([[donut, legend]], colWidths=[160, CONTENT_W - 160])
        combo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        elements.append(combo)
        elements.append(Spacer(1, 8))
        sd_rows = []
        for b in sd:
            style = ParagraphStyle("sd", parent=NORMAL, textColor=colors.HexColor(b["color"]), fontName="Helvetica-Bold")
            sd_rows.append([Paragraph(b["label"], style), Paragraph(str(b["count"]), NORMAL), Paragraph(", ".join(b["coders"]), NORMAL)])
        elements.append(_data_table(["Score Range", "Coders", "Names"], sd_rows, [1, 1, 4]))

    te = insights.get("team_errors") or {}
    if te.get("by_issue_type") or te.get("by_section"):
        _section_heading(elements, "Team Error Patterns")
        both = bool(te.get("by_issue_type")) and bool(te.get("by_section"))
        tbl_width = HALF_W if both else CONTENT_W
        left = None
        if te.get("by_issue_type"):
            issue_rows = [[Paragraph(e["type"].replace("_", " "), NORMAL), Paragraph(str(e["count"]), NORMAL), Paragraph(f"{e['pct']}%", NORMAL)] for e in te["by_issue_type"]]
            left = _data_table(["Issue Type", "Count", "Share"], issue_rows, [2, 1, 1], width=tbl_width)
        right = None
        if te.get("by_section"):
            sec_rows = [[Paragraph(s["section"], NORMAL), Paragraph(str(s["count"]), NORMAL), Paragraph(f"{s['pct']}%", NORMAL)] for s in te["by_section"]]
            right = _data_table(["Section", "Count", "Share"], sec_rows, [2, 1, 1], width=tbl_width)
        if left and right:
            elements.append(_two_col(left, right))
        elif left:
            elements.append(left)
        elif right:
            elements.append(right)

    top_p = insights.get("top_performers") or []
    bottom_p = insights.get("bottom_performers") or []
    _section_heading(elements, "Coder Performance")
    left = _ranked_box("Top Performers", top_p, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {_coder_label(c)} — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Needs Attention", bottom_p, AMBER if bottom_p else GREEN, AMBER_BG if bottom_p else GREEN_BG, AMBER_BORDER if bottom_p else GREEN_BORDER,
                         f"None — every coder is at or above {pt}%",
                         lambda i, c: Paragraph(f"#{i+1} {_coder_label(c)} — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    top_c = insights.get("top_categories") or []
    bottom_c = insights.get("bottom_categories") or []
    cat_perf = insights.get("category_performance") or []
    _section_heading(elements, "Category Performance")
    if cat_perf:
        elements.append(_category_bar_chart(cat_perf, label_key="category"))
        elements.append(Spacer(1, 8))
    left = _ranked_box("Top Categories", top_c, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {c['category']} ({c['attempt_count']}) — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Bottom Categories", bottom_c, RED if bottom_c else GREEN, RED_BG if bottom_c else GREEN_BG, RED_BORDER if bottom_c else GREEN_BORDER,
                         f"None — every category is at or above {pt}%",
                         lambda i, c: Paragraph(f"#{i+1} {c['category']} ({c['attempt_count']}) — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    top_ch = insights.get("top_charts") or []
    bottom_ch = insights.get("bottom_charts") or []
    _section_heading(elements, "Chart Performance")
    left = _ranked_box("Top Charts", top_ch, GREEN, GREEN_BG, GREEN_BORDER, "No data",
                        lambda i, c: Paragraph(f"#{i+1} {c['chart_number']} ({c['category']}) — <b>{c['avg_score']}%</b>", NORMAL))
    right = _ranked_box("Bottom Charts", bottom_ch, RED if bottom_ch else GREEN, RED_BG if bottom_ch else GREEN_BG, RED_BORDER if bottom_ch else GREEN_BORDER,
                         f"None — every chart is at or above {pt}%",
                         lambda i, c: Paragraph(f"#{i+1} {c['chart_number']} ({c['category']}) — <b>{c['avg_score']}%</b>", NORMAL))
    elements.append(_two_col(left, right))

    if te.get("top_missed_codes"):
        _section_heading(elements, "Top Missed Codes (team-wide)")
        mc_rows = [[Paragraph(m["code"], NORMAL), Paragraph(f"missed {m['count']}×", NORMAL)] for m in te["top_missed_codes"]]
        elements.append(_data_table(["Code", "Frequency"], mc_rows, [1, 1]))

    _footer_note(elements)
    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    return buf.getvalue()


# ── Assessment PDF Reports ────────────────────────────────────────────────────

def generate_assessment_coder_report_pdf(coder_name: str, data: dict) -> bytes:
    """PDF report for a single coder's assessment history."""
    buf = io.BytesIO()
    doc = _doc(buf)
    elements = []

    emp_id = data.get("employee_id")
    subtitle = f"Coder: {coder_name}  |  Emp ID: {emp_id}" if emp_id else f"Coder: {coder_name}"
    _header(elements, "Assessment Performance Report", [subtitle])

    avg_score = data.get("avg_score") or 0
    total = data.get("total_assessments_taken", 0)
    pass_rate = data.get("pass_rate") or 0
    PASS_THRESHOLD = 90

    if avg_score >= PASS_THRESHOLD:
        headline, color, bg, border = "STRONG PERFORMER", GREEN, GREEN_BG, GREEN_BORDER
    elif avg_score >= 80:
        headline, color, bg, border = "ON TRACK", AMBER, AMBER_BG, AMBER_BORDER
    else:
        headline, color, bg, border = "NEEDS IMPROVEMENT", RED, RED_BG, RED_BORDER

    detail = f"{avg_score}% average across {total} assessments. Pass rate: {pass_rate}%."
    elements.append(_verdict_box(headline, detail, color, bg, border))
    elements.append(Spacer(1, 12))

    def _fmt_time(sec):
        if sec is None:
            return "—"
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m}m {s}s"

    stats = [
        (str(total), "Assessments Taken"),
        (f"{avg_score}%", "Avg Grading Score"),
        (f"{pass_rate}%", "Pass Rate"),
        (f"{data.get('best_score', 0)}%", "Best Score"),
        (f"{data.get('worst_score', 0)}%", "Worst Score"),
        (_fmt_time(data.get("avg_time_seconds")), "Avg Time"),
    ]
    elements.append(_stat_row(stats))
    elements.append(Spacer(1, 12))

    score_trend = data.get("score_trend") or []
    if len(score_trend) >= 2:
        _section_heading(elements, "Grading Score Trend")
        trend_points = [
            (st["submitted_at"][:10] if st.get("submitted_at") else "", st["score_pct"])
            for st in score_trend
        ]
        elements.append(_trend_line_chart(trend_points))
        elements.append(Spacer(1, 8))

    topic_strength = data.get("topic_strength") or []
    if topic_strength:
        _section_heading(elements, "Topic Performance")
        sorted_topics = sorted(topic_strength, key=lambda t: (t.get("accuracy_pct") or 0))
        elements.append(_category_bar_chart(sorted_topics, label_key="topic", score_key="accuracy_pct"))
        elements.append(Spacer(1, 6))
        topic_rows = [
            [
                Paragraph(t["topic"], NORMAL),
                _score_cell(t.get("accuracy_pct"), pass_threshold=PASS_THRESHOLD),
                Paragraph(f"{t.get('correct', 0)}/{t.get('total', 0)}", NORMAL),
            ]
            for t in topic_strength
        ]
        elements.append(_data_table(["Topic", "Accuracy", "Correct/Total"], topic_rows, [3, 1, 1]))
        elements.append(Spacer(1, 12))

    difficulty_breakdown = data.get("difficulty_breakdown") or []
    if difficulty_breakdown:
        _section_heading(elements, "Difficulty Breakdown")
        diff_rows = [
            [
                Paragraph(d["difficulty"], NORMAL),
                _score_cell(d.get("accuracy_pct"), pass_threshold=PASS_THRESHOLD),
                Paragraph(f"{d.get('correct', 0)}/{d.get('total', 0)}", NORMAL),
            ]
            for d in difficulty_breakdown
        ]
        elements.append(_data_table(["Difficulty", "Accuracy", "Correct/Total"], diff_rows, [2, 1, 1]))
        elements.append(Spacer(1, 12))

    if topic_strength:
        strong_topics = [t for t in topic_strength if (t.get("accuracy_pct") or 0) >= PASS_THRESHOLD]
        weak_topics = [t for t in topic_strength if (t.get("accuracy_pct") or 0) < 80]
        left = _ranked_box(
            "Strong Topics (>=90%)", strong_topics, GREEN, GREEN_BG, GREEN_BORDER, "None at 90%+ yet",
            lambda i, t: Paragraph(f"{t['topic']} — {t.get('accuracy_pct', 0)}%", NORMAL),
        )
        right = _ranked_box(
            "Weak Topics (<80%)", weak_topics, RED if weak_topics else GREEN,
            RED_BG if weak_topics else GREEN_BG, RED_BORDER if weak_topics else GREEN_BORDER,
            "None — all topics above 80%",
            lambda i, t: Paragraph(f"{t['topic']} — {t.get('accuracy_pct', 0)}%", NORMAL),
        )
        elements.append(_two_col(left, right))
        elements.append(Spacer(1, 12))

    session_history = data.get("session_history") or []
    if session_history:
        _section_heading(elements, "Assessment History")
        pass_style_green = ParagraphStyle("passg", parent=NORMAL, textColor=GREEN, fontName="Helvetica-Bold")
        pass_style_red = ParagraphStyle("passr", parent=NORMAL, textColor=RED, fontName="Helvetica-Bold")
        hist_rows = []
        for sh in session_history:
            date_str = sh["submitted_at"][:10] if sh.get("submitted_at") else "—"
            pf = sh.get("pass_fail", "FAIL")
            result_p = Paragraph(pf, pass_style_green if pf == "PASS" else pass_style_red)
            hist_rows.append([
                Paragraph(sh.get("assessment_name", "—"), NORMAL),
                Paragraph(date_str, NORMAL),
                _score_cell(sh.get("score_pct"), pass_threshold=PASS_THRESHOLD),
                Paragraph(f"{sh.get('correct_count', 0)}/{sh.get('total_questions', 0)}", NORMAL),
                Paragraph(_fmt_time(sh.get("time_taken_seconds")), NORMAL),
                result_p,
            ])
        elements.append(_data_table(
            ["Assessment", "Date", "Score", "Correct", "Time", "Result"],
            hist_rows, [2.5, 1.2, 1, 1, 1, 0.8],
        ))

    _footer_note(elements)
    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    return buf.getvalue()


def generate_assessment_batch_report_pdf(data: dict) -> bytes:
    """PDF report for a batch of assessments."""
    buf = io.BytesIO()
    doc = _doc(buf)
    elements = []

    batch_name = data.get("batch_name", "Unknown Batch")
    assessment_count = data.get("assessment_count", 0)
    total_coders = data.get("total_coders", 0)
    submitted_count = data.get("submitted_count", 0)
    avg_score = data.get("avg_score") or 0
    pass_rate = data.get("pass_rate") or 0
    PASS_THRESHOLD = 90

    _header(elements, "Batch Performance Report", [
        f"Batch: {batch_name}  |  {assessment_count} Assessments  |  {total_coders} Coders",
    ])

    if pass_rate >= PASS_THRESHOLD:
        headline, color, bg, border = "STRONG BATCH", GREEN, GREEN_BG, GREEN_BORDER
    elif pass_rate >= 75:
        headline, color, bg, border = "ACCEPTABLE", AMBER, AMBER_BG, AMBER_BORDER
    else:
        headline, color, bg, border = "BELOW TARGET", RED, RED_BG, RED_BORDER

    detail = f"{pass_rate}% pass rate across {submitted_count} submissions. Average score: {avg_score}%."
    elements.append(_verdict_box(headline, detail, color, bg, border))
    elements.append(Spacer(1, 12))

    stats = [
        (str(assessment_count), "Assessments"),
        (str(total_coders), "Coders"),
        (str(submitted_count), "Submitted"),
        (f"{pass_rate}%", "Pass Rate"),
        (f"{avg_score}%", "Avg Grading Score"),
    ]
    elements.append(_stat_row(stats))
    elements.append(Spacer(1, 12))

    weak_topics = data.get("weak_topics") or []
    strong_topics = data.get("strong_topics") or []
    _section_heading(elements, "Training Need Identification")
    left = _ranked_box(
        "Weak Topics (Need Training)", weak_topics,
        AMBER if weak_topics else GREEN,
        AMBER_BG if weak_topics else GREEN_BG,
        AMBER_BORDER if weak_topics else GREEN_BORDER,
        "None — all topics above 80%",
        lambda i, t: Paragraph(f"{t['topic']} — {t.get('accuracy_pct', 0)}%", NORMAL),
    )
    right = _ranked_box(
        "Strong Topics (Well Performed)", strong_topics, GREEN, GREEN_BG, GREEN_BORDER,
        "None above 90% yet",
        lambda i, t: Paragraph(f"{t['topic']} — {t.get('accuracy_pct', 0)}%", NORMAL),
    )
    elements.append(_two_col(left, right))
    elements.append(Spacer(1, 12))

    topic_summary = data.get("topic_summary") or []
    if topic_summary:
        _section_heading(elements, "Topic Accuracy")
        sorted_ts = sorted(topic_summary, key=lambda t: (t.get("accuracy_pct") or 0))
        elements.append(_category_bar_chart(sorted_ts, label_key="topic", score_key="accuracy_pct"))
        elements.append(Spacer(1, 6))
        ts_rows = [
            [
                Paragraph(t["topic"], NORMAL),
                _score_cell(t.get("accuracy_pct"), pass_threshold=PASS_THRESHOLD),
                Paragraph(f"{t.get('correct', 0)}/{t.get('total', 0)}", NORMAL),
            ]
            for t in topic_summary
        ]
        elements.append(_data_table(["Topic", "Accuracy", "Correct/Total"], ts_rows, [3, 1, 1]))
        elements.append(Spacer(1, 12))

    coder_rows = data.get("coder_rows") or []
    if coder_rows:
        _section_heading(elements, "Coder Performance")
        sorted_coders = sorted(coder_rows, key=lambda c: -(c.get("latest_score") or 0))
        delta_green = ParagraphStyle("dg", parent=NORMAL, textColor=GREEN, fontName="Helvetica-Bold")
        delta_red = ParagraphStyle("dr", parent=NORMAL, textColor=RED, fontName="Helvetica-Bold")
        delta_gray = ParagraphStyle("dgr", parent=NORMAL, textColor=GRAY)
        cr_rows = []
        for c in sorted_coders:
            delta = c.get("delta")
            if delta is None:
                delta_p = Paragraph("—", delta_gray)
            elif delta > 0:
                delta_p = Paragraph(f"+{delta}", delta_green)
            elif delta < 0:
                delta_p = Paragraph(str(delta), delta_red)
            else:
                delta_p = Paragraph("0", delta_gray)
            cr_rows.append([
                Paragraph(c.get("coder_name", "—"), NORMAL),
                _score_cell(c.get("latest_score"), pass_threshold=PASS_THRESHOLD),
                delta_p,
                Paragraph(str(c.get("assessment_count", 0)), NORMAL),
            ])
        elements.append(_data_table(["Coder", "Score", "Delta Change", "Assessments"], cr_rows, [3, 1.2, 1, 1]))
        elements.append(Spacer(1, 12))

    assessments = data.get("assessments") or []
    if assessments:
        _section_heading(elements, "Assessments in Batch")
        a_rows = [
            [
                Paragraph(a.get("name", "—"), NORMAL),
                Paragraph(a["generated_at"][:10] if a.get("generated_at") else "—", NORMAL),
            ]
            for a in assessments
        ]
        elements.append(_data_table(["Assessment", "Date"], a_rows, [3, 1]))

    _footer_note(elements)
    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    return buf.getvalue()
