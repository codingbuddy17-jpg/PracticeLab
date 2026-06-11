import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, CheckCircle, XCircle, ChevronLeft, BookOpen } from 'lucide-react'
import toast from 'react-hot-toast'
import { bulkUpload } from '../api'
import { RationaleEditor } from '../components/RationaleEditor'
import { useLocalStorage } from '../hooks/useLocalStorage'
import type { BulkUploadMeta, BulkUploadResult, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES, detectSpecialtyFromFilename } from '../types'

interface RowMeta extends BulkUploadMeta { file: File; complete: boolean }

export function TrainerUpload() {
  const navigate = useNavigate()
  const [trainerName, setTrainerName] = useLocalStorage<string>('trainer_name', '')
  const [rows, setRows] = useState<RowMeta[]>([])
  const [results, setResults] = useState<BulkUploadResult[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

  const isRowComplete = (r: Partial<RowMeta>) => !!(r.category?.trim() && r.specialty && r.difficulty)

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return
    const newRows: RowMeta[] = Array.from(files).map(file => {
      const specialty = detectSpecialtyFromFilename(file.name) ?? 'IP-DRG'
      const row: RowMeta = { file, uploaded_by: trainerName, specialty, category: '', difficulty: 'Beginner', rationale: '', complete: false }
      return row
    })
    setRows(prev => [...prev, ...newRows])
  }, [trainerName])

  const updateRow = (idx: number, key: keyof RowMeta, value: string) => {
    setRows(prev => prev.map((r, i) => {
      if (i !== idx) return r
      const updated = { ...r, [key]: value }
      return { ...updated, complete: isRowComplete(updated) }
    }))
  }

  const applyToAll = (key: keyof BulkUploadMeta, value: string) => {
    setRows(prev => prev.map(r => {
      const updated = { ...r, [key]: value }
      return { ...updated, complete: isRowComplete(updated) }
    }))
  }

  const removeRow = (idx: number) => setRows(prev => prev.filter((_, i) => i !== idx))

  const handleSubmit = async () => {
    if (!trainerName.trim()) { toast.error('Enter your name before uploading'); return }
    const incomplete = rows.findIndex(r => !r.category.trim())
    if (incomplete !== -1) { toast.error(`Row ${incomplete + 1}: category is required`); return }
    if (!window.confirm(`Upload ${rows.length} chart${rows.length !== 1 ? 's' : ''}? This cannot be undone.`)) return

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
              onClick={handleSubmit}
            >
              {uploading ? `Uploading...` : `Upload ${rows.length} Chart${rows.length !== 1 ? 's' : ''}`}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function PageHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div style={headerStyles.topBar}>
      <button style={headerStyles.backBtn} onClick={onBack}><ChevronLeft size={16} /> Back</button>
      <div style={headerStyles.logo}><BookOpen size={18} color="#4f46e5" /><span style={headerStyles.logoText}>Chart Viewer</span></div>
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
}
