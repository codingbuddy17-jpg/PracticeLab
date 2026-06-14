import { useState, useEffect } from 'react'
import { Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell,
} from 'recharts'
import {
  getPLAnalyticsOverview, getPLAnalyticsBySpecialty, getPLAnalyticsByChart,
  getPLAnalyticsByBatch, getCoderTrend,
  getPLAnalyticsByCategory, getPLChartTeachingValue, getPLCoderMatrix,
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
  const [categoryData, setCategoryData] = useState<{ team: any[]; coder_category: any[] } | null>(null)
  const [teachingData, setTeachingData] = useState<any[]>([])
  const [matrixData, setMatrixData] = useState<{ batches: any[]; coders: string[]; cells: any[] } | null>(null)
  const [teachingFilter, setTeachingFilter] = useState<string>('All')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getPLAnalyticsOverview(),
      getPLAnalyticsBySpecialty(),
      getPLAnalyticsByBatch(),
    ]).then(([ov, sp, bt]) => {
      setOverview(ov); setBySpecialty(sp); setByBatch(bt)
    }).catch(() => toast.error('Failed to load analytics')).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (tab === 'chart' && byChart.length === 0) getPLAnalyticsByChart().then(setByChart).catch(() => {})
    if (tab === 'category' && !categoryData) getPLAnalyticsByCategory().then(setCategoryData).catch(() => {})
    if (tab === 'teaching' && teachingData.length === 0) getPLChartTeachingValue().then(setTeachingData).catch(() => {})
    if (tab === 'matrix' && !matrixData) getPLCoderMatrix().then(setMatrixData).catch(() => {})
  }, [tab])

  async function loadCoderTrend() {
    if (!coderName.trim()) return
    const data = await getCoderTrend(coderName.trim()).catch(() => null)
    if (data) setCoderTrend(data)
    else toast.error('No data for this coder')
  }

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
                {bySpecialty.map((r: any) => (
                  <div key={r.specialty} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
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
              <div style={{ ...styles.tableHeader, gridTemplateColumns: '120px 1fr 1fr 80px 80px' }}>
                <span>Chart</span><span>Category</span><span>Specialty</span><span>Attempts</span><span>Avg Score</span>
              </div>
              {byChart.map((r: any) => (
                <div key={r.chart_number} style={{ ...styles.tableRow, gridTemplateColumns: '120px 1fr 1fr 80px 80px', flexDirection: 'column' as const, height: 'auto', alignItems: 'stretch', padding: 0 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 80px 80px', padding: '10px 16px', alignItems: 'center' }}>
                    <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                    <span style={{ fontSize: 12 }}>{r.category}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span>{r.attempt_count}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                  </div>
                  {r.top_missed?.length > 0 && (
                    <div style={{ padding: '4px 16px 8px 132px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {r.top_missed.map(([code, cnt]: any) => (
                        <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '1px 8px', borderRadius: 10 }}>{code} {cnt}×</span>
                      ))}
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
                {byBatch.map((r: any) => (
                  <div key={r.batch_id} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 100px 80px 80px 80px' }}>
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
            <input style={{ ...styles.input, width: 260 }} placeholder="Enter coder name exactly"
              value={coderName} onChange={e => setCoderName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadCoderTrend()} />
            <button style={styles.primaryBtn} onClick={loadCoderTrend}>Look Up</button>
          </div>
          {coderTrend.length === 0 ? (
            <div style={styles.emptyState}>Enter the coder's exact name (as used in batch creation) and press Look Up to see their score trend across batches.</div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Score Trend — {coderName}</div>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={coderTrend.map(r => ({ ...r, label: r.batch_name.length > 14 ? r.batch_name.slice(0, 14) + '…' : r.batch_name }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => [`${v}%`, 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 6, fill: '#4f46e5' }} activeDot={{ r: 8 }} name="Avg Score" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 120px 80px 80px' }}>
                  <span>Batch</span><span>Date</span><span>Charts</span><span>Avg Score</span>
                </div>
                {coderTrend.map((r: any, i: number) => {
                  const prev = coderTrend[i - 1]
                  const delta = prev ? round1(r.avg_score - prev.avg_score) : null
                  return (
                    <div key={r.batch_id} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 120px 80px 80px' }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{r.batch_name}</span>
                      <span style={{ fontSize: 12, color: '#6b7280' }}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</span>
                      <span>{r.chart_count}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                        {delta != null && <span style={{ fontSize: 11, fontWeight: 700, color: delta > 0 ? '#16a34a' : delta < 0 ? '#dc2626' : '#9ca3af' }}>{delta > 0 ? '↑' : delta < 0 ? '↓' : '→'}{Math.abs(delta)}%</span>}
                      </span>
                    </div>
                  )
                })}
              </div>
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
              {categoryData.coder_category.length > 0 && (() => {
                const coders = Array.from(new Set(categoryData.coder_category.map((r: any) => r.coder_name)))
                const cats = categoryData.team.map((r: any) => r.category)
                const cellMap: Record<string, Record<string, any>> = {}
                categoryData.coder_category.forEach((r: any) => {
                  if (!cellMap[r.coder_name]) cellMap[r.coder_name] = {}
                  cellMap[r.coder_name][r.category] = r
                })
                return (
                  <div style={{ overflowX: 'auto' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 10 }}>Coder × Category Heatmap</div>
                    <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: 'left', padding: '6px 10px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' }}>Coder</th>
                          {cats.map((c: string) => (
                            <th key={c} style={{ padding: '6px 8px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap', textAlign: 'center', fontWeight: 600 }}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {coders.map((coder: string) => (
                          <tr key={coder}>
                            <td style={{ padding: '6px 10px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' }}>{coder}</td>
                            {cats.map((cat: string) => {
                              const cell = cellMap[coder]?.[cat]
                              const score = cell?.avg_score
                              const bg = score == null ? '#f9fafb' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                              const color = score == null ? '#9ca3af' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
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
                    <div style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>Green ≥80% · Yellow 60–79% · Red &lt;60% · — no data</div>
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
            const filtered = teachingFilter === 'All' ? teachingData : teachingData.filter((c: any) => c.teaching_label === teachingFilter)
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
                    <button key={opt} onClick={() => setTeachingFilter(opt)}
                      style={{ padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        background: teachingFilter === opt ? '#4f46e5' : '#f3f4f6',
                        color: teachingFilter === opt ? '#fff' : '#374151',
                        border: teachingFilter === opt ? '1px solid #4f46e5' : '1px solid #e5e7eb' }}>
                      {opt}{opt !== 'All' && grouped[opt] ? ` (${grouped[opt].length})` : ''}
                    </button>
                  ))}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
                  {filtered.map((c: any, i: number) => {
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
                {filtered.length === 0 && <div style={styles.emptyState}>No charts in this category.</div>}
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
              <div style={{ fontSize: 13, color: '#6b7280' }}>
                Cross-batch performance grid — each cell shows the coder's avg score for that batch. Only closed batches are shown.
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '7px 12px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', fontWeight: 700, color: '#374151' }}>Coder</th>
                      {matrixData.batches.map((b: any) => (
                        <th key={b.id} style={{ padding: '7px 10px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', textAlign: 'center', fontWeight: 600, color: '#374151', minWidth: 80 }}>
                          <div>{b.name.length > 14 ? b.name.slice(0, 14) + '…' : b.name}</div>
                          <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af' }}>{b.closed_at ? new Date(b.closed_at).toLocaleDateString() : ''}</div>
                        </th>
                      ))}
                      <th style={{ padding: '7px 10px', background: '#f1f5f9', borderBottom: '2px solid #e5e7eb', textAlign: 'center', fontWeight: 700, color: '#374151', minWidth: 70 }}>Overall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matrixData.coders.map((coder: string) => {
                      const coderCells = matrixData.cells.filter((c: any) => c.coder_name === coder)
                      const allScores = coderCells.filter((c: any) => c.avg_score != null).map((c: any) => c.avg_score)
                      const overall = allScores.length ? Math.round(allScores.reduce((a: number, b: number) => a + b, 0) / allScores.length) : null
                      const cellMap: Record<number, any> = {}
                      coderCells.forEach((c: any) => { cellMap[c.batch_id] = c })
                      return (
                        <tr key={coder}>
                          <td style={{ padding: '7px 12px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap', color: '#111' }}>{coder}</td>
                          {matrixData.batches.map((b: any) => {
                            const cell = cellMap[b.id]
                            const score = cell?.avg_score
                            const bg = score == null ? '#f9fafb' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                            const color = score == null ? '#9ca3af' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
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
                          <td style={{ padding: '7px 10px', textAlign: 'center', background: overall == null ? '#f9fafb' : overall >= 80 ? '#bbf7d0' : overall >= 60 ? '#fde68a' : '#fecaca', color: overall == null ? '#9ca3af' : overall >= 80 ? '#14532d' : overall >= 60 ? '#78350f' : '#7f1d1d', fontWeight: 800, borderBottom: '1px solid #f3f4f6', borderLeft: '2px solid #e5e7eb' }}>
                            {overall != null ? `${overall}%` : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: 11, color: '#6b7280' }}>Green ≥80% · Yellow 60–79% · Red &lt;60%</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
