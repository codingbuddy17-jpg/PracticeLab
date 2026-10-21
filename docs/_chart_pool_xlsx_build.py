#!/usr/bin/env python3
"""Builds PracticeLab_Chart_Pool_Tracker.xlsx.

The training team's working view of the live chart pool: what is in there,
by topic and specialty, uploaded when, and which charts to assign to whom.

Deliberately separate from PracticeLab_Chart_Inventory_Tracker.xlsx, which
tracks the BUILD programme -- targets, expected dates, FTE, slippage, issues.
This one answers "what do we have, and who should practise on it". Both import
_chart_taxonomy_data, so the taxonomy cannot differ between them.

Counting mirrors the application exactly. The app stores `category` as one
verbatim string and never parses it; the allocator splits the TRAINER's filter
on commas and substring-matches each piece. So a chart may legitimately carry
`Sepsis, AKI` and be found by a filter of either. Every count here therefore
uses a wildcard COUNTIF against the stored string rather than an equality
test, which is why the short names are guaranteed never to be substrings of
one another -- otherwise one topic's count would quietly include another's.

Dated when it is built, not when someone remembered to change a string.
"""
import datetime as _dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule, DataBarRule
from openpyxl.chart import LineChart, BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList

from _chart_taxonomy_data import POOLS, TOPICS, priority_of, SHORT_NAME

BUILT = _dt.date.today().strftime("%d %B %Y")
OUT = "docs/PracticeLab_Chart_Pool_Tracker.xlsx"

NAVY, NAVY_MID, ACCENT, GREY, INK = "1F3864", "2F5597", "2E75B6", "595959", "212121"
HDR_BG, BAND_BG, BAND_ALT, NOTE_BG, EDIT_BG, CARD_BG = (
    "DCE6F1", "EEF3F9", "F7FAFD", "FFF4E5", "FFF8E1", "F4F8FC")
GREEN, GREEN_BG = "1B6B3A", "E6F4EA"
AMBER, AMBER_BG = "9C6500", "FFF4D6"
RED, RED_BG = "A4262C", "FCE8E6"
BLUE, BLUE_BG = "1F5C99", "E7F0FA"

F_TITLE = Font(name="Calibri", bold=True, size=16, color=NAVY)
F_SUB = Font(name="Calibri", size=10, italic=True, color=GREY)
F_H = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
F_SEC = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
F_B = Font(name="Calibri", bold=True, size=10, color=INK)
F_N = Font(name="Calibri", size=10, color=INK)
F_SM = Font(name="Calibri", size=9, color=GREY)
F_AUTO = Font(name="Calibri", size=9, italic=True, color=GREY)
F_MONO = Font(name="Consolas", size=10, color=INK)
F_LAB = Font(name="Calibri", bold=True, size=10, color=NAVY)
F_VAL = Font(name="Calibri", bold=True, size=15, color=NAVY)

FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_SEC = PatternFill("solid", fgColor=NAVY_MID)
FILL_SUBH = PatternFill("solid", fgColor=HDR_BG)
FILL_BAND = PatternFill("solid", fgColor=BAND_BG)
FILL_NOTE = PatternFill("solid", fgColor=NOTE_BG)
FILL_EDIT = PatternFill("solid", fgColor=EDIT_BG)
FILL_CARD = PatternFill("solid", fgColor=CARD_BG)
FILL_ACCENT = PatternFill("solid", fgColor=ACCENT)
FILL_GREEN = PatternFill("solid", fgColor=GREEN_BG)
FILL_AMBER = PatternFill("solid", fgColor=AMBER_BG)
FILL_RED = PatternFill("solid", fgColor=RED_BG)
FILL_BLUE = PatternFill("solid", fgColor=BLUE_BG)

THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HDR_BORDER = Border(left=Side(style="thin", color=NAVY), right=Side(style="thin", color=NAVY),
                    top=Side(style="thin", color=NAVY), bottom=Side(style="medium", color=ACCENT))
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")
TOP = Alignment(vertical="top")
CTR = Alignment(horizontal="center", vertical="center")
DATE_FMT = "dd-mmm-yy"
MONTH_FMT = "mmm-yy"

# ------------------------------------------------------------------ geometry
DB, DB_FIRST, DB_LAST = "Chart Database", 6, 4005
DICT_S, DICT_FIRST = "Category Dictionary", 5
TREND_MONTHS = 24
# Blank rows below the 111 governed topics, where the team registers a topic
# the taxonomy does not have. Counting formulas span these too, so a name typed
# here starts being counted the moment it is entered.
EXTRA_SLOTS = 20
# One row per AUTHORED audit key set, not per chart: a chart may hold several
# ("IP001 - foundational", "IP001 - DRG impact"), which is exactly why they
# cannot live on the chart row.
AUD, AUD_FIRST, AUD_LAST = "Audit Versions", 6, 605

FLAT = [(spec, cat, t) for spec, _, _, _ in POOLS
        for cat, parent, rows in TOPICS[spec][1] for t in rows]
DICT_GOVERNED_LAST = DICT_FIRST + len(FLAT) - 1
DICT_LAST = DICT_GOVERNED_LAST + EXTRA_SLOTS
POOL_OF = dict((s, p) for s, _, p, _ in POOLS)
SPECIALTIES = [s for s, _, _, _ in POOLS]
PREFIX = {"IP-DRG": "IP", "ED Facility": "ED", "ED Profee": "EDP",
          "ED Single Path": "EDSP", "SDS": "SDS", "Surgery": "SURG", "E/M": "EM"}
DIFFICULTY = ["Beginner", "Intermediate", "Advanced"]   # the app's own enum
STATUS = ["Active", "Retired"]
YESNO = ["Yes", "No"]
ROW_OF_TOPIC = {}

wb = Workbook()
wb.remove(wb.active)

TAB_COLOUR = {
    "Read Me": GREY, "Leader Dashboard": NAVY, "Chart Database": GREEN,
    "Category Dictionary": ACCENT, "Topic Coverage": NAVY_MID,
    "Specialty Overview": NAVY_MID, "Monthly Trend": BLUE,
    "Recent Activity": BLUE, "Assignment Builder": AMBER,
    "Field Conventions": RED, "Lists": "BFBFBF", "Audit Versions": AMBER,
}


def sheet(title, widths, freeze=None):
    ws = wb.create_sheet(title)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    if freeze:
        ws.freeze_panes = freeze
    if title in TAB_COLOUR:
        ws.sheet_properties.tabColor = TAB_COLOUR[title]
    return ws


def title_block(ws, title, sub, span):
    ws["A1"] = title
    ws["A1"].font = F_TITLE
    ws["A1"].alignment = Alignment(vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    ws["A2"] = sub
    ws["A2"].font = F_SUB
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    ws.row_dimensions[1].height = 26
    for i in range(1, span + 1):
        ws.cell(row=3, column=i).fill = FILL_ACCENT
    ws.row_dimensions[3].height = 3


def header_row(ws, row, labels, height=34):
    for c, lab in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=c, value=lab)
        cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, HDR_BORDER
    ws.row_dimensions[row].height = height


def section(ws, row, text, span):
    c = ws.cell(row=row, column=1, value="  " + text)
    c.font, c.fill, c.alignment = F_SEC, FILL_SEC, Alignment(vertical="center")
    for i in range(2, span + 1):
        ws.cell(row=row, column=i).fill = FILL_SEC
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = 20


def zebra(ws, first, last, last_col):
    ws.conditional_formatting.add(
        "A%d:%s%d" % (first, get_column_letter(last_col), last),
        FormulaRule(formula=["MOD(ROW(),2)=0"], fill=PatternFill("solid", fgColor=BAND_ALT)))


def note(ws, row, text, span, fill=FILL_NOTE):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.fill, c.alignment = F_SM, fill, WRAP
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = max(14, 13 * (1 + len(text) // 150))


def rg(sheet_name, col, first, last):
    return "'%s'!$%s$%d:$%s$%d" % (sheet_name, col, first, col, last)


# Chart Database columns. The first nine ARE the live `charts` table columns,
# in table order, so an export pasted in as values needs no reshaping.
DB_COLS = [
    ("chart_number", 13, "db"), ("specialty", 15, "db"), ("category", 34, "db"),
    ("difficulty", 12, "db"), ("alias", 30, "db"), ("status", 10, "db"),
    ("uploaded_by", 15, "db"), ("created_at", 11, "db"), ("view_count", 9, "db"),
    ("Topics on chart\n(auto)", 11, "auto"), ("Recognised\n(auto)", 11, "auto"),
    ("Primary topic\n(auto)", 20, "auto"),
    ("Upload month\n(auto)", 11, "auto"), ("Days in pool\n(auto)", 10, "auto"),
    ("Answer key", 10, "ours"), ("Audit versions\n(auto)", 10, "auto"),
    ("Audit cycles\nused", 9, "ours"), ("Next version\n(auto)", 11, "auto"),
    ("Times\nassigned", 9, "ours"), ("Last assigned", 11, "ours"),
    ("Matches filter\n(auto)", 12, "auto"), ("Notes", 30, "ours"),
]
C = {}
for _i, (_n, _w, _k) in enumerate(DB_COLS, start=1):
    C[_n.split("\n")[0]] = get_column_letter(_i)
NDB = len(DB_COLS)
CAT_R = rg(DB, C["category"], DB_FIRST, DB_LAST)
SPEC_R = rg(DB, C["specialty"], DB_FIRST, DB_LAST)
STAT_R = rg(DB, C["status"], DB_FIRST, DB_LAST)
DIFF_R = rg(DB, C["difficulty"], DB_FIRST, DB_LAST)
NUM_R = rg(DB, C["chart_number"], DB_FIRST, DB_LAST)
CREATED_R = rg(DB, C["created_at"], DB_FIRST, DB_LAST)
KEY_R = rg(DB, C["Answer key"], DB_FIRST, DB_LAST)
USED_R = rg(DB, C["Times"], DB_FIRST, DB_LAST)
MATCH_R = rg(DB, C["Matches filter"], DB_FIRST, DB_LAST)

# ===================================================== Assignment Builder
# First, because the database's "matches filter" column references these cells.
ws = sheet("Assignment Builder", [26, 20, 4, 62])
title_block(ws, "Assignment Builder", "Set the filters, read the count, then filter the Chart Database by its last column. Nothing to write.", 4)
section(ws, 4, "FILTERS  —  leave a cell blank to ignore it", 4)
FILTERS = [
    ("Specialty", "", "Blank means every specialty."),
    ("Category contains", "", "A short name from the Category Dictionary, e.g. Sepsis. Matches charts carrying it among several, exactly as the app does."),
    ("Build priority", "", "P1 to P4. For a cohort that should meet the foundation topics first."),
    ("Difficulty", "", "Beginner, Intermediate or Advanced."),
    ("Status", "Active", "Active unless you are deliberately reviewing retired charts."),
    ("Answer key required", "Yes", "Yes keeps only charts that can be graded. Blank is how an ungradeable chart reaches a batch."),
    ("Uploaded on or after", "", "A date. Use to assign only recently refreshed material."),
    ("Max times already assigned", "", "A number. 0 finds charts nobody has had yet. Blank ignores usage."),
]
r = 5
for lab, default, why in FILTERS:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, TOP
    b = ws.cell(row=r, column=2, value=default or None)
    b.font, b.fill, b.border, b.alignment = F_B, FILL_EDIT, BOX, CTR
    if lab == "Uploaded on or after":
        b.number_format = DATE_FMT
    c = ws.cell(row=r, column=4, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws.row_dimensions[r].height = max(16, 12 * (1 + len(why) // 80))
    r += 1
F = dict(spec="$B$5", cat="$B$6", prio="$B$7", diff="$B$8",
         status="$B$9", key="$B$10", frm="$B$11", maxuse="$B$12")
AB = "Assignment Builder"

r += 1
section(ws, r, "RESULT", 4)
r += 1
res_first = r
RESULTS = [
    ("Charts matching", "=COUNTIF(%s,TRUE)" % MATCH_R,
     "How many charts in the pool satisfy every filter set above."),
    ("of which never assigned", '=COUNTIFS(%s,TRUE,%s,0)' % (MATCH_R, USED_R),
     "Unseen charts — what an assessment or a post-QIP reassessment needs."),
    ("Distinct topics covered", "=SUMPRODUCT(--(COUNTIFS(%s,TRUE,%s,\"*\"&'%s'!$D$%d:$D$%d&\"*\")>0))"
     % (MATCH_R, CAT_R, DICT_S, DICT_FIRST, DICT_LAST),
     "How many of the 111 topics the matching set touches. A batch drawn from one topic trains one thing."),
]
for lab, formula, why in RESULTS:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_LAB, FILL_CARD, BOX, Alignment(vertical="center", indent=1)
    b = ws.cell(row=r, column=2, value=formula)
    b.font, b.fill, b.border, b.alignment = F_VAL, FILL_CARD, BOX, CTR
    b.number_format = "#,##0"
    ws.cell(row=r, column=3).fill = FILL_CARD
    c = ws.cell(row=r, column=4, value=why)
    c.font, c.fill, c.alignment = F_SM, FILL_CARD, WRAP
    ws.row_dimensions[r].height = max(20, 12 * (1 + len(why) // 80))
    r += 1
ws.conditional_formatting.add("B%d" % res_first,
    CellIsRule(operator="equal", formula=["0"], fill=FILL_RED,
               font=Font(name="Calibri", bold=True, size=15, color=RED)))
ws.conditional_formatting.add("B%d" % res_first,
    CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_GREEN,
               font=Font(name="Calibri", bold=True, size=15, color=GREEN)))

r += 1
section(ws, r, "HOW TO GET THE LIST", 4)
r += 1
for step in [
    "1.   Set the filters above. Only the cells you fill narrow the result.",
    "2.   Open Chart Database. Use the filter arrow on the last column, Matches filter, and tick TRUE.",
    "3.   The visible rows are the assignment set. Copy the chart_number column into the batch.",
    "4.   In the app, type the short name into the category filter — the same text you used in step 1.",
    "5.   Afterwards add 1 to Times assigned on those rows and set Last assigned. That is what keeps 'never assigned' honest.",
]:
    c = ws.cell(row=r, column=1, value=step)
    c.font, c.alignment = F_N, WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    ws.row_dimensions[r].height = 17
    r += 1

note(ws, r + 1, "The count is live, so widen a filter until the number is workable rather than guessing. A count of zero means the pool cannot serve that request, which is itself the answer and the gap to take to sourcing.", 4)
note(ws, r + 2, "Category contains uses the same substring match the application uses, so a chart filed as \"Sepsis, AKI\" is found by a filter of either. That is why the short names are guaranteed never to contain one another — otherwise one topic's set would quietly include another's.", 4)
note(ws, r + 3, "Why a filter column and not a list that writes itself: a self-populating list needs the dynamic array functions only recent Excel has, and this file goes round a team on whatever version they run. The filter arrow works everywhere.", 4)

for col, listname in [("B5", "Specialty"), ("B7", "Priority"), ("B8", "Difficulty"),
                      ("B9", "Status"), ("B10", "YesNo")]:
    pass  # validations added after Lists exists


def _namecheck(r):
    """Live guard against the one mistake that silently corrupts a count.

    Matching is substring, so if one short name is contained in another within
    the same specialty, filtering or counting either picks up both. Python
    asserts this for the 111 governed topics; for a name somebody types into a
    user slot, only a formula can say so."""
    return (
        '=IF($D{r}="","",'
        'IF(SUMPRODUCT(--($A${f}:$A${l}=$A{r}),--($D${f}:$D${l}<>""),'
        '--(ROW($D${f}:$D${l})<>ROW()),'
        '--(ISNUMBER(SEARCH($D{r},$D${f}:$D${l}))+ISNUMBER(SEARCH($D${f}:$D${l}&"",$D{r}))>0))>0,'
        '"CLASH — overlaps another name in this specialty","OK"))'
    ).format(r=r, f=DICT_FIRST, l=DICT_LAST)

# ======================================================= Category Dictionary
ws = sheet(DICT_S, [16, 10, 13, 24, 40, 11, 9, 9, 9, 10, 26, 24], freeze="A5")
title_block(ws, "Category Dictionary — what to type", "The controlled vocabulary the application does not have. Type the short name exactly as it appears here, on upload and when filtering. Rows below the 111 are yours to add.", 12)
header_row(ws, 4, ["Specialty", "Topic ID", "Build\npriority", "SHORT NAME  —  type this",
                   "Full topic (taxonomy)", "Coverage\ncategory", "Target\ncharts",
                   "In pool\nnow", "% of\ntarget", "Gap", "Name check", "Notes"])
r = DICT_FIRST
for spec, cat, t in FLAT:
    tid = t[0]
    ROW_OF_TOPIC[tid] = r
    pool = POOL_OF[spec]
    vals = [
        spec, tid, priority_of(tid), SHORT_NAME[tid], t[1], cat, round(t[4] * pool),
        '=COUNTIFS(%s,$A%d,%s,"*"&$D%d&"*",%s,"Active")' % (SPEC_R, r, CAT_R, r, STAT_R),
        "=IF($G%d=0,\"NA\",H%d/$G%d)" % (r, r, r),
        "=$G%d-H%d" % (r, r),
        _namecheck(r),
        "",
    ]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c == 2:
            cell.font, cell.alignment = F_B, CTR
        elif c == 3:
            cell.alignment = CTR
            cell.font = Font(size=9, bold=True, color={
                "P1": RED, "P2": INK, "P3": GREY, "P4": GREY}[priority_of(tid)])
        elif c == 4:
            cell.font = Font(name="Consolas", size=10, bold=True, color=NAVY)
            cell.fill = FILL_BLUE
        elif c == 5:
            cell.alignment = WRAP
            cell.font = F_SM
        elif c == 6:
            cell.font, cell.alignment = F_SM, WRAP
        elif c == 9:
            cell.number_format = "0%"
            cell.alignment = CTR
        elif c == 11:
            cell.font, cell.alignment = F_SM, CTR
        elif c in (7, 8, 10):
            cell.alignment = CTR
            if c == 7:
                cell.font = F_B
    ws.row_dimensions[r].height = 24
    r += 1
# user slots: specialty, short name and target are typed; the rest computes
for r in range(DICT_GOVERNED_LAST + 1, DICT_LAST + 1):
    vals = [None, "—", "P2", None, "Added by the team — not in the composition taxonomy",
            None, None,
            '=IF($D%d="","",COUNTIFS(%s,$A%d,%s,"*"&$D%d&"*",%s,"Active"))' % (r, SPEC_R, r, CAT_R, r, STAT_R),
            '=IF(OR($D%d="",$G%d=""),"NA",IF($G%d=0,"NA",H%d/$G%d))' % (r, r, r, r, r),
            '=IF(OR($D%d="",$G%d=""),"",$G%d-H%d)' % (r, r, r, r),
            _namecheck(r), None]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c in (1, 4, 7):
            cell.fill = FILL_EDIT
            cell.font = F_B
            if c == 4:
                cell.font = Font(name="Consolas", size=10, bold=True, color=NAVY)
        if c == 2:
            cell.font, cell.alignment = F_SM, CTR
        if c == 3:
            cell.alignment = CTR
            cell.fill = FILL_EDIT
        if c == 5:
            cell.font, cell.alignment = F_SM, WRAP
        if c == 9:
            cell.number_format = "0%"
        if c in (7, 8, 9, 10, 11):
            cell.alignment = CTR
    ws.row_dimensions[r].height = 22

ws.auto_filter.ref = "A4:L%d" % DICT_LAST
zebra(ws, DICT_FIRST, DICT_LAST, 11)
tr = DICT_LAST + 1
for c, v in [(1, "TOTAL"), (7, "=SUM(G%d:G%d)" % (DICT_FIRST, DICT_LAST)),
             (8, "=SUM(H%d:H%d)" % (DICT_FIRST, DICT_LAST)),
             (9, "=IF(G%d=0,\"NA\",H%d/G%d)" % (tr, tr, tr)),
             (10, "=G%d-H%d" % (tr, tr)),
             (11, '=COUNTIF(K%d:K%d,"CLASH*")&" name clash(es)"' % (DICT_FIRST, DICT_LAST))]:
    cell = ws.cell(row=tr, column=c, value=v)
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR
    if c == 1:
        cell.alignment = TOP
    if c == 9:
        cell.number_format = "0%"
for c in range(1, 13):
    if ws.cell(row=tr, column=c).value is None:
        ws.cell(row=tr, column=c).fill = FILL_H
        ws.cell(row=tr, column=c).border = BOX

ws.conditional_formatting.add("I%d:I%d" % (DICT_FIRST, DICT_LAST),
    DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                color=ACCENT, showValue=True, minLength=None, maxLength=None))
ws.conditional_formatting.add("H%d:H%d" % (DICT_FIRST, DICT_LAST),
    CellIsRule(operator="equal", formula=["0"], fill=FILL_RED,
               font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add("K%d:K%d" % (DICT_FIRST, DICT_LAST),
    FormulaRule(formula=['LEFT($K%d,5)="CLASH"' % DICT_FIRST],
                fill=FILL_RED, font=Font(size=9, bold=True, color=RED)))
ws.conditional_formatting.add("A%d:A%d" % (DICT_GOVERNED_LAST + 1, DICT_LAST),
    FormulaRule(formula=['$D%d<>""' % (DICT_GOVERNED_LAST + 1)],
                fill=FILL_AMBER))
note(ws, tr + 2, "In pool now counts ACTIVE charts whose category contains this short name, which is how the application matches. A chart filed as \"Sepsis, Renal\" counts under both Sepsis and Renal — correctly, because it teaches both.", 12)
note(ws, tr + 3, "A consequence worth knowing: the In pool column can sum to more than the number of charts, because a multi-topic chart is counted under each topic it carries. Use Specialty Overview for a headcount of charts and this sheet for coverage of topics.", 12, FILL_AMBER)
note(ws, tr + 4, "THE LAST %d ROWS ARE YOURS. To track a topic the taxonomy does not have, type its specialty and a short name in the shaded cells; a target is optional and the coverage columns read NA without one. The name is counted from that moment, and the Leader Dashboard stops reporting charts carrying it as unrecognised." % EXTRA_SLOTS, 12, FILL_BLUE)
note(ws, tr + 5, "Name check is the one guard that cannot be skipped. Because the application matches by substring, a name that contains or sits inside another name in the same specialty makes both counts wrong — \"Respiratory\" would pick up every \"Respiratory surgical\" chart. Pick a name that reads CLASH again until it reads OK.", 12, FILL_RED)
note(ws, tr + 6, "A topic added here has no place in the composition taxonomy, so it carries no weight and no agreed target. If it turns out to be permanent, it belongs in that workbook properly — which means taking its share of charts from a sibling topic, since the weights must still sum to the HC parent percentage.", 12)

# ============================================================ Lists sheet
wsL = sheet("Lists", [18, 14, 13, 10, 10, 20, 18, 14, 26], freeze=None)
title_block(wsL, "Dropdown lists", "The source for every dropdown. Add a value here, never straight into a cell.", 6)
LISTS = [("Specialty", SPECIALTIES), ("Difficulty", DIFFICULTY), ("Status", STATUS),
         ("Priority", ["P1", "P2", "P3", "P4"]), ("YesNo", YESNO),
         ("QueryExpected", ["Yes", "No", "NA — not authored"]),
         ("SpecialtyAll", ["All"] + SPECIALTIES), ("DifficultyAll", ["All"] + DIFFICULTY)]
LREF = {}
for ci, (name, vals) in enumerate(LISTS, start=1):
    h = wsL.cell(row=4, column=ci, value=name)
    h.font, h.fill, h.alignment, h.border = F_H, FILL_H, WRAP_C, BOX
    for i, v in enumerate(vals):
        c = wsL.cell(row=5 + i, column=ci, value=v)
        c.font, c.border = F_N, BOX
    col = get_column_letter(ci)
    LREF[name] = "Lists!$%s$5:$%s$%d" % (col, col, 4 + len(vals))
h = wsL.cell(row=4, column=9, value="Short name (reference — 111)")
h.font, h.fill, h.alignment, h.border = F_H, FILL_H, WRAP_C, BOX
wsL.cell(row=5, column=9, value="See the Category Dictionary sheet; it carries the topic and target beside each name.").font = F_SM
wsL.cell(row=5, column=9).alignment = WRAP

# validations on the Assignment Builder, now that Lists exists
wsAB = wb["Assignment Builder"]
for cell_ref, listname in [("B5", "Specialty"), ("B7", "Priority"), ("B8", "Difficulty"),
                           ("B9", "Status"), ("B10", "YesNo")]:
    dv = DataValidation(type="list", formula1="=%s" % LREF[listname],
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick a value from the list, or leave blank to ignore this filter."
    dv.errorTitle = "Not on the list"
    wsAB.add_data_validation(dv)
    dv.add(cell_ref)

# =========================================================== Chart Database
ws = sheet(DB, [w for _, w, _ in DB_COLS], freeze="C6")
title_block(ws, "Chart Database", "One row per chart. The first nine columns are the live charts table, in order — paste an export straight in. Grey columns fill themselves.", NDB)
hdr = ["Export from the app  →" if False else n for n, _, _ in DB_COLS]
# a band naming which columns come from where
for c, (n, w, kind) in enumerate(DB_COLS, start=1):
    lab = {"db": "FROM THE APP", "auto": "AUTO", "ours": "WE MAINTAIN"}[kind]
    cell = ws.cell(row=4, column=c, value=lab)
    cell.font = Font(name="Calibri", size=8, bold=True,
                     color={"db": GREEN, "auto": GREY, "ours": AMBER}[kind])
    cell.fill = {"db": FILL_GREEN, "auto": FILL_BAND, "ours": FILL_AMBER}[kind]
    cell.alignment = CTR
    cell.border = BOX
ws.row_dimensions[4].height = 13
header_row(ws, 5, [n for n, _, _ in DB_COLS], height=40)

AUTOC = {C["Topics on chart"], C["Recognised"], C["Primary topic"],
         C["Upload month"], C["Days in pool"], C["Matches filter"],
         C["Audit versions"], C["Next version"]}
for r in range(DB_FIRST, DB_LAST + 1):
    n, cat = C["chart_number"], C["category"]
    # how many topics the chart carries = commas + 1
    f = ('=IF($%s%d="","",LEN($%s%d)-LEN(SUBSTITUTE($%s%d,",",""))+1)'
         % (n, r, cat, r, cat, r))
    c1 = ws.cell(row=r, column=ws[C["Topics on chart"] + "1"].column, value=f)
    # How many dictionary short names appear in this chart's category string.
    # Fewer than the comma count means at least one topic is not in the
    # dictionary at all, which is the only way such a chart becomes visible.
    f = ('=IF($%s%d="","",SUMPRODUCT(--ISNUMBER(SEARCH('
         "'%s'!$D$%d:$D$%d&\"\",$%s%d)),--('%s'!$D$%d:$D$%d<>\"\")))"
         % (n, r, DICT_S, DICT_FIRST, DICT_LAST, cat, r, DICT_S, DICT_FIRST, DICT_LAST))
    c1b = ws.cell(row=r, column=ws[C["Recognised"] + "1"].column, value=f)
    # primary topic = text before the first comma
    f = ('=IF($%s%d="","",TRIM(IF(ISERROR(FIND(",",$%s%d)),$%s%d,'
         'LEFT($%s%d,FIND(",",$%s%d)-1))))' % (n, r, cat, r, cat, r, cat, r, cat, r))
    c2 = ws.cell(row=r, column=ws[C["Primary topic"] + "1"].column, value=f)
    # upload month, as a real date pinned to the first of the month
    f = ('=IF($%s%d="","",DATE(YEAR($%s%d),MONTH($%s%d),1))'
         % (C["created_at"], r, C["created_at"], r, C["created_at"], r))
    c3 = ws.cell(row=r, column=ws[C["Upload month"] + "1"].column, value=f)
    c3.number_format = MONTH_FMT
    f = '=IF($%s%d="","",TODAY()-$%s%d)' % (C["created_at"], r, C["created_at"], r)
    c4 = ws.cell(row=r, column=ws[C["Days in pool"] + "1"].column, value=f)
    # the filter
    f = ('=IF($%s%d="","",AND('
         'OR(\'{ab}\'!{spec}="",$%s%d=\'{ab}\'!{spec}),'
         'OR(\'{ab}\'!{cat}="",ISNUMBER(SEARCH(\'{ab}\'!{cat},$%s%d))),'
         'OR(\'{ab}\'!{prio}="",\'{ab}\'!{prio}=IFERROR(INDEX(\'{d}\'!$C${df}:$C${dl},'
         'MATCH($%s%d,\'{d}\'!$D${df}:$D${dl},0)),"")),'
         'OR(\'{ab}\'!{diff}="",$%s%d=\'{ab}\'!{diff}),'
         'OR(\'{ab}\'!{status}="",$%s%d=\'{ab}\'!{status}),'
         'OR(\'{ab}\'!{key}="",$%s%d=\'{ab}\'!{key}),'
         'OR(\'{ab}\'!{frm}="",$%s%d>=\'{ab}\'!{frm}),'
         'OR(\'{ab}\'!{maxuse}="",N($%s%d)<=\'{ab}\'!{maxuse})'
         '))').format(ab=AB, d=DICT_S, df=DICT_FIRST, dl=DICT_LAST, **F) % (
            n, r, C["specialty"], r, C["category"], r, C["Primary topic"], r,
            C["difficulty"], r, C["status"], r, C["Answer key"], r,
            C["created_at"], r, C["Times"], r)
    c5 = ws.cell(row=r, column=ws[C["Matches filter"] + "1"].column, value=f)
    # how many ACTIVE authored versions this chart has
    f = ('=IF($%s%d="","",COUNTIFS(%s,$%s%d,%s,"Active"))'
         % (n, r, rg(AUD, "A", AUD_FIRST, AUD_LAST), n, r,
            rg(AUD, "L", AUD_FIRST, AUD_LAST)))
    c6 = ws.cell(row=r, column=ws[C["Audit versions"] + "1"].column, value=f)
    # Which version the NEXT cycle will serve. The allocator does
    # pool[use_index % len(pool)], so this is arithmetic, not a guess. Shown
    # 1-based because a trainer counts versions from one, not from zero.
    f = ('=IF(OR($%s%d="",$%s%d=0),"",MOD(N($%s%d),$%s%d)+1)'
         % (n, r, C["Audit versions"], r, C["Audit cycles"], r,
            C["Audit versions"], r))
    c7 = ws.cell(row=r, column=ws[C["Next version"] + "1"].column, value=f)
    for cell in (c1, c1b, c2, c3, c4, c5, c6, c7):
        cell.font, cell.fill, cell.border = F_AUTO, FILL_BAND, BOX
        cell.alignment = CTR
    c2.alignment = TOP
    for c in range(1, NDB + 1):
        L = get_column_letter(c)
        if L in AUTOC:
            continue
        cell = ws.cell(row=r, column=c)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if L in (C["created_at"], C["Last assigned"]):
            cell.number_format = DATE_FMT
            cell.alignment = CTR
        elif L in (C["difficulty"], C["status"], C["view_count"],
                   C["Answer key"], C["Audit cycles"], C["Times"]):
            cell.alignment = CTR
        elif L == C["category"]:
            cell.font = Font(name="Consolas", size=10, color=INK)

for L, listname in [(C["specialty"], "Specialty"), (C["difficulty"], "Difficulty"),
                    (C["status"], "Status"), (C["Answer key"], "YesNo")]:
    dv = DataValidation(type="list", formula1="=%s" % LREF[listname],
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick a value from the list. Add new values on the Lists sheet, not here."
    dv.errorTitle = "Not on the list"
    ws.add_data_validation(dv)
    dv.add("%s%d:%s%d" % (L, DB_FIRST, L, DB_LAST))

ws.auto_filter.ref = "A5:%s%d" % (get_column_letter(NDB), DB_LAST)
zebra(ws, DB_FIRST, DB_LAST, NDB)
ws.conditional_formatting.add("%s%d:%s%d" % (C["Matches filter"], DB_FIRST, C["Matches filter"], DB_LAST),
    FormulaRule(formula=['$%s%d=TRUE' % (C["Matches filter"], DB_FIRST)],
                fill=FILL_GREEN, font=Font(size=9, bold=True, color=GREEN)))
ws.conditional_formatting.add("%s%d:%s%d" % (C["status"], DB_FIRST, C["status"], DB_LAST),
    FormulaRule(formula=['$%s%d="Retired"' % (C["status"], DB_FIRST)],
                fill=FILL_BAND, font=Font(size=10, color=GREY)))
ws.conditional_formatting.add("%s%d:%s%d" % (C["Answer key"], DB_FIRST, C["Answer key"], DB_LAST),
    FormulaRule(formula=['$%s%d="No"' % (C["Answer key"], DB_FIRST)],
                fill=FILL_RED, font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add("%s%d:%s%d" % (C["Topics on chart"], DB_FIRST, C["Topics on chart"], DB_LAST),
    CellIsRule(operator="greaterThanOrEqual", formula=["2"], fill=FILL_BLUE,
               font=Font(size=9, bold=True, color=BLUE)))
# One authored version and it has been used: every auditor meets the same
# planting, which becomes a tell. Two or more is what rotation needs.
ws.conditional_formatting.add("%s%d:%s%d" % (C["Audit versions"], DB_FIRST, C["Audit versions"], DB_LAST),
    FormulaRule(formula=['AND($%s%d=1,N($%s%d)>0)' % (
        C["Audit versions"], DB_FIRST, C["Audit cycles"], DB_FIRST)],
        fill=FILL_AMBER, font=Font(size=9, bold=True, color=AMBER)))
# Recognised < topics on chart: at least one name is not in the dictionary.
ws.conditional_formatting.add("%s%d:%s%d" % (C["Recognised"], DB_FIRST, C["Recognised"], DB_LAST),
    FormulaRule(formula=['AND($%s%d<>"",$%s%d<$%s%d)' % (
        C["chart_number"], DB_FIRST, C["Recognised"], DB_FIRST, C["Topics on chart"], DB_FIRST)],
        fill=FILL_RED, font=Font(size=9, bold=True, color=RED)))

# ======================================================= Specialty Overview
ws = sheet("Specialty Overview", [18, 8, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 24])
title_block(ws, "Specialty Overview", "A headcount of charts, not of topics. Every figure a formula over the Chart Database.", 14)
header_row(ws, 4, ["Specialty", "Prefix", "Target\npool", "Active", "Retired",
                   "Total\nrows", "% of\ntarget", "Beginner", "Intermediate",
                   "Advanced", "No answer\nkey", "Added last\n30 days",
                   "Never\nassigned", "Reading"])
r = 5
sv_first = r
for spec in SPECIALTIES:
    vals = [
        spec, PREFIX[spec], POOL_OF[spec],
        '=COUNTIFS(%s,$A%d,%s,"Active")' % (SPEC_R, r, STAT_R),
        '=COUNTIFS(%s,$A%d,%s,"Retired")' % (SPEC_R, r, STAT_R),
        '=COUNTIF(%s,$A%d)' % (SPEC_R, r),
        "=IF($C%d=0,\"NA\",D%d/$C%d)" % (r, r, r),
        '=COUNTIFS(%s,$A%d,%s,"Beginner",%s,"Active")' % (SPEC_R, r, DIFF_R, STAT_R),
        '=COUNTIFS(%s,$A%d,%s,"Intermediate",%s,"Active")' % (SPEC_R, r, DIFF_R, STAT_R),
        '=COUNTIFS(%s,$A%d,%s,"Advanced",%s,"Active")' % (SPEC_R, r, DIFF_R, STAT_R),
        '=COUNTIFS(%s,$A%d,%s,"No",%s,"Active")' % (SPEC_R, r, KEY_R, STAT_R),
        '=COUNTIFS(%s,$A%d,%s,">="&TODAY()-30,%s,"<="&TODAY())' % (SPEC_R, r, CREATED_R, CREATED_R),
        '=COUNTIFS(%s,$A%d,%s,0,%s,"Active")' % (SPEC_R, r, USED_R, STAT_R),
        ('=IF(D{r}=0,"Nothing in the pool yet",IF(D{r}>=C{r},"At target",'
         'IF(K{r}>0,K{r}&" chart(s) cannot be graded",'
         'IF(D{r}/C{r}<0.5,"Under half built","Building"))))').format(r=r),
    ]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c == 2:
            cell.font = F_MONO
        if c == 7:
            cell.number_format = "0.0%"
        if c == 14:
            cell.font, cell.alignment = F_SM, WRAP
    ws.row_dimensions[r].height = 24
    r += 1
tr = r
ws.cell(row=tr, column=1, value="TOTAL").font = F_H
for c in list(range(3, 7)) + list(range(8, 14)):
    cell = ws.cell(row=tr, column=c,
                   value="=SUM(%s%d:%s%d)" % (get_column_letter(c), sv_first, get_column_letter(c), tr - 1))
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR
ws.cell(row=tr, column=7, value="=IF(C%d=0,\"NA\",D%d/C%d)" % (tr, tr, tr))
ws.cell(row=tr, column=7).number_format = "0.0%"
for c in (1, 2, 7, 14):
    ws.cell(row=tr, column=c).fill = FILL_H
    ws.cell(row=tr, column=c).border = BOX
    ws.cell(row=tr, column=c).font = F_H
    ws.cell(row=tr, column=c).alignment = CTR
ws.cell(row=tr, column=1).alignment = TOP

ws.conditional_formatting.add("G%d:G%d" % (sv_first, tr - 1),
    DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                color=ACCENT, showValue=True, minLength=None, maxLength=None))
ws.conditional_formatting.add("K%d:K%d" % (sv_first, tr - 1),
    CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_RED,
               font=Font(size=10, bold=True, color=RED)))
ws.conditional_formatting.add("L%d:L%d" % (sv_first, tr - 1),
    CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_GREEN,
               font=Font(size=10, bold=True, color=GREEN)))
note(ws, tr + 2, "This sheet counts CHARTS. The Category Dictionary counts TOPIC COVERAGE, and its total is larger because a chart carrying \"Sepsis, AKI\" is counted under both topics. Neither is wrong; they answer different questions.", 14)
note(ws, tr + 3, "Difficulty uses the application's own values — Beginner, Intermediate, Advanced. The composition taxonomy speaks of Basic, Moderate and Complex tiers; the Field Conventions sheet maps the two.", 14)

# =========================================================== Monthly Trend
ws = sheet("Monthly Trend", [13] + [11] * len(SPECIALTIES) + [11, 12, 46])
title_block(ws, "Monthly Trend — uploads by month", "Counted from created_at. Change the start month and the whole table moves with it.", len(SPECIALTIES) + 4)
section(ws, 4, "FIRST MONTH SHOWN", len(SPECIALTIES) + 4)
start_cell = "$B$5"
a = ws.cell(row=5, column=1, value="Start month")
a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, TOP
b = ws.cell(row=5, column=2, value=_dt.date(_dt.date.today().year - 1, _dt.date.today().month, 1))
b.font, b.fill, b.border, b.alignment, b.number_format = F_B, FILL_EDIT, BOX, CTR, MONTH_FMT
c = ws.cell(row=5, column=4, value="%d months are shown from here. Any month with no uploads reads 0 rather than being skipped, so a gap in sourcing is visible." % TREND_MONTHS)
c.font, c.alignment = F_SM, WRAP
ws.merge_cells(start_row=5, start_column=4, end_row=5, end_column=len(SPECIALTIES) + 4)

header_row(ws, 7, ["Month"] + SPECIALTIES + ["Total", "Cumulative", "Reading"])
r = 8
mt_first = r
for i in range(TREND_MONTHS):
    mcell = "=EDATE(%s,%d)" % (start_cell, i) if i else "=%s" % start_cell
    cell = ws.cell(row=r, column=1, value=mcell)
    cell.font, cell.border, cell.alignment, cell.number_format = F_B, BOX, CTR, MONTH_FMT
    for j, spec in enumerate(SPECIALTIES, start=2):
        f = ('=COUNTIFS(%s,"%s",%s,">="&$A%d,%s,"<"&EDATE($A%d,1))'
             % (SPEC_R, spec, CREATED_R, r, CREATED_R, r))
        c2 = ws.cell(row=r, column=j, value=f)
        c2.font, c2.border, c2.alignment = F_N, BOX, CTR
    tot_col = len(SPECIALTIES) + 2
    c3 = ws.cell(row=r, column=tot_col,
                 value="=SUM(B%d:%s%d)" % (r, get_column_letter(len(SPECIALTIES) + 1), r))
    c3.font, c3.border, c3.alignment, c3.fill = F_B, BOX, CTR, FILL_SUBH
    cum = ws.cell(row=r, column=tot_col + 1,
                  value="=SUM($%s$%d:%s%d)" % (get_column_letter(tot_col), mt_first,
                                               get_column_letter(tot_col), r))
    cum.font, cum.border, cum.alignment = F_N, BOX, CTR
    rd = ws.cell(row=r, column=tot_col + 2,
                 value='=IF(%s%d=0,"no uploads this month","")' % (get_column_letter(tot_col), r))
    rd.font, rd.alignment = F_SM, TOP
    r += 1
mt_last = r - 1
tr = r
ws.cell(row=tr, column=1, value="TOTAL").font = F_H
ws.cell(row=tr, column=1).alignment = TOP
for c in range(2, len(SPECIALTIES) + 3):
    cell = ws.cell(row=tr, column=c,
                   value="=SUM(%s%d:%s%d)" % (get_column_letter(c), mt_first, get_column_letter(c), mt_last))
    cell.font, cell.fill, cell.border, cell.alignment = F_H, FILL_H, BOX, CTR
for c in (1, len(SPECIALTIES) + 3, len(SPECIALTIES) + 4):
    ws.cell(row=tr, column=c).fill = FILL_H
    ws.cell(row=tr, column=c).border = BOX
    ws.cell(row=tr, column=c).font = F_H

tot_col_L = get_column_letter(len(SPECIALTIES) + 2)
ws.conditional_formatting.add("%s%d:%s%d" % (tot_col_L, mt_first, tot_col_L, mt_last),
    DataBarRule(start_type="num", start_value=0, end_type="max", color=ACCENT,
                showValue=True, minLength=None, maxLength=None))
ws.conditional_formatting.add("%s%d:%s%d" % (tot_col_L, mt_first, tot_col_L, mt_last),
    CellIsRule(operator="equal", formula=["0"], fill=FILL_RED,
               font=Font(size=10, bold=True, color=RED)))
zebra(ws, mt_first, mt_last, len(SPECIALTIES) + 4)
note(ws, tr + 2, "The data bar in the Total column is the build rate. A run of short bars is the refresh falling behind; a spike is usually one trainer clearing a backlog, which is worth knowing before it is read as capacity.", len(SPECIALTIES) + 4)
note(ws, tr + 3, "Months are counted on created_at, which is when the chart was UPLOADED, not when it was sourced or when it went live to a batch.", len(SPECIALTIES) + 4)

# ========================================================= Recent Activity
ws = sheet("Recent Activity", [26, 12, 12, 12, 12, 4, 44])
title_block(ws, "Recent Activity", "What has changed lately, by window. Everything counts ACTIVE charts unless the row says otherwise.", 7)
header_row(ws, 4, ["", "Last 7\ndays", "Last 30\ndays", "Last 90\ndays", "This\nmonth", "", "Reading"])
WINDOWS = [("B", 7), ("C", 30), ("D", 90)]
RA_ROWS = [
    ("Charts uploaded", None, "Rows whose created_at falls in the window."),
    ("of which multi-topic", None, "Carrying more than one category. Those cover more ground per chart."),
    ("of which no answer key yet", None, "Uploaded but not gradeable. This is the number that should be falling."),
    ("Charts retired", None, "Status set to Retired. Compare against the refresh policy of 10% per cycle."),
]
r = 5
ra_first = r
for lab, _x, why in RA_ROWS:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, TOP
    for col, days in WINDOWS:
        if lab == "Charts uploaded":
            f = '=COUNTIFS(%s,">="&TODAY()-%d,%s,"<="&TODAY())' % (CREATED_R, days, CREATED_R)
        elif lab == "of which multi-topic":
            f = ('=COUNTIFS(%s,">="&TODAY()-%d,%s,"<="&TODAY(),%s,">=2")'
                 % (CREATED_R, days, CREATED_R, rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST)))
        elif lab == "of which no answer key yet":
            f = ('=COUNTIFS(%s,">="&TODAY()-%d,%s,"<="&TODAY(),%s,"No")'
                 % (CREATED_R, days, CREATED_R, KEY_R))
        else:
            f = ('=COUNTIFS(%s,"Retired",%s,">="&TODAY()-%d)'
                 % (STAT_R, rg(DB, C["Last assigned"], DB_FIRST, DB_LAST), days))
        cell = ws.cell(row=r, column={"B": 2, "C": 3, "D": 4}[col], value=f)
        cell.font, cell.border, cell.alignment = F_B, BOX, CTR
    # this month
    if lab == "Charts uploaded":
        f = '=COUNTIFS(%s,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),%s,"<="&TODAY())' % (CREATED_R, CREATED_R)
    elif lab == "of which multi-topic":
        f = ('=COUNTIFS(%s,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),%s,"<="&TODAY(),%s,">=2")'
             % (CREATED_R, CREATED_R, rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST)))
    elif lab == "of which no answer key yet":
        f = ('=COUNTIFS(%s,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),%s,"<="&TODAY(),%s,"No")'
             % (CREATED_R, CREATED_R, KEY_R))
    else:
        f = '=""'
    cell = ws.cell(row=r, column=5, value=f)
    cell.font, cell.border, cell.alignment = F_B, BOX, CTR
    c = ws.cell(row=r, column=7, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws.row_dimensions[r].height = max(18, 12 * (1 + len(why) // 56))
    r += 1
ws.conditional_formatting.add("B%d:E%d" % (ra_first + 2, ra_first + 2),
    CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_AMBER,
               font=Font(size=10, bold=True, color=AMBER)))

r += 1
section(ws, r, "UPLOADS BY TRAINER  —  LAST 90 DAYS", 7)
r += 1
header_row(ws, r, ["uploaded_by", "Charts", "Multi-topic", "No key", "Avg topics", "", "Reading"], height=30)
r += 1
ub_first = r
UB_SLOTS = 12
for i in range(UB_SLOTS):
    # The "already listed" range is anchored on the HEADER row, not on the first
    # data row. Anchored on the first data row, that row's own formula spans
    # $A$12:$A11 -- which Excel normalises to A11:A12, swallowing the cell
    # itself and making the whole workbook circular. The header is text and
    # matches no trainer name, so counting it costs nothing.
    a = ws.cell(row=r, column=1,
                value=('=IFERROR(INDEX(%s,MATCH(0,INDEX(COUNTIF($A$%d:$A%d,%s),0),0)),"")'
                       % (rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST), ub_first - 1, r - 1,
                          rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST))))
    a.font, a.border, a.alignment = F_AUTO, BOX, TOP
    a.fill = FILL_BAND
    for c, f in [
        (2, '=IF($A%d="","",COUNTIFS(%s,$A%d,%s,">="&TODAY()-90))' % (r, rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST), r, CREATED_R)),
        (3, '=IF($A%d="","",COUNTIFS(%s,$A%d,%s,">="&TODAY()-90,%s,">=2"))' % (r, rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST), r, CREATED_R, rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST))),
        (4, '=IF($A%d="","",COUNTIFS(%s,$A%d,%s,">="&TODAY()-90,%s,"No"))' % (r, rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST), r, CREATED_R, KEY_R)),
        (5, '=IF(OR($A%d="",B%d=0),"",ROUND(SUMIFS(%s,%s,$A%d,%s,">="&TODAY()-90)/B%d,2))' % (r, r, rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST), rg(DB, C["uploaded_by"], DB_FIRST, DB_LAST), r, CREATED_R, r)),
    ]:
        cell = ws.cell(row=r, column=c, value=f)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
    r += 1
ws.cell(row=ub_first, column=7, value="The trainer column fills itself from whoever appears in the database — the first 12 distinct names. It is a workload picture, not a scorecard: a trainer on IP-DRG at three hours a chart cannot match one on SDS at an hour and a half.").font = F_SM
ws.cell(row=ub_first, column=7).alignment = WRAP
ws.merge_cells(start_row=ub_first, start_column=7, end_row=r - 1, end_column=7)
zebra(ws, ub_first, r - 1, 5)

note(ws, r + 1, "Charts retired counts on Last assigned rather than a retirement date, because the application does not store one. Treat that row as indicative and record the real date in Notes if it matters.", 7, FILL_AMBER)
note(ws, r + 2, "To see the charts behind any of these numbers, go to the Chart Database and filter created_at by the same window. Every figure here is a COUNTIFS over that sheet and nothing else.", 7)


# ============================================== Chart Data (hidden helper)
# Excel charts plot a contiguous range, and several of the figures worth
# plotting are not contiguous anywhere else. These small tables exist only to
# be plotted; the sheet is hidden so nobody mistakes it for a view.
wsH = sheet("Chart Data", [26, 12, 12, 12])
title_block(wsH, "Chart data", "Helper ranges for the dashboard charts. Hidden by design — nothing here is meant to be read directly.", 4)

wsH["A5"] = "Difficulty mix"
wsH["A5"].font = F_B
for i, d in enumerate(DIFFICULTY):
    wsH.cell(row=6 + i, column=1, value=d).font = F_N
    wsH.cell(row=6 + i, column=2,
             value='=COUNTIFS(%s,"%s",%s,"Active")' % (DIFF_R, d, STAT_R)).font = F_N

wsH["A10"] = "Pool status"
wsH["A10"].font = F_B
for i, (lab, f) in enumerate([
        ("Live in pool", '=COUNTIF(%s,"Active")' % STAT_R),
        ("Retired", '=COUNTIF(%s,"Retired")' % STAT_R),
        ("Still to source",
         '=MAX(0,\'Specialty Overview\'!$C$12-COUNTIF(%s,"Active"))' % STAT_R)]):
    wsH.cell(row=11 + i, column=1, value=lab).font = F_N
    wsH.cell(row=11 + i, column=2, value=f).font = F_N

wsH["A15"] = "Top 10 topic gaps"
wsH["A15"].font = F_B
for i in range(10):
    r = 16 + i
    # kth largest gap, and the topic name that carries it
    wsH.cell(row=r, column=2, value="=IFERROR(LARGE(%s,%d),0)" % (
        rg(DICT_S, "J", DICT_FIRST, DICT_LAST), i + 1)).font = F_N
    wsH.cell(row=r, column=1, value=(
        '=IFERROR(INDEX(%s,MATCH(1,INDEX((%s=$B%d)*(COUNTIF($A$%d:$A%d,%s)=0),0),0)),"")'
        % (rg(DICT_S, "D", DICT_FIRST, DICT_LAST),
           rg(DICT_S, "J", DICT_FIRST, DICT_LAST), r, 15, r - 1,
           rg(DICT_S, "D", DICT_FIRST, DICT_LAST)))).font = F_N
wsH.sheet_state = "hidden"

# ========================================================= Leader Dashboard
ws = sheet("Leader Dashboard", [28, 13, 12, 12, 12, 12, 4, 15, 12, 12, 12, 12, 12])
title_block(ws, "Chart pool — leader dashboard", "Set the two filters and every figure below follows them. Charts refresh with the data. Nothing on this sheet is typed except the filters. Built %s." % BUILT, 13)

# ---------------------------------------------------------------- filters
section(ws, 4, "FILTER  —  every figure and chart below obeys these", 13)
for i, (lab, default, listname, why) in enumerate([
    ("Specialty", "All", "SpecialtyAll",
     "All, or one specialty. The charts follow too."),
    ("Difficulty", "All", "DifficultyAll",
     "All, or one of the application's three values."),
]):
    r = 5 + i
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, TOP
    b = ws.cell(row=r, column=2, value=default)
    b.font, b.fill, b.border, b.alignment = Font(name="Calibri", bold=True, size=11, color=NAVY), FILL_EDIT, BOX, CTR
    c = ws.cell(row=r, column=3, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=13)
    dv = DataValidation(type="list", formula1="=%s" % LREF[listname], allow_blank=False,
                        showDropDown=False)
    dv.error = "Pick All, or one value from the list."
    dv.errorTitle = "Not on the list"
    ws.add_data_validation(dv)
    dv.add("B%d" % r)
# "*" matches any text, so one formula serves both All and a single pick
SP = 'IF($B$5="All","*",$B$5)'
DF = 'IF($B$6="All","*",$B$6)'

# ---------------------------------------------------------------- headline
section(ws, 8, "HEADLINE", 13)
TILES = [
    ("Charts in the pool", '=COUNTIFS(%s,%s,%s,%s,%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, STAT_R), "",
     "Active charts matching the filter, available to a batch right now."),
    ("Target pool", '=IF($B$5="All",\'Specialty Overview\'!$C$12,SUMIF(\'Specialty Overview\'!$A$5:$A$11,$B$5,\'Specialty Overview\'!$C$5:$C$11))', "",
     "From the composition taxonomy. A difficulty filter does not change it, because targets are set per specialty, not per tier."),
    ("Pool complete", "=IF(B10=0,\"NA\",B9/B10)", "pct",
     "Active against target. Reads NA before a target exists."),
    ("Retired", '=COUNTIFS(%s,%s,%s,%s,%s,"Retired")' % (SPEC_R, SP, DIFF_R, DF, STAT_R), "",
     "Kept as rows rather than deleted, so what left the pool is still visible."),
    ("Cannot be graded", '=COUNTIFS(%s,%s,%s,%s,%s,"No",%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, KEY_R, STAT_R), "act",
     "Active charts with no answer key. These reach a batch and then cannot be scored."),
    ("Multi-topic charts", '=COUNTIFS(%s,%s,%s,%s,%s,">=2",%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST), STAT_R), "good",
     "Carrying more than one category, so they cover more ground per chart."),
    ("Never assigned", '=COUNTIFS(%s,%s,%s,%s,%s,0,%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, USED_R, STAT_R), "good",
     "Unseen by anyone — the reserve for assessments and reassessments."),
    ("Off-list category", '=SUMPRODUCT(--(%s<>""),--(N(%s)<N(%s)))' % (
        NUM_R, rg(DB, C["Recognised"], DB_FIRST, DB_LAST),
        rg(DB, C["Topics on chart"], DB_FIRST, DB_LAST)), "act",
     "Carrying a category name in no dictionary row. Counted as charts, but toward no topic's coverage. Not filtered — this is a whole-pool figure."),
    ("Audit-ready charts", '=COUNTIFS(%s,%s,%s,%s,%s,">=2",%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, rg(DB, C["Audit versions"], DB_FIRST, DB_LAST), STAT_R), "good",
     "Two or more authored versions, so rotation can actually vary what an auditor meets."),
    ("Single-version charts", '=COUNTIFS(%s,%s,%s,%s,%s,1,%s,">0",%s,"Active")' % (SPEC_R, SP, DIFF_R, DF, rg(DB, C["Audit versions"], DB_FIRST, DB_LAST), rg(DB, C["Audit cycles"], DB_FIRST, DB_LAST), STAT_R), "warn",
     "One version and already used, so every auditor meets the same planting. A tell."),
    ("Topics with nothing at all", '=COUNTIFS(%s,0,%s,"<>")' % (
        rg(DICT_S, "H", DICT_FIRST, DICT_LAST), rg(DICT_S, "D", DICT_FIRST, DICT_LAST)), "act",
     "Topics with no chart. The sourcing list in one number. Whole pool, not filtered."),
    ("Uploaded this month", '=COUNTIFS(%s,%s,%s,%s,%s,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),%s,"<="&TODAY())' % (SPEC_R, SP, DIFF_R, DF, CREATED_R, CREATED_R), "good",
     "The build rate, measured rather than assumed."),
    ("Oldest active chart, days",
     # MAX inside SUMPRODUCT, not a bare SUMPRODUCT: without it this sums every
     # chart's age instead of reporting the oldest, which reads plausibly and
     # is completely wrong.
     '=SUMPRODUCT(MAX((%s="Active")*(%s<>"")*(((%s=$B$5)+($B$5="All"))>0)*(TODAY()-%s)))' % (
         STAT_R, CREATED_R, SPEC_R, CREATED_R), "warn",
     "Days since the oldest matching chart was uploaded. Past about 540 it predates a code-set year."),
]
TONE = {"good": (FILL_GREEN, GREEN), "warn": (FILL_AMBER, AMBER), "act": (FILL_RED, RED)}
r = 9
for lab, formula, tone, why in TILES:
    a = ws.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_LAB, FILL_CARD, BOX, Alignment(vertical="center", indent=1)
    b = ws.cell(row=r, column=2, value=formula)
    b.font, b.fill, b.border, b.alignment = F_VAL, FILL_CARD, BOX, CTR
    b.number_format = "0.0%" if tone == "pct" else "#,##0"
    for cc in range(3, 14):
        ws.cell(row=r, column=cc).fill = FILL_CARD
    c = ws.cell(row=r, column=3, value=why)
    c.font, c.fill, c.alignment = F_SM, FILL_CARD, WRAP
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=13)
    ws.cell(row=r, column=13).border = BOX
    ws.row_dimensions[r].height = max(20, 12 * (1 + len(why) // 125))
    if tone in TONE:
        fill, colour = TONE[tone]
        ws.conditional_formatting.add("B%d" % r,
            CellIsRule(operator="greaterThan", formula=["0"], fill=fill,
                       font=Font(name="Calibri", bold=True, size=15, color=colour)))
    r += 1
ws.conditional_formatting.add("B11",
    CellIsRule(operator="greaterThanOrEqual", formula=["0.8"], fill=FILL_GREEN,
               font=Font(name="Calibri", bold=True, size=15, color=GREEN)))

# ------------------------------------------------------------------ charts
CH = r + 1
section(ws, CH, "CHARTS  —  these refresh with the data, no action needed", 13)

def _style(ch, title, h=7.4, w=13.6):
    ch.title = title
    ch.height, ch.width = h, w
    ch.style = 2

line = LineChart()
_style(line, "Charts uploaded per month")
line.add_data(Reference(wb["Monthly Trend"], min_col=9, min_row=7, max_row=31), titles_from_data=True)
line.set_categories(Reference(wb["Monthly Trend"], min_col=1, min_row=8, max_row=31))
line.y_axis.title, line.x_axis.title = "Charts", None
ws.add_chart(line, "A%d" % (CH + 1))

bar = BarChart()
_style(bar, "Active against target, by specialty")
bar.type, bar.grouping = "col", "clustered"
bar.add_data(Reference(wb["Specialty Overview"], min_col=3, max_col=4, min_row=4, max_row=11), titles_from_data=True)
bar.set_categories(Reference(wb["Specialty Overview"], min_col=1, min_row=5, max_row=11))
ws.add_chart(bar, "H%d" % (CH + 1))

pie = PieChart()
_style(pie, "Difficulty mix of the live pool")
pie.add_data(Reference(wsH, min_col=2, min_row=6, max_row=8), titles_from_data=False)
pie.set_categories(Reference(wsH, min_col=1, min_row=6, max_row=8))
pie.dataLabels = DataLabelList()
pie.dataLabels.showVal, pie.dataLabels.showPercent = False, True
ws.add_chart(pie, "A%d" % (CH + 17))

pie2 = PieChart()
_style(pie2, "Pool status against target")
pie2.add_data(Reference(wsH, min_col=2, min_row=11, max_row=13), titles_from_data=False)
pie2.set_categories(Reference(wsH, min_col=1, min_row=11, max_row=13))
pie2.dataLabels = DataLabelList()
pie2.dataLabels.showVal = True
ws.add_chart(pie2, "H%d" % (CH + 17))

gaps = BarChart()
_style(gaps, "Ten largest topic gaps", h=7.4, w=28)
gaps.type, gaps.grouping = "bar", "clustered"
gaps.add_data(Reference(wsH, min_col=2, min_row=16, max_row=25), titles_from_data=False)
gaps.set_categories(Reference(wsH, min_col=1, min_row=16, max_row=25))
gaps.legend = None
ws.add_chart(gaps, "A%d" % (CH + 33))

r = CH + 49

# -------------------------------------------------------------- by specialty
section(ws, r, "BY SPECIALTY  —  the whole pool, ignoring the filters above", 13)
r += 1
header_row(ws, r, ["Specialty", "Target", "Active", "% of target", "Beginner",
                   "Intermediate", "Advanced", "No key", "Audit ready",
                   "Single ver.", "", "", "Status"], height=30)
r += 1
ls_first = r
for i, spec in enumerate(SPECIALTIES):
    src = 5 + i
    vals = [spec, "='Specialty Overview'!$C$%d" % src, "='Specialty Overview'!$D$%d" % src,
            "='Specialty Overview'!$G$%d" % src, "='Specialty Overview'!$H$%d" % src,
            "='Specialty Overview'!$I$%d" % src, "='Specialty Overview'!$J$%d" % src,
            "='Specialty Overview'!$K$%d" % src,
            '=COUNTIFS(%s,$A%d,%s,">=2",%s,"Active")' % (SPEC_R, r, rg(DB, C["Audit versions"], DB_FIRST, DB_LAST), STAT_R),
            '=COUNTIFS(%s,$A%d,%s,1,%s,">0",%s,"Active")' % (SPEC_R, r, rg(DB, C["Audit versions"], DB_FIRST, DB_LAST), rg(DB, C["Audit cycles"], DB_FIRST, DB_LAST), STAT_R),
            None, None, "='Specialty Overview'!$N$%d" % src]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, CTR
        if c == 1:
            cell.font, cell.alignment = F_B, TOP
        if c == 4:
            cell.number_format = "0.0%"
        if c == 13:
            cell.font, cell.alignment = F_SM, WRAP
    ws.merge_cells(start_row=r, start_column=11, end_row=r, end_column=12)
    ws.row_dimensions[r].height = 22
    r += 1
ws.conditional_formatting.add("D%d:D%d" % (ls_first, r - 1),
    DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                color=ACCENT, showValue=True, minLength=None, maxLength=None))
for col, fill, colour in [("H", FILL_RED, RED), ("J", FILL_AMBER, AMBER)]:
    ws.conditional_formatting.add("%s%d:%s%d" % (col, ls_first, col, r - 1),
        CellIsRule(operator="greaterThan", formula=["0"], fill=fill,
                   font=Font(size=10, bold=True, color=colour)))
ws.conditional_formatting.add("I%d:I%d" % (ls_first, r - 1),
    CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_GREEN,
               font=Font(size=10, bold=True, color=GREEN)))

r += 1
section(ws, r, "WHERE TO LOOK NEXT", 13)
r += 1
for text in [
    "Topics with nothing at all  \u2192  Category Dictionary, filter In pool to 0. That is the sourcing list.",
    "Charts that cannot be graded  \u2192  Chart Database, filter Answer key to No.",
    "Charts with an off-list category  \u2192  Chart Database, filter Recognised below Topics on chart. Correct it, or register the name in the dictionary's spare rows.",
    "Single-version audit charts  \u2192  Audit Versions. One version means every auditor meets the same planting.",
    "Which version comes next  \u2192  Audit Versions, the NEXT column. It is arithmetic: uses modulo version count.",
    "Who should practise what  \u2192  Assignment Builder, then filter the database by Matches filter.",
    "What a trainer should type  \u2192  Category Dictionary, the SHORT NAME column.",
]:
    c = ws.cell(row=r, column=1, value=text)
    c.font, c.alignment = F_N, WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
    ws.row_dimensions[r].height = 17
    r += 1

note(ws, r + 1, "The two filters drive the HEADLINE block only. The charts and the specialty table below show the whole pool deliberately: a trend line that moves when somebody changes a filter is read as a change in the data by the next person to open the file.", 13)
note(ws, r + 2, "Four tiles ignore the filters because they are whole-pool questions: off-list categories, topics with nothing at all, and the two dictionary-level figures. Each says so in its own description.", 13)
note(ws, r + 3, "Every figure reads Chart Database rows %d to %d. Paste beyond row %d and the dashboard silently stops counting the overflow." % (DB_FIRST, DB_LAST, DB_LAST), 13, FILL_RED)


# =========================================================== Audit Versions
AUD_COLS = [
    ("chart_number", 13, "ours"), ("Specialty\n(auto)", 14, "auto"),
    ("Version name", 26, "ours"), ("Authored by", 14, "ours"),
    ("Created", 11, "ours"), ("Planted\nfindings", 9, "ours"),
    ("Sections touched", 26, "ours"), ("Query expected\n(IP-DRG only)", 12, "ours"),
    ("Always\nplant", 9, "ours"), ("Times\ndrawn", 8, "ours"),
    ("Last drawn", 11, "ours"), ("Status", 10, "ours"),
    ("Version #\n(auto)", 10, "auto"), ("Next in\nrotation (auto)", 13, "auto"),
    ("Notes", 30, "ours"),
]
ws = sheet(AUD, [w for _, w, _ in AUD_COLS], freeze="C6")
title_block(ws, "Audit Versions", "One row per trainer-authored audit key set. A chart may hold several, which is why these cannot live on the chart row.", len(AUD_COLS))
for c, (n_, w_, kind) in enumerate(AUD_COLS, start=1):
    lab = {"auto": "AUTO", "ours": "WE MAINTAIN"}[kind]
    cell = ws.cell(row=4, column=c, value=lab)
    cell.font = Font(name="Calibri", size=8, bold=True,
                     color={"auto": GREY, "ours": AMBER}[kind])
    cell.fill = {"auto": FILL_BAND, "ours": FILL_AMBER}[kind]
    cell.alignment, cell.border = CTR, BOX
ws.row_dimensions[4].height = 13
header_row(ws, 5, [n_ for n_, _, _ in AUD_COLS], height=40)

for r in range(AUD_FIRST, AUD_LAST + 1):
    f = ('=IF($A%d="","",IFERROR(INDEX(%s,MATCH($A%d,%s,0)),"UNKNOWN CHART"))'
         % (r, rg(DB, C["specialty"], DB_FIRST, DB_LAST), r,
            rg(DB, C["chart_number"], DB_FIRST, DB_LAST)))
    b = ws.cell(row=r, column=2, value=f)
    f = ('=IF(OR($A%d="",$L%d<>"Active"),"",COUNTIFS($A$%d:$A%d,$A%d,$L$%d:$L%d,"Active"))'
         % (r, r, AUD_FIRST - 1, r, r, AUD_FIRST - 1, r))
    m = ws.cell(row=r, column=13, value=f)
    f = ('=IF(OR($A%d="",$M%d=""),"",IF($M%d=IFERROR(INDEX(%s,MATCH($A%d,%s,0)),0),'
         '"NEXT",""))'
         % (r, r, r, rg(DB, C["Next version"], DB_FIRST, DB_LAST), r,
            rg(DB, C["chart_number"], DB_FIRST, DB_LAST)))
    nx = ws.cell(row=r, column=14, value=f)
    for cell in (b, m, nx):
        cell.font, cell.fill, cell.border, cell.alignment = F_AUTO, FILL_BAND, BOX, CTR
    for c in range(1, len(AUD_COLS) + 1):
        if c in (2, 13, 14):
            continue
        cell = ws.cell(row=r, column=c)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c in (5, 11):
            cell.number_format = DATE_FMT
            cell.alignment = CTR
        elif c in (6, 8, 9, 10, 12):
            cell.alignment = CTR

for col, listname in [("H", "QueryExpected"), ("I", "YesNo"), ("L", "Status")]:
    dv = DataValidation(type="list", formula1="=%s" % LREF[listname],
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick a value from the list. Add new values on the Lists sheet, not here."
    dv.errorTitle = "Not on the list"
    ws.add_data_validation(dv)
    dv.add("%s%d:%s%d" % (col, AUD_FIRST, col, AUD_LAST))

ws.auto_filter.ref = "A5:%s%d" % (get_column_letter(len(AUD_COLS)), AUD_LAST)
zebra(ws, AUD_FIRST, AUD_LAST, len(AUD_COLS))
ws.conditional_formatting.add("B%d:B%d" % (AUD_FIRST, AUD_LAST),
    FormulaRule(formula=['$B%d="UNKNOWN CHART"' % AUD_FIRST],
                fill=FILL_RED, font=Font(size=9, bold=True, color=RED)))
ws.conditional_formatting.add("N%d:N%d" % (AUD_FIRST, AUD_LAST),
    FormulaRule(formula=['$N%d="NEXT"' % AUD_FIRST],
                fill=FILL_GREEN, font=Font(size=9, bold=True, color=GREEN)))
ws.conditional_formatting.add("I%d:I%d" % (AUD_FIRST, AUD_LAST),
    FormulaRule(formula=['$I%d="Yes"' % AUD_FIRST],
                fill=FILL_AMBER, font=Font(size=10, bold=True, color=AMBER)))
ws.conditional_formatting.add("F%d:F%d" % (AUD_FIRST, AUD_LAST),
    CellIsRule(operator="equal", formula=["0"], fill=FILL_BLUE,
               font=Font(size=10, bold=True, color=BLUE)))

n = AUD_LAST + 2
note(ws, n, "Version rotation is arithmetic, not chance. The allocator serves pool[uses mod version count], so with three versions and seven previous uses the next cycle serves version 2. The NEXT column marks that row, and it moves on its own as the chart's use count changes.", len(AUD_COLS))
note(ws, n + 1, "Rotation keys on the CHART's own use count, not on the cycle and not on the auditor. Keyed on the auditor, four auditors would meet three different versions in one sitting; keyed on the cycle, a chart that does not appear every cycle would be pinned to one version forever.", len(AUD_COLS))
note(ws, n + 2, "A chart with ONE active version shows every auditor the same planting. That is a tell as soon as anyone has seen it, and both the Chart Database and the dashboard flag it. Two is the minimum for rotation to mean anything.", len(AUD_COLS), FILL_AMBER)
note(ws, n + 3, "Planted findings of ZERO is legitimate and reads blue, not red: a curated clean chart. A set may carry no mutations and still author a query determination, which is why clean and authored are not mutually exclusive.", len(AUD_COLS))
note(ws, n + 4, "Always plant exempts a set from the clean quota, so it is planted whenever drawn. Use it sparingly — a curated chart that never comes up clean becomes its own tell, the same failure as a chart that always carries the same version.", len(AUD_COLS), FILL_AMBER)
note(ws, n + 5, "Query expected applies to IP-DRG only. Blank is NA and is NOT scored against the auditor: the system cannot read whether documentation supported a code, so an unauthored answer is not an answer.", len(AUD_COLS))

# ======================================================= Field Conventions
ws = sheet("Field Conventions", [3, 24, 92], freeze=None)
title_block(ws, "Field conventions — category and alias", "What goes in the two fields a trainer fills on upload, and why. Agreed 21 October 2026.", 3)
CONV = [
 ("SEC", "How the application actually behaves"),
 ("P", "Both fields already exist. `category` is String(200) and required; `alias` is String(100) and optional. Neither is a dropdown anywhere in the application: both are free-text boxes, and the category filter when allocating a batch is a free-text box too."),
 ("KV", "What upload stores|The category string verbatim, with only outer whitespace trimmed. Type `Sepsis, AKI` and the database holds exactly that one string. It is never split."),
 ("KV", "What the allocator does|Splits the TRAINER'S filter on commas, then substring-matches each piece against the whole stored string, OR'd together. So your filter is split and the chart's category is not; they meet by substring."),
 ("KV", "What follows|Several topics on one chart WORK for assignment — a chart filed as `Sepsis, AKI` is found by a filter of either. What breaks is counting: the application groups by the whole string, so `Sepsis, AKI` is a third value beside `Sepsis` and `AKI`. This workbook does the parsing the application does not."),
 ("SEC", "category"),
 ("KV", "Is|One or more short topic names, comma separated. Nothing else."),
 ("KV", "Example|`Sepsis` for a single topic. `Sepsis, AKI` where the chart genuinely teaches both."),
 ("KV", "Taken from|The SHORT NAME column of the Category Dictionary sheet, spelled exactly. That sheet is the vocabulary; the application has none."),
 ("KV", "Order matters a little|List the topic the ANSWER KEY turns on first. This workbook reads the first name as the primary topic, which is what the per-chart views show."),
 ("KV", "Length|Each name is at most 25 characters and the column holds 200, so four or five topics fit. Past that, the chart is probably two charts."),
 ("KV", "Never|A description, a sentence, a code number alone, or a name not in the dictionary. Every new spelling becomes a separate value in the application's own analytics and quietly fragments the counts."),
 ("SEC", "alias"),
 ("KV", "Is|The clinical scenario in a trainer's own words. A recognition handle, so somebody scanning sixty rows knows the chart without opening it."),
 ("KV", "Example|`68F septic shock, AKI on CKD3, pressors` · `34wk twin delivery, one NICU admit` · `Lap chole converted to open`"),
 ("KV", "Length|100 characters, and this is a hard database limit. SQLite does not enforce it and PostgreSQL rejects outright, so an over-long alias passes every local test and fails on the live service."),
 ("KV", "Never drives assignment|Alias is for finding and recognising. Category is for selecting. The allocator does not read alias at all."),
 ("KV", "Never contains PHI|It is free text typed AFTER de-identification, which makes it the likeliest place for a name, a date or a facility to come back into a scrubbed chart. Ages as a band, sex as a letter, no names, no dates, no facility."),
 ("KV", "Never hints at the finding|Both fields are reachable by a coder — category is rendered on the chart, and alias is covered by the search box. `Missed MCC` or `wrong PDx sequence` tells an auditor the answer before they read the chart, which voids the restraint measurement the auditor module exists to produce."),
 ("SEC", "The rule worth remembering"),
 ("P", "The topic names the SKILL, never the FINDING."),
 ("SEC", "Difficulty: two vocabularies, mapped"),
 ("P", "The application's enum is Beginner, Intermediate, Advanced, and that is what this workbook uses. The composition taxonomy and the HC framework speak of Basic, Moderate and Complex tiers. They are the same three bands under different names:"),
 ("MAP", "Beginner|Basic|Single encounter focus, few codes, clear documentation, straightforward guideline application."),
 ("MAP", "Intermediate|Moderate|Multiple diagnoses or procedures, some sequencing decisions, modifiers or CC/MCC capture."),
 ("MAP", "Advanced|Complex|Conflicting or incomplete documentation, query opportunities, tricky guidelines, multiple edits in play."),
 ("P", "Enter the application's word on upload and in this workbook. Read the taxonomy's word when planning composition. Nobody should have to convert in their head, which is why the mapping is written down here rather than remembered."),
 ("SEC", "Long descriptive names — worked examples"),
 ("P", "Experience produces names like \"Sepsis with pneumonia\" or \"CABG with 3 grafts\". These are real and worth recording, but they are not categories. One test settles it: would you ever build a batch by filtering on it? If yes, and other charts share it, it is a topic. If it is specific to this chart, it is an alias."),
 ("EX", "Sepsis with pneumonia|Sepsis, Respiratory medical|sepsis 2/2 RLL pneumonia|Two genuine topics, so both go in the category and the chart is found by a filter of either."),
 ("EX", "CABG with 3 grafts|Cardiac surgical|CABG x3, LIMA + 2 SVG|One topic plus a clinical detail. Nobody assigns a batch of three-graft charts; they assign Cardiac surgical. The graft count is the teaching point and belongs in the alias."),
 ("EX", "AKI on CKD3 in a septic patient|Sepsis, Renal|AKI on CKD3, sepsis source urinary|Two topics. The staging detail is what a trainer recognises the chart by, not what anyone filters on."),
 ("EX", "Lap chole converted to open|GI surgical|lap chole converted to open, bile leak|The conversion is the error the chart teaches, but it is one topic. Put the conversion in the alias so a trainer can find it; keep the category filterable."),
 ("P", "Three reasons not to put the long string in the category. It has to be retyped exactly to filter on, so in practice nobody can. It becomes its own value in the application's group_by, which fragments the counts. And it escapes the off-list guard, because with no comma the recognised count equals the topic count and the row reads as fine while being useless as a filter — that one is on discipline, not on this workbook."),
 ("P", "Nothing is lost by moving it to the alias: the application's search box covers chart number, category AND alias together, so typing CABG still finds the chart."),
 ("SEC", "A topic the taxonomy does not have"),
 ("P", "The 111 topics are not a closed list, and nothing in the application enforces them. Two ways to add one, and they are not interchangeable:"),
 ("KV", "For something that will last|It belongs in the composition taxonomy, with an ID, a weight and a target. That means taking its share of charts from a sibling topic, because the weights must still sum to the HC parent percentage. Ask for it and it is a ten-minute change to the taxonomy module, after which it appears in all three workbooks at once."),
 ("KV", "For something provisional|Use the spare rows at the bottom of the Category Dictionary. Type the specialty and a short name; a target is optional. The name is counted from that moment and charts carrying it stop being reported as off-list. It carries no agreed target, so it appears in coverage as NA rather than as a gap."),
 ("KV", "Either way, check the name|The Name check column must read OK. Because the application matches by substring, a name that contains or sits inside another in the same specialty makes both counts wrong — `Respiratory` would pick up every `Respiratory surgical` chart. This is why the governed names read `Respiratory medical` and `Thoracic surgical`."),
 ("KV", "What happens if you skip both|The chart still counts as a chart on Specialty Overview, but toward no topic's coverage. The Leader Dashboard reports it under 'Charts with an off-list category' so it cannot sit unnoticed, which is the only reason that tile exists."),
 ("SEC", "What this does not solve"),
 ("P", "The application still accepts anything typed into either field. This workbook is the vocabulary, not an enforcement mechanism, so a category typed from memory rather than copied from the dictionary will still be accepted and will still fragment the counts. Enforcement needs the field to become a controlled list in the application, which is a code change and out of scope here."),
]
r = 4
for kind, text in CONV:
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
        ws.row_dimensions[r].height = 13 * (1 + len(text) // 112)
        r += 1
    elif kind == "EX":
        want, cat, ali, why = text.split("|")
        a = ws.cell(row=r, column=2, value='"%s"' % want)
        a.font, a.fill, a.alignment = Font(name="Calibri", bold=True, size=10, color=RED), FILL_RED, WRAP
        b = ws.cell(row=r, column=3,
                    value="category:  %s\nalias:  %s\n%s" % (cat, ali, why))
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 15 + 13 * (2 + len(why) // 92)
        r += 1
    elif kind == "MAP":
        app, tax, desc = text.split("|")
        a = ws.cell(row=r, column=2, value="%s  =  %s" % (app, tax))
        a.font, a.fill, a.alignment = F_B, FILL_BLUE, WRAP
        b = ws.cell(row=r, column=3, value=desc)
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 13 * (1 + len(desc) // 96)
        r += 1
    else:
        k, v = text.split("|", 1)
        a = ws.cell(row=r, column=2, value=k)
        a.font, a.alignment, a.fill = F_B, WRAP, FILL_BAND
        b = ws.cell(row=r, column=3, value=v)
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 13 * (1 + len(v) // 96)
        r += 1

# ================================================================ Read Me
ws = sheet("Read Me", [3, 28, 94], freeze=None)
title_block(ws, "PracticeLab Chart Pool Tracker", "What is in the pool, by topic and specialty, uploaded when, and who should practise on it · built %s" % BUILT, 3)
READ = [
 ("SEC", "What this is"),
 ("P", "The training team's working view of the live chart pool. It answers four questions: what do we have, where are the holes, is the build keeping up, and which charts should this cohort get."),
 ("P", "It is maintained by hand for now. One row per chart on the Chart Database sheet, whose first nine columns are the live charts table in table order — so when the application can export, that export pastes straight in with no reshaping. That is the whole reason the column order looks the way it does."),
 ("SEC", "The sheets, in the order you need them"),
 ("KV", "Leader Dashboard|Twelve figures, the specialty table, and a list of where to look next. Read-only, all formulas. Start here."),
 ("KV", "Chart Database|Where the work is recorded. One row per chart. The only sheet most people type into."),
 ("KV", "Category Dictionary|The 111 topics and — the point of the sheet — the SHORT NAME to type in the application. Live counts and gaps beside each."),
 ("KV", "Assignment Builder|Set filters, read the count, filter the database. This is the selective-practice tool."),
 ("KV", "Specialty Overview|A headcount of charts per specialty, with the difficulty split."),
 ("KV", "Monthly Trend|Uploads by month and specialty, 24 months from an editable start."),
 ("KV", "Recent Activity|7, 30 and 90 day windows, plus uploads by trainer."),
 ("KV", "Field Conventions|What goes in category and alias, and why. Read before briefing a trainer."),
 ("KV", "Lists|The source of every dropdown. Add a value here, never straight into a cell."),
 ("SEC", "The one thing to understand about counting"),
 ("P", "A chart may carry several topics in one comma-separated category string, because that is how the application works. Two sheets therefore count two different things, and both are right:"),
 ("KV", "Specialty Overview counts CHARTS|A chart filed as `Sepsis, AKI` counts once. Use it for a headcount and for % of target."),
 ("KV", "Category Dictionary counts TOPIC COVERAGE|The same chart counts under Sepsis AND under AKI, because it teaches both. Its total is therefore larger than the number of charts. Use it for gaps."),
 ("P", "Matching uses the same substring test the application uses, which is why the short names are guaranteed never to contain one another. `Respiratory` inside `Respiratory surgical` would have made one topic's count silently include another's; that is why the names read `Respiratory medical` and `Thoracic surgical`."),
 ("SEC", "Keeping it honest"),
 ("KV", "After every batch|Add 1 to Times assigned and set Last assigned on the rows you used. Nothing else keeps the never-assigned reserve meaningful."),
 ("KV", "Answer key|Set it Yes once a key exists. An Active chart marked No can reach a batch and then fail to score, which is the one error this file is best placed to catch."),
 ("KV", "Retiring|Set status to Retired. Keep the row — deleting it loses the history of what left the pool and when."),
 ("KV", "Capacity|Formulas cover database rows %d to %d, about a third again over the 2,942-chart target. Paste past row %d and the dashboard quietly stops counting the overflow." % (DB_FIRST, DB_LAST, DB_LAST)),
 ("SEC", "Its relationship to the other two workbooks"),
 ("KV", "Chart Composition Taxonomy|The standard: what the pool SHOULD contain, topic by topic, with weights and targets. This file's targets come from there."),
 ("KV", "Chart Inventory Tracker|The build programme: expected dates, FTE, slippage, issues. Deliberately a separate file, because it answers to a different audience on a different cadence."),
 ("KV", "This file|The live pool and day-to-day assignment, for the whole training team. All three import one topic module, so the taxonomy cannot differ between them."),
 ("SEC", "What it cannot do"),
 ("P", "There are no native PivotTables — the tool that writes this file cannot create them. The summary views are formulas instead, which need no refresh and survive being emailed. For ad-hoc pivoting, select the Chart Database and insert a PivotTable; it is a flat table with a header row, which is all a pivot needs."),
 ("P", "It is not connected to the application. Nothing here reads or writes PracticeLab, and nothing in PracticeLab knows this file exists. The moment the application can export the charts table, the Chart Database sheet is where that export lands."),
]
r = 4
for kind, text in READ:
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
        ws.row_dimensions[r].height = 13 * (1 + len(text) // 114)
        r += 1
    else:
        k, v = text.split("|", 1)
        a = ws.cell(row=r, column=2, value=k)
        a.font, a.alignment, a.fill = F_B, WRAP, FILL_BAND
        b = ws.cell(row=r, column=3, value=v)
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 13 * (1 + len(v) // 98)
        r += 1

ORDER = ["Read Me", "Leader Dashboard", "Chart Database", "Category Dictionary",
         "Audit Versions", "Assignment Builder", "Specialty Overview",
         "Monthly Trend", "Recent Activity", "Field Conventions", "Lists"]
for name in ORDER:
    wb.move_sheet(name, offset=len(wb.sheetnames) - wb.sheetnames.index(name) - 1)
wb.active = 0
wb.save(OUT)
print("wrote %s" % OUT)
print("sheets: %s" % ", ".join(wb.sheetnames))
print("topics: %d   short names: %d   database rows: %d"
      % (len(FLAT), len(SHORT_NAME), DB_LAST - DB_FIRST + 1))
