#!/usr/bin/env python3
"""Builds PracticeLab_Chart_Composition_Taxonomy.xlsx.

The topic layer BENEATH the Coverage Matrix in PracticeLab_HC.xlsx. Every
parent percentage here is carried from that file's Section 6 unchanged; the
topics decompose it and must sum back to the parent exactly, which the
TOTAL row on each sheet proves. Nothing here restates a number the HC model
already owns -- the baseline pools are typed once, in POOLS below.

Dated when it is built, not when someone remembered to change a string:
a regenerated document carrying an old date is worse than an undated one.
"""
import datetime as _dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BUILT = _dt.date.today().strftime("%d %B %Y")
OUT = "docs/PracticeLab_Chart_Composition_Taxonomy.xlsx"

NAVY, ACCENT, GREY, RED = "1F3864", "2E75B6", "595959", "B23A33"
HDR_BG, BAND_BG, NOTE_BG, EDIT_BG = "DCE6F1", "F2F6FB", "FFF4E5", "FDF7E3"

F_TITLE = Font(bold=True, size=15, color=NAVY)
F_SUB = Font(size=10, italic=True, color=GREY)
F_H = Font(bold=True, size=10, color="FFFFFF")
F_SEC = Font(bold=True, size=11, color=NAVY)
F_B = Font(bold=True, size=10)
F_N = Font(size=10)
F_SM = Font(size=9, color=GREY)
F_RED = Font(size=10, bold=True, color=RED)

FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_SUBH = PatternFill("solid", fgColor=HDR_BG)
FILL_BAND = PatternFill("solid", fgColor=BAND_BG)
FILL_NOTE = PatternFill("solid", fgColor=NOTE_BG)
FILL_EDIT = PatternFill("solid", fgColor=EDIT_BG)

THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")
TOP = Alignment(vertical="top")

from _chart_taxonomy_data import (  # noqa: E402
    POOLS, SHEET_OF, DIFF_MIX, TOPICS, priority_of,
)

wb = Workbook()
wb.remove(wb.active)


def sheet(title, widths, freeze="A5"):
    ws = wb.create_sheet(title)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.sheet_view.showGridLines = False
    if freeze:
        ws.freeze_panes = freeze
    return ws


def title_block(ws, title, sub, span):
    ws["A1"] = title
    ws["A1"].font = F_TITLE
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    ws["A2"] = sub
    ws["A2"].font = F_SUB
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    ws.row_dimensions[1].height = 22


def header_row(ws, row, labels, height=32):
    for c, lab in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=c, value=lab)
        cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, BOX
    ws.row_dimensions[row].height = height


def note(ws, row, text, span, fill=FILL_NOTE):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.fill, c.alignment = F_SM, fill, WRAP
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = max(14, 13 * (1 + len(text) // 150))


# ============================================================== Read Me
ws = sheet("Read Me", [3, 34, 96], freeze=None)
title_block(ws, "PracticeLab — Ideal Chart Composition by Topic", f"Inventory classification for chart identification and sourcing · built {BUILT}", 3)

READ_ME = [
    ("SEC", "What this workbook is"),
    ("P", "The topic layer beneath the Coverage Matrix in PracticeLab_HC.xlsx. The HC model answers how many charts each specialty needs and what the team costs. It does not say which charts. This does: for every specialty it names the topics the pool must contain, the share of the pool each topic should hold, and the resulting target count."),
    ("P", "It is a classification taxonomy, not an inventory. No chart is listed here. It is the standard a sourced chart is classified against and the yardstick a gap report is measured by."),
    ("SEC", "Its relationship to the HC model"),
    ("KV", "Baseline chart pools|Typed once, on Specialty Summary, from the HC Specialty Grid (Baseline Charts Required, +10% buffer). Change a pool there and every topic target reflows."),
    ("KV", "Parent percentages|Carried from HC Chart Selection section 6 (Coverage Matrix) unchanged. Topic weights decompose a parent and sum back to it exactly — the TOTAL row on each sheet proves it."),
    ("KV", "Difficulty mix|HC section 4 sets 40% Basic / 40% Moderate / 20% Complex across the pool. Applied at specialty level on Specialty Summary. Each topic carries a skew instead, because a topic such as critical care cannot hold a Basic-tier chart."),
    ("KV", "Sourcing channels|The C1–C8 codes are HC section 3. Each topic names the channel most likely to yield it, so a gap in a topic points at a report to pull from."),
    ("KV", "Required tags|HC section 7 lists eight mandatory tags per chart. The Tag Dictionary sheet repeats them and adds the Topic ID this workbook introduces, which is the field that makes a topic-level gap report possible at all."),
    ("SEC", "How to use it"),
    ("KV", "Sourcing|Read Target Charts as the ceiling for a topic. Once it is filled, further charts in that topic displace coverage elsewhere, however good they are."),
    ("KV", "Classifying|Every chart entering the pool gets exactly one Topic ID. A chart that genuinely spans two topics is classified by the element its answer key turns on."),
    ("KV", "Gap review|Count live charts per Topic ID against Target Charts. HC section 9 sets the trigger at 80% of target, reviewed monthly and at each half-yearly refresh."),
    ("KV", "Changing a weight|Edit the Topic % cell (shaded). The target recalculates and the TOTAL row will stop reading 100% until the other weights in that parent category are rebalanced. That is the point — the sheet refuses to let a topic quietly grow."),
    ("KV", "Build priority|P1, P2 or P3 per topic, in a column of its own, because priority and volume are different questions. The weight says how many charts a topic should hold once the pool is complete; the priority says which topics are sourced and built before it is. IP-DRG leads with the OB and newborn block across both medical and surgical DRGs, then GI, respiratory and cardiovascular."),
    ("SEC", "The four populations are separate"),
    ("P", "ED Facility, ED Profee, ED Single Path and E/M are four distinct chart populations, confirmed on 15 October 2026. The same clinical encounter coded for the facility, coded professionally, and coded single-path produces three different charts, and none of them sits in the E/M pool. Their pools therefore add rather than overlap, and the E/M topic list holding no ED setting is deliberate."),
    ("P", "The consequence for sourcing is the part worth saying out loud: four populations means four separate pulls, not one pull classified four ways. A chart cannot be filed under an ED Facility topic and an ED Profee topic at once, and reusing one encounter across two pools would put the same documentation in front of a coder twice under two different names."),
    ("SEC", "What the targets are and are not"),
    ("P", "A target is a proportion of a pool, not a forecast of what production will yield. Where the two disagree the pool is wrong, not the sheet: a pool that drifts toward whatever charts were easy to find teaches whatever those charts happened to contain."),
    ("P", "Rounding is per topic, so the sum of targets can differ from the pool by a chart or two. Each sheet shows the variance rather than hiding it, and the pool is the authority."),
    ("SEC", "Scope"),
    ("P", "Seven specialties. IP-DRG, ED Facility, E/M and SDS carry HC baseline pools. ED Profee, Surgery and ED Single Path each carry a pool set on 15 October 2026 (400, 300 and 300) rather than one derived in the HC model. Denials/Edits and Ancillary are deferred — their HC pools and coverage matrices stand, and a topic layer for them is the obvious next addition."),
    ("P", "Open questions that need a decision before this is final are on the Open Decisions sheet. They are listed rather than resolved because each changes a number somebody else owns."),
]

r = 4
for kind, text in READ_ME:
    if kind == "SEC":
        r += 1
        c = ws.cell(row=r, column=2, value=text)
        c.font = F_SEC
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        r += 1
    elif kind == "P":
        c = ws.cell(row=r, column=2, value=text)
        c.font, c.alignment = F_N, WRAP
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        ws.row_dimensions[r].height = 13 * (1 + len(text) // 118)
        r += 1
    else:
        k, v = text.split("|", 1)
        a = ws.cell(row=r, column=2, value=k)
        a.font, a.alignment, a.fill = F_B, WRAP, FILL_BAND
        b = ws.cell(row=r, column=3, value=v)
        b.font, b.alignment = F_N, WRAP
        ws.row_dimensions[r].height = 13 * (1 + len(v) // 96)
        r += 1

# ====================================================== Specialty Summary
ws = sheet("Specialty Summary", [20, 7, 13, 11, 10, 12, 11, 11, 11, 11, 34])
title_block(ws, "Specialty Summary — baseline pools and difficulty mix", "Pools are the only hand-typed counts in this workbook. Shaded cells are inputs; everything else is a formula.", 11)
header_row(ws, 4, ["Specialty", "Type", "Baseline\nChart Pool", "% of\nTotal Pool", "Topics\nDefined", "Allocated\nby Topic", "Variance\n(rounding)", "Basic\n(40%)", "Moderate\n(40%)", "Complex\n(20%)", "Pool source"])

first = 5
for i, (spec, typ, pool, src) in enumerate(POOLS):
    r = first + i
    tsheet = SHEET_OF[spec]
    vals = [
        spec, typ, pool, f"=C{r}/$C${first + len(POOLS)}",
        f"='{tsheet}'!$D$2", f"='{tsheet}'!$F$2", f"=F{r}-C{r}",
        f"=ROUND(C{r}*0.4,0)", f"=ROUND(C{r}*0.4,0)", f"=ROUND(C{r}*0.2,0)", src,
    ]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, TOP
        if c == 1:
            cell.font = F_B
        if c == 3:
            cell.fill = FILL_EDIT
        if c == 4:
            cell.number_format = "0.0%"
        if c == 11:
            cell.alignment = WRAP
            cell.font = F_SM
ws.cell(row=first + len(POOLS), column=1, value="TOTAL").font = F_B
tr = first + len(POOLS)
for c, v in [(3, f"=SUM(C{first}:C{tr-1})"), (4, f"=SUM(D{first}:D{tr-1})"),
             (5, f"=SUM(E{first}:E{tr-1})"), (6, f"=SUM(F{first}:F{tr-1})"),
             (7, f"=SUM(G{first}:G{tr-1})"), (8, f"=SUM(H{first}:H{tr-1})"),
             (9, f"=SUM(I{first}:I{tr-1})"), (10, f"=SUM(J{first}:J{tr-1})")]:
    cell = ws.cell(row=tr, column=c, value=v)
    cell.font, cell.fill, cell.border = F_B, FILL_SUBH, BOX
    if c == 4:
        cell.number_format = "0.0%"
for c in (1, 2, 11):
    ws.cell(row=tr, column=c).fill = FILL_SUBH
    ws.cell(row=tr, column=c).border = BOX

note(ws, tr + 2, "Difficulty columns apply the pool-level 40 / 40 / 20 mix from HC Chart Selection section 4. They are a specialty-level target: no single topic is required to hold that mix, and some topics cannot (critical care has no Basic-tier chart; a routine lab has no Complex one). Each topic sheet carries a skew column instead.", 11)
note(ws, tr + 3, "Variance is the rounding drift between the sum of topic targets and the pool. The pool is the authority; a variance of more than a few charts means a topic weight was edited without rebalancing its parent category.", 11)
note(ws, tr + 4, "Three specialties sit outside the HC model: ED Profee (400), Surgery (300) and ED Single Path (300). Each has a pool but none has the +10% buffer calculation, batch count or build-hour line the other four get from the HC Specialty Grid. That is 1,000 charts the HC model does not know about — at its own build rates roughly 1,500 to 2,250 build hours, close to a further FTE. The Specialty Grid, Chart Pool and FTE sheets understate until all three are added there.", 11, PatternFill("solid", fgColor="FDECEA"))


# ======================================================== topic sheets
TOPIC_COLS = ["Topic ID", "Coverage\ncategory", "Topic", "Scope — what counts here",
              "Not here\n(goes where instead)", "Topic %\nof pool", "Target\ncharts",
              "Build\npriority", "Difficulty\nskew", "Primary sourcing\nchannel",
              "Key elements the chart must exercise", "Notes"]
TOPIC_W = [10, 20, 38, 54, 30, 8, 8, 14, 12, 19, 44, 50]

for idx, (spec, typ, pool, src) in enumerate(POOLS):
    name = SHEET_OF[spec]
    dim, cats = TOPICS[spec]
    ws = sheet(name, TOPIC_W, freeze="A5")
    ncols = len(TOPIC_COLS)

    ws["A1"] = "%s — ideal chart composition by topic" % spec
    ws["A1"].font = F_TITLE
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws.row_dimensions[1].height = 22

    strip = [("Baseline pool", f"='Specialty Summary'!$C${first + idx}"),
             ("Topics", None), ("Allocated", None), ("Variance", None)]
    for i, (lab, _) in enumerate(strip):
        lc = ws.cell(row=2, column=1 + i * 2, value=lab)
        lc.font, lc.fill, lc.alignment = F_SM, FILL_SUBH, Alignment(horizontal="right", vertical="center")
        vc = ws.cell(row=2, column=2 + i * 2)
        vc.font, vc.fill, vc.alignment = F_B, FILL_SUBH, Alignment(horizontal="left", vertical="center")
    ws["B2"] = f"='Specialty Summary'!$C${first + idx}"
    ws.cell(row=2, column=9, value="Dimension: %s" % dim).font = F_SEC
    ws.merge_cells(start_row=2, start_column=9, end_row=2, end_column=ncols)
    ws.row_dimensions[2].height = 18

    header_row(ws, 4, TOPIC_COLS)

    r = 5
    band_rows = []
    for cat, parent, rows in cats:
        bc = ws.cell(row=r, column=1, value="%s  —  HC Coverage Matrix parent: %s" % (cat.upper(), ("%g%%" % (parent * 100))))
        bc.font, bc.fill, bc.alignment = Font(bold=True, size=10, color=NAVY), FILL_SUBH, TOP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        for c in range(6, ncols + 1):
            ws.cell(row=r, column=c).fill = FILL_SUBH
        band_rows.append((r, cat))
        r += 1
        for t in rows:
            tid, topic, scope, excl, pct, skew, chan, elems, notes = t
            vals = [tid, cat, topic, scope, excl or "—", pct, f"=ROUND(F{r}*$B$2,0)",
                    priority_of(tid), skew, chan, elems, notes or ""]
            for c, v in enumerate(vals, start=1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.font, cell.alignment, cell.border = F_N, WRAP, BOX
                if c == 1:
                    cell.font = F_B
                elif c == 6:
                    cell.number_format = "0%"
                    cell.fill = FILL_EDIT
                    cell.alignment = WRAP_C
                elif c == 7:
                    cell.font = F_B
                    cell.alignment = WRAP_C
                elif c == 8:
                    cell.alignment = WRAP_C
                    pr = cell.value
                    cell.font = Font(size=9, bold=True,
                                     color=(RED if pr.startswith("P1") else
                                            GREY if pr.startswith("P3") else "000000"))
                elif c in (5, 12):
                    cell.font = F_SM
            longest = max(len(scope), len(elems), len(notes or ""), len(topic) * 2)
            ws.row_dimensions[r].height = max(30, 11 * (1 + longest // 56))
            r += 1

    last = r - 1
    tot = r
    tc = ws.cell(row=tot, column=1, value="TOTAL")
    tc.font, tc.fill = F_B, FILL_H
    tc.font = F_H
    ws.merge_cells(start_row=tot, start_column=1, end_row=tot, end_column=5)
    f_tot = ws.cell(row=tot, column=6, value="=SUM(F5:F%d)" % last)
    f_tot.font, f_tot.fill, f_tot.number_format, f_tot.alignment = F_H, FILL_H, "0%", WRAP_C
    g_tot = ws.cell(row=tot, column=7, value="=SUM(G5:G%d)" % last)
    g_tot.font, g_tot.fill, g_tot.alignment = F_H, FILL_H, WRAP_C
    for c in range(8, ncols + 1):
        ws.cell(row=tot, column=c).fill = FILL_H
    ws.cell(row=tot, column=8, value="Weights must total 100%").font = F_H
    ws.merge_cells(start_row=tot, start_column=8, end_row=tot, end_column=ncols)
    ws.row_dimensions[tot].height = 20

    # roll-up check per category, written into the band row's notes span
    for br, cat in band_rows:
        parent_pct = dict((c, p) for c, p, _ in cats)[cat]
        chk = ws.cell(row=br, column=6,
                      value='=IF(ROUND(SUMIF($B$5:$B$%d,"%s",$F$5:$F$%d),6)=%s,"OK — topics sum to the %g%% parent","CHECK — topics do not sum to the %g%% parent")'
                            % (last, cat.replace('"', '""'), last, repr(parent_pct),
                               parent_pct * 100, parent_pct * 100))
        chk.font, chk.fill, chk.alignment = F_SM, FILL_SUBH, TOP
        ws.merge_cells(start_row=br, start_column=6, end_row=br, end_column=ncols)
        ws.row_dimensions[br].height = 16

    n = tot + 2
    ws["B2"] = f"='Specialty Summary'!$C${first + idx}"
    ws.cell(row=2, column=4, value="=COUNTA(A5:A%d)-%d" % (last, len(cats)))
    ws.cell(row=2, column=4).font = F_B
    ws.cell(row=2, column=6, value="=SUM(G5:G%d)" % last).font = F_B
    ws.cell(row=2, column=8, value="=F2-B2").font = F_B
    for c in (2, 4, 6, 8):
        ws.cell(row=2, column=c).fill = FILL_SUBH

    note(ws, n, "Shaded Topic %% cells are the only editable numbers on this sheet. Target charts recalculates from the pool on Specialty Summary. Edit a weight and the category check in its band row will read CHECK until the other weights in that category are rebalanced — the sheet is built to refuse a topic that quietly grows at its neighbours' expense.", ncols)
    note(ws, n + 1, "Target charts is a ceiling, not a quota to fill at any cost. Where eligible supply genuinely is not there — a topic narrowed by exclusion X2, or a low-volume case type — report it as constrained in the gap review rather than substituting charts from an adjacent topic.", ncols)
    note(ws, n + 2, "Variance in the strip above is rounding drift between the sum of topic targets and the pool. The pool is the authority.", ncols)

# ================================================== Coverage Dimensions
ws = sheet("Coverage Dimensions", [18, 22, 40, 10, 11, 58])
title_block(ws, "Coverage Dimensions — carried from the HC model", "Section 6 of PracticeLab_HC.xlsx, unchanged, plus the three specialties it does not cover. This is the parent layer every topic sheet decomposes.", 6)
header_row(ws, 4, ["Specialty", "Dimension", "Category", "Target %", "Target\ncharts", "Source and note"])

HC = "Carried from HC Chart Selection section 6"
NEWS = "Not in the HC model — set 2026-10-15 with this workbook"
DIMS = [
 ("IP-DRG", "DRG type", "Medical DRGs (top client volume)", 0.55, 693, HC),
 ("", "", "Surgical DRGs (top client volume)", 0.45, 693, HC),
 ("", "Severity", "Without CC/MCC", 0.30, 693, HC + ". A second, independent dimension: it cuts across every topic rather than sitting under one, so it is not decomposed on the topic sheet."),
 ("", "", "With CC", 0.35, 693, HC),
 ("", "", "With MCC", 0.35, 693, HC),
 ("", "Must include", "POA indicators · principal diagnosis sequencing · ICD-10-PCS procedures · query opportunities", None, None, HC + ". Every one of these appears in the elements column of at least one IP-DRG topic."),
 ("ED Facility", "Facility level", "Levels 1–2", 0.20, 704, HC),
 ("", "", "Level 3", 0.30, 704, HC),
 ("", "", "Level 4", 0.30, 704, HC),
 ("", "", "Level 5 / critical care", 0.20, 704, HC),
 ("", "Must include", "Injuries · infusions and injections · ED procedures · observation", None, None, HC),
 ("E/M", "Level", "Low (levels 2–3)", 0.35, 413, HC),
 ("", "", "Moderate (level 4)", 0.40, 413, HC),
 ("", "", "High (level 5)", 0.25, 413, HC),
 ("", "Method", "MDM-based", 0.80, 413, HC + ". Cross-cutting. Preventive visits, consults and time-levelled visits are not graded on medical decision making at all, so applicable_weights drops the MDM weights for them and the form is resolved per chart."),
 ("", "", "Time-based", 0.20, 413, HC + ". Topics EM-05, EM-16 and EM-17 are where these charts come from."),
 ("", "Must include", "New versus established · office versus hospital · modifier 25 · split and shared visits", None, None, HC),
 ("SDS", "Service line", "Orthopaedics", 0.25, 132, HC),
 ("", "", "GI / endoscopy", 0.25, 132, HC),
 ("", "", "Ophthalmology", 0.15, 132, HC),
 ("", "", "Pain management", 0.15, 132, HC),
 ("", "", "Other surgical", 0.20, 132, HC),
 ("", "Must include", "Modifiers (bilateral, distinct procedure) · implants and devices", None, None, HC),
 ("ED Profee", "ED E/M level", "Low acuity (99281 / 99282)", 0.08, 400, NEWS),
 ("", "", "Moderate (99283)", 0.18, 400, NEWS),
 ("", "", "Level 4 (99284)", 0.20, 400, NEWS),
 ("", "", "Level 5 (99285)", 0.24, 400, NEWS),
 ("", "", "Critical care (99291 / 99292)", 0.12, 400, NEWS),
 ("", "", "Cross-cutting (procedures, observation, split/shared)", 0.18, 400, NEWS),
 ("", "Must include", "Modifier 25 · the 99285 versus 99291 boundary · split and shared documentation", None, None, NEWS + ". The boundary charts only plant if AnswerKey.cc_boundary is set to borderline."),
 ("Surgery", "Service line", "High-volume service lines (general, ortho, CT/vascular, neuro, gynae)", 0.64, 300, NEWS),
 ("", "", "Specialty and cross-cutting", 0.36, 300, NEWS),
 ("", "Must include", "Global period and staged procedure modifiers · co-surgeon and assistant modifiers · laterality", None, None, NEWS),
 ("ED Single Path", "Acuity ladder", "Low acuity", 0.08, 300, NEWS),
 ("", "", "Moderate (level 3)", 0.18, 300, NEWS),
 ("", "", "Level 4", 0.20, 300, NEWS),
 ("", "", "Level 5", 0.22, 300, NEWS),
 ("", "", "Critical care", 0.12, 300, NEWS),
 ("", "", "Cross-cutting", 0.20, 300, NEWS),
 ("", "Must include", "Both level determinations on one record · legitimate divergence between them · modifier 25", None, None, NEWS + ". Divergence is the reason single path is a specialty and not a view of the other two ED pools."),
]
r = 5
for spec, dim, cat, pct, pool, src in DIMS:
    vals = [spec, dim, cat, pct, (None if pct is None or pool is None else round(pct * pool)), src]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.alignment, cell.border = F_N, WRAP, BOX
        if c == 1 and v:
            cell.font = F_B
        if c == 4 and v is not None:
            cell.number_format = "0%"
            cell.alignment = WRAP_C
        if c == 5:
            cell.alignment = WRAP_C
        if c == 6:
            cell.font = F_SM
        if dim == "Must include":
            cell.fill = FILL_BAND
    ws.row_dimensions[r].height = max(26, 11 * (1 + max(len(cat), len(src)) // 56))
    r += 1
note(ws, r + 1, "ED Facility, ED Profee and ED Single Path are three separate populations, not three views of one. The same encounter coded for the facility, coded professionally and coded single-path is three different charts; none of them belongs in the E/M pool, which is why the E/M dimension here has no ED setting. Confirmed 15 October 2026.", 6)
note(ws, r + 2, "Severity on IP-DRG and Method on E/M are cross-cutting dimensions: a chart has a CC/MCC status and an MDM-or-time basis whatever its topic. They are checked across the pool, not decomposed per topic, which is why the topic sheets carry one dimension each.", 6)
note(ws, r + 3, "Where a target percentage here changes, the matching band row on the topic sheet and its child weights must change together. The band row's check cell is what tells you they have come apart.", 6)

# ======================================================== Tag Dictionary
ws = sheet("Tag Dictionary", [26, 12, 60, 46])
title_block(ws, "Required tags per chart", "HC Chart Selection section 7, plus the one field this workbook adds. A chart missing a mandatory tag is not classified and cannot appear in a gap report.", 4)
header_row(ws, 4, ["Tag", "Mandatory", "What is captured", "Why it is needed"])
TAGS = [
 ("Topic ID", "Yes — new", "The topic from this workbook, exactly one per chart (e.g. IPD-02, EDP-07). A chart spanning two topics is classified by the element its answer key turns on.",
  "The field this workbook adds. Without it a gap report can only be run at coverage-category level, which is where the HC model already stops — a category can look full while one topic inside it holds every chart."),
 ("Specialty and coverage category", "Yes", "Specialty plus the coverage-matrix category the chart fills.",
  "HC section 7. The parent of the Topic ID; kept so the two layers can be reconciled."),
 ("Difficulty tier", "Yes", "Basic, Moderate or Complex against the HC section 4 criteria.",
  "Drives the Week 1 / Week 2 mix. The topic sheet's skew column says what is plausible for a topic; this records what the chart actually is."),
 ("Learning objective(s)", "Yes", "The specific guideline or skill the chart teaches.",
  "HC section 7's teaching-value test: a chart with nothing to teach does not enter the pool, however clean it is."),
 ("Sourcing channel", "Yes", "Primary channel C1–C8 plus any secondary channels; for C1 and C7, the error or denial category targeted.",
  "Lets a topic gap be traced back to the report that would fill it."),
 ("Source type and client", "Yes", "QA/QR-validated or PL re-coded; client or facility as a de-identified reference.",
  "Carries the HC 60/40 source split and the S2 client-diversity minimum of three clients per specialty."),
 ("Guideline / code-set version", "Yes", "Fiscal year or code-set version the answer key is based on.",
  "The refresh depends on it: Oct 1 ICD-10 and IPPS, Jan 1 CPT, quarterly NCCI and OCE. A chart whose version is unknown cannot be refreshed, only rebuilt."),
 ("Build and validation dates", "Yes", "When built, who validated, when approved.",
  "Second-level validation before publishing is required for every chart, and for PL re-coded charts it is the only check on the key."),
 ("Usage count", "Yes", "Number of batches the chart has appeared in.",
  "Drives retirement, and enforces the rule that a chart may repeat across batches but never within one."),
 ("Answer key presence", "Recommended", "Whether a validated key exists, and in which table it lives.",
  "E/M and ED Profee keys live in em_answer_keys, which has no row in answer_keys. A query joining only against the ordinary key table reports zero keys for every E/M chart — which once told a trainer who had just entered five keys that nothing could be graded."),
 ("Authored error version(s)", "Recommended", "Whether the chart carries trainer-authored error sets for the auditor module, and how many versions.",
  "Version rotation keys on the chart's own use count, so the count has to be visible per chart. Hand-picked allocation is also the only mode that may pin a specific version."),
]
r = 5
for tag, mand, what, why in TAGS:
    for c, v in enumerate([tag, mand, what, why], start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.alignment, cell.border = F_N, WRAP, BOX
        if c == 1:
            cell.font = F_B
        if c == 2:
            cell.alignment = WRAP_C
            if v != "Yes":
                cell.font = Font(size=10, italic=True, color=GREY)
        if c == 4:
            cell.font = F_SM
    ws.row_dimensions[r].height = max(30, 11 * (1 + max(len(what), len(why)) // 58))
    r += 1
note(ws, r + 1, "Enforce these per FIELD, not per chart record. A check asking whether a chart has tags passes as soon as one tag is present; anchor the check on each value, then delete that value and confirm the check fails.", 4)

# ======================================================= Open Decisions
ws = sheet("Open Decisions", [5, 28, 66, 24, 20], freeze=None)
title_block(ws, "Decisions", "Settled ones first, with what was decided. The open ones each change a number somebody else owns, so they are listed rather than resolved — nothing on the topic sheets depends on them being settled first.", 5)
header_row(ws, 4, ["#", "Decision", "What is at stake, or what was decided", "Owner", "Status"])
SETTLED = "Settled 2026-10-15"
OPEN = "Open"
DEC = [
 ("ED Facility, ED Profee, ED Single Path and E/M are four separate chart populations",
  "Confirmed: an ED encounter coded for the facility, the same encounter coded professionally, and a single-path encounter are three different charts, and none of them belongs in the E/M pool. So the pools of 704, 400, 300 and 413 do not overlap and nothing is double-counted — but sourcing has to pull four distinct populations, and the E/M pool holding no ED setting is correct rather than an oversight.",
  "Confirmed by the user", SETTLED),
 ("E/M keeps no ED-setting share",
  "Follows from the above. ED E/M sits in ED Profee, the E/M topic list deliberately holds no ED setting, and the HC E/M pool of 413 is not oversized by it.",
  "Confirmed by the user", SETTLED),
 ("Add ED Profee, Surgery and ED Single Path to the HC model",
  "Pools of 400, 300 and 300 were set here, outside the HC model. None of them has a +10% buffer calculation, a per-batch average, a batch count or a build-hour line. That is 1,000 charts the HC Specialty Grid, Chart Pool, FTE Demand and FTE Summary sheets do not know about — at HC's own build rates roughly 1,500 to 2,250 hours, close to a further FTE. Until they are added, the team size in that model is understated.",
  "Whoever owns the HC model", OPEN),
 ("Set the cc_boundary flag policy for the 99285 / 99291 charts",
  "Topic EDP-07 exists for charts where the critical care call is genuinely arguable, and the auditor module only plants against them when a trainer has set AnswerKey.cc_boundary to borderline. Without a policy on who sets it and on what evidence, the topic fills with charts nothing is ever planted in.",
  "PL Trainer plus QR", OPEN),
 ("Agree the constrained-supply topics",
  "IPD-13 (mental health), EDF-11 (behavioural health), IPD-16 (obstetric surgical) and IPD-24 (transplant) are narrowed by exclusion X2 or by case rarity. Each needs a stated floor below which it is reported as constrained rather than chased, so a gap report does not show a permanent red against a topic nobody can fill.",
  "PL Trainer plus Compliance for X2", OPEN),
 ("Decide how a topic-level gap report is produced",
  "Topic ID has to be a filterable field on the chart record for any of this to be measurable. HC section 9 sets the trigger at 80% of target reviewed monthly, which is not workable by hand across roughly 125 topics.",
  "PL Trainer plus the platform team", OPEN),
 ("Extend the topic layer to Denials/Edits and Ancillary",
  "Both are deferred from this pass. Their HC pools (165 and 594) and coverage matrices stand, so they are classified at category level but not at topic level — 759 charts, a quarter of the HC total, outside this framework.",
  "PL Trainer", OPEN),
 ("Confirm the difficulty skew per topic against real charts",
  "The skew column is a judgement about what a topic can plausibly hold, made before any chart was sourced. Once a few hundred charts are classified and tiered, compare the actual tier distribution per topic against the skew and correct the column, not the charts.",
  "PL Trainer, at the first refresh", OPEN),
]
r = 5
for i, (dec, stake, owner, status) in enumerate(DEC, start=1):
    done = status != OPEN
    for c, v in enumerate([i, dec, stake, owner, status], start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.alignment, cell.border = F_N, WRAP, BOX
        if c == 1:
            cell.font, cell.alignment = F_B, WRAP_C
        if c == 2:
            cell.font = F_B
        if c == 4:
            cell.font = F_SM
        if c == 5:
            cell.alignment = WRAP_C
            cell.font = Font(size=9, bold=True, color=("2E7D32" if done else RED))
        if done:
            cell.fill = FILL_BAND
    ws.row_dimensions[r].height = max(34, 11 * (1 + len(stake) // 68))
    r += 1

wb.save(OUT)
print("wrote %s" % OUT)
print("specialties: %d   topics: %d   pool: %d"
      % (len(POOLS),
         sum(len(rows) for d, cats in TOPICS.values() for c, p, rows in cats),
         sum(p for _, _, p, _ in POOLS)))
