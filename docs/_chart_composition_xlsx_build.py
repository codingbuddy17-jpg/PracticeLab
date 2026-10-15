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

# ---------------------------------------------------------------- pools
# Baseline chart pool per specialty. The first six come from the HC model's
# Specialty Grid (Baseline Charts Required, +10% buffer). ED Profee is a
# later addition and has no HC row yet -- see the Open Decisions sheet.
POOLS = [
    # specialty, type, pool, hc_source
    ("IP-DRG",          "IP", 693, "HC Specialty Grid"),
    ("ED Facility",     "OP", 704, "HC Specialty Grid"),
    ("ED Profee",       "OP", 400, "Set 2026-10-15; no HC row yet"),
    ("E/M",             "OP", 413, "HC Specialty Grid"),
    ("SDS",             "OP", 132, "HC Specialty Grid"),
    ("Surgery",         "OP", 300, "Set 2026-10-15; no HC row yet"),
    ("ED Single Path",  "OP", 300, "Set 2026-10-15; no HC row yet"),
]
SHEET_OF = {
    "IP-DRG": "IP-DRG Topics", "ED Facility": "ED Facility Topics",
    "ED Profee": "ED Profee Topics", "E/M": "E-M Topics",
    "SDS": "SDS Topics", "Surgery": "Surgery Topics",
    "ED Single Path": "ED Single Path Topics",
}
# Build priority. P1 is sourced and built first, then P2, then P3. It is a
# separate question from the weight: the weight says how many charts a topic
# should hold, the priority says which topics get built before the pool is
# complete. Confirmed with the user on 2026-10-15 for IP-DRG: OB and newborn
# first across both medical and surgical DRGs, then GI, respiratory and
# cardiovascular. Anything not named here is P2.
PRIORITY_1 = {
    # IP-DRG: the OB and newborn block, medical and surgical sides together
    "IPD-01", "IPD-02", "IPD-03", "IPD-04", "IPD-15", "IPD-16",
}
PRIORITY_3 = {
    # Low volume, constrained supply, or skills the pool can wait for
    "IPD-13", "IPD-14", "IPD-23", "IPD-24", "IPD-25",
    "EDF-02", "EDF-11", "EDF-16",
    "EDP-11", "EM-15", "EM-17",
    "SDS-09", "SDS-14", "SUR-09", "SUR-10", "ESP-08",
}


def priority_of(tid):
    if tid in PRIORITY_1:
        return "P1 — build first"
    if tid in PRIORITY_3:
        return "P3 — build last"
    return "P2"


# Pool-level difficulty mix, from HC Chart Selection section 4.
DIFF_MIX = [("Basic", 0.40), ("Moderate", 0.40), ("Complex", 0.20)]

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


# ============================================================== topic data
# (dimension, [ (category, parent % from HC section 6, [ (id, topic, scope,
#   excluded, topic % of pool, difficulty skew, primary channel,
#   elements graded, notes) ]) ])
TOPICS = {}

TOPICS["IP-DRG"] = ("DRG type", [
 ("Medical DRGs", 0.55, [
  ("IPD-01", "Vaginal delivery and complications of labour",
   "Delivery admissions grouping medical: vaginal and assisted delivery, complications of labour, and the maternal record only.",
   "Caesarean delivery — IPD-15; the newborn record — IPD-02", 0.05,
   "Complex-led", "C6 Customer escalations",
   "Principal diagnosis for a delivery admission, Z3A gestational weeks, outcome-of-delivery code, PCS delivery root operation, CC/MCC capture",
   "The PDx for a delivery admission is the complication, not the delivery — the error that keeps recurring. Vaginal delivery groups MEDICAL and caesarean groups SURGICAL, so OB sits on both sides of the 55/45 split and must be sourced against both."),
  ("IPD-02", "Normal newborn and newborn with condition",
   "The newborn record: normal newborn, newborn with a condition identified after birth, and the birth-weight and gestational-age axes that drive grouping.",
   "The maternal record — IPD-01 or IPD-15", 0.04, "Moderate-led", "C1 High error rate",
   "Birth weight, gestational age, newborn condition coding, POA on a newborn record, liveborn versus condition sequencing",
   "Mother and newborn records are linked; HC rule R3 requires PHI scrubbed from both before either is used. Birth weight is entered in grams and is the single most consequential value on the record."),
  ("IPD-03", "Neonatal and NICU admissions",
   "Prematurity, low birth weight, respiratory distress of the newborn, and neonatal admissions whose DRG turns on weight bands and procedures.",
   "", 0.02, "Complex-led", "C2 High dollar value",
   "Birth-weight band boundaries, prematurity coding, ventilator hours on a neonate, POA, MCC capture",
   "The weight bands are hard boundaries: a hundred grams moves the DRG. High dollar value and high error rate at once."),
  ("IPD-04", "Antepartum and postpartum medical admissions",
   "Maternal admissions that are not the delivery: hyperemesis, pre-eclampsia, preterm labour not delivered, and postpartum complications managed medically.",
   "Postpartum surgical procedures — IPD-16", 0.02,
   "Complex-led", "C1 High error rate",
   "Trimester characters, delivered versus not delivered, postpartum period rules, PDx selection, Z3A",
   "The not-delivered admissions are where the trimester character and the delivered/undelivered distinction go wrong."),
  ("IPD-05", "Digestive medical — GI bleed, pancreatitis, obstruction",
   "Medical GI admissions: GI haemorrhage with and without a stated site, pancreatitis aetiology, obstruction managed conservatively.",
   "Bowel resection, cholecystectomy and hernia repair — IPD-17", 0.06,
   "Moderate-led", "C1 High error rate",
   "Bleeding site specificity, aetiology linkage, blood transfusion capture, CC/MCC, PDx sequencing",
   ""),
  ("IPD-06", "Respiratory — pneumonia, COPD exacerbation, respiratory failure",
   "Admissions where the principal diagnosis is respiratory and no OR procedure drives the DRG. Includes acute-on-chronic respiratory failure and the ventilator-hours boundary.",
   "Thoracotomy and tracheostomy cases — IPD-19", 0.07,
   "Moderate-led", "C1 High error rate",
   "Principal diagnosis selection, pneumonia organism specificity, CC/MCC capture, POA, ventilator hours",
   "Sequencing respiratory failure against the underlying condition is the most disputed PDx call in this specialty. Carry charts in both directions."),
  ("IPD-07", "Circulatory medical — heart failure, AMI, arrhythmia",
   "Medical cardiac admissions. Heart failure type and acuity, AMI type 1 versus type 2, atrial fibrillation.",
   "CABG, valve, PCI and EP procedures — IPD-18", 0.06,
   "Moderate-led", "C5 DRGV trending PCS / DRG",
   "Heart failure specificity, AMI type, CC/MCC capture, PDx sequencing when cardiac and respiratory both present",
   "Type 2 MI versus demand ischaemia is a current trending error area; refresh from the DRGV report each cycle."),
  ("IPD-08", "Sepsis, severe sepsis and septic shock",
   "Sepsis as principal or secondary, with and without organ dysfunction. Includes the localised-infection-versus-sepsis judgement and post-procedural sepsis.",
   "Newborn sepsis — IPD-02 or IPD-03", 0.07, "Complex-led", "C1 High error rate",
   "Sepsis sequencing, severe sepsis with organ dysfunction, R65.2x, POA, query opportunity, MCC capture",
   "Highest-yield topic for query practice (HC use case 07). Charts with a resolved query are preferred; unresolved ones are excluded by X3."),
  ("IPD-09", "Nervous system medical — CVA, TIA, intracranial haemorrhage",
   "Acute neurological admissions coded medically, including thrombolytic administration and residual-deficit codes.",
   "Craniotomy, shunt and spine decompression — IPD-21", 0.04,
   "Complex-led", "C2 High dollar value",
   "CVA site and laterality, late effect versus acute, thrombolytic status Z92.82, POA, functional deficit capture",
   "Z92.82 affects the DRG and is routinely missed when the thrombolytic was given at a transferring facility."),
  ("IPD-10", "Kidney and urinary — AKI, CKD, UTI",
   "Renal admissions with no OR procedure. Includes AKI on CKD, the AKI-versus-dehydration call, and dialysis dependence.",
   "Dialysis access creation and nephrectomy — IPD-22", 0.03,
   "Moderate-led", "C1 High error rate",
   "AKI versus CKD staging, N17/N18 combination, CC/MCC capture, POA",
   "AKI is a CC and is often documented only as a lab trend; a strong query topic."),
  ("IPD-11", "Endocrine and metabolic — DKA, malnutrition, electrolyte disorders",
   "Diabetic emergencies, severe protein-calorie malnutrition, and significant electrolyte disturbance as principal or as the MCC.",
   "", 0.03, "Complex-led", "C1 High error rate",
   "Diabetes with complication linkage, malnutrition severity and clinical criteria, MCC capture, POA",
   "Severe malnutrition is a high-value MCC and the most commonly denied on audit; the chart must carry the clinical criteria, not just the dietitian note."),
  ("IPD-12", "Haematology and oncology — medical admissions",
   "Neutropenia, anaemia requiring transfusion, sickle-cell crisis, and admissions for a complication of a malignancy.",
   "Admissions for chemotherapy administration alone — out of scope this cycle", 0.03,
   "Complex-led", "C6 Customer escalations",
   "Neoplasm versus complication sequencing, primary versus secondary site, admission-for-treatment rules, anaemia in neoplastic disease",
   "Sequencing an admission for a complication of cancer against the cancer itself is a recurring escalation topic."),
  ("IPD-13", "Mental health and substance use",
   "Psychiatric and substance-withdrawal admissions where the full record is available for training use.",
   "Anything under 42 CFR Part 2 or client-restricted — removed entirely by X2", 0.02,
   "Basic-led", "C8 Foundation",
   "Substance use versus abuse versus dependence, withdrawal with complication, psychiatric PDx selection",
   "Sourcing is narrow by design: X2 removes most candidates. If eligible supply is not there, report it as a constrained topic rather than forcing the target."),
  ("IPD-14", "Other infectious disease",
   "Infectious admissions that are not sepsis: cellulitis, osteomyelitis, C. difficile, endocarditis, and device-related infection.",
   "Sepsis and septic shock — IPD-08", 0.01, "Moderate-led", "C8 Foundation",
   "Organism specificity, device-related infection coding, PDx sequencing against the device complication, CC/MCC",
   "Device-related infection carries a complication code that must be sequenced with the infection; a frequent miss."),
 ]),
 ("Surgical DRGs", 0.45, [
  ("IPD-15", "Caesarean delivery",
   "Caesarean delivery admissions, which group surgical, including the indication that drives the principal diagnosis and sterilisation performed at the same time.",
   "Vaginal delivery — IPD-01; the newborn record — IPD-02", 0.04,
   "Complex-led", "C1 High error rate",
   "Principal diagnosis (the indication, not the caesarean), PCS delivery root operation and approach, concurrent sterilisation, Z3A, CC/MCC",
   "The caesarean half of the OB priority block. Coding the caesarean itself as the PDx instead of the indication is the error this topic exists to train."),
  ("IPD-16", "Obstetric and postpartum surgical procedures",
   "Postpartum haemorrhage requiring intervention, retained products with D&C, obstetric laceration repair, and hysterectomy for an obstetric cause.",
   "Antepartum and postpartum medical admissions — IPD-04", 0.02,
   "Complex-led", "C6 Customer escalations",
   "PCS root operation for evacuation and repair, postpartum period rules, PDx sequencing, blood product capture",
   "Low volume, high error rate. Completes the OB priority block on the surgical side."),
  ("IPD-17", "Digestive surgical — bowel resection, cholecystectomy, hernia repair",
   "Inpatient abdominal surgery, including laparoscopic-to-open conversion and anastomosis as a separate root operation.",
   "Same-day general surgery — SDS-12", 0.08, "Moderate-led", "C8 Foundation",
   "Root operation selection (Excision versus Resection), approach character, conversion coding, post-operative complication with POA",
   "Excision versus Resection on a partial organ is the classic PCS error and is worth planting in both directions."),
  ("IPD-18", "Cardiovascular surgical — CABG, valve, PCI, EP procedures",
   "Open and percutaneous cardiac procedures, including multi-vessel PCI with differing stent counts and intraoperative conversion.",
   "Diagnostic catheterisation with no intervention — out of scope this cycle", 0.08,
   "Complex-led", "C2 High dollar value",
   "PCS body-part and device characters, number of sites treated, graft harvesting as a separate procedure, PDx sequencing",
   "Highest reimbursement per chart in the pool. Counting treated sites and graft harvest is where the PCS code goes wrong."),
  ("IPD-19", "Respiratory surgical — thoracotomy, tracheostomy, lung resection",
   "Thoracic surgery and tracheostomy, including tracheostomy performed during a long ventilator stay, which changes the DRG entirely.",
   "", 0.03, "Complex-led", "C5 DRGV trending PCS / DRG",
   "PCS root operation and approach, tracheostomy with ventilator hours, lobe-level body part, POA",
   "A tracheostomy on a ventilated patient moves the case to the highest-weight DRG family; missing it is a large-dollar error."),
  ("IPD-20", "Musculoskeletal — joint replacement, spinal fusion, fracture fixation",
   "Elective and traumatic MSK surgery requiring admission. Approach and device-value axes of the PCS code, fusion level counts.",
   "Same-day orthopaedic procedures — SDS-01 to SDS-03", 0.09,
   "Moderate-led", "C5 DRGV trending PCS / DRG",
   "PCS root operation and device character, fusion levels and approach, bilateral procedures, POA on post-operative conditions",
   "Highest-volume surgical family and the best place to train PCS character selection. Carries the device-value character the auditor module plants against."),
  ("IPD-21", "Nervous system surgical — craniotomy, shunt, spine decompression",
   "Cranial and spinal surgery including shunt revision, which is a different root operation from shunt insertion.",
   "", 0.04, "Complex-led", "C2 High dollar value",
   "PCS root operation on a device (Revision, Replacement, Removal), body-part character, laterality, POA",
   "Device-related root operations are the least familiar part of PCS and are most often coded as Insertion."),
  ("IPD-22", "Genitourinary surgical",
   "Nephrectomy, prostatectomy, dialysis access creation and urological procedures requiring admission.",
   "Cystoscopy and stone procedures done same-day — SDS-15", 0.03,
   "Moderate-led", "C8 Foundation",
   "PCS body-part laterality, approach character, CC/MCC capture", ""),
  ("IPD-23", "Vascular access and device procedures — PICC, pacemaker, dialysis catheter",
   "Procedures whose DRG is driven by the device rather than the diagnosis, performed during a medical admission.",
   "", 0.02, "Moderate-led", "C6 Customer escalations",
   "PCS device and qualifier characters, central versus peripheral body part, Insertion versus Revision",
   "PICC lines are a named customer escalation area in the HC trainer-role sheet. Keep this topic filled."),
  ("IPD-24", "Transplant and other high-weight DRGs",
   "Solid-organ transplant, ECMO and other very high relative-weight cases.",
   "", 0.01, "Complex-led", "C2 High dollar value",
   "PCS transplant qualifier, ECMO coding, PDx sequencing, MCC capture",
   "Low volume by nature. One or two charts per refresh is the realistic supply; do not inflate the weight to force a count."),
  ("IPD-25", "Multiple significant trauma and burns",
   "Polytrauma and significant burn admissions, where sequencing rules are specific and code volume is high.",
   "Single-site injury seen in the ED — EDF-06", 0.01,
   "Complex-led", "C2 High dollar value",
   "Multiple significant trauma DRG criteria, burn TBSA coding, injury sequencing, POA", ""),
 ]),
])

TOPICS["ED Facility"] = ("Facility level", [
 ("Levels 1–2", 0.20, [
  ("EDF-01", "Minor presentations and rechecks (99281 / 99282)",
   "Low-acuity visits resolved with assessment and simple intervention: medication refill, suture removal, wound recheck, dressing change.",
   "", 0.10, "Basic-led", "C8 Foundation",
   "Facility level criteria and the point-based acuity tool, diagnosis specificity, discharge disposition",
   "The main source of Week 1 Basic-tier charts for ED. Keep this topic full or Week 1 has nothing to run on."),
  ("EDF-02", "Nurse-only and ancillary-only ED encounters",
   "Visits with no provider evaluation: injection-only, blood-draw-only, or ancillary service performed in the ED setting.",
   "Visits where a provider evaluated the patient — EDF-01", 0.05,
   "Basic-led", "C8 Foundation",
   "Whether a facility level is billable at all, ancillary-only service coding, diagnosis linkage",
   "Teaches the lower bound of the ladder: the correct answer is sometimes that no E/M level applies."),
  ("EDF-03", "Low-acuity visits with an ED procedure",
   "Simple procedure as the reason for the visit: foreign body removal, simple I&D, nail trephination.",
   "", 0.05, "Basic-led", "C1 High error rate",
   "Procedure versus facility level interaction, separately reportable service, laterality and site",
   ""),
 ]),
 ("Level 3", 0.30, [
  ("EDF-04", "Moderate medical presentations — URI, UTI, gastroenteritis",
   "Common medical complaints with limited workup: one or two diagnostics, oral or single IV medication.",
   "", 0.10, "Basic-led", "C8 Foundation",
   "Facility level criteria, diagnosis specificity, medication administration capture", ""),
  ("EDF-05", "Minor trauma and wound repair",
   "Laceration repair by length and complexity, contusions, abrasions, and minor burns.",
   "Polytrauma — EDF-15", 0.08, "Moderate-led", "C1 High error rate",
   "Repair length and complexity tiers, anatomic site grouping, injury external cause, facility level",
   "Summing repair lengths across sites in the same anatomic group is the recurring error here."),
  ("EDF-06", "Orthopaedic injury — sprain, simple fracture, splinting",
   "Extremity injury with imaging, splint or cast application, and reduction where performed.",
   "Injuries admitted for operative fixation — IP-DRG (IPD-20)", 0.07,
   "Moderate-led", "C1 High error rate",
   "Fracture site and laterality, initial encounter character, splint and strapping application, facility level",
   "The seventh character for encounter type is the most frequently wrong element in this topic."),
  ("EDF-07", "Infusion and injection administration visits",
   "ED visits where hydration, therapeutic infusion or injection is the substance of the encounter.",
   "", 0.05, "Moderate-led", "C7 Denial trends",
   "Infusion hierarchy (chemo, therapeutic, hydration), initial versus sequential versus concurrent, units by time, diagnosis linkage",
   "The infusion hierarchy and the start/stop time arithmetic are a denial-trend area; source from the denial report."),
 ]),
 ("Level 4", 0.30, [
  ("EDF-08", "Abdominal and chest pain workups",
   "Undifferentiated pain presentations with extensive diagnostics and serial assessment, discharged with a symptom diagnosis.",
   "", 0.09, "Moderate-led", "C1 High error rate",
   "Facility level criteria at the 4/5 boundary, symptom versus confirmed diagnosis, serial diagnostic capture",
   "Teaches coding to a symptom when no diagnosis was reached — the correct answer is often the symptom code."),
  ("EDF-09", "Respiratory distress — asthma, COPD, pneumonia",
   "Respiratory presentations with nebuliser treatment, imaging, and sometimes non-invasive ventilation.",
   "Intubated or critical care patients — EDF-13", 0.07,
   "Moderate-led", "C8 Foundation",
   "Exacerbation documentation, nebuliser and ventilation management capture, facility level, diagnosis specificity", ""),
  ("EDF-10", "Complex medical with multiple workups",
   "Multi-system presentations in comorbid patients: weakness, syncope, altered mental state, with broad workup.",
   "", 0.07, "Complex-led", "C1 High error rate",
   "Facility level at the 4/5 boundary, comorbidity capture, diagnosis sequencing, extent of workup",
   "The level 4 versus 5 call is the highest-volume error in ED facility coding; this topic exists to train the boundary."),
  ("EDF-11", "Behavioural health presentations",
   "Psychiatric and substance-related ED visits with medical screening, sitter or restraint use, and disposition delay.",
   "Records under 42 CFR Part 2 or client-restricted — removed by X2", 0.04,
   "Moderate-led", "C6 Customer escalations",
   "Facility level where time and monitoring drive acuity, substance use coding, suicidal ideation coding, disposition",
   "Constrained supply under X2. Report as constrained rather than forcing the count."),
  ("EDF-12", "Observation services initiated from the ED",
   "ED visit converting to observation: observation hours, the ED level alongside it, and the discharge-or-admit decision.",
   "Inpatient admissions — IP-DRG", 0.03, "Complex-led", "C7 Denial trends",
   "Observation hour counting, whether the ED level is separately reportable, status determination, diagnosis supporting observation",
   "Observation hour counting is a denial-trend area and is routinely coded from the order time rather than the clock time."),
 ]),
 ("Level 5 / critical care", 0.20, [
  ("EDF-13", "High-acuity medical (99285)",
   "Patients with immediate threat requiring extensive evaluation and intervention, short of critical care time.",
   "Encounters where critical care time was documented — EDF-14", 0.09,
   "Complex-led", "C1 High error rate",
   "Facility level 5 criteria, extent of intervention, diagnosis specificity, comorbidity capture", ""),
  ("EDF-14", "Critical care (99291 / 99292)",
   "Encounters with documented critical care time and organ-system failure, including the bundled-service list.",
   "Level 5 visits with no documented critical care time — EDF-13", 0.06,
   "Complex-led", "C2 High dollar value",
   "Critical care qualification, time documentation, bundled versus separately reportable procedures, facility level interaction",
   "Whether the condition qualifies as critical care at all is the hardest question in the ED. The time arithmetic is not the training point and is not where coders go wrong."),
  ("EDF-15", "Trauma activation",
   "Encounters meeting the trauma team activation criteria, with the activation charge and its documentation requirements.",
   "", 0.03, "Complex-led", "C7 Denial trends",
   "Trauma activation criteria and pre-notification requirement, revenue code use, injury coding, facility level",
   "The activation charge requires pre-hospital notification; charts missing it teach the denial."),
  ("EDF-16", "Cardiac arrest and resuscitation",
   "Resuscitation encounters including CPR, defibrillation, intubation and death in the department.",
   "", 0.02, "Complex-led", "C2 High dollar value",
   "Resuscitation procedure coding, critical care interaction, disposition including expired, diagnosis sequencing", ""),
 ]),
])

TOPICS["ED Profee"] = ("ED E/M level", [
 ("Low acuity", 0.08, [
  ("EDP-01", "99281 / 99282 — straightforward presentations",
   "Professional component of low-acuity ED visits: problem-focused history and examination, straightforward MDM.",
   "", 0.08, "Basic-led", "C8 Foundation",
   "MDM-based level selection, problem addressed, diagnosis specificity",
   "Graded on the ED ladder in services/em_levels.py, which is separate from the office ladders. Same level on the wrong ladder is a distinct error from a near miss on the right one."),
 ]),
 ("Moderate", 0.18, [
  ("EDP-02", "99283 — moderate MDM",
   "Visits with limited data reviewed and low-to-moderate risk: one or two problems, limited diagnostics.",
   "", 0.12, "Basic-led", "C8 Foundation",
   "COPA, Data Review and Risk as three MDM levels, the 2-of-3 rule, diagnosis specificity",
   "MDM is audited as three levels, never as element ticks."),
  ("EDP-03", "99283 with a separately reportable procedure",
   "Moderate visits where a minor procedure was performed and modifier 25 is in play.",
   "", 0.06, "Moderate-led", "C1 High error rate",
   "Modifier 25 appropriateness, procedure versus E/M separation, MDM level, laterality",
   "Modifier 25 is the single most audited modifier in ED profee coding."),
 ]),
 ("Level 4", 0.20, [
  ("EDP-04", "99284 — moderate-to-high MDM",
   "Multiple problems or extensive data review with moderate risk, including prescription drug management.",
   "", 0.13, "Moderate-led", "C1 High error rate",
   "COPA, Data Review, Risk, the 2-of-3 rule, prescription drug management as a risk element",
   "The 99284/99285 boundary carries the most level errors; plant in both directions so upcoding and downcoding both appear."),
  ("EDP-05", "99284 with fracture care or wound repair",
   "Level 4 visits with a procedure that has its own global period, so the E/M may or may not be separately reportable.",
   "", 0.07, "Complex-led", "C1 High error rate",
   "Global period of the procedure, modifier 25 and 57, procedure code selection, MDM level", ""),
 ]),
 ("Level 5", 0.24, [
  ("EDP-06", "99285 — high MDM",
   "High COPA with extensive data and high risk, short of critical care.",
   "Documented critical care time — EDP-08", 0.15,
   "Complex-led", "C1 High error rate",
   "COPA at the highest level, data categories, risk including decision for hospitalisation, the 2-of-3 rule", ""),
  ("EDP-07", "99285 versus 99291 — the critical care boundary",
   "Charts sitting on the line: high-acuity patients where whether the condition qualified as critical care is genuinely arguable.",
   "Clear-cut critical care — EDP-08; clear-cut level 5 — EDP-06", 0.09,
   "Complex-led", "C6 Customer escalations",
   "Critical care qualification, organ system failure, time documentation, MDM level if not critical care",
   "The hardest question in the ED and the one a generated error cannot invent. These charts need AnswerKey.cc_boundary set to borderline before the auditor module will plant against them."),
 ]),
 ("Critical care", 0.12, [
  ("EDP-08", "99291 / 99292 — critical care",
   "Professional critical care with documented time and organ-system failure, including the bundled-service list and the second-hour units.",
   "", 0.12, "Complex-led", "C2 High dollar value",
   "Critical care qualification, bundled procedures, separately reportable procedures, diagnosis sequencing",
   "The 99292 unit count follows from the time and is not where coders go wrong; critical care time itself is never planted. An auditor validates the code, not the arithmetic."),
 ]),
 ("Cross-cutting", 0.18, [
  ("EDP-09", "ED procedures billed with an E/M",
   "Laceration repair, I&D, fracture care, joint reduction and foreign body removal alongside the ED E/M.",
   "", 0.10, "Moderate-led", "C1 High error rate",
   "Procedure code selection, modifier 25 and 59, bundling against the E/M, laterality and site", ""),
  ("EDP-10", "Observation and admission by the ED physician",
   "Encounters where the ED physician initiates observation or admits, and the service crosses code families.",
   "", 0.04, "Complex-led", "C7 Denial trends",
   "Which code family applies, same-day E/M rules, modifier 25, diagnosis supporting the status", ""),
  ("EDP-11", "Split / shared and teaching-physician documentation",
   "Encounters documented by a resident, APP or jointly, where attestation and substantive-portion rules decide what is billable.",
   "", 0.04, "Complex-led", "C6 Customer escalations",
   "Split/shared substantive portion, teaching physician attestation, modifier use, MDM level",
   "A documentation-rule topic rather than a code-selection one: the correct answer sometimes is that the service is not billable as documented."),
 ]),
])

TOPICS["E/M"] = ("Level", [
 ("Low (levels 2–3)", 0.35, [
  ("EM-01", "New patient office / outpatient, low (99202 / 99203)",
   "New-patient office visits with one self-limited or stable problem, minimal data, minimal-to-low risk.",
   "ED visits — ED Profee; established patients — EM-02", 0.07,
   "Basic-led", "C8 Foundation",
   "New versus established determination, COPA, Data Review, Risk, the 2-of-3 rule",
   "New-patient and established-patient office visits are separate ladders. The same level on the wrong ladder is the new-versus-established error, not a near miss."),
  ("EM-02", "Established patient office / outpatient, low (99212 / 99213)",
   "Established-patient visits for stable chronic conditions or a single acute uncomplicated problem.",
   "", 0.14, "Basic-led", "C8 Foundation",
   "COPA for a stable chronic condition, Data Review, Risk, the 2-of-3 rule",
   "The highest-volume topic in the specialty and the main Week 1 source. 99213 versus 99214 is the most common level error in outpatient coding."),
  ("EM-03", "Initial hospital / observation care, low (99221)",
   "First inpatient or observation encounter by the admitting provider at the lowest level of the ladder.",
   "ED-initiated observation — ED Profee (EDP-10)", 0.04,
   "Basic-led", "C8 Foundation",
   "Initial versus subsequent determination, COPA, Data Review, Risk, admission date rules", ""),
  ("EM-04", "Subsequent hospital / observation care, low (99231)",
   "Daily inpatient visits where the patient is stable, recovering or improving.",
   "", 0.05, "Basic-led", "C8 Foundation",
   "Subsequent care ladder, interval history, COPA, Risk",
   "The inpatient ladder is distinct from both office ladders; a chart coded on the wrong ladder is a classifier error, not a level error."),
  ("EM-05", "Preventive and annual wellness visits",
   "Preventive medicine services and the Medicare AWV, including a problem-oriented visit on the same day.",
   "", 0.05, "Moderate-led", "C7 Denial trends",
   "Age-banded preventive code selection, AWV versus preventive distinction, modifier 25 for a same-day problem visit, diagnosis linkage",
   "Not graded on medical decision making at all: applicable_weights drops the MDM weights for preventive charts, and sections_for_chart resolves the form per chart. A chart with no key keeps the full form, because absence is not evidence it is preventive."),
 ]),
 ("Moderate (level 4)", 0.40, [
  ("EM-06", "New patient office / outpatient, moderate (99204)",
   "New-patient visits with multiple problems or extensive data review, moderate risk including prescription management.",
   "", 0.09, "Moderate-led", "C1 High error rate",
   "COPA for multiple or chronic problems, data categories, prescription drug management as risk, the 2-of-3 rule", ""),
  ("EM-07", "Established patient office / outpatient, moderate (99214)",
   "The workhorse established visit: two or more stable chronic conditions, or one with exacerbation, with prescription management.",
   "", 0.15, "Moderate-led", "C1 High error rate",
   "COPA, Data Review, Risk, the 2-of-3 rule, chronic condition exacerbation documentation",
   "Largest single topic in the pool. Plant level errors in both directions here: upcoding is what payers audit for, downcoding is revenue quietly left behind."),
  ("EM-08", "Initial hospital / observation care, moderate (99222)",
   "Admissions with multiple active problems and moderate risk.",
   "", 0.05, "Moderate-led", "C8 Foundation",
   "COPA, data categories, risk of morbidity, initial versus subsequent", ""),
  ("EM-09", "Subsequent hospital / observation care, moderate (99232)",
   "Daily visits where the patient is not responding adequately or has a minor complication.",
   "", 0.06, "Moderate-led", "C1 High error rate",
   "Subsequent care ladder, COPA for an inadequately responding problem, Data Review, Risk", ""),
  ("EM-10", "Consultations, moderate (99243 / 99253)",
   "Office and inpatient consultations at moderate level, where the request and the reason for it must be documented.",
   "", 0.05, "Complex-led", "C6 Customer escalations",
   "Consultation requirements (request, reason, report), consult versus transfer of care, COPA, Data Review, Risk",
   "Consults are off-ladder for planting purposes: em_levels.py knows three ladders plus critical care, so a consult is not a near miss along any of them."),
 ]),
 ("High (level 5)", 0.25, [
  ("EM-11", "New patient office / outpatient, high (99205)",
   "New-patient visits with high COPA, extensive data and high risk.",
   "", 0.04, "Complex-led", "C1 High error rate",
   "COPA at the highest level, independent interpretation and external discussion as data, high risk", ""),
  ("EM-12", "Established patient office / outpatient, high (99215)",
   "Established visits with severe exacerbation or threat to function, with high-risk management.",
   "", 0.05, "Complex-led", "C1 High error rate",
   "COPA for severe exacerbation, data categories, high risk including drug therapy requiring monitoring", ""),
  ("EM-13", "Initial hospital / observation care, high (99223)",
   "Admissions with high COPA and high risk of morbidity.",
   "", 0.04, "Complex-led", "C2 High dollar value",
   "COPA, data categories, risk including decision for escalation of care", ""),
  ("EM-14", "Subsequent hospital / observation care, high (99233)",
   "Daily visits where the patient is unstable or has a significant complication.",
   "", 0.04, "Complex-led", "C1 High error rate",
   "COPA for an unstable problem, Data Review, Risk", ""),
  ("EM-15", "Consultations, high (99245 / 99255)",
   "Consultations at the highest level, typically multi-system or where the consultant assumes management.",
   "", 0.03, "Complex-led", "C6 Customer escalations",
   "Consultation requirements, COPA, data categories, high risk", "Off-ladder; see EM-10."),
  ("EM-16", "Discharge day management and prolonged services",
   "Discharge day management by time, and prolonged service add-ons where total time drives the code.",
   "", 0.03, "Moderate-led", "C7 Denial trends",
   "Time thresholds, what counts toward total time on the date of service, add-on code units, same-day rules",
   "Time-based rather than MDM-based, so MDM weights do not apply. These are the charts behind the HC Method split of 80% MDM / 20% time."),
  ("EM-17", "Split / shared visits and telehealth",
   "Visits documented jointly by a physician and APP, and visits delivered by telehealth, where who may bill and at what level is the question.",
   "", 0.02, "Complex-led", "C6 Customer escalations",
   "Substantive portion determination, modifier and place-of-service selection, telehealth modifier use, MDM or time level",
   "Named in the HC coverage matrix as a must-include for this specialty."),
 ]),
])

TOPICS["SDS"] = ("Service line", [
 ("Orthopaedics", 0.25, [
  ("SDS-01", "Knee and shoulder arthroscopy",
   "Same-day arthroscopic procedures, including multiple compartments and procedures performed through one approach.",
   "Arthroplasty requiring admission — IP-DRG (IPD-20)", 0.10,
   "Moderate-led", "C1 High error rate",
   "Multiple procedure bundling in one compartment, modifier 51 and 59, laterality, implant and device capture",
   "Separately reportable versus bundled within the same compartment is the recurring error."),
  ("SDS-02", "Hand and foot procedures",
   "Tendon, nerve and small-joint procedures where the code is driven by the digit and the structure treated.",
   "", 0.08, "Moderate-led", "C8 Foundation",
   "Digit-specific modifiers, number of structures treated, laterality, bundling", ""),
  ("SDS-03", "Fracture care and hardware removal",
   "Closed and open reduction performed same-day, and removal of previously placed hardware.",
   "", 0.07, "Moderate-led", "C8 Foundation",
   "Reduction versus manipulation, global period, hardware removal coding, laterality", ""),
 ]),
 ("GI / endoscopy", 0.25, [
  ("SDS-04", "Screening versus diagnostic colonoscopy",
   "Colonoscopies where the indication decides the code and the modifier: screening, screening converted to diagnostic, and surveillance.",
   "", 0.10, "Moderate-led", "C7 Denial trends",
   "Screening versus diagnostic determination, modifier 33 and PT, diagnosis sequencing, patient liability consequence",
   "A screening that converts to diagnostic changes both the code and the patient's liability. The highest-frequency denial topic in SDS."),
  ("SDS-05", "Colonoscopy with polypectomy — technique-driven coding",
   "Polyp removal where the technique used (snare, hot biopsy, cold forceps, EMR) decides the code, including multiple techniques in one session.",
   "", 0.08, "Complex-led", "C1 High error rate",
   "Technique-specific code selection, one code per technique rule, modifier 59, diagnosis linkage",
   "Coders routinely report one code per polyp rather than one per technique; a clean error to plant."),
  ("SDS-06", "EGD and combined upper and lower endoscopy",
   "Upper endoscopy alone and EGD performed with colonoscopy in the same session.",
   "", 0.07, "Moderate-led", "C8 Foundation",
   "Multiple endoscopy rules, modifier 51, base code selection, diagnosis linkage", ""),
 ]),
 ("Ophthalmology", 0.15, [
  ("SDS-07", "Cataract extraction with IOL",
   "Routine and complex cataract extraction, including the documentation that distinguishes complex from routine.",
   "", 0.08, "Basic-led", "C8 Foundation",
   "Complex versus routine criteria, laterality, staged bilateral procedures, device capture",
   "High volume and largely formulaic, which makes it a reliable Basic-tier source."),
  ("SDS-08", "Intravitreal injections and retinal laser",
   "Injection and laser procedures, often bilateral and repeated on a schedule.",
   "", 0.04, "Moderate-led", "C7 Denial trends",
   "Bilateral and laterality modifiers, repeat service within a period, drug units, diagnosis linkage", ""),
  ("SDS-09", "Oculoplastic and other eye procedures",
   "Lid, lacrimal and strabismus procedures where functional versus cosmetic intent decides coverage.",
   "", 0.03, "Complex-led", "C7 Denial trends",
   "Functional versus cosmetic documentation, laterality, bundling, diagnosis supporting medical necessity", ""),
 ]),
 ("Pain management", 0.15, [
  ("SDS-10", "Epidural and facet joint injections",
   "Injections where the spinal level, the number of levels and the laterality all drive the code and the units.",
   "", 0.08, "Complex-led", "C1 High error rate",
   "Level counting and add-on codes, bilateral reporting, imaging guidance bundling, MUE limits",
   "Level counting against the MUE limit is the specific failure; the units are where it goes wrong, not the base code."),
  ("SDS-11", "Radiofrequency ablation and nerve blocks",
   "Ablation and block procedures by nerve and level, including the diagnostic block that precedes ablation.",
   "", 0.07, "Complex-led", "C7 Denial trends",
   "Nerve-specific code selection, level and laterality units, prior diagnostic block requirement, imaging bundling", ""),
 ]),
 ("Other surgical", 0.20, [
  ("SDS-12", "General surgery — hernia repair, cholecystectomy, excisions",
   "Same-day general surgery, including hernia repair by type and approach and lesion excision by size and margin.",
   "Cases requiring admission — IP-DRG (IPD-17)", 0.07,
   "Moderate-led", "C8 Foundation",
   "Hernia type, approach and reducibility, lesion size including margins, approach character, bundling", ""),
  ("SDS-13", "Gynaecology — hysteroscopy, D&C, laparoscopy",
   "Same-day gynaecological surgery, including diagnostic-to-operative conversion.",
   "Delivery admissions — IP-DRG (IPD-01 / IPD-15)", 0.05,
   "Moderate-led", "C8 Foundation",
   "Diagnostic versus operative, bundling within one approach, modifier 59, diagnosis linkage", ""),
  ("SDS-14", "ENT — tonsillectomy, sinus surgery, myringotomy",
   "Airway and sinus procedures where bilateral reporting and multiple sinuses drive the units.",
   "", 0.04, "Moderate-led", "C8 Foundation",
   "Bilateral and multiple-site reporting, age-banded code selection, bundling", ""),
  ("SDS-15", "Urology — cystoscopy, TURP, stone procedures",
   "Same-day urological procedures, including cystoscopy as a base for a more extensive service.",
   "Procedures requiring admission — IP-DRG (IPD-22)", 0.04,
   "Moderate-led", "C8 Foundation",
   "Base versus more extensive procedure, bundling of the cystoscopy, laterality, stent placement", ""),
 ]),
])

TOPICS["Surgery"] = ("Service line", [
 ("High-volume service lines", 0.64, [
  ("SUR-01", "General surgery — hernia, cholecystectomy, appendectomy, bowel",
   "Professional surgical coding for general-surgery cases across settings, including laparoscopic-to-open conversion.",
   "Same-day minor excisions — SDS-12", 0.18,
   "Moderate-led", "C8 Foundation",
   "Approach and conversion coding, multiple procedure bundling, modifier 51 and 59, global period",
   "Conversion from laparoscopic to open is coded to the completed approach, not both; a clean error to plant."),
  ("SUR-02", "Orthopaedics — arthroplasty, arthroscopy, fracture fixation",
   "Professional coding for orthopaedic surgery including revision arthroplasty and multi-level spinal instrumentation.",
   "Same-day arthroscopy — SDS-01", 0.18,
   "Complex-led", "C2 High dollar value",
   "Primary versus revision, component-level coding, level counting and add-ons, laterality, modifier 62 co-surgeon", ""),
  ("SUR-03", "Cardiothoracic and vascular",
   "Open cardiac, thoracic and vascular procedures, including graft harvest and multi-vessel work.",
   "", 0.10, "Complex-led", "C2 High dollar value",
   "Number of grafts and vessels, harvest as a separate procedure, modifier 62 and 80, bundling of access",
   "Highest reimbursement per chart. Counting vessels and reporting harvest separately are the two recurring errors."),
  ("SUR-04", "Neurosurgery — cranial and spine",
   "Cranial procedures and spinal decompression, fusion and instrumentation, where levels and approaches multiply.",
   "", 0.10, "Complex-led", "C2 High dollar value",
   "Level counting across decompression and fusion, approach-specific codes, add-on hierarchy, co-surgeon modifiers", ""),
  ("SUR-05", "Gynaecology and obstetric surgery",
   "Hysterectomy by approach and weight, caesarean delivery, and oncological gynaecological surgery.",
   "Same-day gynaecology — SDS-13", 0.08,
   "Moderate-led", "C8 Foundation",
   "Approach and specimen weight, bundled oophorectomy, global obstetric package, modifier 22", ""),
 ]),
 ("Specialty and cross-cutting", 0.36, [
  ("SUR-06", "Urology",
   "Open and endoscopic urological surgery including prostatectomy, nephrectomy and reconstruction.",
   "Same-day cystoscopy — SDS-15", 0.08,
   "Moderate-led", "C8 Foundation",
   "Approach, bundling of the endoscopic base, laterality, robotic assistance reporting", ""),
  ("SUR-07", "ENT and head and neck",
   "Airway, sinus, thyroid and head-and-neck oncological surgery, including neck dissection levels.",
   "", 0.07, "Moderate-led", "C8 Foundation",
   "Bilateral and multiple-site reporting, neck dissection extent, bundling, modifier 59", ""),
  ("SUR-08", "Plastics and reconstructive",
   "Flaps, grafts and reconstruction, where defect size and donor site both carry codes, and intent decides coverage.",
   "", 0.06, "Complex-led", "C7 Denial trends",
   "Defect size and site, donor site closure, functional versus cosmetic documentation, staged procedure modifiers", ""),
  ("SUR-09", "Ophthalmic surgery",
   "Retinal, corneal and glaucoma surgery beyond routine same-day cataract work.",
   "Routine cataract — SDS-07", 0.05,
   "Moderate-led", "C8 Foundation",
   "Laterality and staged bilateral work, bundling, global period, device capture", ""),
  ("SUR-10", "Transplant and complex multi-specialty cases",
   "Transplant, multi-team and multi-stage procedures where more than one surgeon reports a service.",
   "", 0.04, "Complex-led", "C2 High dollar value",
   "Modifier 62, 66 and 80, donor versus recipient coding, staged procedure reporting", ""),
  ("SUR-11", "Global period and staged procedure scenarios",
   "Returns to theatre, unrelated procedures during a global period, and staged work, where the modifier is the answer.",
   "", 0.06, "Complex-led", "C1 High error rate",
   "Modifiers 58, 76, 77, 78 and 79, global period boundaries, related versus unrelated determination",
   "A modifier-selection topic rather than a code-selection one. Which of 58, 78 and 79 applies is the whole question, and getting it wrong changes payment entirely."),
 ]),
])

TOPICS["ED Single Path"] = ("Acuity ladder (facility and profee on one chart)", [
 ("Low acuity", 0.08, [
  ("ESP-01", "Low acuity — levels 1–2 both components",
   "Single-path coding of a low-acuity ED encounter: facility level and professional level assigned from the same record.",
   "", 0.08, "Basic-led", "C8 Foundation",
   "Facility acuity tool and professional MDM applied to one record, diagnosis specificity, disposition",
   "Mirrors EDF-01 and EDP-01, but the charts are not shared between pools: a single-path chart is graded on both components at once and belongs only here."),
 ]),
 ("Moderate", 0.18, [
  ("ESP-02", "Moderate — level 3 both components",
   "Moderate presentations with limited workup, coded for facility and professional components together.",
   "", 0.18, "Basic-led", "C8 Foundation",
   "Facility level criteria, professional MDM (COPA, Data, Risk), diagnosis specificity",
   "Mirrors EDF-04 and EDP-02."),
 ]),
 ("Level 4", 0.20, [
  ("ESP-03", "Level 4 both components",
   "Multi-system or extensively worked-up presentations at level 4 on both components.",
   "", 0.20, "Moderate-led", "C1 High error rate",
   "Facility level at the 4/5 boundary, professional MDM and the 2-of-3 rule, comorbidity capture",
   "Mirrors EDF-08 to EDF-10 and EDP-04."),
 ]),
 ("Level 5", 0.22, [
  ("ESP-04", "Level 5 both components",
   "High-acuity encounters short of critical care, coded at level 5 on both components.",
   "Documented critical care time — ESP-05", 0.22,
   "Complex-led", "C1 High error rate",
   "Facility level 5 criteria, professional COPA, data and risk at the highest level, diagnosis sequencing",
   "Mirrors EDF-13 and EDP-06. The largest topic in this pool, as it is on both parent ladders."),
 ]),
 ("Critical care", 0.12, [
  ("ESP-05", "Critical care — both components",
   "Critical care encounters where the facility and professional components are both reported from one record.",
   "", 0.12, "Complex-led", "C2 High dollar value",
   "Critical care qualification, bundled versus separately reportable procedures, facility level interaction, diagnosis sequencing",
   "Whether the condition qualified as critical care at all is the training point. The 99292 unit count follows from the time and is not planted."),
 ]),
 ("Cross-cutting", 0.20, [
  ("ESP-06", "ED procedures across both components",
   "Encounters with a procedure, where the facility charge, the professional procedure code and modifier 25 interact.",
   "", 0.10, "Moderate-led", "C1 High error rate",
   "Procedure code selection, modifier 25 and 59 on the professional side, facility charge capture, bundling", ""),
  ("ESP-07", "Observation and admission decisions",
   "Encounters converting to observation or inpatient, where the two components diverge on what is reportable.",
   "", 0.06, "Complex-led", "C7 Denial trends",
   "Observation hour counting on the facility side, which professional code family applies, status determination", ""),
  ("ESP-08", "Facility and professional level divergence",
   "Encounters where the correct facility level and the correct professional level are legitimately different, because one is driven by resource use and the other by medical decision making.",
   "", 0.04, "Complex-led", "C6 Customer escalations",
   "Both level determinations on one record, why they diverge, documentation supporting each",
   "The reason single path is its own specialty rather than a view of the other two. A coder who assumes the two levels must match is the error this topic exists to find."),
 ]),
])

# ===================================================== validate the weights
for spec, (dim, cats) in TOPICS.items():
    total = 0.0
    for cat, parent, rows in cats:
        child = round(sum(t[4] for t in rows), 6)
        assert child == round(parent, 6), \
            "%s / %s: topics sum to %s, parent is %s" % (spec, cat, child, parent)
        total += child
    assert round(total, 6) == 1.0, "%s: categories sum to %s" % (spec, total)
    ids = [t[0] for cat, p, rows in cats for t in rows]
    assert len(ids) == len(set(ids)), "%s: duplicate topic id" % spec

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
