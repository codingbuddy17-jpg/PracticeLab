import { useState, useRef } from 'react'
import { Upload, Download, RefreshCw, CheckCircle, AlertCircle, FileText } from 'lucide-react'
import toast from 'react-hot-toast'
import { uploadAssessmentQuestions, downloadAssessmentTemplate } from '../../api'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

interface UploadResult {
  stored: number
  stored_ids: string[]
  skipped: number
  errors: string[]
  specialty: string
  trainer: string
  timestamp: string
}

export function UploadView() {
  const [specialty, setSpecialty] = useState('ICD10CM')
  const [trainerName, setTrainerName] = useState(localStorage.getItem('trainer_name') || '')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleUpload() {
    if (!trainerName.trim()) { toast.error('Enter your name before uploading'); return }
    if (!file) { toast.error('Select a file first'); return }
    setUploading(true)
    try {
      const data = await uploadAssessmentQuestions(specialty, trainerName.trim(), file)
      // Detect how many were updates vs new
      setResult({
        stored: data.stored,
        stored_ids: data.stored_ids,
        skipped: data.skipped,
        errors: data.errors || [],
        specialty,
        trainer: trainerName.trim(),
        timestamp: new Date().toLocaleString(),
      })
      toast.success(`Upload complete — ${data.stored} questions processed`)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function downloadSummary() {
    if (!result) return
    const lines = [
      `Upload Summary`,
      `==============`,
      `Trainer:   ${result.trainer}`,
      `Date/Time: ${result.timestamp}`,
      `Specialty: ${result.specialty}`,
      ``,
      `Questions processed: ${result.stored}`,
      `Skipped (other):     ${result.skipped}`,
      `Errors:              ${result.errors.length}`,
      ``,
      `Question IDs uploaded:`,
      ...result.stored_ids.map(id => `  ${id}`),
      ...(result.errors.length ? [``, `Errors:`, ...result.errors.map(e => `  ${e}`)] : []),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `upload_summary_${result.specialty}_${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>

      {/* Instructions */}
      <div style={s.infoBox}>
        <FileText size={14} color="#4f46e5" style={{ flexShrink: 0, marginTop: 1 }} />
        <div style={{ fontSize: 13, color: '#3730a3', lineHeight: 1.6 }}>
          Download the template for your specialty, fill in questions, then upload here.
          Duplicate Question IDs are automatically detected and updated — no manual de-duplication needed.
          Each upload is attributed to you and logged in the audit trail.
        </div>
      </div>

      {/* Upload form */}
      <div style={s.card}>
        <div style={s.cardTitle}>Upload Questions</div>

        <div style={s.formGrid}>
          {/* Trainer name */}
          <div style={s.field}>
            <label style={s.label}>Your Name *</label>
            <input
              style={s.input}
              placeholder="Enter your name"
              value={trainerName}
              onChange={e => setTrainerName(e.target.value)}
            />
          </div>

          {/* Specialty */}
          <div style={s.field}>
            <label style={s.label}>Specialty *</label>
            <select style={s.input} value={specialty} onChange={e => setSpecialty(e.target.value)}>
              {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
            </select>
          </div>
        </div>

        {/* Template + file */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'center', marginTop: 8 }}>
          <button style={s.btnOutline} onClick={() => downloadAssessmentTemplate(specialty)}>
            <Download size={13} /> Download Template
          </button>

          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
            onChange={e => { setFile(e.target.files?.[0] || null); setResult(null) }} />
          <button style={s.btnOutline} onClick={() => fileRef.current?.click()}>
            <Upload size={13} />
            {file ? file.name : 'Choose File (.xlsx)'}
          </button>

          <button
            style={{ ...s.btnPrimary, opacity: uploading || !file ? 0.65 : 1 }}
            disabled={uploading || !file}
            onClick={handleUpload}
          >
            {uploading
              ? <><RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} /> Uploading…</>
              : <><Upload size={13} /> Upload</>}
          </button>

          {file && !uploading && (
            <button style={s.btnCancel} onClick={() => { setFile(null); setResult(null); if (fileRef.current) fileRef.current.value = '' }}>
              ✕ Cancel
            </button>
          )}
        </div>
      </div>

      {/* Upload result summary */}
      {result && (
        <div style={s.resultCard}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <CheckCircle size={18} color="#16a34a" />
              <span style={s.cardTitle}>Upload Summary</span>
            </div>
            <button style={s.btnOutline} onClick={downloadSummary}>
              <Download size={13} /> Download Summary
            </button>
          </div>

          <div style={s.summaryMeta}>
            <span><strong>Trainer:</strong> {result.trainer}</span>
            <span><strong>Specialty:</strong> {result.specialty}</span>
            <span><strong>Date/Time:</strong> {result.timestamp}</span>
          </div>

          <div style={s.statRow}>
            <div style={{ ...s.statBox, background: '#dcfce7', borderColor: '#86efac' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#15803d' }}>{result.stored}</div>
              <div style={{ fontSize: 11, color: '#166534', fontWeight: 600 }}>Questions Processed</div>
            </div>
            <div style={{ ...s.statBox, background: '#fef9c3', borderColor: '#fde047' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#854d0e' }}>{result.skipped}</div>
              <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600 }}>Skipped</div>
            </div>
            <div style={{ ...s.statBox, background: result.errors.length ? '#fee2e2' : '#f0fdf4', borderColor: result.errors.length ? '#fca5a5' : '#86efac' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: result.errors.length ? '#dc2626' : '#15803d' }}>{result.errors.length}</div>
              <div style={{ fontSize: 11, color: result.errors.length ? '#991b1b' : '#166534', fontWeight: 600 }}>Errors</div>
            </div>
          </div>

          {result.errors.length > 0 && (
            <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '10px 14px', marginTop: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <AlertCircle size={13} color="#c2410c" />
                <span style={{ fontSize: 12, fontWeight: 700, color: '#c2410c' }}>Row Errors</span>
              </div>
              {result.errors.map((err, i) => (
                <div key={i} style={{ fontSize: 12, color: '#7c2d12', fontFamily: 'monospace', marginBottom: 2 }}>{err}</div>
              ))}
            </div>
          )}

          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
            {result.stored_ids.length} IDs: {result.stored_ids.slice(0, 12).join(', ')}{result.stored_ids.length > 12 ? ` … +${result.stored_ids.length - 12} more` : ''}
          </div>
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  infoBox: { display: 'flex', gap: 10, background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: 10, padding: '12px 16px' },
  card: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 14, padding: '20px 22px', display: 'flex', flexDirection: 'column' as const, gap: 14 },
  resultCard: { background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 14, padding: '20px 22px', display: 'flex', flexDirection: 'column' as const, gap: 14 },
  cardTitle: { fontSize: 13, fontWeight: 800, color: '#374151' },
  formGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  field: { display: 'flex', flexDirection: 'column' as const, gap: 5 },
  label: { fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  input: { padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, fontFamily: 'inherit', background: '#fff' },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  btnPrimary: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 18px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  btnCancel: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', border: '1px solid #fca5a5', borderRadius: 8, background: '#fff1f2', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#dc2626' },
  summaryMeta: { display: 'flex', gap: 20, fontSize: 13, color: '#6b7280', flexWrap: 'wrap' as const },
  statRow: { display: 'flex', gap: 12 },
  statBox: { flex: 1, border: '1px solid', borderRadius: 10, padding: '14px 18px', textAlign: 'center' as const },
}
