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
    {
        "id": "CR-003",
        "title": "Code descriptions on review, DRG, key-check, auditor-review and analytics screens",
        "kind": "C", "module": "PracticeLab + Auditor trainer screens, analytics",
        "score_impact": "No", "schema": "None",
        "commits": "08e8b3a", "date": "2026-11-19",
        "order": "After CR-001; backend first, then frontend patch",
        "spec": "change_requests/CR-003/CR-003.md",
        "summary": ("Descriptions where codes are READ and judged, not only where typed: the review "
                    "and its export, DRG Review, CC/MCC key check, the trainer's auditor review, "
                    "and hover tooltips on most-missed codes. Wrap or truncate inside their column; "
                    "no overflow."),
    },
]

CRS.append({
    "id": "CR-004",
    "title": "Chart viewer reads charts as documents and sections, like an EHR",
    "kind": "A", "module": "Chart Library viewer (the chart screen coders and auditors work from)",
    "score_impact": "No", "schema": "None",
    "commits": "3846e06", "date": "2026-11-19",
    "order": "Any time: frontend patch only",
    "spec": "change_requests/CR-004/CR-004.md",
    "summary": ("Section detection went from 3 of 17 to 15 of 15 on a sample H&P. Navigator of "
                "documents and sections that follows the reader, jump to the exact heading, side-by-side "
                "scan view, optional coding-aid highlighting, keyboard section stepping, reopens where "
                "the reader left off."),
})

CRS.append({
    "id": "CR-005",
    "title": "CMS POA exempt list applied everywhere POA is keyed, coded, audited or graded",
    "kind": "C+D", "module": "Code sets · PracticeLab · Auditor",
    "score_impact": "Yes", "schema": "code_descriptions.poa_exempt BOOLEAN",
    "commits": "6e32710, 2847e8b", "date": "2026-11-19",
    "order": "DDL, backend rules, run loader, then frontend patch",
    "spec": "change_requests/CR-005/CR-005.md",
    "summary": ("Loads the CMS FY POA exempt list (38,399 codes FY2027). Exempt codes get POA E "
                "automatically and greyed on coder, key editor and auditor screens; keys store E on "
                "upload/edit and existing keys are corrected once; POA on exempt codes is not graded; "
                "the auditor generator never plants POA errors on them."),
})

CRS.append({
    "id": "CR-006", "title": "Report button on each Auditor batch row",
    "kind": "A", "module": "Auditor — Audit Batches list", "score_impact": "No", "schema": "None",
    "commits": "9c443bc", "date": "2026-11-19", "order": "Any time: frontend patch only",
    "spec": "change_requests/CR-006/CR-006.md",
    "summary": "The audit batch list gets PracticeLab's per-row Report (PDF) button, disabled with a reason when nothing is scored.",
})
CRS.append({
    "id": "CR-007", "title": "A same-family code is a wrong code, not a miss",
    "kind": "C", "module": "PracticeLab grading feedback, review screen/export, analytics", "score_impact": "No",
    "schema": "None", "commits": "78256e8", "date": "2026-11-19", "order": "Backend first, then frontend patch",
    "spec": "change_requests/CR-007/CR-007.md",
    "summary": ("Z77.9 entered for Z77.8 is reported as Wrong code with both codes, not 'Missed Z77.8'. Pairs "
                "unmatched codes in the same ICD-10-CM category, PCS root operation or CPT first four. Display only."),
})

CRS.append({
    "id": "CR-008", "title": "Runbook and container guide updated for the POA exempt list (documentation)",
    "kind": "Docs", "module": "IT handover documents", "score_impact": "No", "schema": "None",
    "commits": "30daf10", "date": "2026-11-19", "order": "Read with CR-005",
    "spec": "change_requests/CR-008/CR-008.md",
    "summary": ("No application change. DATABASE_MIGRATION_RUNBOOK.md §8 and the container guide (markdown and "
                "Word) now cover the POA exempt list: the column it needs first, the one-time key correction, "
                "the offline file, the status fields, and the October re-run."),
})

CRS.append({
    "id": "CR-009", "title": "Coding aids: seven quiet cue categories behind one menu",
    "kind": "A", "module": "Chart viewer — Text / Side-by-side", "score_impact": "No", "schema": "None",
    "commits": "cd9a0c9", "date": "2026-11-19", "order": "Any time after CR-004: frontend patch only",
    "spec": "change_requests/CR-009/CR-009.md",
    "summary": ("Coding aids grow from two highlight colours to seven categories (uncertain, negated/history, "
                "linkage, query, specificity, site, POA timing) as thin underlines, behind one menu with counts, "
                "per-category switches and next/previous; setting-aware tooltips; final-diagnosis emphasis."),
})

CRS.append({
    "id": "CR-010-Nov", "title": "E/M review shows the diagnoses behind its Dx score",
    "kind": "B", "module": "PracticeLab E/M & ED Profee review; E/M re-grade", "score_impact": "No",
    "schema": "None", "commits": "cb8667b", "date": "2026-11-19", "order": "After CR-001 and CR-002",
    "spec": "change_requests/CR-010-Nov/CR-010-Nov.md",
    "summary": ("E/M results stored without code lists (submitted before Aug 2026, or re-graded) showed a Dx "
                "score over an empty section. The review falls back to the E/M key and the coder's form; "
                "re-grade now stores the lists. Found live on EM007."),
})

CRS.append({
    "id": "CR-011-Nov", "title": "One review standard for every specialty",
    "kind": "C", "module": "Practice review (trainer, coder, export); batch Results; Auditor review", "score_impact": "No",
    "schema": "None", "commits": "d88e158", "date": "2026-11-19", "order": "After CR-010-Nov; backend first, then frontend patch",
    "spec": "change_requests/CR-011-Nov/CR-011-Nov.md",
    "summary": ("Scoring notes removed (they repeated the review rows); the four facts only they held -- PDx POA, "
                "CPT pointers, ED level, CC/MCC weight -- moved onto rows. Correct rows fold behind a click; one "
                "header and one colour set on every review screen."),
})

# What a team running THIS SAME Python backend does instead of rebuilding.
# Every CR folder carries code.patch (the complete committed change); applied
# in order to the pre-CR-001 code, all of them reproduce the original app exactly.
SAME_BACKEND = {
    "CR-001": "git am code.patch; run the four checks; deploy.",
    "CR-002": "git am code.patch; deploy. Scores change for new and re-graded E/M sessions.",
    "CR-003": "git am code.patch; deploy. Needs the code sets loaded.",
    "CR-004": "git am code.patch (frontend only); deploy.",
    "CR-005": "git am code.patch; deploy (column added automatically on startup — no manual DDL); check logs for 'Migration DDL failed'; then Code Set Maintenance → Run CMS Ingest; confirm the POA tile.",
    "CR-006": "git am code.patch (frontend only); deploy.",
    "CR-007": "git am code.patch; deploy.",
    "CR-008": "Nothing to apply — read the updated documents.",
    "CR-009": "git am code.patch (frontend only); deploy.",
    "CR-010-Nov": "git am code.patch; deploy. Past E/M results show their diagnoses without a re-grade.",
    "CR-011-Nov": "git am code.patch; deploy. Display only.",
}

# Proposed and agreed in principle, NOT built. Listed so nothing raised is
# lost; an item moves to CRS when it is built.
BACKLOG = [
    ("B-001", "2026-11-19", "Auditor results review after submission",
     "After submitting, an auditor sees only percentages and counts ('2 missed'), never WHICH "
     "errors they missed, so cannot learn from it. Coders got a full review in CR-001; the "
     "auditor side has no equivalent. Would show each planted error found / missed / corrected "
     "wrongly, with code descriptions, when the trainer has released results.",
     "Logged at the user's request; design to be proposed before building."),
    ("B-002", "2026-11-19", "Text for scanned / image-only charts (OCR)",
     "Chart text comes only from a PDF's embedded text layer, so a scan or an uploaded image has no "
     "text view or sections. OCR would add a server dependency (Tesseract), upload time and memory, "
     "and .NET work for IT.",
     "Deferred: the user reports scanned charts are rare."),
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
    # ── CR-003 ──
    ("CR-003", "Backend", "backend/services/practice_review.py", "describe_review()", "Added",
     "Adds key_desc / coded_desc to every code row (PDx, SDx, Dx, PCS, CPT) of every chart, one lookup per code system per session.",
     "Review rows carried codes only.", "Each code row carries what the code means; silent when unknown or CPT.",
     "Implement in .NET", "No", "CR-003 §3.1"),
    ("CR-003", "Backend", "backend/routers/practicelab_pkg/practice_sessions.py", "_build_coder_results()", "Modified",
     "Calls describe_review() after building reviews.", "—", "Review, submit and by-token responses carry descriptions.",
     "Implement in .NET", "No", "CR-003 §3.1"),
    ("CR-003", "Backend", "backend/services/practice_review.py", "review_workbook()", "Modified",
     "Review sheet gains Key description and Coded description columns; Result moves to column 10.",
     "9 columns, no descriptions.", "11 columns.", "Implement in .NET", "No", "CR-003 §3.2"),
    ("CR-003", "Frontend", "frontend/src/components/SubmissionReview.tsx", "CodeCell / describeFromReview", "Added",
     "Description under each code, clamped to 2 lines, full text on hover; fixed table layout so columns never widen.",
     "Codes only.", "Code + meaning.", "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/pages/practicelab/BatchDetailView.tsx", "ReviewModal — Scoring notes", "Modified",
     "Passes descriptions from the review to the scoring notes.", "Trainer notes had no descriptions.", "Same descriptions as the coder sees.",
     "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/pages/practicelab/DRGReviewView.tsx", "DRG findings", "Modified",
     "Findings laid out as a fixed grid with code + description for answer key and coder.",
     "One inline row: 'AK: J18.9  Coder: J15.9'.", "A pay-impacting call made with what each code means.",
     "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/pages/practicelab/AnswerKeysView.tsx", "Check Codes — CC/MCC panel", "Modified",
     "One fixed-column row per issue with the description; list scrolls inside the panel.",
     "Wrapping chips with codes only.", "Trainer sees what the flagged code is before fixing the key.",
     "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/pages/auditor/AuditReview.tsx", "Planted errors and over-calls", "Modified",
     "A line per code (claim and correct value) with its description, only where the field is the code.",
     "Codes only.", "Trainer judges the auditor with what each code means.",
     "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/components/DescribedCodes.tsx", "DescribedCodes", "Added",
     "Render-prop lookup used for hover tooltips on most-missed codes (Results, Insights, by-coder analytics).",
     "Bare codes.", "Description on hover.", "Apply patch", "No", "CR-003 frontend.patch"),
    ("CR-003", "Frontend", "frontend/src/pages/practicelab/{ResultsView,InsightsPanel,PLAnalyticsView}.tsx · styles.ts · auditor/styles.ts", "Most-missed chips; styles", "Modified",
     "Tooltips on most-missed chips; shared styles for the new layouts.", "—", "—", "Apply patch", "No", "CR-003 frontend.patch"),
    # ── CR-004 ──
    ("CR-004", "Frontend", "frontend/src/components/chartDocument.ts", "parseChart()", "Added",
     "Parses extracted page text into documents and sections: ~45-section and 13-document vocabulary, heading-shape rules, inline 'HEADER: text', lists, signatures, wrapped-line joining.",
     "3 of 17 sections on a sample H&P; one bookmark per page; one per label per chart.",
     "15 of 15; 24 sections in 3 documents on a 4-page chart; no false headings on 17 trick lines.",
     "Apply patch", "No", "CR-004 §1-3"),
    ("CR-004", "Frontend", "frontend/src/components/chartDocument.ts", "AID_PATTERNS", "Added",
     "Uncertain-diagnosis and linkage wording patterns for the coding-aid highlight.", "—",
     "Generic wording only, never from an answer key.", "Apply patch", "No", "CR-004 §3"),
    ("CR-004", "Frontend", "frontend/src/components/ChartViewer.tsx", "Text view", "Modified",
     "Navigator of documents and sections with scroll tracking; jump to the exact heading; note styling; Side by side mode; Coding aids toggle; Alt+Up/Down and '/'; remembers mode and section per chart.",
     "Flat chip row of up to one section per page; Image and Text only.",
     "EHR-style reading view.", "Apply patch", "No", "CR-004 §2"),
    # ── CR-005 ──
    ("CR-005", "Database", "code_descriptions", "poa_exempt BOOLEAN (nullable)", "Added",
     "Per-code CMS POA exempt flag; NULL = list not loaded. Added by _add_col on boot.",
     "—", "Column present; verified added to a pre-existing table.", "Run DDL", "No", "CR-005 §4"),
    ("CR-005", "Script", "scripts/ingest_code_sets.py", "poa_urls() / parse_poa_exempt() / stamping", "Added",
     "Loads {FY}-poa-exempt-codes.zip, finds the code column by header, stamps each CM row, then corrects existing IP keys.",
     "No exempt list.", "38,399 FY2027 codes stamped; all matched the CM set.", "Run against your DB", "Yes", "CR-005 §2"),
    ("CR-005", "Script", "scripts/ingest_code_sets.py", "_local() / _from_zip() exclude", "Modified",
     "The CM codes-file lookup excludes names containing 'poa'.",
     "POAexemptCodesFY27.txt in the same folder would have been loaded AS the ICD-10-CM set.",
     "Real CM file read with the POA file beside it.", "Implement in .NET", "No", "CR-005 §2"),
    ("CR-005", "Backend", "backend/services/poa_exempt.py", "exempt_among / list_loaded / normalise_key_poa / correct_existing_keys", "Added",
     "Shared lookup and the key rule: an exempt code's POA is E (IP only); nothing changes when the list is not loaded.",
     "—", "One rule for keys, grading and the generator.", "Implement in .NET", "Yes", "CR-005 §3"),
    ("CR-005", "Backend", "backend/services/grading_engine.py", "IPAnswerKey.poa_exempt / poa_same / _match_sdx_ip / grade_ip / compute_dpo_ip", "Modified",
     "POA on an exempt code is not graded: PDx and SDx match on code; no POA opportunity counted.",
     "A key with Y on an exempt code marked a coder wrong for entering E.",
     "Never a coder error.", "Implement in .NET", "Yes", "CR-005 §3.1"),
    ("CR-005", "Backend", "backend/routers/practicelab_pkg/chart_grading.py · practice_sessions.py", "_grade_chart_for_sp(db=)", "Modified",
     "Builds the key's exempt set from the database; all three callers pass db.", "—", "—",
     "Implement in .NET", "Yes", "CR-005 §3.1"),
    ("CR-005", "Backend", "backend/services/audit_mutation.py · audit_allocation.py", "Corpus.poa_exempt; POA planting and feasibility", "Modified",
     "Never plants a POA error on an exempt code; a chart with only exempt POA lines is not eligible for one.",
     "On an exempt code keyed Y it planted 'N, should be Y'.", "No POA error on an exempt code over 200 seeds.",
     "Implement in .NET", "Yes", "CR-005 §3.2"),
    ("CR-005", "Backend", "backend/routers/practicelab_pkg/config.py", "answer-key upload and editor save", "Modified",
     "Applies normalise_key_poa before storing.", "Trainers picked E by hand.", "Exempt codes stored as E from Excel upload and editor.",
     "Implement in .NET", "Yes", "CR-005 §3.3"),
    ("CR-005", "Backend", "backend/routers/codes.py", "/codes/describe · /codes/status", "Modified",
     "describe returns poa_exempt per code; status returns poa_exempt_loaded.", "—", "—",
     "Implement in .NET", "No", "CR-005 §5"),
    ("CR-005", "Frontend", "frontend/src/components/PoaSelect.tsx", "PoaSelect", "Added",
     "Greyed auto-E POA box for exempt codes; clears an auto-set E when the code changes; re-checks every render.",
     "Plain POA select.", "E set automatically; saved draft verified E on three exempt lines.",
     "Apply patch", "No", "CR-005 §6"),
    ("CR-005", "Frontend", "frontend/src/pages/{PracticeSession,AuditSession}.tsx · practicelab/AnswerKeyEditor.tsx · auditor/AuditKeys.tsx", "POA inputs", "Modified",
     "Coder PDx/SDx, key editor PDx/SDx, auditor add rows and claim lines, authored-error editor use the exempt flag.",
     "Manual E everywhere.", "Auto E, greyed; auditor claim lines follow the revised code.", "Apply patch", "No", "CR-005 §6"),
    ("CR-005", "Frontend", "frontend/src/pages/practicelab/CodeSetMaintenancePanel.tsx", "POA exempt list tile", "Added",
     "Shows the exempt-code count, or red 'not loaded — run the ingest'; the banner calls out a missing list.",
     "A finished ingest gave no confirmation the list loaded.", "Tile reads '38,399 exempt codes' on a FY2027 load.",
     "Apply patch", "No", "CR-005 §5"),
    ("CR-005", "Backend", "backend/routers/codes.py", "/codes/status poa_exempt_codes", "Modified",
     "Adds the exempt-code count (SQL count); needs_attention when CM is loaded without the list.", "—", "—",
     "Implement in .NET", "No", "CR-005 §5"),
    ("CR-005", "Test", "backend/tests/test_poa_exempt.py", "19 tests", "Added",
     "Parse, loader trap, grading, keys incl. Excel upload, generator over 200 seeds, API.", "—", "—",
     "None (reference)", "Yes", "CR-005 §7"),
    # ── CR-006 ──
    ("CR-006", "Frontend", "frontend/src/pages/auditor/AuditBatches.tsx", "Batch list row · Report button", "Modified",
     "Per-row Report button calling GET /auditor/batches/{id}/report.pdf; row becomes role=button div (click/Enter/Space).",
     "No report from the list; had to open the batch.", "Same as PracticeLab's batch list.", "Apply patch", "No", "CR-006"),
    # ── CR-007 ──
    ("CR-007", "Backend", "backend/services/grading_engine.py", "code_family / pair_near_misses / _report_unmatched", "Added",
     "Pairs unmatched key and coder codes of the same family and reports Wrong_Code with both codes; PCS names the differing character.",
     "'Missed Z77.8'; the coder's Z77.9 named nowhere.", "'Wrong code Z77.8 → Z77.9 — same category Z77'.",
     "Implement in .NET", "No", "CR-007 §2"),
    ("CR-007", "Backend", "backend/services/grading_engine.py", "_match_sdx_ip / _match_sdx_op / _match_pcs / _match_cpt", "Modified",
     "Use _report_unmatched instead of reporting every leftover as Missed.", "Missed only.", "Wrong_Code or Missed.",
     "Implement in .NET", "No", "CR-007 §2"),
    ("CR-007", "Backend", "backend/services/practice_review.py", "_set_rows(kind=) · summary.wrong · workbook", "Modified",
     "Review pairs near misses with the grader's function; new 'wrong' status; Wrong code column in the export.",
     "Missed + unrelated Extra rows.", "One Wrong code row.", "Implement in .NET", "No", "CR-007 §3"),
    ("CR-007", "Frontend", "frontend/src/components/SubmissionReview.tsx", "wrong status + summary chip", "Modified",
     "Shows ✗ Wrong code rows and a 'N wrong code' chip.", "—", "—", "Apply patch", "No", "CR-007 §3"),
    ("CR-007", "Script", "scripts/smoke_deployed.py", "REVIEW_STATUSES", "Modified",
     "Accepts the 'wrong' status.", "—", "—", "Run against your API", "No", "CR-007 §4"),
    ("CR-007", "Test", "backend/tests/test_practice_review.py", "near-miss tests", "Added",
     "Z77.8/Z77.9, cross-family, PCS character, CPT, OP SDx, and scores unchanged.", "—", "—",
     "None (reference)", "No", "CR-007 §5"),
    # ── CR-008 ──
    ("CR-008", "Docs", "docs/DATABASE_MIGRATION_RUNBOOK.md", "§8 Reference code sets", "Modified",
     "Adds the POA exempt list: column first, one-time key correction, offline file and name trap, status fields, October re-run, in-app button only where the API implements it.",
     "Load described without the POA list.", "Matches CR-005.", "None (reference)", "No", "CR-008"),
    ("CR-008", "Docs", "docs/CONTAINER_DEPLOYMENT.md · PracticeLab_Container_Deployment.docx", "§9 Reference code sets · Troubleshooting", "Modified",
     "Load repeats each October; POA list named; new troubleshooting row for POA boxes never greyed.",
     "Load called a one-off.", "Rebuilt from _container_docx_build.js.", "None (reference)", "No", "CR-008"),
    # ── CR-009 ──
    ("CR-009", "Frontend", "frontend/src/components/chartDocument.ts", "AID_CATEGORIES / findAids / aidTip / FINAL_DX_SECTIONS", "Added",
     "Seven cue categories, one non-overlapping match pass, setting-aware tooltips, final-diagnosis sections.",
     "Two regexes: uncertain and linkage.", "Seven categories; POA cues on inpatient charts only.", "Apply patch", "No", "CR-009"),
    ("CR-009", "Frontend", "frontend/src/components/ChartViewer.tsx", "Coding aids menu · HighlightedText", "Modified",
     "Toolbar menu with per-category counts, switches and previous/next; thin-underline marks; final-diagnosis emphasis; Esc closes the menu first.",
     "One toggle; filled highlights; legend bar in the document.", "Quiet underlines; menu instead of a bar.", "Apply patch", "No", "CR-009"),
    # ── CR-010-Nov ──
    ("CR-010-Nov", "Backend", "backend/services/practice_review.py", "_em_sections — Diagnoses and CPT", "Modified",
     "Falls back to em_answer_keys and the coder's em_data when the stored lists are empty; 'full credit' only when the score agrees.",
     "Empty section beside 'Dx 23.3 of 35', note claiming full credit.", "Rows shown for old and re-graded results.",
     "Implement in .NET", "No", "CR-010-Nov rules 1-2"),
    ("CR-010-Nov", "Backend", "backend/routers/practicelab_pkg/practice_sessions.py", "regrade_practice_session (E/M)", "Modified",
     "Stores em_dx_ak / em_cpt_ak as submit does.", "Re-grade left the key lists empty.", "Lists stored.",
     "Implement in .NET", "No", "CR-010-Nov rule 3"),
    ("CR-010-Nov", "Test", "backend/tests/test_practice_review.py", "3 tests", "Added",
     "Blanked-list E/M result shows its rows; re-grade stores lists; partial score never says full credit.", "—", "—",
     "None (reference)", "No", "CR-010-Nov"),
    # ── CR-011-Nov ──
    ("CR-011-Nov", "Backend", "backend/services/practice_review.py", "_code_sections · _cpt_note · _set_rows · review_workbook", "Modified",
     "PDx POA mismatch, CPT pointer mismatch and wrong ED level become review rows; key lines carry weight CC/MCC (screen badge, Excel key cell).",
     "Those four facts only in the Scoring notes; PDx with wrong POA read Correct.", "Every fact on the row it concerns.",
     "Implement in .NET", "No", "CR-011-Nov rules 1-4"),
    ("CR-011-Nov", "Frontend", "frontend/src/components/SubmissionReview.tsx · theme.ts", "SubmissionReview · ReviewHeader · REVIEW_STATUS", "Modified",
     "Correct rows fold per section; zero chips hidden; one header and one colour set.", "All rows open; per-screen headers and colours.", "One standard.",
     "Apply patch", "No", "CR-011-Nov"),
    ("CR-011-Nov", "Frontend", "frontend/src/pages/practicelab/BatchDetailView.tsx · pages/PracticeSession.tsx", "Review modal · coder results", "Modified",
     "Scoring notes block removed (kept only as fallback when no review); shared header.", "Rows plus Scoring notes repeating them.", "Rows only.",
     "Apply patch", "No", "CR-011-Nov"),
    ("CR-011-Nov", "Frontend", "frontend/src/pages/practicelab/ResultsView.tsx · pages/auditor/AuditReview.tsx", "Batch results expand · auditor review", "Modified",
     "Batch expand uses the grouped findings renderer; auditor review uses the shared colours and folds found-and-corrected lines.",
     "Own list style and colours.", "Shared renderer and colours.", "Apply patch", "No", "CR-011-Nov"),
    ("CR-011-Nov", "Test", "backend/tests/test_practice_review.py", "4 tests", "Added",
     "One per rule; each fails without it.", "—", "—", "None (reference)", "No", "CR-011-Nov"),
    ("CR-003", "Test", "backend/tests/test_practice_review.py", "Description tests", "Added",
     "Descriptions on review rows and export columns; unknown codes silent; E/M level and MDM never described.", "—", "—",
     "None (reference)", "No", "CR-003 §5"),
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


def _month(iso_date: str) -> str:
    """'2026-11-19' -> 'Nov 2026'. CRs are numbered by month, restarting each
    month (CR-YYYY-MM-NN from the tenth November change on)."""
    d = _dt.date.fromisoformat(iso_date)
    return d.strftime("%b %Y")


def build():
    wb = Workbook()

    # Read Me
    rm = wb.active
    rm.title = "Read Me"
    _title(rm, "PracticeLab — Change Register", "Built %s from docs/_change_register_build.py" % BUILT)
    lines = [
        ("What this is", "Every change made to the original PracticeLab application since the migration, for the IT team to carry into the migrated deployment."),
        ("Start here", "This workbook is the INDEX of every change: what changed, where, and what you must do. The step-by-step detail for each change is in docs/change_requests/CR-NNN/CR-NNN.md, next to its patch files."),
        ("Two routes", "Each CR works for either kind of deployment. (A) Same Python backend as the original app: apply code.patch from the CR folder (git am), in CR order, and deploy — schema columns are added automatically on startup. Applied in order to the pre-CR-001 code, all patches reproduce the original app exactly. (B) Backend rebuilt in another language (e.g. .NET): implement the rules in CR-NNN.md, apply frontend.patch to the unchanged React frontend, and run any DDL listed. The Register's 'If same Python backend' column gives route A's action per CR."),
        ("One-off actions", "CR-005 needs the POA exempt list loaded once (and every October): route A uses Code Set Maintenance → Run CMS Ingest after deploying; route B adds the column first, then runs scripts/ingest_code_sets.py --write against its database."),
        ("Register", "One row per change request (CR). The grey-yellow columns are yours: status, owner, dates, notes."),
        ("Backlog", "Items raised and agreed in principle but not built yet."),
        ("Change Detail", "One row per file-level change. Filter 'IT action' for what you must build, or 'Score impact' for anything that moves scores."),
        ("Full specification", "docs/change_requests/CR-NNN/CR-NNN.md — the business rules, API contract and acceptance tests. This workbook indexes it; the CR file is the authority."),
        ("Order", "Within a CR marked Kind C, implement the backend before applying the frontend patch: the frontend is shared, and a patch calling new backend behaviour breaks your deployment until it exists. CRs apply in number order."),
        ("Numbering", "Changes are numbered by month, restarting each month: CR-NNN-Mon (e.g. CR-010-Nov; December starts at CR-001-Dec). CR-001 to CR-009 are November 2026's first nine. The ID has no year, so the Month column carries it (Nov 2026). From CR-010-Nov on, each change also has its own pull request link."),
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
    heads = ["CR", "Month", "Title", "Kind", "Module", "Score impact", "Schema", "Commits", "Date",
             "Apply order", "Summary", "Spec file", "If same Python backend",
             "Backend (.NET)", "Frontend patch", "Verified by IT", "IT owner", "Done on", "IT notes"]
    rows = [(c["id"], _month(c["date"]), c["title"], c["kind"], c["module"], c["score_impact"], c["schema"],
             c["commits"], c["date"], c["order"], c["summary"], "docs/" + c["spec"],
             SAME_BACKEND.get(c["id"], ""),
             "N/A" if c["kind"] in ("A", "Docs") else "Not started",
             "Not started" if c["kind"] in ("A", "C", "C+D") else "N/A",
             "Not started", "", "", "") for c in CRS]
    _table(rg, 4, heads, rows, [11, 10, 40, 6, 24, 9, 9, 16, 11, 18, 60, 30, 44, 14, 14, 14, 14, 11, 30])
    dv = DataValidation(type="list", formula1='"Not started,In progress,Done,Blocked,N/A"', allow_blank=True)
    rg.add_data_validation(dv)
    last = rg.max_row
    dv.add("N5:P%d" % last)
    for row in rg.iter_rows(min_row=5, max_row=last, min_col=14, max_col=19):
        for c in row:
            c.fill = INPUT
            c.border = BORDER
    for r in range(5, last + 1):
        if rg.cell(row=r, column=6).value == "Yes":
            rg.cell(row=r, column=6).fill = YES
            rg.cell(row=r, column=6).font = Font(bold=True, color="991B1B")

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

    bl = wb.create_sheet("Backlog")
    _title(bl, "Proposed, not built", "Built %s · an item moves to the Register when it is built" % BUILT)
    _table(bl, 4, ["Item", "Raised", "Title", "What and why", "Status"], BACKLOG, [8, 11, 34, 90, 40])

    wb.save(OUT)
    return OUT


# ── REGISTER.md table ─────────────────────────────────────────────────────────

START, END = "<!-- register:start -->", "<!-- register:end -->"


def write_register_md():
    lines = [START,
             "| CR | Month | Title | Kind | Score impact | Schema | Commits | Apply order |",
             "|---|---|---|---|---|---|---|---|"]
    for c in CRS:
        rel = c["spec"].replace("change_requests/", "")
        lines.append("| [%s](%s) | %s | %s | %s | %s | %s | `%s` | %s |" % (
            c["id"].replace("CR-", ""), rel, _month(c["date"]), c["title"], c["kind"], c["score_impact"],
            c["schema"], c["commits"], c["order"]))
    lines.append("")
    lines.append("Built %s by `docs/_change_register_build.py`, which also writes "
                 "`docs/PracticeLab_Change_Register.xlsx` — the detailed version, with one "
                 "row per file-level change and the columns IT uses to track progress." % BUILT)
    if BACKLOG:
        lines.append("")
        lines.append("**Backlog: proposed, not built**")
        lines.append("")
        lines.append("| Item | Title | Status |")
        lines.append("|---|---|---|")
        for b in BACKLOG:
            lines.append("| %s | %s | %s |" % (b[0], b[2], b[4]))
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
