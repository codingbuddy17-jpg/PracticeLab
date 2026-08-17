import { useState, useEffect } from 'react'
import { AlertCircle, CheckCircle, Tag, TrendingUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { getAssessmentAnalyticsByTopic } from '../../../api'
import type { AFilters } from '../../../api'

const NO_FILTERS: AFilters = {}
import { scoreColor, fmt, KpiCard, Panel, LoadingSpinner, EmptyState, inputStyle } from './helpers'
import { usePagination } from '../../../components/Paginator'

const PAGE_SIZE = 20

export function ByTopicTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    setLoading(true)
    getAssessmentAnalyticsByTopic(filters)
      .then(setData)
      .catch(() => toast.error('Failed to load topic analytics'))
      .finally(() => setLoading(false))
  }, [filters])

  if (loading) return <LoadingSpinner />
  if (!data || !data.topics || data.topics.length === 0)
    return <EmptyState message="No topic data available yet. Submit some assessments first." />

  const allTopics: any[] = data.topics
  const filtered = filter.trim()
    ? allTopics.filter((t: any) => t.topic.toLowerCase().includes(filter.toLowerCase()) || t.specialties.some((s: string) => s.toLowerCase().includes(filter.toLowerCase())))
    : allTopics

  const strong = filtered.filter((t: any) => (t.accuracy_pct ?? 0) >= 90).length
  const mid = filtered.filter((t: any) => (t.accuracy_pct ?? 0) >= 80 && (t.accuracy_pct ?? 0) < 90).length
  const weak = filtered.filter((t: any) => (t.accuracy_pct ?? 0) < 80).length
  const weakest = [...filtered].sort((a, b) => (a.accuracy_pct ?? 101) - (b.accuracy_pct ?? 101))[0]
  const overallAccuracy = data.overall_accuracy ?? (
    data.total_responses ? Math.round((data.total_correct / data.total_responses) * 1000) / 10 : null
  )
  const chartData = [...filtered].sort((a, b) => (a.accuracy_pct ?? 101) - (b.accuracy_pct ?? 101)).slice(0, 20)

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <KpiCard label="Overall Topic Accuracy" value={fmt(overallAccuracy)} color={scoreColor(overallAccuracy)} icon={<TrendingUp size={14} />} sub={`${data.total_correct ?? 0}/${data.total_responses ?? 0} responses`} />
        <KpiCard label="Weakest Topic" value={fmt(weakest?.accuracy_pct)} color={scoreColor(weakest?.accuracy_pct)} icon={<AlertCircle size={14} />} sub={`${weakest?.topic || '—'} · ${weakest?.correct ?? 0}/${weakest?.total_responses ?? 0}`} />
        <KpiCard label="Strong Topics" value={String(strong)} color="#16a34a" icon={<CheckCircle size={14} />} sub="90% and above" />
        <KpiCard label="Needs Review" value={String(weak)} color="#dc2626" icon={<AlertCircle size={14} />} sub={`${mid} mid topics`} />
      </div>

      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Tag size={14} color="#7c3aed" />
          <input style={{ ...inputStyle, flex: 1 }} placeholder="Filter by topic or specialty…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          {filter && <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 12 }} onClick={() => setFilter('')}>Clear</button>}
          <span style={{ fontSize: 12, color: '#9ca3af' }}>{filtered.length} topic{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </Panel>

      {chartData.length > 0 && (
        <Panel title={`Weakest Topic Accuracy${filtered.length > 20 ? ' (20 shown)' : ''}`}>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 38)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 60, left: 180, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <YAxis type="category" dataKey="topic" tick={{ fontSize: 11 }} width={175} />
              <Tooltip formatter={(v: any) => [`${v}%`, 'Accuracy']} />
              <Bar dataKey="accuracy_pct" radius={[0, 4, 4, 0]}>
                {(chartData as any[]).map((entry: any, i: number) => (
                  <Cell key={i} fill={scoreColor(entry.accuracy_pct)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      <Panel title="Topic Detail">
        <TopicTable rows={filtered} />
      </Panel>
    </div>
  )
}

function TopicTable({ rows }: { rows: any[] }) {
  const { pageData, Paginator } = usePagination(rows, PAGE_SIZE)

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
              {['Topic', 'Specialty', 'Accuracy', 'Correct / Total', 'Coders', 'Bar'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 14px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((t: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700, color: '#111' }}>{t.topic}</td>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {(t.specialties as string[]).map((sp: string, j: number) => (
                      <span key={j} style={{ fontSize: 10, background: 'rgba(124,58,237,0.1)', color: '#7c3aed', padding: '1px 7px', borderRadius: 20, fontWeight: 700 }}>{sp}</span>
                    ))}
                  </div>
                </td>
                <td style={{ padding: '10px 14px', fontWeight: 800, color: scoreColor(t.accuracy_pct), fontSize: 14 }}>{t.accuracy_pct != null ? `${t.accuracy_pct}%` : '—'}</td>
                <td style={{ padding: '10px 14px', color: '#6b7280' }}>{t.correct} / {t.total_responses}</td>
                <td style={{ padding: '10px 14px', color: '#374151' }}>{t.coder_count}</td>
                <td style={{ padding: '10px 14px', minWidth: 100 }}>
                  <div style={{ width: 90, height: 8, background: '#f3f4f6', borderRadius: 4 }}>
                    {t.accuracy_pct != null && <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(t.accuracy_pct, 100)}%`, background: scoreColor(t.accuracy_pct), transition: 'width 0.5s' }} />}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginator />
    </>
  )
}
