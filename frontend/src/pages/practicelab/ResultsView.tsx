import { useState, useEffect } from 'react'
import { Loader, Download, Copy, Check } from 'lucide-react'
import toast from 'react-hot-toast'
import { getBatchResults, downloadBatchResultsExcel, getBatchInsights } from '../../api'
import { InsightsPanel } from './InsightsPanel'
import styles from './styles'

export function ResultsView({ batchId }: any) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
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

      <div style={styles.table}>
        <div style={{ ...styles.tableHeader, gridTemplateColumns: is_ip ? '2fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr' : '2fr 1fr 1fr 1fr 1fr 1fr' }}>
          <span>Coder</span><span>PDx</span><span>SDx</span>
          {is_ip && <><span>PCS</span><span>DRG</span></>}
          {!is_ip && <span>CPT</span>}
          <span>Total</span><span>Result</span>
        </div>
        {coder_summaries.map((c: any, i: number) => (
          <div key={c.coder_name}>
            <div className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, cursor: 'pointer', gridTemplateColumns: is_ip ? '2fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr' : '2fr 1fr 1fr 1fr 1fr 1fr' }}
              onClick={() => setExpanded(expanded === c.coder_name ? null : c.coder_name)}>
              <span style={{ fontWeight: 600 }}>{c.coder_name} {expanded === c.coder_name ? '▲' : '▼'}</span>
              <span>{c.avg_pdx}</span><span>{c.avg_sdx}</span>
              {is_ip && <><span>{c.avg_pcs}</span><span>{c.avg_drg}</span></>}
              {!is_ip && <span>{c.avg_cpt}</span>}
              <span style={{ fontWeight: 700 }}>{c.avg_total}%</span>
              <span style={{ fontWeight: 700, color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{c.pass_fail}</span>
            </div>
            {expanded === c.coder_name && (
              <div style={styles.chartDetail}>
                {use_dpo && (c.dpo_dx_accuracy != null || c.dpo_overall_accuracy != null) && (
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
                {c.charts.map((ch: any) => (
                  <div key={ch.chart_number} style={styles.chartDetailRow}>
                    <span style={{ fontWeight: 600, minWidth: 70 }}>{ch.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>
                      PDx:{ch.pdx_score} SDx:{ch.sdx_score}
                      {is_ip ? ` PCS:${ch.pcs_score} DRG:${ch.drg_score ?? '—'}` : ` CPT:${ch.cpt_score}`}
                    </span>
                    <span style={{ fontWeight: 700 }}>{ch.total_score ?? '—'}%</span>
                    <span style={{ color: ch.pass_fail === 'PASS' ? '#16a34a' : '#dc2626', fontWeight: 600 }}>{ch.pass_fail || '—'}</span>
                    {ch.feedback?.length > 0 && (
                      <div style={styles.fbList}>
                        {ch.feedback.map((f: any, i: number) => (
                          <div key={i} style={styles.fbRow}>
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
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
