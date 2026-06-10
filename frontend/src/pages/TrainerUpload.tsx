import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, CheckCircle, XCircle, ChevronLeft } from 'lucide-react'
import toast from 'react-hot-toast'
import { bulkUpload } from '../api'
import { RationaleEditor } from '../components/RationaleEditor'
import type { BulkUploadMeta, BulkUploadResult, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES, detectSpecialtyFromFilename } from '../types'

interface RowMeta extends BulkUploadMeta {
  file: File
}

export function TrainerUpload() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<RowMeta[]>([])
  const [results, setResults] = useState<BulkUploadResult[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [trainerName, setTrainerName] = useState('')

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return
    const newRows: RowMeta[] = Array.from(files).map(file => ({
      file,
      uploaded_by: trainerName,
      specialty: detectSpecialtyFromFilename(file.name) ?? 'IP-DRG',
      category: '',
      difficulty: 'Beginner',
      rationale: '',
    }))
    setRows(prev => [...prev, ...newRows])
  }, [trainerName])

  const updateRow = (idx: number, key: keyof RowMeta, value: string) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [key]: value } : r))
  }

  const applyToAll = (key: keyof BulkUploadMeta, value: string) => {
    setRows(prev => prev.map(r => ({ ...r, [key]: value })))
  }

  const removeRow = (idx: number) => setRows(prev => prev.filter((_, i) => i !== idx))

  const handleSubmit = async () => {
    if (!trainerName.trim()) { toast.error('Enter your name before uploading'); return }
    const invalid = rows.findIndex(r => !r.category.trim())
    if (invalid !== -1) { toast.error(`Row ${invalid + 1}: category is required`); return }

    setUploading(true)
    try {
      const meta: BulkUploadMeta[] = rows.map(r => ({
        uploaded_by: trainerName,
        specialty: r.specialty,
        category: r.category,
        difficulty: r.difficulty,
        rationale: r.rationale,
      }))
      const res = await bulkUpload(rows.map(r => r.file), meta)
      setResults(res)
      const success = res.filter(r => r.status === 'success').length
      toast.success(`${success} of ${res.length} charts uploaded`)
    } catch {
      toast.error('Upload failed. Check connection.')
    } finally {
      setUploading(false)
    }
  }

  if (results) {
    return (
      <div style={styles.container}>
        <div style={styles.topBar}>
          <button style={styles.backBtn} onClick={() => navigate('/trainer')}><ChevronLeft size={16} /> Back</button>
          <span style={styles.title}>Upload Results</span>
        </div>
        <div style={styles.resultsWrap}>
          {results.map((r, i) => (
            <div key={i} style={{ ...styles.resultRow, borderColor: r.status === 'success' ? '#86efac' : '#fca5a5' }}>
              {r.status === 'success' ? <CheckCircle size={18} color="#16a34a" /> : <XCircle size={18} color="#dc2626" />}
              <div>
                <div style={styles.resultFilename}>{r.filename}</div>
                <div style={styles.resultMsg}>{r.message}</div>
              </div>
            </div>
          ))}
          <button style={styles.primaryBtn} onClick={() => { setRows([]); setResults(null) }}>Upload More</button>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={() => navigate('/trainer')}><ChevronLeft size={16} /> Back</button>
        <span style={styles.title}>Upload Charts</span>
      </div>

      <div style={styles.content}>
        <div style={styles.nameRow}>
          <label style={styles.label}>Your Name</label>
          <input
            style={styles.input}
            placeholder="Trainer name"
            value={trainerName}
            onChange={e => setTrainerName(e.target.value)}
          />
        </div>

        {/* Drop zone */}
        <div
          style={styles.dropzone}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
          onClick={() => document.getElementById('fileInput')?.click()}
        >
          <Upload size={32} color="#9ca3af" />
          <div style={styles.dropText}>Drop chart files here or click to browse</div>
          <div style={styles.dropSub}>PDF, Word, PNG, JPG supported. Name files as IP001.pdf, ED002.pdf etc.</div>
          <input
            id="fileInput"
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff,.tif"
            style={{ display: 'none' }}
            onChange={e => handleFiles(e.target.files)}
          />
        </div>

        {rows.length > 0 && (
          <>
            {/* Apply to all strip */}
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
            </div>

            {/* Per-row table */}
            <div style={styles.tableWrap}>
              {rows.map((row, idx) => (
                <div key={idx} style={styles.rowCard}>
                  <div style={styles.rowHeader}>
                    <span style={styles.rowFilename}>{row.file.name}</span>
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

            <button style={{ ...styles.primaryBtn, opacity: uploading ? 0.6 : 1 }} disabled={uploading} onClick={handleSubmit}>
              {uploading ? 'Uploading...' : `Upload ${rows.length} Chart${rows.length !== 1 ? 's' : ''}`}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '6px 12px', cursor: 'pointer', fontSize: 13 },
  title: { fontWeight: 700, fontSize: 18 },
  content: { maxWidth: 900, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 20 },
  nameRow: { display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 300 },
  dropzone: { border: '2px dashed #d1d5db', borderRadius: 8, padding: '40px 24px', textAlign: 'center', cursor: 'pointer', background: '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 },
  dropText: { fontWeight: 600, fontSize: 15, color: '#374151' },
  dropSub: { fontSize: 12, color: '#9ca3af' },
  applyAllRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: '#ede9fe', borderRadius: 6 },
  applyLabel: { fontSize: 13, fontWeight: 600, color: '#4f46e5' },
  tableWrap: { display: 'flex', flexDirection: 'column', gap: 12 },
  rowCard: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 },
  rowHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  rowFilename: { fontWeight: 600, fontSize: 14, color: '#374151' },
  removeBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 16 },
  rowFields: { display: 'flex', gap: 12, flexWrap: 'wrap' },
  field: { display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 160 },
  label: { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5 },
  input: { padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 },
  select: { padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, background: '#fff' },
  primaryBtn: { padding: '12px 24px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14, alignSelf: 'flex-start' },
  resultsWrap: { maxWidth: 700, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 12 },
  resultRow: { display: 'flex', gap: 12, alignItems: 'flex-start', padding: 12, border: '1px solid', borderRadius: 6, background: '#fff' },
  resultFilename: { fontWeight: 600, fontSize: 13 },
  resultMsg: { fontSize: 12, color: '#6b7280' },
}
