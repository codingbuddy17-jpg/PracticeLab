import { useState, useEffect, useRef } from 'react'
import { Download, Plus, Trash2, ChevronDown, ChevronUp, CheckCircle, Upload } from 'lucide-react'
import toast from 'react-hot-toast'
import { listEMAnswerKeys, upsertEMAnswerKey, deleteEMAnswerKey, downloadEMAnswerKeyTemplate, uploadEMAnswerKeys } from '../../api'
import { searchCharts, getAnswerKeyStatus, getChartsMissingKeys } from '../../api'
import { trainerName } from './shared'
import styles from './styles'

// ── MDM constants ─────────────────────────────────────────────────────────────

const COPA_FIELDS: { key: string; label: string; desc: string }[] = [
  { key: 'copa_self_limited', label: 'Self-limited / Minor Problem', desc: 'Runs a definite course; not likely to alter health status permanently' },
  { key: 'copa_stable_acute', label: 'Stable Acute Illness', desc: 'Recent problem with treatment initiated; patient improved but not fully resolved' },
  { key: 'copa_stable_chronic', label: 'Stable Chronic Illness', desc: 'Expected duration ≥1 year; patient at treatment goal' },
  { key: 'copa_acute_uncomplicated', label: 'Acute Uncomplicated Illness / Injury', desc: 'Short-term, low morbidity risk; full recovery expected' },
  { key: 'copa_chronic_exacerbation', label: 'Chronic Illness — Exacerbation / Progression / Treatment Side Effects', desc: 'Worsening chronic condition; not severe enough to threaten life/function' },
  { key: 'copa_undiagnosed_new', label: 'Undiagnosed New Problem — Uncertain Prognosis', desc: 'Differential diagnosis likely resulting in high morbidity risk without treatment' },
  { key: 'copa_acute_systemic', label: 'Acute Illness with Systemic Symptoms', desc: 'High risk of morbidity without treatment; affects multiple systems' },
  { key: 'copa_acute_complicated_injury', label: 'Acute Complicated Injury', desc: 'Requires evaluation beyond directly injured area; multiple treatment options' },
  { key: 'copa_chronic_severe', label: 'Chronic Illness — Severe Exacerbation', desc: 'Significant morbidity risk; may require escalation of care level' },
  { key: 'copa_threat_to_life', label: 'Acute / Chronic — Threat to Life or Bodily Function', desc: 'Poses a near-term threat to life or function without treatment (e.g., sepsis, MI, PE)' },
]

const DR_CAT1_FIELDS: { key: string; label: string }[] = [
  { key: 'dr_prior_external_notes', label: 'Review of prior external notes (per unique source)' },
  { key: 'dr_review_test_results', label: 'Review of test results (per unique test)' },
  { key: 'dr_order_tests', label: 'Ordering of tests (per unique test)' },
]

const DR_BOOL_FIELDS: { key: string; label: string; desc: string }[] = [
  { key: 'dr_independent_historian', label: 'Assessment requiring independent historian', desc: 'History from someone other than the patient (e.g., parent, spouse of impaired patient)' },
  { key: 'dr_independent_interpretation', label: 'Independent interpretation of test by another clinician', desc: 'Provider personally reviews diagnostic test and documents their own interpretation' },
  { key: 'dr_external_discussion', label: 'Discussion with external physician / appropriate source', desc: 'Discussion of management or test interpretation with external clinician/pharmacist/social worker' },
]

const RISK_FIELDS: { key: string; label: string; level: 'Low' | 'Moderate' | 'High' }[] = [
  { key: 'risk_low', label: 'Low-risk treatment / OTC management / minor procedure without identified risk factors', level: 'Low' },
  { key: 'risk_prescription_drug_mgmt', label: 'Prescription drug management', level: 'Moderate' },
  { key: 'risk_minor_surgery_with_factors', label: 'Minor surgery with identified patient/procedure risk factors', level: 'Moderate' },
  { key: 'risk_elective_major_no_factors', label: 'Elective major surgery without identified risk factors', level: 'Moderate' },
  { key: 'risk_hospitalization', label: 'Decision regarding hospitalization', level: 'Moderate' },
  { key: 'risk_sdoh', label: 'Diagnosis/treatment significantly limited by social determinants of health (SDOH)', level: 'Moderate' },
  { key: 'risk_drug_intensive_monitoring', label: 'Drug therapy requiring intensive monitoring for toxicity', level: 'High' },
  { key: 'risk_elective_major_with_factors', label: 'Elective major surgery with identified patient/procedure risk factors', level: 'High' },
  { key: 'risk_emergency_major_surgery', label: 'Emergency major surgery', level: 'High' },
  { key: 'risk_hospitalization_escalation', label: 'Decision regarding hospitalization or escalation of hospital-level care', level: 'High' },
  { key: 'risk_dnr_deescalate', label: 'Decision not to resuscitate / de-escalate care due to poor prognosis', level: 'High' },
  { key: 'risk_parenteral_controlled', label: 'Parenteral controlled substances (IV/IM/SQ)', level: 'High' },
]

const RISK_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  Low: { bg: '#f0fdf4', border: '#86efac', text: '#166534' },
  Moderate: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
  High: { bg: '#fff1f2', border: '#fca5a5', text: '#991b1b' },
}

import {
  EMCategory, EM_CATEGORY_LABELS, EM_CATEGORY_ORDER, EM_CODES_BY_CATEGORY,
  categoryUsesMdm, resolveCategory,
} from './emCategories'

// Codes with a CPT total-time band. ED visit codes have none.
const EM_TIME_ELIGIBLE = ['99202','99203','99204','99205','99212','99213','99214','99215']
const EM_CODES = ['99202','99203','99204','99205','99211','99212','99213','99214','99215','99281','99282','99283','99284','99285']

// ── Empty form state ──────────────────────────────────────────────────────────

function emptyForm() {
  const f: Record<string, any> = { em_code: '', em_modifier: '', patient_type: 'NA',
    level_method: 'MDM', total_time: '',
    // Blank means "work it out from the E/M code", which is what every key
    // written before categories existed says.
    em_category: '', critical_care_minutes: '',
    dx_codes: [''], procedure_cpts: [{ code: '', modifier: '', pointers: [], units: '' }] }
  COPA_FIELDS.forEach(c => { f[c.key] = 0 })
  DR_CAT1_FIELDS.forEach(c => { f[c.key] = 0 })
  DR_BOOL_FIELDS.forEach(c => { f[c.key] = false })
  RISK_FIELDS.forEach(c => { f[c.key] = false })
  f.copa_level_overridden = false; f.copa_level_override = ''
  f.dr_level_overridden = false; f.dr_level_override = ''
  f.risk_level_overridden = false; f.risk_level_override = ''
  return f
}

// ── Main component ────────────────────────────────────────────────────────────

export function EMAnswerKeysView() {
  const [akList, setAkList] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<Record<string, any>>(emptyForm())
  const [chartSearch, setChartSearch] = useState('')
  const [chartResults, setChartResults] = useState<any[]>([])
  const [selectedChart, setSelectedChart] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const [deleteDialog, setDeleteDialog] = useState<{ chartId: number; chartNumber: string } | null>(null)
  const [deletePassphrase, setDeletePassphrase] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [expandedSection, setExpandedSection] = useState<string>('copa')
  const [uploading, setUploading] = useState(false)
  const [uploadReplace, setUploadReplace] = useState(false)
  const [uploadPassphrase, setUploadPassphrase] = useState('')
  const [showUploadPassphrase, setShowUploadPassphrase] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  // Same coverage stats the IP/OP tab shows. E/M and ED Profee are both
  // MDM-graded, so each is counted separately rather than lumped together.
  const [statuses, setStatuses] = useState<Record<string, any>>({})
  // Mirrors the IP/OP tab: the work left to do, with a button per chart,
  // rather than making the trainer search for a chart number they have to
  // already know is unkeyed.
  const [missing, setMissing] = useState<any[]>([])

  useEffect(() => { loadList(); loadStatuses(); loadMissing() }, [])

  async function loadList() {
    setLoading(true)
    try { setAkList(await listEMAnswerKeys()) } catch { toast.error('Could not load E/M answer keys') }
    finally { setLoading(false) }
  }

  async function loadMissing() {
    const rows: any[] = []
    await Promise.all(['E/M', 'ED Profee'].map(async s => {
      try {
        const r = await getChartsMissingKeys(s)
        rows.push(...r.map((c: any) => ({ ...c, specialty: s })))
      } catch { /* leave absent */ }
    }))
    setMissing(rows)
  }

  async function loadStatuses() {
    const out: Record<string, any> = {}
    await Promise.all(['E/M', 'ED Profee'].map(async s => {
      try { out[s] = await getAnswerKeyStatus(s) } catch { /* leave absent */ }
    }))
    setStatuses(out)
  }

  async function searchChartsByNumber() {
    if (!chartSearch.trim()) return
    try {
      const res = await searchCharts({ q: chartSearch, specialty: 'E/M', page: 1, page_size: 10 })
      setChartResults(res.results || [])
    } catch { toast.error('Search failed') }
  }

  function setField(key: string, val: any) {
    setForm(f => ({ ...f, [key]: val }))
  }

  // What kind of encounter this key describes, and therefore which steps the
  // form shows. Falls back to the E/M code so a key saved before categories
  // existed opens on the category it always had.
  const category: EMCategory = resolveCategory(form.em_category, form.em_code)
  const mdm = categoryUsesMdm(category)
  const steps = [
    ...(mdm ? [
      { key: 'copa', label: 'COPA' },
      { key: 'dr', label: 'Data Review' },
      { key: 'risk', label: 'Risk' },
    ] : []),
    { key: 'dx', label: 'Dx Coding' },
    { key: 'em', label: 'E/M Code & CPT' },
  ]

  // A non-MDM category has no COPA step to sit on, so a form left open there
  // would render nothing at all.
  useEffect(() => {
    if (!steps.some(s => s.key === expandedSection)) setExpandedSection(steps[0].key)
  }, [category])

  function addDx() { setForm(f => ({ ...f, dx_codes: [...f.dx_codes, ''] })) }
  function removeDx(i: number) { setForm(f => ({ ...f, dx_codes: f.dx_codes.filter((_: any, idx: number) => idx !== i) })) }
  function setDx(i: number, val: string) { setForm(f => { const a = [...f.dx_codes]; a[i] = val; return { ...f, dx_codes: a } }) }

  function addCpt() { setForm(f => ({ ...f, procedure_cpts: [...f.procedure_cpts, { code: '', modifier: '', pointers: [], units: '' }] })) }
  function removeCpt(i: number) { setForm(f => ({ ...f, procedure_cpts: f.procedure_cpts.filter((_: any, idx: number) => idx !== i) })) }
  function setCpt(i: number, field: 'code' | 'modifier' | 'pointers' | 'units', val: any) {
    setForm(f => { const a = [...f.procedure_cpts]; a[i] = { ...a[i], [field]: val }; return { ...f, procedure_cpts: a } })
  }

  async function handleSave() {
    if (!selectedChart) { toast.error('Select a chart first'); return }
    if (!form.em_code) { toast.error('E/M code is required'); return }
    setSaving(true)
    try {
      const payload = {
        ...form,
        chart_id: selectedChart.id,
        dx_codes: form.dx_codes.filter((c: string) => c.trim()),
        // Dicts so pointers survive; the grader also accepts the legacy string form.
        procedure_cpts: form.procedure_cpts
          .filter((c: any) => c.code.trim())
          .map((c: any) => {
            const line: any = {
              code: c.code.trim(),
              modifier: (c.modifier || '').trim(),
              pointers: c.pointers || [],
            }
            // Blank stays blank: a key that says nothing about units does not
            // grade them, which is not the same as claiming 1.
            const u = parseInt(String(c.units ?? ''), 10)
            if (u >= 1) line.units = u
            return line
          }),
        // The form holds time as a string; the API expects an int or null.
        total_time: form.level_method === 'TIME' && form.total_time
          ? parseInt(form.total_time, 10) : null,
        em_category: category,
        critical_care_minutes: category === 'critical_care' && form.critical_care_minutes
          ? parseInt(form.critical_care_minutes, 10) : null,
        entered_by: trainerName(),
      }
      const res = await upsertEMAnswerKey(payload)
      toast.success(`Saved — COPA: ${res.copa_level}, Data Review: ${res.dr_level}, Risk: ${res.risk_level}`)
      setShowForm(false)
      setForm(emptyForm())
      setSelectedChart(null)
      // Refresh the coverage cards and drop the row that just got a key,
      // instead of leaving stale counts behind.
      loadStatuses()
      loadMissing()
      setChartSearch('')
      setChartResults([])
      loadList()
    } catch { toast.error('Save failed') }
    finally { setSaving(false) }
  }

  async function handleDelete() {
    if (!deleteDialog) return
    setDeleting(true)
    try {
      await deleteEMAnswerKey(deleteDialog.chartId, deletePassphrase)
      toast.success('Answer key deleted')
      setDeleteDialog(null)
      setDeletePassphrase('')
      loadList()
    } catch { toast.error('Delete failed — check passphrase') }
    finally { setDeleting(false) }
  }

  const toggle = (s: string) => setExpandedSection(v => v === s ? '' : s)

  const handleUploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    if (uploadReplace && !uploadPassphrase) {
      toast.error('Enter passphrase to replace existing keys')
      return
    }
    setUploading(true)
    try {
      const res = await uploadEMAnswerKeys(file, trainerName(), uploadReplace, uploadPassphrase)
      const parts = []
      if (res.stored.length) parts.push(`${res.stored.length} stored`)
      if (res.replaced.length) parts.push(`${res.replaced.length} replaced`)
      if (res.skipped_duplicates.length) parts.push(`${res.skipped_duplicates.length} skipped (duplicate)`)
      if (res.not_found.length) parts.push(`${res.not_found.length} not found`)
      toast.success(parts.join(', ') || 'No changes')
      loadList()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      setUploadPassphrase('')
      setShowUploadPassphrase(false)
      setUploadReplace(false)
    }
  }

  return (
    <div>
      {/* Coverage stats, matching the IP/OP tab. Split by specialty because both
          are MDM-graded but keyed and practised separately — and it makes
          "ED Profee has no charts yet" visible instead of silent. */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' as const }}>
        {['E/M', 'ED Profee'].map(spec => {
          const s = statuses[spec]
          if (!s) return null
          return (
            <div key={spec} style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: '10px 14px', minWidth: 240 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 8 }}>
                {spec}
              </div>
              {s.total_charts === 0 ? (
                <div style={{ fontSize: 12, color: '#9ca3af' }}>No charts uploaded yet</div>
              ) : (
                <div style={{ display: 'flex', gap: 20 }}>
                  <div>
                    <div style={styles.statValue}>{s.total_charts}</div>
                    <div style={styles.statLabel}>Total Charts</div>
                  </div>
                  <div>
                    <div style={{ ...styles.statValue, color: '#16a34a' }}>{s.with_answer_key}</div>
                    <div style={styles.statLabel}>Have Answer Key</div>
                  </div>
                  <div>
                    <div style={{ ...styles.statValue, color: '#dc2626' }}>{s.without_answer_key}</div>
                    <div style={styles.statLabel}>Missing Key</div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, color: '#374151' }}>
            E/M and ED Profee charts — MDM element-level answer keys.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button style={styles.outlineBtn} onClick={downloadEMAnswerKeyTemplate}>
            <Download size={14} /> Bulk Template
          </button>
          <button
            style={styles.outlineBtn}
            onClick={() => setShowUploadPassphrase(v => !v)}
            disabled={uploading}
          >
            <Upload size={14} /> {uploading ? 'Uploading…' : 'Upload Keys'}
          </button>
          <button style={styles.primaryBtn} onClick={() => { setShowForm(true); setExpandedSection('copa') }}>
            <Plus size={14} /> Add Answer Key
          </button>
          <input ref={fileRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleUploadFile} />
        </div>
      </div>

      {/* Upload panel */}
      {showUploadPassphrase && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: 14, marginBottom: 16, display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={uploadReplace} onChange={e => setUploadReplace(e.target.checked)} />
            Replace existing keys
          </label>
          {uploadReplace && (
            <input
              type="password" autoComplete="new-password"
              placeholder="Master passphrase"
              value={uploadPassphrase}
              onChange={e => setUploadPassphrase(e.target.value)}
              style={{ ...styles.input, width: 200, margin: 0 }}
            />
          )}
          <button style={styles.primaryBtn} onClick={() => fileRef.current?.click()} disabled={uploading}>
            <Upload size={13} /> Choose File & Upload
          </button>
          <button style={styles.outlineBtn} onClick={() => { setShowUploadPassphrase(false); setUploadReplace(false); setUploadPassphrase('') }}>
            Cancel
          </button>
        </div>
      )}

      {/* Entry Form */}
      {showForm && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, marginBottom: 20 }}>

          {/* Chart Search */}
          <div style={{ marginBottom: 16 }}>
            <label style={styles.label}>Chart</label>
            {selectedChart ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, color: '#1e3a5f', fontSize: 14 }}>{selectedChart.chart_number}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{selectedChart.category}</span>
                <button style={{ ...styles.outlineBtn, padding: '2px 8px', fontSize: 11 }} onClick={() => { setSelectedChart(null); setChartSearch('') }}>Change</button>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 8 }}>
                <input style={styles.input} placeholder="Search E/M chart number..." value={chartSearch}
                  onChange={e => setChartSearch(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') searchChartsByNumber() }} />
                <button style={styles.outlineBtn} onClick={searchChartsByNumber}>Search</button>
              </div>
            )}
            {chartResults.length > 0 && !selectedChart && (
              <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 4, background: '#fff', maxHeight: 160, overflowY: 'auto' }}>
                {chartResults.map(c => (
                  <div key={c.id} style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6' }}
                    onClick={() => { setSelectedChart(c); setChartResults([]) }}>
                    <strong>{c.chart_number}</strong> — {c.category} <span style={{ color: '#9ca3af' }}>{c.specialty}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* What kind of encounter this is, and therefore what this form asks
              for. Above the steps because it decides which steps exist. */}
          <div style={{ marginBottom: 14 }}>
            <label style={styles.label}>Encounter Category</label>
            <select style={styles.select} value={category}
              onChange={e => {
                const next = e.target.value as EMCategory
                // Drop a code that does not belong to the new category, rather
                // than leaving a 99214 sitting under "Preventive".
                const keep = next === 'other'
                  || EM_CODES_BY_CATEGORY[next].includes(form.em_code)
                setForm((f: any) => ({
                  ...f, em_category: next,
                  em_code: keep ? f.em_code : '',
                  critical_care_minutes: next === 'critical_care' ? f.critical_care_minutes : '',
                }))
              }}>
              {EM_CATEGORY_ORDER.map(c => (
                <option key={c} value={c}>{EM_CATEGORY_LABELS[c]}</option>
              ))}
            </select>
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 5 }}>
              {mdm
                ? 'Levelled by medical decision making — the COPA, Data Review and Risk steps apply.'
                : category === 'critical_care'
                  ? 'Levelled by total critical care time on the date of service. The MDM tables do not apply — this chart is scored in thirds: code and time, diagnoses, and procedures.'
                  : 'Levelled by the code itself, not by MDM. This key is graded on the E/M code, diagnoses and procedures, and the MDM weight folds into those.'}
            </div>
          </div>

          {/* Progress steps */}
          <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderRadius: 8, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
            {steps.map((s, i) => (
              <button key={s.key} onClick={() => toggle(s.key)}
                style={{ flex: 1, padding: '10px 4px', border: 'none', borderRight: i < steps.length - 1 ? '1px solid #e2e8f0' : 'none',
                  background: expandedSection === s.key ? '#1e3a5f' : '#fff',
                  color: expandedSection === s.key ? '#fff' : '#374151',
                  fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>
                {s.label}
              </button>
            ))}
          </div>

          {/* COPA Section */}
          {mdm && expandedSection === 'copa' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1e3a5f', marginBottom: 12 }}>
                Number & Complexity of Problems Addressed (COPA)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {COPA_FIELDS.map(f => (
                  <div key={f.key} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827', marginBottom: 4 }}>{f.label}</div>
                    <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8, lineHeight: 1.4 }}>{f.desc}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <button style={stepperBtn} onClick={() => setField(f.key, Math.max(0, (form[f.key] || 0) - 1))}>−</button>
                      <span style={{ minWidth: 24, textAlign: 'center', fontWeight: 700, fontSize: 16 }}>{form[f.key] || 0}</span>
                      <button style={stepperBtn} onClick={() => setField(f.key, Math.min(f.key === 'copa_threat_to_life' ? 1 : 9, (form[f.key] || 0) + 1))}>+</button>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12 }}>
                <label style={{ ...styles.label, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" checked={form.copa_level_overridden}
                    onChange={e => setField('copa_level_overridden', e.target.checked)} />
                  Override auto-derived COPA level
                </label>
                {form.copa_level_overridden && (
                  <select style={{ ...styles.select, marginTop: 6 }} value={form.copa_level_override}
                    onChange={e => setField('copa_level_override', e.target.value)}>
                    <option value="">Select level</option>
                    {['Minimal', 'Low', 'Moderate', 'High'].map(l => <option key={l}>{l}</option>)}
                  </select>
                )}
              </div>
            </div>
          )}

          {/* Data Review Section */}
          {mdm && expandedSection === 'dr' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1e3a5f', marginBottom: 12 }}>Data Review</div>

              <div style={{ border: '1px solid #bfdbfe', borderRadius: 8, padding: 14, background: '#eff6ff', marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#1d4ed8', marginBottom: 10 }}>
                  Category 1 — Tests, Documents & Historian
                  <span style={{ fontWeight: 400, color: '#3b82f6', marginLeft: 8 }}>
                    (2 items = Limited · 3 items = Moderate contribution)
                  </span>
                </div>
                {DR_CAT1_FIELDS.map(f => (
                  <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <span style={{ flex: 1, fontSize: 12, color: '#1e3a5f' }}>{f.label}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <button style={stepperBtn} onClick={() => setField(f.key, Math.max(0, (form[f.key] || 0) - 1))}>−</button>
                      <span style={{ minWidth: 20, textAlign: 'center', fontWeight: 700 }}>{form[f.key] || 0}</span>
                      <button style={stepperBtn} onClick={() => setField(f.key, (form[f.key] || 0) + 1)}>+</button>
                    </div>
                  </div>
                ))}
                {/* Independent historian is boolean but in Cat 1 */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 4 }}>
                  <input type="checkbox" id="dr_ih" checked={!!form.dr_independent_historian}
                    onChange={e => setField('dr_independent_historian', e.target.checked)} style={{ marginTop: 2 }} />
                  <label htmlFor="dr_ih" style={{ fontSize: 12, color: '#1e3a5f', cursor: 'pointer' }}>
                    Assessment requiring independent historian
                    <div style={{ fontSize: 11, color: '#6b7280' }}>History from someone other than the patient (counts as 1 Category 1 item)</div>
                  </label>
                </div>
              </div>

              {DR_BOOL_FIELDS.slice(1).map(f => (
                <div key={f.key} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, background: '#fff', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <input type="checkbox" id={f.key} checked={!!form[f.key]}
                      onChange={e => setField(f.key, e.target.checked)} style={{ marginTop: 2 }} />
                    <label htmlFor={f.key} style={{ cursor: 'pointer' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>{f.label}</div>
                      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{f.desc}</div>
                    </label>
                  </div>
                </div>
              ))}

              <div style={{ marginTop: 12 }}>
                <label style={{ ...styles.label, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" checked={form.dr_level_overridden}
                    onChange={e => setField('dr_level_overridden', e.target.checked)} />
                  Override auto-derived Data Review level
                </label>
                {form.dr_level_overridden && (
                  <select style={{ ...styles.select, marginTop: 6 }} value={form.dr_level_override}
                    onChange={e => setField('dr_level_override', e.target.value)}>
                    <option value="">Select level</option>
                    {['Minimal', 'Limited', 'Moderate', 'Extensive'].map(l => <option key={l}>{l}</option>)}
                  </select>
                )}
              </div>
            </div>
          )}

          {/* Risk Section */}
          {mdm && expandedSection === 'risk' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1e3a5f', marginBottom: 12 }}>
                Risk of Complications / Morbidity or Mortality
                <span style={{ fontWeight: 400, fontSize: 11, color: '#6b7280', marginLeft: 8 }}>Highest checked element determines level</span>
              </div>
              {(['Low', 'Moderate', 'High'] as const).map(level => (
                <div key={level} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: RISK_COLORS[level].text, background: RISK_COLORS[level].bg,
                    border: `1px solid ${RISK_COLORS[level].border}`, borderRadius: 6, padding: '4px 10px', marginBottom: 6, display: 'inline-block' }}>
                    {level} Risk
                  </div>
                  {RISK_FIELDS.filter(r => r.level === level).map(f => (
                    <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      background: form[f.key] ? RISK_COLORS[level].bg : '#fff',
                      border: `1px solid ${form[f.key] ? RISK_COLORS[level].border : '#e5e7eb'}`,
                      borderRadius: 8, marginBottom: 6, cursor: 'pointer', transition: 'background 0.1s' }}
                      onClick={() => setField(f.key, !form[f.key])}>
                      <input type="checkbox" checked={!!form[f.key]} onChange={() => {}} style={{ cursor: 'pointer' }} />
                      <span style={{ fontSize: 12, color: form[f.key] ? RISK_COLORS[level].text : '#374151' }}>{f.label}</span>
                    </div>
                  ))}
                </div>
              ))}
              <div style={{ marginTop: 8 }}>
                <label style={{ ...styles.label, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" checked={form.risk_level_overridden}
                    onChange={e => setField('risk_level_overridden', e.target.checked)} />
                  Override auto-derived Risk level
                </label>
                {form.risk_level_overridden && (
                  <select style={{ ...styles.select, marginTop: 6 }} value={form.risk_level_override}
                    onChange={e => setField('risk_level_override', e.target.value)}>
                    <option value="">Select level</option>
                    {['Minimal', 'Low', 'Moderate', 'High'].map(l => <option key={l}>{l}</option>)}
                  </select>
                )}
              </div>
            </div>
          )}

          {/* Dx Coding Section */}
          {expandedSection === 'dx' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1e3a5f', marginBottom: 12 }}>Diagnosis Coding (ICD-10-CM)</div>
              {form.dx_codes.map((code: string, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                  <input style={{ ...styles.input, flex: 1 }}
                    placeholder={i === 0 ? 'Primary Dx (e.g. E11.9)' : `Additional Dx ${i + 1}`}
                    value={code} onChange={e => setDx(i, e.target.value.toUpperCase())} />
                  {form.dx_codes.length > 1 && (
                    <button style={{ ...styles.outlineBtn, color: '#dc2626', borderColor: '#fca5a5', padding: '6px 10px' }}
                      onClick={() => removeDx(i)}><Trash2 size={13} /></button>
                  )}
                </div>
              ))}
              <button style={{ ...styles.outlineBtn, fontSize: 12 }} onClick={addDx}>+ Add Diagnosis Code</button>
            </div>
          )}

          {/* E/M Code & CPT Section */}
          {expandedSection === 'em' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1e3a5f', marginBottom: 12 }}>E/M Code & Procedure CPTs</div>
              <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
                <div style={{ flex: 1 }}>
                  <label style={styles.label}>E/M Code *</label>
                  {/* Free text for Other: the point of that category is codes
                      the app does not model, so a fixed list would exclude the
                      only codes it exists to carry. */}
                  {category === 'other' ? (
                    <input style={styles.input} placeholder="e.g. 99347" value={form.em_code}
                      onChange={e => setField('em_code', e.target.value.trim())} />
                  ) : (
                    <select style={styles.select} value={form.em_code} onChange={e => setField('em_code', e.target.value)}>
                      <option value="">Select E/M code</option>
                      {EM_CODES_BY_CATEGORY[category].map(c => <option key={c}>{c}</option>)}
                    </select>
                  )}
                </div>
                <div style={{ width: 120 }}>
                  <label style={styles.label}>Modifier</label>
                  <input style={styles.input} placeholder="e.g. 25" value={form.em_modifier}
                    onChange={e => setField('em_modifier', e.target.value)} />
                </div>
              </div>

              {/* Bulk Excel has carried these since patient type and time-based
                  levelling landed; without them a hand-built key silently
                  defaults to NA / MDM and cannot exercise either rule. */}
              {category === 'critical_care' && (
                <div style={{ marginBottom: 16 }}>
                  <label style={styles.label}>Total Critical Care Time (minutes) *</label>
                  <input style={{ ...styles.input, width: 160 }} inputMode="numeric"
                    placeholder="e.g. 75" value={form.critical_care_minutes}
                    onChange={e => setField('critical_care_minutes',
                      e.target.value.replace(/[^0-9]/g, '').slice(0, 4))} />
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 5 }}>
                    The coder's time is graded against this number and nothing else — no
                    threshold table is applied. It counts as part of the code: a coder who
                    picks the right code but misreads the clock earns half of that share.
                    Enter 99291 once and 99292 as many units as the encounter supports on
                    the CPT lines below.
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
                <div style={{ flex: 1 }}>
                  <label style={styles.label}>Patient Type</label>
                  <select style={styles.select} value={form.patient_type}
                    onChange={e => setField('patient_type', e.target.value)}>
                    <option value="NA">N/A — category has no New/Established split</option>
                    <option value="NEW">New</option>
                    <option value="ESTABLISHED">Established</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={styles.label}>Level By</label>
                  <select style={styles.select} value={form.level_method}
                    disabled={!EM_TIME_ELIGIBLE.includes(form.em_code)}
                    onChange={e => setField('level_method', e.target.value)}>
                    <option value="MDM">Medical Decision Making</option>
                    <option value="TIME">Total Time</option>
                  </select>
                  {!EM_TIME_ELIGIBLE.includes(form.em_code) && form.em_code && (
                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                      {form.em_code} cannot be levelled by time
                    </div>
                  )}
                </div>
                {form.level_method === 'TIME' && (
                  <div style={{ width: 140 }}>
                    <label style={styles.label}>Total Time (min)</label>
                    <input style={styles.input} placeholder="e.g. 35" inputMode="numeric"
                      value={form.total_time}
                      onChange={e => setField('total_time', e.target.value.replace(/[^0-9]/g, ''))} />
                  </div>
                )}
              </div>

              <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 8 }}>
                Procedure CPTs (if applicable)
              </div>
              {form.procedure_cpts.map((cpt: any, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                  <input style={{ ...styles.input, flex: 2 }} placeholder={`CPT Code ${i + 1}`}
                    value={cpt.code} onChange={e => setCpt(i, 'code', e.target.value)} />
                  <input style={{ ...styles.input, flex: 1 }} placeholder="Modifier"
                    value={cpt.modifier} onChange={e => setCpt(i, 'modifier', e.target.value)} />
                  <input style={{ ...styles.input, width: 74 }} placeholder="Units" inputMode="numeric"
                    title="Leave blank unless the count matters — a blank line is not graded on units."
                    value={cpt.units ?? ''}
                    onChange={e => setCpt(i, 'units' as any, e.target.value.replace(/[^0-9]/g, '').slice(0, 3))} />
                  <input style={{ ...styles.input, flex: 1, textTransform: 'uppercase' }} placeholder="Dx ptrs 1,2"
                    title="Which diagnoses justify this line. Up to 4 per line (CMS-1500 Box 24E) — choose the ones supporting medical necessity for this procedure. First is primary."
                    value={(cpt.pointers || []).join(',')}
                    onChange={e => setCpt(i, 'pointers', e.target.value.toUpperCase()
                      .replace(/[^0-9A-L,\s]/g, '').split(/[,\s]+/).filter(Boolean).slice(0, 4) as any)} />
                  <button style={{ ...styles.outlineBtn, color: '#dc2626', borderColor: '#fca5a5', padding: '6px 10px' }}
                    onClick={() => removeCpt(i)}><Trash2 size={13} /></button>
                </div>
              ))}
              {/* ED Profee and office E/M bill on a CMS-1500, so each line points
                  at the diagnoses justifying it. Letters index the Dx list above. */}
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4, marginBottom: 8 }}>
                Dx pointers: A = first diagnosis above, B = second, C = third… up to 4 per line, first is primary.
                Leave blank to skip pointer scoring for that line.
              </div>
              <button style={{ ...styles.outlineBtn, fontSize: 12 }} onClick={addCpt}>+ Add Procedure CPT</button>
            </div>
          )}

          {/* Form actions */}
          <div style={{ display: 'flex', gap: 10, marginTop: 16, paddingTop: 16, borderTop: '1px solid #e5e7eb' }}>
            <button style={saving ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
              onClick={handleSave} disabled={saving}>
              <CheckCircle size={14} /> {saving ? 'Saving...' : 'Save Answer Key'}
            </button>
            <button style={styles.outlineBtn} onClick={() => { setShowForm(false); setForm(emptyForm()); setSelectedChart(null); setChartSearch(''); setChartResults([]) }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Charts still needing a key — same shape and placement as the IP/OP tab,
          so a trainer moving between the two sees one layout, and can start a
          key from the chart rather than searching for it. */}
      {missing.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 8 }}>
            Charts without answer keys
            <span style={{ fontWeight: 400, color: '#9ca3af', marginLeft: 6 }}>({missing.length})</span>
          </div>
          <div style={styles.table}>
            <div style={{ ...styles.tableHeader, gridTemplateColumns: '130px 120px 1fr 100px' }}>
              <span>Chart</span><span>Specialty</span><span>Category</span><span></span>
            </div>
            {missing.map((c, i) => (
              <div key={c.chart_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                style={{ ...styles.tableRow, gridTemplateColumns: '130px 120px 1fr 100px' }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{c.chart_number}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{c.specialty}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{c.category || '—'}</span>
                <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    style={{ ...styles.outlineBtn, padding: '4px 10px', fontSize: 12 }}
                    title={`Create the E/M answer key for ${c.chart_number}`}
                    onClick={() => {
                      setSelectedChart({ id: c.chart_id, chart_number: c.chart_number,
                                         category: c.category, specialty: c.specialty })
                      setChartResults([])
                      setChartSearch(c.chart_number)
                      setForm(emptyForm())
                      setShowForm(true)
                      setExpandedSection('copa')
                    }}>
                    <Plus size={13} /> Key
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Answer Key List */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>Loading...</div>
      ) : akList.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af', fontSize: 14 }}>
          No E/M answer keys yet. Click "Add Answer Key" to enter the first one.
        </div>
      ) : (
        <div style={styles.table}>
          <div style={{ ...styles.tableHeader, gridTemplateColumns: '110px 1fr 80px 80px 80px 100px 80px 60px' }}>
            <div>Chart</div><div>Category</div>
            <div>COPA</div><div>Data Rev.</div><div>Risk</div>
            <div>E/M Code</div><div>Entered By</div><div></div>
          </div>
          {akList.map(row => (
            <div key={row.chart_id} style={{ ...styles.tableRow, gridTemplateColumns: '110px 1fr 80px 80px 80px 100px 80px 60px' }}>
              <div style={{ fontWeight: 700, color: '#1e3a5f' }}>{row.chart_number}</div>
              <div style={{ fontSize: 12, color: '#374151' }}>{row.category || '—'}</div>
              <div>
                <span style={{ ...levelBadge, ...levelColor(row.copa_level) }}>
                  {row.copa_level}{row.copa_level_overridden ? ' *' : ''}
                </span>
              </div>
              <div>
                <span style={{ ...levelBadge, ...levelColor(row.dr_level) }}>
                  {row.dr_level}{row.dr_level_overridden ? ' *' : ''}
                </span>
              </div>
              <div>
                <span style={{ ...levelBadge, ...levelColor(row.risk_level) }}>
                  {row.risk_level}{row.risk_level_overridden ? ' *' : ''}
                </span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{row.em_code}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>{row.entered_by}</div>
              <div>
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}
                  onClick={() => setDeleteDialog({ chartId: row.chart_id, chartNumber: row.chart_number })}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete dialog */}
      {deleteDialog && (
        <div style={overlay}>
          <div style={modal}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Delete E/M Answer Key — {deleteDialog.chartNumber}</div>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>Enter master passphrase to confirm deletion.</div>
            <input type="password" autoComplete="new-password" style={styles.input} placeholder="Master passphrase"
              value={deletePassphrase} onChange={e => setDeletePassphrase(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleDelete() }} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button style={{ ...styles.primaryBtn, background: '#dc2626' }} onClick={handleDelete} disabled={deleting}>
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
              <button style={styles.outlineBtn} onClick={() => { setDeleteDialog(null); setDeletePassphrase('') }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Local style helpers ───────────────────────────────────────────────────────

const stepperBtn: React.CSSProperties = {
  width: 28, height: 28, borderRadius: 6, border: '1px solid #d1d5db',
  background: '#fff', cursor: 'pointer', fontSize: 16, fontWeight: 700,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  color: '#374151',
}

const levelBadge: React.CSSProperties = {
  display: 'inline-block', fontSize: 10, fontWeight: 700,
  padding: '2px 6px', borderRadius: 4,
}

function levelColor(level: string): React.CSSProperties {
  const m: Record<string, React.CSSProperties> = {
    Minimal: { background: '#f3f4f6', color: '#374151' },
    Low: { background: '#f0fdf4', color: '#166534' },
    Limited: { background: '#f0fdf4', color: '#166534' },
    Moderate: { background: '#fffbeb', color: '#92400e' },
    Extensive: { background: '#fef3c7', color: '#78350f' },
    High: { background: '#fff1f2', color: '#991b1b' },
  }
  return m[level] || { background: '#f3f4f6', color: '#374151' }
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
}

const modal: React.CSSProperties = {
  background: '#fff', borderRadius: 12, padding: 24, minWidth: 340, maxWidth: 440,
  boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
}
