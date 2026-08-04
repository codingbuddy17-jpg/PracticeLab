import { useState, useEffect } from 'react'
import { Loader, ChevronDown, ChevronRight, FileDown } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentAnalyticsByBatch, getAssessmentAnalyticsBatchDrill, downloadAssessmentBatchReport, downloadAssessmentBatchCoderReportsZip } from '../../../api'
import { PASS, scoreColor, fmt, LoadingSpinner, EmptyState } from './helpers'
import { usePagination } from '../../../components/Paginator'

export function BatchAnalysisTab() {
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

  return <BatchList batches={batches} expanded={expanded} setExpanded={setExpanded} drillData={drillData} drillLoading={drillLoading} toggleBatch={toggleBatch} />
}

function BatchList({ batches, expanded, setExpanded, drillData, drillLoading, toggleBatch }: {
  batches: any[]; expanded: string | null; setExpanded: (v: string | null) => void;
  drillData: Record<string, any>; drillLoading: string | null; toggleBatch: (name: string) => void;
}) {
  const { pageData, Paginator } = usePagination(batches, 10)
  // Reports are fetched rather than window.open()'d, so a failure surfaces as a
  // toast instead of a blank tab showing raw JSON. Keyed by batch so the button
  // that was pressed is the one that shows progress.
  const [dlBusy, setDlBusy] = useState<string | null>(null)

  async function runDownload(key: string, fn: () => Promise<void>) {
    setDlBusy(key)
    try {
      await fn()
    } catch (e: any) {
      toast.error(e.message || 'Download failed.')
    } finally {
      setDlBusy(null)
    }
  }

  return (
    <>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {pageData.map((batch: any) => {
        const isOpen = expanded === batch.batch_name
        const drill = drillData[batch.batch_name]
        const isDrillLoading = drillLoading === batch.batch_name

        return (
          <div key={batch.batch_name} style={{ background: 'rgba(255,255,255,0.68)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderRadius: 16, border: isOpen ? '1px solid rgba(124,58,237,0.3)' : '1px solid rgba(255,255,255,0.55)', boxShadow: '0 2px 12px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 24px' }}>
              <button onClick={() => toggleBatch(batch.batch_name)} style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}>
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
                <button onClick={(e) => { e.stopPropagation(); runDownload(`pdf:${batch.batch_name}`, () => downloadAssessmentBatchReport(batch.batch_name)) }} disabled={dlBusy === `pdf:${batch.batch_name}`} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 13px', borderRadius: 9, background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700 }}>
                  <FileDown size={12} /> {dlBusy === `pdf:${batch.batch_name}` ? 'Preparing…' : 'PDF Report'}
                </button>
                <button onClick={(e) => { e.stopPropagation(); runDownload(`zip:${batch.batch_name}`, () => downloadAssessmentBatchCoderReportsZip(batch.batch_name)) }} disabled={dlBusy === `zip:${batch.batch_name}`} title={`Download individual PDF reports for all ${batch.total_coders} coders as a ZIP`} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 13px', borderRadius: 9, background: 'linear-gradient(135deg, #059669, #047857)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700 }}>
                  <FileDown size={12} /> {dlBusy === `zip:${batch.batch_name}` ? 'Preparing…' : 'All Coder Reports (.zip)'}
                </button>
              </div>
            </div>

            {isOpen && (
              <div style={{ padding: '0 24px 24px', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                {isDrillLoading && <div style={{ padding: '24px 0', color: '#7c3aed', display: 'flex', alignItems: 'center', gap: 8 }}><Loader size={16} style={{ animation: 'spin 1s linear infinite' }} /> Loading batch detail…</div>}

                {drill && !isDrillLoading && (
                  <div>
                    <div style={{ marginTop: 20, marginBottom: 20 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: '#111', marginBottom: 10 }}>Training Need Identification (TNI)</div>
                      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' as const }}>
                        <div style={{ flex: 1, minWidth: 200 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#dc2626', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 6 }}>✗ Weak Topics (need training)</div>
                          {drill.weak_topics.length === 0
                            ? <div style={{ fontSize: 12, color: '#9ca3af' }}>None — all topics above 80%</div>
                            : drill.weak_topics.map((t: any, i: number) => (
                              <div key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: '#fee2e2', color: '#991b1b', borderRadius: 20, padding: '4px 12px', margin: '3px 4px 3px 0', fontSize: 12, fontWeight: 700 }}>
                                {t.topic} <span style={{ opacity: 0.7 }}>{t.accuracy_pct}%</span>
                              </div>
                            ))
                          }
                        </div>
                        <div style={{ flex: 1, minWidth: 200 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#16a34a', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 6 }}>✓ Strong Topics (well performed)</div>
                          {drill.strong_topics.length === 0
                            ? <div style={{ fontSize: 12, color: '#9ca3af' }}>None above 90% yet</div>
                            : drill.strong_topics.map((t: any, i: number) => (
                              <div key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: '#dcfce7', color: '#166534', borderRadius: 20, padding: '4px 12px', margin: '3px 4px 3px 0', fontSize: 12, fontWeight: 700 }}>
                                {t.topic} <span style={{ opacity: 0.7 }}>{t.accuracy_pct}%</span>
                              </div>
                            ))
                          }
                        </div>
                      </div>
                    </div>

                    {drill.all_topics && drill.all_topics.length > 0 && drill.coder_rows && drill.coder_rows.length > 0 && (
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: '#111', marginBottom: 10 }}>Coder × Topic Accuracy Matrix</div>
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                            <thead>
                              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, whiteSpace: 'nowrap' as const }}>Coder</th>
                                {(drill.all_topics as string[]).map((tp: string) => (
                                  <th key={tp} style={{ padding: '8px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, whiteSpace: 'nowrap' as const, maxWidth: 100 }}>
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
                                  <td style={{ padding: '7px 10px', textAlign: 'center', fontWeight: 700, fontSize: 12, color: row.delta == null ? '#9ca3af' : row.delta > 0 ? '#16a34a' : row.delta < 0 ? '#dc2626' : '#6b7280' }}>
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
    <Paginator />
    </>
  )
}
