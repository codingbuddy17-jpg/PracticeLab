import { useState, useEffect } from 'react'
import { Loader, FileCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { getDRGReview, submitDRGDecision } from '../../api'
import { trainerName } from './shared'
import styles from './styles'

export function DRGReviewView({ batchId, onDone }: any) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState<Record<number, boolean>>({})

  useEffect(() => { loadRows() }, [])

  async function loadRows() {
    setLoading(true)
    try { setRows(await getDRGReview(batchId)) } catch { /* ignore */ } finally { setLoading(false) }
  }

  async function decide(resultId: number, drgError: boolean) {
    setSubmitting(s => ({ ...s, [resultId]: true }))
    try {
      await submitDRGDecision(resultId, drgError, trainerName())
      setRows(r => r.filter(x => x.result_id !== resultId))
      toast.success(drgError ? 'Marked as DRG error (0 pts)' : 'Confirmed correct DRG (40 pts)')
    } catch { toast.error('Failed to save decision') }
    finally { setSubmitting(s => ({ ...s, [resultId]: false })) }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>DRG Review</div>
      <p style={styles.helpText}>
        Review flagged cases. Confirm if the DRG is correct (40 pts) or mark as DRG error (0 pts).
        Results are finalized after all rows are reviewed.
      </p>
      {rows.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={36} color="#16a34a" />
          <p style={{ color: '#16a34a', fontWeight: 600 }}>All DRG reviews complete!</p>
          <button style={styles.primaryBtn} onClick={onDone}>← Back to Batch</button>
        </div>
      ) : (
        rows.map((r: any) => (
          <div key={r.result_id} style={styles.drgCard}>
            <div style={styles.drgHeader}>
              <span style={{ fontWeight: 700 }}>{r.coder_name}</span>
              <span style={styles.badge}>{r.chart_number}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                PDx {r.pdx_score} + SDx {r.sdx_score} + PCS {r.pcs_score || 0} = {(r.pdx_score || 0) + (r.sdx_score || 0) + (r.pcs_score || 0)} pts (before DRG)
              </span>
            </div>
            {r.feedback?.length > 0 && (
              <div style={styles.fbList}>
                {r.feedback.map((f: any, i: number) => (
                  <div key={i} style={styles.fbRow}>
                    <span style={styles.fbSection}>{f.section}</span>
                    <span style={styles.fbIssue}>{f.issue_type}</span>
                    {f.ak_code && <span style={{ fontSize: 12, color: '#374151' }}>AK: {f.ak_code}</span>}
                    {f.coder_code && <span style={{ fontSize: 12, color: '#6b7280' }}>Coder: {f.coder_code}</span>}
                    {f.detail && <span style={{ fontSize: 12, color: '#6b7280' }}>{f.detail}</span>}
                  </div>
                ))}
              </div>
            )}
            <div style={styles.drgActions}>
              <button style={{ ...styles.outlineBtn, borderColor: '#16a34a', color: '#16a34a' }}
                disabled={submitting[r.result_id]} onClick={() => decide(r.result_id, false)}>
                ✓ DRG Correct (+40 pts)
              </button>
              <button style={{ ...styles.outlineBtn, borderColor: '#dc2626', color: '#dc2626' }}
                disabled={submitting[r.result_id]} onClick={() => decide(r.result_id, true)}>
                ✗ DRG Error (0 pts)
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
