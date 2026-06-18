import { useState } from 'react'
import { BarChart2 } from 'lucide-react'
import { getAssessmentPoolSummary } from '../../api'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

const DIFF_COLORS: Record<string, string> = {
  Easy: '#16a34a',
  Medium: '#d97706',
  Hard: '#dc2626',
}

export function PoolSummaryView() {
  const [specialty, setSpecialty] = useState('')
  const [summary, setSummary] = useState<{
    total_active: number
    by_topic: { topic: string; count: number }[]
    by_difficulty: Record<string, number>
  } | null>(null)
  const [loading, setLoading] = useState(false)

  function handleSpecialtyChange(s: string) {
    setSpecialty(s)
    setSummary(null)
    if (!s) return
    setLoading(true)
    getAssessmentPoolSummary(s)
      .then(d => setSummary(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  const totalByDiff = summary
    ? (summary.by_difficulty.Easy || 0) + (summary.by_difficulty.Medium || 0) + (summary.by_difficulty.Hard || 0)
    : 0

  return (
    <div>
      {/* Specialty selector */}
      <div style={s.filterRow}>
        <label style={s.label}>Select Specialty</label>
        <select style={s.select} value={specialty} onChange={e => handleSpecialtyChange(e.target.value)}>
          <option value="">— choose a specialty —</option>
          {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
        </select>
        {summary && (
          <span style={s.totalChip}>{summary.total_active} active questions</span>
        )}
      </div>

      {loading && (
        <div style={s.emptyState}>Loading summary...</div>
      )}

      {!loading && !specialty && (
        <div style={s.emptyState}>
          <BarChart2 size={36} color="#d1d5db" />
          <div style={{ marginTop: 12, fontSize: 14, color: '#9ca3af' }}>Select a specialty to view pool statistics</div>
          <div style={{ fontSize: 12, color: '#d1d5db', marginTop: 4 }}>No question content is shown here — counts only</div>
        </div>
      )}

      {!loading && summary && (
        <div style={s.grid}>
          {/* Difficulty breakdown */}
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

          {/* Topic breakdown */}
          <div style={s.card}>
            <div style={s.cardTitle}>By Topic</div>
            {summary.by_topic.length === 0 ? (
              <div style={{ fontSize: 13, color: '#9ca3af', marginTop: 16 }}>No topics tagged yet.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
                {summary.by_topic.map(row => (
                  <div key={row.topic} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 10px', background: '#f9fafb', borderRadius: 8 }}>
                    <span style={{ fontSize: 13, color: '#374151', fontWeight: 500 }}>{row.topic}</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#4f46e5', background: '#ede9fe', padding: '2px 9px', borderRadius: 12 }}>{row.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  filterRow: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24, flexWrap: 'wrap' },
  label: { fontSize: 13, fontWeight: 700, color: '#374151', whiteSpace: 'nowrap' },
  select: { padding: '9px 14px', border: '1px solid #e5e7eb', borderRadius: 9, fontSize: 13, background: '#fff', cursor: 'pointer', minWidth: 220 },
  totalChip: { fontSize: 12, fontWeight: 700, background: '#ede9fe', color: '#4f46e5', padding: '4px 12px', borderRadius: 20 },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 0', color: '#9ca3af' },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16 },
  card: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  cardTitle: { fontSize: 13, fontWeight: 800, color: '#374151', textTransform: 'uppercase', letterSpacing: 0.4, paddingLeft: 10, borderLeft: '3px solid #7c3aed' },
}
