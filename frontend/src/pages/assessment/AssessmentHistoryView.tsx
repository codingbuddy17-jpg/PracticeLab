import { useState, useEffect } from 'react'
import { Download, Trash2, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { listAssessmentHistory, exportAssessmentPDF, exportAnswerKey, deleteAssessment } from '../../api'
import { errorMessage } from '../../api/errors'
import { getPassphrase, rememberPassphrase } from '../../api/assessmentAuth'

interface AssessmentRecord {
  id: number
  assessment_name: string
  config_name: string | null
  student_count: number
  questions_per_student: number
  generated_by: string
  generated_at: string | null
  batch_name: string | null
  /** null means the paper uses the platform default. */
  pass_threshold: number | null
  status_counts?: { pending: number; in_progress: number; submitted: number; expired: number }
}

export function AssessmentHistoryView() {
  const [records, setRecords] = useState<AssessmentRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  // Seeded from whatever was verified elsewhere in the module this session.
  const [passphrase, setPassphrase] = useState(getPassphrase())
  const [reason, setReason] = useState('')
  const [blocked, setBlocked] = useState<{ id: number; message: string; submitted: number } | null>(null)
  const [search, setSearch] = useState('')

  /**
   * Both exports hand over the exam — the paper and the answer key — so they
   * are passphrase-gated server-side now. The passphrase usually comes from
   * the session store (set when the Question Bank verified it); the field
   * beside Delete is the fallback for a trainer who has not opened that tab.
   */
  async function runExport(fn: () => Promise<void>) {
    try {
      await fn()
    } catch (e: any) {
      const msg = errorMessage(e, 'Export failed')
      // The old message pointed at a field that only appeared after clicking
      // the bin, and that served Delete rather than the exports.
      toast.error(
        msg.includes('passphrase') && !passphrase.trim()
          ? 'Enter the trainer passphrase at the top of this tab — these exports contain the answers.'
          : msg,
      )
    }
  }

  function load() {
    setLoading(true)
    listAssessmentHistory()
      .then(setRecords)
      .catch(() => toast.error('Failed to load history'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  /**
   * Delete an assessment. The backend refuses once anyone has sat it, and
   * answers with what would be lost — so the second confirmation states the
   * cost rather than repeating "are you sure?".
   *
   * Uses the shared API helper rather than a hand-built fetch, so failures read
   * the same as everywhere else. The passphrase is still a query parameter on
   * the wire; moving it to a header is a separate change across all endpoints.
   */
  async function handleDelete(id: number, force = false) {
    if (!passphrase.trim()) { toast.error('Enter passphrase'); return }
    if (force && reason.trim().length < 5) {
      toast.error('Enter a reason for deleting completed work'); return
    }
    setDeletingId(id)
    try {
      const res = await deleteAssessment(id, {
        passphrase: passphrase.trim(),
        trainerName: localStorage.getItem('trainer_name')?.trim() || 'Trainer',
        force, reason: reason.trim(),
      })
      toast.success(res.completed_removed
        ? `Deleted — ${res.completed_removed} completed session(s) removed.`
        : 'Assessment deleted')
      setConfirmDelete(null)
      setBlocked(null)
      setPassphrase('')
      setReason('')
      load()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (detail && typeof detail === 'object' && detail.requires === 'force') {
        // Completed work exists. Say what would be lost and require a reason.
        setBlocked({ id, message: detail.message, submitted: detail.submitted })
      } else {
        toast.error(errorMessage(e, 'Delete failed'))
      }
    } finally {
      setDeletingId(null)
    }
  }

  const q = search.trim().toLowerCase()
  const visible = q
    ? records.filter(r => `${r.assessment_name} ${r.batch_name || ''} ${r.generated_by}`
        .toLowerCase().includes(q))
    : records

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
        <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite', color: '#6b7280' }} />
      </div>
    )
  }

  return (
    <div>
      {/* Above the table, so a search that matches nothing keeps the box that
          would clear it. */}
      {records.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setSearch('') }}
            placeholder="Find by name, batch, or who generated it…"
            // Chrome pairs the nearest text input ABOVE a password field as the
            // username and autofills it, then keeps re-filling it — which reads
            // as a search box that has typed your name and cannot be cleared.
            autoComplete="off"
            name="history-search"
            style={{ padding: '7px 11px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, minWidth: 260 }}
          />
          {search && (
            <span style={{ fontSize: 11, color: '#6b7280' }}>{visible.length} of {records.length}</span>
          )}

          {/* One passphrase for the whole tab. It used to appear only after
              clicking the bin, and only served Delete — so an export refused
              for want of a passphrase pointed at a field that was not on
              screen. Verifying it anywhere in the module fills this in. */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            <label style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Trainer passphrase</label>
            <input
              type="password"
              value={passphrase}
              onChange={e => { setPassphrase(e.target.value); rememberPassphrase(e.target.value.trim()) }}
              placeholder={passphrase ? '' : 'required for exports & delete'}
              autoComplete="new-password"
              name="assessment-passphrase"
              style={{ padding: '7px 11px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, width: 190 }}
            />
          </div>
        </div>
      )}

      {blocked && (
        <div style={{ background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.25)', borderRadius: 12, padding: '14px 18px', marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#b91c1c' }}>{blocked.message}</div>
          <div style={{ fontSize: 12, color: '#7f1d1d', marginTop: 4 }}>
            Their answers and scores cannot be recovered. Say why this is being deleted.
          </div>
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            rows={2}
            placeholder="e.g. Duplicate paper issued in error; coders re-sat the correct one."
            style={{ width: '100%', marginTop: 8, padding: '8px 10px', borderRadius: 8, border: '1px solid #fecaca', fontSize: 12, fontFamily: 'inherit', resize: 'vertical' }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <button disabled={reason.trim().length < 5 || deletingId === blocked.id}
              onClick={() => handleDelete(blocked.id, true)}
              style={{ padding: '6px 13px', borderRadius: 8, border: 'none', fontSize: 12, fontWeight: 700,
                       background: reason.trim().length < 5 ? '#e5e7eb' : '#dc2626',
                       color: reason.trim().length < 5 ? '#9ca3af' : '#fff',
                       cursor: reason.trim().length < 5 ? 'not-allowed' : 'pointer' }}>
              Delete anyway
            </button>
            <button onClick={() => { setBlocked(null); setReason('') }}
              style={{ padding: '6px 13px', borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff', color: '#374151', cursor: 'pointer', fontSize: 12, fontWeight: 700 }}>
              Keep it
            </button>
          </div>
        </div>
      )}

      {records.length === 0 ? (
        <div style={styles.empty}>No assessments generated yet. Go to Generate tab to create your first assessment.</div>
      ) : (
        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.thead}>
                {['Name', 'Batch', 'Date', 'Generated By', 'Students', 'Questions', 'Pass mark', 'Progress', 'Actions'].map(h => (
                  <th key={h} style={styles.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map(r => (
                <tr key={r.id} style={styles.tr}>
                  <td style={{ ...styles.td, fontWeight: 700 }}>{r.assessment_name}</td>
                  <td style={{ ...styles.td, color: '#6b7280', fontSize: 12 }}>{r.batch_name || '—'}</td>
                  <td style={{ ...styles.td, fontSize: 12, color: '#6b7280' }}>
                    {r.generated_at ? new Date(r.generated_at).toLocaleDateString() : '—'}
                  </td>
                  <td style={styles.td}>{r.generated_by}</td>
                  <td style={{ ...styles.td, fontWeight: 700, textAlign: 'center' as const }}>{r.student_count}</td>
                  <td style={{ ...styles.td, fontWeight: 700, textAlign: 'center' as const }}>{r.questions_per_student}</td>
                  <td style={{ ...styles.td, textAlign: 'center' as const, fontSize: 12, color: '#6b7280' }}>
                    {r.pass_threshold != null ? `${r.pass_threshold}%` : 'default'}
                  </td>
                  {/* Where it stands, so the list answers "is this finished?"
                      without opening Sessions to find out. */}
                  <td style={{ ...styles.td, fontSize: 11, whiteSpace: 'nowrap' as const }}>
                    {(() => {
                      const c = r.status_counts
                      if (!c) return <span style={{ color: '#9ca3af' }}>—</span>
                      const done = c.submitted, waiting = c.pending + c.in_progress
                      return (
                        <span>
                          <strong style={{ color: done ? '#15803d' : '#9ca3af' }}>{done} done</strong>
                          {waiting > 0 && <span style={{ color: '#92400e' }}> · {waiting} waiting</span>}
                          {c.expired > 0 && <span style={{ color: '#b91c1c' }}> · {c.expired} expired</span>}
                        </span>
                      )
                    })()}
                  </td>
                  <td style={styles.td}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <button
                        style={styles.actionBtn}
                        title="Download every coder's question paper, as a .zip of PDFs"
                        onClick={() => runExport(() => exportAssessmentPDF(r.id, passphrase))}
                      >
                        <Download size={13} />
                        <span style={{ fontSize: 11 }}>Papers</span>
                      </button>
                      <button
                        style={{ ...styles.actionBtn, color: '#4f46e5' }}
                        title="Download the answer key for this assessment"
                        onClick={() => runExport(() => exportAnswerKey(r.id, passphrase))}
                      >
                        <Download size={13} />
                        <span style={{ fontSize: 11 }}>Keys</span>
                      </button>
                      {confirmDelete === r.id ? (
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <button
                            style={{ ...styles.actionBtn, color: '#dc2626', fontSize: 11 }}
                            disabled={deletingId === r.id}
                            onClick={() => handleDelete(r.id)}
                          >
                            {deletingId === r.id ? '…' : 'Confirm'}
                          </button>
                          <button
                            style={{ ...styles.actionBtn, fontSize: 11 }}
                            onClick={() => { setConfirmDelete(null); setPassphrase('') }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          style={{ ...styles.actionBtn, color: '#dc2626' }}
                          title="Delete assessment"
                          onClick={() => setConfirmDelete(r.id)}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  empty: {
    background: 'rgba(255,255,255,0.6)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 14, padding: '40px 24px',
    textAlign: 'center' as const, color: '#9ca3af', fontSize: 14,
  },
  tableWrap: {
    background: 'rgba(255,255,255,0.6)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 14, overflow: 'auto',
  },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  th: {
    padding: '10px 14px', textAlign: 'left' as const,
    fontSize: 11, fontWeight: 700, color: '#6b7280',
    textTransform: 'uppercase' as const, letterSpacing: 0.4,
    borderBottom: '1px solid #f3f4f6',
  },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '12px 14px', color: '#374151', verticalAlign: 'middle' as const },
  actionBtn: {
    display: 'flex', alignItems: 'center', gap: 4,
    padding: '5px 10px', border: '1px solid #e5e7eb',
    borderRadius: 7, background: 'none', cursor: 'pointer',
    fontSize: 13, color: '#4b5563',
  },
  passphraseInput: {
    padding: '5px 10px', border: '1px solid #e5e7eb',
    borderRadius: 7, fontSize: 12, width: 120,
  },
}
