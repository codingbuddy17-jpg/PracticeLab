import { useState, useEffect, useMemo } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentQuestionSignals } from '../../../api'
import type { AFilters } from '../../../api'
import { Panel, LoadingSpinner, EmptyState } from './helpers'
import { usePagination } from '../../../components/Paginator'

const NO_FILTERS: AFilters = {}
const PAGE_SIZE = 10

/**
 * What each label means, in the trainer's terms rather than the model's.
 * The order here is the order the chips appear — most actionable first.
 */
const SIGNALS: { id: string; label: string; hint: string; color: string; bg: string }[] = [
  { id: 'misleading', label: 'Misleading', color: '#b91c1c', bg: 'rgba(220,38,38,0.1)',
    hint: 'A wrong option was chosen more often than the right one. Check the stem and the key before teaching this harder.' },
  { id: 'very_hard', label: 'Very hard', color: '#c2410c', bg: 'rgba(234,88,12,0.1)',
    hint: '30% or fewer got it right. Either a real training gap, or a key worth re-reading.' },
  { id: 'skipped', label: 'Skipped', color: '#a16207', bg: 'rgba(202,138,4,0.12)',
    hint: 'A quarter or more left it blank. Usually unclear wording or a question too long for the time given.' },
  { id: 'too_easy', label: 'Too easy', color: '#0369a1', bg: 'rgba(2,132,199,0.1)',
    hint: '95% or more got it right. It is no longer telling you anything — retire or replace it.' },
  { id: 'healthy', label: 'Healthy', color: '#15803d', bg: 'rgba(22,163,74,0.1)',
    hint: 'Discriminating normally.' },
]

export function QuestionSignalsTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [signal, setSignal] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [minAttempts, setMinAttempts] = useState(5)
  const [topic, setTopic] = useState('')
  const [specialty, setSpecialty] = useState('')

  useEffect(() => {
    setLoading(true)
    getAssessmentQuestionSignals(filters, minAttempts)
      .then(setData)
      .catch(() => toast.error('Failed to load question signals'))
      .finally(() => setLoading(false))
  }, [filters, minAttempts])

  // Above the early returns: hooks must run in the same order every render.
  // With `if (loading) return` first, the initial render ran none of these and
  // the next ran three — React error #310, which crashed this tab and took the
  // whole analytics view down with it.
  const all: any[] = data?.questions || []
  const summary = data?.summary || {}
  const topics = useMemo(() => Array.from(new Set(all.map((row: any) => row.topic || 'Unknown'))).sort(), [all])
  const specialties = useMemo(() => Array.from(new Set(all.map((row: any) => row.specialty || 'Unknown'))).sort(), [all])

  // Below every hook this component owns. usePagination lives in QuestionList,
  // a separate component with its own hook order, so it is unaffected.
  if (loading) return <LoadingSpinner />
  if (!data) return <EmptyState message="No question data available yet." />


  const q = search.trim().toLowerCase()
  const questions = all.filter((row: any) => {
    if (signal && row.signal !== signal) return false
    if (topic && (row.topic || 'Unknown') !== topic) return false
    if (specialty && (row.specialty || 'Unknown') !== specialty) return false
    if (q && !`${row.question_text} ${row.topic} ${row.question_id}`.toLowerCase().includes(q)) return false
    return true
  })

  const emptyMessage = all.length === 0 && summary.too_few_attempts
    ? `No question has been answered ${data.min_attempts} times yet — ${summary.too_few_attempts} are waiting for more attempts before they can be judged.`
    : all.length === 0
      ? 'No submitted answers yet.'
      : 'No question matches these filters.'

  return (
    <div>
      <Panel>
        <div style={{ fontSize: 13, color: '#6b7280' }}>
          Question quality signals based on submitted answers. Only questions answered
          at least <strong>{data.min_attempts}</strong> times are ranked
          {summary.too_few_attempts > 0 && <> — {summary.too_few_attempts} more are still too thin to judge</>}.
        </div>
      </Panel>

      {/* Filters above the list: a chip that matches nothing must not remove
          the chip that would undo it. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        <select value={minAttempts} onChange={e => setMinAttempts(Number(e.target.value))}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff' }}>
          {[3, 5, 10, 20, 50].map(n => <option key={n} value={n}>Min {n} attempts</option>)}
        </select>
        <select value={specialty} onChange={e => setSpecialty(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff', maxWidth: 180 }}>
          <option value="">All specialties</option>
          {specialties.map(sp => <option key={sp} value={sp}>{sp}</option>)}
        </select>
        <select value={topic} onChange={e => setTopic(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff', maxWidth: 220 }}>
          <option value="">All topics</option>
          {topics.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        {SIGNALS.map(s => {
          const n = summary.by_signal?.[s.id] || 0
          const on = signal === s.id
          return (
            <button key={s.id} onClick={() => setSignal(on ? null : s.id)} title={s.hint}
              disabled={n === 0}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', borderRadius: 9, fontSize: 12, fontWeight: 700,
                cursor: n === 0 ? 'default' : 'pointer', opacity: n === 0 ? 0.4 : 1,
                border: on ? `1px solid ${s.color}` : '1px solid #e5e7eb',
                background: on ? s.bg : '#fff',
                color: on ? s.color : '#6b7280',
              }}>
              {s.label} <span style={{ fontWeight: 800 }}>{n}</span>
            </button>
          )
        })}

        <div style={{ position: 'relative', marginLeft: 'auto' }}>
          <input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setSearch('') }}
            placeholder="Find a question or topic…"
            style={{ padding: '6px 26px 6px 11px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, minWidth: 210 }} />
          {search && (
            <button onClick={() => setSearch('')} title="Clear"
              style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', display: 'flex', padding: 0 }}>
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {questions.length === 0
        ? <EmptyState message={emptyMessage} />
        : <QuestionList questions={questions} />}
    </div>
  )
}

function QuestionList({ questions }: { questions: any[] }) {
  const { pageData, Paginator } = usePagination(questions, PAGE_SIZE)
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {pageData.map((row: any) => <QuestionCard key={row.question_key || row.question_id} row={row} />)}
      </div>
      <Paginator />
    </>
  )
}

function QuestionCard({ row }: { row: any }) {
  const meta = SIGNALS.find(s => s.id === row.signal)
  return (
    <div style={{
      background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(10px)',
      WebkitBackdropFilter: 'blur(10px)', borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.6)', padding: '16px 18px',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#111', lineHeight: 1.45 }}>
            {row.question_text || <span style={{ color: '#9ca3af' }}>(no text)</span>}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
            {row.question_id} · {row.specialty} · {row.topic} · {row.difficulty} · {row.attempts} attempt{row.attempts === 1 ? '' : 's'}
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 22, fontWeight: 900, color: meta?.color || '#374151' }}>
            {row.accuracy_pct != null ? `${row.accuracy_pct}%` : '—'}
          </div>
          {meta && (
            <div title={meta.hint} style={{ fontSize: 10, fontWeight: 800, color: meta.color, background: meta.bg, borderRadius: 20, padding: '2px 9px', marginTop: 3 }}>
              {meta.label}
            </div>
          )}
        </div>
      </div>

      {row.misleading && row.top_distractor && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7, fontSize: 12, color: '#b91c1c', background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.15)', borderRadius: 9, padding: '8px 11px', marginBottom: 10 }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            More coders chose <strong>“{row.top_distractor.text}”</strong> ({row.top_distractor.pct}%)
            than the correct answer. Worth re-reading the stem and the key before teaching this harder.
          </span>
        </div>
      )}

      {/* Distractor spread. Aggregated on the option TEXT, because the letters
          are shuffled per coder and mean different things to each of them. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {row.options.map((o: any, i: number) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 150, fontSize: 11, color: o.correct ? '#15803d' : '#6b7280', fontWeight: o.correct ? 800 : 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={o.text}>
              {o.correct ? 'Correct: ' : ''}{o.text}
            </div>
            <div style={{ flex: 1, height: 8, background: '#f3f4f6', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${o.pct}%`, background: o.correct ? '#16a34a' : '#dc2626', opacity: o.correct ? 1 : 0.55, borderRadius: 4 }} />
            </div>
            <div style={{ width: 44, textAlign: 'right', fontSize: 11, fontWeight: 700, color: o.correct ? '#15803d' : '#6b7280' }}>
              {o.pct}%
            </div>
          </div>
        ))}
        {row.blank_pct > 0 && (
          <div style={{ fontSize: 11, color: '#a16207', marginTop: 2 }}>
            {row.blank_pct}% left this blank.
          </div>
        )}
      </div>
    </div>
  )
}
