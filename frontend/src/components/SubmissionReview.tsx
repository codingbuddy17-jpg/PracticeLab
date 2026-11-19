import { Download } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { downloadPracticeReview, downloadPracticeReviewByToken } from '../api/practicelabApi'

/**
 * The post-submit review of one chart: every line the key and the coder
 * produced, side by side — what was right as well as what was wrong.
 *
 * Built server-side (services/practice_review.py) so this screen, the coder's
 * results screen and the Excel export all show the same thing. This component
 * only draws it. Sections arrive already classified: Coding (E/M level, primary
 * and secondary diagnoses, CPT) and, for E/M, Reasoning — COPA, Data Review and
 * Risk element by element, or Time.
 */

export type ReviewStatus = 'correct' | 'missed' | 'extra' | 'different' | 'order' | 'info'

export interface ReviewRow { item: string; key: string; coded: string; status: ReviewStatus; note: string }
export interface ReviewSection {
  key: string; title: string; group: 'Coding' | 'Reasoning'
  points: number | null; max_points: number | null; note: string | null
  rows: ReviewRow[]
}
export interface ChartReview {
  sections: ReviewSection[]
  summary: { correct: number; missed: number; extra: number; different: number }
}

const STATUS: Record<ReviewStatus, { label: string; color: string; bg: string }> = {
  correct:   { label: '✓ Correct',  color: '#047857', bg: '#ecfdf5' },
  missed:    { label: '✗ Missed',   color: '#b91c1c', bg: '#fef2f2' },
  extra:     { label: '+ Extra',    color: '#9a3412', bg: '#fff7ed' },
  different: { label: '≠ Differs',  color: '#92400e', bg: '#fffbeb' },
  order:     { label: '↕ Order only', color: '#1e40af', bg: '#eff6ff' },
  info:      { label: '',           color: '#6b7280', bg: 'transparent' },
}

const GROUP_ACCENT = { Coding: '#5b21b6', Reasoning: '#065f46' }

const s = {
  wrap: { display: 'flex', flexDirection: 'column' as const, gap: 10, marginTop: 8 },
  summary: { display: 'flex', gap: 6, flexWrap: 'wrap' as const, alignItems: 'center' },
  chip: { fontSize: 11, fontWeight: 700, borderRadius: 6, padding: '2px 8px' },
  groupHead: { fontSize: 11, fontWeight: 800, textTransform: 'uppercase' as const, letterSpacing: 0.6, marginTop: 4 },
  section: { border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' },
  secHead: { display: 'flex', alignItems: 'baseline', gap: 10, padding: '7px 12px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb' },
  secTitle: { fontSize: 13, fontWeight: 700, color: '#111827', flex: 1 },
  secPts: { fontSize: 12, fontWeight: 700, color: '#374151' },
  secNote: { fontSize: 11, color: '#6b7280', padding: '6px 12px', background: '#fcfcfd', borderBottom: '1px solid #f3f4f6' },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 12 },
  th: { textAlign: 'left' as const, fontSize: 10, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, padding: '6px 12px', borderBottom: '1px solid #f3f4f6' },
  td: { padding: '6px 12px', borderBottom: '1px solid #f3f4f6', verticalAlign: 'top' as const },
  code: { fontFamily: 'ui-monospace, monospace', color: '#111827' },
  note: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  empty: { fontSize: 12, color: '#9ca3af', padding: '6px 12px' },
}

function fmtPts(sec: ReviewSection) {
  if (sec.points === null || sec.points === undefined) return null
  return sec.max_points !== null && sec.max_points !== undefined
    ? `${sec.points.toFixed(1)} of ${sec.max_points.toFixed(1)} pts`
    : `${sec.points.toFixed(1)} pts`
}

export function SubmissionReview({ review }: { review?: ChartReview | null }) {
  if (!review || !review.sections?.length) return null
  const groups: Array<'Coding' | 'Reasoning'> = ['Coding', 'Reasoning']
  const { summary } = review
  return (
    <div style={s.wrap}>
      <div style={s.summary}>
        <span style={{ ...s.chip, color: STATUS.correct.color, background: STATUS.correct.bg }}>{summary.correct} correct</span>
        <span style={{ ...s.chip, color: STATUS.missed.color, background: STATUS.missed.bg }}>{summary.missed} missed</span>
        <span style={{ ...s.chip, color: STATUS.extra.color, background: STATUS.extra.bg }}>{summary.extra} extra</span>
        <span style={{ ...s.chip, color: STATUS.different.color, background: STATUS.different.bg }}>{summary.different} differ</span>
      </div>
      {groups.map(g => {
        const secs = review.sections.filter(x => x.group === g)
        if (!secs.length) return null
        return (
          <div key={g} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {review.sections.some(x => x.group === 'Reasoning') && (
              <div style={{ ...s.groupHead, color: GROUP_ACCENT[g] }}>{g === 'Coding' ? 'Coding' : 'Reasoning (MDM / Time)'}</div>
            )}
            {secs.map(sec => <Section key={sec.key} sec={sec} accent={GROUP_ACCENT[g]} />)}
          </div>
        )
      })}
    </div>
  )
}

function Section({ sec, accent }: { sec: ReviewSection; accent: string }) {
  const pts = fmtPts(sec)
  return (
    <div style={{ ...s.section, borderLeft: `3px solid ${accent}` }}>
      <div style={s.secHead}>
        <span style={s.secTitle}>{sec.title}</span>
        {pts && <span style={s.secPts}>{pts}</span>}
      </div>
      {sec.note && <div style={s.secNote}>{sec.note}</div>}
      {sec.rows.length === 0 ? (
        !sec.note && <div style={s.empty}>Nothing coded or expected.</div>
      ) : (
        <table style={s.table}>
          <thead>
            <tr>
              <th style={{ ...s.th, width: '34%' }}>Item</th>
              <th style={{ ...s.th, width: '20%' }}>Answer key</th>
              <th style={{ ...s.th, width: '20%' }}>Coded</th>
              <th style={s.th}>Result</th>
            </tr>
          </thead>
          <tbody>
            {sec.rows.map((r, i) => {
              const st = STATUS[r.status] || STATUS.info
              return (
                <tr key={i}>
                  <td style={s.td}>{r.item}</td>
                  <td style={{ ...s.td, ...s.code }}>{r.key || '—'}</td>
                  <td style={{ ...s.td, ...s.code }}>{r.coded || '—'}</td>
                  <td style={s.td}>
                    {st.label && <span style={{ ...s.chip, color: st.color, background: st.bg }}>{st.label}</span>}
                    {r.note && <div style={s.note}>{r.note}</div>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

/**
 * Download the review as a formatted workbook. Two URLs: the trainer's by
 * session, the coder's by their own access code (refused until results are
 * released, as the results screen is).
 */
export function ReviewExportButton({ sessionId, token, coderName }: {
  sessionId?: number; token?: string; coderName?: string
}) {
  const [busy, setBusy] = useState(false)
  const safe = (coderName || 'coder').replace(/[^A-Za-z0-9]+/g, '_')
  async function go() {
    setBusy(true)
    try {
      const name = `PracticeReview_${safe}.xlsx`
      if (token) await downloadPracticeReviewByToken(token, name)
      else if (sessionId) await downloadPracticeReview(sessionId, name)
    } catch (e: any) {
      toast.error(e?.message || 'Export failed')
    }
    setBusy(false)
  }
  return (
    <button
      onClick={go}
      disabled={busy}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#fff', color: '#047857', border: '1.5px solid #10b981', borderRadius: 8, cursor: busy ? 'wait' : 'pointer', fontWeight: 700, fontSize: 13, opacity: busy ? 0.7 : 1 }}
    >
      <Download size={14} /> {busy ? 'Preparing…' : 'Export to Excel'}
    </button>
  )
}
