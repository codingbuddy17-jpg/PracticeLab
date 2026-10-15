#!/usr/bin/env python3
"""Builds PracticeLab_Chart_Inventory_Tracker.xlsx.

The operational companion to the composition taxonomy. The taxonomy says what
the pool SHOULD hold; this tracks what it actually holds, chart by chart, and
how far behind the build is.

The register starts empty by design: a row exists once a chart exists. What is
not yet sourced is a gap computed against the Topic Plan, not a thousand
placeholder rows nobody maintains.

Expected dates are derived from the HC build-hour rates and the FTE assigned,
so a slipping date is traceable to either a rate or a staffing assumption
rather than to someone's optimism.

Dated when it is built, not when someone remembered to change a string.
"""
import datetime as _dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule, DataBarRule

from _chart_taxonomy_data import POOLS, TOPICS, priority_of

BUILT = _dt.date.today().strftime("%d %B %Y")
OUT = "docs/PracticeLab_Chart_Inventory_Tracker.xlsx"

# One palette, used everywhere. Ink colours first, then surfaces, then the
# four semantic states. Nothing in this file picks a colour that is not here:
# a tracker where red means two different things is a tracker nobody trusts.
NAVY = "1F3864"        # headers, titles, the primary figure in a tile
NAVY_MID = "2F5597"    # section bars
ACCENT = "2E75B6"      # rules and emphasis
GREY = "595959"        # secondary text
INK = "212121"

HDR_BG = "DCE6F1"      # subheading surface
BAND_BG = "EEF3F9"     # computed columns, and the darker band row
BAND_ALT = "F7FAFD"    # zebra striping on long tables
NOTE_BG = "FFF4E5"     # explanatory notes
EDIT_BG = "FFF8E1"     # cells a person is meant to type in
CARD_BG = "F4F8FC"     # KPI tile surface

GREEN, GREEN_BG = "1B6B3A", "E6F4EA"    # good: complete, on track, closed
AMBER, AMBER_BG = "9C6500", "FFF4D6"    # watch: stalled, on hold, approaching
RED, RED_BG = "A4262C", "FCE8E6"        # act now: behind, blocker, overdue
BLUE, BLUE_BG = "1F5C99", "E7F0FA"      # in flight: in build

F_TITLE = Font(name="Calibri", bold=True, size=16, color=NAVY)
F_SUB = Font(name="Calibri", size=10, italic=True, color=GREY)
F_H = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
F_SEC = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
F_B = Font(name="Calibri", bold=True, size=10, color=INK)
F_N = Font(name="Calibri", size=10, color=INK)
F_SM = Font(name="Calibri", size=9, color=GREY)
F_AUTO = Font(name="Calibri", size=9, italic=True, color=GREY)
F_TILE_LAB = Font(name="Calibri", bold=True, size=10, color=NAVY)
F_TILE_VAL = Font(name="Calibri", bold=True, size=14, color=NAVY)

FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_SEC = PatternFill("solid", fgColor=NAVY_MID)
FILL_SUBH = PatternFill("solid", fgColor=HDR_BG)
FILL_BAND = PatternFill("solid", fgColor=BAND_BG)
FILL_NOTE = PatternFill("solid", fgColor=NOTE_BG)
FILL_EDIT = PatternFill("solid", fgColor=EDIT_BG)
FILL_CARD = PatternFill("solid", fgColor=CARD_BG)
FILL_GREEN = PatternFill("solid", fgColor=GREEN_BG)
FILL_AMBER = PatternFill("solid", fgColor=AMBER_BG)
FILL_RED = PatternFill("solid", fgColor=RED_BG)
FILL_BLUE = PatternFill("solid", fgColor=BLUE_BG)
FILL_ACCENT = PatternFill("solid", fgColor=ACCENT)

THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")
TOP = Alignment(vertical="top")
CTR = Alignment(horizontal="center", vertical="center")
DATE_FMT = "dd-mmm-yy"

# ----------------------------------------------------------------- geometry
REG, REG_FIRST, REG_LAST = "Chart Register", 5, 1004
ISS, ISS_FIRST, ISS_LAST = "Issues Log", 5, 504
PLAN, PLAN_FIRST = "Topic Plan", 5
SCHED = "Schedule Model"

FLAT = [(spec, t) for spec, _, _, _ in POOLS
        for cat, parent, rows in TOPICS[spec][1] for t in rows]
PLAN_LAST = PLAN_FIRST + len(FLAT) - 1
SPEC_ROW = {}          # specialty -> row on Schedule Model
TOPIC_ROW = {}         # topic id  -> row on Topic Plan

# HC build hours per chart. The first four are the rates in the HC FTE Demand
# sheet. The last three have no HC row, so they are stated as assumptions and
# left editable rather than quietly averaged in.
BUILD_HRS = {
    "IP-DRG": (3.0, "HC FTE Demand"),
    "ED Facility": (1.5, "HC FTE Demand"),
    "ED Profee": (3.0, "Assumption — E/M rate, no HC row"),
    "E/M": (3.0, "HC FTE Demand"),
    "SDS": (1.5, "HC FTE Demand"),
    "Surgery": (3.0, "Assumption — no HC row"),
    "ED Single Path": (3.0, "Assumption — dual-coded, no HC row"),
}
EFF_HRS_FTE_YR = 1795.5     # HC Assumptions, section E
UTILISATION = 0.95          # HC Assumptions, section E
GAP_THRESHOLD = 0.80        # HC Chart Selection, section 9
REFRESH_ADD = 0.30          # HC Assumptions, section C
REFRESH_RETIRE = 0.10       # HC Assumptions, section C

STATUSES = ["Identified", "De-identified", "Built", "Validated", "Live",
            "On hold", "Retired"]
IN_BUILD = ["Identified", "De-identified", "Built", "Validated"]
TIERS = ["Basic", "Moderate", "Complex"]
SOURCE_TYPES = ["QA/QR-validated", "PL re-coded"]
CHANNELS = ["C1 High error rate", "C2 High dollar value",
            "C3 Targeted PDx / DRG", "C4 Smart recommendations",
            "C5 DRGV trending PCS / DRG", "C6 Customer escalations",
            "C7 Denial trends", "C8 Foundation"]
ISSUE_TYPES = ["Answer key disputed", "Answer key suspected wrong",
               "Documentation incomplete after de-ID", "PHI found after publish",
               "Client permission not confirmed", "Chart too easy",
               "Chart too long for practice time", "Duplicate of existing chart",
               "Code set out of date", "Validation failed",
               "Specialty or topic misclassified", "Other"]
SEVERITIES = ["Blocker", "High", "Medium", "Low"]
ISSUE_STATUS = ["Open", "In progress", "Resolved", "Will not fix"]

wb = Workbook()
wb.remove(wb.active)


TAB_COLOUR = {
    "Read Me": GREY, "Dashboard": NAVY, "Schedule Model": ACCENT,
    "Topic Plan": NAVY_MID, "Chart Register": GREEN, "Issues Log": RED,
    "Specialty View": NAVY_MID, "Refresh & Retirement": AMBER, "Lists": "BFBFBF",
}


def sheet(title, widths, freeze=None, grid=False):
    ws = wb.create_sheet(title)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.sheet_view.showGridLines = grid
    if freeze:
        ws.freeze_panes = freeze
    if title in TAB_COLOUR:
        ws.sheet_properties.tabColor = TAB_COLOUR[title]
    return ws


def section(ws, row, text, span):
    """A full-width navy bar. Used instead of bold text so the eye finds the
    breaks on a sheet that is mostly numbers."""
    c = ws.cell(row=row, column=1, value="  " + text)
    c.font, c.fill, c.alignment = F_SEC, FILL_SEC, Alignment(vertical="center")
    for i in range(2, span + 1):
        ws.cell(row=row, column=i).fill = FILL_SEC
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = 20


def zebra(ws, first, last, last_col):
    """Striping as a conditional format rather than per-cell fills: one rule
    instead of tens of thousands of styled cells, so the file stays small and
    inserting a row does not break the pattern."""
    ws.conditional_formatting.add(
        "A%d:%s%d" % (first, get_column_letter(last_col), last),
        FormulaRule(formula=["MOD(ROW(),2)=0"],
                    fill=PatternFill("solid", fgColor=BAND_ALT)))


def title_block(ws, title, sub, span):
    ws["A1"] = title
    ws["A1"].font = F_TITLE
    ws["A1"].alignment = Alignment(vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    ws["A2"] = sub
    ws["A2"].font = F_SUB
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 14
    # a thin accent rule under the title, so every sheet opens the same way
    for i in range(1, span + 1):
        ws.cell(row=3, column=i).fill = FILL_ACCENT
    ws.row_dimensions[3].height = 3


HDR_BORDER = Border(left=Side(style="thin", color=NAVY),
                    right=Side(style="thin", color=NAVY),
                    top=Side(style="thin", color=NAVY),
                    bottom=Side(style="medium", color=ACCENT))


def header_row(ws, row, labels, height=34):
    for c, lab in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=c, value=lab)
        cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, HDR_BORDER
    ws.row_dimensions[row].height = height


def note(ws, row, text, span, fill=FILL_NOTE):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.fill, c.alignment = F_SM, fill, WRAP
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = max(14, 13 * (1 + len(text) // 150))


def rng(sheet_name, col, first=REG_FIRST, last=REG_LAST):
    return "'%s'!$%s$%d:$%s$%d" % (sheet_name, col, first, col, last)


# register column letters, so a formula names the thing rather than a letter
R = dict(zip(
    "id spec topic topic_name category priority tier source client channel "
    "objective version owner status d_ident d_deid d_built d_valid d_live "
    "d_retired d_expected days_late stage_age usage issue notes".split(),
    [get_column_letter(i) for i in range(1, 27)]))
I = dict(zip(
    "id raised chart topic spec type severity desc by owner status target "
    "resolved days_open overdue resolution".split(),
    [get_column_letter(i) for i in range(1, 17)]))

# ===================================================== Schedule Model first
# The Topic Plan's expected dates reference this sheet, so it is built first.
ws = sheet(SCHED, [22, 12, 13, 13, 11, 13, 12, 15, 46], freeze=None)
title_block(ws, "Schedule Model — where the expected dates come from", "Derived from the HC build-hour rates and the FTE assigned. Shaded cells are inputs; every date in this workbook moves when they change.", 9)

section(ws, 4, "PROGRAMME INPUTS", 9)
INPUTS = [
    ("Programme start date", _dt.date.today(), "date",
     "The day building begins. Expected dates are measured forward from here."),
    ("Effective hours per FTE per year", EFF_HRS_FTE_YR, "num",
     "HC Assumptions section E. Already net of the utilisation buffer below."),
    ("Productive utilisation target", UTILISATION, "pct",
     "HC Assumptions section E. Shown for traceability; it is baked into the line above, so changing it here changes nothing on its own."),
    ("Gap threshold", GAP_THRESHOLD, "pct",
     "HC Chart Selection section 9. A topic below this share of its target triggers targeted sourcing."),
]
r = 5
for lab, val, kind, why in INPUTS:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.alignment, a.border = F_B, FILL_SUBH, TOP, BOX
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    b = ws.cell(row=r, column=3, value=val)
    b.font, b.fill, b.border, b.alignment = F_B, FILL_EDIT, BOX, CTR
    if kind == "date":
        b.number_format = DATE_FMT
    elif kind == "pct":
        b.number_format = "0%"
    c = ws.cell(row=r, column=4, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=9)
    ws.row_dimensions[r].height = max(16, 12 * (1 + len(why) // 90))
    r += 1
START_CELL, EFF_CELL, THRESH_CELL = "$C$5", "$C$6", "$C$8"

r += 1
section(ws, r, "BUILD EFFORT AND EXPECTED COMPLETION BY SPECIALTY", 9)
r += 1
header_row(ws, r, ["Specialty", "Target\ncharts", "Build hrs\nper chart", "Total build\nhours",
                   "FTE\nassigned", "Hours per\nweek", "Weeks\nrequired", "Expected\ncompletion",
                   "Build rate source"])
hdr = r
r += 1
first_spec = r
for spec, typ, pool, _src in POOLS:
    hrs, hsrc = BUILD_HRS[spec]
    SPEC_ROW[spec] = r
    vals = [spec, pool, hrs, "=B%d*C%d" % (r, r), 1.0,
            "=%s/52*E%d" % (EFF_CELL, r),
            "=IF(F%d=0,\"NA\",D%d/F%d)" % (r, r, r),
            "=IF(F%d=0,\"NA\",INT(%s+G%d*7))" % (r, START_CELL, r), hsrc]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c in (3, 5):
            cell.fill = FILL_EDIT
        if c == 4:
            cell.number_format = "#,##0"
        if c in (6, 7):
            cell.number_format = "0.0"
        if c == 8:
            cell.number_format = DATE_FMT
        if c == 9:
            cell.font, cell.alignment = F_SM, WRAP
    r += 1
last_spec = r - 1
tr = r
for c, v in [(1, "TOTAL"), (2, "=SUM(B%d:B%d)" % (first_spec, last_spec)),
             (4, "=SUM(D%d:D%d)" % (first_spec, last_spec)),
             (5, "=SUM(E%d:E%d)" % (first_spec, last_spec)),
             (7, "=MAX(G%d:G%d)" % (first_spec, last_spec)),
             (8, "=MAX(H%d:H%d)" % (first_spec, last_spec))]:
    cell = ws.cell(row=tr, column=c, value=v)
    cell.font, cell.fill, cell.border, cell.alignment = F_B, FILL_SUBH, BOX, CTR
    if c == 4:
        cell.number_format = "#,##0"
    if c == 7:
        cell.number_format = "0.0"
    if c == 8:
        cell.number_format = DATE_FMT
for c in (3, 6, 9):
    ws.cell(row=tr, column=c).fill = FILL_SUBH
    ws.cell(row=tr, column=c).border = BOX
ws.cell(row=tr, column=9, value="Weeks and date are the LONGEST specialty, not the sum — they run in parallel").font = F_SM
ws.cell(row=tr, column=9).alignment = WRAP

note(ws, tr + 2, "Weeks required assumes the FTE in column E works only on this specialty's initial build. It is elapsed build time, not the steady-state workload: HC's FTE Demand sheet adds refresh and batch handling on top, and a trainer doing both will take longer than column G says.", 9)
note(ws, tr + 3, "Hours per week divides the annual effective hours by 52, so it already carries HC's utilisation buffer and does not need a second haircut for leave or admin.", 9)
note(ws, tr + 4, "Three build rates are assumptions, not HC figures: ED Profee, Surgery and ED Single Path have no row in the HC model. Single Path is set at the E/M rate on the grounds that one chart carries two code sets, which is a guess worth revisiting once a few have actually been built.", 9, PatternFill("solid", fgColor="FDECEA"))
SCHED_WEEKS_COL = "G"

# ============================================================= Topic Plan
ws = sheet(PLAN, [17, 10, 40, 20, 14, 12, 19, 9, 9, 8, 9, 8, 9, 10, 9, 24, 13, 12, 9],
           freeze="C5")
title_block(ws, "Topic Plan — target against actual, topic by topic", "Targets come from the composition taxonomy. Everything from column I rightwards counts the register, so it is live the moment a chart is logged.", 19)
header_row(ws, 4, ["Specialty", "Topic ID", "Topic", "Coverage category", "Build\npriority",
                   "Difficulty\nskew", "Primary sourcing\nchannel", "Target\ncharts",
                   "Rows\nlogged", "Live", "In\nbuild", "On\nhold", "Retired",
                   "% of\ntarget", "Gap to\ntarget", "Gap status (HC section 9)",
                   "Expected\ncomplete", "Days vs\nexpected", "Open\nissues"])

# expected dates: cumulative share of a specialty's target, in build-priority order
ORDER = {"P1 — build first": 0, "P2": 1, "P3 — build last": 2}
plan_rows = []
for spec, typ, pool, _s in POOLS:
    items = []
    for cat, parent, rows in TOPICS[spec][1]:
        for t in rows:
            items.append((ORDER[priority_of(t[0])], cat, t))
    items.sort(key=lambda x: x[0])
    targets = [round(t[4] * pool) for _, _, t in items]
    total = sum(targets) or 1
    run = 0
    for (grp, cat, t), tgt in zip(items, targets):
        run += tgt
        plan_rows.append((spec, cat, t, tgt, run / total))

r = PLAN_FIRST
for spec, cat, t, tgt, frac in plan_rows:
    tid = t[0]
    TOPIC_ROW[tid] = r
    srow = SPEC_ROW[spec]
    vals = [
        spec, tid, t[1], cat, priority_of(tid), t[5], t[6], tgt,
        "=COUNTIFS(%s,$B%d)" % (rng(REG, R["topic"]), r),
        "=COUNTIFS(%s,$B%d,%s,\"Live\")" % (rng(REG, R["topic"]), r, rng(REG, R["status"])),
        "=I%d-J%d-L%d-M%d" % (r, r, r, r),
        "=COUNTIFS(%s,$B%d,%s,\"On hold\")" % (rng(REG, R["topic"]), r, rng(REG, R["status"])),
        "=COUNTIFS(%s,$B%d,%s,\"Retired\")" % (rng(REG, R["topic"]), r, rng(REG, R["status"])),
        "=IF($H%d=0,\"NA\",J%d/$H%d)" % (r, r, r),
        "=$H%d-J%d" % (r, r),
        ('=IF($H{r}=0,"NA",IF(J{r}>=$H{r},"Complete",'
         'IF(J{r}/$H{r}>=\'{s}\'!{th},"At or above threshold","BELOW THRESHOLD — source now")))'
         ).format(r=r, s=SCHED, th=THRESH_CELL),
        "=IF('%s'!$G$%d=\"NA\",\"NA\",INT('%s'!%s+%s*'%s'!$G$%d*7))"
        % (SCHED, srow, SCHED, START_CELL, repr(round(frac, 6)), SCHED, srow),
        ('=IF(OR($H{r}=0,NOT(ISNUMBER(Q{r}))),"NA",IF(J{r}>=$H{r},"On target",'
         'IF(TODAY()<=Q{r},"Not yet due",TODAY()-Q{r})))').format(r=r),
        "=COUNTIFS(%s,$B%d,%s,\"Open\")+COUNTIFS(%s,$B%d,%s,\"In progress\")"
        % (rng(ISS, I["topic"], ISS_FIRST, ISS_LAST), r,
           rng(ISS, I["status"], ISS_FIRST, ISS_LAST),
           rng(ISS, I["topic"], ISS_FIRST, ISS_LAST), r,
           rng(ISS, I["status"], ISS_FIRST, ISS_LAST)),
    ]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c == 2:
            cell.font, cell.alignment = F_B, CTR
        elif c == 3:
            cell.alignment = WRAP
        elif c in (4, 6, 7):
            cell.font, cell.alignment = F_SM, WRAP
        elif c == 5:
            cell.alignment = CTR
            cell.font = Font(size=9, bold=True,
                             color=(RED if priority_of(tid).startswith("P1")
                                    else GREY if priority_of(tid).startswith("P3") else "000000"))
        elif c == 14:
            cell.number_format = "0%"
            cell.alignment = CTR
        elif c == 16:
            cell.font, cell.alignment = F_SM, WRAP
        else:
            cell.alignment = CTR
        if c == 8:
            cell.font = F_B
        if c == 17:
            cell.number_format = DATE_FMT
    ws.row_dimensions[r].height = 26
    r += 1

ws.auto_filter.ref = "A4:S%d" % PLAN_LAST
tr = PLAN_LAST + 1
for c, v in [(1, "TOTAL"), (8, "=SUM(H%d:H%d)" % (PLAN_FIRST, PLAN_LAST)),
             (9, "=SUM(I%d:I%d)" % (PLAN_FIRST, PLAN_LAST)),
             (10, "=SUM(J%d:J%d)" % (PLAN_FIRST, PLAN_LAST)),
             (11, "=SUM(K%d:K%d)" % (PLAN_FIRST, PLAN_LAST)),
             (12, "=SUM(L%d:L%d)" % (PLAN_FIRST, PLAN_LAST)),
             (13, "=SUM(M%d:M%d)" % (PLAN_FIRST, PLAN_LAST)),
             (14, "=IF(H%d=0,\"NA\",J%d/H%d)" % (tr, tr, tr)),
             (15, "=H%d-J%d" % (tr, tr)),
             (16, "=COUNTIF(P%d:P%d,\"BELOW*\")&\" topics below threshold\"" % (PLAN_FIRST, PLAN_LAST)),
             (19, "=SUM(S%d:S%d)" % (PLAN_FIRST, PLAN_LAST))]:
    cell = ws.cell(row=tr, column=c, value=v)
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR
    if c == 1:
        cell.alignment = TOP
    if c == 14:
        cell.number_format = "0%"
    if c == 16:
        cell.alignment = WRAP
for c in range(1, 20):
    if ws.cell(row=tr, column=c).value is None:
        ws.cell(row=tr, column=c).fill = FILL_H
        ws.cell(row=tr, column=c).border = BOX

zebra(ws, PLAN_FIRST, PLAN_LAST, 19)
ws.conditional_formatting.add(
    "N%d:N%d" % (PLAN_FIRST, PLAN_LAST),
    DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                color=ACCENT, showValue=True, minLength=None, maxLength=None))
ws.conditional_formatting.add(
    "P%d:P%d" % (PLAN_FIRST, PLAN_LAST),
    FormulaRule(formula=['ISNUMBER(SEARCH("BELOW",$P%d))' % PLAN_FIRST],
                fill=FILL_RED, font=Font(size=9, bold=True, color=RED)))
ws.conditional_formatting.add(
    "P%d:P%d" % (PLAN_FIRST, PLAN_LAST),
    FormulaRule(formula=['$P%d="Complete"' % PLAN_FIRST],
                fill=FILL_GREEN, font=Font(size=9, bold=True, color=GREEN)))
ws.conditional_formatting.add(
    "P%d:P%d" % (PLAN_FIRST, PLAN_LAST),
    FormulaRule(formula=['$P%d="At or above threshold"' % PLAN_FIRST],
                fill=FILL_BLUE, font=Font(size=9, bold=True, color=BLUE)))
ws.conditional_formatting.add(
    "R%d:R%d" % (PLAN_FIRST, PLAN_LAST),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add(
    "S%d:S%d" % (PLAN_FIRST, PLAN_LAST),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
# P1 topics carry a tinted priority cell so the build order is visible unsorted
ws.conditional_formatting.add(
    "E%d:E%d" % (PLAN_FIRST, PLAN_LAST),
    FormulaRule(formula=['LEFT($E%d,2)="P1"' % PLAN_FIRST],
                fill=FILL_AMBER, font=Font(size=9, bold=True, color=AMBER)))

note(ws, tr + 2, "Rows logged counts every register row for the topic whatever its status. Live counts only charts actually in the pool. In build is the difference less on-hold and retired, so a chart sitting at Identified for a month still shows as in build — which is the point, and the Dashboard's stage ageing is where it surfaces.", 19)
note(ws, tr + 3, "% of target has Live as its numerator and the taxonomy target as its denominator. A topic with no target reads NA, not 0% — NA is a real value here and means no target was set, which is a different thing from nothing built.", 19)
note(ws, tr + 4, "Days vs expected is positive when the expected date has passed and the target is not met. It reads On target once Live reaches the target, whenever that happened, and NA before a schedule exists.", 19)

# ============================================================ Lists sheet
wsL = sheet("Lists", [26, 26, 20, 18, 16, 34, 14, 16], freeze=None)
title_block(wsL, "Dropdown lists", "The source for every dropdown in this workbook. Add a value here and it appears in the register — do not type a new value straight into a cell.", 8)
LISTS = [
    ("Specialty", [s for s, _, _, _ in POOLS]),
    ("Topic ID", [t[0] for _, _, t, _, _ in plan_rows]),
    ("Status", STATUSES),
    ("Difficulty tier", TIERS),
    ("Source type", SOURCE_TYPES),
    ("Sourcing channel", CHANNELS),
    ("Issue severity", SEVERITIES),
    ("Issue status", ISSUE_STATUS),
]
for ci, (name, vals) in enumerate(LISTS, start=1):
    h = wsL.cell(row=4, column=ci, value=name)
    h.font, h.fill, h.alignment, h.border = F_H, FILL_H, WRAP_C, BOX
    for i, v in enumerate(vals):
        c = wsL.cell(row=5 + i, column=ci, value=v)
        c.font, c.border = F_N, BOX
LIST_REF = {}
for ci, (name, vals) in enumerate(LISTS, start=1):
    col = get_column_letter(ci)
    LIST_REF[name] = "Lists!$%s$5:$%s$%d" % (col, col, 4 + len(vals))
# issue types need more room than the grid above
ic = len(LISTS) + 1
h = wsL.cell(row=4, column=ic, value="Issue type")
h.font, h.fill, h.alignment, h.border = F_H, FILL_H, WRAP_C, BOX
wsL.column_dimensions[get_column_letter(ic)].width = 40
for i, v in enumerate(ISSUE_TYPES):
    c = wsL.cell(row=5 + i, column=ic, value=v)
    c.font, c.border = F_N, BOX
LIST_REF["Issue type"] = "Lists!$%s$5:$%s$%d" % (get_column_letter(ic), get_column_letter(ic), 4 + len(ISSUE_TYPES))

# ========================================================= Chart Register
REG_COLS = [
    ("Chart ID", 13), ("Specialty", 16), ("Topic ID", 10), ("Topic (auto)", 34),
    ("Coverage category (auto)", 20), ("Priority (auto)", 13), ("Difficulty tier", 12),
    ("Source type", 17), ("Client / facility ref", 17), ("Primary channel", 19),
    ("Learning objective", 34), ("Code-set version", 13), ("Owner", 15),
    ("Status", 14), ("Date identified", 12), ("Date de-identified", 12),
    ("Date built", 12), ("Date validated", 12), ("Date live", 12),
    ("Date retired", 12), ("Expected live date", 13), ("Days late (auto)", 11),
    ("Days in stage (auto)", 11), ("Batches used", 10), ("Open issues (auto)", 11),
    ("Notes", 40),
]
ws = sheet(REG, [w for _, w in REG_COLS], freeze="D5")
title_block(ws, "Chart Register — one row per chart", "Starts empty: a row exists once a chart exists. Grey columns fill themselves from the Topic ID — do not type into them.", len(REG_COLS))
header_row(ws, 4, [n for n, _ in REG_COLS], height=42)

AUTO_COLS = (4, 5, 6, 22, 23, 25)
for r in range(REG_FIRST, REG_LAST + 1):
    f = {
        4: '=IF($C{r}="","",IFERROR(INDEX(\'{p}\'!$C${a}:$C${b},MATCH($C{r},\'{p}\'!$B${a}:$B${b},0)),"UNKNOWN TOPIC ID"))',
        5: '=IF($C{r}="","",IFERROR(INDEX(\'{p}\'!$D${a}:$D${b},MATCH($C{r},\'{p}\'!$B${a}:$B${b},0)),""))',
        6: '=IF($C{r}="","",IFERROR(INDEX(\'{p}\'!$E${a}:$E${b},MATCH($C{r},\'{p}\'!$B${a}:$B${b},0)),""))',
    }
    for c, tpl in f.items():
        cell = ws.cell(row=r, column=c,
                       value=tpl.format(r=r, p=PLAN, a=PLAN_FIRST, b=PLAN_LAST))
        cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, TOP
    # days late: expected date passed and the chart is not live yet
    cell = ws.cell(row=r, column=22, value=(
        '=IF(OR($A{r}="",$U{r}=""),"",IF($S{r}<>"",MAX(0,$S{r}-$U{r}),'
        'MAX(0,TODAY()-$U{r})))').format(r=r))
    cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    # days in current stage: since the latest stage date reached
    cell = ws.cell(row=r, column=23, value=(
        '=IF($A{r}="","",IF(OR($N{r}="Live",$N{r}="Retired"),"",'
        'TODAY()-MAX($O{r},$P{r},$Q{r},$R{r})))').format(r=r))
    cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    cell = ws.cell(row=r, column=25, value=(
        '=IF($A{r}="","",COUNTIFS({ic},$A{r},{ist},"Open")+COUNTIFS({ic},$A{r},{ist},"In progress"))'
    ).format(r=r, ic=rng(ISS, I["chart"], ISS_FIRST, ISS_LAST),
             ist=rng(ISS, I["status"], ISS_FIRST, ISS_LAST)))
    cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    for c in range(1, len(REG_COLS) + 1):
        if c in AUTO_COLS:
            continue
        cell = ws.cell(row=r, column=c)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if 15 <= c <= 21:
            cell.number_format = DATE_FMT
            cell.alignment = CTR
        elif c in (7, 14, 24):
            cell.alignment = CTR

for col, listname in [(R["spec"], "Specialty"), (R["topic"], "Topic ID"),
                      (R["tier"], "Difficulty tier"), (R["source"], "Source type"),
                      (R["channel"], "Sourcing channel"), (R["status"], "Status")]:
    dv = DataValidation(type="list", formula1="=%s" % LIST_REF[listname],
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick a value from the list. Add new values on the Lists sheet, not here."
    dv.errorTitle = "Not on the list"
    ws.add_data_validation(dv)
    dv.add("%s%d:%s%d" % (col, REG_FIRST, col, REG_LAST))

ws.auto_filter.ref = "A4:%s%d" % (get_column_letter(len(REG_COLS)), REG_LAST)
zebra(ws, REG_FIRST, REG_LAST, len(REG_COLS))
# one colour per status, so a filtered register reads as a state board
for _st, (_fill, _col) in {
        "Live": (FILL_GREEN, GREEN), "On hold": (FILL_AMBER, AMBER),
        "Retired": (PatternFill("solid", fgColor=BAND_BG), GREY),
        "Identified": (FILL_BLUE, BLUE), "De-identified": (FILL_BLUE, BLUE),
        "Built": (FILL_BLUE, BLUE), "Validated": (FILL_BLUE, BLUE)}.items():
    ws.conditional_formatting.add(
        "N%d:N%d" % (REG_FIRST, REG_LAST),
        FormulaRule(formula=['$N%d="%s"' % (REG_FIRST, _st)],
                    fill=_fill, font=Font(size=10, bold=True, color=_col)))
ws.conditional_formatting.add(
    "D%d:D%d" % (REG_FIRST, REG_LAST),
    FormulaRule(formula=['$D%d="UNKNOWN TOPIC ID"' % REG_FIRST],
                fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add(
    "V%d:V%d" % (REG_FIRST, REG_LAST),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add(
    "W%d:W%d" % (REG_FIRST, REG_LAST),
    CellIsRule(operator="greaterThan", formula=["30"],
               fill=FILL_AMBER, font=Font(size=10, bold=True, color=AMBER)))
ws.conditional_formatting.add(
    "Y%d:Y%d" % (REG_FIRST, REG_LAST),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))

# ============================================================= Issues Log
ISS_COLS = [("Issue ID", 11), ("Date raised", 12), ("Chart ID", 13), ("Topic ID", 10),
            ("Specialty", 16), ("Issue type", 34), ("Severity", 11),
            ("Description", 50), ("Raised by", 15), ("Owner", 15), ("Status", 14),
            ("Target resolution", 13), ("Date resolved", 12), ("Days open (auto)", 11),
            ("Overdue (auto)", 13), ("Resolution", 44)]
ws = sheet(ISS, [w for _, w in ISS_COLS], freeze="C5")
title_block(ws, "Issues Log", "Anything that blocks a chart entering the pool or casts doubt on one already in it. An answer-key dispute belongs here the day it is raised, not after it is settled.", len(ISS_COLS))
header_row(ws, 4, [n for n, _ in ISS_COLS], height=42)

for r in range(ISS_FIRST, ISS_LAST + 1):
    cell = ws.cell(row=r, column=14, value=(
        '=IF($A{r}="","",IF($M{r}="",TODAY()-$B{r},$M{r}-$B{r}))').format(r=r))
    cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    cell = ws.cell(row=r, column=15, value=(
        '=IF(OR($A{r}="",$L{r}=""),"",IF(OR($K{r}="Resolved",$K{r}="Will not fix"),'
        '"Closed",IF(TODAY()>$L{r},"OVERDUE","On time")))').format(r=r))
    cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    for c in range(1, len(ISS_COLS) + 1):
        if c in (14, 15):
            continue
        cell = ws.cell(row=r, column=c)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c in (2, 12, 13):
            cell.number_format = DATE_FMT
            cell.alignment = CTR
        elif c in (7, 11):
            cell.alignment = CTR

for col, listname in [(I["spec"], "Specialty"), (I["topic"], "Topic ID"),
                      (I["type"], "Issue type"), (I["severity"], "Issue severity"),
                      (I["status"], "Issue status")]:
    dv = DataValidation(type="list", formula1="=%s" % LIST_REF[listname],
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick a value from the list. Add new values on the Lists sheet, not here."
    dv.errorTitle = "Not on the list"
    ws.add_data_validation(dv)
    dv.add("%s%d:%s%d" % (col, ISS_FIRST, col, ISS_LAST))

ws.auto_filter.ref = "A4:%s%d" % (get_column_letter(len(ISS_COLS)), ISS_LAST)
zebra(ws, ISS_FIRST, ISS_LAST, len(ISS_COLS))
ws.conditional_formatting.add(
    "O%d:O%d" % (ISS_FIRST, ISS_LAST),
    FormulaRule(formula=['$O%d="OVERDUE"' % ISS_FIRST],
                fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add(
    "O%d:O%d" % (ISS_FIRST, ISS_LAST),
    FormulaRule(formula=['$O%d="Closed"' % ISS_FIRST],
                fill=FILL_GREEN, font=Font(size=10, bold=True, color=GREEN)))
for _sev, (_fill, _col) in {"Blocker": (FILL_RED, RED), "High": (FILL_AMBER, AMBER),
                            "Medium": (FILL_BLUE, BLUE),
                            "Low": (PatternFill("solid", fgColor=BAND_BG), GREY)}.items():
    ws.conditional_formatting.add(
        "G%d:G%d" % (ISS_FIRST, ISS_LAST),
        FormulaRule(formula=['$G%d="%s"' % (ISS_FIRST, _sev)],
                    fill=_fill, font=Font(size=10, bold=True, color=_col)))
for _st, (_fill, _col) in {"Open": (FILL_RED, RED), "In progress": (FILL_AMBER, AMBER),
                           "Resolved": (FILL_GREEN, GREEN),
                           "Will not fix": (PatternFill("solid", fgColor=BAND_BG), GREY)}.items():
    ws.conditional_formatting.add(
        "K%d:K%d" % (ISS_FIRST, ISS_LAST),
        FormulaRule(formula=['$K%d="%s"' % (ISS_FIRST, _st)],
                    fill=_fill, font=Font(size=10, bold=True, color=_col)))
note(ws, ISS_LAST + 2, "An answer-key issue is not an ordinary defect. A wrong key silently grades everyone against it, so a chart with a suspected key problem goes On hold in the register until the issue is closed, rather than staying live while the dispute runs.", len(ISS_COLS), PatternFill("solid", fgColor="FDECEA"))
note(ws, ISS_LAST + 3, "Days open counts to today while the issue is open and freezes at the resolution date once it closes, so the column is a live age and a historical duration in the same place.", len(ISS_COLS))

# =============================================================== Dashboard
ws = sheet("Dashboard", [26, 13, 13, 13, 13, 13, 13, 13, 3, 30], freeze=None)
title_block(ws, "PracticeLab chart inventory — dashboard", "Everything here is a formula over the register, the plan and the issues log. Nothing is typed. Built %s; the figures are live whenever the file is opened." % BUILT, 10)

REG_STATUS = rng(REG, R["status"])
REG_LIVE_D = rng(REG, R["d_live"])
REG_RET_D = rng(REG, R["d_retired"])
REG_ID = rng(REG, R["id"])

in_build_sum = "+".join('COUNTIF(%s,"%s")' % (REG_STATUS, s) for s in IN_BUILD)

TILES = [
    ("Planned charts", "='%s'!$H$%d" % (PLAN, PLAN_LAST + 1),
     "Sum of every topic target. The size of the finished pool."),
    ("Live in the pool", '=COUNTIF(%s,"Live")' % REG_STATUS,
     "Charts available to a batch right now."),
    ("Pool complete", "=IF(B5=0,\"NA\",B6/B5)",
     "Live as a share of planned. Reads NA before any target exists."),
    ("In build", "=%s" % in_build_sum,
     "Logged and moving: identified, de-identified, built or validated, but not yet live."),
    ("Not yet sourced", '=MAX(0,B5-COUNTIF(%s,"<>"))' % REG_ID,
     "Planned charts with no register row at all. The sourcing backlog."),
    ("Added live, last 30 days", '=COUNTIFS(%s,">="&TODAY()-30,%s,"<="&TODAY())' % (REG_LIVE_D, REG_LIVE_D),
     "Charts that went live in the last month. The build rate, measured rather than assumed."),
    ("Retired, last 90 days", '=COUNTIFS(%s,">="&TODAY()-90,%s,"<="&TODAY())' % (REG_RET_D, REG_RET_D),
     "Recent retirements. HC policy retires 10% of the pool each half-yearly refresh."),
    ("On hold", '=COUNTIF(%s,"On hold")' % REG_STATUS,
     "Charts stopped by an unresolved issue. These are not in the pool and are not progressing."),
    ("Topics below threshold", '=COUNTIF(%s,"BELOW*")' % rng(PLAN, "P", PLAN_FIRST, PLAN_LAST),
     "Topics under the HC section 9 gap threshold. Each one triggers targeted sourcing."),
    ("Charts past expected date", '=COUNTIF(%s,">0")' % rng(REG, R["days_late"]),
     "Logged charts whose expected live date has passed and which are not live."),
    ("Stalled over 30 days", '=COUNTIF(%s,">30")' % rng(REG, R["stage_age"]),
     "Charts sitting in the same stage for over a month. Where the build is actually blocked."),
    ("Open issues", '=COUNTIF(%s,"Open")+COUNTIF(%s,"In progress")'
     % (rng(ISS, I["status"], ISS_FIRST, ISS_LAST), rng(ISS, I["status"], ISS_FIRST, ISS_LAST)),
     "Unresolved issues across every specialty."),
    ("Blocker issues open", '=COUNTIFS(%s,"Blocker",%s,"Open")+COUNTIFS(%s,"Blocker",%s,"In progress")'
     % (rng(ISS, I["severity"], ISS_FIRST, ISS_LAST), rng(ISS, I["status"], ISS_FIRST, ISS_LAST),
        rng(ISS, I["severity"], ISS_FIRST, ISS_LAST), rng(ISS, I["status"], ISS_FIRST, ISS_LAST)),
     "Issues stopping a chart outright. Clear these first."),
    ("Issues overdue", '=COUNTIF(%s,"OVERDUE")' % rng(ISS, I["overdue"], ISS_FIRST, ISS_LAST),
     "Open issues past their own target resolution date."),
]
# tone: "" neutral, "good" green when above zero, "warn" amber, "act" red
TONE = {"Live in the pool": "good", "Added live, last 30 days": "good",
        "In build": "flight", "On hold": "warn", "Stalled over 30 days": "warn",
        "Open issues": "warn", "Topics below threshold": "act",
        "Charts past expected date": "act", "Blocker issues open": "act",
        "Issues overdue": "act"}
TONE_STYLE = {"good": (FILL_GREEN, GREEN), "warn": (FILL_AMBER, AMBER),
              "act": (FILL_RED, RED), "flight": (FILL_BLUE, BLUE)}

r = 5
tiles_first = r
for lab, formula, why in TILES:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_TILE_LAB, FILL_CARD, BOX, Alignment(vertical="center", indent=1)
    b = ws.cell(row=r, column=2, value=formula)
    b.font, b.fill, b.border, b.alignment = F_TILE_VAL, FILL_CARD, BOX, CTR
    if lab == "Pool complete":
        b.number_format = "0.0%"
    else:
        b.number_format = "#,##0"
    c = ws.cell(row=r, column=3, value=why)
    c.font, c.fill, c.alignment = F_SM, FILL_CARD, WRAP
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=10)
    for col in range(3, 11):
        ws.cell(row=r, column=col).fill = FILL_CARD
    ws.cell(row=r, column=10).border = BOX
    ws.row_dimensions[r].height = max(20, 12 * (1 + len(why) // 105))
    tone = TONE.get(lab)
    if tone:
        fill, colour = TONE_STYLE[tone]
        ws.conditional_formatting.add(
            "B%d" % r,
            CellIsRule(operator="greaterThan", formula=["0"], fill=fill,
                       font=Font(name="Calibri", bold=True, size=14, color=colour)))
    r += 1

ws.conditional_formatting.add(
    "B%d" % (tiles_first + 2),
    CellIsRule(operator="greaterThanOrEqual", formula=["0.8"], fill=FILL_GREEN,
               font=Font(name="Calibri", bold=True, size=14, color=GREEN)))
ws.conditional_formatting.add(
    "B%d" % (tiles_first + 2),
    CellIsRule(operator="lessThan", formula=["0.5"], fill=FILL_AMBER,
               font=Font(name="Calibri", bold=True, size=14, color=AMBER)))

r += 1
section(ws, r, "STAGE FUNNEL — WHERE THE CHARTS ARE", 10)
r += 1
header_row(ws, r, ["Stage", "Charts", "% of planned", "", "", "", "", "", "", "Reading"])
r += 1
funnel_first = r
for st in STATUSES:
    vals = [st, '=COUNTIF(%s,"%s")' % (REG_STATUS, st),
            "=IF($B$5=0,\"NA\",B%d/$B$5)" % r]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c == 3:
            cell.number_format = "0.0%"
    r += 1
ws.conditional_formatting.add(
    "B%d:B%d" % (funnel_first, funnel_first + len(STATUSES) - 1),
    DataBarRule(start_type="num", start_value=0, end_type="max", color=ACCENT,
                showValue=True, minLength=None, maxLength=None))
ws.cell(row=funnel_first, column=10, value="A stage holding far more charts than the ones after it is the bottleneck. Validated piling up means second-level review is the constraint, not sourcing.").font = F_SM
ws.cell(row=funnel_first, column=10).alignment = WRAP
ws.merge_cells(start_row=funnel_first, start_column=10, end_row=r - 1, end_column=10)

r += 1
section(ws, r, "DIFFICULTY MIX — ACTUAL AGAINST THE HC 40 / 40 / 20 TARGET", 10)
r += 1
header_row(ws, r, ["Tier", "Live charts", "Actual %", "Target %", "Deviation", "", "", "", "", "Reading"])
r += 1
dmix_first = r
for tier, target in [("Basic", 0.40), ("Moderate", 0.40), ("Complex", 0.20)]:
    vals = [tier,
            '=COUNTIFS(%s,"%s",%s,"Live")' % (rng(REG, R["tier"]), tier, REG_STATUS),
            "=IF($B$6=0,\"NA\",B%d/$B$6)" % r, target,
            "=IF($B$6=0,\"NA\",C%d-D%d)" % (r, r)]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c in (3, 4, 5):
            cell.number_format = "0.0%"
    r += 1
for _c in ("E",):
    ws.conditional_formatting.add(
        "%s%d:%s%d" % (_c, dmix_first, _c, dmix_first + 2),
        CellIsRule(operator="greaterThan", formula=["0.1"], fill=FILL_AMBER,
                   font=Font(name="Calibri", bold=True, size=10, color=AMBER)))
    ws.conditional_formatting.add(
        "%s%d:%s%d" % (_c, dmix_first, _c, dmix_first + 2),
        CellIsRule(operator="lessThan", formula=["-0.1"], fill=FILL_AMBER,
                   font=Font(name="Calibri", bold=True, size=10, color=AMBER)))
ws.cell(row=dmix_first, column=10, value="Measured over live charts only, so it reports the pool a coder actually meets. A pool drifting toward Basic teaches less than the mix intends; one drifting Complex fails Week 1.").font = F_SM
ws.cell(row=dmix_first, column=10).alignment = WRAP
ws.merge_cells(start_row=dmix_first, start_column=10, end_row=r - 1, end_column=10)

r += 1
note(ws, r, "Native Excel PivotTables cannot be generated by the tool that writes this file, so the summary views here and on Specialty View are formula-driven instead. They need no refresh and survive being emailed. For ad-hoc pivoting, select the register range and insert a PivotTable — the register is a flat table with a header row, which is all a pivot needs.", 10)
note(ws, r + 1, "Every count here reads register rows %d to %d and issue rows %d to %d. Paste beyond those rows and the dashboard will quietly stop counting the overflow, so extend the formulas rather than typing past the end." % (REG_FIRST, REG_LAST, ISS_FIRST, ISS_LAST), 10, PatternFill("solid", fgColor="FDECEA"))

# =========================================================== Specialty View
ws = sheet("Specialty View", [18, 9, 9, 9, 9, 9, 9, 10, 11, 12, 12, 11, 26], freeze="A5")
title_block(ws, "Specialty View — progress and slippage", "One row per specialty, every figure a formula. Expected completion comes from the Schedule Model; the variance is measured against it.", 13)
header_row(ws, 4, ["Specialty", "Target", "Live", "In\nbuild", "On\nhold", "Retired",
                   "Not yet\nsourced", "% of\ntarget", "Topics below\nthreshold",
                   "Expected\ncompletion", "Days vs\nexpected", "Open\nissues", "Status"])
r = 5
sv_first = r
for spec, typ, pool, _s in POOLS:
    srow = SPEC_ROW[spec]
    ps = rng(PLAN, "A", PLAN_FIRST, PLAN_LAST)
    vals = [
        spec,
        "=SUMIF(%s,$A%d,%s)" % (ps, r, rng(PLAN, "H", PLAN_FIRST, PLAN_LAST)),
        "=SUMIF(%s,$A%d,%s)" % (ps, r, rng(PLAN, "J", PLAN_FIRST, PLAN_LAST)),
        "=SUMIF(%s,$A%d,%s)" % (ps, r, rng(PLAN, "K", PLAN_FIRST, PLAN_LAST)),
        "=SUMIF(%s,$A%d,%s)" % (ps, r, rng(PLAN, "L", PLAN_FIRST, PLAN_LAST)),
        "=SUMIF(%s,$A%d,%s)" % (ps, r, rng(PLAN, "M", PLAN_FIRST, PLAN_LAST)),
        "=MAX(0,B%d-COUNTIF(%s,$A%d))" % (r, rng(REG, R["spec"]), r),
        "=IF(B%d=0,\"NA\",C%d/B%d)" % (r, r, r),
        '=COUNTIFS(%s,$A%d,%s,"BELOW*")' % (ps, r, rng(PLAN, "P", PLAN_FIRST, PLAN_LAST)),
        "=IF('%s'!$H$%d=\"NA\",\"NA\",'%s'!$H$%d)" % (SCHED, srow, SCHED, srow),
        ('=IF(NOT(ISNUMBER(J{r})),"NA",IF(C{r}>=B{r},"Complete",'
         'IF(TODAY()<=J{r},"Not yet due",TODAY()-J{r})))').format(r=r),
        '=COUNTIFS(%s,$A%d,%s,"Open")+COUNTIFS(%s,$A%d,%s,"In progress")'
        % (rng(ISS, I["spec"], ISS_FIRST, ISS_LAST), r,
           rng(ISS, I["status"], ISS_FIRST, ISS_LAST),
           rng(ISS, I["spec"], ISS_FIRST, ISS_LAST), r,
           rng(ISS, I["status"], ISS_FIRST, ISS_LAST)),
        ('=IF(B{r}=0,"No target set",IF(C{r}>=B{r},"Complete",'
         'IF(AND(ISNUMBER(K{r}),K{r}>0),"BEHIND — expected date passed",'
         'IF(I{r}>0,"Coverage gap in "&I{r}&" topic(s)","On track"))))').format(r=r),
    ]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c == 8:
            cell.number_format = "0.0%"
        if c == 10:
            cell.number_format = DATE_FMT
        if c == 13:
            cell.font, cell.alignment = F_SM, WRAP
    ws.row_dimensions[r].height = 26
    r += 1
tr = r
for c, v in [(1, "TOTAL")] + [(i, "=SUM(%s%d:%s%d)" % (get_column_letter(i), sv_first, get_column_letter(i), tr - 1)) for i in (2, 3, 4, 5, 6, 7, 9, 12)] + [
        (8, "=IF(B%d=0,\"NA\",C%d/B%d)" % (tr, tr, tr)),
        (10, "=MAX(J%d:J%d)" % (sv_first, tr - 1))]:
    cell = ws.cell(row=tr, column=c, value=v)
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR
    if c == 1:
        cell.alignment = TOP
    if c == 8:
        cell.number_format = "0.0%"
    if c == 10:
        cell.number_format = DATE_FMT
for c in (11, 13):
    ws.cell(row=tr, column=c).fill = FILL_H
    ws.cell(row=tr, column=c).border = BOX
ws.cell(row=tr, column=13, value="Expected completion is the LATEST specialty, not a sum").font = F_H
ws.cell(row=tr, column=13).alignment = WRAP

ws.conditional_formatting.add("H%d:H%d" % (sv_first, tr - 1),
    DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                color=ACCENT, showValue=True, minLength=None, maxLength=None))
ws.conditional_formatting.add("M%d:M%d" % (sv_first, tr - 1),
    FormulaRule(formula=['ISNUMBER(SEARCH("BEHIND",$M%d))' % sv_first],
                fill=FILL_RED, font=Font(size=9, bold=True, color=RED)))
ws.conditional_formatting.add("M%d:M%d" % (sv_first, tr - 1),
    FormulaRule(formula=['$M%d="On track"' % sv_first],
                fill=FILL_GREEN, font=Font(size=9, bold=True, color=GREEN)))
ws.conditional_formatting.add("M%d:M%d" % (sv_first, tr - 1),
    FormulaRule(formula=['$M%d="Complete"' % sv_first],
                fill=FILL_GREEN, font=Font(size=9, bold=True, color=GREEN)))
ws.conditional_formatting.add("M%d:M%d" % (sv_first, tr - 1),
    FormulaRule(formula=['ISNUMBER(SEARCH("Coverage gap",$M%d))' % sv_first],
                fill=FILL_AMBER, font=Font(size=9, bold=True, color=AMBER)))
ws.conditional_formatting.add("I%d:I%d" % (sv_first, tr - 1),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_AMBER, font=Font(size=10, bold=True, color=AMBER)))
ws.conditional_formatting.add("L%d:L%d" % (sv_first, tr - 1),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
note(ws, tr + 2, "Not yet sourced is the target less the register rows for that specialty, floored at zero. It goes to zero before the specialty is finished, because a logged chart is sourced whether or not it is live — read it with In build beside it.", 13)
note(ws, tr + 3, "Days vs expected compares today with the Schedule Model date. It is a capacity statement, not a judgement: a specialty behind on one FTE is on time on two, which is exactly what the FTE column on that sheet is for.", 13)

# ====================================================== Refresh & Retirement
ws = sheet("Refresh & Retirement", [18, 10, 11, 11, 13, 13, 13, 13, 42], freeze=None)
title_block(ws, "Refresh and retirement", "HC policy adds 30% and retires 10% of the pool each half-yearly refresh, a net 20% growth per cycle. This sizes the next one and flags what is due to go.", 9)
section(ws, 4, "POLICY INPUTS", 9)
POL = [("New charts added per refresh", REFRESH_ADD, "pct", "HC Assumptions section C."),
       ("Charts retired per refresh", REFRESH_RETIRE, "pct", "HC Assumptions section C: the oldest and most-used."),
       ("Retire at this many batches used", 8, "num", "A chart seen this often has been seen by most of the cohort. Editable — HC sets no number, so this is a starting point to argue with."),
       ("Retire at this age in days", 540, "num", "Charts older than this predate at least one code-set year. Editable."),
       ("Next refresh date", _dt.date.today() + _dt.timedelta(days=180), "date", "Align with the code-set calendar: Oct 1 ICD-10 and IPPS, Jan 1 CPT, quarterly NCCI and OCE.")]
r = 5
for lab, val, kind, why in POL:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, TOP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    b = ws.cell(row=r, column=3, value=val)
    b.font, b.fill, b.border, b.alignment = F_B, FILL_EDIT, BOX, CTR
    if kind == "date":
        b.number_format = DATE_FMT
    elif kind == "pct":
        b.number_format = "0%"
    c = ws.cell(row=r, column=4, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=9)
    ws.row_dimensions[r].height = max(16, 12 * (1 + len(why) // 95))
    r += 1
ADD_C, RET_C, USE_C, AGE_C = "$C$5", "$C$6", "$C$7", "$C$8"

r += 1
section(ws, r, "NEXT REFRESH BY SPECIALTY", 9)
r += 1
header_row(ws, r, ["Specialty", "Target\npool", "Live\nnow", "Add per\nrefresh",
                   "Retire per\nrefresh", "Live past\nusage limit", "Live past\nage limit",
                   "Due to retire\n(either rule)", "Reading"])
r += 1
rr_first = r
for spec, typ, pool, _s in POOLS:
    vals = [spec, pool,
            '=COUNTIFS(%s,$A%d,%s,"Live")' % (rng(REG, R["spec"]), r, REG_STATUS),
            "=ROUND(B%d*%s,0)" % (r, ADD_C),
            "=ROUND(B%d*%s,0)" % (r, RET_C),
            '=COUNTIFS(%s,$A%d,%s,"Live",%s,">="&%s)'
            % (rng(REG, R["spec"]), r, REG_STATUS, rng(REG, R["usage"]), USE_C),
            '=COUNTIFS(%s,$A%d,%s,"Live",%s,"<="&TODAY()-%s,%s,">0")'
            % (rng(REG, R["spec"]), r, REG_STATUS, rng(REG, R["d_live"]), AGE_C, rng(REG, R["d_live"])),
            "=MAX(F%d,G%d)" % (r, r),
            ('=IF(H{r}>E{r},"More charts qualify to retire than policy removes — retire the most-used first",'
             'IF(H{r}=0,"Nothing qualifies yet","Within policy"))').format(r=r)]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c == 9:
            cell.font, cell.alignment = F_SM, WRAP
    ws.row_dimensions[r].height = 26
    r += 1
tr = r
for c in range(1, 10):
    cell = ws.cell(row=tr, column=c)
    cell.fill, cell.border = FILL_H, BOX
ws.cell(row=tr, column=1, value="TOTAL").font = F_H
for c in (2, 3, 4, 5, 6, 7, 8):
    cell = ws.cell(row=tr, column=c,
                   value="=SUM(%s%d:%s%d)" % (get_column_letter(c), rr_first, get_column_letter(c), tr - 1))
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR

ws.conditional_formatting.add("I%d:I%d" % (rr_first, tr - 1),
    FormulaRule(formula=['ISNUMBER(SEARCH("More charts",$I%d))' % rr_first],
                fill=FILL_AMBER, font=Font(size=9, bold=True, color=AMBER)))
ws.conditional_formatting.add("H%d:H%d" % (rr_first, tr - 1),
    CellIsRule(operator="greaterThan", formula=["0"],
               fill=FILL_AMBER, font=Font(size=10, bold=True, color=AMBER)))
note(ws, tr + 2, "Due to retire takes whichever rule catches more charts rather than adding the two, because a chart can be both old and heavily used and must not be counted twice.", 9)
note(ws, tr + 3, "Retirement is not the same as deletion. A retired chart keeps its register row and its dates, which is what lets the dashboard report what left the pool and when. Deleting the row loses the history and makes the next refresh look smaller than it was.", 9)
note(ws, tr + 4, "Age is measured from the date the chart went live, so a chart built long before it was published is not punished for the wait.", 9)

# ================================================================= Read Me
ws = sheet("Read Me", [3, 32, 98], freeze=None)
title_block(ws, "PracticeLab Chart Inventory Tracker", "End-to-end tracking for every chart, from candidate to retirement · built %s" % BUILT, 3)

READ_ME = [
 ("SEC", "What this is"),
 ("P", "The operational companion to PracticeLab_Chart_Composition_Taxonomy.xlsx. That workbook is the standard: what the pool should contain, topic by topic. This one is the record: what it actually contains, who is building it, and how far behind the build is."),
 ("P", "The register starts empty on purpose. A row exists once a chart exists, so nothing in this file is a placeholder somebody has to maintain. What is not yet sourced is a number on the dashboard, computed against the plan — not two thousand blank rows."),
 ("SEC", "The sheets, in the order you need them"),
 ("KV", "Dashboard|Read-only. Fourteen figures, a stage funnel and the difficulty mix, all formulas. Start here, then follow whatever is red."),
 ("KV", "Chart Register|Where the work is recorded. One row per chart, five dated stages, dropdowns on every classified field. The only sheet most people type into."),
 ("KV", "Topic Plan|All 103 topics with their targets, and live counts beside them. This is where a coverage gap shows up at the level sourcing actually works at."),
 ("KV", "Specialty View|The same thing one level up: progress, slippage and status per specialty. The view for a weekly update."),
 ("KV", "Schedule Model|Where every expected date comes from. Two editable columns — build hours per chart and FTE assigned — drive the whole schedule."),
 ("KV", "Issues Log|Anything blocking a chart or casting doubt on one already live. Severity, owner, target resolution date, overdue flag."),
 ("KV", "Refresh & Retirement|Sizes the next half-yearly refresh and flags charts past the usage or age limit."),
 ("KV", "Lists|The source of every dropdown. Add a value here, never straight into a cell."),
 ("SEC", "The five stages"),
 ("P", "Identified, De-identified, Built, Validated, Live — then Retired, or On hold while an issue runs. Each has its own date column, which is what makes the stage funnel on the dashboard meaningful: a stage holding more charts than the ones after it is the bottleneck, and the Days in stage column names the individual charts stuck there."),
 ("P", "Set the Status column to where a chart is now, and fill the date column for each stage as it is reached. The two are not the same field and both are needed: the status drives every count, the dates drive the ageing."),
 ("SEC", "How a delay is measured"),
 ("KV", "Where expected dates come from|The Schedule Model multiplies a specialty's target by its build hours per chart, divides by the hours one FTE has in a week, and lays the result out from the programme start date. Topics within a specialty are sequenced by build priority, so the P1 topics carry the earliest dates."),
 ("KV", "What a slipping date means|Either the build rate is wrong or the staffing is. Both are editable columns on that sheet, so a date that cannot be met should be met by changing the assumption on the record rather than by quietly missing it."),
 ("KV", "Per chart|Days late on the register compares the expected live date with today, or with the actual live date once the chart is live. Positive means late."),
 ("KV", "Per topic and specialty|Days vs expected compares today with the modelled completion date, and reads On target as soon as live reaches target."),
 ("SEC", "What this file cannot do"),
 ("P", "It has no native PivotTables — the tool that writes it cannot create them. The summary views are formulas instead, which need no refresh and survive being emailed. If you want ad-hoc pivoting, select the register and insert a PivotTable; it is a flat table with a header row, which is all a pivot needs."),
 ("P", "Formulas cover register rows 5 to 1004 and issue rows 5 to 504. That is headroom for a pool of 2,942 across several refresh cycles, but it is not infinite: paste past the end and the dashboard will quietly stop counting the overflow. Extend the formulas, do not type past them."),
 ("P", "Nothing here is connected to the platform. It is a planning and governance record maintained by hand, and the moment Topic ID exists as a field on the chart record in the application, the counts in it should come from there instead."),
 ("SEC", "Rules worth keeping"),
 ("P", "A suspected answer-key problem puts the chart On hold, not Live-with-a-note. A wrong key silently grades everyone against it, which is worse than a missing chart."),
 ("P", "Retiring a chart keeps its row. Deleting the row loses the history that lets the dashboard say what left the pool and when."),
 ("P", "Every rate on the dashboard carries its denominator in the description beside it. Pool complete is live over planned; the difficulty mix is over live charts only, because that is the pool a coder actually meets."),
 ("P", "A topic with no target reads NA, not 0%. They are different statements: one means no target was set, the other means nothing was built against one."),
]
r = 4
for kind, text in READ_ME:
    if kind == "SEC":
        r += 1
        c = ws.cell(row=r, column=2, value=text)
        c.font = Font(name="Calibri", bold=True, size=11, color=NAVY)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        r += 1
    elif kind == "P":
        c = ws.cell(row=r, column=2, value=text)
        c.font, c.alignment = F_N, WRAP
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        ws.row_dimensions[r].height = 13 * (1 + len(text) // 120)
        r += 1
    else:
        k, v = text.split("|", 1)
        a = ws.cell(row=r, column=2, value=k)
        a.font, a.alignment, a.fill = F_B, WRAP, FILL_BAND
        b = ws.cell(row=r, column=3, value=v)
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 13 * (1 + len(v) // 98)
        r += 1

# --- colour legend, so the palette is documented rather than decorative
r += 1
c = ws.cell(row=r, column=2, value="What the colours mean")
c.font = Font(name="Calibri", bold=True, size=11, color=NAVY)
ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
r += 1
LEGEND = [
    ("Green", FILL_GREEN, GREEN, "Done or healthy: live, complete, on track, a closed issue."),
    ("Blue", FILL_BLUE, BLUE, "In flight: a chart moving through the stages, or a topic at or above the gap threshold."),
    ("Amber", FILL_AMBER, AMBER, "Watch it: on hold, stalled over 30 days, a coverage gap, a P1 topic, more charts qualifying to retire than policy removes."),
    ("Red", FILL_RED, RED, "Act now: past the expected date, below the gap threshold, a blocker, an overdue issue, an unrecognised Topic ID."),
    ("Cream", FILL_EDIT, INK, "You type here. Build hours, FTE, the start date, the retirement limits."),
    ("Grey-blue", FILL_BAND, GREY, "Computed — do not type. These columns fill themselves from the Topic ID or the dates."),
]
for name, fill, colour, meaning in LEGEND:
    a = ws.cell(row=r, column=2, value=name)
    a.fill, a.font, a.alignment, a.border = fill, Font(name="Calibri", bold=True, size=10, color=colour), Alignment(horizontal="center", vertical="center"), BOX
    b = ws.cell(row=r, column=3, value=meaning)
    b.font, b.alignment = F_N, WRAP
    ws.row_dimensions[r].height = max(15, 13 * (1 + len(meaning) // 98))
    r += 1
c = ws.cell(row=r + 1, column=2, value="Colour is never the only signal: every highlighted cell also carries the words, so the workbook still reads correctly printed in black and white or to anyone who cannot distinguish the hues.")
c.font, c.alignment, c.fill = F_SM, WRAP, FILL_NOTE
ws.merge_cells(start_row=r + 1, start_column=2, end_row=r + 1, end_column=3)

# --- tab order: what you open, in the order you need it
for _name in ["Read Me", "Dashboard", "Chart Register", "Issues Log", "Topic Plan",
              "Specialty View", "Schedule Model", "Refresh & Retirement", "Lists"]:
    wb.move_sheet(_name, offset=len(wb.sheetnames) - wb.sheetnames.index(_name) - 1)
for _ws in wb.worksheets:
    _ws.sheet_view.zoomScale = 90
wb.active = 0
wb.save(OUT)
print("wrote %s" % OUT)
print("sheets: %s" % ", ".join(wb.sheetnames))
print("topics planned: %d   register rows: %d   issue rows: %d"
      % (len(plan_rows), REG_LAST - REG_FIRST + 1, ISS_LAST - ISS_FIRST + 1))
