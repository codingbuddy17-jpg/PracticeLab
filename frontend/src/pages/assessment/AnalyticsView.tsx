import { useState, useEffect } from 'react'
import { Loader, TrendingUp, BarChart2, User, Award, Clock, AlertCircle, CheckCircle, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, ReferenceLine, Cell,
} from 'recharts'
import {
  getAssessmentAnalyticsOverview,
  getAssessmentAnalyticsByAssessment,
  getAssessmentAnalyticsCoder,
  listAssessmentHistory,
} from '../../api'

// ── Helpers ───────────────────────────────────────────────────────────────────

const PASS = 90

function scoreColor(v: number | null | undefined): string {
  if (v == null) return '#9ca3af'
  if (v >= PASS) return '#16a34a'
  if (v >= 70) return '#d97706'
  return '#dc2626'
}

function bandColor(band: string): string {
  if (band === '90-100') return '#16a34a'
  if (band === '80-89') return '#d97706'
  return '#dc2626'
}

function fmt(v: number | null | undefined, suffix = '%'): string {
  if (v == null) return '—'
  return `${v}${suffix}`
}

function fmtTime(sec: number | null | undefined): string {
  if (sec == null) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

// ── Shared KPI card ───────────────────────────────────────────────────────────

function KpiCard({ label, value, color, icon }: { label: string; value: string; color?: string; icon?: React.ReactNode }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.72)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.6)',
      padding: '18px 22px',
      minWidth: 130,
      flex: 1,
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {icon && <span style={{ color: '#7c3aed' }}>{icon}</span>}
        <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || '#111', letterSpacing: -0.5 }}>
        {value}
      </div>
    </div>
  )
}

// ── Difficulty badge ──────────────────────────────────────────────────────────

function DiffBadge({ diff }: { diff: string }) {
  const colors: Record<string, { bg: string; color: string }> = {
    Easy: { bg: '#dcfce7', color: '#166534' },
    Medium: { bg: '#fef9c3', color: '#854d0e' },
    Hard: { bg: '#fee2e2', color: '#991b1b' },
  }
  const c = colors[diff] || { bg: '#f3f4f6', color: '#374151' }
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: c.bg, color: c.color }}>
      {diff}
    </span>
  )
}

// ── Pass/Fail badge ───────────────────────────────────────────────────────────

function PassBadge({ pf }: { pf: string }) {
  const pass = pf === 'PASS'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
      background: pass ? '#dcfce7' : '#fee2e2',
      color: pass ? '#166534' : '#991b1b',
    }}>
      {pass ? <CheckCircle size={10} /> : <XCircle size={10} />}
      {pf}
    </span>
  )
}

// ── Glass panel ───────────────────────────────────────────────────────────────

function Panel({ title, children, style }: { title?: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.68)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderRadius: 16,
      border: '1px solid rgba(255,255,255,0.55)',
      padding: '20px 24px',
      boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
      marginBottom: 22,
      ...style,
    }}>
      {title && <div style={{ fontSize: 14, fontWeight: 800, color: '#111', marginBottom: 16, letterSpacing: -0.2 }}>{title}</div>}
      {children}
    </div>
  )
}

// ── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab() {
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
      {/* KPI Row */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Total Assessments" value={String(data.total_assessments)} icon={<BarChart2 size={14} />} />
        <KpiCard label="Coders Assessed" value={String(data.unique_coders_assessed)} icon={<User size={14} />} />
        <KpiCard
          label="Overall Pass Rate"
          value={fmt(data.overall_pass_rate)}
          color={data.overall_pass_rate >= PASS ? '#16a34a' : '#dc2626'}
          icon={<Award size={14} />}
        />
        <KpiCard label="Avg Score" value={fmt(data.avg_score)} color={scoreColor(data.avg_score)} icon={<TrendingUp size={14} />} />
        <KpiCard label="Completion Rate" value={fmt(data.completion_rate)} icon={<CheckCircle size={14} />} />
        <KpiCard label="Auto-submit Rate" value={fmt(data.auto_submit_rate)} color={data.auto_submit_rate > 20 ? '#d97706' : undefined} icon={<Clock size={14} />} />
      </div>

      {/* Pass rate bar chart */}
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
                  <Cell key={i} fill={entry.pass_rate >= PASS ? '#16a34a' : entry.pass_rate >= 70 ? '#d97706' : '#dc2626'} />
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

      {/* Top specialties */}
      {data.top_specialties && data.top_specialties.length > 0 && (
        <Panel title="Top Specialties by Submission Volume">
          <div style={{ display: 'flex', gap: 14 }}>
            {data.top_specialties.map((s: any, i: number) => (
              <div key={i} style={{
                flex: 1,
                background: 'rgba(124,58,237,0.07)',
                borderRadius: 12,
                padding: '14px 18px',
                border: '1px solid rgba(124,58,237,0.15)',
              }}>
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

// ── Assessment Drill-down Tab ─────────────────────────────────────────────────

function AssessmentDrillTab() {
  const [assessments, setAssessments] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [listLoading, setListLoading] = useState(true)

  useEffect(() => {
    listAssessmentHistory()
      .then(setAssessments)
      .catch(() => toast.error('Failed to load assessments'))
      .finally(() => setListLoading(false))
  }, [])

  useEffect(() => {
    if (selectedId == null) return
    setLoading(true)
    setData(null)
    getAssessmentAnalyticsByAssessment(selectedId)
      .then(setData)
      .catch(() => toast.error('Failed to load assessment analytics'))
      .finally(() => setLoading(false))
  }, [selectedId])

  return (
    <div>
      {/* Assessment selector */}
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, fontWeight: 700, color: '#374151' }}>Select Assessment:</label>
          {listLoading ? (
            <span style={{ fontSize: 13, color: '#9ca3af' }}>Loading…</span>
          ) : (
            <select
              style={{
                padding: '8px 14px', borderRadius: 10, border: '1px solid #e5e7eb',
                fontSize: 13, background: 'white', cursor: 'pointer', minWidth: 300,
              }}
              value={selectedId ?? ''}
              onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Choose an assessment —</option>
              {assessments.map((a: any) => (
                <option key={a.id} value={a.id}>
                  {a.assessment_name} ({a.generated_at ? new Date(a.generated_at).toLocaleDateString() : '—'})
                </option>
              ))}
            </select>
          )}
        </div>
      </Panel>

      {loading && <LoadingSpinner />}
      {!loading && selectedId && !data && <EmptyState message="No data found for this assessment." />}
      {!loading && !selectedId && <EmptyState message="Select an assessment above to see detailed analytics." />}

      {data && !loading && <AssessmentDrillContent data={data} />}
    </div>
  )
}

function AssessmentDrillContent({ data }: { data: any }) {
  return (
    <div>
      {/* Header */}
      <Panel>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#111', marginBottom: 4 }}>{data.assessment_name}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>
              Generated by <strong>{data.generated_by}</strong> &nbsp;·&nbsp;
              {data.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'} &nbsp;·&nbsp;
              {data.total_questions} questions &nbsp;·&nbsp; {data.duration_minutes}min time limit
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 12, background: 'rgba(124,58,237,0.1)', borderRadius: 8, padding: '6px 12px', color: '#7c3aed', fontWeight: 700 }}>
              {data.total_submitted}/{data.total_sessions} submitted
            </div>
          </div>
        </div>
      </Panel>

      {/* KPI row */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Avg Score" value={fmt(data.avg_score)} color={scoreColor(data.avg_score)} />
        <KpiCard label="Pass Rate" value={fmt(data.pass_rate)} color={data.pass_rate >= PASS ? '#16a34a' : '#dc2626'} />
        <KpiCard label="Min Score" value={fmt(data.min_score)} color={scoreColor(data.min_score)} />
        <KpiCard label="Max Score" value={fmt(data.max_score)} color={scoreColor(data.max_score)} />
        <KpiCard label="Completion" value={fmt(data.completion_rate)} />
        <KpiCard label="Auto-submits" value={fmt(data.auto_submit_rate)} color={data.auto_submit_rate > 20 ? '#d97706' : undefined} />
      </div>

      {/* Score distribution */}
      {data.score_distribution && (
        <Panel title="Score Distribution">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.score_distribution} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="band" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip formatter={(v: any) => [v, 'Coders']} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(data.score_distribution as any[]).map((entry: any, i: number) => (
                  <Cell key={i} fill={bandColor(entry.band)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {/* Coder results table */}
      {data.coder_rows && data.coder_rows.length > 0 && (
        <Panel title="Coder Results">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                  {['Coder', 'Emp ID', 'Score', 'Correct', 'Time', 'Pass/Fail', 'Auto-submit'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.coder_rows as any[]).map((row: any, i: number) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '9px 12px', fontWeight: 600 }}>{row.coder_name}</td>
                    <td style={{ padding: '9px 12px', color: '#6b7280' }}>{row.employee_id || '—'}</td>
                    <td style={{ padding: '9px 12px', fontWeight: 800, color: scoreColor(row.score_pct) }}>
                      {fmt(row.score_pct)}
                    </td>
                    <td style={{ padding: '9px 12px', color: '#374151' }}>{row.correct_count}/{row.total_questions}</td>
                    <td style={{ padding: '9px 12px', color: '#6b7280' }}>{fmtTime(row.time_taken_seconds)}</td>
                    <td style={{ padding: '9px 12px' }}><PassBadge pf={row.pass_fail} /></td>
                    <td style={{ padding: '9px 12px' }}>
                      {row.auto_submitted && (
                        <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 20, fontWeight: 700 }}>Auto</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Topic breakdown */}
        {data.topic_breakdown && data.topic_breakdown.length > 0 && (
          <Panel title="Accuracy by Topic">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(data.topic_breakdown as any[]).map((t: any, i: number) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ fontWeight: 600, color: '#374151' }}>{t.topic}</span>
                    <span style={{ color: scoreColor(t.avg_accuracy), fontWeight: 700 }}>
                      {t.avg_accuracy != null ? `${t.avg_accuracy}%` : '—'} ({t.question_count}q)
                    </span>
                  </div>
                  <div style={{ height: 7, background: '#f3f4f6', borderRadius: 4 }}>
                    {t.avg_accuracy != null && (
                      <div style={{
                        height: '100%', borderRadius: 4,
                        width: `${Math.min(t.avg_accuracy, 100)}%`,
                        background: scoreColor(t.avg_accuracy),
                        transition: 'width 0.5s',
                      }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* Difficulty calibration */}
        {data.difficulty_calibration && (
          <Panel title="Difficulty Calibration">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(data.difficulty_calibration as any[]).map((d: any, i: number) => (
                <div key={i} style={{
                  background: 'rgba(249,250,251,0.8)',
                  borderRadius: 10,
                  padding: '12px 14px',
                  border: '1px solid #f3f4f6',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <DiffBadge diff={d.difficulty} />
                    <span style={{ fontSize: 11, color: '#9ca3af' }}>{d.question_count} questions</span>
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                    <div>
                      <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600 }}>EXPECTED</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: '#6b7280' }}>{d.expected_accuracy}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600 }}>ACTUAL</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: scoreColor(d.actual_accuracy) }}>
                        {d.actual_accuracy != null ? `${d.actual_accuracy}%` : '—'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </div>

      {/* Question accuracy table */}
      {data.question_accuracy && data.question_accuracy.length > 0 && (
        <Panel title="Question Accuracy (Most-Missed First)">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                  {['Question', 'Topic', 'Difficulty', 'Accuracy', 'Responses'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.question_accuracy as any[]).map((q: any, i: number) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '9px 12px', maxWidth: 300 }}>
                      <div style={{ fontWeight: 600, color: '#111', fontSize: 12 }}>{q.question_id}</div>
                      <div style={{ color: '#6b7280', fontSize: 11, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 260 }}>
                        {q.question_text}
                      </div>
                    </td>
                    <td style={{ padding: '9px 12px', color: '#374151', fontSize: 12 }}>{q.topic}</td>
                    <td style={{ padding: '9px 12px' }}><DiffBadge diff={q.difficulty} /></td>
                    <td style={{ padding: '9px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 70, height: 6, background: '#f3f4f6', borderRadius: 3 }}>
                          {q.accuracy_pct != null && (
                            <div style={{
                              height: '100%', borderRadius: 3,
                              width: `${Math.min(q.accuracy_pct, 100)}%`,
                              background: scoreColor(q.accuracy_pct),
                            }} />
                          )}
                        </div>
                        <span style={{ fontWeight: 700, color: scoreColor(q.accuracy_pct), fontSize: 12 }}>
                          {q.accuracy_pct != null ? `${q.accuracy_pct}%` : '—'}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '9px 12px', color: '#6b7280', fontSize: 12 }}>{q.correct}/{q.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  )
}

// ── Coder History Tab ─────────────────────────────────────────────────────────

function CoderHistoryTab() {
  const [coderName, setCoderName] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  function handleSearch() {
    if (!coderName.trim()) {
      toast.error('Please enter a coder name')
      return
    }
    setLoading(true)
    setData(null)
    setSearched(true)
    getAssessmentAnalyticsCoder(coderName.trim(), employeeId.trim() || undefined)
      .then(setData)
      .catch(() => toast.error('Failed to load coder history'))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      {/* Search */}
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <input
            style={inputStyle}
            placeholder="Coder name (required)"
            value={coderName}
            onChange={(e) => setCoderName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <input
            style={{ ...inputStyle, maxWidth: 180 }}
            placeholder="Employee ID (optional)"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button style={searchBtnStyle} onClick={handleSearch} disabled={loading}>
            {loading ? <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> : null}
            Search
          </button>
        </div>
      </Panel>

      {loading && <LoadingSpinner />}
      {!loading && searched && !data && <EmptyState message="No assessment history found for this coder." />}
      {!loading && !searched && <EmptyState message="Enter a coder name above to view their assessment history." />}
      {data && !loading && <CoderHistoryContent data={data} />}
    </div>
  )
}

function CoderHistoryContent({ data }: { data: any }) {
  return (
    <div>
      {/* Profile header */}
      <Panel>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 20, fontWeight: 800,
            }}>
              {data.coder_name.charAt(0).toUpperCase()}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: '#111' }}>{data.coder_name}</div>
              {data.employee_id && (
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>ID: {data.employee_id}</div>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: scoreColor(data.avg_score) }}>{fmt(data.avg_score)}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Avg Score</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: data.pass_rate >= PASS ? '#16a34a' : '#dc2626' }}>{fmt(data.pass_rate)}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Pass Rate</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: '#111' }}>{data.total_assessments_taken}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Assessments</div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13, color: '#374151' }}>Best: <strong style={{ color: '#16a34a' }}>{fmt(data.best_score)}</strong></div>
          <div style={{ fontSize: 13, color: '#374151' }}>Worst: <strong style={{ color: scoreColor(data.worst_score) }}>{fmt(data.worst_score)}</strong></div>
          {data.avg_time_seconds && (
            <div style={{ fontSize: 13, color: '#374151' }}>Avg Time: <strong>{fmtTime(data.avg_time_seconds)}</strong></div>
          )}
        </div>
      </Panel>

      {/* Score trend */}
      {data.score_trend && data.score_trend.length > 1 && (
        <Panel title="Score Trend Over Time">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.score_trend} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis
                dataKey="submitted_at"
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => new Date(v).toLocaleDateString()}
              />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
                formatter={(v: any) => [`${v}%`, 'Score']}
              />
              <ReferenceLine y={PASS} stroke="#dc2626" strokeDasharray="4 4" label={{ value: '90% pass line', fill: '#dc2626', fontSize: 11 }} />
              <Line type="monotone" dataKey="score_pct" stroke="#7c3aed" strokeWidth={2.5} dot={{ r: 4, fill: '#7c3aed' }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {/* Assessment history table */}
      {data.session_history && data.session_history.length > 0 && (
        <Panel title="Assessment History">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                  {['Assessment', 'Date', 'Score', 'Correct', 'Time', 'Pass/Fail', 'Auto'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.session_history as any[]).map((sh: any, i: number) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '9px 12px', fontWeight: 600, color: '#111' }}>{sh.assessment_name}</td>
                    <td style={{ padding: '9px 12px', color: '#6b7280', fontSize: 12 }}>
                      {sh.submitted_at ? new Date(sh.submitted_at).toLocaleDateString() : '—'}
                    </td>
                    <td style={{ padding: '9px 12px', fontWeight: 800, color: scoreColor(sh.score_pct) }}>{fmt(sh.score_pct)}</td>
                    <td style={{ padding: '9px 12px', color: '#374151' }}>{sh.correct_count}/{sh.total_questions}</td>
                    <td style={{ padding: '9px 12px', color: '#6b7280' }}>{fmtTime(sh.time_taken_seconds)}</td>
                    <td style={{ padding: '9px 12px' }}><PassBadge pf={sh.pass_fail} /></td>
                    <td style={{ padding: '9px 12px' }}>
                      {sh.auto_submitted && (
                        <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 20, fontWeight: 700 }}>Auto</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Topic strength/weakness */}
        {data.topic_strength && data.topic_strength.length > 0 && (
          <Panel title="Topic Strength / Weakness">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(data.topic_strength as any[]).map((t: any, i: number) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ fontWeight: 600, color: '#374151' }}>{t.topic}</span>
                    <span style={{ color: scoreColor(t.accuracy_pct), fontWeight: 700 }}>
                      {t.accuracy_pct != null ? `${t.accuracy_pct}%` : '—'}
                    </span>
                  </div>
                  <div style={{ height: 7, background: '#f3f4f6', borderRadius: 4 }}>
                    {t.accuracy_pct != null && (
                      <div style={{
                        height: '100%', borderRadius: 4,
                        width: `${Math.min(t.accuracy_pct, 100)}%`,
                        background: scoreColor(t.accuracy_pct),
                        transition: 'width 0.5s',
                      }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* Difficulty breakdown */}
        {data.difficulty_breakdown && (
          <Panel title="Difficulty Breakdown">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(data.difficulty_breakdown as any[]).map((d: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  background: 'rgba(249,250,251,0.8)',
                  borderRadius: 10,
                  padding: '12px 16px',
                  border: '1px solid #f3f4f6',
                }}>
                  <DiffBadge diff={d.difficulty} />
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor(d.accuracy_pct) }}>
                      {d.accuracy_pct != null ? `${d.accuracy_pct}%` : '—'}
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>{d.correct}/{d.total} correct</div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </div>
    </div>
  )
}

// ── Utility components ────────────────────────────────────────────────────────

function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '60px 0', color: '#7c3aed' }}>
      <Loader size={28} style={{ animation: 'spin 1s linear infinite' }} />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '60px 24px', color: '#9ca3af', gap: 12,
      background: 'rgba(255,255,255,0.5)', borderRadius: 16,
      border: '1px dashed #e5e7eb',
    }}>
      <AlertCircle size={32} />
      <div style={{ fontSize: 14, fontWeight: 600 }}>{message}</div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  padding: '9px 14px', borderRadius: 10, border: '1px solid #e5e7eb',
  fontSize: 13, outline: 'none', minWidth: 220,
}

const searchBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6,
  padding: '9px 20px', borderRadius: 10,
  background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
  color: '#fff', border: 'none', cursor: 'pointer',
  fontSize: 13, fontWeight: 700,
}

// ── Main export ───────────────────────────────────────────────────────────────

type AnalyticsTab = 'overview' | 'drill' | 'coder'

export function AnalyticsView() {
  const [tab, setTab] = useState<AnalyticsTab>('overview')

  const tabs: { id: AnalyticsTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'drill', label: 'Assessment Drill-down', icon: <TrendingUp size={14} /> },
    { id: 'coder', label: 'Coder History', icon: <User size={14} /> },
  ]

  return (
    <div>
      {/* Sub-tab bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 22 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', borderRadius: 10,
              border: tab === t.id ? '1px solid rgba(124,58,237,0.3)' : '1px solid transparent',
              background: tab === t.id ? 'rgba(124,58,237,0.1)' : 'rgba(255,255,255,0.5)',
              cursor: 'pointer', fontSize: 13, fontWeight: 700,
              color: tab === t.id ? '#7c3aed' : '#6b7280',
              backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
              transition: 'all 0.15s',
            }}
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'drill' && <AssessmentDrillTab />}
      {tab === 'coder' && <CoderHistoryTab />}
    </div>
  )
}
