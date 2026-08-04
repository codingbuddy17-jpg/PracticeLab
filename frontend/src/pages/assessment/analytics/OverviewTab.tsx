import { useState, useEffect } from 'react'
import { BarChart2, User, Award, TrendingUp, CheckCircle, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { getAssessmentAnalyticsOverview } from '../../../api'
import { rateColor, scoreColor, fmt, KpiCard, Panel, LoadingSpinner, EmptyState, PASS_RATE_TARGET } from './helpers'

export function OverviewTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAssessmentAnalyticsOverview()
      .then(setData)
      .catch(() => toast.error('Failed to load overview'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner />
  if (!data) return <EmptyState message="No analytics data available yet." />

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Total Assessments" value={String(data.total_assessments)} icon={<BarChart2 size={14} />} />
        <KpiCard label="Coders Assessed" value={String(data.unique_coders_assessed)} icon={<User size={14} />} />
        <KpiCard label="Overall Pass Rate" value={fmt(data.overall_pass_rate)} color={rateColor(data.overall_pass_rate)} icon={<Award size={14} />} />
        <KpiCard label="Avg Score" value={fmt(data.avg_score)} color={scoreColor(data.avg_score, data.default_pass_threshold)} icon={<TrendingUp size={14} />} />
        <KpiCard label="Completion Rate" value={fmt(data.completion_rate)} icon={<CheckCircle size={14} />} />
        <KpiCard label="Auto-submit Rate" value={fmt(data.auto_submit_rate)} color={data.auto_submit_rate > 20 ? '#d97706' : undefined} icon={<Clock size={14} />} />
      </div>

      {/* A pass rate means nothing without the bar it was measured against, and
          the bars can differ per paper. Say which, rather than letting the
          colours imply one number governs everything. */}
      <div style={{ fontSize: 11, color: '#6b7280', marginTop: -10, marginBottom: 18 }}>
        Scores are judged against each assessment's own pass mark
        {data.pass_thresholds_vary
          ? ' (these differ between assessments).'
          : ` — currently ${data.default_pass_threshold}%.`}
        {' '}Pass rates are shares of coders, measured against a {PASS_RATE_TARGET}% target.
      </div>

      {data.per_assessment_pass_rates && data.per_assessment_pass_rates.length > 0 ? (
        <Panel title="Pass Rate by Assessment (Recent 10)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.per_assessment_pass_rates} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="assessment_name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip formatter={(v: any) => [`${v}%`, 'Pass Rate']} />
              <Bar dataKey="pass_rate" radius={[4, 4, 0, 0]}>
                {(data.per_assessment_pass_rates as any[]).map((entry: any, i: number) => (
                  <Cell key={i} fill={rateColor(entry.pass_rate)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      ) : (
        <Panel title="Pass Rate by Assessment">
          <EmptyState message="No submitted assessments yet." />
        </Panel>
      )}

      {data.top_specialties && data.top_specialties.length > 0 && (
        <Panel title="Top Specialties by Submission Volume">
          <div style={{ display: 'flex', gap: 14 }}>
            {data.top_specialties.map((s: any, i: number) => (
              <div key={i} style={{ flex: 1, background: 'rgba(124,58,237,0.07)', borderRadius: 12, padding: '14px 18px', border: '1px solid rgba(124,58,237,0.15)' }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#7c3aed', marginBottom: 4 }}>#{i + 1}</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#111' }}>{s.specialty}</div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{s.count} question{s.count !== 1 ? 's' : ''}</div>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  )
}
