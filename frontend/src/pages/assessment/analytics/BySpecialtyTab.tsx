import { useState, useEffect } from 'react'
import { Layers, Award, AlertCircle, TrendingUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { getAssessmentAnalyticsBySpecialty } from '../../../api'
import type { AFilters } from '../../../api'

const NO_FILTERS: AFilters = {}
import { scoreColor, fmt, KpiCard, Panel, LoadingSpinner, EmptyState } from './helpers'

export function BySpecialtyTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getAssessmentAnalyticsBySpecialty(filters)
      .then(setData)
      .catch(() => toast.error('Failed to load specialty analytics'))
      .finally(() => setLoading(false))
  }, [filters])

  if (loading) return <LoadingSpinner />
  if (!data || !data.specialties || data.specialties.length === 0)
    return <EmptyState message="No specialty data available yet. Submit some assessments first." />

  const specialties: any[] = data.specialties
  const ranked = [...specialties].sort((a, b) => (b.accuracy_pct ?? -1) - (a.accuracy_pct ?? -1))
  const weakest = [...specialties].sort((a, b) => (a.accuracy_pct ?? 101) - (b.accuracy_pct ?? 101))[0]
  const best = ranked[0]
  const overallAccuracy = data.overall_accuracy ?? (
    data.total_responses ? Math.round((data.total_correct / data.total_responses) * 1000) / 10 : null
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Specialties Covered" value={String(specialties.length)} icon={<Layers size={14} />} />
        <KpiCard label="Best Specialty" value={fmt(best?.accuracy_pct)} color={scoreColor(best?.accuracy_pct)} icon={<Award size={14} />} sub={`${best?.specialty || '—'} · ${best?.correct ?? 0}/${best?.total_responses ?? 0}`} />
        <KpiCard label="Weakest Specialty" value={fmt(weakest?.accuracy_pct)} color={scoreColor(weakest?.accuracy_pct)} icon={<AlertCircle size={14} />} sub={`${weakest?.specialty || '—'} · ${weakest?.correct ?? 0}/${weakest?.total_responses ?? 0}`} />
        <KpiCard label="Overall Accuracy" value={fmt(overallAccuracy)} color={scoreColor(overallAccuracy)} icon={<TrendingUp size={14} />} sub={`${data.total_correct ?? 0}/${data.total_responses ?? 0} responses`} />
      </div>

      <Panel title="Accuracy by Specialty">
        <ResponsiveContainer width="100%" height={Math.max(260, specialties.length * 42)}>
          <BarChart data={ranked} layout="vertical" margin={{ top: 5, right: 60, left: 160, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
            <YAxis type="category" dataKey="specialty" tick={{ fontSize: 12, fontWeight: 600 }} width={155} />
            <Tooltip formatter={(v: any) => [`${v}%`, 'Accuracy']} />
            <Bar dataKey="accuracy_pct" radius={[0, 4, 4, 0]}>
              {(ranked as any[]).map((entry: any, i: number) => (
                <Cell key={i} fill={scoreColor(entry.accuracy_pct)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Specialty Detail">
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                {['Specialty', 'Accuracy', 'Correct / Total', 'Coders', 'Strength'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '8px 14px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {specialties.map((s: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#111' }}>{s.specialty}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 800, color: scoreColor(s.accuracy_pct), fontSize: 15 }}>{s.accuracy_pct != null ? `${s.accuracy_pct}%` : '—'}</td>
                  <td style={{ padding: '10px 14px', color: '#6b7280' }}>{s.correct} / {s.total_responses}</td>
                  <td style={{ padding: '10px 14px', color: '#374151' }}>{s.coder_count}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ width: 100, height: 8, background: '#f3f4f6', borderRadius: 4 }}>
                      {s.accuracy_pct != null && <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(s.accuracy_pct, 100)}%`, background: scoreColor(s.accuracy_pct), transition: 'width 0.5s' }} />}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
