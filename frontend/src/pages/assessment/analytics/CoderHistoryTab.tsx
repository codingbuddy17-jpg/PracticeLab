import { useState } from 'react'
import { Loader, FileDown } from 'lucide-react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts'
import { getAssessmentAnalyticsCoder, downloadAssessmentCoderReport } from '../../../api'
import { rateColor, DEFAULT_PASS, scoreColor, fmt, fmtTime, Panel, PassBadge, DiffBadge, LoadingSpinner, EmptyState, inputStyle, searchBtnStyle } from './helpers'

export function CoderHistoryTab() {
  const [coderName, setCoderName] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  function handleSearch() {
    if (!coderName.trim()) { toast.error('Please enter a coder name'); return }
    setLoading(true)
    setData(null)
    setSearched(true)
    getAssessmentAnalyticsCoder(coderName.trim(), employeeId.trim() || undefined, dateFrom || undefined, dateTo || undefined)
      .then(setData)
      .catch(() => toast.error('Failed to load coder history'))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <input style={inputStyle} placeholder="Coder name (required)" value={coderName} onChange={(e) => setCoderName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} />
          <input style={{ ...inputStyle, maxWidth: 180 }} placeholder="Employee ID (optional)" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>From</span>
            <input type="date" style={{ ...inputStyle, maxWidth: 150, cursor: 'pointer' }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>To</span>
            <input type="date" style={{ ...inputStyle, maxWidth: 150, cursor: 'pointer' }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
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
  // The download is a fetch now, so a failure is a message rather than a blank
  // tab showing raw JSON.
  const [downloadError, setDownloadError] = useState('')
  const [downloading, setDownloading] = useState(false)

  function toggleExclude(id: number) {
    setExcludedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleDownloadPdf() {
    setDownloadError('')
    setDownloading(true)
    try {
      await downloadAssessmentCoderReport(data.coder_name, data.employee_id || undefined, undefined, undefined, excludedIds.size > 0 ? Array.from(excludedIds) : undefined)
    } catch (e: any) {
      setDownloadError(e.message || 'Could not download the report.')
    } finally {
      setDownloading(false)
    }
  }

  const includedCount = allSessionIds.length - excludedIds.size

  return (
    <div>
      <Panel>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 20, fontWeight: 800 }}>
              {data.coder_name.charAt(0).toUpperCase()}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: '#111' }}>{data.coder_name}</div>
              {data.employee_id && <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>ID: {data.employee_id}</div>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: scoreColor(data.avg_score, data.default_pass_threshold) }}>{fmt(data.avg_score)}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Avg Score</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: rateColor(data.pass_rate) }}>{fmt(data.pass_rate)}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Pass Rate</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: '#111' }}>{data.total_assessments_taken}</div>
              <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Assessments</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
              <button onClick={handleDownloadPdf} disabled={includedCount === 0 || downloading}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 10, background: includedCount === 0 ? '#e5e7eb' : 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: includedCount === 0 ? '#9ca3af' : '#fff', border: 'none', cursor: includedCount === 0 ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 700 }}>
                <FileDown size={13} />
                {downloading ? 'Preparing…' : excludedIds.size > 0 ? `PDF (${includedCount} assessments)` : 'Download PDF Report'}
              </button>
              {downloadError && (
                <div style={{ fontSize: 11, color: '#b91c1c', fontWeight: 600, maxWidth: 260, textAlign: 'right' }}>{downloadError}</div>
              )}
              {allSessionIds.length > 1 && (
                <button onClick={() => setShowFilter(v => !v)}
                  style={{ fontSize: 11, color: '#7c3aed', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, textDecoration: 'underline', padding: 0 }}>
                  {showFilter ? 'Hide' : 'Select'} assessments for PDF
                </button>
              )}
            </div>
          </div>
        </div>

        {showFilter && allSessionIds.length > 1 && (
          <div style={{ marginTop: 14, padding: '12px 16px', background: 'rgba(124,58,237,0.05)', borderRadius: 10, border: '1px solid rgba(124,58,237,0.15)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#7c3aed', marginBottom: 10 }}>Include in PDF report — uncheck to exclude:</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(data.session_history as any[]).map((sh: any) => (
                <label key={sh.session_id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={!excludedIds.has(sh.session_id)} onChange={() => toggleExclude(sh.session_id)} style={{ accentColor: '#7c3aed', width: 15, height: 15 }} />
                  <span style={{ fontWeight: 600, color: '#111' }}>{sh.assessment_name}</span>
                  <span style={{ color: '#6b7280', fontSize: 11 }}>{sh.submitted_at ? new Date(sh.submitted_at).toLocaleDateString() : ''}</span>
                  <span style={{ color: scoreColor(sh.score_pct, sh.pass_threshold), fontWeight: 700, fontSize: 12 }}>{fmt(sh.score_pct)}</span>
                  <PassBadge pf={sh.pass_fail} />
                </label>
              ))}
            </div>
            {excludedIds.size > 0 && (
              <button onClick={() => setExcludedIds(new Set())} style={{ marginTop: 8, fontSize: 11, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>
                Reset (include all)
              </button>
            )}
          </div>
        )}

        <div style={{ display: 'flex', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13, color: '#374151' }}>Best: <strong style={{ color: '#16a34a' }}>{fmt(data.best_score)}</strong></div>
          <div style={{ fontSize: 13, color: '#374151' }}>Worst: <strong style={{ color: scoreColor(data.worst_score, data.default_pass_threshold) }}>{fmt(data.worst_score)}</strong></div>
          {data.avg_time_seconds && <div style={{ fontSize: 13, color: '#374151' }}>Avg Time: <strong>{fmtTime(data.avg_time_seconds)}</strong></div>}
        </div>
      </Panel>

      {data.score_trend && data.score_trend.length > 1 && (
        <Panel title="Score Trend Over Time">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.score_trend} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="submitted_at" tick={{ fontSize: 10 }} tickFormatter={(v) => new Date(v).toLocaleDateString()} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip labelFormatter={(v) => new Date(v as string).toLocaleDateString()} formatter={(v: any) => [`${v}%`, 'Score']} />
              <ReferenceLine y={data.default_pass_threshold ?? DEFAULT_PASS} stroke="#dc2626" strokeDasharray="4 4" label={{ value: data.pass_thresholds_vary ? 'typical pass line' : `${data.default_pass_threshold ?? DEFAULT_PASS}% pass line`, fill: '#dc2626', fontSize: 11 }} />
              <Line type="monotone" dataKey="score_pct" stroke="#7c3aed" strokeWidth={2.5} dot={{ r: 4, fill: '#7c3aed' }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      )}

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
                    <td style={{ padding: '9px 12px', color: '#6b7280', fontSize: 12 }}>{sh.submitted_at ? new Date(sh.submitted_at).toLocaleDateString() : '—'}</td>
                    <td style={{ padding: '9px 12px', fontWeight: 800, color: scoreColor(sh.score_pct, sh.pass_threshold) }}>{fmt(sh.score_pct)}</td>
                    <td style={{ padding: '9px 12px', color: '#374151' }}>{sh.correct_count}/{sh.total_questions}</td>
                    <td style={{ padding: '9px 12px', color: '#6b7280' }}>{fmtTime(sh.time_taken_seconds)}</td>
                    <td style={{ padding: '9px 12px' }}><PassBadge pf={sh.pass_fail} /></td>
                    <td style={{ padding: '9px 12px' }}>
                      {sh.auto_submitted && <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 20, fontWeight: 700 }}>Auto</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {data.topic_strength && data.topic_strength.length > 0 && (
          <Panel title="Topic Strength / Weakness">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(data.topic_strength as any[]).map((t: any, i: number) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ fontWeight: 600, color: '#374151' }}>{t.topic}</span>
                    <span style={{ color: scoreColor(t.accuracy_pct), fontWeight: 700 }}>{t.accuracy_pct != null ? `${t.accuracy_pct}%` : '—'}</span>
                  </div>
                  <div style={{ height: 7, background: '#f3f4f6', borderRadius: 4 }}>
                    {t.accuracy_pct != null && <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(t.accuracy_pct, 100)}%`, background: scoreColor(t.accuracy_pct), transition: 'width 0.5s' }} />}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {data.difficulty_breakdown && (
          <Panel title="Difficulty Breakdown">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(data.difficulty_breakdown as any[]).map((d: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(249,250,251,0.8)', borderRadius: 10, padding: '12px 16px', border: '1px solid #f3f4f6' }}>
                  <DiffBadge diff={d.difficulty} />
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor(d.accuracy_pct) }}>{d.accuracy_pct != null ? `${d.accuracy_pct}%` : '—'}</div>
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
