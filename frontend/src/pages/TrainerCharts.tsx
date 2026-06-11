import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Edit2, Archive, RotateCcw, PlusCircle, Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import { searchCharts, updateChart, retireChart, restoreChart, addFilesToChart, getChartTrainer } from '../api'
import { RationaleEditor } from '../components/RationaleEditor'
import type { Chart, ChartStatus, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES } from '../types'

export function TrainerCharts() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<ChartStatus>('Active')
  const [specialty, setSpecialty] = useState<Specialty | ''>('')
  const [charts, setCharts] = useState<Chart[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<Chart | null>(null)
  const [editForm, setEditForm] = useState<{ category: string; difficulty: Difficulty; rationale: string }>({ category: '', difficulty: 'Beginner', rationale: '' })
  const [actor, setActor] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [addingFiles, setAddingFiles] = useState<Chart | null>(null)
  const [viewingRationale, setViewingRationale] = useState<{ chart: Chart; rationale: string } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await searchCharts({ specialty: specialty || undefined, status, page: 1, page_size: 100 })
      setCharts(res.results)
      setTotal(res.total)
    } finally { setLoading(false) }
  }, [specialty, status])

  useEffect(() => { load() }, [load])

  const startEdit = (c: Chart) => {
    setEditing(c)
    setEditForm({ category: c.category, difficulty: c.difficulty, rationale: '' })
  }

  const saveEdit = async () => {
    if (!editing || !actor.trim()) { toast.error('Enter your name'); return }
    try {
      await updateChart(editing.id, actor, editForm)
      toast.success('Chart updated')
      setEditing(null)
      load()
    } catch { toast.error('Update failed') }
  }

  const handleRetire = async (c: Chart) => {
    const name = prompt('Your name:')
    if (!name) return
    let pw: string | null = null
    if (c.uploaded_by !== name) pw = prompt('This chart belongs to another trainer. Enter master admin passphrase:')
    try {
      await retireChart(c.id, name, pw ?? undefined)
      toast.success(`${c.chart_number} retired`)
      load()
    } catch { toast.error('Failed — check passphrase') }
  }

  const handleRestore = async (c: Chart) => {
    const name = prompt('Your name:')
    if (!name) return
    let pw: string | null = null
    if (c.uploaded_by !== name) pw = prompt('Enter master admin passphrase:')
    try {
      await restoreChart(c.id, name, pw ?? undefined)
      toast.success(`${c.chart_number} restored`)
      load()
    } catch { toast.error('Failed — check passphrase') }
  }

  const handleViewRationale = async (c: Chart) => {
    try {
      const full = await getChartTrainer(c.id)
      setViewingRationale({ chart: c, rationale: full.rationale || '<p>No rationale added.</p>' })
    } catch { toast.error('Could not load rationale') }
  }

  const handleAddFiles = async (files: FileList | null) => {
    if (!files || !addingFiles || !actor.trim()) return
    try {
      const res = await addFilesToChart(addingFiles.id, Array.from(files), actor)
      toast.success(res.message)
      setAddingFiles(null)
      load()
    } catch { toast.error('Failed to add files') }
  }

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={() => navigate('/trainer')}><ChevronLeft size={16} /> Back</button>
        <span style={styles.title}>Manage Charts</span>
      </div>

      <div style={styles.content}>
        <div style={styles.filterRow}>
          <select style={styles.select} value={status} onChange={e => setStatus(e.target.value as ChartStatus)}>
            <option value="Active">Active</option>
            <option value="Retired">Retired</option>
          </select>
          <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value as Specialty | '')}>
            <option value="">All Specialties</option>
            {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <span style={styles.count}>{total} chart{total !== 1 ? 's' : ''}</span>
        </div>

        {loading ? <div style={styles.center}>Loading...</div> : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  {['Chart #', 'Specialty', 'Category', 'Difficulty', 'Uploaded By', 'Views', 'Actions'].map(h => (
                    <th key={h} style={styles.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {charts.map(c => (
                  <tr key={c.id} style={styles.tr}>
                    <td style={styles.td}><strong>{c.chart_number}</strong></td>
                    <td style={styles.td}>{c.specialty}</td>
                    <td style={styles.td}>{c.category}</td>
                    <td style={styles.td}>{c.difficulty}</td>
                    <td style={styles.td}>{c.uploaded_by}</td>
                    <td style={styles.td}>{c.view_count}</td>
                    <td style={styles.td}>
                      <div style={styles.actions}>
                        <button style={styles.actionBtn} title="View rationale" onClick={() => handleViewRationale(c)}><Eye size={14} /></button>
                        <button style={styles.actionBtn} title="Edit" onClick={() => startEdit(c)}><Edit2 size={14} /></button>
                        <button style={styles.actionBtn} title="Add files" onClick={() => { setAddingFiles(c); setActor('') }}>
                          <PlusCircle size={14} />
                        </button>
                        {status === 'Active' ? (
                          <button style={{ ...styles.actionBtn, color: '#dc2626' }} title="Retire" onClick={() => handleRetire(c)}>
                            <Archive size={14} />
                          </button>
                        ) : (
                          <button style={{ ...styles.actionBtn, color: '#16a34a' }} title="Restore" onClick={() => handleRestore(c)}>
                            <RotateCcw size={14} />
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

      {/* Edit modal */}
      {editing && (
        <div style={styles.overlay}>
          <div style={styles.modal}>
            <div style={styles.modalTitle}>Edit {editing.chart_number}</div>
            <label style={styles.label}>Your Name</label>
            <input style={styles.input} value={actor} onChange={e => setActor(e.target.value)} placeholder="Your name" />
            <label style={styles.label}>Category</label>
            <input style={styles.input} value={editForm.category} onChange={e => setEditForm(f => ({ ...f, category: e.target.value }))} />
            <label style={styles.label}>Difficulty</label>
            <select style={styles.select} value={editForm.difficulty} onChange={e => setEditForm(f => ({ ...f, difficulty: e.target.value as Difficulty }))}>
              {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <label style={styles.label}>Rationale</label>
            <RationaleEditor content={editForm.rationale} onChange={v => setEditForm(f => ({ ...f, rationale: v }))} />
            <div style={styles.modalActions}>
              <button style={styles.primaryBtn} onClick={saveEdit}>Save</button>
              <button style={styles.cancelBtn} onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* View rationale modal */}
      {viewingRationale && (
        <div style={styles.overlay}>
          <div style={styles.modal}>
            <div style={styles.modalTitle}>Rationale — {viewingRationale.chart.chart_number}</div>
            <div style={styles.rationaleSubtitle}>
              {viewingRationale.chart.specialty} · {viewingRationale.chart.category} · {viewingRationale.chart.difficulty}
            </div>
            <div
              style={styles.rationaleBody}
              dangerouslySetInnerHTML={{ __html: viewingRationale.rationale }}
            />
            <div style={styles.modalActions}>
              <button style={styles.primaryBtn} onClick={() => { setViewingRationale(null); startEdit(viewingRationale.chart) }}>Edit</button>
              <button style={styles.cancelBtn} onClick={() => setViewingRationale(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Add files modal */}
      {addingFiles && (
        <div style={styles.overlay}>
          <div style={styles.modal}>
            <div style={styles.modalTitle}>Add Files to {addingFiles.chart_number}</div>
            <label style={styles.label}>Your Name</label>
            <input style={styles.input} value={actor} onChange={e => setActor(e.target.value)} placeholder="Your name" />
            <label style={styles.label}>Select Files to Append</label>
            <input type="file" multiple accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff" onChange={e => handleAddFiles(e.target.files)} />
            <div style={styles.modalActions}>
              <button style={styles.cancelBtn} onClick={() => setAddingFiles(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '6px 12px', cursor: 'pointer', fontSize: 13 },
  title: { fontWeight: 700, fontSize: 18 },
  content: { maxWidth: 1100, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 },
  filterRow: { display: 'flex', gap: 10, alignItems: 'center' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, background: '#fff' },
  count: { fontSize: 13, color: '#6b7280', marginLeft: 'auto' },
  center: { textAlign: 'center', padding: 60, color: '#9ca3af' },
  tableWrap: { overflowX: 'auto', background: '#fff', borderRadius: 8, border: '1px solid #e5e7eb' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '10px 14px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', fontSize: 13, color: '#374151' },
  actions: { display: 'flex', gap: 6 },
  actionBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 5, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#374151' },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 },
  modal: { background: '#fff', borderRadius: 10, padding: 28, width: '90%', maxWidth: 560, display: 'flex', flexDirection: 'column', gap: 12 },
  modalTitle: { fontWeight: 700, fontSize: 17, marginBottom: 4 },
  modalActions: { display: 'flex', gap: 10, marginTop: 8 },
  label: { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' },
  input: { padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 },
  primaryBtn: { padding: '10px 20px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  cancelBtn: { padding: '10px 20px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', fontSize: 14 },
  rationaleSubtitle: { fontSize: 12, color: '#6b7280', marginTop: -8 },
  rationaleBody: { padding: '12px', border: '1px solid #e5e7eb', borderRadius: 6, minHeight: 120, fontSize: 14, lineHeight: 1.7, background: '#fafafa', overflowY: 'auto' as const, maxHeight: 400 },
}
