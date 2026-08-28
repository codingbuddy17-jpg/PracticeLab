import { useState, useEffect, useCallback } from 'react'
import { Loader, Download, Copy, Check, ChevronDown, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
import { getBatchResults, downloadBatchResultsExcel, getBatchInsights, setBatchScoring } from '../../api'
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

  const reload = useCallback(() => {
    getBatchResults(batchId).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [batchId])

  useEffect(() => { reload() }, [reload])

  // DPO is computed for every chart whose specialty supports it, whatever the
  // batch says — the flag only decides whether the figures are shown, and it
  // could previously only be set while CREATING the batch. A trainer who meant
  // to enable it and did not had the numbers all along, behind a switch they
  // could no longer reach. Turning it on here reveals them; nothing is
  // re-graded, because there is nothing to re-grade.
  async function enableDpo() {
    try {
      await setBatchScoring(batchId, true, true)
      toast.success('Accuracy (DPO) shown — these figures were already recorded')
      reload()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not enable DPO for this batch')
    }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!data) return <div style={styles.center}>No results yet</div>

  const { batch_summary: bs, coder_summaries, is_ip, use_dpo, dpo_available } = data

  // The per-chart DPO column only earns its width when the batch is scored on
  // DPO and at least one chart actually carries a figure — a specialty that
  // does not compute it would otherwise get a column of dashes.
  const showChartDpo = !!use_dpo && (coder_summaries || []).some(
    (c: any) => (c.charts || []).some((ch: any) => ch.dpo_overall_accuracy != null))
  const chartCols = showChartDpo ? '100px 1fr 90px 110px 70px' : '100px 1fr 100px 70px'

  // The server answers this, because the payload masks the figures to null
  // when the flag is off — so the screen cannot tell from the data whether
  // there is anything to reveal.
  const dpoAvailable = !use_dpo && !!dpo_available

  function copySummary() {
    const lines = [
      `Batch: ${data.batch_name}`,
      `Coders: ${bs.total_coders}  Passed: ${bs.passed}  Failed: ${bs.failed}`,
      `Coder Pass Rate: ${bs.pass_rate}%  Avg Grading Score: ${bs.avg_score}%`,
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
  const gradingMetricStyle = {
    background: '#fffbeb',
    borderLeft: '3px solid #f59e0b',
  }
  const accuracyMetricStyle = {
    background: '#eef2ff',
    borderLeft: '3px solid #6366f1',
  }

  function pfBadge(pf: string | null | undefined) {
    if (!pf || pf === 'PENDING') return { label: pf || '—', color: '#6b7280', bg: '#f3f4f6' }
    if (pf === 'PASS') return { label: 'PASS', color: '#16a34a', bg: '#f0fdf4' }
    return { label: 'FAIL', color: '#dc2626', bg: '#fef2f2' }
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

      {/* The figures are already recorded; the batch is simply not showing
          them. Offering it here is the only place a trainer would look — the
          switch lived on the create form and could not be reached again, and
          the Scoring Config screen has a similarly named setting that governs
          the specialty defaults rather than this batch. */}
      {dpoAvailable && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
                      background: '#faf5ff', border: '1px solid #e9d5ff', borderRadius: 8,
                      padding: '10px 14px', marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#6b21a8' }}>
            Accuracy (DPO) was recorded for these charts but is not switched on for this batch.
          </span>
          <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '5px 12px',
                           borderColor: '#c084fc', color: '#7c3aed' }}
            onClick={enableDpo}>
            Show Accuracy (DPO)
          </button>
        </div>
      )}

      {showInsights && insights?.has_data && <InsightsPanel insights={insights} batchId={batchId} onClose={() => setShowInsights(false)} />}

      <div style={styles.statsRow}>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.total_coders}</div><div style={styles.statLabel}>Coders</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#16a34a' }}>{bs.passed}</div><div style={styles.statLabel}>Passed</div></div>
        <div style={styles.statCard}><div style={{ ...styles.statValue, color: '#dc2626' }}>{bs.failed}</div><div style={styles.statLabel}>Failed</div></div>
        <div style={styles.statCard}><div style={styles.statValue}>{bs.pass_rate}%</div><div style={styles.statLabel}>Coder Pass Rate</div></div>
        <div style={{ ...styles.statCard, background: '#fffbeb', borderLeft: '3px solid #f59e0b' }}><div style={styles.statValue}>{bs.avg_score}%</div><div style={styles.statLabel}>Avg Grading Score</div></div>
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
          <span style={{ textAlign: 'center' }}>Avg Grading Score</span>
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
                <span style={{ textAlign: 'center' }}>
                  {(() => { const b = pfBadge(c.pass_fail); return <span style={{ fontWeight: 700, color: b.color, background: b.bg, padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>{b.label}</span> })()}
                </span>
              </div>

              {/* Expanded: cumulative panel + per-chart rows */}
              {isOpen && (
                <div style={styles.chartDetail}>
                  {/* Cumulative summary */}
                  <div style={{ background: '#f8faff', border: '1px solid #e0e7ff', borderRadius: 10, marginBottom: 12, overflow: 'hidden' }}>
                    {/* Header bar */}
                    <div style={{ background: '#ede9fe', padding: '7px 18px', display: 'flex', gap: 24 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' as const, letterSpacing: 0.7 }}>Cumulative — This Batch</span>
                      {use_dpo && c.cumulative_dpo && <span style={{ fontSize: 11, fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase' as const, letterSpacing: 0.7, marginLeft: 'auto' }}>Accuracy (DPO)</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'stretch' }}>
                      {/* Left: core stats */}
                      <div style={{ display: 'flex', gap: 0, flex: '0 0 auto' }}>
                        {[
                          { value: String(c.charts_scored ?? c.chart_count), label: 'Charts Graded', color: '#374151' },
                          { value: `${c.avg_total}%`, label: 'Grading Score', color: scoreColor(c.avg_total), kind: 'grading' },
                          { value: `${c.charts_passed ?? 0}/${c.charts_scored ?? c.chart_count}`, label: 'Charts Passed', color: pfBadge(c.pass_fail).color },
                        ].map((s, si) => (
                          <div key={si} style={{ textAlign: 'center' as const, padding: '16px 24px', borderRight: '1px solid #e0e7ff', ...(s.kind === 'grading' ? gradingMetricStyle : {}) }}>
                            <div style={{ fontSize: 26, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
                            <div style={{ fontSize: 11, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.5, marginTop: 6 }}>{s.label}</div>
                          </div>
                        ))}
                      </div>
                      {/* Right: accuracy stats — same size font */}
                      {use_dpo && c.cumulative_dpo && (
                        <div style={{ display: 'flex', flex: 1, alignItems: 'center' }}>
                          {[
                            c.cumulative_dpo.overall_accuracy != null ? { value: `${c.cumulative_dpo.overall_accuracy}%`, label: 'Overall accuracy (DPO)', color: scoreColor(c.cumulative_dpo.overall_accuracy), bold: true } : null,
                            c.cumulative_dpo.dx_total > 0 ? { value: `${c.cumulative_dpo.dx_accuracy}%`, label: 'Diagnosis accuracy', color: scoreColor(c.cumulative_dpo.dx_accuracy) } : null,
                            c.cumulative_dpo.proc_total > 0 ? { value: `${c.cumulative_dpo.proc_accuracy}%`, label: 'Procedure accuracy', color: scoreColor(c.cumulative_dpo.proc_accuracy) } : null,
                            is_ip && c.cumulative_dpo.drg_total > 0 ? { value: `${c.cumulative_dpo.drg_accuracy}%`, label: 'DRG accuracy', color: scoreColor(c.cumulative_dpo.drg_accuracy) } : null,
                          ].filter(Boolean).map((s: any, si, arr) => (
                            <div key={si} style={{ textAlign: 'center' as const, padding: '16px 20px', flex: 1, borderRight: si < arr.length - 1 ? '1px solid #e0e7ff' : 'none', ...accuracyMetricStyle }}>
                              <div style={{ fontSize: 26, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
                              <div style={{ fontSize: 11, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.5, marginTop: 6 }}>{s.label}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Per-chart header */}
                  {/* This column showed total_score under the heading
                      "Accuracy", which is the weighted score and not an
                      accuracy figure at all. DPO accuracy was already in the
                      per-chart payload and simply never rendered — the two
                      numbers answer different questions and now sit side by
                      side, which is how they read on the coder summary above. */}
                  <div style={{ display: 'grid', gridTemplateColumns: chartCols, gap: 8, padding: '8px 12px', fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 0.5, borderBottom: '1px solid #f0f0f0' }}>
                    <span>Chart</span>
                    <span>Category</span>
                    <span style={{ textAlign: 'center' }}>Score</span>
                    {showChartDpo && <span style={{ textAlign: 'center' }}>Accuracy (DPO)</span>}
                    <span style={{ textAlign: 'center' }}>Result</span>
                  </div>

                  {c.charts.map((ch: any, ci: number) => {
                    const chartKey = `${c.coder_name}:${ch.chart_number}`
                    const chartOpen = expandedChart === chartKey
                    return (
                      <div key={ch.chart_number}>
                        <div
                          className={ci % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                          style={{ display: 'grid', gridTemplateColumns: chartCols, gap: 8, padding: '10px 12px', alignItems: 'center', cursor: ch.feedback?.length ? 'pointer' : 'default' }}
                          onClick={() => ch.feedback?.length && setExpandedChart(chartOpen ? null : chartKey)}
                        >
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600, fontSize: 13 }}>
                            {ch.feedback?.length > 0 && (chartOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
                            {ch.chart_number}
                          </span>
                          <span style={{ fontSize: 13, color: '#374151' }}>
                            {ch.category || '—'}
                            {ch.specialty && <span style={{ ...styles.badge, marginLeft: 6, fontSize: 10, padding: '1px 6px' }}>{ch.specialty}</span>}
                          </span>
                          <span style={{ textAlign: 'center', fontWeight: 700, fontSize: 13, color: ch.total_score != null ? scoreColor(ch.total_score) : '#9ca3af' }}>
                            {ch.total_score != null ? `${ch.total_score}%` : '—'}
                            {ch.drg_flag && !ch.drg_reviewed && <span title="DRG review pending" style={{ marginLeft: 4, fontSize: 10, color: '#d97706' }}>⏳</span>}
                            {ch.drg_reviewed && ch.drg_reviewed_by && (
                              <span title={`DRG reviewed by ${ch.drg_reviewed_by}${ch.drg_reviewed_at ? ' on ' + new Date(ch.drg_reviewed_at).toLocaleDateString() : ''}`} style={{ marginLeft: 4, fontSize: 10, color: '#6b7280', cursor: 'help' }}>✓DRG</span>
                            )}
                          </span>
                          {showChartDpo && (
                            <span style={{ textAlign: 'center', fontWeight: 700, fontSize: 13,
                              color: ch.dpo_overall_accuracy != null ? scoreColor(ch.dpo_overall_accuracy) : '#d1d5db' }}>
                              {/* Blank rather than 0% where this chart carries no
                                  DPO figure — a specialty that does not compute it
                                  has not scored zero. */}
                              {ch.dpo_overall_accuracy != null ? `${ch.dpo_overall_accuracy}%` : '—'}
                            </span>
                          )}
                          <span style={{ textAlign: 'center' }}>
                            {(() => { const b = pfBadge(ch.pass_fail); return <span style={{ fontWeight: 700, fontSize: 12, color: b.color }}>{b.label}</span> })()}
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
