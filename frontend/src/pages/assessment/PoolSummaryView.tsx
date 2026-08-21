import { useState, useEffect, useCallback } from 'react'
import { BarChart2, AlertTriangle, RefreshCw, Upload, Wand2 } from 'lucide-react'
import { getAssessmentPoolSummary } from '../../api'
import type { PoolSummary, PoolReadiness } from '../../api'
import { errorMessage } from '../../api/errors'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E/M', 'E/M - Multispecialty', 'IVR', 'Anesthesia',
]

const DIFF_COLORS: Record<string, string> = {
  Easy: '#16a34a',
  Medium: '#d97706',
  Hard: '#dc2626',
}

/** Topics shown before the trainer asks for the rest. */
const TOPIC_CAP = 20

const VERDICT: Record<PoolReadiness['verdict'], { label: string; color: string; bg: string; border: string }> = {
  insufficient:   { label: 'Not enough questions', color: '#b91c1c', bg: 'rgba(220,38,38,0.08)', border: 'rgba(220,38,38,0.25)' },
  near_identical: { label: 'Papers near-identical', color: '#b91c1c', bg: 'rgba(220,38,38,0.08)', border: 'rgba(220,38,38,0.25)' },
  heavy_overlap:  { label: 'Heavy overlap',         color: '#c2410c', bg: 'rgba(234,88,12,0.08)', border: 'rgba(234,88,12,0.25)' },
  workable:       { label: 'Workable',              color: '#0369a1', bg: 'rgba(2,132,199,0.08)', border: 'rgba(2,132,199,0.22)' },
  strong:         { label: 'Strong',                color: '#15803d', bg: 'rgba(22,163,74,0.08)', border: 'rgba(22,163,74,0.22)' },
}

export function PoolSummaryView({ onJump, initialSpecialty }: {
  /** Carry the chosen specialty into Upload or Generate. */
  onJump?: (tab: 'upload' | 'generate', specialty: string) => void
  /** Specialty handed over from another tab — usually straight after upload. */
  initialSpecialty?: string
} = {}) {
  const [specialty, setSpecialty] = useState(initialSpecialty || '')
  const [summary, setSummary] = useState<PoolSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showAllTopics, setShowAllTopics] = useState(false)

  // The paper you intend to generate. Readiness is meaningless without it — 30
  // questions is thin for a 25-question paper and generous for a 5-question
  // one, so a fixed "50+ is healthy" rule answers the wrong question.
  const [perPaper, setPerPaper] = useState(25)
  const [coders, setCoders] = useState(40)

  const load = useCallback((sp: string) => {
    if (!sp) { setSummary(null); setError(''); return }
    setLoading(true)
    setError('')
    getAssessmentPoolSummary(sp, perPaper, coders)
      .then(d => { setSummary(d); setShowAllTopics(false) })
      // Previously `.catch(() => {})`. With specialty set and summary null,
      // every render branch was false and the page went completely blank —
      // no message, no spinner, nothing to retry.
      .catch(e => { setSummary(null); setError(errorMessage(e, 'Could not load the pool summary')) })
      .finally(() => setLoading(false))
  }, [perPaper, coders])

  useEffect(() => { load(specialty) }, [specialty, load])

  const readiness = (summary?.readiness && 'verdict' in summary.readiness)
    ? summary.readiness as PoolReadiness
    : null
  const outlook = summary?.difficulty_outlook || {}

  const totalByDiff = summary
    ? (summary.by_difficulty.Easy || 0) + (summary.by_difficulty.Medium || 0) + (summary.by_difficulty.Hard || 0)
    : 0

  const topics = summary?.by_topic || []
  const shownTopics = showAllTopics ? topics : topics.slice(0, TOPIC_CAP)

  return (
    <div>
      <div style={s.filterRow}>
        <label style={s.label}>Select Specialty</label>
        <select style={s.select} value={specialty} onChange={e => setSpecialty(e.target.value)}>
          <option value="">— choose a specialty —</option>
          {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
        </select>

        {summary && (
          <>
            <span style={s.totalChip}>{summary.total_active} active</span>
            {/* Reactivating retired questions is far cheaper than authoring
                them, so the inactive count is a decision, not trivia. */}
            {summary.total_inactive > 0 && (
              <span style={s.mutedChip} title="Inactive questions can be reactivated from the Question Bank">
                {summary.total_inactive} inactive
              </span>
            )}
          </>
        )}
      </div>

      {specialty && (
        <div style={s.intentRow}>
          <span style={s.intentLabel}>Planning a paper of</span>
          <input type="number" min={1} max={500} value={perPaper}
            onChange={e => setPerPaper(Math.max(1, Number(e.target.value) || 1))}
            style={s.numInput} />
          <span style={s.intentLabel}>questions for</span>
          <input type="number" min={1} max={5000} value={coders}
            onChange={e => setCoders(Math.max(1, Number(e.target.value) || 1))}
            style={s.numInput} />
          <span style={s.intentLabel}>coders</span>
        </div>
      )}

      {loading && <div style={s.emptyState}>Loading summary…</div>}

      {!loading && error && (
        <div style={s.errorBox}>
          <AlertTriangle size={16} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>{error}</span>
          <button style={s.retryBtn} onClick={() => load(specialty)}>
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {!loading && !error && !specialty && (
        <div style={s.emptyState}>
          <BarChart2 size={36} color="#d1d5db" />
          <div style={{ marginTop: 12, fontSize: 14, color: '#9ca3af' }}>Select a specialty to view pool readiness</div>
          {/* Was #d1d5db, roughly 1.5:1 against this ground — below the 4.5:1
              a body-size caption needs, and effectively invisible. */}
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>No question content is shown here — counts only</div>
        </div>
      )}

      {!loading && !error && summary && readiness && (
        <div style={{
          ...s.readinessBox,
          background: VERDICT[readiness.verdict].bg,
          border: `1px solid ${VERDICT[readiness.verdict].border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ ...s.verdictChip, color: VERDICT[readiness.verdict].color, borderColor: VERDICT[readiness.verdict].border }}>
              {VERDICT[readiness.verdict].label}
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>{readiness.headline}</span>
          </div>
          <div style={{ fontSize: 12, color: '#4b5563', marginTop: 6 }}>{readiness.advice}</div>
          {readiness.overlap_pct != null && (
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
              Overlap is what decides whether comparing notes defeats the assessment.
              {readiness.uniqueness_pct != null && ` Questions held by no one else: ${readiness.uniqueness_pct}%.`}
            </div>
          )}

          {/* The verdict says what to do; these do it, without making the
              trainer re-pick the specialty they are already looking at. */}
          {onJump && (
            <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              <button style={s.jumpBtn} onClick={() => onJump('upload', specialty)}>
                <Upload size={13} /> Add questions to {specialty}
              </button>
              <button
                style={readiness.verdict === 'insufficient' ? s.jumpBtnDisabled : s.jumpBtnPrimary}
                disabled={readiness.verdict === 'insufficient'}
                title={readiness.verdict === 'insufficient'
                  ? 'Generation will refuse a pool this small — add questions first.'
                  : `Start a ${specialty} assessment from this pool`}
                onClick={() => onJump('generate', specialty)}>
                <Wand2 size={13} /> Generate from this pool
              </button>
            </div>
          )}
        </div>
      )}

      {!loading && !error && summary && (outlook.notes || []).length > 0 && (
        <div style={s.outlookBox}>
          {(outlook.notes || []).map((n, i) => (
            <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', fontSize: 12, color: '#92400e' }}>
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>{n}</span>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && summary && (
        <div style={s.grid}>
          <div style={s.card}>
            <div style={s.cardTitle}>By Difficulty</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
              {(['Easy', 'Medium', 'Hard'] as const).map(d => {
                const count = summary.by_difficulty[d] || 0
                const pct = totalByDiff > 0 ? Math.round((count / totalByDiff) * 100) : 0
                return (
                  <div key={d}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: DIFF_COLORS[d] }}>{d}</span>
                      <span style={{ fontSize: 13, fontWeight: 800, color: '#111' }}>{count} <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 500 }}>({pct}%)</span></span>
                    </div>
                    <div style={{ height: 7, background: '#f3f4f6', borderRadius: 99, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${pct}%`, background: DIFF_COLORS[d], borderRadius: 99, transition: 'width 0.5s ease' }} />
                    </div>
                  </div>
                )
              })}
            </div>
            <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid #f3f4f6', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, color: '#6b7280' }}>Total active</span>
              <span style={{ fontSize: 14, fontWeight: 800, color: '#111' }}>{summary.total_active}</span>
            </div>
          </div>

          <div style={s.card}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
              <div style={s.cardTitle}>By Topic</div>
              {topics.length > TOPIC_CAP && (
                <button style={s.linkBtn} onClick={() => setShowAllTopics(v => !v)}>
                  {showAllTopics ? `Show top ${TOPIC_CAP}` : `Show all ${topics.length}`}
                </button>
              )}
            </div>
            {topics.length === 0 ? (
              <div style={{ fontSize: 13, color: '#9ca3af', marginTop: 16 }}>No topics tagged yet.</div>
            ) : (
              <>
                {/* Capped and scrollable: a topic-heavy specialty otherwise runs
                    the page on for hundreds of rows. */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14, maxHeight: 420, overflowY: 'auto' }}>
                  {shownTopics.map(row => (
                    <div key={row.topic} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 10px', background: '#f9fafb', borderRadius: 8 }}>
                      <span style={{ fontSize: 13, color: '#374151', fontWeight: 500 }}>{row.topic}</span>
                      <span style={{ fontSize: 13, fontWeight: 800, color: '#4f46e5', background: '#ede9fe', padding: '2px 9px', borderRadius: 12 }}>{row.count}</span>
                    </div>
                  ))}
                </div>
                {!showAllTopics && topics.length > TOPIC_CAP && (
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>
                    Showing the {TOPIC_CAP} largest of {topics.length} topics.
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  filterRow: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' },
  label: { fontSize: 13, fontWeight: 700, color: '#374151', whiteSpace: 'nowrap' },
  select: { padding: '9px 14px', border: '1px solid #e5e7eb', borderRadius: 9, fontSize: 13, background: '#fff', cursor: 'pointer', minWidth: 220 },
  totalChip: { fontSize: 12, fontWeight: 700, background: '#ede9fe', color: '#4f46e5', padding: '4px 12px', borderRadius: 20 },
  mutedChip: { fontSize: 12, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '4px 12px', borderRadius: 20 },
  intentRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18, flexWrap: 'wrap' },
  intentLabel: { fontSize: 12, color: '#6b7280', fontWeight: 600 },
  numInput: { width: 68, padding: '5px 9px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 12, textAlign: 'center' },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 0', color: '#9ca3af' },
  errorBox: { display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.2)', color: '#b91c1c', borderRadius: 12, padding: '12px 16px', fontSize: 13, fontWeight: 600, marginBottom: 16 },
  retryBtn: { display: 'flex', alignItems: 'center', gap: 5, padding: '5px 11px', borderRadius: 8, border: '1px solid rgba(220,38,38,0.3)', background: '#fff', color: '#b91c1c', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  readinessBox: { borderRadius: 12, padding: '14px 18px', marginBottom: 14 },
  verdictChip: { fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.4, background: '#fff', border: '1px solid', borderRadius: 20, padding: '3px 10px' },
  outlookBox: { display: 'flex', flexDirection: 'column', gap: 7, background: 'rgba(202,138,4,0.08)', border: '1px solid rgba(202,138,4,0.2)', borderRadius: 12, padding: '12px 16px', marginBottom: 16 },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16 },
  card: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  cardTitle: { fontSize: 13, fontWeight: 800, color: '#374151', textTransform: 'uppercase', letterSpacing: 0.4, paddingLeft: 10, borderLeft: '3px solid #7c3aed' },
  jumpBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 13px', borderRadius: 9, border: '1px solid #e5e7eb', background: '#fff', color: '#374151', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  jumpBtnPrimary: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 13px', borderRadius: 9, border: 'none', background: '#7c3aed', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  jumpBtnDisabled: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 13px', borderRadius: 9, border: '1px solid #e5e7eb', background: '#f3f4f6', color: '#9ca3af', cursor: 'not-allowed', fontSize: 12, fontWeight: 700 },
  linkBtn: { fontSize: 11, color: '#7c3aed', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700, textDecoration: 'underline', padding: 0, whiteSpace: 'nowrap' },
}
