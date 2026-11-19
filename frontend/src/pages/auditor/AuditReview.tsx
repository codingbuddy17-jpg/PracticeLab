import { useCallback, useEffect, useState } from 'react'
import { useCodeDescriptions } from '../../hooks/useCodeDescriptions'
import toast from 'react-hot-toast'
import { AlertTriangle, CheckCircle, ChevronDown, ChevronLeft, ChevronRight, Circle, XCircle } from 'lucide-react'
import { getAuditReview } from '../../api/auditorApi'
import { ISSUE_COLORS } from '../practicelab/shared'
import s from './styles'
import { REVIEW_STATUS } from '../../theme'

/**
 * What one auditor did, chart by chart.
 *
 * The backend has carried this since the module was built and nothing reached
 * it — a trainer could see a score and never the reasoning behind it. Every
 * error introduced is shown beside what the auditor did about it, which is the
 * only view that answers "why did they get 60%".
 *
 * This is the trainer's screen, so it names chart types and sources. The
 * auditor's own results never do.
 */

// The practice review's colours (theme.REVIEW_STATUS), so green, red and amber
// mean the same thing on every review screen in the app.
const OUTCOME = {
  correct: { label: 'Found and corrected', color: REVIEW_STATUS.correct.color, Icon: CheckCircle },
  detected_not_corrected: { label: 'Found, corrected wrongly', color: REVIEW_STATUS.different.color, Icon: Circle },
  missed: { label: 'Missed', color: REVIEW_STATUS.missed.color, Icon: XCircle },
} as const

const ACTION_COLORS: Record<string, string> = {
  Add: ISSUE_COLORS.Missed,
  Revise: ISSUE_COLORS.Wrong_Code,
  Delete: ISSUE_COLORS.Over_coded,
}

export function AuditReview({ sessionId, onBack }: {
  sessionId: number; onBack: () => void
}) {
  const [data, setData] = useState<any>(null)
  // Found-and-corrected lines fold away per chart, as correct lines do on the
  // practice review: what cost points is open, the rest is one click.
  const [showCorrect, setShowCorrect] = useState<Record<number, boolean>>({})

  const load = useCallback(async () => {
    try { setData(await getAuditReview(sessionId)) }
    catch { toast.error('Could not load this review') }
  }, [sessionId])
  useEffect(() => { load() }, [load])

  // What the codes in each planting and finding MEAN — the evidence a trainer
  // weighs when judging the auditor. Only where the field is the code itself:
  // a POA, modifier or units value is not a code. Above the early return.
  const codeRows = (data?.charts || []).flatMap((c: any) => (c.outcomes || []).map((o: any) =>
    o.outcome === 'over_call' ? o.finding || {} : o.planting || {}))
    .filter((r: any) => !r.field || r.field === 'code')
  const codesFor = (secs: string[]) => codeRows.filter((r: any) => secs.includes(r.section))
    .flatMap((r: any) => [r.claim_value, r.correct_value]).filter(Boolean)
  const describeDx = useCodeDescriptions(codesFor(['PDx', 'SDx']), 'SDx')
  const describePcs = useCodeDescriptions(codesFor(['PCS']), 'PCS')
  const describeCpt = useCodeDescriptions(codesFor(['CPT']), 'CPT')
  const meaning = (r: any) => {
    if (r.field && r.field !== 'code') return null
    const fn = r.section === 'PCS' ? describePcs : r.section === 'CPT' ? describeCpt
      : (r.section === 'PDx' || r.section === 'SDx') ? describeDx : null
    if (!fn) return null
    const parts = [r.claim_value, r.correct_value].filter(Boolean)
      .map((c: string) => ({ c, d: fn(c)?.description || '' })).filter(x => x.d)
    if (!parts.length) return null
    return (
      <div style={s.codeMeaning}>
        {parts.map(x => (
          <div key={x.c} title={`${x.c} — ${x.d}`} style={s.codeMeaningLine}>
            <code>{x.c}</code> {x.d}
          </div>
        ))}
      </div>
    )
  }

  if (!data) return <div style={s.empty}>Loading…</div>
  const sum = data.summary || {}

  return (
    <div>
      <button style={s.backBtn} onClick={onBack}>
        <ChevronLeft size={14} /> Back to batch
      </button>
      <div style={s.h1}>{data.auditor_name}</div>
      <div style={s.sub}>
        {data.emp_id ? `${data.emp_id} · ` : ''}{data.specialty} · {data.status}
        {data.submitted_at
          ? ` · submitted ${new Date(data.submitted_at).toLocaleString()}` : ''}
      </div>

      <div style={s.panel}>
        <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>Session</span></div>
        <div style={{ padding: '16px', display: 'flex', gap: 26, flexWrap: 'wrap' }}>
          <Stat label="Audit accuracy" value={pct(sum.audit_accuracy)} big />
          <Stat label="Clean charts" value={pct(sum.clean_accuracy)}
            sub={`${sum.clean_charts ?? 0} — restraint`} />
          <Stat label="Opportunity charts" value={pct(sum.opportunity_accuracy)}
            sub={`${sum.opportunity_charts ?? 0} — detection`} />
          <Stat label="Add" value={pct(sum.add_accuracy)}
            sub={sum.add_planted ? `${sum.add_found}/${sum.add_planted}` : 'none'} />
          <Stat label="Revise" value={pct(sum.revise_accuracy)}
            sub={sum.revise_planted ? `${sum.revise_found}/${sum.revise_planted}` : 'none'} />
          <Stat label="Delete" value={pct(sum.delete_accuracy)}
            sub={sum.delete_planted ? `${sum.delete_found}/${sum.delete_planted}` : 'none'} />
        </div>
      </div>

      {(data.charts || []).map((c: any, ci: number) => (
        <div key={c.chart_id} style={s.panel}>
          <div style={s.panelHead}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>{c.chart_number}</span>
            <span style={{ ...s.tag, background: c.chart_type === 'clean' ? '#eff6ff' : '#f5f3ff',
                           color: c.chart_type === 'clean' ? '#2563eb' : '#7c3aed' }}>
              {c.chart_type === 'clean' ? 'Clean — nothing to find' : c.source}
            </span>
            <span style={{ marginLeft: 'auto', fontWeight: 700, fontSize: 14,
                           color: tone(c.audit_accuracy) }}>
              {c.audit_accuracy}%
            </span>
          </div>
          <div style={{ padding: '12px 16px' }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 11.5,
                          color: '#6b7280', marginBottom: 10 }}>
              {Object.entries(c.section_verdicts || {}).map(([sec, v]) => (
                <span key={sec}>
                  <strong>{sec}</strong>{' '}
                  {v === 'needs_changes' ? 'needs changes' : 'no changes'}
                </span>
              ))}
              {c.over_calls > 0 && (
                <span style={{ color: REVIEW_STATUS.missed.color, fontWeight: 600 }}>
                  {c.over_calls} finding(s) on correct items
                  {c.over_call_deduction ? ` · −${c.over_call_deduction}%` : ''}
                </span>
              )}
              {c.query_correct === false && (
                <span style={{ color: REVIEW_STATUS.missed.color, fontWeight: 600 }}>
                  query {c.query_expected ? 'was needed and not raised' : 'raised unnecessarily'}
                </span>
              )}
              {c.drg_impacting_planted > 0 && (
                <span style={{ color: c.drg_impacting_found === c.drg_impacting_planted
                                 ? REVIEW_STATUS.correct.color : REVIEW_STATUS.missed.color, fontWeight: 600 }}>
                  DRG-impacting {c.drg_impacting_found}/{c.drg_impacting_planted}
                </span>
              )}
            </div>

            {(c.outcomes || []).length === 0 ? (
              <div style={{ fontSize: 12.5, color: '#9ca3af' }}>
                Nothing was introduced in this chart.
                {c.over_calls > 0
                  ? ' The auditor raised findings anyway.'
                  : ' The auditor correctly left it alone.'}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {(c.outcomes || []).map((o: any, i: number) => {
                  if (o.outcome === 'correct' && !showCorrect[ci]) return null
                  // An over-call has no planting — nothing was introduced
                  // where the auditor raised a finding, which is exactly what
                  // makes it an over-call. Rendering it through the planting
                  // path printed "undefined should be undefined".
                  if (o.outcome === 'over_call') {
                    const f = o.finding || {}
                    return (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 8px', borderRadius: 6, background: REVIEW_STATUS.extra.bg }}>
                        <AlertTriangle size={14} color={REVIEW_STATUS.extra.color} style={{ flexShrink: 0, marginTop: 2 }} />
                        <div style={{ fontSize: 12, lineHeight: 1.5, minWidth: 0, flex: 1 }}>
                          <strong style={{ color: REVIEW_STATUS.extra.color }}>Over-call</strong>{' '}
                          {f.section}
                          {f.field && f.field !== 'code' ? ` ${f.field}` : ''}
                          {typeof f.line === 'number' ? ` line ${f.line + 1}` : ''}
                          {' — flagged '}
                          <code>{f.claim_value || '—'}</code>
                          {f.correct_value ? <> as <code>{f.correct_value}</code></> : null}
                          <span style={{ color: '#9ca3af' }}> · nothing was wrong here</span>
                          {meaning(f)}
                        </div>
                      </div>
                    )
                  }
                  const p = o.planting || {}
                  const cfg = OUTCOME[o.outcome as keyof typeof OUTCOME] || OUTCOME.missed
                  const Icon = cfg.Icon
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8,
                                          padding: '6px 8px', borderRadius: 6,
                                          background: o.outcome === 'correct' ? '#f8fafc' : '#fffafa' }}>
                      <Icon size={14} color={cfg.color} style={{ flexShrink: 0, marginTop: 2 }} />
                      <div style={{ fontSize: 12, lineHeight: 1.5, minWidth: 0, flex: 1 }}>
                        <strong style={{ color: ACTION_COLORS[p.action] || '#374151' }}>
                          {p.action}
                        </strong>{' '}
                        {p.section}
                        {p.field && p.field !== 'code' ? ` ${p.field}` : ''}
                        {typeof p.line === 'number' && p.action !== 'Add'
                          ? ` line ${p.line + 1}` : ''}
                        {' — '}
                        {p.action === 'Add' ? p.correct_value
                          : p.action === 'Delete' ? p.claim_value
                            : `${p.claim_value} should be ${p.correct_value}`}
                        {p.pcs_character ? ` (${p.pcs_character})` : ''}
                        {p.drg_impacting && (
                          <span style={{ ...s.tag, marginLeft: 6, background: '#fee2e2', color: '#b91c1c' }}>
                            DRG
                          </span>
                        )}
                        {p.origin === 'observed' && (
                          <span style={s.observedTag}>
                            seen in {p.observed_coders} coder submission(s)
                          </span>
                        )}
                        <span style={{ marginLeft: 8, color: cfg.color, fontWeight: 600 }}>
                          {cfg.label}
                        </span>
                        {meaning(p)}
                      </div>
                    </div>
                  )
                })}
                {(() => {
                  const n = (c.outcomes || []).filter((o: any) => o.outcome === 'correct').length
                  if (!n) return null
                  const open = !!showCorrect[ci]
                  return (
                    <button onClick={() => setShowCorrect(m => ({ ...m, [ci]: !open }))}
                      style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: REVIEW_STATUS.correct.color }}>
                      {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      {open ? 'Hide' : 'Show'} {n} found and corrected
                    </button>
                  )
                })()}
              </div>
            )}

            {c.query_text && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#374151' }}>
                <strong>Their query:</strong> {c.query_text}
              </div>
            )}
            {c.auditor_notes && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>
                {c.auditor_notes}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function Stat({ label, value, sub, big }: {
  label: string; value: string; sub?: string; big?: boolean
}) {
  return (
    <div style={{ minWidth: 96 }}>
      <div style={{ fontSize: big ? 30 : 20, fontWeight: 800, lineHeight: 1.1,
                    color: value === 'NA' ? '#9ca3af' : '#111' }}>{value}</div>
      <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 700, marginTop: 3 }}>{label}</div>
      {sub && <div style={{ fontSize: 10.5, color: '#9ca3af' }}>{sub}</div>}
    </div>
  )
}

/** NA is a real value — nothing of that kind was in the session. */
function pct(v: number | null | undefined) {
  return v === null || v === undefined ? 'NA' : `${v}%`
}

function tone(v: number | null | undefined) {
  if (v === null || v === undefined) return '#9ca3af'
  return v >= 90 ? REVIEW_STATUS.correct.color : v >= 70 ? REVIEW_STATUS.different.color : REVIEW_STATUS.missed.color
}
