import { useState, useEffect } from 'react'
import { BarChart2, User, Award, TrendingUp, CheckCircle, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { getAssessmentAnalyticsOverview } from '../../../api'
import type { AFilters } from '../../../api'

const NO_FILTERS: AFilters = {}
import { rateColor, scoreColor, fmt, KpiCard, Panel, LoadingSpinner, EmptyState, PASS_RATE_TARGET } from './helpers'

export function OverviewTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getAssessmentAnalyticsOverview(filters)
      .then(setData)
      .catch(() => toast.error('Failed to load overview'))
      .finally(() => setLoading(false))
  }, [filters])

  if (loading) return <LoadingSpinner />
  if (!data) return <EmptyState message="No analytics data available yet." />

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Total Assessments" value={String(data.total_assessments)} icon={<BarChart2 size={14} />} />
        <KpiCard label="Coders Assessed" value={String(data.unique_coders_assessed)} icon={<User size={14} />} />
        <KpiCard label="Overall Pass Rate" value={fmt(data.overall_pass_rate)} color={rateColor(data.overall_pass_rate)} icon={<Award size={14} />} />
        {/*
          Coloured against the pass mark only when there IS one pass mark. The
          note below already says the bars differ per paper; colouring an
          average against a default that governs none of them contradicts it,
          and green-or-red is a stronger claim than a sentence. When they vary
          the number stands on its own and the card says which marks are in
          scope.
        */}
        <KpiCard label="Avg Score" value={fmt(data.avg_score)}
          color={data.pass_thresholds_vary
            ? undefined
            : scoreColor(data.avg_score, data.default_pass_threshold)}
          sub={data.pass_thresholds_vary ? 'pass marks differ by assessment' : undefined}
          icon={<TrendingUp size={14} />} />
        <KpiCard label="Completion Rate" value={fmt(data.completion_rate)}
          sub={`${data.total_submitted} of ${data.total_sessions} sessions${data.expired_sessions ? ` · ${data.expired_sessions} lapsed unstarted` : ''}`}
          icon={<CheckCircle size={14} />} />
        <KpiCard label="Auto-submit Rate" value={fmt(data.auto_submit_rate)}
          sub={`${data.auto_submitted_count} of ${data.total_submitted} submitted`}
          color={data.auto_submit_rate > 20 ? '#d97706' : undefined} icon={<Clock size={14} />} />
      </div>

      {/* A pass rate means nothing without the bar it was measured against, and
          the bars can differ per paper. Say which, rather than letting the
          colours imply one number governs everything. */}
      <div style={{ fontSize: 11, color: '#6b7280', marginTop: -10, marginBottom: 18 }}>
        Scores are judged against each assessment's own pass mark
        {data.pass_thresholds_vary
          ? ' (these differ between assessments).'
          : ` — currently ${data.default_pass_threshold}%.`}
        {' '}Pass rate is the share of coders who cleared that mark. It is shaded
        green once {PASS_RATE_TARGET}% of them do — a cohort target for reading the
        colour, not a second mark anyone is judged against.
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
        <Panel title="Most Tested Specialties">
          {/* Counts how often a specialty's questions APPEAR on the papers
              coders sat — 20 questions across 3 coders is 60. It says what has
              been tested most, not how anyone performed and not how many
              submissions there were. The old title said "Submission Volume",
              which was neither. */}
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 10 }}>
            By question appearances across submitted papers — what is tested most, not how it scored.
          </div>
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
