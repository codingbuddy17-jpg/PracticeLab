import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, CheckCircle, XCircle, ChevronLeft, BookOpen, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { bulkUpload, previewChartNumbers } from '../api'
import { RationaleEditor } from '../components/RationaleEditor'
import { useLocalStorage } from '../hooks/useLocalStorage'
import type { BulkUploadMeta, BulkUploadResult, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES, detectSpecialtyFromFilename } from '../types'

const ALLOWED_TYPES = new Set([
  'application/pdf', 'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/png', 'image/jpeg', 'image/tiff',
])
const ALLOWED_EXTS = /\.(pdf|doc|docx|png|jpg|jpeg|tiff?|tif)$/i

interface RowMeta extends BulkUploadMeta { file: File; complete: boolean; specialtyMismatch?: boolean }

export function TrainerUpload() {
  const navigate = useNavigate()
  const [trainerName, setTrainerName] = useLocalStorage<string>('trainer_name', '')
  const [rows, setRows] = useState<RowMeta[]>([])
  const [results, setResults] = useState<BulkUploadResult[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [preview, setPreview] = useState<{ filename: string; specialty: string; assigned_number: string }[]>([])
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const isRowComplete = (r: Partial<RowMeta>) => !!(r.category?.trim() && r.specialty && r.difficulty)

  const refreshPreview = async (updatedRows: RowMeta[]) => {
    if (updatedRows.length === 0) { setPreview([]); return }
    setLoadingPreview(true)
    try {
      const items = updatedRows.map(r => ({ filename: r.file.name, specialty: r.specialty }))
      const res = await previewChartNumbers(items)
      setPreview(res)
    } catch { toast.error('Could not load chart number preview') }
    finally { setLoadingPreview(false) }
  }

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return
    const existingNames = new Set(rows.map(r => r.file.name))
    const rejected: string[] = []
    const duplicates: string[] = []
    const newRows: RowMeta[] = []

    for (const file of Array.from(files)) {
      if (!ALLOWED_TYPES.has(file.type) && !ALLOWED_EXTS.test(file.name)) {
        rejected.push(file.name); continue
      }
      if (existingNames.has(file.name)) {
        duplicates.push(file.name); continue
      }
      existingNames.add(file.name)
      const detected = detectSpecialtyFromFilename(file.name)
      const specialty: Specialty = detected ?? 'IP-DRG'
      newRows.push({ file, uploaded_by: trainerName, specialty, category: '', difficulty: 'Beginner', rationale: '', complete: false, specialtyMismatch: false })
    }

    if (rejected.length) toast.error(`${rejected.length} file${rejected.length > 1 ? 's' : ''} skipped — unsupported type: ${rejected.join(', ')}`, { duration: 6000 })
    if (duplicates.length) toast.error(`${duplicates.length} duplicate${duplicates.length > 1 ? 's' : ''} skipped: ${duplicates.join(', ')}`, { duration: 5000 })

    const updated = [...rows, ...newRows]
    setRows(updated)
    refreshPreview(updated)
  }, [trainerName, rows])

  const checkMismatch = (file: File, specialty: string) => {
    const detected = detectSpecialtyFromFilename(file.name)
    return detected !== null && detected !== specialty
  }

  const updateRow = (idx: number, key: keyof RowMeta, value: string) => {
    setRows(prev => {
      const next = prev.map((r, i) => {
        if (i !== idx) return r
        const updated = { ...r, [key]: value }
        const mismatch = key === 'specialty' ? checkMismatch(r.file, value) : r.specialtyMismatch
        return { ...updated, complete: isRowComplete(updated), specialtyMismatch: mismatch }
      })
      if (key === 'specialty') refreshPreview(next)
      return next
    })
  }

  const applyToAll = (key: keyof BulkUploadMeta, value: string) => {
    setRows(prev => {
      const next = prev.map(r => {
        const updated = { ...r, [key]: value }
        return { ...updated, complete: isRowComplete(updated) }
      })
      if (key === 'specialty') refreshPreview(next)
      return next
    })
  }

  const removeRow = (idx: number) => {
    setRows(prev => {
      const next = prev.filter((_, i) => i !== idx)
      refreshPreview(next)
      return next
    })
  }

  const handleSubmitClick = () => {
    if (!trainerName.trim()) { toast.error('Enter your name before uploading'); return }
    const incomplete = rows.findIndex(r => !r.category.trim())
    if (incomplete !== -1) { toast.error(`Row ${incomplete + 1}: category is required`); return }
    setConfirmOpen(true)
  }

  const handleSubmit = async () => {
    setConfirmOpen(false)
    setUploading(true)
    setUploadProgress(0)

    try {
      const meta: BulkUploadMeta[] = rows.map(r => ({
        uploaded_by: trainerName,
        specialty: r.specialty,
        category: r.category,
        difficulty: r.difficulty,
        rationale: r.rationale,
      }))

      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress(p => Math.min(p + 8, 90))
      }, 400)

      const res = await bulkUpload(rows.map(r => r.file), meta)
      clearInterval(progressInterval)
      setUploadProgress(100)

      setTimeout(() => {
        setResults(res)
        const success = res.filter(r => r.status === 'success').length
        toast.success(`${success} of ${res.length} charts uploaded`)
      }, 400)
    } catch {
      toast.error('Upload failed. Check connection.')
    } finally {
      setUploading(false)
    }
  }

  if (results) {
    const success = results.filter(r => r.status === 'success')
    const errors = results.filter(r => r.status === 'error')
    return (
      <div style={styles.container}>
        <PageHeader title="Upload Results" onBack={() => navigate('/trainer')} />
        <div style={styles.resultsWrap}>
          <div style={styles.resultsSummary}>
            <div style={{ ...styles.summaryChip, background: '#dcfce7', color: '#16a34a' }}>
              <CheckCircle size={16} /> {success.length} Uploaded
            </div>
            {errors.length > 0 && (
              <div style={{ ...styles.summaryChip, background: '#fee2e2', color: '#dc2626' }}>
                <XCircle size={16} /> {errors.length} Failed
              </div>
            )}
          </div>
          {results.map((r, i) => (
            <div key={i} style={{ ...styles.resultRow, borderLeft: `4px solid ${r.status === 'success' ? '#22c55e' : '#ef4444'}` }}>
              {r.status === 'success' ? <CheckCircle size={18} color="#16a34a" /> : <XCircle size={18} color="#dc2626" />}
              <div>
                <div style={styles.resultFilename}>{r.filename}</div>
                <div style={styles.resultMsg}>{r.message}</div>
              </div>
            </div>
          ))}
          <button style={styles.primaryBtn} onClick={() => { setRows([]); setResults(null); setUploadProgress(0) }}>Upload More</button>
        </div>
      </div>
    )
  }

  const completeCount = rows.filter(r => r.complete).length

  return (
    <div style={styles.container}>
      <PageHeader title="Upload Charts" onBack={() => navigate('/trainer')} />
      <div style={styles.content}>
        <div style={styles.nameRow}>
          <label style={styles.label}>Your Name</label>
          <input style={styles.input} placeholder="Trainer name" value={trainerName} onChange={e => setTrainerName(e.target.value)} />
        </div>

        <div
          style={styles.dropzone}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
          onClick={() => document.getElementById('fileInput')?.click()}
        >
          <div style={styles.dropIconWrap}><Upload size={28} color="#4f46e5" /></div>
          <div style={styles.dropText}>Drop chart files here or click to browse</div>
          <div style={styles.dropSub}>PDF, Word, PNG, JPG · Name files as IP001.pdf, ED002.pdf etc.</div>
          <input id="fileInput" type="file" multiple accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff,.tif" style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
        </div>

        {rows.length > 0 && (
          <>
            {/* Chart number preview */}
            <div style={styles.previewBox}>
              <div style={styles.previewHeader}>
                📋 Chart numbers that will be assigned
                {loadingPreview && <span style={styles.previewLoading}> — updating...</span>}
              </div>
              <div style={styles.previewNote}>Share these with your team before uploading so answer keys are aligned.</div>
              <div style={styles.previewTable}>
                <div style={styles.previewRowHeader}>
                  <span>File</span><span>Specialty</span><span>Assigned Number</span>
                </div>
                {preview.length > 0 ? preview.map((p, i) => (
                  <div key={i} style={styles.previewRow}>
                    <span style={styles.previewFilename}>{p.filename}</span>
                    <span style={styles.previewSpecialty}>{p.specialty}</span>
                    <span style={styles.previewNumber}>{p.assigned_number}</span>
                  </div>
                )) : rows.map((r, i) => (
                  <div key={i} style={styles.previewRow}>
                    <span style={styles.previewFilename}>{r.file.name}</span>
                    <span style={styles.previewSpecialty}>{r.specialty}</span>
                    <span style={{ ...styles.previewNumber, color: '#9ca3af' }}>Loading...</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={styles.applyAllRow}>
              <span style={styles.applyLabel}>Apply to all:</span>
              <select style={styles.select} onChange={e => e.target.value && applyToAll('difficulty', e.target.value)} defaultValue="">
                <option value="" disabled>Difficulty</option>
                {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
              <select style={styles.select} onChange={e => e.target.value && applyToAll('specialty', e.target.value)} defaultValue="">
                <option value="" disabled>Specialty</option>
                {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <span style={styles.progressLabel}>{completeCount}/{rows.length} ready</span>
            </div>

            <div style={styles.tableWrap}>
              {rows.map((row, idx) => (
                <div key={idx} style={{ ...styles.rowCard, borderLeft: `4px solid ${row.complete ? '#22c55e' : '#e5e7eb'}` }}>
                  <div style={styles.rowHeader}>
                    <div style={styles.rowFileInfo}>
                      <span style={row.complete ? styles.rowFilenameComplete : styles.rowFilename}>{row.file.name}</span>
                      {row.complete && <CheckCircle size={14} color="#22c55e" />}
                      {row.specialtyMismatch && (
                        <span style={styles.mismatchBadge} title="Filename prefix suggests a different specialty">
                          <AlertTriangle size={12} /> Specialty mismatch
                        </span>
                      )}
                    </div>
                    <button style={styles.removeBtn} onClick={() => removeRow(idx)}>✕</button>
                  </div>
                  <div style={styles.rowFields}>
                    <div style={styles.field}>
                      <label style={styles.label}>Specialty</label>
                      <select style={styles.select} value={row.specialty} onChange={e => updateRow(idx, 'specialty', e.target.value)}>
                        {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div style={styles.field}>
                      <label style={styles.label}>Category *</label>
                      <input style={styles.input} value={row.category} onChange={e => updateRow(idx, 'category', e.target.value)} placeholder="e.g. Sepsis" />
                    </div>
                    <div style={styles.field}>
                      <label style={styles.label}>Difficulty</label>
                      <select style={styles.select} value={row.difficulty} onChange={e => updateRow(idx, 'difficulty', e.target.value)}>
                        {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
                      </select>
                    </div>
                  </div>
                  <div style={styles.field}>
                    <label style={styles.label}>Rationale (trainer only)</label>
                    <RationaleEditor content={row.rationale ?? ''} onChange={v => updateRow(idx, 'rationale', v)} />
                  </div>
                </div>
              ))}
            </div>

            {uploading && (
              <div style={styles.progressWrap}>
                <div style={styles.progressBar}>
                  <div style={{ ...styles.progressFill, width: `${uploadProgress}%` }} />
                </div>
                <span style={styles.progressText}>Uploading... {uploadProgress}%</span>
              </div>
            )}

            <button
              style={{ ...styles.primaryBtn, opacity: uploading ? 0.7 : 1 }}
              disabled={uploading}
              onClick={handleSubmitClick}
            >
              {uploading ? `Uploading...` : `Upload ${rows.length} Chart${rows.length !== 1 ? 's' : ''}`}
            </button>
          </>
        )}
      </div>

      {confirmOpen && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalBox}>
            <div style={styles.modalTitle}>Confirm Upload</div>
            <div style={styles.modalBody}>
              Upload <strong>{rows.length} chart{rows.length !== 1 ? 's' : ''}</strong>? Chart numbers will be assigned automatically and cannot be changed after upload.
              {rows.some(r => r.specialtyMismatch) && (
                <div style={styles.modalWarn}>
                  <AlertTriangle size={14} /> Some files have specialty mismatches — verify before continuing.
                </div>
              )}
            </div>
            <div style={styles.modalActions}>
              <button style={styles.cancelBtn} onClick={() => setConfirmOpen(false)}>Cancel</button>
              <button style={styles.primaryBtn} onClick={handleSubmit}>Confirm Upload</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
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

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  content: { maxWidth: 900, margin: '0 auto', padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 20 },
  nameRow: { display: 'flex', flexDirection: 'column', gap: 5, maxWidth: 320 },
  dropzone: { border: '2px dashed #c7d2fe', borderRadius: 12, padding: '40px 24px', textAlign: 'center', cursor: 'pointer', background: '#fafafe', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, transition: 'border-color 0.15s' },
  dropIconWrap: { background: '#ede9fe', borderRadius: '50%', padding: 14, display: 'flex' },
  dropText: { fontWeight: 700, fontSize: 15, color: '#374151' },
  dropSub: { fontSize: 12, color: '#9ca3af' },
  applyAllRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#ede9fe', borderRadius: 8 },
  applyLabel: { fontSize: 13, fontWeight: 700, color: '#4f46e5' },
  progressLabel: { marginLeft: 'auto', fontSize: 13, color: '#374151', fontWeight: 600 },
  tableWrap: { display: 'flex', flexDirection: 'column', gap: 14 },
  rowCard: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: 18, display: 'flex', flexDirection: 'column', gap: 14, transition: 'border-color 0.2s' },
  rowHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  rowFileInfo: { display: 'flex', alignItems: 'center', gap: 8 },
  rowFilename: { fontWeight: 600, fontSize: 14, color: '#374151' },
  rowFilenameComplete: { fontWeight: 600, fontSize: 14, color: '#16a34a' },
  removeBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 16, padding: '2px 6px' },
  rowFields: { display: 'flex', gap: 12, flexWrap: 'wrap' as const },
  field: { display: 'flex', flexDirection: 'column', gap: 5, flex: 1, minWidth: 160 },
  label: { fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.6 },
  input: { padding: '9px 11px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 },
  select: { padding: '9px 11px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, background: '#fff' },
  primaryBtn: { padding: '12px 28px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, alignSelf: 'flex-start' },
  previewBox: { background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 10, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 },
  previewHeader: { fontWeight: 700, fontSize: 14, color: '#15803d', display: 'flex', alignItems: 'center', gap: 6 },
  previewLoading: { fontWeight: 400, fontSize: 12, color: '#6b7280' },
  previewNote: { fontSize: 12, color: '#16a34a' },
  previewTable: { display: 'flex', flexDirection: 'column', gap: 0, border: '1px solid #bbf7d0', borderRadius: 7, overflow: 'hidden', background: '#fff' },
  previewRowHeader: { display: 'grid', gridTemplateColumns: '1fr 140px 140px', padding: '7px 12px', background: '#f0fdf4', fontSize: 11, fontWeight: 700, color: '#15803d', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #bbf7d0' },
  previewRow: { display: 'grid', gridTemplateColumns: '1fr 140px 140px', padding: '8px 12px', borderBottom: '1px solid #f0fdf4', fontSize: 13, alignItems: 'center' },
  previewFilename: { color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  previewSpecialty: { color: '#6b7280', fontSize: 12 },
  previewNumber: { fontWeight: 800, color: '#15803d', fontSize: 15, letterSpacing: -0.3 },
  progressWrap: { display: 'flex', flexDirection: 'column', gap: 6 },
  progressBar: { height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: '100%', background: '#4f46e5', borderRadius: 3, transition: 'width 0.4s ease' },
  progressText: { fontSize: 12, color: '#6b7280' },
  resultsWrap: { maxWidth: 700, margin: '0 auto', padding: 28, display: 'flex', flexDirection: 'column', gap: 12 },
  resultsSummary: { display: 'flex', gap: 10, marginBottom: 8 },
  summaryChip: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 20, fontSize: 13, fontWeight: 700 },
  resultRow: { display: 'flex', gap: 12, alignItems: 'flex-start', padding: '12px 16px', border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff' },
  resultFilename: { fontWeight: 600, fontSize: 13 },
  resultMsg: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  mismatchBadge: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 700, color: '#b45309', background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 12, padding: '2px 8px' },
  modalOverlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 },
  modalBox: { background: '#fff', borderRadius: 12, padding: 28, maxWidth: 420, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', display: 'flex', flexDirection: 'column', gap: 16 },
  modalTitle: { fontWeight: 800, fontSize: 17, color: '#111' },
  modalBody: { fontSize: 14, color: '#374151', lineHeight: 1.6 },
  modalWarn: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, fontSize: 13, color: '#b45309', background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 8, padding: '8px 12px' },
  modalActions: { display: 'flex', gap: 10, justifyContent: 'flex-end' },
  cancelBtn: { padding: '9px 20px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, cursor: 'pointer', fontWeight: 600, fontSize: 13, color: '#374151' },
}
