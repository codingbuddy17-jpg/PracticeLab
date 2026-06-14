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

      {showInsights && insights?.has_data && <InsightsPanel insights={insights} onClose={() => setShowInsights(false)} />}

      <div style={styles.statsRow}>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.total_coders}</div><div style={styles.statLabel}>Coders</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#16a34a' }}>{bs.passed}</div><div style={styles.statLabel}>Passed</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#dc2626' }}>{bs.failed}</div><div style={styles.statLabel}>Failed</div></div>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.pass_rate}%</div><div style={styles.statLabel}>Coder Pass Rate</div></div>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.avg_score}%</div><div style={styles.statLabel}>Avg Score</div></div>
      </div>

      {bs.top_missed_codes?.length > 0 && (
        <div style={{ ...styles.infoBox, marginBottom: 20 }}>
          <strong>Top missed codes:</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {bs.top_missed_codes.map((m: any) => (
              <span key={m.code} style={{ ...styles.badge, background: '#fee2e2', color: '#dc2626' }}>
                {m.code} <span style={{ opacity: 0.7 }}>({m.count}×)</span>
              </span>
            ))}
          </div>
        </div>
      )}

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

              {/* Expanded: DPO panel + per-chart rows */}
              {isOpen && (
                <div style={styles.chartDetail}>
                  {use_dpo && c.dpo_overall_accuracy != null && (
                    <div style={styles.dpoPanel}>
                      <div style={styles.dpoPanelTitle}>
                        <span style={styles.dpoSupBadge}>DPO Supplementary</span>
                        Coding Accuracy Breakdown
                      </div>
                      <div style={styles.dpoPanelRow}>
                        <AccBadge val={c.dpo_dx_accuracy} label="Dx Accuracy" />
                        {is_ip && <AccBadge val={c.dpo_poa_accuracy} label="POA Accuracy" />}
                        <AccBadge val={c.dpo_proc_accuracy} label={is_ip ? 'PCS Accuracy' : 'CPT Accuracy'} />
                        <div style={styles.dpoDivider} />
                        <AccBadge val={c.dpo_overall_accuracy} label="Overall Accuracy" />
                      </div>
                    </div>
                  )}

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
