"""
Excel generation and parsing for PracticeLab assessments.
- generate_answer_key_template: blank IP or OP answer key for trainers to fill
- generate_coder_sheet: one Excel file per coder (assessment submission template)
- parse_answer_key_upload: reads trainer-filled answer key Excel, returns rows
- parse_submission: reads coder-returned Excel, returns submission data
"""
import io
import zipfile
from typing import Optional
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ── Style helpers ─────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
SECTION_FILL = PatternFill("solid", fgColor="2E75B6")
INPUT_FILL = PatternFill("solid", fgColor="FFFDE7")
LOCKED_FILL = PatternFill("solid", fgColor="E8F5E9")
WHITE_FONT = Font(color="FFFFFF", bold=True, size=10)
DARK_FONT = Font(bold=True, size=10)
THIN = Side(style="thin", color="BDBDBD")
THIN_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _header(ws, col, row, value, fill=None, font=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = fill or HEADER_FILL
    cell.font = font or WHITE_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = THIN_BORDER
    return cell


def _input_cell(ws, col, row, value=None):
    # Use value=None (not "") so openpyxl writes a plain styled empty cell.
    # value="" creates t="inlineStr" cells which Excel for Mac rewrites in a
    # format openpyxl cannot read back, causing all filled values to read as None.
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = INPUT_FILL
    cell.border = THIN_BORDER
    cell.alignment = Alignment(horizontal="center", vertical="center")
    return cell


def _locked_cell(ws, col, row, value=""):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = LOCKED_FILL
    cell.border = THIN_BORDER
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.font = Font(bold=True, size=10)
    return cell


# ── IP Answer Key template ────────────────────────────────────────────────────

IP_SDX_COUNT = 20
IP_PCS_COUNT = 8
OP_SDX_COUNT = 20
OP_CPT_COUNT = 10


def _build_ip_ak_headers(ws):
    """Write IP answer key header row. Returns column map."""
    col = 1
    _header(ws, col, 1, "Chart_Number"); col += 1
    _header(ws, col, 1, "PDx_Code"); col += 1
    _header(ws, col, 1, "PDx_POA\n(Y/N/U/W/1)"); col += 1
    for i in range(1, IP_SDX_COUNT + 1):
        _header(ws, col, 1, f"SDx_{i}"); col += 1
        _header(ws, col, 1, f"SDx_{i}_POA"); col += 1
        _header(ws, col, 1, f"SDx_{i}_CCMCC\n(MCC/CC/-)"); col += 1
    for i in range(1, IP_PCS_COUNT + 1):
        _header(ws, col, 1, f"PCS_{i}"); col += 1
    ws.row_dimensions[1].height = 36


def _build_op_ak_headers(ws):
    col = 1
    _header(ws, col, 1, "Chart_Number"); col += 1
    _header(ws, col, 1, "PDx_Code"); col += 1
    for i in range(1, OP_SDX_COUNT + 1):
        _header(ws, col, 1, f"SDx_{i}"); col += 1
    for i in range(1, OP_CPT_COUNT + 1):
        _header(ws, col, 1, f"CPT_{i}"); col += 1
        _header(ws, col, 1, f"CPT_{i}_Modifier"); col += 1
    ws.row_dimensions[1].height = 36


def generate_coder_list_template() -> bytes:
    """Blank coder list template: Coder_Name | Emp_ID columns."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Coder_List"

    _header(ws, 1, 1, "Coder_Name")
    _header(ws, 2, 1, "Emp_ID")
    ws.row_dimensions[1].height = 28

    info = [
        "Enter one coder per row.",
        "Coder_Name: Enter exactly as you want it to appear on reports (e.g. Smith, John A  or  Sarah Johnson).",
        "Emp_ID: Required. Used as the unique identifier for trend analytics across batches.",
        "Duplicate Emp_IDs in this file will be skipped (first row kept).",
    ]
    for r in range(2, 7):
        _input_cell(ws, 1, r)
        _input_cell(ws, 2, r)

    note = wb.create_sheet("Instructions")
    for i, line in enumerate(info, 1):
        c = note.cell(row=i, column=1, value=line)
        c.font = Font(size=11)
    note.column_dimensions["A"].width = 90

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 20

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_coder_list(file_bytes: bytes) -> list[dict]:
    """
    Parse uploaded coder list Excel.
    Returns [{name, emp_id}] — deduped by emp_id (first occurrence wins).
    """
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    seen_ids: set[str] = set()
    coders = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or (not row[0] and not row[1]):
            continue
        name = str(row[0] or "").strip()
        emp_id = str(row[1] or "").strip().upper()
        if not name or not emp_id:
            continue
        if emp_id in seen_ids:
            continue
        seen_ids.add(emp_id)
        coders.append({"name": name, "emp_id": emp_id})

    return coders


def generate_answer_key_template(specialty: str) -> bytes:
    """
    Returns bytes of blank answer key Excel file.
    specialty: 'IP' for inpatient, 'OP' for outpatient.
    """
    wb = Workbook()
    ws = wb.active
    is_ip = specialty.upper() == "IP"
    ws.title = f"{'IP' if is_ip else 'OP'}_Answer_Key"

    if is_ip:
        _build_ip_ak_headers(ws)
        total_cols = 3 + IP_SDX_COUNT * 3 + IP_PCS_COUNT
    else:
        _build_op_ak_headers(ws)
        total_cols = 2 + OP_SDX_COUNT + OP_CPT_COUNT * 2

    # 10 blank input rows
    for r in range(2, 12):
        for c in range(1, total_cols + 1):
            _input_cell(ws, c, r)

    # Column widths
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    for c in range(4, total_cols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 12

    # Instructions sheet
    info = wb.create_sheet("Instructions")
    instructions = [
        ("PracticeLab Answer Key Template", True),
        ("", False),
        ("HOW TO USE:", True),
        ("1. Fill one row per chart. Chart_Number must match exactly what is in PracticeLab.", False),
        ("2. PDx_Code: Principal diagnosis ICD-10-CM code (e.g. J18.9)", False),
    ]
    if is_ip:
        instructions += [
            ("3. PDx_POA: Present on Admission indicator — Y, N, U, W, or 1", False),
            ("4. SDx: Secondary diagnoses. Fill from left, leave unused columns blank.", False),
            ("5. SDx_POA: POA indicator per secondary diagnosis.", False),
            ("6. SDx_CCMCC: Enter MCC, CC, or - (dash for neither).", False),
            ("7. PCS: ICD-10-PCS procedure codes (7 characters). Fill from left.", False),
            ("8. Do NOT enter column headers or extra rows.", False),
            ("", False),
            ("SCORING REFERENCE (IP-DRG):", True),
            ("  PDx (code + POA): 20 pts", False),
            ("  SDx: 20 pts  |  PCS: 20 pts  |  DRG (trainer review): 40 pts", False),
            ("  Pass threshold: 80%", False),
        ]
    else:
        instructions += [
            ("3. SDx: Secondary diagnoses (code only, no POA for OP).", False),
            ("4. CPT: Procedure codes. CPT_Modifier is optional (e.g. 59, LT, RT).", False),
            ("5. Do NOT enter column headers or extra rows.", False),
            ("", False),
            ("SCORING REFERENCE (OP):", True),
            ("  PDx: 25 pts  |  SDx: 25 pts  |  CPT (code + modifier): 50 pts", False),
            ("  Pass threshold: 90%", False),
        ]
    instructions += [
        ("", False),
        ("Upload this completed file via PracticeLab → Answer Keys → Upload.", False),
    ]
    for r, (text, bold) in enumerate(instructions, 1):
        cell = info.cell(row=r, column=1, value=text)
        cell.font = Font(bold=bold, size=11)
    info.column_dimensions["A"].width = 80

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Consolidated answer key export ───────────────────────────────────────────

def export_all_answer_keys(answer_keys: list) -> bytes:
    """
    Export all stored answer keys as a filled Excel workbook.
    answer_keys: list of (AnswerKey, Chart) tuples from DB query.
    Produces one sheet per specialty group, same column layout as the upload template.
    """
    wb = Workbook()
    wb.remove(wb.active)

    # Group by specialty type (IP vs OP)
    ip_rows = [(ak, ch) for ak, ch in answer_keys if ch.specialty.value == "IP-DRG"]
    op_rows = [(ak, ch) for ak, ch in answer_keys if ch.specialty.value != "IP-DRG"]

    def _fill_sheet(ws, rows, is_ip):
        if is_ip:
            _build_ip_ak_headers(ws)
        else:
            _build_op_ak_headers(ws)
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 14
        ws.column_dimensions["C"].width = 14

        for row_num, (ak, ch) in enumerate(sorted(rows, key=lambda x: x[1].chart_number), start=2):
            col = 1
            if is_ip:
                _input_cell(ws, col, row_num, ch.chart_number); col += 1
                _input_cell(ws, col, row_num, ak.pdx_code or ""); col += 1
                _input_cell(ws, col, row_num, ak.pdx_poa or ""); col += 1
                sdx_list = ak.sdx or []
                for i in range(IP_SDX_COUNT):
                    entry = sdx_list[i] if i < len(sdx_list) else {}
                    _input_cell(ws, col, row_num, entry.get("code", "")); col += 1
                    _input_cell(ws, col, row_num, entry.get("poa", "")); col += 1
                    _input_cell(ws, col, row_num, entry.get("ccmcc", "")); col += 1
                pcs_list = ak.pcs or []
                for i in range(IP_PCS_COUNT):
                    entry = pcs_list[i] if i < len(pcs_list) else {}
                    _input_cell(ws, col, row_num, entry.get("code", "")); col += 1
            else:
                _input_cell(ws, col, row_num, ch.chart_number); col += 1
                _input_cell(ws, col, row_num, ak.pdx_code or ""); col += 1
                sdx_list = ak.sdx or []
                for i in range(OP_SDX_COUNT):
                    entry = sdx_list[i] if i < len(sdx_list) else {}
                    _input_cell(ws, col, row_num, entry.get("code", "")); col += 1
                cpt_list = ak.cpt or []
                for i in range(OP_CPT_COUNT):
                    entry = cpt_list[i] if i < len(cpt_list) else {}
                    _input_cell(ws, col, row_num, entry.get("code", "")); col += 1
                    _input_cell(ws, col, row_num, entry.get("modifier", "")); col += 1

    if ip_rows:
        ws_ip = wb.create_sheet("IP-DRG")
        _fill_sheet(ws_ip, ip_rows, is_ip=True)
    if op_rows:
        ws_op = wb.create_sheet("OP")
        _fill_sheet(ws_op, op_rows, is_ip=False)

    if not wb.sheetnames:
        ws = wb.create_sheet("No Data")
        ws.cell(1, 1, "No answer keys found.")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Coder answer sheet ────────────────────────────────────────────────────────

def generate_coder_sheet(
    coder_name: str,
    batch_name: str,
    charts: list[dict],   # [{chart_number, specialty, category, difficulty, chart_url}]
    emp_id: str = "",
) -> bytes:
    """
    One Excel file per coder — one sheet per assigned chart.
    Charts list is already randomized by caller.
    """
    wb = Workbook()
    wb.remove(wb.active)

    # ── INFO sheet ────────────────────────────────────────────────────────────
    info = wb.create_sheet("INFO", 0)

    BANNER_FILL   = PatternFill("solid", fgColor="1F3864")
    ACCENT_FILL   = PatternFill("solid", fgColor="2E75B6")
    ROW_ALT_FILL  = PatternFill("solid", fgColor="EBF3FB")
    ROW_BASE_FILL = PatternFill("solid", fgColor="FFFFFF")
    LABEL_FILL    = PatternFill("solid", fgColor="D6E4F0")
    INSTRUCT_FILL = PatternFill("solid", fgColor="FFF8E1")
    CHART_HDR_FILL= PatternFill("solid", fgColor="1F3864")
    CHART_ALT_FILL= PatternFill("solid", fgColor="F0F7FF")
    MED_BORDER = Border(
        left=Side(style="medium", color="2E75B6"),
        right=Side(style="medium", color="2E75B6"),
        top=Side(style="medium", color="2E75B6"),
        bottom=Side(style="medium", color="2E75B6"),
    )

    def _info_set(ws, row, col, value, fill=None, font=None, align=None, border=None):
        cell = ws.cell(row=row, column=col, value=value)
        if fill:  cell.fill = fill
        if font:  cell.font = font
        if align: cell.alignment = align
        if border: cell.border = border
        return cell

    CENTER = Alignment(horizontal="center", vertical="center")
    LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=True)

    # Row 1: Banner
    info.merge_cells("A1:F1")
    _info_set(info, 1, 1, "PracticeLab — Coding Assessment",
              fill=BANNER_FILL,
              font=Font(bold=True, size=16, color="FFFFFF"),
              align=CENTER)
    info.row_dimensions[1].height = 36

    # Row 2: Sub-banner
    info.merge_cells("A2:F2")
    _info_set(info, 2, 1, "Confidential — For Internal Use Only",
              fill=ACCENT_FILL,
              font=Font(italic=True, size=10, color="FFFFFF"),
              align=CENTER)
    info.row_dimensions[2].height = 18

    # Row 3: blank spacer
    info.row_dimensions[3].height = 8

    # Rows 4-6: Coder details table
    details = [
        ("Coder Name", coder_name or "—"),
        ("Employee ID", emp_id or "—"),
        ("Batch",       batch_name or "—"),
    ]
    for i, (label, value) in enumerate(details):
        r = 4 + i
        info.merge_cells(f"A{r}:B{r}")
        info.merge_cells(f"C{r}:F{r}")
        alt = ROW_ALT_FILL if i % 2 == 0 else ROW_BASE_FILL
        _info_set(info, r, 1, label,
                  fill=LABEL_FILL,
                  font=Font(bold=True, size=11, color="1F3864"),
                  align=LEFT, border=THIN_BORDER)
        _info_set(info, r, 3, value,
                  fill=alt,
                  font=Font(size=11),
                  align=LEFT, border=THIN_BORDER)
        info.row_dimensions[r].height = 22

    # Row 7: spacer
    info.row_dimensions[7].height = 10

    # Rows 8-13: Instructions box
    info.merge_cells("A8:F8")
    _info_set(info, 8, 1, "INSTRUCTIONS",
              fill=ACCENT_FILL,
              font=Font(bold=True, size=11, color="FFFFFF"),
              align=CENTER)
    info.row_dimensions[8].height = 22

    instructions = [
        "Do NOT rename this file or any of the chart tabs — the file name and tab names are used during grading.",
        "Fill your answers in the YELLOW cells only. Do not modify section headers or row numbers.",
        "Each tab below this INFO sheet represents one assigned chart. Complete all charts.",
        "For each chart tab, refer to the chart number shown at the top to locate the chart in PracticeLab.",
        "Save this file and return it to your trainer by the agreed deadline.",
    ]
    for i, text in enumerate(instructions):
        r = 9 + i
        info.merge_cells(f"A{r}:F{r}")
        alt = INSTRUCT_FILL if i % 2 == 0 else PatternFill("solid", fgColor="FFFDE7")
        cell = _info_set(info, r, 1, f"{i+1}.  {text}",
                         fill=alt,
                         font=Font(size=10),
                         align=LEFT, border=THIN_BORDER)
        info.row_dimensions[r].height = 28

    # Row 14: spacer
    info.row_dimensions[14].height = 10

    # Row 15: Charts table header
    info.merge_cells("A15:F15")
    _info_set(info, 15, 1, f"CHARTS ASSIGNED — {len(charts)} CHART(S)",
              fill=CHART_HDR_FILL,
              font=Font(bold=True, size=11, color="FFFFFF"),
              align=CENTER)
    info.row_dimensions[15].height = 22

    # Row 16: column headers
    chart_cols = ["#", "Chart Number", "Specialty", "Category", "Difficulty", "Tab Name"]
    for ci, h in enumerate(chart_cols, 1):
        _info_set(info, 16, ci, h,
                  fill=ACCENT_FILL,
                  font=Font(bold=True, size=10, color="FFFFFF"),
                  align=CENTER, border=THIN_BORDER)
    info.row_dimensions[16].height = 20

    for i, ch in enumerate(charts):
        r = 17 + i
        alt = CHART_ALT_FILL if i % 2 == 0 else ROW_BASE_FILL
        row_vals = [i+1, ch["chart_number"], ch["specialty"], ch["category"], ch["difficulty"], ch["chart_number"]]
        for ci, val in enumerate(row_vals, 1):
            _info_set(info, r, ci, val,
                      fill=alt,
                      font=Font(size=10, bold=(ci == 2)),
                      align=CENTER if ci != 4 else LEFT,
                      border=THIN_BORDER)
        info.row_dimensions[r].height = 18

    # Column widths
    info.column_dimensions["A"].width = 5
    info.column_dimensions["B"].width = 18
    info.column_dimensions["C"].width = 14
    info.column_dimensions["D"].width = 24
    info.column_dimensions["E"].width = 14
    info.column_dimensions["F"].width = 16

    # One sheet per chart
    for ch in charts:
        chart_num = ch["chart_number"]
        specialty = ch["specialty"]
        is_ip = specialty == "IP-DRG"
        ws = wb.create_sheet(chart_num)

        # ── Chart tab header ─────────────────────────────────────────────────
        # Row 1: dark banner
        ws.merge_cells("A1:F1")
        title = ws["A1"]
        title.value = "PracticeLab — Coding Assessment"
        title.font = Font(bold=True, size=13, color="FFFFFF")
        title.fill = PatternFill("solid", fgColor="1F3864")
        title.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26

        # Row 2: chart identity bar
        ws.merge_cells("A2:F2")
        id_cell = ws["A2"]
        id_cell.value = f"Chart #: {chart_num}     |     {specialty}     |     {ch['category']}     |     Difficulty: {ch['difficulty']}"
        id_cell.font = Font(bold=True, size=11, color="1F3864")
        id_cell.fill = PatternFill("solid", fgColor="D6E4F0")
        id_cell.alignment = Alignment(horizontal="center", vertical="center")
        id_cell.border = THIN_BORDER
        ws.row_dimensions[2].height = 22

        # Row 3: coder reminder
        ws.merge_cells("A3:F3")
        remind = ws["A3"]
        remind.value = f"Coder: {coder_name}     |     Fill YELLOW cells only     |     Do not rename this tab"
        remind.font = Font(italic=True, size=9, color="555555")
        remind.fill = PatternFill("solid", fgColor="F5F5F5")
        remind.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[3].height = 16

        row = 5

        # PDx section
        _header(ws, 1, row, "SECTION 1 — Principal Diagnosis (PDx)",
                fill=PatternFill("solid", fgColor="2E75B6"))
        ws.merge_cells(f"A{row}:F{row}")
        row += 1

        if is_ip:
            _header(ws, 1, row, "PDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 2, row, "POA (Y/N/U/W/1)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"C{row}:F{row}")
            row += 1
            _input_cell(ws, 1, row)
            _input_cell(ws, 2, row)
        else:
            _header(ws, 1, row, "PDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"B{row}:F{row}")
            row += 1
            _input_cell(ws, 1, row)

        row += 2

        # SDx section
        _header(ws, 1, row, "SECTION 2 — Secondary Diagnoses (SDx) — up to 20",
                fill=PatternFill("solid", fgColor="2E75B6"))
        ws.merge_cells(f"A{row}:F{row}")
        row += 1

        if is_ip:
            _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 2, row, "SDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 3, row, "POA (Y/N/U/W/1)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"D{row}:F{row}")
            row += 1
            for i in range(1, 21):
                _locked_cell(ws, 1, row, i)
                _input_cell(ws, 2, row)
                _input_cell(ws, 3, row)
                row += 1
        else:
            _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 2, row, "SDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"C{row}:F{row}")
            row += 1
            for i in range(1, 21):
                _locked_cell(ws, 1, row, i)
                _input_cell(ws, 2, row)
                row += 1

        row += 1

        # PCS or CPT section
        if is_ip:
            _header(ws, 1, row, "SECTION 3 — ICD-10-PCS Procedure Codes — up to 8",
                    fill=PatternFill("solid", fgColor="2E75B6"))
            ws.merge_cells(f"A{row}:F{row}")
            row += 1
            _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 2, row, "PCS Code (7 characters)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"C{row}:F{row}")
            row += 1
            for i in range(1, 9):
                _locked_cell(ws, 1, row, i)
                _input_cell(ws, 2, row)
                row += 1
        else:
            _header(ws, 1, row, "SECTION 3 — CPT Procedure Codes — up to 10",
                    fill=PatternFill("solid", fgColor="2E75B6"))
            ws.merge_cells(f"A{row}:F{row}")
            row += 1
            _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 2, row, "CPT Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            _header(ws, 3, row, "Modifier (optional)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
            ws.merge_cells(f"D{row}:F{row}")
            row += 1
            for i in range(1, 11):
                _locked_cell(ws, 1, row, i)
                _input_cell(ws, 2, row)
                _input_cell(ws, 3, row)
                row += 1

        # Column widths
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 18
        for col_letter in ["D", "E", "F"]:
            ws.column_dimensions[col_letter].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_self_practice_template() -> bytes:
    """
    Blank self-practice answer sheet.
    Instructions tab + one sample coding tab named 'CHART_NUMBER'.
    Coder duplicates the coding tab and renames each copy with the actual chart number.
    """
    wb = Workbook()
    wb.remove(wb.active)

    # Instructions tab
    info = wb.create_sheet("Instructions", 0)
    lines = [
        ("PracticeLab — Self Practice Answer Sheet", True),
        ("", False),
        ("HOW TO USE THIS TEMPLATE:", True),
        ("1. Look up the chart numbers you want to practice in PracticeLab (e.g. IP002, ED005).", False),
        ("2. Right-click the 'CHART_NUMBER' tab below → 'Move or Copy' → tick 'Create a copy'.", False),
        ("3. Rename the copy with the exact chart number (e.g. IP002). Repeat for each chart.", False),
        ("4. Delete the original 'CHART_NUMBER' tab when done.", False),
        ("5. Fill your answers in the YELLOW cells only.", False),
        ("6. Save the file and upload it back in PracticeLab → Self Practice → Upload.", False),
        ("", False),
        ("IMPORTANT:", True),
        ("  • The tab name IS the chart number — it must match exactly what is in PracticeLab.", False),
        ("  • Do NOT rename or delete the section headers inside each tab.", False),
        ("  • Tabs named 'Instructions' are ignored on upload.", False),
        ("", False),
        ("Your trainer will review your submission and share feedback with you.", False),
    ]
    for r, (text, bold) in enumerate(lines, 1):
        cell = info.cell(row=r, column=1, value=text)
        cell.font = Font(bold=bold, size=11 if bold else 10)
    info.column_dimensions["A"].width = 80

    # Sample coding tab — IP format (covers most users; OP charts auto-detected on parse)
    ws = wb.create_sheet("CHART_NUMBER", 1)
    ws.merge_cells("A1:F1")
    title = ws["A1"]
    title.value = "Chart: CHART_NUMBER  |  Enter your chart number as the tab name"
    title.font = Font(bold=True, size=12, color="FFFFFF")
    title.fill = PatternFill("solid", fgColor="1F3864")
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    # Reuse the same structure as generate_coder_sheet by calling its sub-functions
    # We build a minimal IP sheet inline
    row = 3
    _header(ws, 1, row, "SECTION 1 — Principal Diagnosis (PDx)",
            fill=PatternFill("solid", fgColor="2E75B6"))
    ws.merge_cells(f"A{row}:F{row}")
    row += 1
    _header(ws, 1, row, "PDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 2, row, "POA (Y/N/U/W/1) — IP only", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    ws.merge_cells(f"C{row}:F{row}")
    row += 1
    _input_cell(ws, 1, row); _input_cell(ws, 2, row)
    row += 2

    _header(ws, 1, row, "SECTION 2 — Secondary Diagnoses (SDx)",
            fill=PatternFill("solid", fgColor="2E75B6"))
    ws.merge_cells(f"A{row}:F{row}")
    row += 1
    _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 2, row, "SDx Code", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 3, row, "POA (IP only)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 4, row, "CC/MCC (IP only)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    row += 1
    for i in range(1, 13):
        ws.cell(row=row, column=1, value=i).font = Font(color="9CA3AF", size=9)
        _input_cell(ws, 2, row); _input_cell(ws, 3, row); _input_cell(ws, 4, row)
        row += 1
    row += 1

    _header(ws, 1, row, "SECTION 3 — Procedures (PCS / CPT)",
            fill=PatternFill("solid", fgColor="2E75B6"))
    ws.merge_cells(f"A{row}:F{row}")
    row += 1
    _header(ws, 1, row, "#", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 2, row, "PCS Code (IP) / CPT Code (OP)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    _header(ws, 3, row, "Modifier (OP only)", fill=PatternFill("solid", fgColor="4472C4"), font=WHITE_FONT)
    row += 1
    for i in range(1, 9):
        ws.cell(row=row, column=1, value=i).font = Font(color="9CA3AF", size=9)
        _input_cell(ws, 2, row); _input_cell(ws, 3, row)
        row += 1

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 16

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_batch_zip(coder_files: list[tuple[str, bytes]]) -> bytes:
    """Zip multiple coder Excel files. coder_files: [(filename, bytes)]"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in coder_files:
            zf.writestr(filename, data)
    return buf.getvalue()


# ── Answer key upload parser ──────────────────────────────────────────────────

def parse_answer_key_upload(file_bytes: bytes, specialty: str) -> list[dict]:
    """
    Parse a trainer-uploaded answer key Excel file.
    Returns list of dicts, one per non-empty row:
      IP: {chart_number, pdx_code, pdx_poa, sdx:[{code,poa,ccmcc}], pcs:[{code}]}
      OP: {chart_number, pdx_code, sdx:[{code}], cpt:[{code,modifier}]}
    """
    # data_only=False is more compatible with files saved by Numbers/Google Sheets —
    # data_only=True can return None for plain values in non-Excel-written xlsx files.
    wb = load_workbook(io.BytesIO(file_bytes), data_only=False)
    # worksheets[0] is always the data sheet; Instructions is created last so it
    # becomes wb.active, but its index is always 1.
    ws = wb.worksheets[0]
    is_ip = specialty.upper() == "IP"
    # Scan ALL rows; skip the header row by name so this works regardless of
    # whether data starts at row 2 or somewhere else (e.g. Numbers adds a blank row).
    HEADER_NAMES = {"chart_number", "chart number", "chart#", "chartnumber"}
    results = []

    def _cell(row, idx) -> str:
        """Safely read a cell value, returning "" for None/empty/'None' sentinel."""
        val = row[idx] if idx < len(row) else None
        if val is None:
            return ""
        s = str(val).strip()
        return "" if s.lower() == "none" else s

    for row in ws.iter_rows(min_row=1, values_only=True):
        if not row or row[0] is None:
            continue
        chart_number = _cell(row, 0)
        if not chart_number or chart_number.lower().replace(" ", "_") in HEADER_NAMES:
            continue

        if is_ip:
            pdx_code = _cell(row, 1)
            pdx_poa = _cell(row, 2).upper()
            sdx = []
            col = 3
            for _ in range(IP_SDX_COUNT):
                code = _cell(row, col)
                poa = _cell(row, col + 1).upper()
                ccmcc = _cell(row, col + 2).upper()
                if code:
                    sdx.append({"code": code, "poa": poa, "ccmcc": ccmcc or "-"})
                col += 3
            pcs = []
            for _ in range(IP_PCS_COUNT):
                code = _cell(row, col)
                if code:
                    pcs.append({"code": code})
                col += 1
            results.append({
                "chart_number": chart_number,
                "pdx_code": pdx_code,
                "pdx_poa": pdx_poa,
                "sdx": sdx,
                "pcs": pcs,
            })
        else:
            pdx_code = str(row[1] or "").strip()
            sdx = []
            col = 2
            for _ in range(OP_SDX_COUNT):
                code = _cell(row, col)
                if code:
                    sdx.append({"code": code})
                col += 1
            cpt = []
            for _ in range(OP_CPT_COUNT):
                code = _cell(row, col)
                modifier = _cell(row, col + 1)
                if code:
                    cpt.append({"code": code, "modifier": modifier})
                col += 2
            results.append({
                "chart_number": chart_number,
                "pdx_code": pdx_code,
                "sdx": sdx,
                "cpt": cpt,
            })

    return results


# ── Coder submission parser ───────────────────────────────────────────────────

def parse_submission(file_bytes: bytes) -> list[dict]:
    """
    Parse a coder-returned Excel answer sheet.
    Returns list of dicts, one per chart sheet:
      IP: {chart_number, specialty, pdx_code, pdx_poa, sdx:[{code,poa}], pcs:[{code}]}
      OP: {chart_number, specialty, pdx_code, sdx:[{code}], cpt:[{code,modifier}]}
    """
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    results = []

    for ws in wb.worksheets:
        if ws.title in ("INFO", "Instructions"):
            continue
        chart_number = ws.title.strip()

        # Detect specialty from title cell
        title_cell = ws["A1"].value or ""
        is_ip = "IP-DRG" in str(title_cell)

        rows = list(ws.iter_rows(values_only=True))

        # Find section start rows by scanning for known labels
        pdx_row = sdx_start = proc_start = None
        for i, row in enumerate(rows):
            first = str(row[0] or "").strip()
            if "SECTION 1" in first:
                pdx_row = i + 3  # header + label rows + 1
            elif "SECTION 2" in first:
                sdx_start = i + 3
            elif "SECTION 3" in first:
                proc_start = i + 3

        def cell_val(r, c):
            try:
                return str(rows[r][c] or "").strip()
            except (IndexError, TypeError):
                return ""

        if pdx_row is None:
            continue

        pdx_code = cell_val(pdx_row - 1, 0)
        pdx_poa = cell_val(pdx_row - 1, 1) if is_ip else ""

        sdx = []
        if sdx_start:
            for r in range(sdx_start - 1, sdx_start - 1 + 20):
                code = cell_val(r, 1)
                if not code:
                    continue
                if is_ip:
                    poa = cell_val(r, 2)
                    sdx.append({"code": code, "poa": poa})
                else:
                    sdx.append({"code": code})

        pcs, cpt = [], []
        if proc_start:
            for r in range(proc_start - 1, proc_start - 1 + (8 if is_ip else 10)):
                code = cell_val(r, 1)
                if not code:
                    continue
                if is_ip:
                    pcs.append({"code": code})
                else:
                    modifier = cell_val(r, 2)
                    cpt.append({"code": code, "modifier": modifier})

        entry = {
            "chart_number": chart_number,
            "specialty": "IP-DRG" if is_ip else "OP",
            "pdx_code": pdx_code,
            "sdx": sdx,
        }
        if is_ip:
            entry["pdx_poa"] = pdx_poa
            entry["pcs"] = pcs
        else:
            entry["cpt"] = cpt

        results.append(entry)

    return results


# ── E/M answer key Excel parser ──────────────────────────────────────────────

def parse_em_answer_key_upload(file_bytes: bytes) -> list[dict]:
    """
    Parse a trainer-filled E/M answer key Excel (from the bulk template).

    Column layout (A=0 … AY=50):
      A  chart_number
      B  copa_self_limited      C  copa_stable_acute       D  copa_stable_chronic
      E  copa_acute_uncomplicated F copa_chronic_exacerbation G copa_undiagnosed_new
      H  copa_acute_systemic    I  copa_acute_complicated_injury
      J  copa_chronic_severe    K  copa_threat_to_life
      L  copa_level_override (blank = auto-derive)
      M  dr_prior_external_notes N dr_review_test_results  O  dr_order_tests
      P  dr_independent_historian (Y/N)
      Q  dr_independent_interpretation (Y/N)
      R  dr_external_discussion (Y/N)
      S  dr_level_override
      T  risk_low               U  risk_prescription_drug_mgmt
      V  risk_minor_surgery_with_factors W risk_elective_major_no_factors
      X  risk_hospitalization   Y  risk_sdoh
      Z  risk_drug_intensive_monitoring AA risk_elective_major_with_factors
      AB risk_emergency_major_surgery   AC risk_hospitalization_escalation
      AD risk_dnr_deescalate           AE risk_parenteral_controlled
      AF risk_level_override
      AG em_code               AH em_modifier
      AI-AP dx_codes (Primary + 7 additional = 8 total)
      AQ-AX procedure_cpts (4 CPTs × code+modifier)
      AY entered_by
    """
    wb = load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws = wb.worksheets[0]

    HEADER_NAMES = {"chart_number", "chart number", "chart#", "chartnumber"}

    def _v(row, idx, default=""):
        val = row[idx] if idx < len(row) else None
        if val is None:
            return default
        s = str(val).strip()
        return default if s.lower() in ("none", "") else s

    def _int(row, idx) -> int:
        try:
            return max(0, int(float(_v(row, idx, "0") or "0")))
        except (ValueError, TypeError):
            return 0

    def _bool(row, idx) -> bool:
        return _v(row, idx).upper() in ("Y", "YES", "TRUE", "1")

    results = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        if not row or row[0] is None:
            continue
        chart_number = _v(row, 0)
        if not chart_number or chart_number.lower().replace(" ", "_") in HEADER_NAMES:
            continue

        # COPA counts
        copa_override = _v(row, 11)  # L

        # Data Review
        dr_override = _v(row, 18)  # S

        # Risk booleans (T–AE = indices 19–30)
        risk_fields = [
            "risk_low", "risk_prescription_drug_mgmt", "risk_minor_surgery_with_factors",
            "risk_elective_major_no_factors", "risk_hospitalization", "risk_sdoh",
            "risk_drug_intensive_monitoring", "risk_elective_major_with_factors",
            "risk_emergency_major_surgery", "risk_hospitalization_escalation",
            "risk_dnr_deescalate", "risk_parenteral_controlled",
        ]
        risk_override = _v(row, 31)  # AF

        # Dx codes (AI–AP = indices 34–41, 8 total)
        dx_codes = [_v(row, i) for i in range(34, 42) if _v(row, i)]

        # Procedure CPTs (AQ+AR = 42+43, AS+AT = 44+45, AU+AV = 46+47, AW+AX = 48+49)
        procedure_cpts = []
        for base in (42, 44, 46, 48):
            code = _v(row, base)
            if code:
                modifier = _v(row, base + 1)
                procedure_cpts.append(f"{code}:{modifier}" if modifier else code)

        entered_by = _v(row, 50)  # AY

        results.append({
            "chart_number": chart_number,
            "copa_self_limited":           _int(row, 1),
            "copa_stable_acute":           _int(row, 2),
            "copa_stable_chronic":         _int(row, 3),
            "copa_acute_uncomplicated":    _int(row, 4),
            "copa_chronic_exacerbation":   _int(row, 5),
            "copa_undiagnosed_new":        _int(row, 6),
            "copa_acute_systemic":         _int(row, 7),
            "copa_acute_complicated_injury": _int(row, 8),
            "copa_chronic_severe":         _int(row, 9),
            "copa_threat_to_life":         _int(row, 10),
            "copa_level_override":         copa_override,
            "copa_level_overridden":       bool(copa_override),
            "dr_prior_external_notes":     _int(row, 12),
            "dr_review_test_results":      _int(row, 13),
            "dr_order_tests":              _int(row, 14),
            "dr_independent_historian":    _bool(row, 15),
            "dr_independent_interpretation": _bool(row, 16),
            "dr_external_discussion":      _bool(row, 17),
            "dr_level_override":           dr_override,
            "dr_level_overridden":         bool(dr_override),
            **{field: _bool(row, 19 + i) for i, field in enumerate(risk_fields)},
            "risk_level_override":         risk_override,
            "risk_level_overridden":       bool(risk_override),
            "em_code":                     _v(row, 32),   # AG
            "em_modifier":                 _v(row, 33),   # AH
            "dx_codes":                    dx_codes,
            "procedure_cpts":              procedure_cpts,
            "entered_by":                  entered_by,
        })

    return results


# ── Results Excel export ──────────────────────────────────────────────────────

def export_batch_results(batch_name: str, results: list[dict]) -> bytes:
    """
    Export grading results to Excel with three sheets:
    Batch_Summary, Results_Summary (per coder), Feedback_Detail
    """
    wb = Workbook()
    wb.remove(wb.active)

    # ── Batch Summary sheet
    bs = wb.create_sheet("Batch_Summary")
    bs["A1"] = "Batch"
    bs["B1"] = batch_name
    bs["A1"].font = bs["B1"].font = Font(bold=True)

    # Aggregate from results
    coders = {}
    for r in results:
        name = r["coder_name"]
        if name not in coders:
            coders[name] = {"scores": [], "pass": 0, "fail": 0}
        if r.get("total_score") is not None:
            coders[name]["scores"].append(r["total_score"])
            if r.get("pass_fail") == "PASS":
                coders[name]["pass"] += 1
            else:
                coders[name]["fail"] += 1

    total_coders = len(coders)
    # Only count coders with at least one finalized score; ties go to FAIL
    passed = sum(1 for v in coders.values() if (v["pass"] + v["fail"]) > 0 and v["pass"] > v["fail"])
    all_scores = [s for v in coders.values() for s in v["scores"]]
    avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

    bs["A3"] = "Total Coders"; bs["B3"] = total_coders
    bs["A4"] = "Passed"; bs["B4"] = passed
    bs["A5"] = "Failed"; bs["B5"] = total_coders - passed
    bs["A6"] = "Pass Rate"; bs["B6"] = f"{round(passed/total_coders*100, 1)}%" if total_coders else "N/A"
    bs["A7"] = "Avg Score"; bs["B7"] = f"{avg}%"
    for r in range(3, 8):
        bs.cell(r, 1).font = Font(bold=True)
    bs.column_dimensions["A"].width = 20
    bs.column_dimensions["B"].width = 20

    # ── Results Summary sheet
    rs = wb.create_sheet("Results_Summary")
    is_ip = any(r.get("specialty") == "IP-DRG" for r in results)
    headers = ["Coder", "Charts", "Avg PDx", "Avg SDx"]
    if is_ip:
        headers += ["Avg PCS", "Avg DRG"]
    else:
        headers.append("Avg CPT")
    headers += ["Avg Total", "Pass/Fail"]

    for c, h in enumerate(headers, 1):
        _header(rs, c, 1, h)

    # Per-coder aggregation
    coder_detail: dict[str, dict] = {}
    for r in results:
        name = r["coder_name"]
        if name not in coder_detail:
            coder_detail[name] = {
                "count": 0, "scored": 0, "pdx": 0, "sdx": 0, "pcs": 0, "cpt": 0,
                "drg": 0, "total": 0, "passed": 0,
            }
        d = coder_detail[name]
        d["count"] += 1
        d["pdx"] += r.get("pdx_score", 0)
        d["sdx"] += r.get("sdx_score", 0)
        d["pcs"] += r.get("pcs_score") or 0
        d["cpt"] += r.get("cpt_score") or 0
        d["drg"] += r.get("drg_score") or 0
        if r.get("total_score") is not None:
            d["total"] += r["total_score"]
            d["scored"] += 1
        if r.get("pass_fail") == "PASS":
            d["passed"] += 1

    for row_num, (name, d) in enumerate(coder_detail.items(), 2):
        cnt = d["count"] or 1
        scored = d["scored"]
        pf = "PENDING" if scored == 0 else ("PASS" if d["passed"] > scored / 2 else "FAIL")
        row_data = [name, d["count"],
                    round(d["pdx"] / cnt, 1), round(d["sdx"] / cnt, 1)]
        if is_ip:
            row_data += [round(d["pcs"] / cnt, 1), round(d["drg"] / cnt, 1)]
        else:
            row_data.append(round(d["cpt"] / cnt, 1))
        row_data += [round(d["total"] / cnt, 1), pf]
        for c, val in enumerate(row_data, 1):
            cell = rs.cell(row=row_num, column=c, value=val)
            cell.border = THIN_BORDER
            if c == len(row_data):
                pf_color = "00A000" if val == "PASS" else "6B7280" if val == "PENDING" else "CC0000"
                cell.font = Font(bold=True, color=pf_color)
    for c in range(1, len(headers) + 1):
        rs.column_dimensions[get_column_letter(c)].width = 14

    # ── Feedback Detail sheet
    fd = wb.create_sheet("Feedback_Detail")
    fb_headers = ["Coder", "Chart_Number", "Section", "Issue_Type", "AK_Code", "Coder_Code", "Detail"]
    for c, h in enumerate(fb_headers, 1):
        _header(fd, c, 1, h)

    fb_row = 2
    for r in results:
        for fb in r.get("feedback", []):
            fd.cell(fb_row, 1, r["coder_name"]).border = THIN_BORDER
            fd.cell(fb_row, 2, r.get("chart_number", "")).border = THIN_BORDER
            fd.cell(fb_row, 3, fb.get("section", "")).border = THIN_BORDER
            fd.cell(fb_row, 4, fb.get("issue_type", "")).border = THIN_BORDER
            fd.cell(fb_row, 5, fb.get("ak_code", "")).border = THIN_BORDER
            fd.cell(fb_row, 6, fb.get("coder_code", "")).border = THIN_BORDER
            fd.cell(fb_row, 7, fb.get("detail", "")).border = THIN_BORDER
            fb_row += 1
    for c, w in enumerate([18, 16, 10, 18, 14, 14, 30], 1):
        fd.column_dimensions[get_column_letter(c)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
