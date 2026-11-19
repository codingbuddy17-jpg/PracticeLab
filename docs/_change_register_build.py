"""
Builds docs/PracticeLab_Change_Register.xlsx AND the table in
docs/change_requests/REGISTER.md, from the one list below.

The change register records every change made to the original application
since the migration, for the IT team carrying them into their deployment
(this React frontend kept, the PostgreSQL dump restored, the backend rebuilt
in .NET). The CR markdown files hold the full spec; this workbook is the
detailed, filterable index: one row per CR on the Register sheet, one row per
file-level change on Change Detail, so "everything that changes scoring" or
"everything IT must build in .NET" is one filter.

One source for both outputs, because two hand-kept copies of one list drift —
see _chart_taxonomy_data.py for the time that cost this project. Add a change
HERE and rebuild; never edit the workbook or the REGISTER.md table by hand.

    python3 docs/_change_register_build.py

IT's progress columns (status, owner, notes) are theirs to fill in the
workbook. They are not in REGISTER.md on purpose: the markdown would go stale
the moment IT updated the workbook.
"""
import datetime as _dt
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "PracticeLab_Change_Register.xlsx")
REGISTER_MD = os.path.join(HERE, "change_requests", "REGISTER.md")
BUILT = _dt.date.today().strftime("%d %B %Y")

# ── The register ──────────────────────────────────────────────────────────────

CRS = [
    {
        "id": "CR-001",
        "title": "Practice review shows right as well as wrong; E/M review classified; Excel export",
        "kind": "C", "module": "PracticeLab — post-submit review",
        "score_impact": "No", "schema": "None",
        "commits": "db51300, f6198ef", "date": "2026-11-19",
        "order": "Backend first, then frontend patch",
        "spec": "change_requests/CR-001/CR-001.md",
        "summary": ("Every graded chart carries a classified side-by-side of key and coder "
                    "(right and wrong). E/M and ED Profee are sectioned: E/M level, diagnoses, "
                    "CPT, then COPA / Data Review / Risk element by element. Trainer and coder "
                    "screens render it; an Excel export downloads it."),
    },
    {
        "id": "CR-002",
        "title": "E/M primary diagnosis becomes a scoring factor; diagnosis dots ignored",
        "kind": "B", "module": "PracticeLab — E/M and ED Profee grading",
        "score_impact": "Yes", "schema": "None",
        "commits": "bccf4ff", "date": "2026-11-19",
        "order": "After CR-001",
        "spec": "change_requests/CR-002/CR-002.md",
        "summary": ("Primary diagnosis earns half the Dx weight, all or nothing, only when listed "
                    "first; secondaries share the other half. E119 now matches E11.9. Stored "
                    "scores are not rescored; Re-grade applies the rule."),
    },
]

# One row per file-level change.
# area: Backend | Frontend | Database | Script | Test | Docs
# it_action: Implement in .NET | Apply patch | Run against your API | None (reference)
CHANGES = [
    # ── CR-001 ──
    ("CR-001", "Backend", "backend/services/practice_review.py", "build_review()", "Added",
     "Builds the review for one chart: sections of rows (item, key, coded, status, note) plus a summary count.",
     "Grading feedback listed only what lost points.",
     "Every key and coder line is listed with Correct / Missed / Extra / Differs.",
     "Implement in .NET", "No", "CR-001 §3, §4.1"),
    ("CR-001", "Backend", "backend/services/practice_review.py", "_code_sections()", "Added",
     "IP/OP/Surgery/ED Facility sections: Principal Dx, Secondary Dx (POA compared), PCS, CPT (modifier and units compared).",
     "—", "Codes compared without dots, case-insensitive, as multisets.",
     "Implement in .NET", "No", "CR-001 §3.2"),
    ("CR-001", "Backend", "backend/services/practice_review.py", "_em_sections() / _mdm_section()", "Added",
     "E/M and ED Profee sections: E/M Level, Diagnoses, CPT, then COPA / Data Review / Risk element by element, or Time.",
     "E/M review fell through the IP/OP layout; a reasoning score like 6.7 of 10 was unexplained.",
     "Each MDM table lists the key's and the coder's elements and says 'Matched m of n'.",
     "Implement in .NET", "No", "CR-001 §3.3, §3.5"),
    ("CR-001", "Backend", "backend/services/practice_review.py", "ELEMENT_LABELS", "Added",
     "Display labels for all 28 MDM elements, worded as on the coder's form.",
     "—", "A test fails per element the grader scores without a label.",
     "Implement in .NET", "No", "CR-001 §3.5"),
    ("CR-001", "Backend", "backend/services/practice_review.py", "review_workbook()", "Added",
     "Two-sheet .xlsx: Summary (one row per chart) and Review (one row per line), colour-coded, frozen header, filters.",
     "No export existed.", "Review downloadable as a formatted workbook.",
     "Implement in .NET", "No", "CR-001 §4.3"),
    ("CR-001", "Backend", "backend/routers/practicelab_pkg/practice_sessions.py", "_build_coder_results()", "Modified",
     "Attaches 'review' to every chart; reads practice_chart_drafts.em_data and em_answer_keys per E/M chart. A builder failure logs and returns review=null.",
     "Response had no review field.",
     "GET .../review, POST .../submit and GET .../by-token/{token} carry charts[].review / results[].review.",
     "Implement in .NET", "No", "CR-001 §4.1"),
    ("CR-001", "Backend", "backend/routers/practicelab_pkg/practice_sessions.py",
     "GET /practicelab/practice-sessions/{session_id}/review/export", "Added",
     "Trainer download of the review workbook.", "—", "200 .xlsx · 404 no session · 400 not submitted.",
     "Implement in .NET", "No", "CR-001 §4.2"),
    ("CR-001", "Backend", "backend/routers/practicelab_pkg/practice_sessions.py",
     "GET /practicelab/practice-sessions/by-token/{token}/review/export", "Added",
     "Coder's own download, gated as the results screen is.", "—",
     "200 .xlsx · 404 unknown token · 400 not submitted · 403 results not released.",
     "Implement in .NET", "No", "CR-001 §4.2"),
    ("CR-001", "Backend", "backend/routers/practicelab_pkg/em_grading.py", "COPA_FIELDS / DR_FIELDS / RISK_FIELDS", "Moved",
     "The three MDM element lists moved from inside grade_em_chart to module constants.",
     "Lists were local to the grader.", "Grader and review read one list. No behaviour change.",
     "None (reference)", "No", "CR-001 §7"),
    ("CR-001", "Backend", "backend/services/excel_style.py", "EXTRA / DIFFER / INFO fills", "Added",
     "Semantic cell fills for Extra (orange), Differs (amber), Info (blue) beside PASS/FAIL.",
     "—", "Workbook result colours come from the shared style module.",
     "Implement in .NET", "No", "CR-001 §4.3"),
    ("CR-001", "Backend", "backend/services/practice_review.py", "_em_sections() — Diagnoses", "Modified",
     "E/M diagnoses shown as ONE 'Diagnoses' section (primary and secondary as rows) instead of separate Primary/Secondary sections. Commit f6198ef.",
     "Dx points sat beside an 'Order only' badge and read as a deduction for order.",
     "One section, one score, a note naming what the points are for. Superseded by CR-002 §4.",
     "None (reference)", "No", "CR-001 §3.4"),
    ("CR-001", "Frontend", "frontend/src/components/SubmissionReview.tsx", "SubmissionReview, ReviewExportButton", "Added",
     "Renders review sections grouped Coding / Reasoning with result badges; Export to Excel button.",
     "—", "Shared by the trainer and coder screens.", "Apply patch", "No", "CR-001 frontend.patch"),
    ("CR-001", "Frontend", "frontend/src/pages/practicelab/BatchDetailView.tsx", "ReviewModal", "Modified",
     "Export button in the header; full review replaces the single PDx line; old error list moved into a collapsed 'Scoring notes' (open when no review).",
     "Errors only; E/M shown in the IP/OP layout.", "Classified review for every specialty.",
     "Apply patch", "No", "CR-001 frontend.patch"),
    ("CR-001", "Frontend", "frontend/src/pages/PracticeSession.tsx", "ResultsView / EMResultCard", "Modified",
     "Coder results show the full review and an export by access code; E/M two-panel summary replaced by sections.",
     "Errors only; E/M as two panels of totals.", "Same review the trainer sees.",
     "Apply patch", "No", "CR-001 frontend.patch"),
    ("CR-001", "Frontend", "frontend/src/api/practicelabApi.ts", "downloadPracticeReview / downloadPracticeReviewByToken", "Added",
     "Literal-path downloads, so check_api_contracts.py can verify them.", "—", "—",
     "Apply patch", "No", "CR-001 frontend.patch"),
    ("CR-001", "Frontend", "frontend/src/api/download.ts", "saveBlob / detailOf", "Modified",
     "saveBlob extracted and detailOf exported for reuse.", "—", "No behaviour change.",
     "Apply patch", "No", "CR-001 frontend.patch"),
    ("CR-001", "Script", "scripts/smoke_deployed.py", "--session <id>", "Added",
     "Checks a submitted session's review shape, MDM explanations and that the export is an .xlsx.",
     "—", "IT runs it against their own API.", "Run against your API", "No", "CR-001 §6"),
    ("CR-001", "Test", "backend/tests/test_practice_review.py", "—", "Added",
     "Review content, E/M worked example, export gates, builder-fault fallback.", "—", "—",
     "None (reference)", "No", "CR-001 §6"),
    ("CR-001", "Test", "backend/tests/test_excel_house_style.py", "WRITERS / SEMANTIC", "Modified",
     "New Excel writer registered; Extra/Differs fills added to the semantic palette.", "—", "—",
     "None (reference)", "No", "—"),
    ("CR-001", "Docs", "CLAUDE.md · docs/README.md · docs/change_requests/", "—", "Added",
     "Change-request convention, register and CR-001 spec.", "—", "—",
     "None (reference)", "No", "—"),
    # ── CR-002 ──
    ("CR-002", "Backend", "backend/routers/practicelab_pkg/em_grading.py", "score_em_dx()", "Added",
     "Primary = half the Dx weight (whole if one key Dx), all or nothing, only when listed first; secondaries share the rest wherever listed; over-coding penalty unchanged.",
     "Dx scored as an order-blind set; primary had no weight.",
     "Primary listed second: 17.5 of 35 instead of 35.",
     "Implement in .NET", "Yes", "CR-002 §2"),
    ("CR-002", "Backend", "backend/routers/practicelab_pkg/em_grading.py", "grade_em_chart() — Dx block", "Modified",
     "Calls score_em_dx(). Applies to E/M and ED Profee.", "Proportional set match.", "Primary-weighted.",
     "Implement in .NET", "Yes", "CR-002 §2"),
    ("CR-002", "Backend", "backend/routers/practicelab_pkg/em_grading.py", "_clean_codes()", "Modified",
     "Removes dots from codes before comparison.",
     "E119 against a key of E11.9 scored as wrong (8.8 of 35 for three correct codes).",
     "Dots ignored, as IP/OP grading does.", "Implement in .NET", "Yes", "CR-002 §1, §2"),
    ("CR-002", "Backend", "backend/services/practice_review.py", "_em_sections() — Diagnoses", "Modified",
     "Primary row correct only when listed first; note gives primary and secondary points; flags a result scored under the earlier rule.",
     "Order shown as not scored.", "Explanation matches the new rule.", "Implement in .NET", "No", "CR-002 §4"),
    ("CR-002", "Test", "backend/tests/test_practice_review.py", "Dx rule tests", "Added",
     "Primary first / second / only / single-Dx key / over-coding / no key Dx / dotless / end-to-end.",
     "—", "Removing the 'listed first' condition fails three tests.", "None (reference)", "Yes", "CR-002 §5"),
    ("CR-002", "Database", "—", "—", "None",
     "No schema change. Stored scores are not rescored; Re-grade applies the rule per session.",
     "—", "—", "None (reference)", "Yes", "CR-002 §3"),
]

_ids = {c["id"] for c in CRS}
for row in CHANGES:
    assert row[0] in _ids, "change row names unknown CR %s" % row[0]
    assert len(row) == 11, "change row has %d fields, expected 11: %r" % (len(row), row[:3])
for c in CRS:
    assert os.path.exists(os.path.join(HERE, c["spec"])), "missing spec %s" % c["spec"]
    assert any(r[0] == c["id"] for r in CHANGES), "%s has no change rows" % c["id"]

# ── Workbook ──────────────────────────────────────────────────────────────────

NAVY, ACCENT = "1F3864", "2E75B6"
HEAD = PatternFill("solid", fgColor=NAVY)
WHITE = Font(color="FFFFFF", bold=True, size=10)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
INPUT = PatternFill("solid", fgColor="FFFDE7")
YES = PatternFill("solid", fgColor="FFF1F2")


def _table(ws, header_row, headers, rows, widths):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=header_row, column=i, value=h)
        c.fill, c.font = HEAD, WHITE
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[header_row].height = 30
    for r in rows:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
        for c in row:
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = "A%d:%s%d" % (header_row, get_column_letter(len(headers)), ws.max_row)


def _title(ws, text, sub):
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws["A2"] = sub
    ws["A2"].font = Font(italic=True, size=9, color="595959")


def build():
    wb = Workbook()

    # Read Me
    rm = wb.active
    rm.title = "Read Me"
    _title(rm, "PracticeLab — Change Register", "Built %s from docs/_change_register_build.py" % BUILT)
    lines = [
        ("What this is", "Every change made to the original PracticeLab application since the migration, for the IT team to carry into the migrated deployment."),
        ("Your deployment", "Kept this React frontend and the restored PostgreSQL database; the backend is .NET. Frontend changes arrive as a patch to apply; backend changes as a specification to implement; database changes as portable DDL."),
        ("Register", "One row per change request (CR). The grey-yellow columns are yours: status, owner, dates, notes."),
        ("Change Detail", "One row per file-level change. Filter 'IT action' for what you must build, or 'Score impact' for anything that moves scores."),
        ("Full specification", "docs/change_requests/CR-NNN/CR-NNN.md — the business rules, API contract and acceptance tests. This workbook indexes it; the CR file is the authority."),
        ("Order", "Within a CR marked Kind C, implement the backend before applying the frontend patch: the frontend is shared, and a patch calling new backend behaviour breaks your deployment until it exists. CRs apply in number order."),
        ("Kinds", "A frontend only · B backend only · C both · D schema."),
        ("Verify", "python3 scripts/smoke_deployed.py --base <your API> [--session <submitted session id>]"),
        ("Python code", "Reference reading only — never port it line by line."),
    ]
    for i, (k, v) in enumerate(lines, start=4):
        rm.cell(row=i, column=1, value=k).font = Font(bold=True, size=10)
        c = rm.cell(row=i, column=2, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    rm.column_dimensions["A"].width = 20
    rm.column_dimensions["B"].width = 110

    # Register
    rg = wb.create_sheet("Register")
    _title(rg, "Change requests", "Built %s · grey-yellow columns are for the IT team" % BUILT)
    heads = ["CR", "Title", "Kind", "Module", "Score impact", "Schema", "Commits", "Date",
             "Apply order", "Summary", "Spec file",
             "Backend (.NET)", "Frontend patch", "Verified by IT", "IT owner", "Done on", "IT notes"]
    rows = [(c["id"], c["title"], c["kind"], c["module"], c["score_impact"], c["schema"],
             c["commits"], c["date"], c["order"], c["summary"], "docs/" + c["spec"],
             "Not started", "Not started" if c["kind"] in ("A", "C") else "N/A",
             "Not started", "", "", "") for c in CRS]
    _table(rg, 4, heads, rows, [9, 40, 6, 24, 9, 9, 16, 11, 18, 60, 30, 14, 14, 14, 14, 11, 30])
    dv = DataValidation(type="list", formula1='"Not started,In progress,Done,Blocked,N/A"', allow_blank=True)
    rg.add_data_validation(dv)
    last = rg.max_row
    dv.add("L5:N%d" % last)
    for row in rg.iter_rows(min_row=5, max_row=last, min_col=12, max_col=17):
        for c in row:
            c.fill = INPUT
            c.border = BORDER
    for r in range(5, last + 1):
        if rg.cell(row=r, column=5).value == "Yes":
            rg.cell(row=r, column=5).fill = YES
            rg.cell(row=r, column=5).font = Font(bold=True, color="991B1B")

    # Change Detail
    cd = wb.create_sheet("Change Detail")
    _title(cd, "Change detail — one row per file-level change", "Built %s" % BUILT)
    heads = ["CR", "#", "Area", "File", "Function / route / component", "Change",
             "What changed", "Before", "After", "IT action", "Score impact", "Spec ref"]
    rows, n = [], {}
    for r in CHANGES:
        n[r[0]] = n.get(r[0], 0) + 1
        rows.append((r[0], n[r[0]], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]))
    _table(cd, 4, heads, rows, [9, 5, 10, 38, 34, 10, 60, 40, 40, 20, 9, 16])
    for r in range(5, cd.max_row + 1):
        if cd.cell(row=r, column=11).value == "Yes":
            cd.cell(row=r, column=11).fill = YES
            cd.cell(row=r, column=11).font = Font(bold=True, color="991B1B")

    wb.save(OUT)
    return OUT


# ── REGISTER.md table ─────────────────────────────────────────────────────────

START, END = "<!-- register:start -->", "<!-- register:end -->"


def write_register_md():
    lines = [START,
             "| CR | Title | Kind | Score impact | Schema | Commits | Apply order |",
             "|---|---|---|---|---|---|---|"]
    for c in CRS:
        rel = c["spec"].replace("change_requests/", "")
        lines.append("| [%s](%s) | %s | %s | %s | %s | `%s` | %s |" % (
            c["id"].replace("CR-", ""), rel, c["title"], c["kind"], c["score_impact"],
            c["schema"], c["commits"], c["order"]))
    lines.append("")
    lines.append("Built %s by `docs/_change_register_build.py`, which also writes "
                 "`docs/PracticeLab_Change_Register.xlsx` — the detailed version, with one "
                 "row per file-level change and the columns IT uses to track progress." % BUILT)
    lines.append(END)
    block = "\n".join(lines)
    s = open(REGISTER_MD).read()
    if START in s:
        s = re.sub(re.escape(START) + ".*?" + re.escape(END), block, s, flags=re.S)
    else:
        i = s.index("| CR | Title |")
        s = s[:i] + block + "\n"
    open(REGISTER_MD, "w").write(s)


if __name__ == "__main__":
    print(build())
    write_register_md()
    print(REGISTER_MD)
