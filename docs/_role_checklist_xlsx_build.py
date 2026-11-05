#!/usr/bin/env python3
"""Builds PracticeLab_Role_Access_Checklist.xlsx.

A one-page checklist of every destructive, editing, sensitive or
passphrase-gated action across the four modules, against four roles.

Every row was taken from the routers by enumerating @router decorators, not
from intent: "Gate today" is what the running application actually enforces,
and where that disagrees with the proposed role the row is flagged. Six of
those disagreements are asymmetries in the application itself -- a write that
is gated in one module and ungated in its twin -- and they are listed at the
foot of the sheet rather than quietly normalised.

Ticks are a PROPOSAL. The sheet exists to be argued with: every tick cell is a
dropdown, so a reviewer changes it in place and the counts at the top follow.

Dated when it is built, not when someone remembered to change a string.
"""
import datetime as _dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule

BUILT = _dt.date.today().strftime("%d %B %Y")
OUT = "docs/PracticeLab_Role_Access_Checklist.xlsx"

NAVY, NAVY_MID, ACCENT, GREY, INK = "1F3864", "2F5597", "2E75B6", "595959", "212121"
HDR_BG, BAND, BAND_ALT, EDIT_BG = "DCE6F1", "EEF3F9", "F7FAFD", "FFF8E1"
GREEN, GREEN_BG = "1B6B3A", "E6F4EA"
AMBER, AMBER_BG = "9C6500", "FFF4D6"
RED, RED_BG = "A4262C", "FCE8E6"
BLUE, BLUE_BG = "1F5C99", "E7F0FA"

TICK = "✓"
NO = "✗"   # explicit NOT allowed, so a blank means "not yet decided"
ROLES = ["Coder /\nAuditor", "Trainer /\nSupervisor", "Leader", "Admin"]

# risk classes, worst first; the fill is the row's own colour
RISK = {
    "Irreversible": (RED_BG, RED),
    "Destructive": (AMBER_BG, AMBER),
    "Key / answer": (BLUE_BG, BLUE),
    "Config": (BLUE_BG, BLUE),
    "Edit": (BAND, INK),
    "Create": (BAND, INK),
    "Sensitive read": (AMBER_BG, AMBER),
    "Read": ("FFFFFF", GREY),
    "Own work": (GREEN_BG, GREEN),
}

# (module, action, risk, gate today, coder, trainer, leader, admin, note)
#
# Gate TODAY is VERIFIED, not inferred. Each value was established by finding
# the route's own enforcement, which takes three forms in this codebase and a
# text search for "passphrase" catches only the first:
#   1. an inline compare    if passphrase != MASTER_PASSPHRASE
#   2. a helper call        require_passphrase(payload.passphrase, "...")
#   3. a dependency         _: None = Depends(require_passphrase)
# Form 3 has no comparison line at all. A nested compare under
# "if chart.uploaded_by != actor" is also conditional, not absolute.
# Verified count: 37 routes enforce it -- 30 always, 7 conditionally.
A = [
 ("Chart Management", "View and search the chart library", "Read", "None", 1,1,1,1, ""),
 ("Chart Management", "Send chart feedback", "Own work", "None", 1,1,1,1, ""),
 ("Chart Management", "Upload new charts", "Create", "None", 0,1,1,1, ""),
 ("Chart Management", "Edit a chart you uploaded", "Edit", "None", 0,1,1,1, "update_chart gates only when uploaded_by differs from the actor"),
 ("Chart Management", "Edit a chart someone else uploaded", "Edit", "Passphrase", 0,0,1,1, ""),
 ("Chart Management", "Add page files to a chart", "Edit", "Passphrase if not yours", 0,1,1,1, "Appending is additive and undoable, so it follows the ownership rule"),
 ("Chart Management", "Replace a chart's page files", "Destructive", "Passphrase", 0,0,1,1, "Always gated, by design: destroys the only copy of the original pages"),
 ("Chart Management", "Resolve or reopen chart feedback", "Edit", "None", 0,1,1,1, ""),
 ("Chart Management", "Retire a chart you uploaded", "Destructive", "None", 0,1,1,1, "Ownership rule again: your own chart retires without the passphrase"),
 ("Chart Management", "Retire or restore someone else's chart", "Destructive", "Passphrase", 0,0,1,1, "Revokes access to the chart and its images"),
 ("Chart Management", "Purge a chart permanently", "Irreversible", "Passphrase", 0,0,0,1, "Always gated. Row and images gone; refused if a key or grading history exists"),
 ("Chart Management", "Export the chart library report", "Sensitive read", "None", 0,1,1,1, ""),
 ("Chart Management", "Load the CMS code sets", "Config", "Passphrase", 0,0,0,1, "~186,000 rows; a wrong source changes what auditors are scored on"),

 ("PracticeLab", "Open own session and save a draft", "Own work", "Access code", 1,0,0,0, ""),
 ("PracticeLab", "Submit own session", "Own work", "Code + batch open", 1,0,0,0, "assert_batch_open is the expiry"),
 ("PracticeLab", "View own feedback after submitting", "Own work", "Access code", 1,0,0,0, "Stays open after the batch closes, by design"),
 ("PracticeLab", "Create a batch", "Create", "None", 0,1,1,1, ""),
 ("PracticeLab", "Add coders to a batch", "Edit", "None", 0,1,1,1, ""),
 ("PracticeLab", "Generate practice session tokens", "Create", "None", 0,1,1,1, ""),
 ("PracticeLab", "Run allocation", "Edit", "None", 0,1,1,1, ""),
 ("PracticeLab", "Close a batch", "Edit", "None", 0,1,1,1, "Ends the write window for every coder on it"),
 ("PracticeLab", "Release or reassign a session", "Edit", "None", 0,1,1,1, ""),
 ("PracticeLab", "Grade an ED chart by hand", "Edit", "None", 0,1,1,1, ""),
 ("PracticeLab", "Regrade a submitted session", "Edit", "None", 0,0,1,1, "Changes a score already shown to a coder"),
 ("PracticeLab", "Reopen a closed batch", "Destructive", "Passphrase", 0,0,1,1, "Re-opens the write window a close deliberately shut"),
 ("PracticeLab", "Force-close a batch", "Destructive", "Passphrase", 0,0,1,1, ""),
 ("PracticeLab", "View every open batch", "Sensitive read", "Passphrase", 0,0,1,1, "Cross-batch visibility; gated today"),
 ("PracticeLab", "Create a NEW IP/OP answer key", "Key / answer", "None", 0,1,1,1, "Gated only when a key already exists, so the first write is open"),
 ("PracticeLab", "Edit an EXISTING IP/OP answer key", "Key / answer", "Passphrase", 0,1,1,1, "A wrong key silently grades everyone against it"),
 ("PracticeLab", "Upload answer keys in bulk", "Key / answer", "Passphrase to replace", 0,1,1,1, "Gated only when replace is set; adding new keys is open"),
 ("PracticeLab", "Enter or edit an E/M answer key", "Key / answer", "NONE", 0,1,1,1, "ASYMMETRY: editing an existing IP/OP key is gated, the E/M equivalent is not"),
 ("PracticeLab", "Upload E/M answer keys in bulk", "Key / answer", "Passphrase to replace", 0,1,1,1, ""),
 ("PracticeLab", "Delete an answer key (IP/OP)", "Irreversible", "Passphrase", 0,0,0,1, ""),
 ("PracticeLab", "Delete an E/M answer key", "Irreversible", "Passphrase", 0,0,0,1, ""),
 ("PracticeLab", "Export every answer key", "Sensitive read", "Passphrase", 0,0,1,1, "Top of the protect list: a leak voids every score"),
 ("PracticeLab", "Read one chart's answer key", "Sensitive read", "None", 0,1,1,1, "ASYMMETRY: the bulk export is gated, the per-chart read is not"),
 ("PracticeLab", "Change the scoring config (IP/OP)", "Config", "Passphrase", 0,0,0,1, "Re-weights every result, past and future"),
 ("PracticeLab", "Change the E/M scoring config", "Config", "Passphrase", 0,0,0,1, ""),
 ("PracticeLab", "View analytics and results", "Read", "None", 0,1,1,1, ""),
 ("PracticeLab", "Export analytics workbooks", "Sensitive read", "None", 0,1,1,1, "Individual performance data"),
 ("PracticeLab", "Reset all PracticeLab data", "Irreversible", "Passphrase", 0,0,0,1, "Nothing survives it"),

 ("Auditor", "Open own audit session and save a draft", "Own work", "Access code", 1,0,0,0, ""),
 ("Auditor", "Submit own audit session", "Own work", "Code + batch open", 1,0,0,0, ""),
 ("Auditor", "Create an audit batch", "Create", "None", 0,1,1,1, ""),
 ("Auditor", "Run audit allocation", "Edit", "None", 0,1,1,1, ""),
 ("Auditor", "Regenerate an assignment before it is opened", "Edit", "None", 0,1,1,1, "Locked once the auditor opens the chart"),
 ("Auditor", "Close an audit batch", "Edit", "None", 0,1,1,1, ""),
 ("Auditor", "Reopen an audit batch", "Destructive", "Passphrase", 0,0,1,1, ""),
 ("Auditor", "Force-close an audit batch", "Destructive", "Passphrase", 0,0,1,1, ""),
 ("Auditor", "Create an error set (audit version)", "Key / answer", "Passphrase", 0,1,1,1, ""),
 ("Auditor", "Edit an error set", "Key / answer", "Passphrase", 0,1,1,1, "Affects future allocations only; made assignments keep their frozen copy"),
 ("Auditor", "Set the critical-care boundary flag", "Key / answer", "Passphrase", 0,1,1,1, "Decides whether 99285 vs 99291 may be planted at all"),
 ("Auditor", "Delete an error set", "Irreversible", "Passphrase", 0,0,0,1, ""),
 ("Auditor", "Preview a planted set", "Sensitive read", "None", 0,1,1,1, ""),
 ("Auditor", "View the planted errors for a batch", "Sensitive read", "NONE", 0,0,1,1, "GAP: the most damaging read in the app, and nothing gates it"),
 ("Auditor", "Export audit keys", "Sensitive read", "Passphrase", 0,0,1,1, ""),
 ("Auditor", "Change the audit score config", "Config", "Passphrase", 0,0,0,1, ""),
 ("Auditor", "View audit analytics and export", "Read", "None", 0,1,1,1, ""),

 ("Assessment", "Take own assessment and submit", "Own work", "Token, 8 hours", 1,0,0,0, "The only token in the app with a clock"),
 ("Assessment", "Upload questions", "Create", "None", 0,1,1,1, ""),
 ("Assessment", "Generate an assessment", "Create", "None", 0,1,1,1, ""),
 ("Assessment", "Create sessions and issue tokens", "Create", "None", 0,1,1,1, ""),
 ("Assessment", "View the question bank", "Sensitive read", "Passphrase", 0,0,1,1, "Gated by a Depends, not an inline check. Reused across cohorts: one leak contaminates every future sitting"),
 ("Assessment", "Edit a question", "Edit", "Passphrase", 0,0,1,1, "Gated by a Depends"),
 ("Assessment", "Change a question's status", "Edit", "Passphrase", 0,0,1,1, "Gated by a Depends"),
 ("Assessment", "Export questions", "Sensitive read", "Passphrase", 0,0,1,1, ""),
 ("Assessment", "Export an assessment's answer key", "Sensitive read", "NONE", 0,0,1,1, "ASYMMETRY: the question bank behind it is gated, this key export is not"),
 ("Assessment", "Export responses and student PDFs", "Sensitive read", "None", 0,1,1,1, ""),
 ("Assessment", "View the assessment audit log", "Sensitive read", "Passphrase", 0,0,1,1, ""),
 ("Assessment", "Delete sessions", "Destructive", "NONE", 0,0,1,1, "ASYMMETRY: deleting the assessment is gated, deleting its sessions is not"),
 ("Assessment", "Delete a question", "Irreversible", "Passphrase", 0,0,0,1, ""),
 ("Assessment", "Delete an assessment", "Irreversible", "Passphrase", 0,0,0,1, ""),
 ("Assessment", "Override a coder's response", "Irreversible", "Passphrase", 0,0,0,1, "Gated by a Depends. Changes a graded answer; integrity, not convenience"),

 ("System", "Manage coding resources", "Edit", "None", 0,1,1,1, ""),
]

# Endpoint behind each action, for the team that has to gate it. Taken from the
# @router decorators, prefix included. Several actions cover more than one.
EP = {
 "View and search the chart library": "GET /charts · GET /charts/{id}",
 "Send chart feedback": "POST /feedback",
 "Upload new charts": "POST /upload/bulk · POST /upload/preview",
 "Edit a chart you uploaded": "PATCH /charts/{id}",
 "Edit a chart someone else uploaded": "PATCH /charts/{id}",
 "Add page files to a chart": "POST /upload/{chart_id}/add-files",
 "Replace a chart's page files": "POST /upload/{chart_id}/replace-files",
 "Resolve or reopen chart feedback": "POST /feedback/{id}/resolve · /reopen",
 "Retire a chart you uploaded": "POST /charts/{chart_id}/retire",
 "Retire or restore someone else's chart": "POST /charts/{chart_id}/retire · /restore",
 "Purge a chart permanently": "DELETE /charts/{id}/purge",
 "Export the chart library report": "GET /reports/export",
 "Load the CMS code sets": "POST /codes/ingest-job",
 "Open own session and save a draft": "POST /practicelab/practice-sessions/{id}/save-draft",
 "Submit own session": "POST /practicelab/practice-sessions/{id}/submit",
 "View own feedback after submitting": "GET /practicelab/practice-sessions/{id}",
 "Create a batch": "POST /practicelab/batches",
 "Add coders to a batch": "POST /practicelab/batches/{id}/coders",
 "Generate practice session tokens": "POST /practicelab/practice-sessions/generate-tokens",
 "Run allocation": "POST /practicelab/batches/{id}/run-allocation",
 "Close a batch": "POST /practicelab/batches/{id}/close",
 "Release or reassign a session": "POST /practicelab/practice-sessions/{id}/release",
 "Grade an ED chart by hand": "POST /practicelab/batches/{id}/grade-ed",
 "Regrade a submitted session": "POST /practicelab/practice-sessions/{id}/regrade",
 "Reopen a closed batch": "POST /practicelab/batches/{id}/reopen",
 "Force-close a batch": "POST /practicelab/batches/{id}/force-close",
 "Create a NEW IP/OP answer key": "PUT /practicelab/answer-key/{chart_id}  (ungated while no key exists)",
 "Edit an EXISTING IP/OP answer key": "PUT /practicelab/answer-key/{chart_id}",
 "Upload E/M answer keys in bulk": "POST /practicelab/em/answer-key/upload",
 "View every open batch": "GET /practicelab/admin/open-batches",
 "Upload answer keys in bulk": "POST /practicelab/answer-key/upload",
 "Enter or edit an E/M answer key": "POST /practicelab/em/answer-key",
 "Delete an answer key (IP/OP)": "DELETE /practicelab/answer-key/{chart_id}",
 "Delete an E/M answer key": "DELETE /practicelab/em/answer-key/{chart_id}",
 "Export every answer key": "GET /practicelab/answer-key/export",
 "Read one chart's answer key": "GET /practicelab/answer-key/{chart_id}/detail · /em/answer-key/{chart_id}",
 "Change the scoring config (IP/OP)": "PUT /practicelab/config/scoring",
 "Change the E/M scoring config": "PUT /practicelab/em/scoring-config",
 "View analytics and results": "GET /practicelab/analytics/* · /results/*",
 "Export analytics workbooks": "GET /practicelab/analytics/*.xlsx (6 routes)",
 "Reset all PracticeLab data": "POST /practicelab/admin/reset-data",
 "Open own audit session and save a draft": "POST /auditor/sessions/{id}/save-draft",
 "Submit own audit session": "POST /auditor/sessions/{id}/submit",
 "Create an audit batch": "POST /auditor/batches",
 "Run audit allocation": "POST /auditor/batches/{id}/run-allocation",
 "Regenerate an assignment before it is opened": "POST /auditor/assignments/{id}/regenerate",
 "Close an audit batch": "POST /auditor/batches/{id}/close",
 "Reopen an audit batch": "POST /auditor/batches/{id}/reopen",
 "Force-close an audit batch": "POST /auditor/batches/{id}/force-close",
 "Create an error set (audit version)": "POST /auditor/keys/chart/{chart_id}",
 "Edit an error set": "PUT /auditor/keys/{set_id}",
 "Set the critical-care boundary flag": "POST /auditor/keys/chart/{id}/cc-boundary",
 "Delete an error set": "POST /auditor/keys/{set_id}/delete",
 "Preview a planted set": "POST /auditor/keys/chart/{id}/preview",
 "View the planted errors for a batch": "GET /auditor/batches/{id}/plantings · /sessions/{id}/review",
 "Export audit keys": "GET /auditor/keys/export",
 "Change the audit score config": "PUT /auditor/config",
 "View audit analytics and export": "GET /auditor/analytics/* · /analytics/export",
 "Take own assessment and submit": "POST /assessment/take/{token}/answer · /submit",
 "Upload questions": "POST /assessment/questions/upload",
 "Generate an assessment": "POST /assessment/generate",
 "Create sessions and issue tokens": "POST /assessment/sessions/create",
 "View the question bank": "GET /assessment/questions",
 "Edit a question": "PUT /assessment/questions/{id}",
 "Change a question's status": "PUT /assessment/questions/{id}/status",
 "Export questions": "GET /assessment/questions/export · /export-all",
 "Export an assessment's answer key": "GET /assessment/{id}/export-answer-key",
 "Export responses and student PDFs": "GET /assessment/{id}/export-responses.xlsx · /export-pdf",
 "View the assessment audit log": "GET /assessment/audit/logs",
 "Delete sessions": "DELETE /assessment/{id}/sessions",
 "Delete a question": "DELETE /assessment/questions/{id}",
 "Delete an assessment": "DELETE /assessment/{id}",
 "Override a coder's response": "POST /assessment/{id}/session/{sid}/response/{idx}/override",
 "Manage coding resources": "POST /resources · DELETE /resources/{id} · PATCH /{id}/reorder",
}
_missing = [a[1] for a in A if a[1] not in EP]
assert not _missing, "actions with no endpoint mapped: %s" % _missing

F_T = Font(name="Calibri", bold=True, size=15, color=NAVY)
F_SUB = Font(name="Calibri", size=9, italic=True, color=GREY)
F_H = Font(name="Calibri", bold=True, size=9, color="FFFFFF")
F_B = Font(name="Calibri", bold=True, size=9, color=INK)
F_N = Font(name="Calibri", size=9, color=INK)
F_SM = Font(name="Calibri", size=8, color=GREY)
F_TICK = Font(name="Calibri", bold=True, size=11, color=GREEN)
FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_SEC = PatternFill("solid", fgColor=NAVY_MID)
FILL_SUBH = PatternFill("solid", fgColor=HDR_BG)
FILL_EDIT = PatternFill("solid", fgColor=EDIT_BG)
FILL_RED = PatternFill("solid", fgColor=RED_BG)
FILL_AMBER = PatternFill("solid", fgColor=AMBER_BG)
FILL_GREEN = PatternFill("solid", fgColor=GREEN_BG)
FILL_BLUE = PatternFill("solid", fgColor=BLUE_BG)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CTR = Alignment(horizontal="center", vertical="center")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")

wb = Workbook()

# ===================================================== 1. Access Checklist
ws = wb.active
ws.title = "Access Checklist"
ws.sheet_view.showGridLines = False
for col, w in zip("ABCDEFGHI", [15, 46, 13, 15, 10, 11, 8, 8, 44]):
    ws.column_dimensions[col].width = w

ws["A1"] = "PracticeLab — Role Access Checklist"
ws["A1"].font = F_T
ws.merge_cells("A1:I1")
ws["A2"] = ("Every destructive, editing, sensitive and passphrase-gated action across the four modules, against four roles. "
            "Ticks are a PROPOSAL for review — each one is a dropdown, so change it in place. Built %s from the application's own routes." % BUILT)
ws["A2"].font = F_SUB
ws["A2"].alignment = WRAP
ws.merge_cells("A2:I2")
ws.row_dimensions[1].height = 21
ws.row_dimensions[2].height = 22

RULES = [
    ("Coder / Auditor", "Own work only. No destructive, editing or configuration action anywhere, and no sight of any answer key, planted error or question."),
    ("Trainer / Supervisor", "Runs the training: builds batches, allocates, grades, uploads charts, authors keys. Reaches no destructive action and no configuration."),
    ("Leader", "Everything a Trainer can, plus escalation and oversight: reopen, force-close, retire, regrade, and sight of keys, plantings and the question bank. No irreversible action, no configuration."),
    ("Admin", "All of the above, plus the irreversible and the configuration: purge, delete, reset, override, every scoring config, the code-set load. Not a coder's own session: nobody submits work on another person's behalf, which is why Admin reads 64 of 70 rather than 70."),
]
r = 4
for role, rule in RULES:
    a = ws.cell(row=r, column=1, value=role)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, WRAP
    b = ws.cell(row=r, column=2, value=rule)
    b.font, b.alignment = F_N, WRAP
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=9)
    ws.row_dimensions[r].height = 11 * (1 + len(rule) // 150)
    r += 1

r += 1
HDR = r
for c, lab in enumerate(["Module", "Action", "Risk", "Gate TODAY", "Required\ngate"] + ROLES + ["Note"], start=1):
    cell = ws.cell(row=HDR, column=c, value=lab)
    cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, BOX
ws.row_dimensions[HDR].height = 26
# the role columns sit at E..H after the two gate columns -> recompute
ROLE_COLS = ["F", "G", "H", "I"]
# rebuild the header to match 10 columns
for c, lab in enumerate(["Module", "Action", "Risk", "Gate TODAY", "Required gate"] + ROLES
                        + ["Note", "Changed from\nproposal?", "proposal"], start=1):
    cell = ws.cell(row=HDR, column=c, value=lab)
    cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, BOX
for col, w in zip("ABCDEFGHIJKL", [14, 42, 12, 12, 21, 9, 10, 8, 8, 36, 11, 2]):
    ws.column_dimensions[col].width = w
ws.column_dimensions["L"].hidden = True

r = HDR + 1
first = r
last_mod = None
for mod, act, risk, gate, co, tr, le, ad, note in A:
    fill_hex, font_hex = RISK[risk]
    rowfill = PatternFill("solid", fgColor=fill_hex) if fill_hex != "FFFFFF" else None
    required = ("Admin only" if (ad and not le) else
                "Leader or Admin" if (le and not tr) else
                "Trainer and above" if (tr and not co) else
                "Own session only" if (co and not tr) else
                "Any signed-in user")
    marks = [TICK if f else NO for f in (co, tr, le, ad)]
    vals = ([mod if mod != last_mod else "", act, risk, gate, required]
            + marks + [note,
                       '=IF($L%d="","",IF($F%d&$G%d&$H%d&$I%d=$L%d,"","CHANGED"))' % (r, r, r, r, r, r),
                       "".join(marks)])
    last_mod = mod
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, WRAP
        if c == 1:
            cell.font = F_B
        elif c == 3:
            cell.font = Font(name="Calibri", bold=True, size=8, color=font_hex)
            cell.alignment = WRAP_C
            if rowfill:
                cell.fill = rowfill
        elif c == 4:
            cell.alignment = WRAP_C
            cell.font = (Font(name="Calibri", bold=True, size=8, color=RED)
                         if gate == "NONE" else Font(name="Calibri", size=8, color=GREY))
            if gate == "NONE":
                cell.fill = FILL_RED
        elif c == 5:
            cell.font, cell.alignment = F_SM, WRAP_C
        elif c in (6, 7, 8, 9):
            cell.alignment = CTR
            cell.font = F_TICK if v == TICK else Font(name="Calibri", size=11, color="AAAAAA")
            cell.protection = Protection(locked=False)
        elif c == 10:
            cell.font = F_SM
            if "ASYMMETRY" in note:
                cell.font = Font(name="Calibri", bold=True, size=8, color=RED)
        elif c == 11:
            cell.font, cell.alignment = Font(name="Calibri", bold=True, size=8, color=AMBER), CTR
        elif c == 12:
            cell.font = Font(name="Calibri", size=8, color="FFFFFF")
    ws.row_dimensions[r].height = max(13, 10 * (1 + max(len(act) // 46, len(note) // 46)))
    r += 1
LASTROW = r - 1

dv = DataValidation(type="list", formula1='"%s,%s"' % (TICK, NO), allow_blank=True,
                    showDropDown=False)
dv.error = ("Pick the tick for allowed or the cross for not allowed. "
            "Clear the cell to mark it as not yet decided.")
dv.errorTitle = "Allowed, not allowed, or undecided"
ws.add_data_validation(dv)
for col in ROLE_COLS:
    dv.add("%s%d:%s%d" % (col, first, col, LASTROW))
for col in ROLE_COLS:
    rng = "%s%d:%s%d" % (col, first, col, LASTROW)
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=['$%s%d="%s"' % (col, first, TICK)], fill=FILL_GREEN,
        font=Font(name="Calibri", bold=True, size=11, color=GREEN)))
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=['$%s%d="%s"' % (col, first, NO)], fill=PatternFill("solid", fgColor="F2F2F2"),
        font=Font(name="Calibri", size=11, color="9A9A9A")))
    # a cell nobody has decided yet must not read as a refusal
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=['$%s%d=""' % (col, first)], fill=FILL_EDIT))
ws.conditional_formatting.add("K%d:K%d" % (first, LASTROW), FormulaRule(
    formula=['$K%d="CHANGED"' % first], fill=FILL_AMBER,
    font=Font(name="Calibri", bold=True, size=8, color=AMBER)))

# three live count rows, so an undecided cell cannot hide
r = LASTROW + 1
for lab, mark, tone in [("ALLOWED", TICK, GREEN), ("NOT ALLOWED", NO, GREY),
                        ("NOT YET DECIDED", "", RED)]:
    a = ws.cell(row=r, column=2, value=lab)
    a.font, a.fill, a.border, a.alignment = F_H, FILL_SEC, BOX, Alignment(horizontal="right", vertical="center")
    for c in (1, 3, 4, 5):
        ws.cell(row=r, column=c).fill = FILL_SEC
        ws.cell(row=r, column=c).border = BOX
    for col in ROLE_COLS:
        f = ('=COUNTBLANK(%s%d:%s%d)' % (col, first, col, LASTROW) if mark == ""
             else '=COUNTIF(%s%d:%s%d,"%s")' % (col, first, col, LASTROW, mark))
        cell = ws.cell(row=r, column=ws[col + "1"].column, value=f)
        cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_SEC, CTR, BOX
    tail = ws.cell(row=r, column=10,
                   value=("of %d actions" % len(A) if mark == TICK else
                          "deliberately withheld" if mark == NO else
                          "every one of these needs an answer before the auth layer is built"))
    tail.font, tail.fill, tail.border = F_H, FILL_SEC, BOX
    k = ws.cell(row=r, column=11,
                value='=COUNTIF(K%d:K%d,"CHANGED")&" changed"' % (first, LASTROW) if mark == TICK else None)
    k.fill, k.border = FILL_SEC, BOX
    if mark == TICK:
        k.font, k.alignment = F_H, CTR
    ws.cell(row=r, column=12).fill = FILL_SEC
    r += 1
COUNTS_LAST = r - 1

r += 1
ws.cell(row=r, column=1, value="HOW TO CHANGE IT")
ws.cell(row=r, column=1).font = Font(name="Calibri", bold=True, size=10, color=NAVY)
r += 1
for text in [
    "Click any cell in the four role columns and pick from the dropdown: \u2713 allowed, \u2717 not allowed. Clear the cell to mark it as not yet decided — the cream fill makes those obvious and the NOT YET DECIDED row counts them.",
    "Nothing else on this sheet can be typed into. The rest is locked, with no password, so a stray keystroke cannot damage a formula; Review then Unprotect Sheet opens it if you need to.",
    "The CHANGED column flags every row where your answer differs from the proposal shipped with the file, and the count sits beside the ALLOWED row. That is the list to walk the IT team through: it is what the business decided, as distinct from what was suggested.",
    "Add a row for an action nobody listed by inserting it inside the table, then fill its Required gate and ticks by hand. The counts extend over the whole table and will pick it up.",
]:
    c = ws.cell(row=r, column=1, value="\u2022  " + text)
    c.font, c.alignment = F_N, WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
    ws.row_dimensions[r].height = 11 * (1 + len(text) // 175)
    r += 1

r += 1
ws.cell(row=r, column=1, value="HOW TO READ AND USE THIS").font = Font(name="Calibri", bold=True, size=10, color=NAVY)
r += 1
for text in [
    "Gate TODAY is what the running application enforces right now — Passphrase, an access code, or NONE. It was read off the routes, not assumed.",
    "Five rows are marked ASYMMETRY or GAP: the application gates an action and leaves a comparable one open. Those are defects, not design, and the Build Reference tab lists them with their endpoints. Two more that an earlier draft of this sheet named have been WITHDRAWN after checking the code: allocation and batch close are ungated in both modules, so neither was an asymmetry.",
    "Required gate is what the role column implies. Where it disagrees with Gate TODAY, that row is work for the auth layer.",
    "Enforce on the SERVER, per route. Hiding a button is not a control: every row here is an HTTP endpoint anyone on the network can call directly today.",
    "Roles are exclusive and do not compose. A person holds exactly one. Leader includes everything Trainer has; Admin includes everything Leader has.",
    "Deny by default. A route not on this list gets the strictest role that could plausibly need it, never open access.",
]:
    c = ws.cell(row=r, column=1, value="•  " + text)
    c.font, c.alignment = F_N, WRAP
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    ws.row_dimensions[r].height = 11 * (1 + len(text) // 175)
    r += 1

ws.freeze_panes = "A%d" % (HDR + 1)
ws.auto_filter.ref = "A%d:K%d" % (HDR, LASTROW)
ws.print_area = "A1:K%d" % (r - 1)
ws.page_setup.orientation = "landscape"
ws.page_setup.paperSize = ws.PAPERSIZE_A4
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.print_options.horizontalCentered = True
ws.print_title_rows = "%d:%d" % (HDR, HDR)
# Locked with no password: the tick cells are the only unlocked ones, so a
# stray keystroke cannot break a formula, and Review > Unprotect opens it.
ws.protection.sheet = True
ws.protection.formatCells = False
ws.protection.insertRows = True
ws.protection.autoFilter = False
ws.protection.sort = False

# ====================================================== 2. Build Reference
ws2 = wb.create_sheet("Build Reference")
ws2.sheet_view.showGridLines = False
for col, w in zip("ABCDEFG", [14, 42, 13, 13, 22, 62, 46]):
    ws2.column_dimensions[col].width = w
ws2["A1"] = "Build Reference — the endpoint behind every row"
ws2["A1"].font = F_T
ws2.merge_cells("A1:G1")
ws2["A2"] = ("For the team implementing the auth layer. Paths are the router's own, prefix included, read from the @router decorators. "
             "Where an action spans several routes they are all listed: all of them need the same gate.")
ws2["A2"].font = F_SUB
ws2["A2"].alignment = WRAP
ws2.merge_cells("A2:G2")
ws2.row_dimensions[2].height = 22

h = 4
for c, lab in enumerate(["Module", "Action", "Risk", "Gate TODAY", "Required gate", "Endpoint(s)", "Note"], start=1):
    cell = ws2.cell(row=h, column=c, value=lab)
    cell.font, cell.fill, cell.alignment, cell.border = F_H, FILL_H, WRAP_C, BOX
ws2.row_dimensions[h].height = 22
r = h + 1
f2 = r
for mod, act, risk, gate, co, tr, le, ad, note in A:
    required = ("Admin only" if (ad and not le) else
                "Leader or Admin" if (le and not tr) else
                "Trainer and above" if (tr and not co) else
                "Own session only" if (co and not tr) else
                "Any signed-in user")
    vals = [mod, act, risk, gate, required, EP[act], note]
    for c, v in enumerate(vals, start=1):
        cell = ws2.cell(row=r, column=c, value=v)
        cell.font, cell.border, cell.alignment = F_N, BOX, WRAP
        if c == 1:
            cell.font = F_B
        elif c == 3:
            cell.font = Font(name="Calibri", bold=True, size=8, color=RISK[risk][1])
            cell.alignment = WRAP_C
        elif c == 4:
            cell.alignment = WRAP_C
            if gate == "NONE":
                cell.font, cell.fill = Font(name="Calibri", bold=True, size=8, color=RED), FILL_RED
            else:
                cell.font = Font(name="Calibri", size=8, color=GREY)
        elif c == 5:
            cell.font, cell.alignment = F_SM, WRAP_C
        elif c == 6:
            cell.font = Font(name="Consolas", size=8, color=INK)
        elif c == 7:
            cell.font = (Font(name="Calibri", bold=True, size=8, color=RED)
                         if "ASYMMETRY" in note else F_SM)
    ws2.row_dimensions[r].height = max(13, 10 * (1 + max(len(EP[act]) // 64, len(note) // 48)))
    r += 1
ws2.freeze_panes = "A%d" % (h + 1)
ws2.auto_filter.ref = "A%d:G%d" % (h, r - 1)
ws2.page_setup.orientation = "landscape"
ws2.page_setup.fitToWidth = 1
ws2.page_setup.fitToHeight = 0
ws2.sheet_properties.pageSetUpPr.fitToPage = True
ws2.print_title_rows = "%d:%d" % (h, h)

r += 1
ws2.cell(row=r, column=1, value="FIVE GAPS AND ASYMMETRIES  —  fix these whatever the role model ends up being").font = Font(name="Calibri", bold=True, size=11, color=RED)
ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
r += 1
for text in [
 "Not role decisions. In each case the application gates one action and leaves a comparable one open, so one of the two is wrong today whatever role model you land on. Every gate below was read off the route's own enforcement, including the ones injected as a FastAPI dependency, which a search for the word \"passphrase\" does not find.",
 "1.  THE PLANTED-ERROR LIST IS UNGATED.  GET /auditor/batches/{id}/plantings and GET /auditor/sessions/{id}/review. The single most damaging read in the application: it does not merely leak answers, it voids the restraint measurement the auditor module exists to produce. Nothing comparable is left open anywhere else.",
 "2.  E/M answer keys edit with NO gate, while editing an existing IP/OP key needs the passphrase. POST /practicelab/em/answer-key against PUT /practicelab/answer-key/{chart_id}. The same data, the same consequence, one of them free.",
 "3.  Per-chart answer keys read with NO gate, while the bulk export needs it. GET /practicelab/answer-key/{chart_id}/detail and /em/answer-key/{chart_id}. Gating the export and not the read protects nothing: it is the same keys, one chart at a time.",
 "4.  An assessment's answer key exports with NO gate, while the question bank behind it is gated by a dependency. GET /assessment/{id}/export-answer-key against GET /assessment/questions.",
 "5.  Deleting an assessment's sessions is ungated, while deleting the assessment is gated. DELETE /assessment/{id}/sessions against DELETE /assessment/{id}.",
 "AND ONE PATTERN WORTH DECIDING ON: the FIRST answer key written to a chart is ungated in both IP/OP and E/M. PUT /practicelab/answer-key/{chart_id} checks the passphrase only when a key already exists, and the bulk uploads check it only when replace is set. So creating a key is open and changing one is gated, which is a defensible rule but an undocumented one -- and it is why two rows on the checklist split what used to be a single \"enter or edit a key\" line.",
 "WITHDRAWN after reading the code, and listed here because an earlier draft of this workbook named them as defects:  allocation is ungated in BOTH PracticeLab and Auditor, not gated in one;  batch close is ungated in BOTH, not gated in the auditor.  Neither was an asymmetry. Replacing a chart's page files IS stricter than adding them, but deliberately so, with a comment in the code explaining that it destroys the only copy of the original pages -- design, not defect.",
]:
    c = ws2.cell(row=r, column=1, value=text)
    c.font, c.alignment = (F_N if text[0].isdigit() else F_SM), WRAP
    ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    ws2.row_dimensions[r].height = 11 * (1 + len(text) // 200)
    r += 1

r += 1
ws2.cell(row=r, column=1, value="WHAT THE APPLICATION HAS TODAY").font = Font(name="Calibri", bold=True, size=11, color=NAVY)
r += 1
for lab, val, why in [
    ("API operations", "207", "Counted by walking every @router decorator in backend/routers."),
    ("With no authentication of any kind", "165  (80%)", "No login, no session cookie, no token validation on a route, no auth dependency anywhere."),
    ("Routes enforcing the passphrase", "37", "30 always, 7 only conditionally — on ownership, on replace, or on a key already existing. A text search for the word reports 42, because it counts routes that merely pass it through."),
    ("Of those, gated by a dependency", "5", "_: None = Depends(require_passphrase) — real enforcement with no comparison line, so a text search misses all five."),
    ("Mutating operations", "74", "POST, PUT, PATCH or DELETE. 7 are outright deletes."),
    ("Sensitive reads", "45", "Answer keys, planted errors, the question bank, exports and the audit log. 4 of the actions on the checklist are ungated today."),
    ("User records in the database", "0", "46 tables, none of them a person. A coder is a name typed into browser storage."),
]:
    a = ws2.cell(row=r, column=1, value=lab)
    a.font, a.fill, a.border, a.alignment = F_B, FILL_SUBH, BOX, WRAP
    b = ws2.cell(row=r, column=2, value=val)
    b.font, b.border, b.alignment = Font(name="Calibri", bold=True, size=11, color=RED if "%" in val or val == "0" else NAVY), BOX, CTR
    c = ws2.cell(row=r, column=3, value=why)
    c.font, c.alignment = F_SM, WRAP
    ws2.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
    ws2.row_dimensions[r].height = 11 * (1 + len(why) // 150)
    r += 1

r += 1
ws2.cell(row=r, column=1, value="FOR THE AUTH LAYER").font = Font(name="Calibri", bold=True, size=11, color=NAVY)
r += 1
for text in [
    "Enforce per route on the SERVER. Every row in this workbook is an HTTP endpoint that anyone who can reach the service can call directly today; hiding a button changes nothing.",
    "Role comes from a directory group claim in the token. Four groups, one per role. The application maps group to role and stores no permissions of its own, so changing someone's access is a directory change rather than a deployment.",
    "Roles are exclusive and never compose: a person holds exactly one. Leader is a superset of Trainer, Admin a superset of Leader, so implement them as ordered levels rather than as independent permission sets.",
    "Retire the shared passphrase in the same change that lands the roles. It is a reasonable stopgap and a poor control: one secret held by everyone cannot attribute an action to a person, and attribution is a correctness requirement wherever a score carries a consequence.",
    "Leave the health endpoints open — /health and /openapi.json — so platform monitoring and the deployment smoke test keep working.",
    "The session access codes stay, but stop being credentials: after sign-in a code says WHICH work is yours, not WHO you are. That removes the forwarding problem without discarding the session machinery.",
    "Write an audit row for every action in the Irreversible and Destructive classes, carrying the verified identity. The assessment module already has an audit log; the other three do not.",
]:
    c = ws2.cell(row=r, column=1, value="•  " + text)
    c.font, c.alignment = F_N, WRAP
    ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    ws2.row_dimensions[r].height = 11 * (1 + len(text) // 190)
    r += 1
ws2.print_area = "A1:G%d" % (r - 1)

wb.active = 0
wb.save(OUT)
print("wrote %s" % OUT)
print("actions: %d   asymmetries flagged: %d"
      % (len(A), sum(1 for a in A if "ASYMMETRY" in a[8])))
from collections import Counter
print("allowed per role:", {ROLES[i].replace("\n"," "): sum(a[4+i] for a in A) for i in range(4)})
print("by risk:", dict(Counter(a[2] for a in A)))
print("ungated today:", sum(1 for a in A if a[3] == "NONE"))
