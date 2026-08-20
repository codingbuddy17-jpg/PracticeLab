import { useState, useEffect, useCallback, useRef } from 'react'
import { checkCpt, checkDx, checkModifier, checkPcs } from '../codeFormat'
import { useCodeDescriptions } from '../hooks/useCodeDescriptions'
import { CodeSuggest } from '../components/CodeSuggest'
import { useParams } from 'react-router-dom'
import { Flag, Save, ChevronRight, CheckCircle, AlertTriangle, Circle, Send, BookOpen, Plus, X, Info, Copy, Check } from 'lucide-react'
import {
  EMCategory, emCategory, categoryUsesMdm, EM_CATEGORY_LABELS, EM_CATEGORY_ORDER,
} from './practicelab/emCategories'
import api from '../api/client'

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChartInfo {
  chart_id: number
  chart_number: string
  specialty: string
  category: string
  difficulty: string
}

interface CodeEntry {
  chart_id: number
  pdx_code: string
  pdx_poa: string
  sdx: Array<{ code: string; poa: string }>
  pcs: Array<{ code: string }>
  cpt: Array<{ code: string; modifier: string; pointers?: string[]; units?: number | string }>
  facility_level?: string
  profee_level?: string
  // E&D fields
  ed_review: string
  ed_research: string
  ed_resolution: string
  ed_rationale: string
  flagged: boolean
  coder_notes: string
  // Inpatient only — the coder is saying the record cannot be coded as
  // documented. The query text goes in coder_notes, which becomes mandatory.
  query_flag: boolean
  // E/M MDM fields
  em_data?: {
    // COPA counts
    copa_self_limited: number
    copa_stable_chronic: number
    copa_stable_acute: number
    copa_acute_uncomplicated: number
    copa_chronic_exacerbation: number
    copa_undiagnosed_new: number
    copa_acute_systemic: number
    copa_acute_complicated_injury: number
    copa_threat_to_life: number
    copa_chronic_severe: number
    // Data Review
    dr_prior_external_notes: number
    dr_review_test_results: number
    dr_order_tests: number
    dr_independent_historian: boolean
    dr_independent_interpretation: boolean
    dr_external_discussion: boolean
    // Risk booleans
    risk_low: boolean
    risk_prescription_drug_mgmt: boolean
    risk_minor_surgery_with_factors: boolean
    risk_elective_major_no_factors: boolean
    risk_hospitalization: boolean
    risk_sdoh: boolean
    risk_drug_intensive_monitoring: boolean
    risk_elective_major_with_factors: boolean
    risk_emergency_major_surgery: boolean
    risk_hospitalization_escalation: boolean
    risk_dnr_deescalate: boolean
    risk_parenteral_controlled: boolean
    // E/M code + patient type + Dx + CPT
    em_code: string
    em_modifier: string
    em_category?: string
    critical_care_minutes?: number | string
    patient_type: 'NEW' | 'ESTABLISHED' | 'NA'
    level_method: 'MDM' | 'TIME'
    total_time: string
    em_dx: Array<{ code: string }>
    em_cpt: Array<{ code: string; modifier: string; pointers?: string[]; units?: number | string }>
  }
}

interface SessionData {
  session_id: number
  coder_name: string
  specialty: string
  status: string
  show_results: boolean
  charts: ChartInfo[]
  drafts: Record<number, Partial<CodeEntry>>
  results?: unknown[]
}

const POA_OPTIONS = [
  { value: 'Y', label: 'Y — Present at admission' },
  { value: 'N', label: 'N — Not present' },
  { value: 'W', label: 'W — Clinically undetermined' },
  { value: 'U', label: 'U — Documentation insufficient' },
  { value: '1', label: '1 — Exempt from POA' },
]


function isIP(specialty: string) {
  return specialty.toUpperCase().startsWith('IP')
}

function isED(specialty: string) {
  const sp = specialty.toUpperCase()
  return sp.includes('EDIT') || sp.includes('DENIAL')
}

function isEM(specialty: string) {
  const sp = specialty.toUpperCase()
  return sp === 'E/M' || sp.includes('E/M') || sp === 'ED PROFEE' || sp.includes('ED_PROFEE') || sp.includes('ED PROFEE')
}

// Professional claims (CMS-1500 / 837P) carry diagnosis pointers on every
// service line; facility claims (UB-04 / 837I) have none. Mirrors
// POINTER_SPECIALTIES in the backend's practicelab_pkg/shared.py.
function isSinglePath(specialty: string) {
  return specialty.toUpperCase().includes('SINGLE PATH')
}

function usesPointers(specialty: string) {
  const sp = specialty.toUpperCase()
  return sp.includes('SURGERY') || sp.includes('PROFEE') || sp.includes('E/M')
}

// Mirrors NO_UNITS_SPECIALTIES in practicelab_pkg/shared.py. IP-DRG codes
// procedures in ICD-10-PCS, Ancillary is diagnosis-only, and Edits/Denials are
// rubric-graded — a units box in any of them cannot score.
function usesUnits(specialty: string) {
  const sp = specialty.toUpperCase()
  return !(sp.includes('IP-DRG') || sp.includes('ANCILLARY')
    || sp.includes('EDITS') || sp.includes('DENIALS'))
}

/**
 * Parse "1,2" into ['1','2'] — max 4 per line, first is primary.
 *
 * Coders refer to diagnoses by NUMBER, in the order they are listed, so that
 * is what is asked for and stored. Letters are still accepted because keys
 * written before the switch used them and mean the same positions.
 */
/**
 * A shape warning under a code box. Never blocks: this checks that a code
 * looks like its kind, not that it exists, so an unusual-but-real code must
 * still go through. It exists to catch `J189` for `J18.9`, which otherwise
 * scores as a wrong answer and reads as a knowledge gap.
 *
 * Same rules as the auditor screen — one module, so the two cannot drift.
 */
/**
 * What the code the coder just typed actually says.
 *
 * Confirmation, not lookup. It appears once a code is complete enough to
 * resolve and says nothing otherwise, so it can tell someone they typed J18.0
 * when they meant J18.9 without ever telling them which code to pick — a
 * graded session measures whether they can find the code, and only prefix
 * completion is offered on that side of the line.
 *
 * ICD-10-CM, ICD-10-PCS and HCPCS Level II only; CPT descriptions are AMA
 * copyright and this app does not carry them.
 */
function CodeSays({ info }: { info: { description: string; short_description?: string | null } | null }) {
  if (!info) return null
  return (
    <div style={s.codeSays} title={info.description}>
      {info.description}
    </div>
  )
}

function CodeHint({ check }: { check: { ok: boolean; hint?: string } }) {
  if (check.ok) return null
  return (
    <div style={{ fontSize: 10.5, color: '#dc2626', fontWeight: 600, marginTop: 3, lineHeight: 1.3 }}>
      {check.hint}
    </div>
  )
}

function parsePointers(raw: string): string[] {
  return raw.toUpperCase()
    .split(/[,\s]+/)
    .map(t => {
      const n = parseInt(t, 10)
      if (!isNaN(n)) return n >= 1 && n <= 12 ? String(n) : ''
      return /^[A-L]$/.test(t) ? String(t.charCodeAt(0) - 64) : ''
    })
    .filter(Boolean)
    .slice(0, 4)
}

// The numbered Dx list a pointer refers to (Box 21 order).
function dxLabelList(codes: string[]) {
  return codes
    .map((code, i) => ({ letter: String(i + 1), code }))
    .filter(d => d.code && d.code.trim())
    .slice(0, 12)
}

const EMPTY_EM_DATA = () => ({
  copa_self_limited: 0, copa_stable_chronic: 0, copa_stable_acute: 0,
  copa_acute_uncomplicated: 0, copa_chronic_exacerbation: 0, copa_undiagnosed_new: 0,
  copa_acute_systemic: 0, copa_acute_complicated_injury: 0, copa_threat_to_life: 0, copa_chronic_severe: 0,
  dr_prior_external_notes: 0, dr_review_test_results: 0, dr_order_tests: 0,
  dr_independent_historian: false, dr_independent_interpretation: false, dr_external_discussion: false,
  risk_low: false, risk_prescription_drug_mgmt: false, risk_minor_surgery_with_factors: false,
  risk_elective_major_no_factors: false, risk_hospitalization: false, risk_sdoh: false,
  risk_drug_intensive_monitoring: false, risk_elective_major_with_factors: false,
  risk_emergency_major_surgery: false, risk_hospitalization_escalation: false,
  risk_dnr_deescalate: false, risk_parenteral_controlled: false,
  em_code: '', em_modifier: '', patient_type: 'NA' as 'NEW' | 'ESTABLISHED' | 'NA',
  // Office is the commonest encounter and the one the MDM tables were written
  // for, so it is the least surprising place to start.
  em_category: 'office' as string,
  critical_care_minutes: '' as number | string,
  level_method: 'MDM' as 'MDM' | 'TIME', total_time: '',
  em_dx: [] as Array<{ code: string }>, em_cpt: [] as Array<{ code: string; modifier: string; pointers?: string[]; units?: number | string }>,
})

const EMPTY_ENTRY = (chart_id: number): CodeEntry => ({
  chart_id,
  pdx_code: '',
  pdx_poa: '',
  sdx: [],
  pcs: [],
  cpt: [],
  facility_level: '',
  profee_level: '',
  ed_review: '',
  ed_research: '',
  ed_resolution: '',
  ed_rationale: '',
  flagged: false,
  coder_notes: '',
  query_flag: false,
  em_data: EMPTY_EM_DATA(),
})

// A raised physician query with no query written is not a submittable chart —
// the note field IS the query, so an empty one leaves the trainer nothing to
// review. Inpatient only; no other specialty shows the control.
function queryTextMissing(entry: CodeEntry | undefined, ip: boolean): boolean {
  return !!(ip && entry?.query_flag && !(entry.coder_notes || '').trim())
}

function chartStatus(entry: CodeEntry, ip: boolean, ed: boolean, em: boolean): 'complete' | 'partial' | 'empty' {
  if (em) {
    const d = entry.em_data
    if (!d) return 'empty'
    if (d.em_code) return 'complete'
    const hasAny = d.em_dx.length > 0 || Object.values(d).some(v => typeof v === 'number' && v > 0) || Object.values(d).some(v => v === true)
    return hasAny ? 'partial' : 'empty'
  }
  if (ed) {
    const hasAny = entry.ed_review.trim() || entry.ed_research.trim() || entry.ed_resolution.trim() || entry.ed_rationale.trim()
    if (!hasAny) return 'empty'
    const hasAll = entry.ed_review.trim() && entry.ed_research.trim() && entry.ed_resolution.trim() && entry.ed_rationale.trim()
    return hasAll ? 'complete' : 'partial'
  }
  if (!entry.pdx_code.trim()) return 'empty'
  if (ip) {
    const missingPOA = !entry.pdx_poa || entry.sdx.some(s => s.code.trim() && !s.poa)
    if (missingPOA) return 'partial'
  }
  return 'complete'
}

// ── Main Component ─────────────────────────────────────────────────────────────

export function PracticeSession() {
  const { token } = useParams<{ token: string }>()
  const [session, setSession] = useState<SessionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [entries, setEntries] = useState<Record<number, CodeEntry>>({})
  const [activeChartId, setActiveChartId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  // Unsaved edits on the chart currently open — everything else is auto-saved
  // when moving between charts.
  const [dirty, setDirty] = useState(false)
  const [exiting, setExiting] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [view, setView] = useState<'coding' | 'review' | 'submitted'>('coding')
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<{ show_results: boolean; results?: unknown[] } | null>(null)
  const [toast, setToast] = useState('')
  const toastTimer = useRef<ReturnType<typeof setTimeout>>()

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(''), 3000)
  }, [])

  // ── Load session ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) return
    api.get(`/practicelab/practice-sessions/by-token/${token}`).then(res => {
      const data = res.data as SessionData
      if (data.status === 'submitted') {
        setSubmitResult({ show_results: data.show_results, results: data.results })
        setView('submitted')
        setSession(data)
        setLoading(false)
        return
      }
      setSession(data)
      // Hydrate entries from drafts
      const initial: Record<number, CodeEntry> = {}
      for (const chart of data.charts) {
        const draft = data.drafts?.[chart.chart_id] as any
        const savedEm = draft?.em_data
        initial[chart.chart_id] = {
          chart_id: chart.chart_id,
          pdx_code: draft?.pdx_code || '',
          pdx_poa: draft?.pdx_poa || '',
          sdx: draft?.sdx || [],
          pcs: draft?.pcs || [],
          cpt: draft?.cpt || [],
          facility_level: draft?.facility_level || '',
          profee_level: draft?.profee_level || '',
          ed_review: draft?.ed_review || '',
          ed_research: draft?.ed_research || '',
          ed_resolution: draft?.ed_resolution || '',
          ed_rationale: draft?.ed_rationale || '',
          flagged: draft?.flagged || false,
          coder_notes: draft?.coder_notes || '',
          query_flag: draft?.query_flag || false,
          em_data: savedEm ? { ...EMPTY_EM_DATA(), ...savedEm } : EMPTY_EM_DATA(),
        }
      }
      setEntries(initial)
      setActiveChartId(data.charts[0]?.chart_id ?? null)
      setLoading(false)
    }).catch(e => {
      const err = e as { response?: { data?: { detail?: string } } }
      setError(err?.response?.data?.detail || 'Failed to load practice session')
      setLoading(false)
    })
  }, [token])

  const ip = session ? isIP(session.specialty) : false
  const ed = session ? isED(session.specialty) : false
  const em = session ? isEM(session.specialty) : false
  const activeEntry = activeChartId !== null ? entries[activeChartId] : null

  // ── Save draft ──────────────────────────────────────────────────────────────
  const saveDraft = useCallback(async (showMsg = false) => {
    if (!session) return
    setSaving(true)
    try {
      await api.post(`/practicelab/practice-sessions/${session.session_id}/save-draft`, {
        entries: Object.values(entries),
      })
      setDirty(false)
      if (showMsg) { setSaveMsg('Saved'); setTimeout(() => setSaveMsg(''), 2000) }
    } catch {
      // Was silent. A save that fails without saying so is the one case where
      // a coder loses work believing it is safe.
      showToast('Could not save — check your connection and try again')
    }
    setSaving(false)
  }, [session, entries])

  /**
   * Warn before closing with unsaved edits.
   *
   * Drafts auto-save when moving BETWEEN charts, so the only work at risk is
   * the chart currently open — which is exactly the chart someone is in the
   * middle of when they close the tab.
   */
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // ── Navigate between charts — auto-save on leave ───────────────────────────
  const navigateTo = useCallback((chartId: number) => {
    if (chartId === activeChartId) return
    saveDraft()
    setActiveChartId(chartId)
  }, [activeChartId, saveDraft])

  // ── Entry update helpers ────────────────────────────────────────────────────
  function updateEntry(chartId: number, patch: Partial<CodeEntry>) {
    setDirty(true)
    setEntries(prev => ({ ...prev, [chartId]: { ...prev[chartId], ...patch } }))
  }

  // ── Validate before Save button ─────────────────────────────────────────────
  function validateAndSave() {
    if (!activeEntry || !activeChartId) return
    if (!ed && !em && !activeEntry.pdx_code.trim()) {
      showToast(`${ip ? 'Principal' : 'First-Listed'} Diagnosis is required before saving this chart`)
      return
    }
    if (ip && (!activeEntry.pdx_poa || activeEntry.sdx.some(s => s.code.trim() && !s.poa))) {
      showToast('Some diagnoses are missing POA selection')
      return
    }
    saveDraft(true)
  }

  // ── Submit ──────────────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!session) return
    const missingQuery = session.charts.filter(c => queryTextMissing(entries[c.chart_id], ip))
    if (missingQuery.length > 0) {
      const first = missingQuery[0]
      showToast(`Write your query for ${first.chart_number} before submitting`)
      setActiveChartId(first.chart_id)
      setView('coding')
      return
    }
    setSubmitting(true)
    try {
      const res = await api.post(`/practicelab/practice-sessions/${session.session_id}/submit`, {
        entries: Object.values(entries),
      })
      setSubmitResult(res.data)
      setView('submitted')
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      showToast(err?.response?.data?.detail || 'Submission failed — try again')
    }
    setSubmitting(false)
  }

  // ── Render: loading / error ─────────────────────────────────────────────────
  if (loading) return <div style={s.center}><div style={s.spinner} /></div>
  if (error) return (
    <div style={s.center}>
      <div style={{ ...s.card, maxWidth: 420, textAlign: 'center', gap: 12 }}>
        <AlertTriangle size={32} color="#dc2626" />
        <div style={{ fontWeight: 700, fontSize: 16 }}>{error}</div>
      </div>
    </div>
  )
  if (!session) return null

  // ── Saved & exited ──────────────────────────────────────────────────────────
  // The token IS the way back in, so an exit screen that does not show it
  // leaves the coder holding a saved session they cannot reopen.
  if (exiting) return (
    <div style={s.center}>
      <div style={{ ...s.card, maxWidth: 480, textAlign: 'center', gap: 14 }}>
        <CheckCircle size={34} color="#059669" />
        <div style={{ fontWeight: 700, fontSize: 17 }}>Your work is saved</div>
        <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.6 }}>
          Nothing has been submitted yet. Open the same link again to carry on from
          where you stopped — every chart you had entered will still be there.
        </div>
        <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 3 }}>Your session token</div>
          <div style={{ fontFamily: 'monospace', fontSize: 15, fontWeight: 700, color: '#111' }}>{token}</div>
        </div>
        <button
          onClick={() => setExiting(false)}
          style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid #e5e7eb',
                   background: '#fff', color: '#4f46e5', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
        >
          Back to my charts
        </button>
      </div>
    </div>
  )

  // ── Submitted view ──────────────────────────────────────────────────────────
  if (view === 'submitted') {
    if (submitResult?.show_results && submitResult.results) {
      return <ResultsView results={submitResult.results as ReturnType<typeof _shapeResult>[]} coderName={session.coder_name} />
    }
    return (
      <div style={s.center}>
        <div style={{ ...s.card, maxWidth: 460, textAlign: 'center', gap: 16 }}>
          <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#d1fae5', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto' }}>
            <CheckCircle size={32} color="#059669" />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#111' }}>Submission Complete</div>
          <div style={{ fontSize: 14, color: '#6b7280', lineHeight: 1.6 }}>
            Your responses have been submitted successfully. Your trainer will review your coding and share feedback.
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af' }}>You may now close this window.</div>
        </div>
      </div>
    )
  }

  // ── Pre-submit review view ──────────────────────────────────────────────────
  if (view === 'review') {
    const charts = session.charts
    const complete = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed, em) === 'complete').length
    const partial = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed, em) === 'partial').length
    const empty = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed, em) === 'empty').length
    const flagged = charts.filter(c => entries[c.chart_id]?.flagged).length
    const queried = charts.filter(c => ip && entries[c.chart_id]?.query_flag).length
    const queryGaps = charts.filter(c => queryTextMissing(entries[c.chart_id], ip))

    return (
      <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 700, margin: '0 auto', padding: '32px 20px' }}>
        <div style={{ marginBottom: 24 }}>
          <button onClick={() => setView('coding')} style={s.backBtn}>← Back to coding</button>
        </div>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Review Before Submit</div>
        <div style={{ fontSize: 14, color: '#6b7280', marginBottom: 20 }}>
          {complete} chart{complete !== 1 ? 's' : ''} coded
          {flagged > 0 ? ` · ${flagged} flagged for review` : ''}
          {queried > 0 ? ` · ${queried} sent for physician query` : ''}
          {partial > 0 ? ` · ${partial} ${ed ? 'incomplete' : 'missing POA'}` : ''}
          {empty > 0 ? ` · ${empty} not started` : ''}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 28 }}>
          {charts.map(c => {
            const st = chartStatus(entries[c.chart_id], ip, ed, em)
            const fl = entries[c.chart_id]?.flagged
            const qGap = queryTextMissing(entries[c.chart_id], ip)
            const qOn = ip && entries[c.chart_id]?.query_flag
            return (
              <div key={c.chart_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: qGap ? '#fffafa' : '#fff', border: `1px solid ${qGap ? '#fecaca' : '#e5e7eb'}`, borderRadius: 10 }}>
                {st === 'complete' ? <CheckCircle size={16} color="#059669" /> : st === 'partial' ? <AlertTriangle size={16} color="#f59e0b" /> : <Circle size={16} color="#d1d5db" />}
                <span style={{ fontWeight: 600, fontSize: 14 }}>{c.chart_number}</span>
                <span style={{ fontSize: 13, color: '#6b7280', flex: 1 }}>{c.category}</span>
                {fl && <Flag size={13} color="#f59e0b" />}
                {qOn && !qGap && <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#fef3c7', color: '#b45309' }}>Query raised</span>}
                {qGap && <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#fee2e2', color: '#dc2626' }}>Query not written</span>}
                {st === 'empty' && <span style={{ fontSize: 12, color: '#9ca3af' }}>Not started</span>}
                {st === 'partial' && <span style={{ fontSize: 12, color: '#f59e0b' }}>{ed ? 'Incomplete' : 'Missing POA'}</span>}
                <button onClick={() => { setActiveChartId(c.chart_id); setView('coding') }} style={{ fontSize: 12, color: '#7c3aed', background: 'none', border: 'none', cursor: 'pointer' }}>Edit</button>
              </div>
            )
          })}
        </div>

        {queryGaps.length > 0 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 12,
                        padding: '12px 14px', borderRadius: 10, background: '#fef2f2', border: '1px solid #fecaca' }}>
            <AlertTriangle size={16} color="#dc2626" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ fontSize: 13, color: '#b91c1c', lineHeight: 1.5 }}>
              <strong>{queryGaps.length} chart{queryGaps.length !== 1 ? 's' : ''} sent for query with no query written.</strong>
              {' '}Open {queryGaps.map(c => c.chart_number).join(', ')} and write the question you would raise with the physician.
            </div>
          </div>
        )}
        <button
          onClick={handleSubmit}
          disabled={submitting || queryGaps.length > 0}
          style={{ ...s.submitBtn, opacity: submitting || queryGaps.length > 0 ? 0.5 : 1,
                   cursor: queryGaps.length > 0 ? 'not-allowed' : 'pointer' }}
        >
          <Send size={15} />
          {submitting ? 'Submitting…' : 'Submit All Charts'}
        </button>
        <div style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center', marginTop: 10 }}>
          Submissions cannot be edited after submit.
        </div>
      </div>
    )
  }

  // ── Coding view ─────────────────────────────────────────────────────────────
  const charts = session.charts

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', display: 'flex', minHeight: '100vh', background: '#f9fafb' }}>
      {/* Toast */}
      {toast && (
        <div style={s.toast}>{toast}</div>
      )}

      {/* Left panel — chart palette */}
      <div style={s.leftPanel}>
        <div style={{ padding: '14px 12px 10px', borderBottom: '1px solid #e5e7eb', background: 'linear-gradient(135deg, #f0fdf4, #eff6ff)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOpen size={16} color="#059669" />
            <span style={{ fontWeight: 800, fontSize: 13, color: '#111', flex: 1 }}>{session.coder_name}</span>
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2, marginLeft: 24 }}>{session.specialty}</div>
          {(() => {
            const done = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed, em) === 'complete').length
            const total = charts.length
            const pct = total ? Math.round((done / total) * 100) : 0
            return (
              <div style={{ marginTop: 10, marginLeft: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
                  <span>{done}/{total} charts coded</span>
                  <span style={{ fontWeight: 700, color: pct === 100 ? '#059669' : '#374151' }}>{pct}%</span>
                </div>
                <div style={{ height: 4, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: pct === 100 ? '#059669' : '#7c3aed', borderRadius: 4, transition: 'width 0.3s' }} />
                </div>
              </div>
            )
          })()}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {charts.map(c => {
            const st = chartStatus(entries[c.chart_id], ip, ed, em)
            const fl = entries[c.chart_id]?.flagged
            const active = c.chart_id === activeChartId
            return (
              <button
                key={c.chart_id}
                onClick={() => navigateTo(c.chart_id)}
                style={{
                  ...s.chartBtn,
                  background: active ? '#ede9fe' : '#fff',
                  borderLeft: active ? '3px solid #7c3aed' : '3px solid transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
                  {st === 'complete' ? <CheckCircle size={13} color="#059669" /> : st === 'partial' ? <AlertTriangle size={13} color="#f59e0b" /> : <Circle size={13} color="#d1d5db" />}
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1, textAlign: 'left' }}>{c.chart_number}</span>
                  {fl && <Flag size={12} color="#f59e0b" />}
                </div>
                <div style={{ fontSize: 11, color: '#6b7280', textAlign: 'left', marginTop: 2, paddingLeft: 19, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.category}</div>
              </button>
            )
          })}
        </div>

        <div style={{ padding: '12px', borderTop: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            onClick={() => { saveDraft(); setView('review') }}
            style={s.reviewBtn}
          >
            <ChevronRight size={14} /> Review & Submit
          </button>
          {/* Resume already worked — drafts save and the token rehydrates them.
              What was missing was any way to LEAVE, so a coder who had to stop
              could only close the tab and hope. */}
          <button
            onClick={async () => { await saveDraft(); setExiting(true) }}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '9px 12px', borderRadius: 8, border: '1px solid #e5e7eb',
              background: '#fff', color: '#6b7280', fontSize: 13, fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Save & Exit
          </button>
        </div>
      </div>

      {/* Right panel — code entry form */}
      <div style={s.rightPanel}>
        {activeEntry && activeChartId !== null ? (
          <CodeEntryForm
            key={activeChartId}
            chart={charts.find(c => c.chart_id === activeChartId)!}
            entry={activeEntry}
            ip={ip}
            ed={ed}
            em={em}
            onChange={patch => updateEntry(activeChartId, patch)}
            onSave={validateAndSave}
            saving={saving}
            saveMsg={saveMsg}
          />
        ) : (
          <div style={s.center}>Select a chart from the left panel.</div>
        )}
      </div>
    </div>
  )
}

// ── Code Entry Form ────────────────────────────────────────────────────────────

interface FormProps {
  chart: ChartInfo
  entry: CodeEntry
  ip: boolean
  ed: boolean
  em: boolean
  onChange: (patch: Partial<CodeEntry>) => void
  onSave: () => void
  saving: boolean
  saveMsg: string
}

function CodeEntryForm({ chart, entry, ip, ed, em, onChange, onSave, saving, saveMsg }: FormProps) {
  const [emOpenSections, setEmOpenSections] = useState({ copa: true, dr: false, risk: false, dx: false, code: false })
  // Coders work dual-screen: chart library on one, this form on the other.
  // Copying the chart number saves re-typing it into the library search.
  const [copied, setCopied] = useState(false)
  function copyChartNumber() {
    navigator.clipboard.writeText(chart.chart_number).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  function toggleSection(s: keyof typeof emOpenSections) {
    setEmOpenSections(prev => {
      const isOpen = prev[s]
      return { copa: false, dr: false, risk: false, dx: false, code: false, [s]: !isOpen }
    })
  }
  // One batched lookup for every code on the form. Dx and PCS resolve against
  // different systems, so they are asked separately rather than letting a
  // seven-character string match something in the wrong table.
  const emData = entry.em_data || EMPTY_EM_DATA()
  // E/M charts carry their diagnoses on em_data.em_dx, not entry.sdx — a
  // separate form path in the same component. Left out of this list, every
  // E/M diagnosis silently had no description while IP/OP had them.
  const describeDx = useCodeDescriptions(
    [entry.pdx_code, ...entry.sdx.map(r => r.code),
     ...emData.em_dx.map(r => r.code)], 'SDx')
  const describePcs = useCodeDescriptions(entry.pcs.map(r => r.code), 'PCS')
  // Procedure lines and their modifiers. AMA CPT is unlicensed and absent, so
  // most of these resolve to nothing; HCPCS Level II codes typed in the same
  // box DO resolve, and the modifier file is the only thing in the app that
  // explains a modifier. Asked apart because the two share a numeric shape.
  const describeCpt = useCodeDescriptions(
    [...entry.cpt.map(r => r.code),
     ...(entry.em_data?.em_cpt || []).map((r: any) => r.code)], 'CPT')
  const describeMod = useCodeDescriptions(
    [...entry.cpt, ...(entry.em_data?.em_cpt || [])].flatMap(
      (r: any) => String(r.modifier || '').split(/[,\s]+/).filter(Boolean)),
    'MODIFIER')
  const queryOn = ip && entry.query_flag
  const queryNoteMissing = queryOn && !entry.coder_notes.trim()
  // ED codes (99281-99285) cannot be levelled by time — MDM only.
  const timeEligible = !chart.specialty.toUpperCase().includes('ED PROFEE')
  const byTime = timeEligible && (emData.level_method || 'MDM') === 'TIME'
  // The coder states the category; it is not read off their code.
  //
  // Deriving it made the code the only signal, so a typo — 99219 for 99291 —
  // silently reshaped the form and nothing could warn about it, because there
  // was nothing for it to disagree WITH. Two independent statements make the
  // disagreement visible in both directions. It also stops the form thrashing
  // on every keystroke: "9", "99", "992" are all unrecognised, so the MDM
  // sections used to grey out and flip back while the coder was still typing.
  //
  // The key's own category is never consulted here — which kind of encounter
  // this is forms part of what the coder is being assessed on.
  const emCat: EMCategory = (emData.em_category as EMCategory) || 'office'
  const criticalCare = emCat === 'critical_care'
  const mdmApplies = categoryUsesMdm(emCat)
  const mdmOff = byTime || !mdmApplies
  // Ungraded: the code already carries the category, so scoring both would
  // charge a coder twice for one misreading. This warns and lets them through.
  const codeCat = emData.em_code ? emCategory(emData.em_code) : null
  const categoryMismatch = !!codeCat && codeCat !== emCat && codeCat !== 'other'
  function updateEM(patch: Partial<typeof emData>) {
    onChange({ em_data: { ...emData, ...patch } })
  }
  function updateSdx(idx: number, field: 'code' | 'poa', val: string) {
    const sdx = [...entry.sdx]
    sdx[idx] = { ...sdx[idx], [field]: val }
    onChange({ sdx })
  }
  function addSdx() { onChange({ sdx: [...entry.sdx, { code: '', poa: '' }] }) }
  function removeSdx(idx: number) { onChange({ sdx: entry.sdx.filter((_, i) => i !== idx) }) }

  function updatePcs(idx: number, val: string) {
    const pcs = [...entry.pcs]
    pcs[idx] = { code: val }
    onChange({ pcs })
  }
  function addPcs() { onChange({ pcs: [...entry.pcs, { code: '' }] }) }
  function removePcs(idx: number) { onChange({ pcs: entry.pcs.filter((_, i) => i !== idx) }) }

  const pointers = usesPointers(chart.specialty)
  const singlePath = isSinglePath(chart.specialty)
  const units = usesUnits(chart.specialty)
  const dxLabels = dxLabelList([entry.pdx_code, ...entry.sdx.map(sx => sx.code)])

  function updateCpt(idx: number, field: 'code' | 'modifier' | 'pointers' | 'units', val: string) {
    const cpt = [...entry.cpt]
    cpt[idx] = { ...cpt[idx], [field]: field === 'pointers' ? parsePointers(val) : val }
    onChange({ cpt })
  }
  function addCpt() { onChange({ cpt: [...entry.cpt, { code: '', modifier: '', pointers: [], units: '1' }] }) }
  function removeCpt(idx: number) { onChange({ cpt: entry.cpt.filter((_, i) => i !== idx) }) }

  const pdxPOAMissing = ip && entry.pdx_code.trim() && !entry.pdx_poa
  const sdxPOAMissing = ip ? entry.sdx.filter(s => s.code.trim() && !s.poa) : []

  return (
    <div style={{ padding: '24px 28px', maxWidth: 760, margin: '0 auto' }}>
      {/* Header card */}
      <div style={{ background: 'linear-gradient(135deg, #f0fdf4, #eff6ff)', border: '1px solid #d1fae5', borderRadius: 12, padding: '16px 20px', marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 20, fontWeight: 800, color: '#111', letterSpacing: -0.3 }}>{chart.chart_number}</span>
            <button
              onClick={copyChartNumber}
              title="Copy chart number"
              aria-label={`Copy chart number ${chart.chart_number}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: copied ? '#d1fae5' : 'none',
                border: '1px solid', borderColor: copied ? '#6ee7b7' : '#d1d5db',
                borderRadius: 6, cursor: 'pointer',
                color: copied ? '#065f46' : '#6b7280',
                padding: '3px 7px', fontSize: 11, fontWeight: 600,
                transition: 'all 0.15s',
              }}
            >
              {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <Chip label={chart.specialty} />
            {chart.category && <Chip label={chart.category} color="#065f46" bg="#d1fae5" />}
            {/* No difficulty chip. It is trainer metadata for matching work to a
                coder's level; shown to the coder it either excuses a poor
                result or seeds doubt about a good one. The server no longer
                sends it either. */}
          </div>
        </div>
        <button
          onClick={() => onChange({ flagged: !entry.flagged })}
          style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 8, border: entry.flagged ? '1.5px solid #f59e0b' : '1.5px solid #d1d5db', background: entry.flagged ? '#fef9c3' : '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: entry.flagged ? '#b45309' : '#6b7280', whiteSpace: 'nowrap' }}
        >
          <Flag size={14} />
          {entry.flagged ? 'Flagged' : 'Flag'}
        </button>
      </div>

      {/* ── E/M MDM form ── */}
      {em && (<>
        {/* Section tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
          {([
            { label: 'COPA',        key: 'copa', color: '#7c3aed', activeBg: '#f5f3ff' },
            { label: 'Data Review', key: 'dr',   color: '#0891b2', activeBg: '#f0f9ff' },
            { label: 'Risk',        key: 'risk',  color: '#dc2626', activeBg: '#fff1f2' },
            { label: 'E/M & CPT',  key: 'code',  color: '#d97706', activeBg: '#fffbeb' },
            { label: 'Dx Coding',  key: 'dx',    color: '#059669', activeBg: '#f0fdf4' },
          ] as const).map(({ label, key, color, activeBg }) => {
            const active = emOpenSections[key]
            return (
              <button key={key} onClick={() => toggleSection(key)} style={{
                flex: 1, padding: '6px 4px', fontSize: 11, fontWeight: 700, borderRadius: 6,
                border: active ? `1.5px solid ${color}` : '1.5px solid #e5e7eb',
                cursor: 'pointer',
                background: active ? activeBg : '#f9fafb',
                color: active ? color : '#9ca3af',
                transition: 'all 0.15s',
              }}>
                {label}
              </button>
            )
          })}
        </div>

        {/* ── Encounter category ──
            First decision on the chart, and the one that decides what the rest
            of this form asks for. The coder reads the note, recognises the kind
            of encounter, and then picks the code — so this sits above the code,
            in the order the work actually happens. */}
        <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 10, padding: '12px 14px', marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 8 }}>
            Encounter category
          </div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            {EM_CATEGORY_ORDER.map(c => (
              <label key={c} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
                <input
                  type="radio"
                  name={`em_category_${chart.chart_id}`}
                  checked={emCat === c}
                  /* Switching category never clears the MDM entries or the
                     clock — a coder changing their mind must not lose work. */
                  onChange={() => updateEM({ em_category: c })}
                />
                {EM_CATEGORY_LABELS[c]}
              </label>
            ))}
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>
            {mdmApplies
              ? 'Levelled by medical decision making — complete the COPA, Data Review and Risk sections.'
              : criticalCare
                ? 'Levelled by total critical care time, not by MDM. Enter the time below; the MDM sections are not scored for this chart.'
                : 'Levelled by the code itself, not by MDM. You are scored on the E/M code, diagnoses and procedures; the MDM sections are not scored for this chart.'}
          </div>
        </div>

        {/* ── Levelling method ──
            Since 2021 an office/outpatient visit may be levelled by MDM OR by
            total time on the date of encounter — the coder chooses, and the two
            can legitimately give different levels. ED codes have no time option,
            so this control is hidden there. */}
        {criticalCare && (
          <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 14px', marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#991b1b', marginBottom: 8 }}>
              Total critical care time
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                style={{ ...s.inputField, width: 110, marginBottom: 0 }}
                placeholder="e.g. 75"
                inputMode="numeric"
                value={emData.critical_care_minutes || ''}
                onChange={e => updateEM({
                  critical_care_minutes: e.target.value.replace(/[^0-9]/g, '').slice(0, 4),
                })}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>minutes on the date of service</span>
            </div>
            <div style={{ fontSize: 11, color: '#991b1b', marginTop: 8 }}>
              Report 99291 once for the initial period, then 99292 for each additional
              period — as separate lines or one line carrying units, whichever your
              guidelines use.
            </div>
          </div>
        )}

        {/* Only the MDM-levelled categories have a Time alternative at all.
            Offering "Level by MDM / Total Time" on a preventive visit asks the
            coder to choose between two routes neither of which applies. */}
        {timeEligible && mdmApplies && (
          <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 10, padding: '12px 14px', marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 8 }}>Level by</div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              {(['MDM', 'TIME'] as const).map(m => (
                <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
                  <input
                    type="radio"
                    name={`level_method_${chart.chart_id}`}
                    checked={(emData.level_method || 'MDM') === m}
                    /* Switching method never clears MDM entries — a coder
                       exploring both routes must not lose their work. */
                    onChange={() => updateEM({ level_method: m })}
                  />
                  {m === 'MDM' ? 'Medical Decision Making' : 'Total Time'}
                </label>
              ))}
              {byTime && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 4 }}>
                  <input
                    style={{ ...s.inputField, width: 90, marginBottom: 0 }}
                    placeholder="e.g. 40"
                    inputMode="numeric"
                    value={emData.total_time || ''}
                    onChange={e => updateEM({ total_time: e.target.value.replace(/[^0-9]/g, '') })}
                  />
                  <span style={{ fontSize: 12, color: '#6b7280' }}>minutes</span>
                </span>
              )}
            </div>
            {byTime && (
              <div style={{ fontSize: 11, color: '#b45309', marginTop: 8 }}>
                Levelling by time — the MDM sections below are not scored for this chart.
              </div>
            )}
          </div>
        )}

        {/* MDM sections are greyed rather than hidden: seeing what does not
            apply, and why, is part of the lesson. */}
        {/* The whole point of asking for the category separately: the code and
            the category are two independent statements, so they can disagree,
            and a disagreement is nearly always a typo. Warn, never block — a
            coder with a defensible reason keeps the last word. */}
        {categoryMismatch && (
          <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10,
            padding: '10px 14px', marginBottom: 12, fontSize: 12, color: '#92400e' }}>
            <strong>Check this before you submit.</strong> You selected{' '}
            <strong>{EM_CATEGORY_LABELS[emCat]}</strong>, but {emData.em_code} is
            a {EM_CATEGORY_LABELS[codeCat!].toLowerCase()} code. If the code is a typo, fix it;
            if you meant it, leave it — the category itself is not scored.
          </div>
        )}

        {/* MDM sections are greyed rather than hidden: seeing what does not
            apply, and why, is part of the lesson. */}
        <div style={mdmOff ? { opacity: 0.45, pointerEvents: 'none' as const } : undefined}
             aria-disabled={mdmOff}>

        {/* ── COPA ── */}
        <EMAccordion title="COPA — Number & Complexity of Problems" open={emOpenSections.copa} onToggle={() => toggleSection('copa')} accent="#7c3aed">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {([
              { key: 'copa_self_limited', label: 'Self-limited / minor', level: 'Minimal', color: '#059669' },
              { key: 'copa_stable_chronic', label: 'Stable, chronic illness', level: 'Low', color: '#0891b2' },
              { key: 'copa_stable_acute', label: 'Stable, acute illness ★', level: 'Low', color: '#0891b2' },
              { key: 'copa_acute_uncomplicated', label: 'Acute, uncomplicated illness/injury', level: 'Low', color: '#0891b2' },
              { key: 'copa_chronic_exacerbation', label: 'Chronic illness with exacerbation', level: 'Moderate', color: '#d97706' },
              { key: 'copa_undiagnosed_new', label: 'Undiagnosed new problem', level: 'Moderate', color: '#d97706' },
              { key: 'copa_acute_systemic', label: 'Acute illness with systemic symptoms', level: 'Moderate', color: '#d97706' },
              { key: 'copa_acute_complicated_injury', label: 'Acute, complicated injury', level: 'Moderate', color: '#d97706' },
              { key: 'copa_chronic_severe', label: 'Chronic illness, severe exacerbation', level: 'High', color: '#dc2626' },
              { key: 'copa_threat_to_life', label: 'Threat to life or bodily function', level: 'High', color: '#dc2626' },
            ] as Array<{ key: keyof typeof emData; label: string; level: string; color: string }>).map(item => (
              <div key={item.key} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#111', lineHeight: 1.3 }}>{item.label}</div>
                <span style={{ fontSize: 10, fontWeight: 700, color: item.color, background: `${item.color}15`, padding: '1px 6px', borderRadius: 4, alignSelf: 'flex-start' }}>{item.level}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <button onClick={() => updateEM({ [item.key]: Math.max(0, (emData[item.key] as number) - 1) })} style={{ width: 28, height: 28, borderRadius: 6, border: '1.5px solid #d1d5db', background: '#f9fafb', cursor: 'pointer', fontSize: 16, fontWeight: 700, color: '#374151', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>−</button>
                  <span style={{ width: 28, textAlign: 'center', fontWeight: 800, fontSize: 16, color: (emData[item.key] as number) > 0 ? '#7c3aed' : '#9ca3af' }}>{emData[item.key] as number}</span>
                  <button onClick={() => updateEM({ [item.key]: (emData[item.key] as number) + 1 })} style={{ width: 28, height: 28, borderRadius: 6, border: '1.5px solid #7c3aed', background: '#f5f3ff', cursor: 'pointer', fontSize: 16, fontWeight: 700, color: '#7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>★ 2023 AMA addition · mark all that apply</div>
        </EMAccordion>

        {/* ── Data Review ── */}
        <EMAccordion title="Data Review — Amount and/or Complexity" open={emOpenSections.dr} onToggle={() => toggleSection('dr')} accent="#0891b2">
          <div style={{ border: '1px solid #bae6fd', borderRadius: 8, padding: 12, marginBottom: 10, background: '#f0f9ff' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#0e7490', marginBottom: 8 }}>Category 1 — Tests, Documents, Orders</div>
            {([
              { key: 'dr_order_tests', label: 'Tests ordered' },
              { key: 'dr_review_test_results', label: 'Test results reviewed' },
              { key: 'dr_prior_external_notes', label: 'Prior external notes reviewed' },
            ] as Array<{ key: keyof typeof emData; label: string }>).map(item => (
              <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <button onClick={() => updateEM({ [item.key]: Math.max(0, (emData[item.key] as number) - 1) })} style={{ width: 24, height: 24, borderRadius: 5, border: '1.5px solid #bae6fd', background: '#fff', cursor: 'pointer', fontWeight: 700, color: '#0891b2' }}>−</button>
                <span style={{ width: 24, textAlign: 'center', fontWeight: 800, color: (emData[item.key] as number) > 0 ? '#0891b2' : '#9ca3af' }}>{emData[item.key] as number}</span>
                <button onClick={() => updateEM({ [item.key]: (emData[item.key] as number) + 1 })} style={{ width: 24, height: 24, borderRadius: 5, border: '1.5px solid #0891b2', background: '#e0f2fe', cursor: 'pointer', fontWeight: 700, color: '#0891b2' }}>+</button>
                <span style={{ fontSize: 13, color: '#0e7490' }}>{item.label}</span>
              </div>
            ))}
            <DrToggle label="Independent historian" value={emData.dr_independent_historian} onChange={v => updateEM({ dr_independent_historian: v })} color="#0891b2" />
          </div>
          <DrToggle label="Category 2 — Independent interpretation of test results" value={emData.dr_independent_interpretation} onChange={v => updateEM({ dr_independent_interpretation: v })} color="#7c3aed" />
          <DrToggle label="Category 3 — Discussion with treating/consulting provider" value={emData.dr_external_discussion} onChange={v => updateEM({ dr_external_discussion: v })} color="#059669" />
        </EMAccordion>

        {/* ── Risk ── */}
        <EMAccordion title="Risk — Risk of Complications, Morbidity, and/or Mortality" open={emOpenSections.risk} onToggle={() => toggleSection('risk')} accent="#dc2626">
          {/* Minimal is the implicit floor in the AMA table — it has no element of
              its own, it's what you get when nothing else applies. Say so, rather
              than leaving an unexplained gap where coders expect a Minimal row. */}
          <div style={{ marginBottom: 8, fontSize: 11, color: '#6b7280', fontStyle: 'italic' }}>
            Minimal risk — select nothing below.
          </div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#0891b2', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Low Risk</div>
            <RiskChip label="Minor/OTC medications only; lab tests; X-rays; limited ultrasound" field="risk_low" value={emData.risk_low} onChange={v => updateEM({ risk_low: v })} level="Low" />
          </div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#d97706', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Moderate Risk</div>
            {([
              { field: 'risk_prescription_drug_mgmt', label: 'Prescription drug management' },
              { field: 'risk_minor_surgery_with_factors', label: 'Minor surgery with identified risk factors' },
              { field: 'risk_elective_major_no_factors', label: 'Elective major surgery without identified risk factors' },
              { field: 'risk_hospitalization', label: 'Decision regarding hospitalization' },
              { field: 'risk_sdoh', label: 'Social determinants of health (SDOH)' },
            ] as Array<{ field: keyof typeof emData; label: string }>).map(item => (
              <RiskChip key={item.field} label={item.label} field={item.field} value={emData[item.field] as boolean} onChange={v => updateEM({ [item.field]: v })} level="Moderate" />
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#dc2626', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>High Risk</div>
            {([
              { field: 'risk_drug_intensive_monitoring', label: 'Drug therapy requiring intensive monitoring for toxicity' },
              { field: 'risk_elective_major_with_factors', label: 'Elective major surgery with identified risk factors' },
              { field: 'risk_emergency_major_surgery', label: 'Emergency major surgery' },
              { field: 'risk_hospitalization_escalation', label: 'Hospitalization or escalation of care' },
              { field: 'risk_dnr_deescalate', label: 'Decision not to resuscitate or de-escalate care ★' },
              { field: 'risk_parenteral_controlled', label: 'Parenteral controlled substances ★' },
            ] as Array<{ field: keyof typeof emData; label: string }>).map(item => (
              <RiskChip key={item.field} label={item.label} field={item.field} value={emData[item.field] as boolean} onChange={v => updateEM({ [item.field]: v })} level="High" />
            ))}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>★ 2023 AMA addition · highest element present determines Risk level</div>
        </EMAccordion>

        </div>{/* end MDM greyed wrapper */}

        {/* ── E/M Code & CPT ── */}
        <EMAccordion title="E/M Code, Modifier & Procedure CPTs" open={emOpenSections.code} onToggle={() => toggleSection('code')} accent="#d97706">
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>E/M Code</div>
              <input
                style={{ ...s.inputField, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 0.5 }}
                placeholder="e.g. 99214"
                value={emData.em_code}
                onChange={e => updateEM({ em_code: e.target.value })}
                maxLength={10}
              />
            </div>
            <div style={{ width: 120 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Modifier</div>
              <input
                style={{ ...s.inputField, marginBottom: 0 }}
                placeholder="e.g. 25"
                value={emData.em_modifier}
                onChange={e => updateEM({ em_modifier: e.target.value })}
                maxLength={10}
              />
            </div>
          </div>
          {/* Patient Type */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Patient Type</div>
            <div style={{ display: 'flex', gap: 16 }}>
              {(['NEW', 'ESTABLISHED', 'NA'] as const).map(pt => (
                <label key={pt} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
                  <input
                    type="radio"
                    name={`patient_type_${chart.chart_id}`}
                    value={pt}
                    checked={emData.patient_type === pt}
                    onChange={() => updateEM({ patient_type: pt })}
                  />
                  {pt === 'NA' ? 'N/A' : pt === 'NEW' ? 'New' : 'Established'}
                </label>
              ))}
            </div>
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Procedure CPTs (if applicable)</div>
          {pointers && dxLabelList(emData.em_dx.map(d => d.code)).length > 0 && (
            <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 12px', marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Diagnosis list (Box 21)</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {dxLabelList(emData.em_dx.map(d => d.code)).map(d => (
                  <span key={d.letter} style={{ fontSize: 12, fontFamily: 'monospace', background: '#fff', border: '1px solid #d1d5db', borderRadius: 5, padding: '2px 7px' }}>
                    <b>{d.letter}</b> {d.code}
                  </span>
                ))}
              </div>
            </div>
          )}
          {emData.em_cpt.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center',
                                  flexWrap: 'wrap', marginBottom: 6 }}>
              <CodeSuggest
                style={{ ...s.inputField, width: 120, marginBottom: 0 }}
                section="CPT"
                placeholder="e.g. 20610"
                value={row.code}
                onChange={v => {
                  const cpt = [...emData.em_cpt]
                  cpt[i] = { ...cpt[i], code: v }
                  updateEM({ em_cpt: cpt })
                }}
              />
              <CodeSuggest
                style={{ ...s.inputField, flex: 1, marginBottom: 0 }}
                section="MODIFIER"
                placeholder="Modifier e.g. 25"
                value={row.modifier}
                onChange={v => {
                  const cpt = [...emData.em_cpt]
                  cpt[i] = { ...cpt[i], modifier: v }
                  updateEM({ em_cpt: cpt })
                }}
              />
              <div style={{ flexBasis: '100%' }}>
                <CodeSays info={describeCpt(row.code)} />
                <CodeSays info={describeMod(row.modifier || '')} />
              </div>
              <input
                style={{ ...s.inputField, width: 74, marginBottom: 0 }}
                placeholder="Units"
                inputMode="numeric"
                title="How many units of this procedure. 1 unless the count differs."
                value={row.units ?? '1'}
                onChange={e => {
                  const cpt = [...emData.em_cpt]
                  cpt[i] = { ...cpt[i], units: e.target.value.replace(/[^0-9]/g, '').slice(0, 3) }
                  updateEM({ em_cpt: cpt })
                }}
              />
              {pointers && (
                <input
                  style={{ ...s.inputField, width: 120, marginBottom: 0, textTransform: 'uppercase' }}
                  placeholder="Dx ptrs 1,2"
                  title="Which diagnoses justify this line. Up to 4 per line (CMS-1500 Box 24E) — choose the ones supporting medical necessity for this procedure. First is primary."
                  value={(row.pointers || []).join(',')}
                  onChange={e => {
                    const cpt = [...emData.em_cpt]
                    cpt[i] = { ...cpt[i], pointers: parsePointers(e.target.value) }
                    updateEM({ em_cpt: cpt })
                  }}
                />
              )}
              <button onClick={() => updateEM({ em_cpt: emData.em_cpt.filter((_, j) => j !== i) })} style={s.removeBtn}><X size={14} /></button>
            </div>
          ))}
          <button onClick={() => updateEM({ em_cpt: [...emData.em_cpt, { code: '', modifier: '', pointers: [], units: '1' }] })} style={s.addBtn}><Plus size={13} /> Add Procedure CPT</button>
          <div style={s.hint}>
            Add any procedures performed during the visit that require separate CPT coding
            {pointers && ' · Dx pointers reference the diagnosis list above (A, B, C…), first is primary'}
          </div>
        </EMAccordion>

        {/* ── Dx Coding (last) ── */}
        <EMAccordion title="Dx Coding — ICD-10-CM Diagnoses" open={emOpenSections.dx} onToggle={() => toggleSection('dx')} accent="#059669">
          {emData.em_dx.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 6 }}>
              <div style={{ flex: 1 }}>
                <CodeSuggest
                  style={{ ...s.inputField, width: '100%', boxSizing: 'border-box', marginBottom: 0 }}
                  placeholder={i === 0 ? 'PDx — e.g. J18.9' : `Dx ${i + 1} — e.g. E11.9`}
                  section={i === 0 ? 'PDx' : 'SDx'}
                  value={row.code}
                  onChange={v => {
                    const dx = [...emData.em_dx]
                    dx[i] = { code: v.toUpperCase() }
                    updateEM({ em_dx: dx })
                  }}
                />
                <CodeSays info={describeDx(row.code)} />
              </div>
              <button onClick={() => updateEM({ em_dx: emData.em_dx.filter((_, j) => j !== i) })} style={{ ...s.removeBtn, marginTop: 6 }}><X size={14} /></button>
            </div>
          ))}
          <button onClick={() => updateEM({ em_dx: [...emData.em_dx, { code: '' }] })} style={s.addBtn}><Plus size={13} /> Add Diagnosis</button>
          <div style={s.hint}>ICD-10-CM · dot optional · list principal diagnosis first</div>
        </EMAccordion>
      </>)}

      {/* ── E&D form ── */}
      {ed && (<>
        <Section title="Review" required type="ed_review" step={1}>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="Summarise your review of the claim/denial — what was the original decision and why?"
            value={entry.ed_review}
            onChange={e => onChange({ ed_review: e.target.value })}
          />
        </Section>
        <Section title="Research" required type="ed_research" step={2}>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="What did you research? Include coding guidelines, payer rules, or nuances you found relevant."
            value={entry.ed_research}
            onChange={e => onChange({ ed_research: e.target.value })}
          />
        </Section>
        <Section title="Resolution" required type="ed_resolution" step={3}>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="What is your recommended resolution? (e.g. Uphold denial / Reverse / Partial reversal — and why)"
            value={entry.ed_resolution}
            onChange={e => onChange({ ed_resolution: e.target.value })}
          />
        </Section>
        <Section title="Final Rationale" required type="ed_rationale" step={4}>
          <textarea
            style={{ ...s.inputField, height: 110, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="Write your final supporting rationale — cite the specific guidelines, payer policies, or clinical documentation that supports your resolution."
            value={entry.ed_rationale}
            onChange={e => onChange({ ed_rationale: e.target.value })}
          />
        </Section>
      </>)}

      {/* ── IP / OP form ── */}
      {!ed && !em && <>

      {/* ED Single Path — both levels coded from the one chart. They frequently
          diverge, which is exactly the skill being trained, so they sit side by
          side and are scored independently. */}
      {singlePath && (
        <Section title="ED Levels — Facility & Professional" required type="procedure">
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Facility ED Level</div>
              <input
                style={{ ...s.inputField, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 0.5 }}
                placeholder="e.g. 99283"
                value={entry.facility_level || ''}
                onChange={e => onChange({ facility_level: e.target.value })}
                maxLength={10}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Professional ED Level</div>
              <input
                style={{ ...s.inputField, marginBottom: 0, fontFamily: 'monospace', letterSpacing: 0.5 }}
                placeholder="e.g. 99284"
                value={entry.profee_level || ''}
                onChange={e => onChange({ profee_level: e.target.value })}
                maxLength={10}
              />
            </div>
          </div>
          <div style={s.hint}>Both levels are scored separately — they need not match</div>
        </Section>
      )}

      {/* Principal Diagnosis */}
      <Section title={ip ? "Principal Diagnosis" : "First-Listed Diagnosis"} required type="diagnosis">
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <CodeSuggest
              style={{ ...s.inputField, width: '100%', boxSizing: 'border-box',
                       borderColor: pdxPOAMissing ? '#fca5a5' : '#e5e7eb' }}
              placeholder="e.g. J18.9"
              section="PDx"
              value={entry.pdx_code}
              onChange={v => onChange({ pdx_code: v })}
            />
            <CodeHint check={checkDx(entry.pdx_code)} />
            <CodeSays info={describeDx(entry.pdx_code)} />
            <div style={s.hint}>ICD-10-CM · dot optional</div>
          </div>
          {ip && (
            <div style={{ width: 200 }}>
              <select
                style={{ ...s.selectField, borderColor: pdxPOAMissing ? '#fca5a5' : '#e5e7eb' }}
                value={entry.pdx_poa}
                onChange={e => onChange({ pdx_poa: e.target.value })}
              >
                <option value="">POA…</option>
                {POA_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              {pdxPOAMissing && <div style={s.warningLine}><AlertTriangle size={11} color="#f59e0b" /> POA required</div>}
            </div>
          )}
        </div>
        {ip && (
          <div style={s.poaTooltip}>
            <Info size={11} color="#9ca3af" /> POA: Y=Present at admission · N=Not present · W=Clinically undetermined · U=Insufficient documentation · 1=Exempt
          </div>
        )}
      </Section>

      {/* Secondary Diagnoses */}
      <Section title={ip ? "Secondary Diagnoses" : "Additional Diagnoses"} type="diagnosis">
        {entry.sdx.map((row, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 8 }}>
            <div style={{ flex: 1 }}>
              <CodeSuggest
                style={{ ...s.inputField, marginBottom: 0, width: '100%', boxSizing: 'border-box' }}
                placeholder="e.g. E11.9"
                section="SDx"
                value={row.code}
                onChange={v => updateSdx(i, 'code', v)}
              />
              <CodeHint check={checkDx(row.code)} />
              <CodeSays info={describeDx(row.code)} />
            </div>
            {ip && (
              <select
                style={{ ...s.selectField, width: 180, marginBottom: 0, borderColor: row.code.trim() && !row.poa ? '#fca5a5' : '#e5e7eb' }}
                value={row.poa}
                onChange={e => updateSdx(i, 'poa', e.target.value)}
              >
                <option value="">POA…</option>
                {POA_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            )}
            <button onClick={() => removeSdx(i)} style={s.removeBtn}><X size={14} /></button>
          </div>
        ))}
        {sdxPOAMissing.length > 0 && (
          <div style={s.warningLine}><AlertTriangle size={11} color="#f59e0b" /> {sdxPOAMissing.length} secondary {sdxPOAMissing.length > 1 ? 'diagnoses' : 'diagnosis'} missing POA</div>
        )}
        <button onClick={addSdx} style={s.addBtn}><Plus size={13} /> {ip ? 'Add Secondary Diagnosis' : 'Add Additional Diagnosis'}</button>
        <div style={s.hint}>ICD-10-CM · dot optional</div>
      </Section>

      {/* PCS Procedures (IP only) */}
      {ip && (
        <Section title="PCS Procedures" type="procedure">
          {entry.pcs.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <CodeSuggest
                  style={{ ...s.inputField, width: '100%', boxSizing: 'border-box',
                           marginBottom: 0, fontFamily: 'monospace',
                           borderColor: checkPcs(row.code).ok ? '#e5e7eb' : '#dc2626' }}
                  placeholder="e.g. 0BHN3BZ"
                  section="PCS"
                  value={row.code}
                  onChange={v => updatePcs(i, v)}
                  maxLength={10}
                />
                <CodeSays info={describePcs(row.code)} />
                {/* A seven-character string that is not one of the combinations
                    the CMS tables define. This says the code does not EXIST —
                    a typo check, the same class as the shape check above it.
                    It never suggests what the right code is, and never blocks:
                    the tables may be a year old and the coder may be right. */}
                {describePcs.knownAbsent(row.code, 'ICD10PCS')
                  && checkPcs(row.code).ok && (
                  <div style={s.notACode}>
                    Not a valid PCS combination — check the characters
                  </div>
                )}
              </div>
              <button onClick={() => removePcs(i)} style={s.removeBtn}><X size={14} /></button>
            </div>
          ))}
          <button onClick={addPcs} style={s.addBtn}><Plus size={13} /> Add Procedure</button>
          <div style={s.hint}>7-character PCS · spaces optional</div>
        </Section>
      )}

      {/* CPT Procedures (OP only) */}
      {!ip && (
        <Section title="CPT Procedures" type="procedure">
          {/* Professional claims (CMS-1500) show the Dx list with its numbers,
              so the coder can see what each pointer letter refers to. */}
          {pointers && dxLabels.length > 0 && (
            <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 12px', marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Diagnosis list (Box 21)</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {dxLabels.map(d => (
                  <span key={d.letter} style={{ fontSize: 12, fontFamily: 'monospace', background: '#fff', border: '1px solid #d1d5db', borderRadius: 5, padding: '2px 7px' }}>
                    <b>{d.letter}</b> {d.code}
                  </span>
                ))}
              </div>
            </div>
          )}
          {entry.cpt.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center',
                                  flexWrap: 'wrap', marginBottom: 8 }}>
              <CodeSuggest
                style={{ ...s.inputField, width: 140, marginBottom: 0,
                         borderColor: checkCpt(row.code).ok ? '#e5e7eb' : '#dc2626' }}
                section="CPT"
                placeholder="e.g. 20610"
                value={row.code}
                onChange={v => updateCpt(i, 'code', v)}
              />
              <input
                style={{ ...s.inputField, flex: 1, marginBottom: 0,
                         borderColor: (row.modifier || '').split(/[,\s]+/).filter(Boolean)
                           .every((m: string) => checkModifier(m).ok) ? '#e5e7eb' : '#dc2626' }}
                placeholder="e.g. 25, 59"
                value={row.modifier}
                onChange={e => updateCpt(i, 'modifier', e.target.value)}
              />
              <div style={{ flexBasis: '100%' }}>
                <CodeSays info={describeCpt(row.code)} />
                {String(row.modifier || '').split(/[,\s]+/).filter(Boolean).map(m => (
                  <CodeSays key={m} info={describeMod(m)} />
                ))}
              </div>
              {units && (
                <input
                  style={{ ...s.inputField, width: 78, marginBottom: 0 }}
                  placeholder="Units"
                  inputMode="numeric"
                  title="How many units of this procedure. 1 unless the count differs."
                  value={row.units ?? '1'}
                  onChange={e => updateCpt(i, 'units', e.target.value.replace(/[^0-9]/g, '').slice(0, 3))}
                />
              )}
              {pointers && (
                <input
                  style={{ ...s.inputField, width: 130, marginBottom: 0, textTransform: 'uppercase' }}
                  placeholder="Dx ptrs 1,2"
                  title="Which diagnoses justify this line. Up to 4 per line (CMS-1500 Box 24E) — choose the ones supporting medical necessity for this procedure. First is primary."
                  value={(row.pointers || []).join(',')}
                  onChange={e => updateCpt(i, 'pointers', e.target.value)}
                />
              )}
              <button onClick={() => removeCpt(i)} style={s.removeBtn}><X size={14} /></button>
            </div>
          ))}
          <button onClick={addCpt} style={s.addBtn}><Plus size={13} /> Add CPT Code</button>
          <div style={s.hint}>
            5-digit CPT · append modifiers per guidelines where applicable
            {pointers && ' · Dx pointers: letters from the list above, up to 4, first is primary'}
          </div>
        </Section>
      )}
      </>}

      {/* Physician query — inpatient only, after the codes */}
      {ip && (
        <Section title="Physician Query" type="notes">
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 10 }}>
            Does this chart need to go for a physician query before it can be coded as documented?
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {[{ v: false, label: 'No' }, { v: true, label: 'Yes — send for query' }].map(o => {
              const on = entry.query_flag === o.v
              return (
                <button
                  key={String(o.v)}
                  onClick={() => onChange({ query_flag: o.v })}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '9px 16px',
                    borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
                    border: `1.5px solid ${on ? (o.v ? '#d97706' : '#059669') : '#e5e7eb'}`,
                    background: on ? (o.v ? '#fffbeb' : '#f0fdf4') : '#fff',
                    color: on ? (o.v ? '#b45309' : '#059669') : '#6b7280',
                  }}
                >
                  <span style={{
                    width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
                    border: `2px solid ${on ? (o.v ? '#d97706' : '#059669') : '#d1d5db'}`,
                    background: on ? (o.v ? '#d97706' : '#059669') : '#fff',
                    boxShadow: on ? 'inset 0 0 0 2px #fff' : 'none',
                  }} />
                  {o.label}
                </button>
              )
            })}
          </div>
          {entry.query_flag && (
            <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'flex-start',
                          padding: '10px 12px', borderRadius: 8,
                          background: queryNoteMissing ? '#fef2f2' : '#fffbeb',
                          border: `1px solid ${queryNoteMissing ? '#fecaca' : '#fde68a'}` }}>
              <AlertTriangle size={15} color={queryNoteMissing ? '#dc2626' : '#d97706'} style={{ flexShrink: 0, marginTop: 1 }} />
              <div style={{ fontSize: 12, color: queryNoteMissing ? '#b91c1c' : '#92400e', lineHeight: 1.5 }}>
                {queryNoteMissing
                  ? <><strong>Your query is required.</strong> Write the question you would put to the physician in the notes box below — this chart cannot be submitted until you do.</>
                  : <>Your query is recorded in the notes below and will be reviewed by your trainer.</>}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Notes — mandatory once a query is raised, because that box holds the query */}
      <Section
        title={queryOn ? 'Your Query to the Physician' : ed ? 'Additional Notes (Optional)' : 'Notes for Trainer (Optional)'}
        required={queryOn}
        type="notes"
      >
        <textarea
          style={{
            ...s.inputField, height: 72, resize: 'vertical', fontFamily: 'system-ui, sans-serif',
            ...(queryNoteMissing ? { borderColor: '#dc2626', background: '#fffafa' } : {}),
          }}
          placeholder={queryOn
            ? 'Write the query you would raise with the physician — what is unclear, and what you need clarified…'
            : 'Any questions or notes about this chart…'}
          value={entry.coder_notes}
          onChange={e => onChange({ coder_notes: e.target.value })}
        />
      </Section>

      {/* Save button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16, padding: '14px 16px', background: '#f9fafb', borderRadius: 10, border: '1px solid #e5e7eb' }}>
        <button
          onClick={onSave}
          disabled={saving}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 24px', background: 'linear-gradient(135deg, #059669, #0d9488)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, opacity: saving ? 0.7 : 1, boxShadow: '0 2px 8px rgba(5,150,105,0.25)' }}
        >
          <Save size={15} /> {saving ? 'Saving…' : 'Save Progress'}
        </button>
        {saveMsg
          ? <span style={{ fontSize: 13, color: '#059669', fontWeight: 600 }}>✓ {saveMsg}</span>
          : <span style={{ fontSize: 12, color: '#9ca3af' }}>Auto-saves as you type · use Save to confirm</span>
        }
      </div>
    </div>
  )
}

// ── Section wrapper ────────────────────────────────────────────────────────────

const SECTION_COLORS: Record<string, { accent: string; bg: string; label: string }> = {
  diagnosis:  { accent: '#2563eb', bg: '#eff6ff', label: '#1d4ed8' },
  procedure:  { accent: '#7c3aed', bg: '#f5f3ff', label: '#5b21b6' },
  notes:      { accent: '#6b7280', bg: '#f9fafb', label: '#374151' },
  ed_review:  { accent: '#0891b2', bg: '#ecfeff', label: '#0e7490' },
  ed_research:{ accent: '#7c3aed', bg: '#f5f3ff', label: '#5b21b6' },
  ed_resolution:{ accent: '#059669', bg: '#f0fdf4', label: '#065f46' },
  ed_rationale: { accent: '#dc2626', bg: '#fef2f2', label: '#991b1b' },
}

function Section({ title, required, children, type = 'notes', step }: {
  title: string; required?: boolean; children: React.ReactNode; type?: keyof typeof SECTION_COLORS; step?: number
}) {
  const c = SECTION_COLORS[type] || SECTION_COLORS.notes
  return (
    <div style={{ marginBottom: 20, background: c.bg, borderRadius: 10, border: `1px solid ${c.accent}22`, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderLeft: `4px solid ${c.accent}`, background: `${c.accent}0d` }}>
        {step !== undefined && (
          <span style={{ width: 22, height: 22, borderRadius: '50%', background: c.accent, color: '#fff', fontSize: 11, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{step}</span>
        )}
        <span style={{ fontSize: 13, fontWeight: 700, color: c.label }}>
          {title}{required && <span style={{ color: '#dc2626', marginLeft: 4 }}>*</span>}
        </span>
      </div>
      <div style={{ padding: '12px 14px' }}>{children}</div>
    </div>
  )
}

function Chip({ label, color = '#4f46e5', bg = '#ede9fe' }: { label: string; color?: string; bg?: string }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 600, background: bg, color, borderRadius: 6, padding: '2px 8px' }}>{label}</span>
  )
}

// ── E/M helper components ──────────────────────────────────────────────────────

function EMAccordion({ title, open, onToggle, accent, children }: {
  title: string; open: boolean; onToggle: () => void; accent: string; children: React.ReactNode
}) {
  return (
    <div style={{ marginBottom: 14, border: `1px solid ${accent}33`, borderRadius: 10, overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: `${accent}0d`, borderLeft: `4px solid ${accent}`, border: 'none', cursor: 'pointer', textAlign: 'left' }}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: accent, flex: 1 }}>{title}</span>
        <span style={{ fontSize: 16, color: accent, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▾</span>
      </button>
      {open && <div style={{ padding: '12px 14px' }}>{children}</div>}
    </div>
  )
}

function DrToggle({ label, value, onChange, color }: { label: string; value: boolean; onChange: (v: boolean) => void; color: string }) {
  return (
    <div
      onClick={() => onChange(!value)}
      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 8, border: `1.5px solid ${value ? color : '#e5e7eb'}`, background: value ? `${color}0d` : '#fff', cursor: 'pointer', marginBottom: 6 }}
    >
      <div style={{ width: 18, height: 18, borderRadius: 4, border: `2px solid ${value ? color : '#d1d5db'}`, background: value ? color : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {value && <span style={{ color: '#fff', fontSize: 12, fontWeight: 800, lineHeight: 1 }}>✓</span>}
      </div>
      <span style={{ fontSize: 13, color: value ? color : '#374151', fontWeight: value ? 600 : 400 }}>{label}</span>
    </div>
  )
}

const RISK_LEVEL_COLORS = { Minimal: { bg: '#d1fae5', text: '#059669' }, Low: { bg: '#cffafe', text: '#0891b2' }, Moderate: { bg: '#fef3c7', text: '#d97706' }, High: { bg: '#fee2e2', text: '#dc2626' } }

function RiskChip({ label, field: _field, value, onChange, level }: { label: string; field: string; value: boolean; onChange: (v: boolean) => void; level: 'Minimal' | 'Low' | 'Moderate' | 'High' }) {
  const c = RISK_LEVEL_COLORS[level]
  return (
    <div
      onClick={() => onChange(!value)}
      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderRadius: 8, border: `1.5px solid ${value ? c.text : '#e5e7eb'}`, background: value ? c.bg : '#fff', cursor: 'pointer', marginBottom: 5 }}
    >
      <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${value ? c.text : '#d1d5db'}`, background: value ? c.text : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {value && <span style={{ color: '#fff', fontSize: 10, fontWeight: 800, lineHeight: 1 }}>✓</span>}
      </div>
      <span style={{ fontSize: 12, color: value ? c.text : '#374151', fontWeight: value ? 600 : 400, flex: 1 }}>{label}</span>
      <span style={{ fontSize: 10, fontWeight: 700, color: c.text, background: c.bg, border: `1px solid ${c.text}44`, borderRadius: 4, padding: '1px 5px', flexShrink: 0 }}>{level}</span>
    </div>
  )
}

// ── Results View ───────────────────────────────────────────────────────────────

interface ResultRow {
  chart_number: string
  specialty?: string
  total_score: number | null
  pass_fail: string | null
  pdx_submitted: string | null
  pdx_answer_key: string | null
  pdx_correct: boolean | null
  feedback: Array<{ section: string; issue: string; ak_code: string; coder_code: string }>
  flagged: boolean
}

function _shapeResult(r: unknown): ResultRow { return r as ResultRow }

// Parse E/M feedback into structured breakdown
function parseEMFeedback(feedback: ResultRow['feedback']) {
  const caItems = feedback.filter(f => f.section === 'Coding Accuracy')
  const raItems = feedback.filter(f => f.section === 'Reasoning Accuracy')
  const extractPts = (issue: string) => {
    const m = issue.match(/([\d.]+)\s*\/?\s*[\d.]*\s*pts/)
    return m ? parseFloat(m[1]) : null
  }
  // Match on the row's label, never on position. Mismatch rows (patient type,
  // levelling method) are prepended to their section, which used to shift every
  // subsequent row — the patient-type row rendered as "E/M Level", E/M Level as
  // "CPT", and Dx disappeared. Label matching also repairs already-stored results.
  const find = (items: typeof caItems, prefix: string) =>
    items.find(f => f.issue.trim().toUpperCase().startsWith(prefix.toUpperCase()))
  const pick = (items: typeof caItems, prefix: string) => {
    const f = find(items, prefix)
    return f ? { pts: extractPts(f.issue), ak: f.ak_code, sub: f.coder_code } : null
  }
  return {
    em_level: pick(caItems, 'E/M Level'),
    cpt:      pick(caItems, 'CPT:'),
    dx:       pick(caItems, 'Dx:'),
    copa:     pick(raItems, 'COPA'),
    dr:       pick(raItems, 'Data Review'),
    risk:     pick(raItems, 'Risk'),
    ca_total: caItems.reduce((s, f) => s + (extractPts(f.issue) ?? 0), 0),
    ra_total: raItems.reduce((s, f) => s + (extractPts(f.issue) ?? 0), 0),
    // What each line was worth on THIS chart. A chart with no reasoning
    // component — a preventive visit — scores its coding out of the full 100,
    // because the reasoning weight folds into it. Without the denominator the
    // subtotal reads as a percentage and understates the coder badly.
    ca_max: raItems.length ? 70 : 100,
    ra_max: raItems.length ? 30 : 0,
  }
}

function EMResultCard({ r }: { r: ResultRow }) {
  const em = parseEMFeedback(r.feedback || [])
  const levelMatch = em.em_level?.ak && em.em_level?.sub && em.em_level.ak === em.em_level.sub
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 18px' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{r.chart_number}</span>
        {r.total_score !== null && (
          <span style={{ fontSize: 16, fontWeight: 800, color: (r.total_score ?? 0) >= 80 ? '#059669' : '#dc2626' }}>{r.total_score?.toFixed(1)}%</span>
        )}
        <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 10px', borderRadius: 6, background: r.pass_fail === 'PASS' ? '#d1fae5' : '#fee2e2', color: r.pass_fail === 'PASS' ? '#059669' : '#dc2626' }}>{r.pass_fail || '—'}</span>
        {r.flagged && <Flag size={13} color="#f59e0b" />}
      </div>
      {/* Two-panel accuracy breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {/* Coding Accuracy */}
        <div style={{ background: '#f5f3ff', border: '1px solid #ddd6fe', borderRadius: 8, padding: '10px 12px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#5b21b6', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Coding Accuracy — {em.ca_total.toFixed(1)} of {em.ca_max ?? 70} pts
          </div>
          <EMScoreLine label="E/M Level" pts={em.em_level?.pts} ak={em.em_level?.ak} sub={em.em_level?.sub} isMatch={levelMatch === null ? null : !!levelMatch} />
          <EMScoreLine label="CPT" pts={em.cpt?.pts} />
          <EMScoreLine label="Dx Coding" pts={em.dx?.pts} />
        </div>
        {/* Reasoning Accuracy */}
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '10px 12px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#065f46', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Reasoning Accuracy — {em.ra_total.toFixed(1)} of {em.ra_max ?? 30} pts
          </div>
          <EMScoreLine label="COPA" pts={em.copa?.pts} ak={em.copa?.ak} sub={em.copa?.sub} isMatch={em.copa?.ak === em.copa?.sub && !!em.copa?.ak} />
          <EMScoreLine label="Data Review" pts={em.dr?.pts} ak={em.dr?.ak} sub={em.dr?.sub} isMatch={em.dr?.ak === em.dr?.sub && !!em.dr?.ak} />
          <EMScoreLine label="Risk" pts={em.risk?.pts} ak={em.risk?.ak} sub={em.risk?.sub} isMatch={em.risk?.ak === em.risk?.sub && !!em.risk?.ak} />
        </div>
      </div>
    </div>
  )
}

function EMScoreLine({ label, pts, ak, sub, isMatch }: { label: string; pts: number | null | undefined; ak?: string; sub?: string; isMatch?: boolean | null }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
      {isMatch !== undefined && isMatch !== null && (
        <span style={{ fontSize: 12, flexShrink: 0 }}>{isMatch ? '✓' : '✗'}</span>
      )}
      <span style={{ fontSize: 12, color: '#374151', flex: 1 }}>{label}</span>
      {pts !== null && pts !== undefined && (
        <span style={{ fontSize: 12, fontWeight: 700, color: pts > 0 ? '#059669' : '#9ca3af' }}>{pts.toFixed(1)} pts</span>
      )}
      {ak && sub && ak !== sub && (
        <span style={{ fontSize: 10, color: '#dc2626', marginLeft: 2 }}>({sub} ≠ {ak})</span>
      )}
    </div>
  )
}

/**
 * One line of feedback, with what the codes on it actually say.
 *
 * The descriptions sit under the line rather than inside it: the line is the
 * finding and stays scannable, and a coder comparing two long descriptions
 * wants them one above the other, not run together on one row.
 *
 * A code with no description simply has no line — CPT is the common case,
 * since those descriptions are AMA-licensed and this app does not carry them.
 */
function FeedbackLine({ fb, describe }: {
  fb: { section?: string; issue?: string; coder_code?: string; ak_code?: string }
  describe: (code: string) => { description: string } | null
}) {
  const submitted = fb.coder_code ? describe(fb.coder_code) : null
  const expected = fb.ak_code ? describe(fb.ak_code) : null
  return (
    <div style={{ marginBottom: submitted || expected ? 6 : 0 }}>
      <div>
        • [{fb.section}] {fb.issue} — submitted: <code>{fb.coder_code || '—'}</code>
        {' '}| expected: <code>{fb.ak_code || '—'}</code>
      </div>
      {submitted && (
        <div style={s.feedbackSays}>
          <code style={s.feedbackCode}>{fb.coder_code}</code> {submitted.description}
        </div>
      )}
      {expected && (
        <div style={{ ...s.feedbackSays, color: '#047857' }}>
          <code style={s.feedbackCode}>{fb.ak_code}</code> {expected.description}
        </div>
      )}
    </div>
  )
}

function ResultsView({ results, coderName }: { results: ReturnType<typeof _shapeResult>[]; coderName: string }) {
  const avg = results.filter(r => r.total_score !== null).reduce((a, r) => a + (r.total_score ?? 0), 0) / (results.filter(r => r.total_score !== null).length || 1)
  const isEMSession = results.some(r => r.specialty && isEM(r.specialty))

  // This is where a coder finds out they were wrong, and until now it said
  // "submitted E11.9, expected E11.22" with no indication of what either code
  // means — which is the difference being marked, and the only thing that
  // makes the mark teach anything.
  //
  // Three lookups because three code systems: a seven-character string is a
  // procedure, not a diagnosis, and asking the wrong table gets nothing or,
  // worse, something that happens to collide.
  const feedbackCodes = (section: (s: string) => boolean) => {
    const out: string[] = []
    for (const r of results) {
      for (const fb of (r.feedback || [])) {
        if (!section(fb.section || '')) continue
        if (fb.coder_code) out.push(fb.coder_code)
        if (fb.ak_code) out.push(fb.ak_code)
      }
    }
    return out
  }
  const describeDx = useCodeDescriptions(
    feedbackCodes(sec => sec === 'PDx' || sec === 'SDx'), 'SDx')
  const describePcs = useCodeDescriptions(feedbackCodes(sec => sec === 'PCS'), 'PCS')
  const describeCpt = useCodeDescriptions(feedbackCodes(sec => sec === 'CPT'), 'CPT')
  const describeFor = (sec: string) =>
    sec === 'PCS' ? describePcs : sec === 'CPT' ? describeCpt : describeDx
  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 900, margin: '0 auto', padding: '32px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <CheckCircle size={28} color="#059669" />
        <div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Practice Complete — {coderName}</div>
          <div style={{ fontSize: 13, color: '#6b7280' }}>Average score: {avg.toFixed(1)}%</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {results.map((r, i) => {
          if (isEMSession) return <EMResultCard key={i} r={r} />
          return (
            <div key={i} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: r.feedback?.length ? 10 : 0 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>{r.chart_number}</span>
                {r.total_score !== null && (
                  <span style={{ fontSize: 13, fontWeight: 700, color: (r.total_score ?? 0) >= 80 ? '#059669' : '#dc2626' }}>{r.total_score}%</span>
                )}
                <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: r.pass_fail === 'PASS' ? '#d1fae5' : '#fee2e2', color: r.pass_fail === 'PASS' ? '#059669' : '#dc2626' }}>{r.pass_fail || '—'}</span>
                {r.flagged && <Flag size={13} color="#f59e0b" />}
              </div>
              {r.feedback?.length > 0 && (
                <div style={{ fontSize: 12, color: '#6b7280', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {r.feedback.map((fb, j) => (
                    <FeedbackLine key={j} fb={fb} describe={describeFor(fb.section || '')} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  center: { display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', fontFamily: 'system-ui, sans-serif' },
  spinner: { width: 36, height: 36, borderRadius: '50%', border: '3px solid #e5e7eb', borderTopColor: '#059669', animation: 'spin 0.8s linear infinite' },
  card: { background: '#fff', borderRadius: 16, padding: 28, display: 'flex', flexDirection: 'column', alignItems: 'center', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' },
  leftPanel: { width: 240, minWidth: 240, background: '#fff', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', height: '100vh', position: 'sticky', top: 0, overflowY: 'auto' },
  rightPanel: { flex: 1, overflowY: 'auto', padding: '8px 0' },
  chartBtn: { display: 'block', width: '100%', padding: '10px 12px', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid #f3f4f6', transition: 'background 0.12s' },
  reviewBtn: { display: 'flex', alignItems: 'center', gap: 6, width: '100%', justifyContent: 'center', padding: '10px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13 },
  submitBtn: { display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', width: '100%', padding: '13px', background: 'linear-gradient(135deg, #059669, #0d9488)', color: '#fff', border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 15, fontWeight: 700 },
  backBtn: { background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', fontWeight: 600, fontSize: 14 },
  inputField: { width: '100%', padding: '10px 12px', border: '1.5px solid #e5e7eb', borderRadius: 8, fontSize: 14, outline: 'none', boxSizing: 'border-box', marginBottom: 4, background: '#fafafa' },
  selectField: { width: '100%', padding: '10px 12px', border: '1.5px solid #e5e7eb', borderRadius: 8, fontSize: 13, outline: 'none', boxSizing: 'border-box', background: '#fafafa', cursor: 'pointer' },
  hint: { fontSize: 11, color: '#9ca3af', marginTop: 2 },
  // One line. A PCS description runs to ninety characters and wrapping it
  // pushed every row below it down; the field is full width here, so there is
  // room for the whole thing.
  notACode: {
    fontSize: 11, lineHeight: 1.35, color: '#b45309', marginTop: 3,
    background: '#fffbeb', border: '1px solid #fde68a',
    borderLeft: '3px solid #f59e0b', borderRadius: 6, padding: '4px 9px',
  } as const,
  codeSays: {
    fontSize: 11, lineHeight: 1.35, color: '#334155', marginTop: 3,
    background: '#f8fafc', border: '1px solid #e2e8f0',
    borderLeft: '3px solid #cbd5e1', borderRadius: 6,
    padding: '4px 9px',
    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
  } as const,
  feedbackSays: {
    fontSize: 11, lineHeight: 1.45, color: '#6b7280',
    paddingLeft: 12, marginTop: 2,
  },
  feedbackCode: { fontFamily: 'ui-monospace, monospace', color: '#374151' },
  poaTooltip: { fontSize: 11, color: '#9ca3af', display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 },
  warningLine: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#f59e0b', marginTop: 2, marginBottom: 4 },
  addBtn: { display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1.5px dashed #d1d5db', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13, color: '#6b7280', marginTop: 4 },
  removeBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, background: '#fee2e2', border: 'none', borderRadius: 6, cursor: 'pointer', color: '#dc2626', flexShrink: 0 },
  toast: { position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', background: '#1f2937', color: '#fff', padding: '10px 20px', borderRadius: 10, fontSize: 14, fontWeight: 600, zIndex: 9999, pointerEvents: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' },
}
