import { useState, useEffect } from 'react'
import { Loader, Download, Copy, Check, ChevronDown, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
import { getBatchResults, downloadBatchResultsExcel, getBatchInsights } from '../../api'
import { InsightsPanel } from './InsightsPanel'
import styles from './styles'

export function ResultsView({ batchId }: any) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  const [insights, setInsights] = useState<any>(null)
  const [showInsights, setShowInsights] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    getBatchResults(batchId).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [batchId])

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!data) return <div style={styles.center}>No results yet</div>

  const { batch_summary: bs, coder_summaries, is_ip, use_dpo } = data

  function copySummary() {
    const lines = [
      `Batch: ${data.batch_name}`,
      `Coders: ${bs.total_coders}  Passed: ${bs.passed}  Failed: ${bs.failed}`,
      `Pass Rate: ${bs.pass_rate}%  Avg Score: ${bs.avg_score}%`,
    ]
    if (bs.top_missed_codes?.length) {
      lines.push(`Top Missed: ${bs.top_missed_codes.map((m: any) => `${m.code} (${m.count}×)`).join(', ')}`)
    }
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  function AccBadge({ val, label }: { val: number | null | undefined; label: string }) {
    if (val == null) return null
    const color = val >= 90 ? '#16a34a' : val >= 80 ? '#d97706' : '#dc2626'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 70 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color }}>{val}%</div>
        <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</div>
      </div>
    )
  }

  const scoreColor = (v: number) => v >= 90 ? '#16a34a' : v >= 80 ? '#d97706' : '#dc2626'

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <span style={styles.sectionTitle}>{data.batch_name} — Results</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...styles.outlineBtn, color: '#4f46e5', borderColor: '#a5b4fc' }}
            onClick={() => {
              if (insights) { setShowInsights(s => !s) }
              else { getBatchInsights(batchId).then(ins => { setInsights(ins); setShowInsights(true) }).catch(() => toast.error('Failed to load insights')) }
            }}>
            ✦ {showInsights ? 'Hide Insights' : 'View Insights'}
          </button>
          <button style={styles.outlineBtn} onClick={copySummary} title="Copy batch summary to clipboard">
            {copied ? <><Check size={15} /> Copied!</> : <><Copy size={15} /> Copy Summary</>}
          </button>
          <button style={styles.outlineBtn} title="Download per-coder scores, pass/fail, and feedback detail as Excel (.xlsx)"
            onClick={() => downloadBatchResultsExcel(batchId)}><Download size={15} /> Export Results (.xlsx)</button>
        </div>
      </div>

      {showInsights && insights?.has_data && <InsightsPanel insights={insights} batchId={batchId} onClose={() => setShowInsights(false)} />}

      <div style={styles.statsRow}>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.total_coders}</div><div style={styles.statLabel}>Coders</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#16a34a' }}>{bs.passed}</div><div style={styles.statLabel}>Passed</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#dc2626' }}>{bs.failed}</div><div style={styles.statLabel}>Failed</div></div>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.pass_rate}%</div><div style={styles.statLabel}>Coder Pass Rate</div></div>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.avg_score}%</div><div style={styles.statLabel}>Avg Score</div></div>
      </div>

      {/* Error breakdown panel */}
      {(bs.error_type_counts && Object.keys(bs.error_type_counts).length > 0) && (() => {
        const ERROR_META: Record<string, { label: string; bg: string; color: string }> = {
          'Missed':         { label: 'Missed Code',      bg: '#fee2e2', color: '#dc2626' },
          'Wrong_Code':     { label: 'Wrong Code',       bg: '#fef3c7', color: '#d97706' },
          'Wrong_POA':      { label: 'Wrong POA',        bg: '#fef9c3', color: '#a16207' },
          'Wrong_Modifier': { label: 'Wrong Modifier',   bg: '#ede9fe', color: '#7c3aed' },
          'Over_coded':     { label: 'Over-coded',       bg: '#dbeafe', color: '#2563eb' },
        }
        return (
          <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 10 }}>Error Breakdown — This Batch</div>
            <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8, marginBottom: bs.top_missed_codes?.length ? 12 : 0 }}>
              {Object.entries(bs.error_type_counts).sort((a, b) => (b[1] as number) - (a[1] as number)).map(([type, count]: [string, any]) => {
                const meta = ERROR_META[type] || { label: type, bg: '#f3f4f6', color: '#6b7280' }
                return (
                  <span key={type} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: meta.bg, color: meta.color, border: `1px solid ${meta.color}30`, borderRadius: 20, padding: '4px 12px', fontSize: 12, fontWeight: 700 }}>
                    {meta.label} <span style={{ fontWeight: 400, opacity: 0.8 }}>{count}×</span>
                  </span>
                )
              })}
            </div>
            {bs.top_missed_codes?.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 6 }}>Top missed codes</div>
                <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
                  {bs.top_missed_codes.map((m: any) => (
                    <span key={m.code} style={{ background: '#fee2e2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 700 }}>
                      {m.code} <span style={{ fontWeight: 400, opacity: 0.7 }}>({m.count}×)</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {/* Coder summary table */}
      <div style={styles.table}>
        <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 80px 120px 80px' }}>
          <span>Coder</span>
          <span style={{ textAlign: 'center' }}>Charts</span>
          <span style={{ textAlign: 'center' }}>Avg Accuracy</span>
          <span style={{ textAlign: 'center' }}>Result</span>
        </div>

        {coder_summaries.map((c: any, i: number) => {
          const isOpen = expanded === c.coder_name
          return (
            <div key={c.coder_name}>
              {/* Coder row */}
              <div
                className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                style={{ ...styles.tableRow, cursor: 'pointer', gridTemplateColumns: '2fr 80px 120px 80px', alignItems: 'center' }}
                onClick={() => { setExpanded(isOpen ? null : c.coder_name); setExpandedChart(null) }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
                  {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  {c.coder_name}
                </span>
                <span style={{ textAlign: 'center', color: '#374151' }}>{c.chart_count}</span>
                <span style={{ textAlign: 'center', fontWeight: 700, color: scoreColor(c.avg_total) }}>{c.avg_total}%</span>
                <span style={{ textAlign: 'center', fontWeight: 700, color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{c.pass_fail}</span>
              </div>

              {/* Expanded: cumulative panel + per-chart rows */}
              {isOpen && (
                <div style={styles.chartDetail}>
                  {/* Cumulative summary */}
                  <div style={{ background: '#f8faff', border: '1px solid #e0e7ff', borderRadius: 10, marginBottom: 12, overflow: 'hidden' }}>
                    {/* Header bar */}
                    <div style={{ background: '#ede9fe', padding: '7px 18px', display: 'flex', gap: 24 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' as const, letterSpacing: 0.7 }}>Cumulative — This Batch</span>
                      {use_dpo && c.cumulative_dpo && <span style={{ fontSize: 11, fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase' as const, letterSpacing: 0.7, marginLeft: 'auto' }}>DPO Accuracy</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'stretch' }}>
                      {/* Left: core stats */}
                      <div style={{ display: 'flex', gap: 0, flex: '0 0 auto' }}>
                        {[
                          { value: String(c.charts_scored ?? c.chart_count), label: 'Charts Graded', color: '#374151' },
                          { value: `${c.avg_total}%`, label: 'Weighted Accuracy', color: scoreColor(c.avg_total) },
                          { value: `${c.charts_passed ?? 0}/${c.charts_scored ?? c.chart_count}`, label: 'Charts Passed', color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' },
                        ].map((s, si) => (
                          <div key={si} style={{ textAlign: 'center' as const, padding: '16px 24px', borderRight: '1px solid #e0e7ff' }}>
                            <div style={{ fontSize: 26, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.5, marginTop: 5 }}>{s.label}</div>
                          </div>
                        ))}
                      </div>
                      {/* Right: DPO stats — same size font */}
                      {use_dpo && c.cumulative_dpo && (
                        <div style={{ display: 'flex', flex: 1, alignItems: 'center' }}>
                          {[
                            c.cumulative_dpo.dx_total > 0 ? { value: `${c.cumulative_dpo.dx_accuracy}%`, label: 'Dx', color: scoreColor(c.cumulative_dpo.dx_accuracy) } : null,
                            is_ip && c.cumulative_dpo.poa_total > 0 ? { value: `${c.cumulative_dpo.poa_accuracy}%`, label: 'POA', color: scoreColor(c.cumulative_dpo.poa_accuracy) } : null,
                            c.cumulative_dpo.proc_total > 0 ? { value: `${c.cumulative_dpo.proc_accuracy}%`, label: is_ip ? 'PCS' : 'CPT', color: scoreColor(c.cumulative_dpo.proc_accuracy) } : null,
                            c.cumulative_dpo.overall_accuracy != null ? { value: `${c.cumulative_dpo.overall_accuracy}%`, label: 'Overall DPO', color: scoreColor(c.cumulative_dpo.overall_accuracy), bold: true } : null,
                          ].filter(Boolean).map((s: any, si, arr) => (
                            <div key={si} style={{ textAlign: 'center' as const, padding: '16px 20px', flex: 1, borderRight: si < arr.length - 1 ? '1px solid #e0e7ff' : 'none', background: s.bold ? '#f5f3ff' : undefined }}>
                              <div style={{ fontSize: 26, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
                              <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.5, marginTop: 5 }}>{s.label}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Per-chart header */}
                  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr 100px 70px', gap: 8, padding: '6px 12px', fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 0.5, borderBottom: '1px solid #f0f0f0' }}>
                    <span>Chart</span>
                    <span>Category</span>
                    <span style={{ textAlign: 'center' }}>Accuracy</span>
                    <span style={{ textAlign: 'center' }}>Result</span>
                  </div>

                  {c.charts.map((ch: any, ci: number) => {
                    const chartKey = `${c.coder_name}:${ch.chart_number}`
                    const chartOpen = expandedChart === chartKey
                    return (
                      <div key={ch.chart_number}>
                        <div
                          className={ci % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                          style={{ display: 'grid', gridTemplateColumns: '100px 1fr 100px 70px', gap: 8, padding: '8px 12px', alignItems: 'center', cursor: ch.feedback?.length ? 'pointer' : 'default' }}
                          onClick={() => ch.feedback?.length && setExpandedChart(chartOpen ? null : chartKey)}
                        >
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600, fontSize: 13 }}>
                            {ch.feedback?.length > 0 && (chartOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
                            {ch.chart_number}
                          </span>
                          <span style={{ fontSize: 12, color: '#374151' }}>
                            {ch.category || '—'}
                            {ch.specialty && <span style={{ ...styles.badge, marginLeft: 6, fontSize: 10, padding: '1px 6px' }}>{ch.specialty}</span>}
                          </span>
                          <span style={{ textAlign: 'center', fontWeight: 700, fontSize: 13, color: ch.total_score != null ? scoreColor(ch.total_score) : '#9ca3af' }}>
                            {ch.total_score != null ? `${ch.total_score}%` : '—'}
                          </span>
                          <span style={{ textAlign: 'center', fontWeight: 700, fontSize: 12, color: ch.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>
                            {ch.pass_fail || '—'}
                          </span>
                        </div>

                        {/* Feedback detail */}
                        {chartOpen && ch.feedback?.length > 0 && (
                          <div style={{ ...styles.fbList, margin: '0 0 4px 24px' }}>
                            {ch.feedback.map((f: any, fi: number) => (
                              <div key={fi} style={styles.fbRow}>
                                <span style={styles.fbSection}>{f.section}</span>
                                <span style={styles.fbIssue}>{f.issue_type}</span>
                                {f.ak_code && <span style={{ fontSize: 11 }}>AK:{f.ak_code}</span>}
                                {f.coder_code && <span style={{ fontSize: 11 }}>Cdr:{f.coder_code}</span>}
                                {f.detail && <span style={{ fontSize: 11, color: '#6b7280' }}>{f.detail}</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
