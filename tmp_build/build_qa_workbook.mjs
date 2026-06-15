import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("outputs/practicelab_qa");
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("QA Test Cases");

const headers = ["Test ID", "Scenario", "Steps", "Expected Result", "Pass/Fail", "Notes"];

const rows = [
  ["CH-01", "Search chart by exact number", "Open coder home, search exact chart number, click search", "Correct chart appears in results", "", ""],
  ["CH-02", "Search chart by keyword/category", "Search using keyword/category", "Relevant charts appear, irrelevant ones do not", "", ""],
  ["CH-03", "Open chart viewer", "Open a chart from results/recent", "Viewer opens, pages render correctly", "", ""],
  ["CH-04", "In-chart search", "Use chart search inside viewer", "Matching pages/results are shown correctly", "", ""],
  ["CH-05", "Copy chart number", "Use copy chart number action", "Correct chart number copied", "", ""],
  ["CH-06", "Close viewer", "Open and close viewer", "Viewer closes cleanly, no broken state", "", ""],
  ["UP-01", "Bulk upload valid charts", "Upload multiple valid files with metadata", "Charts created successfully", "", ""],
  ["UP-02", "Upload validation", "Leave required metadata blank", "Submission blocked with clear error", "", ""],
  ["UP-03", "Specialty mismatch handling", "Upload mismatched specialty file", "Warning/error shown correctly", "", ""],
  ["UP-04", "Uploaded chart visibility", "After upload, go to reports/manage charts", "New charts visible with correct metadata", "", ""],
  ["MG-01", "Edit chart metadata", "Open trainer chart, edit category/difficulty/rationale, save", "Changes persist after reload", "", ""],
  ["MG-02", "Add files to existing chart", "Add more files/pages to an existing chart", "New pages/files attached correctly", "", ""],
  ["MG-03", "Retire chart", "Retire an active chart", "Chart marked retired and removed from active browsing", "", ""],
  ["MG-04", "Restore chart", "Restore retired chart", "Chart becomes active again", "", ""],
  ["RP-01", "Reports page loads", "Open trainer reports", "Counts and rows load correctly", "", ""],
  ["RP-02", "Reports filtering", "Filter by specialty/difficulty/status/uploader", "Results update correctly", "", ""],
  ["RP-03", "Report export", "Export Excel from reports", "Download starts and file contains expected rows", "", ""],
  ["AN-01", "Chart library analytics loads", "Open trainer analytics page", "Most viewed, least viewed, specialty breakdown load", "", ""],
  ["AK-01", "Download answer key template", "Open answer keys, download template", "Correct template downloads", "", ""],
  ["AK-02", "Upload valid answer key", "Upload filled valid answer key file", "Keys stored successfully", "", ""],
  ["AK-03", "Upload duplicate answer key", "Re-upload same key", "Duplicate skipped safely", "", ""],
  ["AK-04", "Unknown chart in key", "Upload key with invalid chart number", "Clear error/not found message shown", "", ""],
  ["AK-05", "Key status counts", "Check answer key status before/after upload", "Counts update correctly", "", ""],
  ["BT-01", "Create valid batch", "Create new batch with valid coders/settings", "Batch created and shown in list", "", ""],
  ["BT-02", "Batch validation: no coders", "Try creating with no coders", "Creation blocked with clear error", "", ""],
  ["BT-03", "Batch validation: invalid scoring selection", "Disable all scoring methods if allowed in UI", "Save blocked with clear error", "", ""],
  ["BT-04", "Batch detail open", "Open created batch", "Batch detail loads with correct metadata", "", ""],
  ["AL-01", "Run random allocation", "Run cycle in random mode", "Cycle created, assignments generated", "", ""],
  ["AL-02", "Run manual allocation", "Select manual charts and run cycle", "Selected charts assigned correctly", "", ""],
  ["AL-03", "Allocation warning handling", "Run cycle with exhausted/small pool", "Warning displayed clearly", "", ""],
  ["AL-04", "Multi-cycle behavior", "Run more than one cycle", "Cycle count increments, prior data preserved", "", ""],
  ["EX-01", "Download cycle sheets", "Download one cycle ZIP", "File downloads successfully", "", ""],
  ["EX-02", "Download all-cycle sheets", "Download all cycles ZIP", "File downloads successfully", "", ""],
  ["EX-03", "Validate generated sheets", "Open generated coder files", "Correct charts/coder mapping visible", "", ""],
  ["EX-04", "Empty cycle export behavior", "Download export for 0-assignment cycle", "Behavior is correct and not misleading", "", ""],
  ["GR-01", "Upload valid returned sheets", "Upload returned coder sheet(s)", "Grading completes successfully", "", ""],
  ["GR-02", "Grading result persistence", "Open results after grading", "Scores, pass/fail, feedback stored", "", ""],
  ["GR-03", "Duplicate grading protection", "Re-upload same returned sheet", "Duplicate skipped safely", "", ""],
  ["GR-04", "Malformed grading file", "Upload invalid/wrong-format file", "Clear error shown, app remains stable", "", ""],
  ["GR-05", "Submission counts update", "Check batch detail after grading", "Submitted counts update correctly", "", ""],
  ["DRG-01", "Open DRG review", "Use batch with flagged DRG cases", "Pending DRG cases are listed", "", ""],
  ["DRG-02", "Approve DRG correct", "Mark one result DRG correct", "Final score updates correctly", "", ""],
  ["DRG-03", "Mark DRG error", "Mark one result DRG error", "Final score updates correctly", "", ""],
  ["DRG-04", "Pending DRG count update", "Return to batch/results after decisions", "Pending count decreases correctly", "", ""],
  ["RS-01", "Batch results page", "Open results for graded batch", "Summary and coder rows render correctly", "", ""],
  ["RS-02", "Batch insights panel", "Open insights from results/batch detail", "Insights load correctly", "", ""],
  ["RS-03", "Insights copy summary", "Use copy summary action", "Clipboard contains readable summary", "", ""],
  ["RS-04", "Results export", "Export batch results Excel", "File downloads with correct result rows", "", ""],
  ["PA-01", "Analytics overview", "Open PracticeLab analytics", "KPI cards load correctly", "", ""],
  ["PA-02", "By Specialty tab", "Open specialty analytics", "Data and charts render correctly", "", ""],
  ["PA-03", "By Batch tab", "Open batch analytics", "Data and charts render correctly", "", ""],
  ["PA-04", "By Chart tab", "Open chart analytics", "Attempt counts, avg score, missed codes render correctly", "", ""],
  ["PA-05", "Coder Trend tab", "Search exact coder", "Trend rows/chart load correctly", "", ""],
  ["PA-06", "Category Mastery tab", "Open category mastery", "Team/category heatmap renders correctly", "", ""],
  ["PA-07", "Chart Value tab", "Open chart value", "Teaching labels and filters work correctly", "", ""],
  ["PA-08", "Coder Matrix tab", "Open coder matrix", "Closed-batch matrix loads correctly", "", ""],
  ["PA-09", "Analytics filters", "Apply date/specialty filters if present", "All analytics update consistently", "", ""],
  ["SP-01", "Download self-practice template", "Open self-practice, download template", "Correct template downloads", "", ""],
  ["SP-02", "Submit self-practice", "Submit valid self-practice file", "Submission accepted successfully", "", ""],
  ["SP-03", "Trainer review queue", "Open trainer self-practice queue", "Submission visible in pending review", "", ""],
  ["SP-04", "Release reviewed feedback", "Trainer reviews and releases", "Status changes correctly, feedback saved", "", ""],
  ["SC-01", "Load scoring config", "Open scoring config page", "Existing config loads correctly", "", ""],
  ["SC-02", "Save valid scoring config", "Change valid values and save with passphrase", "Save succeeds and persists", "", ""],
  ["SC-03", "Invalid weights", "Save weights not summing correctly", "Validation blocks save", "", ""],
  ["SC-04", "Invalid passphrase", "Save with wrong passphrase", "Change rejected with clear error", "", ""],
  ["CL-01", "Close batch", "Close an eligible batch", "Status changes to closed", "", ""],
  ["CL-02", "Closed batch restrictions", "Try allocation/grading after close", "Restricted actions blocked", "", ""],
  ["CL-03", "Force close batch", "Force close with passphrase/reason", "Batch closes and reason is stored", "", ""],
  ["ER-01", "Refresh resilience", "Refresh during major workflows", "App recovers safely", "", ""],
  ["ER-02", "Navigation resilience", "Use browser back/forward", "State remains stable or degrades safely", "", ""],
  ["ER-03", "Empty/no-result states", "Search invalid coder/chart or open empty analytics", "Helpful empty state shown", "", ""],
  ["ER-04", "Bad file handling", "Upload malformed Excel files in all flows", "Clear error shown, no crash", "", ""],
];

const releaseRows = [
  ["CH-01", "Search chart by exact number"],
  ["CH-02", "Search chart by keyword/category"],
  ["CH-03", "Open chart viewer"],
  ["UP-01", "Bulk upload valid charts"],
  ["AK-02", "Upload valid answer key"],
  ["BT-01", "Create valid batch"],
  ["AL-01", "Run random allocation"],
  ["EX-01", "Download cycle sheets"],
  ["GR-01", "Upload valid returned sheets"],
  ["DRG-01", "Open DRG review"],
  ["DRG-02", "Approve DRG correct"],
  ["DRG-03", "Mark DRG error"],
  ["RS-01", "Batch results page"],
  ["PA-01", "Analytics overview"],
  ["PA-02", "By Specialty tab"],
  ["PA-03", "By Batch tab"],
  ["PA-04", "By Chart tab"],
  ["PA-05", "Coder Trend tab"],
  ["SP-02", "Submit self-practice"],
  ["SP-03", "Trainer review queue"],
  ["SP-04", "Release reviewed feedback"],
  ["CL-01", "Close batch"],
  ["CL-02", "Closed batch restrictions"],
  ["ER-04", "Bad file handling"],
];

sheet.getRange("A1:F1").merge();
sheet.getRange("A1").values = [["PracticeLab End-to-End QA Tracker"]];
sheet.getRange("A2:F2").merge();
sheet.getRange("A2").values = [["Use this workbook to track end-to-end validation across all major coder, trainer, PracticeLab, analytics, and admin workflows."]];
sheet.getRange(`A4:F${rows.length + 4}`).values = [headers, ...rows];

sheet.getRange(`A4:F4`).format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRange("A1").format = {
  font: { bold: true, color: "#0F172A" },
};
sheet.getRange("A2").format = {
  font: { color: "#475569" },
};

sheet.getRange(`A4:F${rows.length + 4}`).format.borders = { preset: "all", style: "thin", color: "#D1D5DB" };
sheet.getRange(`A5:F${rows.length + 4}`).format.wrapText = true;
sheet.freezePanes.freezeRows(4);
sheet.showGridLines = false;

sheet.getRange(`E5:E${rows.length + 4}`).dataValidation = {
  rule: { type: "list", values: ["", "Pass", "Fail", "Blocked", "N/A"] },
};

sheet.getRange(`E5:E${rows.length + 4}`).conditionalFormats.add("containsText", {
  text: "Pass",
  format: { fill: "#DCFCE7", font: { bold: true, color: "#166534" } },
});
sheet.getRange(`E5:E${rows.length + 4}`).conditionalFormats.add("containsText", {
  text: "Fail",
  format: { fill: "#FEE2E2", font: { bold: true, color: "#991B1B" } },
});
sheet.getRange(`E5:E${rows.length + 4}`).conditionalFormats.add("containsText", {
  text: "Blocked",
  format: { fill: "#FEF3C7", font: { bold: true, color: "#92400E" } },
});

sheet.getRange("H1:K1").merge();
sheet.getRange("H1").values = [["Release Minimum"]];
sheet.getRange("H2:I2").values = [["Test ID", "Scenario"]];
sheet.getRange(`H3:I${releaseRows.length + 2}`).values = releaseRows;
sheet.getRange("H2:I2").format = {
  fill: "#4338CA",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRange(`H2:I${releaseRows.length + 2}`).format.borders = { preset: "all", style: "thin", color: "#D1D5DB" };
sheet.getRange(`H3:I${releaseRows.length + 2}`).format.wrapText = true;

sheet.getRange("H30:K30").merge();
sheet.getRange("H30").values = [["Execution Summary"]];
sheet.getRange("H31:I35").values = [
  ["Total Cases", rows.length],
  ["Passed", ""],
  ["Failed", ""],
  ["Blocked", ""],
  ["Completion %", ""],
];
sheet.getRange("H30").format = { fill: "#1D4ED8", font: { bold: true, color: "#FFFFFF" } };
sheet.getRange("H31:I35").format.borders = { preset: "all", style: "thin", color: "#D1D5DB" };
sheet.getRange("I32").formulas = [[`=COUNTIF(E5:E${rows.length + 4},"Pass")`]];
sheet.getRange("I33").formulas = [[`=COUNTIF(E5:E${rows.length + 4},"Fail")`]];
sheet.getRange("I34").formulas = [[`=COUNTIF(E5:E${rows.length + 4},"Blocked")`]];
sheet.getRange("I35").formulas = [[`=COUNTIF(E5:E${rows.length + 4},"Pass")/COUNTA(E5:E${rows.length + 4})`]];
sheet.getRange("I35").format.numberFormat = "0.0%";

sheet.getRange("A1:F2").format.fill = "#F8FAFC";
sheet.getRange("H1:K1").format.fill = "#EEF2FF";
sheet.getRange("H30:K30").format.fill = "#DBEAFE";

sheet.getRange("A:A").format.columnWidthPx = 90;
sheet.getRange("B:B").format.columnWidthPx = 210;
sheet.getRange("C:C").format.columnWidthPx = 310;
sheet.getRange("D:D").format.columnWidthPx = 300;
sheet.getRange("E:E").format.columnWidthPx = 110;
sheet.getRange("F:F").format.columnWidthPx = 220;
sheet.getRange("H:H").format.columnWidthPx = 90;
sheet.getRange("I:I").format.columnWidthPx = 220;

const inspect = await workbook.inspect({
  kind: "table",
  range: `QA Test Cases!A1:I12`,
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 9,
});
console.log(inspect.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "PracticeLab_QA_Test_Cases.xlsx");
await output.save(outputPath);
console.log(`SAVED:${outputPath}`);
