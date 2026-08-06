import { useState, useEffect, useCallback } from 'react'
import { useSmartBack } from '../hooks/useSmartBack'
import { ChevronLeft, Edit2, Archive, RotateCcw, PlusCircle, Eye, BookOpen, ChevronRight, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { searchCharts, updateChart, retireChart, restoreChart, addFilesToChart, getChartTrainer } from '../api'
import { RationaleEditor } from '../components/RationaleEditor'
import { useLocalStorage } from '../hooks/useLocalStorage'
import type { Chart, ChartStatus, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES } from '../types'
import { SPECIALTY_COLORS, DIFFICULTY_COLORS } from '../theme'

const PAGE_SIZE = 25

export function TrainerCharts() {
  const goBack = useSmartBack('/trainer/chart-management')
  const [trainerName] = useLocalStorage<string>('trainer_name', '')
  const [status, setStatus] = useState<ChartStatus>('Active')
  const [specialty, setSpecialty] = useState<Specialty | ''>('')
  const [query, setQuery] = useState('')
  const [answerKeyStatus, setAnswerKeyStatus] = useState<'all' | 'with_key' | 'missing_key'>('all')
  const [charts, setCharts] = useState<Chart[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const [editing, setEditing] = useState<Chart | null>(null)
  const [editForm, setEditForm] = useState<{ category: string; difficulty: Difficulty; rationale: string }>({ category: '', difficulty: 'Beginner', rationale: '' })
  const [actor, setActor] = useState(trainerName)
  const [editPassphrase, setEditPassphrase] = useState('')
  const [addFilesPassphrase, setAddFilesPassphrase] = useState('')
  const [saving, setSaving] = useState(false)
  const [addingFiles, setAddingFiles] = useState<Chart | null>(null)
  const [viewingRationale, setViewingRationale] = useState<{ chart: Chart; rationale: string } | null>(null)
  const [actionModal, setActionModal] = useState<{
    chart: Chart; action: 'retire' | 'restore'; name: string; passphrase: string; loading: boolean
  } | null>(null)

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    setSelected(new Set())
    try {
      const res = await searchCharts({
        q: query.trim() || undefined,
        specialty: specialty || undefined,
        status,
        answer_key_status: answerKeyStatus === 'all' ? undefined : answerKeyStatus,
        page: p,
        page_size: PAGE_SIZE,
      })
      setCharts(res.results)
      setTotal(res.total)
      setPage(p)
    } finally { setLoading(false) }
  }, [query, specialty, status, answerKeyStatus])

  useEffect(() => { load(1) }, [load])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const startEdit = async (c: Chart) => {
    setEditing(c)
    setEditForm({ category: c.category, difficulty: c.difficulty, rationale: '' })
    setActor(trainerName)
    setEditPassphrase('')
    try {
      const full = await getChartTrainer(c.id)
      setEditForm(f => ({ ...f, rationale: full.rationale || '' }))
    } catch { /* leave rationale blank, user can still edit */ }
  }

  const saveEdit = async () => {
    if (!editing || !actor.trim()) { toast.error('Enter your name'); return }
    const needsPassphrase = editing.uploaded_by !== actor
    if (needsPassphrase && !editPassphrase.trim()) { toast.error('Master admin passphrase required'); return }
    setSaving(true)
    try {
      await updateChart(editing.id, actor, editForm, needsPassphrase ? editPassphrase : undefined)
      toast.success('Chart updated')
      setEditing(null)
      load(page)
    } catch { toast.error('Update failed') } finally { setSaving(false) }
  }

  const handleRetire = (c: Chart) => {
    setActionModal({ chart: c, action: 'retire', name: actor || trainerName, passphrase: '', loading: false })
  }

  const handleRestore = (c: Chart) => {
    setActionModal({ chart: c, action: 'restore', name: actor || trainerName, passphrase: '', loading: false })
  }

  const submitAction = async () => {
    if (!actionModal) return
    const { chart, action, name, passphrase } = actionModal
    if (!name.trim()) { toast.error('Enter your name'); return }
    const needsPassphrase = chart.uploaded_by !== name
    if (needsPassphrase && !passphrase.trim()) { toast.error('Master admin passphrase required'); return }
    setActionModal(m => m ? { ...m, loading: true } : null)
    try {
      if (action === 'retire') {
        await retireChart(chart.id, name, needsPassphrase ? passphrase : undefined)
        toast.success(`${chart.chart_number} retired`)
      } else {
        await restoreChart(chart.id, name, needsPassphrase ? passphrase : undefined)
        toast.success(`${chart.chart_number} restored`)
      }
      setActionModal(null)
      load(page)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Action failed — check passphrase')
      setActionModal(m => m ? { ...m, loading: false } : null)
    }
  }

  const handleBulkRetire = async () => {
    if (selected.size === 0) return
    if (!trainerName) { toast.error('Set your trainer name in Upload Charts first'); return }
    const selectedCharts = charts.filter(c => selected.has(c.id))
    const mine = selectedCharts.filter(c => c.uploaded_by === trainerName)
    const others = selectedCharts.filter(c => c.uploaded_by !== trainerName)
    const msg = others.length > 0
      ? `${mine.length} chart(s) will be retired. ${others.length} belong to other trainers and will be skipped — use the row-level retire button for those. Continue?`
      : `Retire ${mine.length} selected chart${mine.length !== 1 ? 's' : ''}?`
    if (!window.confirm(msg)) return
    let successCount = 0
    for (const c of mine) {
      try { await retireChart(c.id, trainerName); successCount++ } catch { /* skip individual */ }
    }
    toast.success(`${successCount} chart${successCount !== 1 ? 's' : ''} retired`)
    if (others.length > 0) toast(`${others.length} chart(s) from other trainers skipped`, { icon: 'ℹ️' })
    load(page)
  }

  const handleViewRationale = async (c: Chart) => {
    try {
      const full = await getChartTrainer(c.id)
      setViewingRationale({ chart: c, rationale: full.rationale || '<p>No rationale added.</p>' })
    } catch { toast.error('Could not load rationale') }
  }

  const handleAddFiles = async (files: FileList | null) => {
    if (!files || !addingFiles || !actor.trim()) return
    const needsPassphrase = addingFiles.uploaded_by !== actor
    if (needsPassphrase && !addFilesPassphrase.trim()) { toast.error('Master admin passphrase required'); return }
    try {
      const res = await addFilesToChart(addingFiles.id, Array.from(files), actor, needsPassphrase ? addFilesPassphrase : undefined)
      toast.success(res.message)
      setAddingFiles(null)
      setAddFilesPassphrase('')
      load(page)
    } catch (err: any) { toast.error(err?.response?.data?.detail || 'Failed to add files') }
  }

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelected(prev => prev.size === charts.length ? new Set() : new Set(charts.map(c => c.id)))
  }

  return (
    <div style={styles.container}>
      <PageHeader title="Manage Charts" onBack={() => goBack()} />

      <div style={styles.content}>
        <div style={styles.toolbar}>
          <div style={styles.filters}>
            <div style={styles.searchWrap}>
              <Search size={13} color="#9ca3af" />
              <input
                style={styles.searchInput}
                placeholder="Search chart #, alias, category..."
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
            </div>
            <select style={styles.select} value={status} onChange={e => setStatus(e.target.value as ChartStatus)}>
              <option value="Active">Active</option>
              <option value="Retired">Retired</option>
            </select>
            <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value as Specialty | '')}>
              <option value="">All Specialties</option>
              {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select style={styles.select} value={answerKeyStatus} onChange={e => setAnswerKeyStatus(e.target.value as any)}>
              <option value="all">All Key Status</option>
              <option value="with_key">Has Answer Key</option>
              <option value="missing_key">Missing Answer Key</option>
            </select>
            <span style={styles.count}>{total} chart{total !== 1 ? 's' : ''}</span>
          </div>
          {selected.size > 0 && status === 'Active' && (
            <button style={styles.bulkRetireBtn} onClick={handleBulkRetire}>
              <Archive size={14} /> Retire {selected.size} selected
            </button>
          )}
        </div>

        {loading ? (
          <div style={styles.loadingWrap}>
            {[...Array(5)].map((_, i) => <div key={i} style={styles.skeletonRow} />)}
          </div>
        ) : (
          <>
            <div style={styles.tableWrap}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={{ ...styles.th, width: 36 }}>
                      <input type="checkbox" checked={selected.size === charts.length && charts.length > 0} onChange={toggleSelectAll} />
                    </th>
                    {['Chart #', 'Specialty', 'Category', 'Difficulty', 'Answer Key', 'Uploaded By', 'Views', 'Actions'].map(h => (
                      <th key={h} style={styles.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {charts.map(c => {
                    const sc = SPECIALTY_COLORS[c.specialty]
                    const dc = DIFFICULTY_COLORS[c.difficulty]
                    return (
                      <tr key={c.id} style={{ ...styles.tr, background: selected.has(c.id) ? '#f5f3ff' : undefined }}>
                        <td style={styles.td}>
                          <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSelect(c.id)} />
                        </td>
                        <td style={styles.td}>
                          <div style={styles.chartNumCell}>
                            <div style={{ ...styles.colorDot, background: sc.bg }} />
                            <strong>{c.chart_number}</strong>
                          </div>
                        </td>
                        <td style={styles.td}><span style={{ ...styles.specBadge, background: sc.light, color: sc.bg }}>{c.specialty}</span></td>
                        <td style={styles.td}>{c.category}</td>
                        <td style={styles.td}><span style={{ ...styles.diffBadge, ...dc }}>{c.difficulty}</span></td>
                        <td style={styles.td}>
                          <span style={c.has_answer_key ? styles.keyBadgeReady : styles.keyBadgeMissing}>
                            {c.has_answer_key ? 'Has Key' : 'No Key'}
                          </span>
                        </td>
                        <td style={styles.td}>{c.uploaded_by}</td>
                        <td style={styles.td}><span style={styles.viewCount}>{c.view_count}</span></td>
                        <td style={styles.td}>
                          <div style={styles.actions}>
                            <button style={styles.actionBtn} title="View rationale" onClick={() => handleViewRationale(c)}><Eye size={13} /></button>
                            <button style={styles.actionBtn} title="Edit" onClick={() => startEdit(c)}><Edit2 size={13} /></button>
                            <button style={styles.actionBtn} title="Add files" onClick={() => { setAddingFiles(c); setActor(trainerName); setAddFilesPassphrase('') }}><PlusCircle size={13} /></button>
                            {status === 'Active'
                              ? <button style={{ ...styles.actionBtn, color: '#dc2626' }} title="Retire" onClick={() => handleRetire(c)}><Archive size={13} /></button>
                              : <button style={{ ...styles.actionBtn, color: '#16a34a' }} title="Restore" onClick={() => handleRestore(c)}><RotateCcw size={13} /></button>
                            }
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={styles.pagination}>
                <button style={styles.pageBtn} disabled={page === 1} onClick={() => load(page - 1)}><ChevronLeft size={15} /></button>
                <span style={styles.pageInfo}>Page {page} of {totalPages}</span>
                <button style={styles.pageBtn} disabled={page === totalPages} onClick={() => load(page + 1)}><ChevronRight size={15} /></button>
              </div>
            )}
          </>
        )}
      </div>

      {/* View rationale modal */}
      {viewingRationale && (
        <Modal title={`Rationale — ${viewingRationale.chart.chart_number}`} onClose={() => setViewingRationale(null)}>
          <div style={styles.rationaleSubtitle}>{viewingRationale.chart.specialty} · {viewingRationale.chart.category} · {viewingRationale.chart.difficulty}</div>
          <div style={styles.rationaleBody} dangerouslySetInnerHTML={{ __html: viewingRationale.rationale }} />
          <div style={styles.modalActions}>
            <button style={styles.primaryBtn} onClick={() => { setViewingRationale(null); startEdit(viewingRationale.chart) }}>Edit</button>
            <button style={styles.cancelBtn} onClick={() => setViewingRationale(null)}>Close</button>
          </div>
        </Modal>
      )}

      {/* Edit modal */}
      {editing && (
        <Modal title={`Edit ${editing.chart_number}`} onClose={() => setEditing(null)}>
          <Field label="Your Name"><input style={styles.input} value={actor} onChange={e => setActor(e.target.value)} placeholder="Your name" /></Field>
          {editing.uploaded_by !== actor && (
            <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 7, padding: '10px 12px', fontSize: 13, color: '#78350f' }}>
              This chart was uploaded by <strong>{editing.uploaded_by}</strong>. Master admin passphrase required.
            </div>
          )}
          {editing.uploaded_by !== actor && (
            <Field label="Master Admin Passphrase">
              <input style={styles.input} type="password" autoComplete="new-password" value={editPassphrase}
                onChange={e => setEditPassphrase(e.target.value)}
                placeholder="Enter passphrase" />
            </Field>
          )}
          <Field label="Category"><input style={styles.input} value={editForm.category} onChange={e => setEditForm(f => ({ ...f, category: e.target.value }))} /></Field>
          <Field label="Difficulty">
            <select style={styles.select} value={editForm.difficulty} onChange={e => setEditForm(f => ({ ...f, difficulty: e.target.value as Difficulty }))}>
              {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Rationale">
            <RationaleEditor content={editForm.rationale} onChange={v => setEditForm(f => ({ ...f, rationale: v }))} />
          </Field>
          <div style={styles.modalActions}>
            <button style={{ ...styles.primaryBtn, opacity: saving ? 0.7 : 1 }} disabled={saving} onClick={saveEdit}>
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button style={styles.cancelBtn} onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </Modal>
      )}

      {/* Retire / Restore action modal */}
      {actionModal && (
        <Modal
          title={actionModal.action === 'retire' ? `Retire ${actionModal.chart.chart_number}` : `Restore ${actionModal.chart.chart_number}`}
          onClose={() => setActionModal(null)}
        >
          <Field label="Your Name">
            <input style={styles.input} value={actionModal.name}
              onChange={e => setActionModal(m => m ? { ...m, name: e.target.value } : null)}
              placeholder="Your trainer name" />
          </Field>
          {actionModal.chart.uploaded_by !== actionModal.name && (
            <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 7, padding: '10px 12px', fontSize: 13, color: '#78350f' }}>
              This chart was uploaded by <strong>{actionModal.chart.uploaded_by}</strong>. Master admin passphrase required.
            </div>
          )}
          {actionModal.chart.uploaded_by !== actionModal.name && (
            <Field label="Master Admin Passphrase">
              <input style={styles.input} type="password" autoComplete="new-password" value={actionModal.passphrase}
                onChange={e => setActionModal(m => m ? { ...m, passphrase: e.target.value } : null)}
                placeholder="Enter passphrase" />
            </Field>
          )}
          <div style={styles.modalActions}>
            <button
              style={{ ...styles.primaryBtn, background: actionModal.action === 'retire' ? '#dc2626' : '#16a34a', opacity: actionModal.loading ? 0.7 : 1 }}
              disabled={actionModal.loading}
              onClick={submitAction}>
              {actionModal.loading ? 'Processing...' : actionModal.action === 'retire' ? 'Retire Chart' : 'Restore Chart'}
            </button>
            <button style={styles.cancelBtn} onClick={() => setActionModal(null)}>Cancel</button>
          </div>
        </Modal>
      )}

      {/* Add files modal */}
      {addingFiles && (
        <Modal title={`Add Files to ${addingFiles.chart_number}`} onClose={() => setAddingFiles(null)}>
          <Field label="Your Name"><input style={styles.input} value={actor} onChange={e => setActor(e.target.value)} placeholder="Your name" /></Field>
          {addingFiles.uploaded_by !== actor && (
            <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 7, padding: '10px 12px', fontSize: 13, color: '#78350f' }}>
              This chart was uploaded by <strong>{addingFiles.uploaded_by}</strong>. Master admin passphrase required.
            </div>
          )}
          {addingFiles.uploaded_by !== actor && (
            <Field label="Master Admin Passphrase">
              <input style={styles.input} type="password" autoComplete="new-password" value={addFilesPassphrase}
                onChange={e => setAddFilesPassphrase(e.target.value)}
                placeholder="Enter passphrase" />
            </Field>
          )}
          <Field label="Select Files to Append">
            <input type="file" multiple accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff" onChange={e => handleAddFiles(e.target.files)} />
          </Field>
          <div style={styles.modalActions}>
            <button style={styles.cancelBtn} onClick={() => setAddingFiles(null)}>Cancel</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={modalStyles.overlay}>
      <div style={modalStyles.box}>
        <div style={modalStyles.header}><span style={modalStyles.title}>{title}</span><button style={modalStyles.closeBtn} onClick={onClose}>✕</button></div>
        <div style={modalStyles.body}>{children}</div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 5 }}><label style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.6 }}>{label}</label>{children}</div>
}

function PageHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div style={headerStyles.topBar}>
      <button style={headerStyles.backBtn} onClick={onBack}><ChevronLeft size={16} /> Back</button>
      <div style={headerStyles.logo}><BookOpen size={18} color="#4f46e5" /><span style={headerStyles.logoText}>PracticeLab</span></div>
      <span style={headerStyles.title}>{title}</span>
    </div>
  )
}

const headerStyles: Record<string, React.CSSProperties> = {
  topBar: { display: 'flex', alignItems: 'center', gap: 14, padding: '13px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10 },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', fontSize: 13, color: '#374151' },
  logo: { display: 'flex', alignItems: 'center', gap: 6 },
  logoText: { fontWeight: 800, fontSize: 15, color: '#111' },
  title: { fontWeight: 700, fontSize: 17, color: '#111', marginLeft: 4 },
}

const modalStyles: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999, backdropFilter: 'blur(2px)' },
  box: { background: '#fff', borderRadius: 12, width: '90%', maxWidth: 560, boxShadow: '0 20px 40px rgba(0,0,0,0.2)', overflow: 'hidden' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e5e7eb', background: '#fafafa' },
  title: { fontWeight: 800, fontSize: 16 },
  closeBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 18, padding: '2px 6px' },
  body: { padding: 20, display: 'flex', flexDirection: 'column', gap: 14, maxHeight: '75vh', overflowY: 'auto' },
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  content: { maxWidth: 1150, margin: '0 auto', padding: '24px' },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' },
  filters: { display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
  searchWrap: { display: 'flex', alignItems: 'center', gap: 6, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 7, padding: '0 10px', height: 34 },
  searchInput: { border: 'none', outline: 'none', fontSize: 13, minWidth: 220, background: 'transparent' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, background: '#fff' },
  count: { fontSize: 13, color: '#6b7280' },
  bulkRetireBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', background: '#fff5f5', border: '1px solid #fca5a5', color: '#dc2626', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  loadingWrap: { display: 'flex', flexDirection: 'column', gap: 8 },
  skeletonRow: { height: 44, borderRadius: 8, background: 'linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite' },
  tableWrap: { overflowX: 'auto', background: '#fff', borderRadius: 10, border: '1px solid #e5e7eb', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb', background: '#fafafa' },
  tr: { borderBottom: '1px solid #f3f4f6', transition: 'background 0.1s' },
  td: { padding: '10px 14px', fontSize: 13, color: '#374151' },
  chartNumCell: { display: 'flex', alignItems: 'center', gap: 8 },
  colorDot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  specBadge: { fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  diffBadge: { fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20 },
  keyBadgeReady: { fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 20, background: '#dcfce7', color: '#166534', whiteSpace: 'nowrap' },
  keyBadgeMissing: { fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 20, background: '#fef3c7', color: '#92400e', whiteSpace: 'nowrap' },
  viewCount: { fontWeight: 600, color: '#374151' },
  actions: { display: 'flex', gap: 5 },
  actionBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#374151', transition: 'all 0.1s' },
  pagination: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, marginTop: 16 },
  pageBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  pageInfo: { fontSize: 13, color: '#374151', fontWeight: 600 },
  rationaleSubtitle: { fontSize: 12, color: '#6b7280' },
  rationaleBody: { padding: 14, border: '1px solid #e5e7eb', borderRadius: 8, minHeight: 100, fontSize: 14, lineHeight: 1.7, background: '#fafafa', overflowY: 'auto' as const, maxHeight: 360 },
  modalActions: { display: 'flex', gap: 10, paddingTop: 4 },
  primaryBtn: { padding: '10px 20px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 7, cursor: 'pointer', fontWeight: 700, fontSize: 14 },
  cancelBtn: { padding: '10px 20px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 7, cursor: 'pointer', fontSize: 14 },
  input: { padding: '9px 11px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 },
}
