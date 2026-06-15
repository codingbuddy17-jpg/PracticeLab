import { useState, useEffect } from 'react'
import { Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell,
} from 'recharts'
import {
  getPLAnalyticsOverview, getPLAnalyticsBySpecialty, getPLAnalyticsByChart,
  getPLAnalyticsByBatch, getCoderTrend, getCoderSummary,
  getPLAnalyticsByCategory, getPLChartTeachingValue, getPLCoderMatrix, getPLChartDetail,
  type PLFilters,
} from '../../api'
import { round1 } from './shared'
import styles from './styles'

const TEACHING_LABEL_META: Record<string, { color: string; bg: string; desc: string }> = {
  'High Yield':    { color: '#166534', bg: '#dcfce7', desc: 'Commonly attempted, produces meaningful repeatable mistakes' },
  'High Confusion':{ color: '#92400e', bg: '#fef3c7', desc: '>60% fail rate with diverse error types — review answer key' },
  'High Fail':     { color: '#991b1b', bg: '#fee2e2', desc: 'High failure rate, low error variety' },
  'Too Easy':      { color: '#1d4ed8', bg: '#dbeafe', desc: 'Avg score ≥90% — suitable for beginner packs' },
  'Underused':     { color: '#6b7280', bg: '#f3f4f6', desc: 'Fewer than 2 grading attempts' },
  'Standard':      { color: '#374151', bg: '#f9fafb', desc: 'Typical performance range' },
}

const TAB_STORAGE_KEY = 'pl_analytics_tab'

export function PLAnalyticsView() {
  const [tab, setTab] = useState<'overview' | 'specialty' | 'chart' | 'batch' | 'coder' | 'category' | 'teaching' | 'matrix'>(
    () => (localStorage.getItem(TAB_STORAGE_KEY) as any) || 'overview'
  )

  useEffect(() => { localStorage.setItem(TAB_STORAGE_KEY, tab) }, [tab])
  const [overview, setOverview] = useState<any>(null)
  const [bySpecialty, setBySpecialty] = useState<any[]>([])
  const [byChart, setByChart] = useState<any[]>([])
  const [byBatch, setByBatch] = useState<any[]>([])
  const [coderName, setCoderName] = useState('')
  const [coderTrend, setCoderTrend] = useState<any[]>([])
  const [coderSummary, setCoderSummary] = useState<any>(null)
  const [categoryData, setCategoryData] = useState<{ team: any[]; coder_category: any[] } | null>(null)
  const [teachingData, setTeachingData] = useState<any[]>([])
  const [matrixData, setMatrixData] = useState<{ batches: any[]; coders: string[]; cells: any[] } | null>(null)
  const [teachingFilter, setTeachingFilter] = useState<string>('All')
  const [loading, setLoading] = useState(false)
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  const [chartDetail, setChartDetail] = useState<Record<string, any>>({})
  const [draftFilters, setDraftFilters] = useState<PLFilters>({})
  const [filters, setFilters] = useState<PLFilters>({})
  const [filterVersion, setFilterVersion] = useState(0)
  const [matrixCoderSearch, setMatrixCoderSearch] = useState('')
  const [matrixShowAll, setMatrixShowAll] = useState(false)
  const [heatmapCoderSearch, setHeatmapCoderSearch] = useState('')
  const [heatmapShowAll, setHeatmapShowAll] = useState(false)
  const [heatmapSort, setHeatmapSort] = useState<{ col: string; dir: 'asc' | 'desc' }>({ col: 'coder', dir: 'asc' })
  const [matrixSort, setMatrixSort] = useState<{ col: string; dir: 'asc' | 'desc' }>({ col: 'overall', dir: 'desc' })
  const [chartValueShowAll, setChartValueShowAll] = useState(false)
  const [chartValueSort, setChartValueSort] = useState<'score_asc' | 'attempts_desc' | 'score_desc'>('score_asc')

  const CODER_PAGE = 25
  const CHART_VALUE_PAGE = 24

  function sortIcon(col: string, active: { col: string; dir: string }) {
    if (active.col !== col) return <span style={{ color: '#d1d5db', fontSize: 10 }}> ⇅</span>
    return <span style={{ color: '#4f46e5', fontSize: 10 }}>{active.dir === 'asc' ? ' ↑' : ' ↓'}</span>
  }
  function toggleSort(col: string, current: { col: string; dir: 'asc' | 'desc' }, setter: (v: any) => void) {
    setter(current.col === col ? { col, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })
  }

  const SPECIALTIES = ['IP-DRG', 'ED Facility', 'ED Profee', 'SDS', 'Edits', 'Denials', 'Ancillary', 'E/M']
  const activeFilterCount = Object.values(filters).filter(Boolean).length

  function applyFilters() {
    setFilters({ ...draftFilters })
    setByChart([]); setCategoryData(null); setTeachingData([]); setMatrixData(null)
    setFilterVersion(v => v + 1)
  }

  function clearFilters() {
    setDraftFilters({})
    setFilters({})
    setByChart([]); setCategoryData(null); setTeachingData([]); setMatrixData(null)
    setFilterVersion(v => v + 1)
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getPLAnalyticsOverview(filters),
      getPLAnalyticsBySpecialty(filters),
      getPLAnalyticsByBatch(filters),
    ]).then(([ov, sp, bt]) => {
      setOverview(ov); setBySpecialty(sp); setByBatch(bt)
    }).catch(() => toast.error('Failed to load analytics')).finally(() => setLoading(false))
  }, [filters])

  useEffect(() => {
    if ((tab === 'chart' || tab === 'category') && byChart.length === 0) getPLAnalyticsByChart(filters).then(setByChart).catch(() => {})
    if (tab === 'category' && !categoryData) getPLAnalyticsByCategory(filters).then(setCategoryData).catch(() => {})
    if (tab === 'teaching' && teachingData.length === 0) getPLChartTeachingValue(filters).then(setTeachingData).catch(() => {})
    if ((tab === 'matrix' || tab === 'coder') && !matrixData) getPLCoderMatrix(filters).then(setMatrixData).catch(() => {})
  }, [tab, filterVersion])

  async function loadCoderTrend() {
    if (!coderName.trim()) return
    const name = coderName.trim()
    setCoderSummary(null)
    setCoderTrend([])
    const [summary, trend] = await Promise.all([
      getCoderSummary(name, filters).catch(() => null),
      getCoderTrend(name, filters).catch(() => null),
    ])
    if (!summary && !trend?.length) { toast.error('No data for this coder'); return }
    if (summary) setCoderSummary(summary)
    if (trend) setCoderTrend(trend)
  }

  function jumpToCoder(name: string) {
    setCoderName(name)
    setTab('coder')
    setCoderSummary(null)
    setCoderTrend([])
    Promise.all([getCoderSummary(name, filters).catch(() => null), getCoderTrend(name, filters).catch(() => null)])
      .then(([summary, trend]) => {
        if (summary) setCoderSummary(summary)
        if (trend) setCoderTrend(trend)
      })
      .catch(() => toast.error('No data for this coder'))
  }

  async function toggleChartDetail(chartNumber: string) {
    if (expandedChart === chartNumber) { setExpandedChart(null); return }
    if (chartDetail[chartNumber]) { setExpandedChart(chartNumber); return }
    try {
      const d = await getPLChartDetail(chartNumber)
      setChartDetail(prev => ({ ...prev, [chartNumber]: d }))
      setExpandedChart(chartNumber)
    } catch { toast.error('Failed to load chart detail') }
  }

  const coderLink = (name: string) => (
    <button onClick={() => jumpToCoder(name)}
      style={{ background: 'none', border: 'none', padding: 0, color: '#4f46e5', fontWeight: 700, cursor: 'pointer', fontSize: 'inherit', textDecoration: 'underline' }}>
      {name}
    </button>
  )

  const TABS = [
    { key: 'overview', label: 'Overview' },
    { key: 'specialty', label: 'By Specialty' },
    { key: 'batch', label: 'By Batch' },
    { key: 'coder', label: 'Coder Trend' },
    { key: 'category', label: 'Category Mastery' },
    { key: 'teaching', label: 'Chart Value' },
    { key: 'matrix', label: 'Coder Matrix' },
    { key: 'chart', label: 'By Chart' },
  ]

  if (loading) return <div style={styles.center}><Loader size={24} /></div>

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={styles.sectionTitle}>Analytics</span>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '10px 14px', background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 8, flexWrap: 'wrap' as const }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginRight: 4 }}>Filter</span>
        <input type="date" style={{ ...styles.input, width: 140, fontSize: 12 }}
          value={draftFilters.from_date || ''}
          onChange={e => setDraftFilters(f => ({ ...f, from_date: e.target.value || undefined }))} />
        <span style={{ fontSize: 12, color: '#9ca3af' }}>→</span>
        <input type="date" style={{ ...styles.input, width: 140, fontSize: 12 }}
          value={draftFilters.to_date || ''}
          onChange={e => setDraftFilters(f => ({ ...f, to_date: e.target.value || undefined }))} />
        <select style={{ ...styles.select, fontSize: 12 }}
          value={draftFilters.specialty || ''}
          onChange={e => setDraftFilters(f => ({ ...f, specialty: e.target.value || undefined }))}>
          <option value="">All specialties</option>
          {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button style={styles.primaryBtn} onClick={applyFilters}>Apply</button>
        {activeFilterCount > 0 && (
          <button style={styles.outlineBtn} onClick={clearFilters}>
            Clear {activeFilterCount > 0 ? `(${activeFilterCount})` : ''}
          </button>
        )}
        {activeFilterCount > 0 && (
          <span style={{ fontSize: 11, color: '#4f46e5', fontWeight: 700 }}>Filtered view active</span>
        )}
      </div>

      <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', alignSelf: 'flex-start', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.key}
            style={tab === t.key ? { ...styles.modeTab, background: '#4f46e5', color: '#fff', padding: '7px 16px' } : { ...styles.modeTab, padding: '7px 16px' }}
            onClick={() => setTab(t.key as any)}>{t.label}</button>
        ))}
      </div>

      {tab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {!overview ? (
            <div style={styles.emptyState}>No grading data yet</div>
          ) : (
            <>
              <div style={styles.statsRow}>
                {[
                  { label: 'Total Batches', value: overview.total_batches },
                  { label: 'Open Batches', value: overview.open_batches ?? 0, color: '#2563eb' },
                  { label: 'Closed Batches', value: overview.complete_batches ?? 0, color: '#16a34a' },
                  { label: 'Total Graded', value: overview.total_graded },
                  { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%`, color: overview.overall_pass_rate >= 80 ? '#16a34a' : overview.overall_pass_rate >= 60 ? '#d97706' : '#dc2626' },
                ].map(s => (
                  <div key={s.label} style={styles.statCard}>
                    <div style={{ ...styles.statValue, color: (s as any).color || '#111' }}>{s.value}</div>
                    <div style={styles.statLabel}>{s.label}</div>
                  </div>
                ))}
              </div>
              {/* Attention banner */}
              {overview.total_graded > 0 && (() => {
                const atRisk = bySpecialty.filter((s: any) => s.pass_rate < 70)
                if (!atRisk.length) return null
                return (
                  <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 10, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#92400e' }}>⚠ Needs attention</div>
                    {atRisk.map((s: any) => (
                      <div key={s.specialty} style={{ fontSize: 13, color: '#92400e' }}>
                        <strong>{s.specialty}</strong> — {s.pass_rate}% pass rate (below 70% target)
                        {s.pass_rate < 50 && <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, background: '#fecaca', color: '#991b1b', padding: '1px 8px', borderRadius: 10 }}>Critical</span>}
                      </div>
                    ))}
                  </div>
                )
              })()}

              {/* Mini batch trend */}
              {byBatch.length > 1 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginBottom: 10, textTransform: 'uppercase' as const, letterSpacing: 0.5 }}>Pass rate trend — last {Math.min(byBatch.length, 8)} batches</div>
                  <ResponsiveContainer width="100%" height={100}>
                    <LineChart data={byBatch.slice(-8).map((b: any) => ({ ...b, label: b.batch_name.length > 12 ? b.batch_name.slice(0, 12) + '…' : b.batch_name }))} margin={{ left: 0, right: 16, top: 4, bottom: 4 }}>
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                      <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} width={32} />
                      <Tooltip formatter={(v: any) => [`${v}%`, 'Pass Rate']} contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                      <Line type="monotone" dataKey="pass_rate" stroke="#16a34a" strokeWidth={2} dot={{ r: 4, fill: '#16a34a' }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {overview.total_graded === 0 ? (
                <div style={{ ...styles.warnBox, lineHeight: 1.6 }}>
                  No grading results yet. Run an allocation cycle inside a batch, distribute the Excel sheets to coders, then upload the returned files to unlock analytics.
                </div>
              ) : (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px', display: 'flex', alignItems: 'center', gap: 32 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 4 }}>Overall Pass / Fail Split</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{overview.total_graded} graded submissions</div>
                  </div>
                  <PieChart width={180} height={180}>
                    <Pie data={[{ name: 'Passed', value: overview.total_passed }, { name: 'Failed', value: overview.total_graded - overview.total_passed }]}
                      cx={90} cy={90} innerRadius={52} outerRadius={80} paddingAngle={3} dataKey="value">
                      <Cell fill="#16a34a" /><Cell fill="#dc2626" />
                    </Pie>
                    <Tooltip formatter={(v: any, name: any) => [v, name]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'specialty' && (
        <div>
          {bySpecialty.length === 0 ? <div style={styles.emptyState}>No specialty data yet — upload and grade at least one batch to see a breakdown here.</div> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Avg Score & Pass Rate by Specialty</div>
                <ResponsiveContainer width="100%" height={Math.max(200, bySpecialty.length * 56)}>
                  <BarChart data={bySpecialty} layout="vertical" margin={{ left: 20, right: 50, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="specialty" width={110} tick={{ fontSize: 12, fontWeight: 600 }} />
                    <Tooltip formatter={(v: any, name: any) => [`${v}%`, name === 'avg_score' ? 'Avg Score' : 'Pass Rate']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'avg_score' ? 'Avg Score' : 'Pass Rate'} />
                    <Bar dataKey="avg_score" name="avg_score" radius={[0, 4, 4, 0]} fill="#4f46e5" fillOpacity={0.85} />
                    <Bar dataKey="pass_rate" name="pass_rate" radius={[0, 4, 4, 0]} fill="#16a34a" fillOpacity={0.85} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
                  <span>Specialty</span><span>Graded</span><span>Avg Score</span><span>Pass Rate</span>
                </div>
                {bySpecialty.map((r: any, i: number) => (
                  <div key={r.specialty} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
                    <span style={{ fontWeight: 600 }}>{r.specialty}</span>
                    <span>{r.total}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                    <span style={{ fontWeight: 700, color: r.pass_rate >= 80 ? '#16a34a' : r.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{r.pass_rate}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'chart' && (
        <div>
          {byChart.length === 0 ? <div style={styles.emptyState}>No chart data yet — charts appear here once grading results are submitted.</div> : (
            <div style={styles.table}>
              <div style={{ ...styles.tableHeader, gridTemplateColumns: '120px 1fr 1fr 80px 90px' }}>
                <span>Chart</span><span>Category</span><span>Specialty</span>
                <span style={{ textAlign: 'center' as const }}>Attempts</span>
                <span style={{ textAlign: 'center' as const }}>Avg Score</span>
              </div>
              {byChart.map((r: any, i: number) => (
                <div key={r.chart_number} style={{ borderBottom: '1px solid #f3f4f6', background: expandedChart === r.chart_number ? '#f5f3ff' : i % 2 === 1 ? '#f9fafb' : '#fff' }}>
                  {/* Main data row */}
                  <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 80px 90px', padding: '10px 16px', alignItems: 'center', cursor: 'pointer' }}
                    onClick={() => toggleChartDetail(r.chart_number)}>
                    <span style={{ fontWeight: 700, color: '#4f46e5', fontSize: 13 }}>{r.chart_number} {expandedChart === r.chart_number ? '▲' : '▼'}</span>
                    <span style={{ fontSize: 12, color: '#374151' }}>{r.category}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span style={{ fontSize: 13, textAlign: 'center' as const }}>{r.attempt_count}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, textAlign: 'center' as const, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                  </div>
                  {/* Top missed badges — only when collapsed */}
                  {r.top_missed?.length > 0 && expandedChart !== r.chart_number && (
                    <div style={{ padding: '0 16px 8px 136px', display: 'flex', gap: 6, flexWrap: 'wrap' as const }}>
                      {r.top_missed.map(([code, cnt]: any) => (
                        <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '2px 8px', borderRadius: 10 }}>{code} {cnt}×</span>
                      ))}
                    </div>
                  )}
                  {expandedChart === r.chart_number && chartDetail[r.chart_number] && (
                    <div style={{ padding: '12px 16px', background: '#fafafa', borderTop: '1px solid #ede9fe' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>Coder breakdown</div>
                      {chartDetail[r.chart_number].coders.length === 0 ? (
                        <div style={{ fontSize: 12, color: '#9ca3af' }}>No graded results for this chart.</div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {chartDetail[r.chart_number].coders.slice(0, 8).map((c: any) => (
                            <div key={`${c.coder_name}-${c.batch_name}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 10px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12 }}>
                              <span style={{ minWidth: 140 }}>{coderLink(c.coder_name)}</span>
                              <span style={{ fontSize: 11, color: '#9ca3af', flex: 1 }}>{c.batch_name}</span>
                              <span style={{ fontWeight: 700, color: (c.total_score ?? 0) >= 80 ? '#16a34a' : (c.total_score ?? 0) >= 60 ? '#d97706' : '#dc2626' }}>{c.total_score}%</span>
                              <span style={{ fontWeight: 700, fontSize: 11, color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{c.pass_fail}</span>
                              {c.missed_codes?.length > 0 && (
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' as const, alignItems: 'center' }}>
                                  {c.missed_codes.slice(0, 5).map((code: string) => (
                                    <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '1px 6px', borderRadius: 8 }}>{code}</span>
                                  ))}
                                  {c.missed_codes.length > 5 && (
                                    <span style={{ fontSize: 10, color: '#9ca3af' }}>+{c.missed_codes.length - 5} more</span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                          {chartDetail[r.chart_number].coders.length > 8 && (
                            <div style={{ fontSize: 11, color: '#6b7280', padding: '4px 10px' }}>
                              + {chartDetail[r.chart_number].coders.length - 8} more attempts — use Coder Matrix for full view
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'batch' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {byBatch.length === 0 ? <div style={styles.emptyState}>No batch results yet — close a batch after grading to see trends over time.</div> : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Pass Rate & Avg Score Over Batches</div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={byBatch.map(b => ({ ...b, label: b.batch_name.length > 16 ? b.batch_name.slice(0, 16) + '…' : b.batch_name }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any, name: any) => [`${v}%`, name === 'pass_rate' ? 'Pass Rate' : 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'pass_rate' ? 'Pass Rate' : 'Avg Score'} />
                    <Line type="monotone" dataKey="pass_rate" stroke="#16a34a" strokeWidth={2.5} dot={{ r: 5, fill: '#16a34a' }} activeDot={{ r: 7 }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 5, fill: '#4f46e5' }} activeDot={{ r: 7 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 100px 80px 80px 80px' }}>
                  <span>Batch</span><span>Specialty</span><span>Coders</span><span>Avg Score</span><span>Pass Rate</span>
                </div>
                {byBatch.map((r: any, i: number) => (
                  <div key={r.batch_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 100px 80px 80px 80px' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{r.batch_name}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span>{r.coder_count}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                    <span style={{ fontWeight: 700, color: r.pass_rate >= 80 ? '#16a34a' : r.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{r.pass_rate}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'coder' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input list="coder-suggestions" style={{ ...styles.input, width: 260 }} placeholder="Enter or select coder name"
              value={coderName} onChange={e => setCoderName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadCoderTrend()} />
            <datalist id="coder-suggestions">{(matrixData?.coders || []).map((n: string) => <option key={n} value={n} />)}</datalist>
            <button style={styles.primaryBtn} onClick={loadCoderTrend}>Look Up</button>
          </div>

          {!coderSummary && coderTrend.length === 0 ? (
            <div style={styles.emptyState}>Enter the coder's name and press Look Up to see their full performance profile across all batches.</div>
          ) : (
            <>
              {/* Summary stat cards */}
              {coderSummary && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={styles.statsRow}>
                    <div style={styles.statCard}>
                      <div style={styles.statValue}>{coderSummary.total_charts ?? 0}</div>
                      <div style={styles.statLabel}>Charts Completed</div>
                    </div>
                    <div style={styles.statCard}>
                      <div style={{ ...styles.statValue, color: '#16a34a' }}>{coderSummary.charts_passed ?? 0}</div>
                      <div style={styles.statLabel}>Charts Passed</div>
                    </div>
                    {coderSummary.weighted_accuracy != null && (
                      <div style={styles.statCard}>
                        <div style={{ ...styles.statValue, color: coderSummary.weighted_accuracy >= 90 ? '#16a34a' : coderSummary.weighted_accuracy >= 80 ? '#d97706' : '#dc2626' }}>
                          {coderSummary.weighted_accuracy}%
                        </div>
                        <div style={styles.statLabel}>Weighted Accuracy</div>
                      </div>
                    )}
                    {coderSummary.cumulative_dpo?.overall_accuracy != null && (
                      <div style={styles.statCard}>
                        <div style={{ ...styles.statValue, color: coderSummary.cumulative_dpo.overall_accuracy >= 90 ? '#16a34a' : coderSummary.cumulative_dpo.overall_accuracy >= 80 ? '#d97706' : '#dc2626' }}>
                          {coderSummary.cumulative_dpo.overall_accuracy}%
                        </div>
                        <div style={styles.statLabel}>Overall DPO</div>
                      </div>
                    )}
                  </div>

                  {/* DPO breakdown */}
                  {coderSummary.cumulative_dpo && (coderSummary.cumulative_dpo.dx_accuracy != null || coderSummary.cumulative_dpo.poa_accuracy != null || coderSummary.cumulative_dpo.proc_accuracy != null) && (
                    <div style={{ background: '#f8faff', border: '1px solid #e0e7ff', borderRadius: 10, padding: '14px 18px' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' as const, letterSpacing: 0.6, marginBottom: 10 }}>DPO Cumulative (All Batches)</div>
                      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' as const }}>
                        {coderSummary.cumulative_dpo.dx_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: coderSummary.cumulative_dpo.dx_accuracy >= 90 ? '#16a34a' : coderSummary.cumulative_dpo.dx_accuracy >= 80 ? '#d97706' : '#dc2626' }}>{coderSummary.cumulative_dpo.dx_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>Dx</div>
                          </div>
                        )}
                        {coderSummary.cumulative_dpo.poa_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: coderSummary.cumulative_dpo.poa_accuracy >= 90 ? '#16a34a' : coderSummary.cumulative_dpo.poa_accuracy >= 80 ? '#d97706' : '#dc2626' }}>{coderSummary.cumulative_dpo.poa_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>POA</div>
                          </div>
                        )}
                        {coderSummary.cumulative_dpo.proc_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: coderSummary.cumulative_dpo.proc_accuracy >= 90 ? '#16a34a' : coderSummary.cumulative_dpo.proc_accuracy >= 80 ? '#d97706' : '#dc2626' }}>{coderSummary.cumulative_dpo.proc_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>PCS/CPT</div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Top / Bottom categories */}
                  {coderSummary.by_category?.length > 0 && (() => {
                    const cats: any[] = coderSummary.by_category
                    const splitAt = Math.min(3, Math.floor(cats.length / 2))
                    const top = cats.slice(0, splitAt)
                    const bottom = cats.length > splitAt ? cats.slice(-splitAt).reverse() : []
                    return (
                      <div style={{ display: 'grid', gridTemplateColumns: bottom.length ? '1fr 1fr' : '1fr', gap: 12 }}>
                        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '12px 14px' }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#166534', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 8 }}>Top Categories</div>
                          {top.map((c: any) => (
                            <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #dcfce7', fontSize: 12 }}>
                              <span style={{ fontWeight: 600, color: '#111' }}>{c.category}</span>
                              <span style={{ display: 'flex', gap: 8, color: '#6b7280' }}>
                                <span>{c.charts} charts</span>
                                <span style={{ fontWeight: 700, color: '#16a34a' }}>{c.avg_score}%</span>
                              </span>
                            </div>
                          ))}
                        </div>
                        {bottom.length > 0 && (
                          <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 10, padding: '12px 14px' }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#92400e', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 8 }}>Needs Work</div>
                            {bottom.map((c: any) => (
                              <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #fde68a', fontSize: 12 }}>
                                <span style={{ fontWeight: 600, color: '#111' }}>{c.category}</span>
                                <span style={{ display: 'flex', gap: 8, color: '#6b7280' }}>
                                  <span>{c.charts} charts</span>
                                  <span style={{ fontWeight: 700, color: c.avg_score >= 80 ? '#16a34a' : c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              )}

              {/* Score trend chart */}
              {coderTrend.length > 1 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Score Trend — {coderName}</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={coderTrend.map(r => ({ ...r, label: r.batch_name.length > 14 ? r.batch_name.slice(0, 14) + '…' : r.batch_name }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v: any) => [`${v}%`, 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                      <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 6, fill: '#4f46e5' }} activeDot={{ r: 8 }} name="Avg Score" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Batch history table */}
              {(coderSummary?.batches?.length > 0 || coderTrend.length > 0) && (() => {
                const rows: any[] = coderSummary?.batches?.length ? coderSummary.batches : coderTrend
                return (
                  <div style={styles.table}>
                    <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 100px 100px 80px 80px 80px' }}>
                      <span>Batch</span><span>Specialty</span><span>Date</span><span>Charts</span><span>Avg Score</span><span>Passed</span>
                    </div>
                    {rows.map((r: any, i: number) => {
                      const prev = rows[i - 1]
                      const delta = prev?.avg_score != null && r.avg_score != null ? round1(r.avg_score - prev.avg_score) : null
                      return (
                        <div key={r.batch_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 100px 100px 80px 80px 80px' }}>
                          <span style={{ fontWeight: 600, fontSize: 13 }}>{r.batch_name}</span>
                          <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty || '—'}</span>
                          <span style={{ fontSize: 12, color: '#6b7280' }}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</span>
                          <span>{r.chart_count ?? r.charts ?? '—'}</span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                            <span style={{ fontWeight: 700, color: (r.avg_score ?? 0) >= 80 ? '#16a34a' : (r.avg_score ?? 0) >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score != null ? `${r.avg_score}%` : '—'}</span>
                            {delta != null && <span style={{ fontSize: 11, fontWeight: 700, color: delta > 0 ? '#16a34a' : delta < 0 ? '#dc2626' : '#9ca3af' }}>{delta > 0 ? '↑' : delta < 0 ? '↓' : '→'}{Math.abs(delta)}%</span>}
                          </span>
                          <span style={{ fontWeight: 700, color: '#16a34a' }}>{r.charts_passed != null ? `${r.charts_passed}/${r.chart_count ?? r.charts ?? '?'}` : '—'}</span>
                        </div>
                      )
                    })}
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}

      {/* C: Category Mastery */}
      {tab === 'category' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!categoryData ? <div style={styles.emptyState}>Loading…</div> : categoryData.team.length === 0 ? (
            <div style={styles.emptyState}>No category data yet — grade some batches first.</div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Team Avg Score by Category</div>
                <ResponsiveContainer width="100%" height={Math.max(180, categoryData.team.length * 48)}>
                  <BarChart data={categoryData.team} layout="vertical" margin={{ left: 10, right: 40, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={140} />
                    <Tooltip formatter={(v: any) => [`${v}%`]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Bar dataKey="avg_score" name="Avg Score" radius={[0, 4, 4, 0]}>
                      {categoryData.team.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.avg_score >= 80 ? '#22c55e' : entry.avg_score >= 60 ? '#f59e0b' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {/* Clickable category rows with drill-through */}
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 70px 80px 80px' }}>
                  <span>Category</span><span>Attempts</span><span>Avg Score</span><span>Pass Rate</span>
                </div>
                {categoryData.team.map((cat: any, i: number) => {
                  const isExp = expandedCategory === cat.category
                  const catCharts = byChart.filter((c: any) => c.category === cat.category).sort((a: any, b: any) => a.avg_score - b.avg_score)
                  const catCoders = categoryData.coder_category.filter((r: any) => r.category === cat.category).sort((a: any, b: any) => a.avg_score - b.avg_score)
                  return (
                    <div key={cat.category}>
                      <div className={!isExp ? (i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr') : ''} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 70px 80px 80px', cursor: 'pointer', background: isExp ? '#f5f3ff' : undefined }}
                        onClick={() => setExpandedCategory(isExp ? null : cat.category)}>
                        <span style={{ fontWeight: 600 }}>{cat.category} <span style={{ fontSize: 11, color: '#9ca3af' }}>{isExp ? '▲' : '▼'}</span></span>
                        <span>{cat.attempt_count}</span>
                        <span style={{ fontWeight: 700, color: cat.avg_score >= 80 ? '#16a34a' : cat.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{cat.avg_score}%</span>
                        <span style={{ fontWeight: 700, color: cat.pass_rate >= 80 ? '#16a34a' : cat.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{cat.pass_rate}%</span>
                      </div>
                      {isExp && (
                        <div style={{ padding: '12px 16px', background: '#fafafa', borderBottom: '1px solid #ede9fe', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 8 }}>Weak charts in this category</div>
                            {catCharts.length === 0 ? <div style={{ fontSize: 12, color: '#9ca3af' }}>No chart data yet</div> : catCharts.slice(0, 6).map((c: any) => (
                              <div key={c.chart_number} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                                <span style={{ fontWeight: 700, color: '#4f46e5', cursor: 'pointer' }} onClick={e => { e.stopPropagation(); setExpandedChart(c.chart_number); setTab('chart') }}>{c.chart_number}</span>
                                <span style={{ color: '#6b7280' }}>{c.attempt_count} attempts</span>
                                <span style={{ fontWeight: 700, color: c.avg_score >= 80 ? '#16a34a' : c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</span>
                              </div>
                            ))}
                          </div>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 8 }}>Coders by performance</div>
                            {catCoders.length === 0 ? <div style={{ fontSize: 12, color: '#9ca3af' }}>No coder data yet</div> : (
                              <>
                                {catCoders.slice(0, 10).map((c: any) => (
                                  <div key={c.coder_name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                                    {coderLink(c.coder_name)}
                                    <span style={{ color: '#6b7280' }}>{c.attempt_count} charts</span>
                                    <span style={{ fontWeight: 700, color: c.avg_score >= 80 ? '#16a34a' : c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</span>
                                  </div>
                                ))}
                                {catCoders.length > 10 && (
                                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                                    + {catCoders.length - 10} more coders — use Coder Matrix for full view
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {categoryData.coder_category.length > 0 && (() => {
                const allCoders = Array.from(new Set(categoryData.coder_category.map((r: any) => r.coder_name))) as string[]
                const cats = categoryData.team.map((r: any) => r.category)
                const cellMap: Record<string, Record<string, any>> = {}
                categoryData.coder_category.forEach((r: any) => {
                  if (!cellMap[r.coder_name]) cellMap[r.coder_name] = {}
                  cellMap[r.coder_name][r.category] = r
                })
                const filteredCoders = heatmapCoderSearch.trim()
                  ? allCoders.filter(n => n.toLowerCase().includes(heatmapCoderSearch.toLowerCase()))
                  : allCoders
                const sortedCoders = [...filteredCoders].sort((a, b) => {
                  const dir = heatmapSort.dir === 'asc' ? 1 : -1
                  if (heatmapSort.col === 'coder') return a.localeCompare(b) * dir
                  const sa = cellMap[a]?.[heatmapSort.col]?.avg_score ?? -1
                  const sb = cellMap[b]?.[heatmapSort.col]?.avg_score ?? -1
                  return (sa - sb) * dir
                })
                const visibleCoders = heatmapShowAll ? sortedCoders : sortedCoders.slice(0, CODER_PAGE)
                const hiddenCount = sortedCoders.length - visibleCoders.length
                return (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap' as const, gap: 8 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>Coder × Category Heatmap</div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {allCoders.length > CODER_PAGE && (
                          <input
                            placeholder={`Search coders (${allCoders.length} total)…`}
                            value={heatmapCoderSearch}
                            onChange={e => { setHeatmapCoderSearch(e.target.value); setHeatmapShowAll(false) }}
                            style={{ padding: '5px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, width: 200 }}
                          />
                        )}
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>Showing {visibleCoders.length} of {filteredCoders.length}</span>
                      </div>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                        <thead>
                          <tr>
                            <th onClick={() => toggleSort('coder', heatmapSort, setHeatmapSort)} style={{ textAlign: 'left', padding: '6px 10px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' as const, cursor: 'pointer', userSelect: 'none' as const }}>
                              Coder{sortIcon('coder', heatmapSort)}
                            </th>
                            {cats.map((c: string) => (
                              <th key={c} onClick={() => toggleSort(c, heatmapSort, setHeatmapSort)} style={{ padding: '6px 8px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' as const, textAlign: 'center', fontWeight: 600, cursor: 'pointer', userSelect: 'none' as const }}>
                                {c}{sortIcon(c, heatmapSort)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {visibleCoders.map((coder: string, i: number) => (
                            <tr key={coder} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                              <td style={{ padding: '6px 10px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const }}>{coderLink(coder)}</td>
                              {cats.map((cat: string) => {
                                const cell = cellMap[coder]?.[cat]
                                const score = cell?.avg_score
                                const bg = score == null ? 'transparent' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                                const color = score == null ? '#d1d5db' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
                                return (
                                  <td key={cat} style={{ padding: '6px 8px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                    {score != null ? `${score}%` : '—'}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {hiddenCount > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 }}>
                        <span style={{ fontSize: 12, color: '#6b7280' }}>{hiddenCount} more coder{hiddenCount !== 1 ? 's' : ''} not shown</span>
                        <button onClick={() => setHeatmapShowAll(true)} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                          Show all {filteredCoders.length}
                        </button>
                      </div>
                    )}
                    {heatmapShowAll && allCoders.length > CODER_PAGE && (
                      <button onClick={() => setHeatmapShowAll(false)} style={{ marginTop: 8, fontSize: 12, color: '#6b7280', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer' }}>
                        Collapse to {CODER_PAGE}
                      </button>
                    )}
                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>Green ≥80% · Yellow 60–79% · Red &lt;60% · — no data</div>
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}

      {/* D: Chart Teaching Value */}
      {tab === 'teaching' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {teachingData.length === 0 ? <div style={styles.emptyState}>No chart grading data yet.</div> : (() => {
            const labels = Object.keys(TEACHING_LABEL_META)
            const filterOptions = ['All', ...labels]
            const filtered = (teachingFilter === 'All' ? teachingData : teachingData.filter((c: any) => c.teaching_label === teachingFilter))
              .slice()
              .sort((a: any, b: any) => {
                if (chartValueSort === 'score_asc') return a.avg_score - b.avg_score
                if (chartValueSort === 'score_desc') return b.avg_score - a.avg_score
                return b.attempt_count - a.attempt_count  // attempts_desc
              })
            const grouped: Record<string, any[]> = {}
            teachingData.forEach((c: any) => {
              if (!grouped[c.teaching_label]) grouped[c.teaching_label] = []
              grouped[c.teaching_label].push(c)
            })
            const summaryData = labels.map(l => ({ label: l, count: grouped[l]?.length || 0 })).filter(d => d.count > 0)
            return (
              <>
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Chart Teaching Value Distribution</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={summaryData} margin={{ left: 10, right: 20, top: 4, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                      <Bar dataKey="count" name="Charts" radius={[4, 4, 0, 0]}>
                        {summaryData.map((entry: any, i: number) => <Cell key={i} fill={TEACHING_LABEL_META[entry.label]?.color || '#6b7280'} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {filterOptions.map(opt => (
                    <button key={opt} onClick={() => { setTeachingFilter(opt); setChartValueShowAll(false) }}
                      style={{ padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        background: teachingFilter === opt ? '#4f46e5' : '#f3f4f6',
                        color: teachingFilter === opt ? '#fff' : '#374151',
                        border: teachingFilter === opt ? '1px solid #4f46e5' : '1px solid #e5e7eb' }}>
                      {opt}{opt !== 'All' && grouped[opt] ? ` (${grouped[opt].length})` : ''}
                    </button>
                  ))}
                </div>
                {filtered.length === 0 ? (
                  <div style={styles.emptyState}>No charts in this category.</div>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4, flexWrap: 'wrap' as const, gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 12, color: '#9ca3af' }}>
                          Showing {Math.min(chartValueShowAll ? filtered.length : CHART_VALUE_PAGE, filtered.length)} of {filtered.length} charts
                        </span>
                        {[
                          { key: 'score_asc', label: 'Most problematic first' },
                          { key: 'attempts_desc', label: 'Most attempted' },
                          { key: 'score_desc', label: 'Highest scoring' },
                        ].map(opt => (
                          <button key={opt.key} onClick={() => { setChartValueSort(opt.key as any); setChartValueShowAll(false) }}
                            style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, cursor: 'pointer', fontWeight: 600, border: '1px solid',
                              background: chartValueSort === opt.key ? '#4f46e5' : '#fff',
                              color: chartValueSort === opt.key ? '#fff' : '#6b7280',
                              borderColor: chartValueSort === opt.key ? '#4f46e5' : '#e5e7eb' }}>
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      {filtered.length > CHART_VALUE_PAGE && (
                        <button onClick={() => setChartValueShowAll(v => !v)} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                          {chartValueShowAll ? `Collapse to ${CHART_VALUE_PAGE}` : `Show all ${filtered.length}`}
                        </button>
                      )}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
                      {(chartValueShowAll ? filtered : filtered.slice(0, CHART_VALUE_PAGE)).map((c: any, i: number) => {
                        const meta = TEACHING_LABEL_META[c.teaching_label] || { color: '#374151', bg: '#f9fafb', desc: '' }
                        return (
                          <div key={i} style={{ background: meta.bg, border: `1px solid ${meta.color}30`, borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                              <span style={{ fontWeight: 700, fontSize: 13, color: '#111' }}>{c.chart_number}</span>
                              <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: '#fff', border: `1px solid ${meta.color}40`, borderRadius: 10, padding: '2px 8px' }}>{c.teaching_label}</span>
                            </div>
                            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{c.specialty} · {c.category}</div>
                            <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
                              <span><b style={{ color: '#111' }}>{c.attempt_count}</b> attempts</span>
                              <span><b style={{ color: c.avg_score >= 80 ? '#16a34a' : c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</b> avg</span>
                              <span><b style={{ color: c.pass_rate >= 80 ? '#16a34a' : c.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{c.pass_rate}%</b> pass</span>
                            </div>
                            {c.error_variety > 0 && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{c.error_variety} distinct error type{c.error_variety > 1 ? 's' : ''}</div>}
                          </div>
                        )
                      })}
                    </div>
                  </>
                )}
              </>
            )
          })()}
        </div>
      )}

      {/* E: Coder Matrix */}
      {tab === 'matrix' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!matrixData ? <div style={styles.emptyState}>Loading…</div> : matrixData.coders.length === 0 ? (
            <div style={styles.emptyState}>No closed batch results yet — close a batch to see the coder matrix.</div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' as const, gap: 8 }}>
                <div style={{ fontSize: 13, color: '#6b7280' }}>
                  Cross-batch performance grid — each cell shows the coder's avg score for that batch. Only closed batches are shown.
                </div>
                {matrixData.coders.length > CODER_PAGE && (
                  <input
                    placeholder={`Search coders (${matrixData.coders.length} total)…`}
                    value={matrixCoderSearch}
                    onChange={e => { setMatrixCoderSearch(e.target.value); setMatrixShowAll(false) }}
                    style={{ padding: '5px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, width: 220 }}
                  />
                )}
              </div>
              {(() => {
                const filteredCoders = matrixCoderSearch.trim()
                  ? matrixData.coders.filter((n: string) => n.toLowerCase().includes(matrixCoderSearch.toLowerCase()))
                  : matrixData.coders
                const weightedOverall = new Map<string, number>()
                for (const coder of filteredCoders) {
                  const cells = matrixData.cells.filter((c: any) => c.coder_name === coder && c.avg_score != null)
                  const totalCharts = cells.reduce((s: number, c: any) => s + c.chart_count, 0)
                  const scoreSum = cells.reduce((s: number, c: any) => s + c.score_sum, 0)
                  weightedOverall.set(coder, totalCharts > 0 ? scoreSum / totalCharts : -1)
                }
                const sortedMatrixCoders = [...filteredCoders].sort((a: string, b: string) => {
                  const dir = matrixSort.dir === 'asc' ? 1 : -1
                  if (matrixSort.col === 'coder') return a.localeCompare(b) * dir
                  if (matrixSort.col === 'overall') {
                    return ((weightedOverall.get(a) ?? -1) - (weightedOverall.get(b) ?? -1)) * dir
                  }
                  const batchId = Number(matrixSort.col)
                  const sa = matrixData.cells.find((c: any) => c.coder_name === a && c.batch_id === batchId)?.avg_score ?? -1
                  const sb = matrixData.cells.find((c: any) => c.coder_name === b && c.batch_id === batchId)?.avg_score ?? -1
                  return (sa - sb) * dir
                })
                const visibleCoders = matrixShowAll ? sortedMatrixCoders : sortedMatrixCoders.slice(0, CODER_PAGE)
                const hiddenCount = sortedMatrixCoders.length - visibleCoders.length
                return (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 12, color: '#9ca3af' }}>Showing {visibleCoders.length} of {filteredCoders.length} coders</span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                        <thead>
                          <tr>
                            <th onClick={() => toggleSort('coder', matrixSort, setMatrixSort)} style={{ textAlign: 'left', padding: '7px 12px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' as const, fontWeight: 700, color: '#374151', cursor: 'pointer', userSelect: 'none' as const }}>
                              Coder{sortIcon('coder', matrixSort)}
                            </th>
                            {matrixData.batches.map((b: any) => (
                              <th key={b.id} onClick={() => toggleSort(String(b.id), matrixSort, setMatrixSort)} style={{ padding: '7px 10px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' as const, textAlign: 'center', fontWeight: 600, color: '#374151', minWidth: 80, cursor: 'pointer', userSelect: 'none' as const }}>
                                <div>{b.name.length > 14 ? b.name.slice(0, 14) + '…' : b.name}</div>
                                <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af' }}>{b.closed_at ? new Date(b.closed_at).toLocaleDateString() : ''}{sortIcon(String(b.id), matrixSort)}</div>
                              </th>
                            ))}
                            <th onClick={() => toggleSort('overall', matrixSort, setMatrixSort)} style={{ padding: '7px 10px', background: '#f1f5f9', borderBottom: '2px solid #e5e7eb', textAlign: 'center', fontWeight: 700, color: '#374151', minWidth: 70, cursor: 'pointer', userSelect: 'none' as const }}>
                              Overall{sortIcon('overall', matrixSort)}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleCoders.map((coder: string, i: number) => {
                            const coderCells = matrixData.cells.filter((c: any) => c.coder_name === coder)
                            const scoredCells = coderCells.filter((c: any) => c.avg_score != null)
                            const totalCharts = scoredCells.reduce((s: number, c: any) => s + c.chart_count, 0)
                            const scoreSum = scoredCells.reduce((s: number, c: any) => s + c.score_sum, 0)
                            const overall = totalCharts > 0 ? Math.round(scoreSum / totalCharts) : null
                            const cellMap: Record<number, any> = {}
                            coderCells.forEach((c: any) => { cellMap[c.batch_id] = c })
                            return (
                              <tr key={coder} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                                <td style={{ padding: '7px 12px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const }}>{coderLink(coder)}</td>
                                {matrixData.batches.map((b: any) => {
                                  const cell = cellMap[b.id]
                                  const score = cell?.avg_score
                                  const bg = score == null ? 'transparent' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                                  const color = score == null ? '#d1d5db' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
                                  return (
                                    <td key={b.id} style={{ padding: '7px 10px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                      {score != null ? (
                                        <div>
                                          <div>{score}%</div>
                                          {cell?.chart_count != null && <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>{cell.chart_count} charts</div>}
                                        </div>
                                      ) : '—'}
                                    </td>
                                  )
                                })}
                                <td style={{ padding: '7px 10px', textAlign: 'center', background: overall == null ? 'transparent' : overall >= 80 ? '#bbf7d0' : overall >= 60 ? '#fde68a' : '#fecaca', color: overall == null ? '#d1d5db' : overall >= 80 ? '#14532d' : overall >= 60 ? '#78350f' : '#7f1d1d', fontWeight: 800, borderBottom: '1px solid #f3f4f6', borderLeft: '2px solid #e5e7eb' }}>
                                  {overall != null ? `${overall}%` : '—'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    {hiddenCount > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 12, color: '#6b7280' }}>{hiddenCount} more coder{hiddenCount !== 1 ? 's' : ''} not shown</span>
                        <button onClick={() => setMatrixShowAll(true)} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                          Show all {filteredCoders.length}
                        </button>
                      </div>
                    )}
                    {matrixShowAll && matrixData.coders.length > CODER_PAGE && (
                      <button onClick={() => setMatrixShowAll(false)} style={{ fontSize: 12, color: '#6b7280', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer' }}>
                        Collapse to {CODER_PAGE}
                      </button>
                    )}
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>Green ≥80% · Yellow 60–79% · Red &lt;60%</div>
                  </>
                )
              })()}
            </>
          )}
        </div>
      )}
    </div>
  )
}
