/**
 * Reads a chart's extracted page text the way a coder reads an EHR: as
 * DOCUMENTS (an H&P, three progress notes, a discharge summary) made of
 * SECTIONS (HPI, PMH, Medications, Assessment & Plan...).
 *
 * Pure — no React — so it can be measured on sample charts directly. The
 * version it replaces found 3 of 17 sections on a 3-page H&P, for three
 * reasons this one exists to fix:
 *   1. it kept only the FIRST heading on each page, so a page held at most one
 *      bookmark;
 *   2. it kept each label once per chart, so the second note's Assessment &
 *      Plan was invisible;
 *   3. "SOCIAL HISTORY: former smoker" — a heading with its content on the
 *      same line, the commonest way an EHR prints a short section — was read
 *      as a label/value field and never became a section.
 * It also called any line beginning "Plan..." or "Exam..." a heading.
 *
 * The rule now: a line is a heading only when it LOOKS like one — the whole
 * line is a known section name (optionally followed by a colon), or a known
 * name followed by a colon and content, or an ALL-CAPS line ending in a colon.
 * "Plan to discharge tomorrow" is none of those.
 */

// ── Vocabulary ────────────────────────────────────────────────────────────────

/** Document types: a line naming one starts a new document in the navigator. */
const DOC_TYPES: Array<{ type: string; endings: string[] }> = [
  { type: 'History & Physical', endings: ['history and physical', 'history & physical', 'h&p', 'admission note', 'admit note', 'admission history'] },
  { type: 'Progress Note', endings: ['progress note', 'daily progress note', 'progress notes', 'soap note'] },
  { type: 'Consult', endings: ['consultation', 'consult note', 'consultation note', 'consult', 'consultation report'] },
  { type: 'Operative Report', endings: ['operative report', 'operative note', 'op note', 'brief op note', 'brief operative note', 'surgical report'] },
  { type: 'Procedure Note', endings: ['procedure note', 'procedure report'] },
  { type: 'Discharge Summary', endings: ['discharge summary', 'death summary', 'transfer summary'] },
  { type: 'ED Note', endings: ['emergency department note', 'ed note', 'ed provider note', 'er note', 'emergency room note', 'emergency department record', 'ed physician note'] },
  { type: 'Radiology', endings: ['radiology report', 'imaging report'] },
  { type: 'Pathology', endings: ['pathology report', 'surgical pathology', 'surgical pathology report'] },
  { type: 'Lab Report', endings: ['laboratory report', 'lab report'] },
  { type: 'Nursing Note', endings: ['nursing note', 'nursing assessment', 'nursing progress note'] },
  { type: 'Anesthesia Record', endings: ['anesthesia record', 'anesthesia note', 'pre-anesthesia evaluation'] },
  { type: 'Orders / MAR', endings: ['physician orders', 'medication administration record', 'mar', 'orders'] },
]

/** Sections, each with the spellings EHRs actually print. */
const SECTIONS: Array<{ label: string; names: string[] }> = [
  { label: 'Chief Complaint', names: ['chief complaint', 'cc', 'reason for visit', 'reason for admission', 'presenting complaint', 'reason for consultation', 'reason for consult'] },
  { label: 'HPI', names: ['history of present illness', 'history of the present illness', 'hpi', 'present illness'] },
  { label: 'Interval History', names: ['interval history', 'interval events', 'overnight events', 'events overnight'] },
  { label: 'Subjective', names: ['subjective'] },
  { label: 'Objective', names: ['objective'] },
  { label: 'Past Medical History', names: ['past medical history', 'pmh', 'pmhx', 'medical history', 'past history'] },
  { label: 'Past Surgical History', names: ['past surgical history', 'psh', 'pshx', 'surgical history', 'prior surgeries'] },
  { label: 'Family History', names: ['family history', 'fh', 'fhx'] },
  { label: 'Social History', names: ['social history', 'sh', 'shx'] },
  { label: 'Medications', names: ['medications', 'medication', 'meds', 'home medications', 'home meds', 'current medications', 'medication list', 'outpatient medications', 'current outpatient medications', 'current outpatient prescriptions', 'medications on admission', 'prior to admission medications', 'inpatient medications', 'scheduled medications', 'active medications'] },
  { label: 'Discharge Medications', names: ['discharge medications', 'medications at discharge', 'discharge medication list', 'discharge meds'] },
  { label: 'Allergies', names: ['allergies', 'allergy', 'drug allergies', 'allergies and adverse reactions'] },
  { label: 'Review of Systems', names: ['review of systems', 'ros'] },
  { label: 'Vital Signs', names: ['vital signs', 'vitals', 'vs'] },
  { label: 'Physical Exam', names: ['physical exam', 'physical examination', 'exam', 'examination', 'pe'] },
  { label: 'Labs', names: ['labs', 'laboratory', 'laboratory data', 'lab results', 'laboratory results', 'pertinent labs', 'lab data', 'results'] },
  { label: 'Imaging / Studies', names: ['imaging', 'radiology', 'diagnostic imaging', 'studies', 'diagnostic studies', 'diagnostics', 'ekg', 'ecg', 'echocardiogram', 'echo'] },
  { label: 'Assessment & Plan', names: ['assessment and plan', 'assessment/plan', 'assessment & plan', 'a/p', 'a&p', 'impression and plan', 'impression/plan', 'assessment and recommendations', 'plan of care'] },
  { label: 'Assessment', names: ['assessment', 'clinical assessment'] },
  { label: 'Plan', names: ['plan', 'treatment plan'] },
  { label: 'Impression', names: ['impression', 'clinical impression', 'impressions'] },
  { label: 'Recommendations', names: ['recommendations', 'recommendation'] },
  { label: 'Problem List', names: ['problem list', 'active problems', 'active problem list', 'problems'] },
  { label: 'Diagnoses', names: ['diagnoses', 'diagnosis', 'final diagnosis', 'final diagnoses', 'admitting diagnosis', 'admission diagnosis', 'admitting diagnoses', 'principal diagnosis', 'primary diagnosis', 'secondary diagnoses', 'working diagnosis', 'differential diagnosis', 'differential'] },
  { label: 'Discharge Diagnoses', names: ['discharge diagnosis', 'discharge diagnoses'] },
  { label: 'Pre-op Diagnosis', names: ['preoperative diagnosis', 'pre-operative diagnosis', 'preop diagnosis', 'pre-op diagnosis', 'preoperative diagnoses'] },
  { label: 'Post-op Diagnosis', names: ['postoperative diagnosis', 'post-operative diagnosis', 'postop diagnosis', 'post-op diagnosis', 'postoperative diagnoses'] },
  { label: 'Procedure', names: ['procedure', 'procedures', 'procedure performed', 'procedures performed', 'operation', 'operation performed', 'operations performed', 'name of procedure', 'title of procedure'] },
  { label: 'Procedure Details', names: ['description of procedure', 'procedure in detail', 'details of procedure', 'procedure description', 'technique', 'description of operation', 'operative procedure'] },
  { label: 'Indications', names: ['indications', 'indication', 'indication for procedure', 'indications for procedure', 'indications for surgery'] },
  { label: 'Anesthesia', names: ['anesthesia', 'type of anesthesia'] },
  { label: 'Findings', names: ['findings', 'operative findings', 'intraoperative findings'] },
  { label: 'Specimens', names: ['specimens', 'specimen', 'specimens removed'] },
  { label: 'Estimated Blood Loss', names: ['estimated blood loss', 'ebl', 'blood loss'] },
  { label: 'Complications', names: ['complications'] },
  { label: 'Hospital Course', names: ['hospital course', 'brief hospital course', 'course in hospital', 'clinical course', 'hospital course by problem'] },
  { label: 'ED Course', names: ['ed course', 'emergency department course', 'er course', 'course in the ed', 'emergency room course'] },
  { label: 'Medical Decision Making', names: ['medical decision making', 'mdm'] },
  { label: 'Critical Care', names: ['critical care', 'critical care time', 'critical care note'] },
  { label: 'Disposition', names: ['disposition', 'condition at discharge', 'discharge condition', 'discharge disposition', 'condition on discharge'] },
  { label: 'Discharge Instructions', names: ['discharge instructions', 'patient instructions', 'follow up', 'follow-up', 'followup', 'follow up instructions'] },
  { label: 'Consults', names: ['consults', 'consultations', 'consultants'] },
  { label: 'Code Status', names: ['code status', 'advance directives', 'advanced directives'] },
  { label: 'Clinical History', names: ['clinical history', 'clinical information', 'clinical indication', 'history'] },
  { label: 'Gross Description', names: ['gross description', 'gross'] },
  { label: 'Microscopic', names: ['microscopic description', 'microscopic', 'microscopic diagnosis'] },
]

const SECTION_BY_NAME = new Map<string, string>()
for (const s of SECTIONS) for (const n of s.names) SECTION_BY_NAME.set(n, s.label)

const SIGNATURE = /^(electronically signed|e-signed|signed by|dictated by|authenticated by|attestation|attending attestation|transcribed by)\b/i

// ── Blocks ────────────────────────────────────────────────────────────────────

export type Block =
  | { kind: 'doc'; id: string; type: string; title: string }
  | { kind: 'heading'; id: string; label: string; title: string; inline: string }
  | { kind: 'field'; label: string; value: string }
  | { kind: 'list'; marker: string; text: string }
  | { kind: 'text'; text: string }
  | { kind: 'signature'; text: string }
  | { kind: 'gap' }

export interface ChartPageText { page: number; text: string; has_text: boolean }
export interface ParsedPage { page: number; has_text: boolean; blocks: Block[] }
export interface NavSection { id: string; label: string; title: string; page: number }
export interface NavDoc { id: string; type: string; title: string; page: number; sections: NavSection[] }
export interface ParsedChart { pages: ParsedPage[]; docs: NavDoc[]; sectionCount: number }

/** Lower-case, single-spaced, without trailing colon or leading outline marker. */
function norm(line: string) {
  return line.trim().replace(/\s+/g, ' ')
    .replace(/^([ivx]+|[a-z]|\d+)[.)]\s+(?=[a-z])/i, '')   // "I. HISTORY", "1) HPI"
    .replace(/[:\-–]\s*$/, '').trim().toLowerCase()
}

const isAllCaps = (s: string) => /[A-Z]/.test(s) && s === s.toUpperCase()
const SMALL = new Set(['and', 'of', 'the', 'in', 'on', 'at', 'for', 'to', 'by', 'with', 'a', 'an', '&'])
/** Every word capitalised, small connecting words aside — "Hospitalist Progress Note". */
const isTitleShape = (s: string) => s.trim().split(/\s+/)
  .filter(w => /^[A-Za-z]/.test(w) && !SMALL.has(w.toLowerCase()))
  .every(w => /^[A-Z]/.test(w))

function titleCase(s: string) {
  return s.toLowerCase().replace(/\b([a-z])/g, m => m.toUpperCase())
    .replace(/\b(And|Of|The|In|On|At|For|To|By|With)\b/g, m => m.toLowerCase())
}

/** A document title, e.g. "HOSPITALIST PROGRESS NOTE 03/12/2024". */
function docTypeFor(line: string): { type: string; title: string } | null {
  const raw = line.trim()
  if (raw.length > 70 || /:\s*\S/.test(raw)) return null          // has content: not a title
  const n = norm(raw).replace(/\s+(on|dated|date|dos)?\s*[\d/.-]{6,}.*$/, '')   // trailing date
  for (const d of DOC_TYPES) {
    for (const e of d.endings) {
      if (n === e || (n.endsWith(' ' + e) && n.split(' ').length <= e.split(' ').length + 3)) {
        // A title is shaped like one — ALL CAPS or Title Case. "Please see
        // progress note" ends in a document name and is a sentence. Single
        // words ("orders", "consult") need ALL CAPS: too common otherwise.
        if (!(isAllCaps(raw) || isTitleShape(raw))) return null
        if (n === e && e.split(' ').length === 1 && !isAllCaps(raw)) return null
        return { type: d.type, title: isAllCaps(raw) ? titleCase(raw.replace(/[:\s]+$/, '')) : raw.replace(/[:\s]+$/, '') }
      }
    }
  }
  return null
}

/** A section heading, standalone or with its content on the same line. */
function headingFor(line: string): { label: string; title: string; inline: string } | null {
  const raw = line.trim()
  if (!raw || raw.length > 120) return null
  // Heading with inline content: "SOCIAL HISTORY: former smoker"
  const m = raw.match(/^((?:[ivx]+|[a-z]|\d+)[.)]\s+)?([A-Za-z][A-Za-z /&()'-]{0,48}?)\s*:\s*(.*)$/)
  if (m) {
    const name = m[2].trim().replace(/\s+/g, ' ').toLowerCase()
    const label = SECTION_BY_NAME.get(name)
    if (label) return { label, title: m[2].trim(), inline: m[3].trim() }
    // An unknown ALL-CAPS name ending in a colon, alone on its line, is still a
    // heading — "HOSPITAL COURSE BY PROBLEM:" — and keeps its own wording.
    if (!m[3].trim() && isAllCaps(m[2]) && m[2].trim().split(' ').length <= 6 && m[2].trim().length >= 4) {
      return { label: titleCase(m[2].trim()), title: m[2].trim(), inline: '' }
    }
    return null
  }
  // Standalone: the WHOLE line is a known name. "Plan to discharge" is not.
  const label = SECTION_BY_NAME.get(norm(raw))
  if (label) {
    // Single short words ("exam", "plan", "pe") alone on a line are headings
    // only in heading shape, not when they are a sentence fragment.
    if (raw.length <= 3 && !isAllCaps(raw)) return null
    return { label, title: raw.replace(/[:\s]+$/, ''), inline: '' }
  }
  return null
}

const FIELD = /^([A-Za-z][A-Za-z0-9 /&().,'#-]{0,40}):\s*(.+)$/
const LIST = /^((?:\d{1,2}[.)])|[-•*▪●◦]|(?:[a-z][.)]))\s+(.+)$/

export function parseChart(pages: ChartPageText[]): ParsedChart {
  const docs: NavDoc[] = []
  let current: NavDoc | null = null
  let n = 0
  const out: ParsedPage[] = []

  const ensureDoc = (page: number) => {
    if (!current) {
      current = { id: `cv-doc-${n++}`, type: 'Document', title: 'Document', page, sections: [] }
      docs.push(current)
    }
    return current
  }

  for (const pg of pages) {
    const blocks: Block[] = []
    if (!pg.has_text) { out.push({ page: pg.page, has_text: false, blocks }); continue }
    let prevGap = false
    for (const rawLine of pg.text.replace(/\r\n/g, '\n').split('\n')) {
      const line = rawLine.trim()
      if (!line) {
        if (!prevGap && blocks.length) blocks.push({ kind: 'gap' })
        prevGap = true
        continue
      }
      prevGap = false

      const doc = docTypeFor(line)
      if (doc) {
        current = { id: `cv-doc-${n++}`, type: doc.type, title: doc.title, page: pg.page, sections: [] }
        docs.push(current)
        blocks.push({ kind: 'doc', id: current.id, type: doc.type, title: doc.title })
        continue
      }
      if (SIGNATURE.test(line)) { blocks.push({ kind: 'signature', text: line }); continue }

      const h = headingFor(line)
      if (h) {
        const id = `cv-sec-${n++}`
        ensureDoc(pg.page).sections.push({ id, label: h.label, title: h.title, page: pg.page })
        blocks.push({ kind: 'heading', id, label: h.label, title: h.title, inline: h.inline })
        continue
      }
      // A PDF breaks a sentence at its own line width. A line starting in lower
      // case continues the prose or list item just before it.
      const prev = blocks[blocks.length - 1]
      if (/^[a-z(]/.test(line) && prev && (prev.kind === 'text' || prev.kind === 'list')) {
        prev.text = `${prev.text} ${line}`
        continue
      }
      const list = line.match(LIST)
      if (list) { blocks.push({ kind: 'list', marker: list[1], text: list[2] }); continue }
      const field = line.match(FIELD)
      if (field && field[1].trim().split(/\s+/).length <= 5) {
        blocks.push({ kind: 'field', label: field[1].trim(), value: field[2].trim() })
        continue
      }
      blocks.push({ kind: 'text', text: line.replace(/\s{3,}/g, '  ') })
    }
    out.push({ page: pg.page, has_text: true, blocks })
  }
  const sectionCount = docs.reduce((a, d) => a + d.sections.length, 0)
  return { pages: out, docs: docs.filter(d => d.sections.length || d.type !== 'Document'), sectionCount }
}

// ── Coding aids ───────────────────────────────────────────────────────────────

/**
 * Wording a coder must notice. Generic language, never anything drawn from an
 * answer key, so highlighting it gives nothing away.
 *  - uncertain: inpatient guidelines code a condition documented as probable /
 *    suspected / rule out at discharge as if it were established.
 *  - linkage: the words that tie a condition to a cause.
 */
export const AID_PATTERNS = {
  uncertain: /\b(probable|probably|likely|suspected|suspect|suspicious for|possible|possibly|questionable|rule out|r\/o|consistent with|compatible with|indicative of|suggestive of|concern for|concerning for|cannot be ruled out|cannot be excluded|presumed|presumptive|working diagnosis)\b/gi,
  linkage: /\b(due to|secondary to|associated with|related to|caused by|in the setting of|attributed to|as a result of|resulting from|complicated by|manifested by)\b/gi,
}
