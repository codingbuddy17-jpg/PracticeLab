import { ChevronDown, ChevronRight, Download, Flag } from 'lucide-react'
import { REVIEW_STATUS, passFailStyle, reviewScoreColor } from '../theme'
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
 *
 * The standard for every specialty (CR-011-Nov): the chart header and the rows
 * that cost or could cost points are open; correct rows fold behind one line
 * per section. There is no separate "Scoring notes" block — every fact it held
 * (POA, pointers, CC/MCC weight, ED level) is on the row it concerns, so the
 * same finding is never shown twice.
 */

export type ReviewStatus = 'correct' | 'wrong' | 'missed' | 'extra' | 'different' | 'order' | 'info'

export interface ReviewRow {
  item: string; key: string; coded: string; status: ReviewStatus; note: string
  key_desc?: string; coded_desc?: string
  weight?: 'CC' | 'MCC'
}
export interface ReviewSection {
  key: string; title: string; group: 'Coding' | 'Reasoning'
  points: number | null; max_points: number | null; note: string | null
  rows: ReviewRow[]
}
export interface ChartReview {
  sections: ReviewSection[]
  summary: { correct: number; wrong?: number; missed: number; extra: number; different: number }
}

const STATUS: Record<ReviewStatus, { label: string; color: string; bg: string }> = REVIEW_STATUS

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
  // Fixed layout: columns keep their share however long a description is, so
  // a ninety-character PCS title wraps inside its cell instead of widening it.
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 12, tableLayout: 'fixed' as const },
  th: { textAlign: 'left' as const, fontSize: 10, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, padding: '6px 12px', borderBottom: '1px solid #f3f4f6' },
  td: { padding: '6px 12px', borderBottom: '1px solid #f3f4f6', verticalAlign: 'top' as const },
  code: { fontFamily: 'ui-monospace, monospace', color: '#111827', overflowWrap: 'anywhere' as const },
  // Two lines at most; the full text is on hover.
  desc: {
    fontFamily: 'system-ui, sans-serif', fontSize: 11, lineHeight: 1.35, color: '#6b7280', marginTop: 2,
    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden',
  },
  note: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  empty: { fontSize: 12, color: '#9ca3af', padding: '6px 12px' },
  toggle: { display: 'flex', alignItems: 'center', gap: 4, width: '100%', padding: '6px 12px', background: '#fcfcfd', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: STATUS.correct.color, textAlign: 'left' as const },
  weight: { fontFamily: 'system-ui, sans-serif', fontSize: 9.5, fontWeight: 800, letterSpacing: 0.3, padding: '1px 5px', borderRadius: 4, marginLeft: 6 },
  mcc: { background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' },
  cc: { background: '#fef3c7', color: '#92400e', border: '1px solid #fcd34d' },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 18px' },
  head: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const },
  badge: { fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6 },
}

/**
 * The one header every review card opens with, for every specialty: chart,
 * score, PASS/FAIL, flag, then whatever that screen adds (status badges, the
 * E/M coding + reasoning sum). Same sizes and the same colours everywhere.
 */
export function ReviewHeader({ chartNumber, score, passFail, flagged, children }: {
  chartNumber: string; score?: number | null; passFail?: string | null
  flagged?: boolean; children?: any
}) {
  const pf = passFailStyle(passFail)
  return (
    <div style={s.head}>
      <span style={{ fontWeight: 700, fontSize: 14 }}>{chartNumber}</span>
      {score !== null && score !== undefined && (
        <span style={{ fontWeight: 800, fontSize: 15, color: reviewScoreColor(score) }}>{Number(score).toFixed(1)}%</span>
      )}
      {passFail && <span style={{ ...s.badge, color: pf.color, background: pf.bg }}>{passFail}</span>}
      {flagged && <span title="Flagged by the coder"><Flag size={13} color="#d97706" /></span>}
      {children}
    </div>
  )
}

/** The card a chart's review sits in, on every screen. */
export const reviewCardStyle = s.card

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
        {(['correct', 'wrong', 'missed', 'extra', 'different'] as const).map(k => {
          const n = (summary as any)[k] || 0
          if (!n && k !== 'correct') return null
          const label = { correct: 'correct', wrong: 'wrong code', missed: 'missed', extra: 'extra', different: 'differ' }[k]
          return <span key={k} style={{ ...s.chip, color: STATUS[k].color, background: STATUS[k].bg }}>{n} {label}</span>
        })}
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
  const [showCorrect, setShowCorrect] = useState(false)
  const nCorrect = sec.rows.filter(r => r.status === 'correct').length
  // Correct rows fold away only when something else is left to read; a
  // section that is all correct still shows one line saying so.
  const rows = showCorrect ? sec.rows : sec.rows.filter(r => r.status !== 'correct')
  return (
    <div style={{ ...s.section, borderLeft: `3px solid ${accent}` }}>
      <div style={s.secHead}>
        <span style={s.secTitle}>{sec.title}</span>
        {pts && <span style={s.secPts}>{pts}</span>}
      </div>
      {sec.note && <div style={s.secNote}>{sec.note}</div>}
      {sec.rows.length === 0 ? (
        !sec.note && <div style={s.empty}>Nothing coded or expected.</div>
      ) : (<>
        {rows.length > 0 && (
        <table style={s.table}>
          <thead>
            <tr>
              <th style={{ ...s.th, width: '24%' }}>Item</th>
              <th style={{ ...s.th, width: '27%' }}>Answer key</th>
              <th style={{ ...s.th, width: '27%' }}>Coded</th>
              <th style={{ ...s.th, width: '22%' }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const st = STATUS[r.status] || STATUS.info
              return (
                <tr key={i}>
                  <td style={s.td}>{r.item}</td>
                  <CodeCell code={r.key} desc={r.key_desc} weight={r.weight} />
                  {/* Same code both sides: say what it means once, not twice. */}
                  <CodeCell code={r.coded}
                    desc={sameCode(r.key, r.coded) ? '' : r.coded_desc} />
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
        {nCorrect > 0 && (
          <button onClick={() => setShowCorrect(v => !v)} style={s.toggle}>
            {showCorrect ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {showCorrect ? 'Hide' : 'Show'} {nCorrect} correct {nCorrect === 1 ? 'line' : 'lines'}
          </button>
        )}
      </>)}
    </div>
  )
}

/**
 * A describe() for GradingFeedback, built from descriptions the review already
 * carries — so the Scoring notes beside a review need no second lookup.
 */
export function describeFromReview(review?: ChartReview | null) {
  const map: Record<string, string> = {}
  for (const sec of review?.sections || []) {
    for (const r of sec.rows) {
      const k = (r.key || '').split('  ')[0].replace(/\./g, '').toUpperCase()
      const c = (r.coded || '').split('  ')[0].replace(/\./g, '').toUpperCase()
      if (k && r.key_desc) map[k] = r.key_desc
      if (c && r.coded_desc) map[c] = r.coded_desc
    }
  }
  return (code: string) => {
    const d = map[(code || '').replace(/\./g, '').toUpperCase()]
    return d ? { description: d } : null
  }
}

function sameCode(a: string, b: string) {
  const norm = (x: string) => (x || '').split('  ')[0].replace(/\./g, '').toUpperCase()
  return !!a && norm(a) === norm(b)
}

function CodeCell({ code, desc, weight }: { code: string; desc?: string; weight?: string }) {
  return (
    <td style={s.td}>
      <div style={s.code}>
        {code || '—'}
        {weight && (
          <span title={weight === 'MCC' ? 'Major complication or comorbidity — moves the DRG' : 'Complication or comorbidity — can move the DRG'}
            style={{ ...s.weight, ...(weight === 'MCC' ? s.mcc : s.cc) }}>{weight}</span>
        )}
      </div>
      {desc && <div style={s.desc} title={desc}>{desc}</div>}
    </td>
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
