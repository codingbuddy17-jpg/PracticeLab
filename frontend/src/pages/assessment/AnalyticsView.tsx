import { useState, useEffect } from 'react'
import { Loader, TrendingUp, BarChart2, User, Award, Clock, AlertCircle, CheckCircle, XCircle, Layers, Tag, BookOpen, Grid, ChevronDown, ChevronRight, FileDown } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, ReferenceLine, Cell,
} from 'recharts'
import {
  getAssessmentAnalyticsOverview,
  getAssessmentAnalyticsByAssessment,
  getAssessmentAnalyticsCoder,
  getAssessmentAnalyticsBySpecialty,
  getAssessmentAnalyticsByTopic,
  getAssessmentAnalyticsByBatch,
  getAssessmentAnalyticsBatchDrill,
  getAssessmentAnalyticsCoderMatrix,
  listAssessmentHistory,
  downloadAssessmentCoderReport,
  downloadAssessmentBatchReport,
  downloadAssessmentBatchCoderReportsZip,
} from '../../api'

// ── Helpers ───────────────────────────────────────────────────────────────────

const PASS = 90

function scoreColor(v: number | null | undefined): string {
  if (v == null) return '#9ca3af'
  if (v >= PASS) return '#16a34a'
  if (v >= 80) return '#d97706'
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
                  <Cell key={i} fill={entry.pass_rate >= PASS ? '#16a34a' : entry.pass_rate >= 80 ? '#d97706' : '#dc2626'} />
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
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
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
    getAssessmentAnalyticsCoder(
      coderName.trim(),
      employeeId.trim() || undefined,
      dateFrom || undefined,
      dateTo || undefined,
    )
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>From</span>
            <input
              type="date"
              style={{ ...inputStyle, maxWidth: 150, cursor: 'pointer' }}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>To</span>
            <input
              type="date"
              style={{ ...inputStyle, maxWidth: 150, cursor: 'pointer' }}
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
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
  const allSessionIds: number[] = (data.session_history || []).map((sh: any) => sh.session_id)
  const [excludedIds, setExcludedIds] = useState<Set<number>>(new Set())
  const [showFilter, setShowFilter] = useState(false)

  function toggleExclude(id: number) {
    setExcludedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function handleDownloadPdf() {
    downloadAssessmentCoderReport(
      data.coder_name,
      data.employee_id || undefined,
      undefined,
      undefined,
      excludedIds.size > 0 ? Array.from(excludedIds) : undefined,
    )
  }

  const includedCount = allSessionIds.length - excludedIds.size

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
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
              <button
                onClick={handleDownloadPdf}
                disabled={includedCount === 0}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '8px 16px', borderRadius: 10,
                  background: includedCount === 0 ? '#e5e7eb' : 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                  color: includedCount === 0 ? '#9ca3af' : '#fff',
                  border: 'none', cursor: includedCount === 0 ? 'not-allowed' : 'pointer',
                  fontSize: 12, fontWeight: 700,
                }}
              >
                <FileDown size={13} />
                {excludedIds.size > 0 ? `PDF (${includedCount} assessments)` : 'Download PDF Report'}
              </button>
              {allSessionIds.length > 1 && (
                <button
                  onClick={() => setShowFilter(v => !v)}
                  style={{
                    fontSize: 11, color: '#7c3aed', background: 'none', border: 'none',
                    cursor: 'pointer', fontWeight: 600, textDecoration: 'underline', padding: 0,
                  }}
                >
                  {showFilter ? 'Hide' : 'Select'} assessments for PDF
                </button>
              )}
            </div>
          </div>
        </div>

        {showFilter && allSessionIds.length > 1 && (
          <div style={{ marginTop: 14, padding: '12px 16px', background: 'rgba(124,58,237,0.05)', borderRadius: 10, border: '1px solid rgba(124,58,237,0.15)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#7c3aed', marginBottom: 10 }}>
              Include in PDF report — uncheck to exclude:
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(data.session_history as any[]).map((sh: any) => (
                <label key={sh.session_id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={!excludedIds.has(sh.session_id)}
                    onChange={() => toggleExclude(sh.session_id)}
                    style={{ accentColor: '#7c3aed', width: 15, height: 15 }}
                  />
                  <span style={{ fontWeight: 600, color: '#111' }}>{sh.assessment_name}</span>
                  <span style={{ color: '#6b7280', fontSize: 11 }}>
                    {sh.submitted_at ? new Date(sh.submitted_at).toLocaleDateString() : ''}
                  </span>
                  <span style={{ color: scoreColor(sh.score_pct), fontWeight: 700, fontSize: 12 }}>{fmt(sh.score_pct)}</span>
                  <PassBadge pf={sh.pass_fail} />
                </label>
              ))}
            </div>
            {excludedIds.size > 0 && (
              <button
                onClick={() => setExcludedIds(new Set())}
                style={{ marginTop: 8, fontSize: 11, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}
              >
                Reset (include all)
              </button>
            )}
          </div>
        )}

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

// ── By Specialty Tab ──────────────────────────────────────────────────────────

function BySpecialtyTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAssessmentAnalyticsBySpecialty()
      .then(setData)
      .catch(() => toast.error('Failed to load specialty analytics'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner />
  if (!data || !data.specialties || data.specialties.length === 0)
    return <EmptyState message="No specialty data available yet. Submit some assessments first." />

  const specialties: any[] = data.specialties
  const maxAcc = Math.max(...specialties.map((s: any) => s.accuracy_pct ?? 0))
  const minAcc = Math.min(...specialties.map((s: any) => s.accuracy_pct ?? 100))
  const avgAcc = specialties.reduce((sum: number, s: any) => sum + (s.accuracy_pct ?? 0), 0) / specialties.length

  return (
    <div>
      {/* KPI summary */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Specialties Covered" value={String(specialties.length)} icon={<Layers size={14} />} />
        <KpiCard label="Best Specialty Accuracy" value={fmt(Math.round(maxAcc * 10) / 10)} color={scoreColor(maxAcc)} icon={<Award size={14} />} />
        <KpiCard label="Weakest Specialty" value={fmt(Math.round(minAcc * 10) / 10)} color={scoreColor(minAcc)} icon={<AlertCircle size={14} />} />
        <KpiCard label="Overall Avg Accuracy" value={fmt(Math.round(avgAcc * 10) / 10)} color={scoreColor(avgAcc)} icon={<TrendingUp size={14} />} />
      </div>

      {/* Bar chart */}
      <Panel title="Accuracy by Specialty">
        <ResponsiveContainer width="100%" height={Math.max(260, specialties.length * 42)}>
          <BarChart
            data={[...specialties].sort((a, b) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0))}
            layout="vertical"
            margin={{ top: 5, right: 60, left: 160, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
            <YAxis type="category" dataKey="specialty" tick={{ fontSize: 12, fontWeight: 600 }} width={155} />
            <Tooltip formatter={(v: any) => [`${v}%`, 'Accuracy']} />
            <Bar dataKey="accuracy_pct" radius={[0, 4, 4, 0]}>
              {([...specialties].sort((a, b) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0)) as any[]).map((entry: any, i: number) => (
                <Cell key={i} fill={scoreColor(entry.accuracy_pct)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      {/* Detail table */}
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
                  <td style={{ padding: '10px 14px', fontWeight: 800, color: scoreColor(s.accuracy_pct), fontSize: 15 }}>
                    {s.accuracy_pct != null ? `${s.accuracy_pct}%` : '—'}
                  </td>
                  <td style={{ padding: '10px 14px', color: '#6b7280' }}>{s.correct} / {s.total_responses}</td>
                  <td style={{ padding: '10px 14px', color: '#374151' }}>{s.coder_count}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ width: 100, height: 8, background: '#f3f4f6', borderRadius: 4 }}>
                      {s.accuracy_pct != null && (
                        <div style={{
                          height: '100%', borderRadius: 4,
                          width: `${Math.min(s.accuracy_pct, 100)}%`,
                          background: scoreColor(s.accuracy_pct),
                          transition: 'width 0.5s',
                        }} />
                      )}
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

// ── By Topic Tab ──────────────────────────────────────────────────────────────

function ByTopicTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    getAssessmentAnalyticsByTopic()
      .then(setData)
      .catch(() => toast.error('Failed to load topic analytics'))
      .finally(() => setLoading(false))
  }, [])

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

  const chartData = [...filtered]
    .sort((a, b) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0))
    .slice(0, 20)

  return (
    <div>
      {/* Summary pills */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ background: '#dcfce7', border: '1px solid #bbf7d0', borderRadius: 10, padding: '10px 18px', fontSize: 13, fontWeight: 700, color: '#166534' }}>
          ✓ {strong} Strong topics (≥90%)
        </div>
        <div style={{ background: '#fef9c3', border: '1px solid #fde68a', borderRadius: 10, padding: '10px 18px', fontSize: 13, fontWeight: 700, color: '#854d0e' }}>
          ~ {mid} Mid topics (80–89%)
        </div>
        <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 10, padding: '10px 18px', fontSize: 13, fontWeight: 700, color: '#991b1b' }}>
          ✗ {weak} Weak topics (&lt;80%)
        </div>
      </div>

      {/* Search filter */}
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Tag size={14} color="#7c3aed" />
          <input
            style={{ ...inputStyle, flex: 1 }}
            placeholder="Filter by topic or specialty…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {filter && (
            <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 12 }} onClick={() => setFilter('')}>
              Clear
            </button>
          )}
          <span style={{ fontSize: 12, color: '#9ca3af' }}>{filtered.length} topic{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </Panel>

      {/* Bar chart — top 20 */}
      {chartData.length > 0 && (
        <Panel title={`Topic Accuracy${filtered.length > 20 ? ' (Top 20 shown)' : ''}`}>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 38)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 5, right: 60, left: 180, bottom: 5 }}
            >
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

      {/* Detail table */}
      <Panel title="Topic Detail">
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
              {filtered.map((t: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#111' }}>{t.topic}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(t.specialties as string[]).map((sp: string, j: number) => (
                        <span key={j} style={{ fontSize: 10, background: 'rgba(124,58,237,0.1)', color: '#7c3aed', padding: '1px 7px', borderRadius: 20, fontWeight: 700 }}>
                          {sp}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: '10px 14px', fontWeight: 800, color: scoreColor(t.accuracy_pct), fontSize: 14 }}>
                    {t.accuracy_pct != null ? `${t.accuracy_pct}%` : '—'}
                  </td>
                  <td style={{ padding: '10px 14px', color: '#6b7280' }}>{t.correct} / {t.total_responses}</td>
                  <td style={{ padding: '10px 14px', color: '#374151' }}>{t.coder_count}</td>
                  <td style={{ padding: '10px 14px', minWidth: 100 }}>
                    <div style={{ width: 90, height: 8, background: '#f3f4f6', borderRadius: 4 }}>
                      {t.accuracy_pct != null && (
                        <div style={{
                          height: '100%', borderRadius: 4,
                          width: `${Math.min(t.accuracy_pct, 100)}%`,
                          background: scoreColor(t.accuracy_pct),
                          transition: 'width 0.5s',
                        }} />
                      )}
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

// ── Batch Analysis Tab ────────────────────────────────────────────────────────

function BatchAnalysisTab() {
  const [batches, setBatches] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [drillData, setDrillData] = useState<Record<string, any>>({})
  const [drillLoading, setDrillLoading] = useState<string | null>(null)

  useEffect(() => {
    getAssessmentAnalyticsByBatch()
      .then((d: any) => setBatches(d.batches || []))
      .catch(() => toast.error('Failed to load batch analytics'))
      .finally(() => setLoading(false))
  }, [])

  function toggleBatch(batchName: string) {
    if (expanded === batchName) { setExpanded(null); return }
    setExpanded(batchName)
    if (!drillData[batchName]) {
      setDrillLoading(batchName)
      getAssessmentAnalyticsBatchDrill(batchName)
        .then((d: any) => setDrillData(prev => ({ ...prev, [batchName]: d })))
        .catch(() => toast.error('Failed to load batch detail'))
        .finally(() => setDrillLoading(null))
    }
  }

  if (loading) return <LoadingSpinner />
  if (!batches.length) return <EmptyState message="No batches yet. Add a Batch / Cohort Name when generating assessments." />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {batches.map((batch: any) => {
        const isOpen = expanded === batch.batch_name
        const drill = drillData[batch.batch_name]
        const isDrillLoading = drillLoading === batch.batch_name

        return (
          <div key={batch.batch_name} style={{
            background: 'rgba(255,255,255,0.68)', backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)', borderRadius: 16,
            border: isOpen ? '1px solid rgba(124,58,237,0.3)' : '1px solid rgba(255,255,255,0.55)',
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', overflow: 'hidden',
          }}>
            {/* Batch header — click to expand */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 24px' }}>
              <button
                onClick={() => toggleBatch(batch.batch_name)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0,
                }}
              >
                <span style={{ color: '#7c3aed' }}>{isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: '#111' }}>{batch.batch_name}</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    {batch.assessment_count} assessment{batch.assessment_count !== 1 ? 's' : ''} · {batch.total_coders} coder{batch.total_coders !== 1 ? 's' : ''}
                  </div>
                </div>
              </button>
              <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: scoreColor(batch.avg_score) }}>{fmt(batch.avg_score)}</div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Avg Score</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: batch.pass_rate != null && batch.pass_rate >= PASS ? '#16a34a' : '#dc2626' }}>{fmt(batch.pass_rate)}</div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Pass Rate</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#374151' }}>{batch.submitted_count}</div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Submitted</div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); downloadAssessmentBatchReport(batch.batch_name) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '7px 13px', borderRadius: 9,
                    background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                    color: '#fff', border: 'none', cursor: 'pointer',
                    fontSize: 11, fontWeight: 700,
                  }}
                >
                  <FileDown size={12} /> PDF Report
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); downloadAssessmentBatchCoderReportsZip(batch.batch_name) }}
                  title={`Download individual PDF reports for all ${batch.total_coders} coders as a ZIP`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '7px 13px', borderRadius: 9,
                    background: 'linear-gradient(135deg, #059669, #047857)',
                    color: '#fff', border: 'none', cursor: 'pointer',
                    fontSize: 11, fontWeight: 700,
                  }}
                >
                  <FileDown size={12} /> All Coder Reports (.zip)
                </button>
              </div>
            </div>

            {/* Drill-down content */}
            {isOpen && (
              <div style={{ padding: '0 24px 24px', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                {isDrillLoading && <div style={{ padding: '24px 0', color: '#7c3aed', display: 'flex', alignItems: 'center', gap: 8 }}><Loader size={16} style={{ animation: 'spin 1s linear infinite' }} /> Loading batch detail…</div>}

                {drill && !isDrillLoading && (
                  <div>
                    {/* TNI section */}
                    <div style={{ marginTop: 20, marginBottom: 20 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: '#111', marginBottom: 10 }}>Training Need Identification (TNI)</div>
                      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' as const }}>
                        <div style={{ flex: 1, minWidth: 200 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#dc2626', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 6 }}>
                            ✗ Weak Topics (need training)
                          </div>
                          {drill.weak_topics.length === 0
                            ? <div style={{ fontSize: 12, color: '#9ca3af' }}>None — all topics above 80%</div>
                            : drill.weak_topics.map((t: any, i: number) => (
                              <div key={i} style={{
                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                background: '#fee2e2', color: '#991b1b', borderRadius: 20,
                                padding: '4px 12px', margin: '3px 4px 3px 0', fontSize: 12, fontWeight: 700,
                              }}>
                                {t.topic} <span style={{ opacity: 0.7 }}>{t.accuracy_pct}%</span>
                              </div>
                            ))
                          }
                        </div>
                        <div style={{ flex: 1, minWidth: 200 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#16a34a', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 6 }}>
                            ✓ Strong Topics (well performed)
                          </div>
                          {drill.strong_topics.length === 0
                            ? <div style={{ fontSize: 12, color: '#9ca3af' }}>None above 90% yet</div>
                            : drill.strong_topics.map((t: any, i: number) => (
                              <div key={i} style={{
                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                background: '#dcfce7', color: '#166534', borderRadius: 20,
                                padding: '4px 12px', margin: '3px 4px 3px 0', fontSize: 12, fontWeight: 700,
                              }}>
                                {t.topic} <span style={{ opacity: 0.7 }}>{t.accuracy_pct}%</span>
                              </div>
                            ))
                          }
                        </div>
                      </div>
                    </div>

                    {/* Coder × Topic matrix */}
                    {drill.all_topics && drill.all_topics.length > 0 && drill.coder_rows && drill.coder_rows.length > 0 && (
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: '#111', marginBottom: 10 }}>Coder × Topic Accuracy Matrix</div>
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                            <thead>
                              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, whiteSpace: 'nowrap' as const }}>Coder</th>
                                {(drill.all_topics as string[]).map((tp: string) => (
                                  <th key={tp} style={{ padding: '8px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, whiteSpace: 'nowrap' as const, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    <div style={{ maxWidth: 90, overflow: 'hidden', textOverflow: 'ellipsis' }}>{tp}</div>
                                  </th>
                                ))}
                                <th style={{ textAlign: 'center', padding: '8px 10px', color: '#6b7280', fontWeight: 700, fontSize: 11 }}>Score</th>
                                <th style={{ textAlign: 'center', padding: '8px 10px', color: '#6b7280', fontWeight: 700, fontSize: 11 }}>Δ</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(drill.coder_rows as any[]).map((row: any, i: number) => (
                                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                                  <td style={{ padding: '7px 12px', fontWeight: 700, color: '#111', whiteSpace: 'nowrap' as const }}>{row.coder_name}</td>
                                  {(drill.all_topics as string[]).map((tp: string) => {
                                    const acc = row.topics[tp]
                                    const bg = acc == null ? '#f9fafb' : acc >= 90 ? 'rgba(22,163,74,0.14)' : acc >= 80 ? 'rgba(217,119,6,0.12)' : 'rgba(220,38,38,0.1)'
                                    return (
                                      <td key={tp} style={{ padding: '7px 10px', textAlign: 'center', background: bg, fontWeight: 700, fontSize: 12, color: scoreColor(acc) }}>
                                        {acc != null ? `${acc}%` : '—'}
                                      </td>
                                    )
                                  })}
                                  <td style={{ padding: '7px 10px', textAlign: 'center', fontWeight: 800, color: scoreColor(row.latest_score) }}>
                                    {row.latest_score != null ? `${row.latest_score}%` : '—'}
                                  </td>
                                  <td style={{ padding: '7px 10px', textAlign: 'center', fontWeight: 700, fontSize: 12,
                                    color: row.delta == null ? '#9ca3af' : row.delta > 0 ? '#16a34a' : row.delta < 0 ? '#dc2626' : '#6b7280' }}>
                                    {row.delta == null ? '—' : row.delta > 0 ? `↑${row.delta}` : row.delta < 0 ? `↓${Math.abs(row.delta)}` : '0'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>Δ = score change across assessments in this batch. Green = improved, Red = regressed.</div>
                      </div>
                    )}

                    {/* Assessments in this batch */}
                    {drill.assessments && drill.assessments.length > 0 && (
                      <div style={{ marginTop: 20 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginBottom: 8 }}>Assessments in this batch</div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' as const }}>
                          {(drill.assessments as any[]).map((a: any) => (
                            <div key={a.id} style={{ fontSize: 12, background: 'rgba(124,58,237,0.08)', color: '#7c3aed', padding: '4px 12px', borderRadius: 20, fontWeight: 600 }}>
                              {a.name} {a.generated_at ? `(${new Date(a.generated_at).toLocaleDateString()})` : ''}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Coder Matrix Tab ──────────────────────────────────────────────────────────

function CoderMatrixTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAssessmentAnalyticsCoderMatrix()
      .then(setData)
      .catch(() => toast.error('Failed to load coder matrix'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner />
  if (!data || !data.coders || data.coders.length === 0)
    return <EmptyState message="No coder matrix data yet. Submit some assessments first." />

  const coders: any[] = data.coders
  const specialties: string[] = data.specialties

  return (
    <div>
      <Panel>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
          Each cell shows a coder's accuracy on that specialty across all assessments.
          Color intensity indicates performance — <span style={{ color: '#dc2626', fontWeight: 700 }}>red = gap area</span>,{' '}
          <span style={{ color: '#d97706', fontWeight: 700 }}>amber = developing</span>,{' '}
          <span style={{ color: '#16a34a', fontWeight: 700 }}>green = strong</span>.
        </div>
      </Panel>

      <Panel title={`Coder × Specialty Matrix (${coders.length} coders, ${specialties.length} specialties)`}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                <th style={{ textAlign: 'left', padding: '10px 14px', color: '#6b7280', fontWeight: 700, fontSize: 11, whiteSpace: 'nowrap' as const, minWidth: 140 }}>Coder</th>
                {specialties.map((sp: string) => (
                  <th key={sp} style={{ padding: '10px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, textAlign: 'center', whiteSpace: 'nowrap' as const }}>
                    <div style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', margin: '0 auto' }}>{sp}</div>
                  </th>
                ))}
                <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Avg Score</th>
                <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Assessments</th>
              </tr>
            </thead>
            <tbody>
              {coders.map((coder: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 700, color: '#111', whiteSpace: 'nowrap' as const }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{
                        width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                        background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: '#fff', fontSize: 11, fontWeight: 800,
                      }}>
                        {coder.coder_name.charAt(0).toUpperCase()}
                      </div>
                      {coder.coder_name}
                    </div>
                  </td>
                  {specialties.map((sp: string) => {
                    const acc: number | null = coder.specialties[sp]
                    const bg = acc == null ? '#f9fafb' : acc >= 90 ? 'rgba(22,163,74,0.15)' : acc >= 80 ? 'rgba(217,119,6,0.13)' : 'rgba(220,38,38,0.11)'
                    return (
                      <td key={sp} style={{
                        padding: '8px 10px', textAlign: 'center',
                        background: bg, fontWeight: 700, fontSize: 12,
                        color: scoreColor(acc),
                        borderLeft: '1px solid rgba(0,0,0,0.04)',
                      }}>
                        {acc != null ? `${acc}%` : <span style={{ color: '#d1d5db' }}>—</span>}
                      </td>
                    )
                  })}
                  <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 800, fontSize: 14, color: scoreColor(coder.avg_score) }}>
                    {fmt(coder.avg_score)}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280', fontWeight: 600 }}>
                    {coder.assessments_taken}
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

// ── Main export ───────────────────────────────────────────────────────────────

type AnalyticsTab = 'overview' | 'drill' | 'coder' | 'specialty' | 'topic' | 'batch' | 'matrix'

export function AnalyticsView() {
  const [tab, setTab] = useState<AnalyticsTab>('overview')

  const tabs: { id: AnalyticsTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'batch', label: 'Batch Analysis', icon: <BookOpen size={14} /> },
    { id: 'drill', label: 'Assessment Drill-down', icon: <TrendingUp size={14} /> },
    { id: 'specialty', label: 'By Specialty', icon: <Layers size={14} /> },
    { id: 'topic', label: 'By Topic', icon: <Tag size={14} /> },
    { id: 'matrix', label: 'Coder Matrix', icon: <Grid size={14} /> },
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
      {tab === 'batch' && <BatchAnalysisTab />}
      {tab === 'drill' && <AssessmentDrillTab />}
      {tab === 'specialty' && <BySpecialtyTab />}
      {tab === 'topic' && <ByTopicTab />}
      {tab === 'matrix' && <CoderMatrixTab />}
      {tab === 'coder' && <CoderHistoryTab />}
    </div>
  )
}
