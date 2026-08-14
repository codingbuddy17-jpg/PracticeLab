import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  AlertTriangle, Check, CheckCircle, ChevronRight, Circle, Copy, Plus,
  Save, Send, Trash2, X,
} from 'lucide-react'
import {
  AuditChart, AuditResultRow, AuditSessionData, AuditSummary, ChartWork,
  Finding, SectionSpec, openAuditSession, saveAuditDraft, submitAuditSession,
} from '../api/auditorApi'
import { ISSUE_COLORS } from './practicelab/shared'

/**
 * The auditor's working screen.
 *
 * Nothing here knows whether a chart carries introduced errors. Structure comes
 * from the specialty — served by the API rather than hardcoded — and content is
 * whatever claim the chart was assigned. A clean chart renders identically to one
 * carrying errors, which is the whole basis of measuring restraint: an empty state
 * drawn differently, or a section collapsed because nothing was mutated, would
 * tell the auditor the answer before they looked.
 */

const NO_CHANGES = 'no_changes'
const NEEDS_CHANGES = 'needs_changes'

type ChartState = {
  verdicts: Record<string, string>
  findings: Finding[]
  query_flag: boolean
  query_text: string
  notes: string
}

const EMPTY_STATE = (): ChartState => ({
  verdicts: {}, findings: [], query_flag: false, query_text: '', notes: '',
})

function rowsFor(chart: AuditChart, section: string) {
  if (section === 'SDx') return chart.claim.sdx || []
  if (section === 'PCS') return chart.claim.pcs || []
  if (section === 'CPT') return chart.claim.cpt || []
  return []
}

/** A section is settled once the auditor has said something about it. */
function sectionSettled(state: ChartState, key: string) {
  return state.verdicts[key] === NO_CHANGES || state.verdicts[key] === NEEDS_CHANGES
}

/** A "needs changes" verdict with nothing behind it is not a finding — and a
 *  half-written one cannot be matched, so it would score as an over-call. */
function chartGaps(state: ChartState, sections: SectionSpec[], supportsQuery: boolean) {
  const gaps: string[] = []
  for (const spec of sections) {
    if (!sectionSettled(state, spec.key)) { gaps.push(`${spec.key} needs a verdict`); continue }
    if (state.verdicts[spec.key] !== NEEDS_CHANGES) continue
    const mine = state.findings.filter(f => f.section === spec.key)
    if (!mine.length) { gaps.push(`${spec.key} is marked as needing changes but says nothing`); continue }
    if (mine.some(f => f.action === 'Add' && !(f.correct_value || '').trim()))
      gaps.push(`${spec.key} has an empty code to add`)
    if (spec.fields.includes('poa') && mine.some(f => f.action === 'Add' && !(f.poa || '').trim()))
      gaps.push(`${spec.key} has a missing diagnosis without POA`)
    if (mine.some(f => f.action === 'Revise' && !(f.correct_value || '').trim()))
      gaps.push(`${spec.key} has a revision with no corrected value`)
  }
  if (supportsQuery && state.query_flag && !state.query_text.trim())
    gaps.push('the query has not been written')
  return gaps
}

function chartComplete(state: ChartState, sections: SectionSpec[], supportsQuery: boolean) {
  return chartGaps(state, sections, supportsQuery).length === 0
}

function chartTouched(state: ChartState) {
  return Object.keys(state.verdicts).length > 0 || state.findings.length > 0
}

export function AuditSession() {
  const { token } = useParams<{ token: string }>()
  const [session, setSession] = useState<AuditSessionData | null>(null)
  const [states, setStates] = useState<Record<number, ChartState>>({})
  const [activeId, setActiveId] = useState<number | null>(null)
  const [view, setView] = useState<'working' | 'review' | 'submitted'>('working')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [outcome, setOutcome] = useState<{ summary: AuditSummary; results: AuditResultRow[]; show: boolean } | null>(null)
  const [toast, setToast] = useState('')
  const [dirty, setDirty] = useState(false)
  const [exiting, setExiting] = useState(false)
  const toastTimer = useRef<ReturnType<typeof setTimeout>>()

  // Audit findings are granular and slow to re-enter, so losing them to a
  // closed tab costs more than it does on the coder form. Same guard the coder
  // session uses, plus a save whenever the auditor moves between charts.
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const flash = useCallback((msg: string) => {
    setToast(msg)
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(''), 3200)
  }, [])

  useEffect(() => {
    if (!token) return
    openAuditSession(token).then(data => {
      setSession(data)
      if (data.status === 'submitted') {
        setOutcome({ summary: {} as AuditSummary, results: data.results || [], show: data.show_results })
        setView('submitted')
      } else {
        const initial: Record<number, ChartState> = {}
        for (const c of data.charts) {
          initial[c.chart_id] = c.draft
            ? {
              verdicts: c.draft.section_verdicts || {},
              findings: c.draft.findings || [],
              query_flag: !!c.draft.query_flag,
              query_text: c.draft.query_text || '',
              notes: c.draft.auditor_notes || '',
            }
            : EMPTY_STATE()
        }
        setStates(initial)
        setActiveId(data.charts[0]?.chart_id ?? null)
      }
      setLoading(false)
    }).catch(e => {
      const err = e as { response?: { data?: { detail?: string } } }
      setError(err?.response?.data?.detail || 'Access code not recognised')
      setLoading(false)
    })
  }, [token])

  const sections = session?.form?.sections || []
  const supportsQuery = !!session?.supports_query
  const activeChart = session?.charts.find(c => c.chart_id === activeId) || null
  const activeState = activeId !== null ? (states[activeId] || EMPTY_STATE()) : null
  const doneCount = (session?.charts || []).filter(
    c => chartComplete(states[c.chart_id] || EMPTY_STATE(), sections, supportsQuery)).length
  const findingCount = Object.values(states).reduce((n, st) => n + st.findings.length, 0)

  function patch(chartId: number, changes: Partial<ChartState>) {
    setStates(prev => ({ ...prev, [chartId]: { ...(prev[chartId] || EMPTY_STATE()), ...changes } }))
    setDirty(true)
  }

  /** Moving between charts saves first, so a lost connection costs one chart
   *  at most rather than the whole sitting. */
  async function goToChart(id: number) {
    if (id === activeId) return
    if (dirty) await save()
    setActiveId(id)
  }

  function toWork(): ChartWork[] {
    return (session?.charts || []).map(c => {
      const st = states[c.chart_id] || EMPTY_STATE()
      return {
        chart_id: c.chart_id,
        section_verdicts: st.verdicts,
        // A section marked "no changes" cannot carry findings — the two would
        // contradict each other, and the verdict is the auditor's claim.
        findings: st.findings.filter(f => st.verdicts[f.section] === NEEDS_CHANGES),
        query_flag: st.query_flag,
        query_text: st.query_text,
        auditor_notes: st.notes,
      }
    })
  }

  async function save() {
    if (!session) return
    setSaving(true)
    try {
      await saveAuditDraft(session.session_id, toWork())
      setSavedAt(new Date().toLocaleTimeString())
      setDirty(false)
    } catch { flash('Could not save — check your connection') }
    setSaving(false)
  }

  async function submit() {
    if (!session) return
    const blocked = session.charts.filter(
      c => !chartComplete(states[c.chart_id] || EMPTY_STATE(), sections, supportsQuery))
    if (blocked.length) {
      setActiveId(blocked[0].chart_id)
      setView('working')
      const why = chartGaps(states[blocked[0].chart_id] || EMPTY_STATE(), sections, supportsQuery)[0]
      flash(`${blocked[0].chart_number}: ${why}`)
      return
    }
    setSubmitting(true)
    try {
      const res = await submitAuditSession(session.session_id, toWork())
      setOutcome({ summary: res.summary, results: res.results || [], show: res.show_results })
      setDirty(false)
      setView('submitted')
    } catch (e) {
      const err = e as { response?: { data?: { detail?: unknown } } }
      const d = err?.response?.data?.detail
      flash(typeof d === 'string' ? d : (d as { message?: string })?.message || 'Submission failed')
    }
    setSubmitting(false)
  }

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

  if (view === 'submitted') return <SubmittedView outcome={outcome} name={session.auditor_name} />

  if (exiting) return (
    <div style={s.center}>
      <div style={{ ...s.card, maxWidth: 480, textAlign: 'center', gap: 14 }}>
        <CheckCircle size={34} color="#059669" />
        <div style={{ fontWeight: 700, fontSize: 17 }}>Your work is saved</div>
        <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.6 }}>
          Nothing has been submitted yet. Open the same link again to carry on from
          where you stopped — every finding you recorded will still be there.
        </div>
        <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 3 }}>Your access code</div>
          <div style={{ fontFamily: 'monospace', fontSize: 15, fontWeight: 700 }}>{token}</div>
        </div>
        <button onClick={() => setExiting(false)} style={{ padding: '9px 18px', borderRadius: 8,
          border: '1px solid #e5e7eb', background: '#fff', color: '#9333ea',
          fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
          Back to my charts
        </button>
      </div>
    </div>
  )

  if (view === 'review') {
    const incomplete = session.charts.filter(
      c => !chartComplete(states[c.chart_id] || EMPTY_STATE(), sections, supportsQuery))
    return (
      <div style={s.reviewPage}>
        <button onClick={() => setView('working')} style={s.backBtn}>← Back to auditing</button>
        <div style={s.reviewTitle}>Review Before Submit</div>
        <div style={s.reviewSub}>
          {session.charts.length} chart{session.charts.length !== 1 ? 's' : ''} ·{' '}
          {session.charts.reduce((n, c) => n + (states[c.chart_id]?.findings.length || 0), 0)} finding(s) recorded
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
          {session.charts.map(c => {
            const st = states[c.chart_id] || EMPTY_STATE()
            const done = chartComplete(st, sections, supportsQuery)
            return (
              <div key={c.chart_id} style={{ ...s.reviewRow, borderColor: done ? '#e5e7eb' : '#fecaca', background: done ? '#fff' : '#fffafa' }}>
                {done ? <CheckCircle size={16} color="#059669" /> : <AlertTriangle size={16} color="#dc2626" />}
                <span style={{ fontWeight: 700, fontSize: 14 }}>{c.chart_number}</span>
                <span style={{ fontSize: 13, color: '#6b7280', flex: 1 }}>
                  {st.findings.length} finding{st.findings.length !== 1 ? 's' : ''}
                  {st.query_flag ? ' · query raised' : ''}
                </span>
                {!done && (
                  <span style={{ fontSize: 11.5, color: '#dc2626', fontWeight: 600, maxWidth: 260, textAlign: 'right' }}>
                    {chartGaps(st, sections, supportsQuery)[0]}
                  </span>
                )}
                <button onClick={() => { setActiveId(c.chart_id); setView('working') }} style={s.linkBtn}>Open</button>
              </div>
            )
          })}
        </div>
        {incomplete.length > 0 && (
          <div style={s.blockBox}>
            <AlertTriangle size={16} color="#dc2626" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ fontSize: 13, color: '#b91c1c', lineHeight: 1.5 }}>
              <strong>{incomplete.length} chart{incomplete.length !== 1 ? 's are' : ' is'} incomplete.</strong>{' '}
              Every section needs a verdict — saying a section has no changes is itself a finding,
              and the audit cannot be scored without it.
            </div>
          </div>
        )}
        <button
          onClick={submit}
          disabled={submitting || incomplete.length > 0}
          style={{ ...s.submitBtn, opacity: submitting || incomplete.length ? 0.5 : 1, cursor: incomplete.length ? 'not-allowed' : 'pointer' }}
        >
          <Send size={15} /> {submitting ? 'Submitting…' : 'Submit Audit'}
        </button>
        <div style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center', marginTop: 10 }}>
          Submissions cannot be edited afterwards.
        </div>
      </div>
    )
  }

  return (
    <div style={s.shell}>
      {toast && <div style={s.toast}>{toast}</div>}

      <aside style={s.sidebar}>
        <div style={s.brand}>PracticeLab — Auditor</div>
        <div style={s.who}>{session.auditor_name} · {session.specialty}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 16 }}>
          {session.charts.map(c => {
            const st = states[c.chart_id] || EMPTY_STATE()
            const done = chartComplete(st, sections, supportsQuery)
            const started = chartTouched(st)
            const on = c.chart_id === activeId
            return (
              <button
                key={c.chart_id}
                onClick={() => goToChart(c.chart_id)}
                style={{ ...s.chartTab, background: on ? '#fff' : 'transparent', boxShadow: on ? '0 1px 4px rgba(0,0,0,0.08)' : 'none' }}
              >
                {done ? <CheckCircle size={14} color="#059669" />
                  : started ? <Circle size={14} color="#d97706" />
                    : <Circle size={14} color="#d1d5db" />}
                <span style={{ fontWeight: on ? 700 : 600, fontSize: 13 }}>{c.chart_number}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>
                  {st.findings.length || ''}
                </span>
              </button>
            )
          })}
        </div>
        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Progress against the whole sitting, so an auditor can see how far
              in they are without counting icons. */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
              <span>{doneCount} of {session.charts.length} reviewed</span>
              <span>{findingCount} finding{findingCount !== 1 ? 's' : ''}</span>
            </div>
            <div style={{ height: 5, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ height: '100%', borderRadius: 3, background: '#9333ea',
                            width: `${Math.round(doneCount / Math.max(1, session.charts.length) * 100)}%`,
                            transition: 'width 0.3s' }} />
            </div>
          </div>
          <button onClick={save} disabled={saving} style={s.saveBtn}>
            <Save size={14} /> {saving ? 'Saving…' : dirty ? 'Save progress •' : 'Save progress'}
          </button>
          <button onClick={async () => { if (dirty) await save(); setExiting(true) }}
            style={s.saveBtn}>
            Save &amp; exit
          </button>
          <button onClick={() => setView('review')} style={s.reviewBtn}>
            Review &amp; submit <ChevronRight size={14} />
          </button>
          {savedAt && <div style={{ fontSize: 11, color: '#9ca3af', textAlign: 'center' }}>Saved {savedAt}</div>}
        </div>
      </aside>

      <main style={s.main}>
        {activeChart && activeState && (
          <ChartPanel
            key={activeChart.chart_id}
            chart={activeChart}
            state={activeState}
            sections={sections}
            supportsQuery={supportsQuery}
            onChange={changes => patch(activeChart.chart_id, changes)}
          />
        )}
      </main>
    </div>
  )
}

// ── one chart ────────────────────────────────────────────────────────────────

function ChartPanel({ chart, state, sections, supportsQuery, onChange }: {
  chart: AuditChart
  state: ChartState
  sections: SectionSpec[]
  supportsQuery: boolean
  onChange: (c: Partial<ChartState>) => void
}) {
  const [copied, setCopied] = useState(false)

  function setVerdict(section: string, verdict: string) {
    const verdicts = { ...state.verdicts, [section]: verdict }
    // Clearing a section back to "no changes" drops its findings — otherwise a
    // finding survives invisibly under a verdict that contradicts it.
    const findings = verdict === NO_CHANGES
      ? state.findings.filter(f => f.section !== section)
      : state.findings
    onChange({ verdicts, findings })
  }

  function upsert(match: (f: Finding) => boolean, next: Finding | null) {
    const rest = state.findings.filter(f => !match(f))
    onChange({ findings: next ? [...rest, next] : rest })
  }

  const queryMissing = supportsQuery && state.query_flag && !state.query_text.trim()

  return (
    <div style={{ maxWidth: 940, margin: '0 auto', padding: '28px 24px 80px' }}>
      <div style={s.chartHead}>
        <div>
          <div style={s.chartNum}>{chart.chart_number}</div>
          <div style={s.chartMeta}>{chart.category}</div>
        </div>
        <button
          onClick={() => { navigator.clipboard.writeText(chart.chart_number); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          style={s.copyBtn}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy number'}
        </button>
      </div>

      <div style={s.intro}>
        This chart has already been coded. Review each section against the record and
        say whether it needs changes.
      </div>

      {sections.map(spec => (
        <SectionBlock
          key={spec.key}
          spec={spec}
          chart={chart}
          state={state}
          onVerdict={v => setVerdict(spec.key, v)}
          onUpsert={upsert}
        />
      ))}

      {supportsQuery && (
        <div style={{ ...s.section, borderLeft: `4px solid ${NEUTRAL.accent}` }}>
          <div style={{ ...s.sectionHead, background: NEUTRAL.tint,
                        borderBottomColor: NEUTRAL.line }}>
            <span style={{ ...s.sectionName, color: NEUTRAL.accent }}>Physician Query</span>
          </div>
          <div style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 10 }}>
              Does this chart need a physician query before it can be coded as documented?
            </div>
            <Segmented
              value={state.query_flag}
              onChange={v => onChange({ query_flag: v })}
              options={[
                { value: false, label: 'No', tone: '#059669' },
                { value: true, label: 'Yes — needs a query', tone: '#d97706' },
              ]}
            />

            {state.query_flag && (
              <>
                <div style={{ ...s.hintBox, background: queryMissing ? '#fef2f2' : '#fffbeb', borderColor: queryMissing ? '#fecaca' : '#fde68a' }}>
                  <AlertTriangle size={14} color={queryMissing ? '#dc2626' : '#d97706'} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span style={{ fontSize: 12, color: queryMissing ? '#b91c1c' : '#92400e', lineHeight: 1.5 }}>
                    {queryMissing
                      ? <><strong>Your query is required.</strong> Write the question you would put to the physician — this chart cannot be submitted until you do.</>
                      : 'Your query will be reviewed by your trainer.'}
                  </span>
                </div>
                <textarea
                  style={{ ...s.textarea, ...(queryMissing ? { borderColor: '#dc2626', background: '#fffafa' } : {}) }}
                  placeholder="What is unclear, and what do you need clarified?"
                  value={state.query_text}
                  onChange={e => onChange({ query_text: e.target.value })}
                />
              </>
            )}
          </div>
        </div>
      )}

      <div style={{ ...s.section, borderLeft: `4px solid ${NEUTRAL.accent}` }}>
        <div style={{ ...s.sectionHead, background: NEUTRAL.tint,
                      borderBottomColor: NEUTRAL.line }}>
          <span style={{ ...s.sectionName, color: NEUTRAL.accent }}>Notes (Optional)</span>
        </div>
        <div style={{ padding: '14px 16px' }}>
          <textarea
            style={s.textarea}
            placeholder="Anything you want your trainer to know about this chart…"
            value={state.notes}
            onChange={e => onChange({ notes: e.target.value })}
          />
        </div>
      </div>
    </div>
  )
}

// ── one section ──────────────────────────────────────────────────────────────

function SectionBlock({ spec, chart, state, onVerdict, onUpsert }: {
  spec: SectionSpec
  chart: AuditChart
  state: ChartState
  onVerdict: (v: string) => void
  onUpsert: (match: (f: Finding) => boolean, next: Finding | null) => void
}) {
  const key = spec.key
  const open = state.verdicts[key] === NEEDS_CHANGES
  const isPdx = key === 'PDx'
  const rows = isPdx ? [] : rowsFor(chart, key)
  const mine = state.findings.filter(f => f.section === key)
  const adds = mine.filter(f => f.action === 'Add')

  const deletedLines = new Set(mine.filter(f => f.action === 'Delete').map(f => f.line))
  function revisionOf(line: number, field: string) {
    return mine.find(f => f.action === 'Revise' && f.line === line && (f.field || 'code') === field)
  }

  function setRevision(line: number, field: string, claimValue: string, value: string) {
    const match = (f: Finding) => f.section === key && f.action === 'Revise'
      && f.line === line && (f.field || 'code') === field
    const changed = value.trim() && value.trim().toUpperCase() !== (claimValue || '').trim().toUpperCase()
    onUpsert(match, changed
      ? { section: key, action: 'Revise', field, line, claim_value: claimValue, correct_value: value.trim() }
      : null)
  }

  function toggleDelete(line: number, code: string) {
    const match = (f: Finding) => f.section === key && f.action === 'Delete' && f.line === line
    onUpsert(match, deletedLines.has(line)
      ? null
      : { section: key, action: 'Delete', line, claim_value: code })
  }

  function setAddField(index: number, field: string, value: string) {
    const existing = adds[index]
    const match = (f: Finding) => f === existing
    const next = { ...(existing || { section: key, action: 'Add' }) } as Finding
    if (field === 'code') next.correct_value = value
    else (next as any)[field] = value
    onUpsert(match, next)
  }

  function newAdd() {
    onUpsert(() => false, { section: key, action: 'Add', correct_value: '' })
  }

  function removeAdd(index: number) {
    const existing = adds[index]
    onUpsert((f: Finding) => f === existing, null)
  }

  function confirmAddField(index: number, field: string) {
    const pos = spec.fields.indexOf(field)
    const next = spec.fields[pos + 1]
    if (next) {
      const el = document.querySelector<HTMLElement>(
        `[data-add-field="${key}-${index}-${next}"]`
      )
      el?.focus()
      return
    }
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  }

  const t = themeOf(key)
  const codeCount = isPdx ? (chart.claim.pdx_code ? 1 : 0) : rows.length
  const tally = [
    { action: 'Add' as const, n: adds.length },
    { action: 'Revise' as const, n: mine.filter(f => f.action === 'Revise').length },
    { action: 'Delete' as const, n: deletedLines.size },
  ].filter(x => x.n > 0)

  return (
    <div style={{ ...s.section, borderLeft: `4px solid ${t.accent}` }}>
      <div style={{ ...s.sectionHead, background: t.tint, borderBottomColor: t.line }}>
        <div style={{ minWidth: 0 }}>
          {t.kind && <div style={{ ...s.eyebrow, color: t.accent }}>{t.kind}</div>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ ...s.sectionName, color: t.accent }}>
              {SECTION_LABEL[key] || key}
            </span>
            <span style={{ ...s.countPill, color: t.accent, borderColor: t.line }}>
              {codeCount} {codeCount === 1 ? 'code' : 'codes'}
            </span>
            {tally.map(x => (
              <span key={x.action} style={{
                ...s.actionChip,
                color: ACTION_COLOR[x.action],
                borderColor: ACTION_COLOR[x.action] + '55',
                background: ACTION_COLOR[x.action] + '12',
              }}>
                {x.n} {x.action}
              </span>
            ))}
          </div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <Segmented
            value={state.verdicts[key]}
            onChange={onVerdict}
            options={[
              { value: NO_CHANGES, label: 'No changes', tone: '#059669' },
              { value: NEEDS_CHANGES, label: 'Needs changes', tone: '#d97706' },
            ]}
          />
        </div>
      </div>

      <div style={{ padding: '12px 16px' }}>
        {isPdx ? (
          <PdxRow chart={chart} spec={spec} open={open}
            revisionOf={revisionOf} setRevision={setRevision} />
        ) : (
          <>
            {rows.length === 0 && (
              <div style={s.emptyRow}>No codes on this claim in this section.</div>
            )}
            {rows.map((row, i) => (
              <LineRow
                key={i}
                index={i}
                row={row}
                fields={spec.fields}
                open={open}
                deleted={deletedLines.has(i)}
                canDelete={spec.actions.includes('Delete')}
                revisionOf={revisionOf}
                setRevision={setRevision}
                onToggleDelete={() => toggleDelete(i, row.code || '')}
              />
            ))}
            {open && spec.actions.includes('Add') && (
              <div style={{ marginTop: 10 }}>
                {adds.map((f, i) => (
                  <div key={i} style={{
                    ...s.addRow,
                    background: ACTION_COLOR.Add + '0e',
                    boxShadow: `inset 3px 0 0 ${ACTION_COLOR.Add}`,
                  }}>
                    <span style={{ ...s.tagChip, color: ACTION_COLOR.Add,
                                   background: ACTION_COLOR.Add + '18' }}>
                      <Plus size={11} /> Missing
                    </span>
                    {spec.fields.map(field => (
                      <AddField
                        key={field}
                        field={field}
                        finding={f}
                        onChange={v => setAddField(i, field, v)}
                        onEnter={() => confirmAddField(i, field)}
                        fieldId={`${key}-${i}-${field}`}
                        autoFocus={field === 'code' && !f.correct_value}
                        required={field === 'code' || field === 'poa'}
                      />
                    ))}
                    <button onClick={() => removeAdd(i)} style={s.iconBtn}><X size={13} /></button>
                  </div>
                ))}
                <button onClick={newAdd} style={{ ...s.addBtn, color: ACTION_COLOR.Add,
                                                  borderColor: ACTION_COLOR.Add + '55' }}>
                  <Plus size={13} /> Add a missing code
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function PdxRow({ chart, spec, open, revisionOf, setRevision }: {
  chart: AuditChart
  spec: SectionSpec
  open: boolean
  revisionOf: (line: number, field: string) => Finding | undefined
  setRevision: (line: number, field: string, claimValue: string, value: string) => void
}) {
  const values: Record<string, string> = {
    code: chart.claim.pdx_code || '',
    poa: chart.claim.pdx_poa || '',
  }
  return (
    <div style={s.line}>
      {spec.fields.map(field => (
        <Field
          key={field}
          label={FIELD_LABEL[field] || field}
          value={values[field] || ''}
          open={open}
          revision={revisionOf(0, field)}
          onChange={v => setRevision(0, field, values[field] || '', v)}
        />
      ))}
      {!open && <span style={s.lockedNote}>Reviewed as coded</span>}
    </div>
  )
}

function LineRow({ index, row, fields, open, deleted, canDelete, revisionOf, setRevision, onToggleDelete }: {
  index: number
  row: Record<string, unknown>
  fields: string[]
  open: boolean
  deleted: boolean
  canDelete: boolean
  revisionOf: (line: number, field: string) => Finding | undefined
  setRevision: (line: number, field: string, claimValue: string, value: string) => void
  onToggleDelete: () => void
}) {
  const [hover, setHover] = useState(false)
  const del = ACTION_COLOR.Delete
  const revised = fields.some(f => revisionOf(index, f))

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...s.line,
        background: deleted ? del + '0e' : hover && open ? '#fafafa' : 'transparent',
        boxShadow: deleted ? `inset 3px 0 0 ${del}`
          : revised ? `inset 3px 0 0 ${ACTION_COLOR.Revise}` : 'none',
      }}
    >
      <span style={s.lineNo}>{index + 1}</span>
      {fields.map(field => (
        <Field
          key={field}
          label={FIELD_LABEL[field] || field}
          value={String(row[field] ?? '')}
          open={open && !deleted}
          strike={deleted}
          revision={revisionOf(index, field)}
          onChange={v => setRevision(index, field, String(row[field] ?? ''), v)}
        />
      ))}
      {deleted && <span style={{ ...s.tagChip, color: del, background: del + '18' }}>
        <Trash2 size={11} /> Remove from claim
      </span>}
      {open && canDelete && (
        <button
          onClick={onToggleDelete}
          title={deleted ? 'Keep this code' : 'This code should not be on the claim'}
          style={{
            ...s.rowAction, marginLeft: 'auto',
            opacity: deleted || hover ? 1 : 0.35,
            color: deleted ? del : '#6b7280',
            borderColor: deleted ? del + '55' : '#e5e7eb',
            background: deleted ? del + '12' : '#fff',
          }}
        >
          {deleted ? <><X size={12} /> Undo</> : <><Trash2 size={12} /> Delete</>}
        </button>
      )}
    </div>
  )
}

function AddField({ field, finding, onChange, onEnter, fieldId, autoFocus, required }: {
  field: string
  finding: Finding
  onChange: (v: string) => void
  onEnter: () => void
  fieldId: string
  autoFocus?: boolean
  required?: boolean
}) {
  const value = field === 'code'
    ? finding.correct_value || ''
    : String((finding as any)[field] ?? '')
  const missing = required && !value.trim()
  const width = field === 'code' ? 150 : field === 'units' ? 72 : 88
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={s.fieldLabel}>{FIELD_LABEL[field] || field}{required ? ' *' : ''}</span>
      {field === 'poa' ? (
        <select
          style={{ ...s.input, width, borderColor: missing ? '#dc2626' : value ? ACTION_COLOR.Add + '66' : '#e5e7eb' }}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); onEnter() } }}
          data-add-field={fieldId}
        >
          <option value="">POA</option>
          {POA_VALUES.map(v => <option key={v} value={v}>{v}</option>)}
        </select>
      ) : (
        <input
          style={{ ...s.input, width,
                   borderColor: missing ? '#dc2626' : value ? ACTION_COLOR.Add + '66' : '#e5e7eb' }}
          placeholder={FIELD_PLACEHOLDER[field] || FIELD_LABEL[field] || field}
          value={value}
          onChange={e => onChange(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); onEnter() } }}
          data-add-field={fieldId}
          autoFocus={autoFocus}
        />
      )}
    </div>
  )
}

function Field({ label, value, open, revision, strike, onChange }: {
  label: string
  value: string
  open: boolean
  revision?: Finding
  strike?: boolean
  onChange: (v: string) => void
}) {
  const changed = !!revision
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={s.fieldLabel}>{label}</span>
      {open ? (
        <input
          style={{ ...s.input, width: label === 'Code' ? 130 : 82,
                   borderColor: changed ? ACTION_COLOR.Revise : '#e5e7eb',
                   background: changed ? ACTION_COLOR.Revise + '0e' : '#fff',
                   boxShadow: changed ? `0 0 0 3px ${ACTION_COLOR.Revise}1f` : 'none',
                   fontWeight: changed ? 700 : 400 }}
          value={revision?.correct_value ?? value}
          onChange={e => onChange(e.target.value.toUpperCase())}
          placeholder={value || '—'}
        />
      ) : (
        <code style={{ ...s.codeChip, textDecoration: strike ? 'line-through' : 'none',
                       color: strike ? '#9ca3af' : '#111' }}>
          {value || '—'}
        </code>
      )}
      {changed && <span style={s.wasNote}>was {value || '—'}</span>}
    </div>
  )
}

/**
 * One control with two states rather than two independent pills.
 *
 * A verdict is a single choice, and two separate buttons let it look as though
 * neither has been given — which is exactly the state the submit gate cares
 * about. A segmented control shows the unanswered case as one empty track.
 */
function Segmented<T extends string | boolean>({ value, onChange, options }: {
  value: T | undefined
  onChange: (v: T) => void
  options: { value: T; label: string; tone: string }[]
}) {
  return (
    <div style={s.segment}>
      {options.map(o => {
        const on = value === o.value
        return (
          <button key={String(o.value)} onClick={() => onChange(o.value)}
            style={{
              ...s.segmentBtn,
              color: on ? '#fff' : '#6b7280',
              background: on ? o.tone : 'transparent',
              boxShadow: on ? '0 1px 3px rgba(0,0,0,0.16)' : 'none',
            }}>
            {on && <Check size={12} />}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

// ── after submission ─────────────────────────────────────────────────────────

function SubmittedView({ outcome, name }: {
  outcome: { summary: AuditSummary; results: AuditResultRow[]; show: boolean } | null
  name: string
}) {
  const summary = outcome?.summary
  return (
    <div style={s.center}>
      <div style={{ ...s.card, maxWidth: 720, gap: 18 }}>
        <CheckCircle size={38} color="#059669" />
        <div style={{ fontWeight: 800, fontSize: 20 }}>Audit submitted</div>
        <div style={{ fontSize: 13, color: '#6b7280' }}>Thank you, {name}.</div>

        {outcome?.show && summary?.charts ? (
          <>
            <div style={s.scoreRow}>
              <Stat label="Audit accuracy" value={`${summary.audit_accuracy}%`} big />
              <Stat label="Add" value={pct(summary.add_accuracy)} sub={`${summary.add_found}/${summary.add_planted}`} />
              <Stat label="Revise" value={pct(summary.revise_accuracy)} sub={`${summary.revise_found}/${summary.revise_planted}`} />
              <Stat label="Delete" value={pct(summary.delete_accuracy)} sub={`${summary.delete_found}/${summary.delete_planted}`} />
            </div>
            {summary.verdict_withheld_reason && (
              <div style={s.noteBox}>{summary.verdict_withheld_reason}</div>
            )}
            {outcome.results.length > 0 && (
              <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {outcome.results.map(r => (
                  <div key={r.chart_id} style={s.resultRow}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{r.chart_number}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, color: r.audit_accuracy >= 90 ? '#059669' : '#dc2626' }}>
                      {r.audit_accuracy}%
                    </span>
                    <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 'auto' }}>
                      {r.missed.length > 0 ? `${r.missed.length} missed` : 'nothing missed'}
                      {r.detected_not_corrected.length > 0 ? ` · ${r.detected_not_corrected.length} corrected wrongly` : ''}
                      {r.over_calls > 0 ? ` · ${r.over_calls} extra call(s)` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <div style={{ fontSize: 13, color: '#6b7280', textAlign: 'center', lineHeight: 1.6 }}>
            Your trainer will review your findings and share your results.
          </div>
        )}
        <div style={{ fontSize: 12, color: '#9ca3af' }}>You may now close this window.</div>
      </div>
    </div>
  )
}

function pct(v: number | null | undefined) {
  return v === null || v === undefined ? 'NA' : `${v}%`
}

function Stat({ label, value, sub, big }: { label: string; value: string; sub?: string; big?: boolean }) {
  return (
    <div style={{ textAlign: 'center', minWidth: 92 }}>
      <div style={{ fontSize: big ? 30 : 20, fontWeight: 800, color: value === 'NA' ? '#9ca3af' : '#111' }}>{value}</div>
      <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: '#9ca3af' }}>{sub}</div>}
    </div>
  )
}

const SECTION_LABEL: Record<string, string> = {
  PDx: 'Principal Diagnosis',
  SDx: 'Secondary Diagnoses',
  PCS: 'Procedures (ICD-10-PCS)',
  CPT: 'Procedures (CPT)',
}

/**
 * Colour carries the code CATEGORY, not the chart's condition.
 *
 * Diagnoses are indigo, procedures teal, so the two procedure sections read as
 * siblings and a coder scanning the page can tell what kind of code they are
 * looking at before reading the heading. This is safe against the blind-chart
 * rule that governs this screen: the hue is fixed per section, so a clean chart
 * and one carrying errors are still drawn identically.
 *
 * Action colour is separate and comes from ISSUE_COLORS, the same palette the
 * trainer screens use — Add red, Revise purple, Delete amber — so a finding
 * means the same thing wherever it is seen.
 */
type Theme = { accent: string; tint: string; line: string; kind: string }

const NEUTRAL: Theme = { accent: '#4b5563', tint: '#fafafa', line: '#e5e7eb', kind: '' }

const SECTION_THEME: Record<string, Theme> = {
  PDx: { accent: '#4338ca', tint: '#eef2ff', line: '#c7d2fe', kind: 'Diagnosis' },
  SDx: { accent: '#5b21b6', tint: '#f5f3ff', line: '#ddd6fe', kind: 'Diagnosis' },
  PCS: { accent: '#0f766e', tint: '#f0fdfa', line: '#99f6e4', kind: 'Procedure' },
  CPT: { accent: '#0e7490', tint: '#ecfeff', line: '#a5f3fc', kind: 'Procedure' },
}

const themeOf = (key: string): Theme => SECTION_THEME[key] || NEUTRAL

const ACTION_COLOR = {
  Add: ISSUE_COLORS.Missed,
  Revise: ISSUE_COLORS.Wrong_Code,
  Delete: ISSUE_COLORS.Over_coded,
} as const

const FIELD_LABEL: Record<string, string> = {
  code: 'Code', poa: 'POA', ccmcc: 'CC/MCC', modifier: 'Modifier', units: 'Units',
}

const FIELD_PLACEHOLDER: Record<string, string> = {
  code: 'Missing code',
  modifier: 'Modifier',
  units: 'Units',
}

const POA_VALUES = ['Y', 'N', 'U', 'W', '1']

const s: Record<string, React.CSSProperties> = {
  shell: { fontFamily: 'system-ui, sans-serif', display: 'flex', minHeight: '100vh', background: '#f9fafb' },
  sidebar: { width: 236, flexShrink: 0, borderRight: '1px solid #e5e7eb', background: '#f3f4f6', padding: '20px 14px', display: 'flex', flexDirection: 'column' },
  brand: { fontSize: 13, fontWeight: 800, color: '#9333ea' },
  who: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  chartTab: { display: 'flex', alignItems: 'center', gap: 8, padding: '9px 11px', border: 'none', borderRadius: 8, cursor: 'pointer', textAlign: 'left', width: '100%' },
  main: { flex: 1, overflowY: 'auto' },
  chartHead: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 6 },
  chartNum: { fontSize: 22, fontWeight: 800 },
  chartMeta: { fontSize: 13, color: '#6b7280' },
  copyBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', fontSize: 12, fontWeight: 600, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', cursor: 'pointer', color: '#4b5563' },
  intro: { fontSize: 13, color: '#6b7280', marginBottom: 20, lineHeight: 1.6 },
  section: { border: '1px solid #e5e7eb', borderRadius: 14, background: '#fff', marginBottom: 16, overflow: 'hidden', boxShadow: '0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)' },
  sectionHead: { display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px', borderBottom: '1px solid', flexWrap: 'wrap' },
  sectionName: { fontSize: 14.5, fontWeight: 750, letterSpacing: -0.2 },
  line: { display: 'flex', alignItems: 'flex-end', gap: 12, padding: '9px 10px', borderBottom: '1px solid #f3f4f6', flexWrap: 'wrap', borderRadius: 8, transition: 'background 120ms ease' },
  lineNo: { fontSize: 11, color: '#9ca3af', width: 16, paddingBottom: 6 },
  fieldLabel: { fontSize: 10, color: '#9ca3af', fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase' },
  codeChip: { fontFamily: 'ui-monospace, monospace', fontSize: 13, padding: '6px 10px', background: '#f9fafb', borderRadius: 6, display: 'inline-block', minWidth: 60 },
  input: { fontFamily: 'ui-monospace, monospace', fontSize: 13, padding: '6px 9px', border: '1px solid #e5e7eb', borderRadius: 6, outline: 'none', textTransform: 'uppercase' },
  wasNote: { fontSize: 10, color: '#7c3aed', fontWeight: 600 },
  eyebrow: { fontSize: 9.5, fontWeight: 800, letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 3, opacity: 0.75 },
  countPill: { fontSize: 10.5, fontWeight: 700, padding: '2px 8px', borderRadius: 999, border: '1px solid', background: '#fff' },
  actionChip: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10.5, fontWeight: 800, padding: '2px 8px', borderRadius: 999, border: '1px solid' },
  tagChip: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 800, padding: '3px 8px', borderRadius: 999 },
  rowAction: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 700, padding: '5px 10px', borderRadius: 8, border: '1px solid', cursor: 'pointer', transition: 'opacity 120ms ease' },
  segment: { display: 'inline-flex', gap: 3, padding: 3, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10 },
  segmentBtn: { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '6px 12px', fontSize: 12, fontWeight: 700, border: 'none', borderRadius: 8, cursor: 'pointer', transition: 'all 130ms ease' },
  lockedNote: { fontSize: 12, color: '#9ca3af', marginLeft: 'auto' },
  emptyRow: { fontSize: 12.5, color: '#9ca3af', padding: '6px 0' },
  addRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, padding: '8px 10px', borderRadius: 8 },
  addBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 13px', fontSize: 12, fontWeight: 700, border: '1px dashed', borderRadius: 9, background: '#fff', cursor: 'pointer' },
  iconBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', padding: 4, display: 'flex' },
  textarea: { width: '100%', boxSizing: 'border-box', height: 74, resize: 'vertical', fontFamily: 'system-ui, sans-serif', fontSize: 13, padding: '9px 11px', border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 10 },
  hintBox: { display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: 10, padding: '10px 12px', borderRadius: 8, border: '1px solid' },
  saveBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '9px 14px', border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  reviewBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '10px 14px', border: 'none', borderRadius: 8, background: 'linear-gradient(135deg, #be185d, #9333ea)', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  center: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f9fafb', fontFamily: 'system-ui, sans-serif', padding: 20 },
  card: { background: '#fff', borderRadius: 16, padding: '32px 30px', display: 'flex', flexDirection: 'column', alignItems: 'center', boxShadow: '0 8px 32px rgba(0,0,0,0.08)', width: '100%' },
  spinner: { width: 30, height: 30, border: '3px solid #e5e7eb', borderTopColor: '#9333ea', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },
  toast: { position: 'fixed', top: 18, left: '50%', transform: 'translateX(-50%)', background: '#111', color: '#fff', padding: '10px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600, zIndex: 50 },
  reviewPage: { fontFamily: 'system-ui, sans-serif', maxWidth: 720, margin: '0 auto', padding: '32px 20px' },
  reviewTitle: { fontSize: 22, fontWeight: 800, marginTop: 20 },
  reviewSub: { fontSize: 14, color: '#6b7280', marginBottom: 20 },
  reviewRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', border: '1px solid', borderRadius: 10 },
  backBtn: { border: 'none', background: 'none', color: '#6b7280', fontSize: 13, cursor: 'pointer', padding: 0 },
  linkBtn: { fontSize: 12, color: '#9333ea', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 },
  blockBox: { display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 12, padding: '12px 14px', borderRadius: 10, background: '#fef2f2', border: '1px solid #fecaca' },
  submitBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, width: '100%', padding: '13px', border: 'none', borderRadius: 10, background: 'linear-gradient(135deg, #be185d, #9333ea)', color: '#fff', fontSize: 15, fontWeight: 700, cursor: 'pointer' },
  scoreRow: { display: 'flex', gap: 22, alignItems: 'flex-end', flexWrap: 'wrap', justifyContent: 'center' },
  noteBox: { fontSize: 12, color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '8px 12px', textAlign: 'center' },
  resultRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: 8 },
}
