import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Flag, Save, ChevronRight, CheckCircle, AlertTriangle, Circle, Send, BookOpen, Plus, X, Info } from 'lucide-react'
import api from '../api/client'

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChartInfo {
  chart_id: number
  chart_number: string
  description: string
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
  cpt: Array<{ code: string; modifier: string }>
  // E&D fields
  ed_review: string
  ed_research: string
  ed_resolution: string
  ed_rationale: string
  flagged: boolean
  coder_notes: string
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

const EMPTY_ENTRY = (chart_id: number): CodeEntry => ({
  chart_id,
  pdx_code: '',
  pdx_poa: '',
  sdx: [],
  pcs: [],
  cpt: [],
  ed_review: '',
  ed_research: '',
  ed_resolution: '',
  ed_rationale: '',
  flagged: false,
  coder_notes: '',
})

function isIP(specialty: string) {
  return specialty.toUpperCase().startsWith('IP')
}

function isED(specialty: string) {
  const sp = specialty.toUpperCase()
  return sp.includes('EDIT') || sp.includes('DENIAL')
}

function chartStatus(entry: CodeEntry, ip: boolean, ed: boolean): 'complete' | 'partial' | 'empty' {
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
        const draft = data.drafts?.[chart.chart_id]
        initial[chart.chart_id] = {
          chart_id: chart.chart_id,
          pdx_code: draft?.pdx_code || '',
          pdx_poa: draft?.pdx_poa || '',
          sdx: draft?.sdx || [],
          pcs: draft?.pcs || [],
          cpt: draft?.cpt || [],
          ed_review: (draft as any)?.ed_review || '',
          ed_research: (draft as any)?.ed_research || '',
          ed_resolution: (draft as any)?.ed_resolution || '',
          ed_rationale: (draft as any)?.ed_rationale || '',
          flagged: draft?.flagged || false,
          coder_notes: draft?.coder_notes || '',
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
  const activeEntry = activeChartId !== null ? entries[activeChartId] : null

  // ── Save draft ──────────────────────────────────────────────────────────────
  const saveDraft = useCallback(async (showMsg = false) => {
    if (!session) return
    setSaving(true)
    try {
      await api.post(`/practicelab/practice-sessions/${session.session_id}/save-draft`, {
        entries: Object.values(entries),
      })
      if (showMsg) { setSaveMsg('Saved'); setTimeout(() => setSaveMsg(''), 2000) }
    } catch { /* silent */ }
    setSaving(false)
  }, [session, entries])

  // ── Navigate between charts — auto-save on leave ───────────────────────────
  const navigateTo = useCallback((chartId: number) => {
    if (chartId === activeChartId) return
    saveDraft()
    setActiveChartId(chartId)
  }, [activeChartId, saveDraft])

  // ── Entry update helpers ────────────────────────────────────────────────────
  function updateEntry(chartId: number, patch: Partial<CodeEntry>) {
    setEntries(prev => ({ ...prev, [chartId]: { ...prev[chartId], ...patch } }))
  }

  // ── Validate before Save button ─────────────────────────────────────────────
  function validateAndSave() {
    if (!activeEntry || !activeChartId) return
    if (!ed && !activeEntry.pdx_code.trim()) {
      showToast('Principal Diagnosis is required before saving this chart')
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
    const complete = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed) === 'complete').length
    const partial = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed) === 'partial').length
    const empty = charts.filter(c => chartStatus(entries[c.chart_id], ip, ed) === 'empty').length
    const flagged = charts.filter(c => entries[c.chart_id]?.flagged).length

    return (
      <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 700, margin: '0 auto', padding: '32px 20px' }}>
        <div style={{ marginBottom: 24 }}>
          <button onClick={() => setView('coding')} style={s.backBtn}>← Back to coding</button>
        </div>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Review Before Submit</div>
        <div style={{ fontSize: 14, color: '#6b7280', marginBottom: 20 }}>
          {complete} chart{complete !== 1 ? 's' : ''} coded
          {flagged > 0 ? ` · ${flagged} flagged for review` : ''}
          {partial > 0 ? ` · ${partial} missing POA` : ''}
          {empty > 0 ? ` · ${empty} not started` : ''}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 28 }}>
          {charts.map(c => {
            const st = chartStatus(entries[c.chart_id], ip, ed)
            const fl = entries[c.chart_id]?.flagged
            return (
              <div key={c.chart_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10 }}>
                {st === 'complete' ? <CheckCircle size={16} color="#059669" /> : st === 'partial' ? <AlertTriangle size={16} color="#f59e0b" /> : <Circle size={16} color="#d1d5db" />}
                <span style={{ fontWeight: 600, fontSize: 14 }}>{c.chart_number}</span>
                <span style={{ fontSize: 13, color: '#6b7280', flex: 1 }}>{c.description ? c.description.replace(/<[^>]*>/g, '') : ''}</span>
                {fl && <Flag size={13} color="#f59e0b" />}
                {st === 'empty' && <span style={{ fontSize: 12, color: '#9ca3af' }}>Not started</span>}
                {st === 'partial' && <span style={{ fontSize: 12, color: '#f59e0b' }}>Missing POA</span>}
                <button onClick={() => { setActiveChartId(c.chart_id); setView('coding') }} style={{ fontSize: 12, color: '#7c3aed', background: 'none', border: 'none', cursor: 'pointer' }}>Edit</button>
              </div>
            )
          })}
        </div>

        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{ ...s.submitBtn, opacity: submitting ? 0.7 : 1 }}
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
        <div style={{ padding: '16px 12px 8px', borderBottom: '1px solid #e5e7eb' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOpen size={18} color="#059669" />
            <span style={{ fontWeight: 700, fontSize: 14 }}>{session.coder_name}</span>
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{session.specialty}</div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {charts.map(c => {
            const st = chartStatus(entries[c.chart_id], ip, ed)
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
                <div style={{ fontSize: 11, color: '#6b7280', textAlign: 'left', marginTop: 2, paddingLeft: 19, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.description || c.category}</div>
              </button>
            )
          })}
        </div>

        <div style={{ padding: '12px', borderTop: '1px solid #e5e7eb' }}>
          <button
            onClick={() => { saveDraft(); setView('review') }}
            style={s.reviewBtn}
          >
            <ChevronRight size={14} /> Review & Submit
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
  onChange: (patch: Partial<CodeEntry>) => void
  onSave: () => void
  saving: boolean
  saveMsg: string
}

function CodeEntryForm({ chart, entry, ip, ed, onChange, onSave, saving, saveMsg }: FormProps) {
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

  function updateCpt(idx: number, field: 'code' | 'modifier', val: string) {
    const cpt = [...entry.cpt]
    cpt[idx] = { ...cpt[idx], [field]: val }
    onChange({ cpt })
  }
  function addCpt() { onChange({ cpt: [...entry.cpt, { code: '', modifier: '' }] }) }
  function removeCpt(idx: number) { onChange({ cpt: entry.cpt.filter((_, i) => i !== idx) }) }

  const pdxPOAMissing = ip && entry.pdx_code.trim() && !entry.pdx_poa
  const sdxPOAMissing = ip ? entry.sdx.filter(s => s.code.trim() && !s.poa) : []

  return (
    <div style={{ padding: '24px 28px', maxWidth: 760, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: '#111' }}>{chart.chart_number}</div>
          {chart.description && <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }} dangerouslySetInnerHTML={{ __html: chart.description }} />}
          <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
            <Chip label={chart.specialty} />
            {chart.category && <Chip label={chart.category} />}
            {chart.difficulty && <Chip label={chart.difficulty} color="#f59e0b" bg="#fef9c3" />}
          </div>
        </div>
        <button
          onClick={() => onChange({ flagged: !entry.flagged })}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 8, border: entry.flagged ? '1.5px solid #f59e0b' : '1.5px solid #e5e7eb', background: entry.flagged ? '#fef9c3' : '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: entry.flagged ? '#b45309' : '#6b7280' }}
        >
          <Flag size={14} />
          {entry.flagged ? 'Flagged' : 'Flag for Review'}
        </button>
      </div>

      {/* ── E&D form ── */}
      {ed && (<>
        <Section title="Review" required>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="Summarise your review of the claim/denial — what was the original decision and why?"
            value={entry.ed_review}
            onChange={e => onChange({ ed_review: e.target.value })}
          />
        </Section>
        <Section title="Research" required>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="What did you research? Include coding guidelines, payer rules, or nuances you found relevant."
            value={entry.ed_research}
            onChange={e => onChange({ ed_research: e.target.value })}
          />
        </Section>
        <Section title="Resolution" required>
          <textarea
            style={{ ...s.inputField, height: 100, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="What is your recommended resolution? (e.g. Uphold denial / Reverse / Partial reversal — and why)"
            value={entry.ed_resolution}
            onChange={e => onChange({ ed_resolution: e.target.value })}
          />
        </Section>
        <Section title="Final Rationale" required>
          <textarea
            style={{ ...s.inputField, height: 110, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
            placeholder="Write your final supporting rationale — cite the specific guidelines, payer policies, or clinical documentation that supports your resolution."
            value={entry.ed_rationale}
            onChange={e => onChange({ ed_rationale: e.target.value })}
          />
        </Section>
      </>)}

      {/* ── IP / OP form ── */}
      {!ed && <>

      {/* Principal Diagnosis */}
      <Section title="Principal Diagnosis" required>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <input
              style={{ ...s.inputField, borderColor: pdxPOAMissing ? '#fca5a5' : '#e5e7eb' }}
              placeholder="e.g. J18.9"
              value={entry.pdx_code}
              onChange={e => onChange({ pdx_code: e.target.value.toUpperCase() })}
            />
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
      <Section title="Secondary Diagnoses">
        {entry.sdx.map((row, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
            <input
              style={{ ...s.inputField, flex: 1, marginBottom: 0 }}
              placeholder="e.g. E11.9"
              value={row.code}
              onChange={e => updateSdx(i, 'code', e.target.value.toUpperCase())}
            />
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
          <div style={s.warningLine}><AlertTriangle size={11} color="#f59e0b" /> {sdxPOAMissing.length} secondary diagnosis{sdxPOAMissing.length > 1 ? 'es' : ''} missing POA</div>
        )}
        <button onClick={addSdx} style={s.addBtn}><Plus size={13} /> Add Secondary Diagnosis</button>
        <div style={s.hint}>ICD-10-CM · dot optional</div>
      </Section>

      {/* PCS Procedures (IP only) */}
      {ip && (
        <Section title="PCS Procedures">
          {entry.pcs.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <input
                style={{ ...s.inputField, flex: 1, marginBottom: 0, fontFamily: 'monospace' }}
                placeholder="e.g. 0BHN3BZ"
                value={row.code}
                onChange={e => updatePcs(i, e.target.value.toUpperCase())}
                maxLength={10}
              />
              <button onClick={() => removePcs(i)} style={s.removeBtn}><X size={14} /></button>
            </div>
          ))}
          <button onClick={addPcs} style={s.addBtn}><Plus size={13} /> Add Procedure</button>
          <div style={s.hint}>7-character PCS · spaces optional</div>
        </Section>
      )}

      {/* CPT Procedures (OP only) */}
      {!ip && (
        <Section title="CPT Procedures">
          {entry.cpt.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <input
                style={{ ...s.inputField, width: 140, marginBottom: 0 }}
                placeholder="e.g. 20610"
                value={row.code}
                onChange={e => updateCpt(i, 'code', e.target.value)}
              />
              <input
                style={{ ...s.inputField, flex: 1, marginBottom: 0 }}
                placeholder="e.g. 25, 59"
                value={row.modifier}
                onChange={e => updateCpt(i, 'modifier', e.target.value)}
              />
              <button onClick={() => removeCpt(i)} style={s.removeBtn}><X size={14} /></button>
            </div>
          ))}
          <button onClick={addCpt} style={s.addBtn}><Plus size={13} /> Add CPT Code</button>
          <div style={s.hint}>5-digit CPT · append modifiers per guidelines where applicable</div>
        </Section>
      )}
      </>}

      {/* Optional notes */}
      <Section title={ed ? "Additional Notes (Optional) — anything extra beyond the 4 fields above" : "Notes for Trainer (Optional)"}>
        <textarea
          style={{ ...s.inputField, height: 72, resize: 'vertical', fontFamily: 'system-ui, sans-serif' }}
          placeholder="Any questions or notes about this chart…"
          value={entry.coder_notes}
          onChange={e => onChange({ coder_notes: e.target.value })}
        />
      </Section>

      {/* Save button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
        <button
          onClick={onSave}
          disabled={saving}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 22px', background: '#059669', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, opacity: saving ? 0.7 : 1 }}
        >
          <Save size={15} /> {saving ? 'Saving…' : 'Save'}
        </button>
        {saveMsg && <span style={{ fontSize: 13, color: '#059669', fontWeight: 600 }}>✓ {saveMsg}</span>}
      </div>
    </div>
  )
}

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({ title, required, children }: { title: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 8 }}>
        {title}{required && <span style={{ color: '#dc2626', marginLeft: 4 }}>*</span>}
      </div>
      {children}
    </div>
  )
}

function Chip({ label, color = '#4f46e5', bg = '#ede9fe' }: { label: string; color?: string; bg?: string }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 600, background: bg, color, borderRadius: 6, padding: '2px 8px' }}>{label}</span>
  )
}

// ── Results View ───────────────────────────────────────────────────────────────

interface ResultRow {
  chart_number: string
  total_score: number | null
  pass_fail: string | null
  pdx_submitted: string | null
  pdx_answer_key: string | null
  pdx_correct: boolean | null
  feedback: Array<{ section: string; issue: string; ak_code: string; coder_code: string }>
  flagged: boolean
}

function _shapeResult(r: unknown): ResultRow { return r as ResultRow }

function ResultsView({ results, coderName }: { results: ReturnType<typeof _shapeResult>[]; coderName: string }) {
  const avg = results.filter(r => r.total_score !== null).reduce((a, r) => a + (r.total_score ?? 0), 0) / (results.filter(r => r.total_score !== null).length || 1)
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
        {results.map((r, i) => (
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
                  <div key={j}>• [{fb.section}] {fb.issue} — submitted: <code>{fb.coder_code || '—'}</code> | expected: <code>{fb.ak_code || '—'}</code></div>
                ))}
              </div>
            )}
          </div>
        ))}
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
  poaTooltip: { fontSize: 11, color: '#9ca3af', display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 },
  warningLine: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#f59e0b', marginTop: 2, marginBottom: 4 },
  addBtn: { display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1.5px dashed #d1d5db', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13, color: '#6b7280', marginTop: 4 },
  removeBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, background: '#fee2e2', border: 'none', borderRadius: 6, cursor: 'pointer', color: '#dc2626', flexShrink: 0 },
  toast: { position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', background: '#1f2937', color: '#fff', padding: '10px 20px', borderRadius: 10, fontSize: 14, fontWeight: 600, zIndex: 9999, pointerEvents: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' },
}
