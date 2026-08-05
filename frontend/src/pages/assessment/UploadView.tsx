import { useState, useRef } from 'react'
import { Upload, Download, RefreshCw, CheckCircle, AlertCircle, FileText, Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import { uploadAssessmentQuestions, downloadAssessmentTemplate } from '../../api'
import { errorMessage } from '../../api/errors'

/** Rows shown before the list is cut. The full set stays in the download. */
const ROW_MSG_CAP = 25

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

interface UploadResult {
  dry_run: boolean
  stored: number
  stored_ids: string[]
  created: number
  created_ids: string[]
  updated: number
  updated_ids: string[]
  duplicates: number
  duplicate_warnings: string[]
  skipped: number
  errors: string[]
  specialty: string
  trainer: string
  timestamp: string
}

export function UploadView({ initialSpecialty }: { initialSpecialty?: string } = {}) {
  const [specialty, setSpecialty] = useState(initialSpecialty || 'ICD10CM')
  const [trainerName, setTrainerNameState] = useState(localStorage.getItem('trainer_name') || '')
  // Read from localStorage but never written back, so the name had to be
  // retyped on every visit — and an empty one blocks the upload.
  function setTrainerName(v: string) {
    setTrainerNameState(v)
    localStorage.setItem('trainer_name', v.trim())
  }
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleUpload(dryRun = false) {
    if (!trainerName.trim()) { toast.error('Enter your name before uploading'); return }
    if (!file) { toast.error('Select a file first'); return }
    setUploading(true)
    try {
      const data = await uploadAssessmentQuestions(specialty, trainerName.trim(), file, dryRun)
      setResult({
        dry_run: !!data.dry_run,
        stored: data.stored,
        stored_ids: data.stored_ids,
        created: data.created ?? data.stored,
        created_ids: data.created_ids ?? data.stored_ids,
        updated: data.updated ?? 0,
        updated_ids: data.updated_ids ?? [],
        duplicates: data.duplicates ?? 0,
        duplicate_warnings: data.duplicate_warnings ?? [],
        skipped: data.skipped,
        errors: data.errors || [],
        specialty,
        trainer: trainerName.trim(),
        timestamp: new Date().toLocaleString(),
      })
      if (dryRun) {
        // A preview must not clear the file — the next step is uploading it.
        toast(
          data.stored === 0
            ? 'Preview: nothing would be stored. See the details below.'
            : `Preview: ${data.created} new, ${data.updated} would be OVERWRITTEN. Nothing saved yet.`,
          { icon: '👀' },
        )
        return
      }
      // Nothing stored is not a success, however cleanly the request itself
      // completed. Reporting it green sent trainers away believing the bank
      // had grown, with the reasons sitting unread in the panel below.
      if (data.stored === 0) {
        const why = (data.errors || [])[0] || (data.duplicate_warnings || [])[0]
        toast.error(`No questions were stored${why ? ` — ${why}` : '. See the details below.'}`)
      } else if ((data.errors || []).length || (data.duplicates || 0)) {
        toast(`Stored ${data.stored}, but ${(data.errors || []).length} row(s) errored and ${data.duplicates || 0} were skipped as duplicates.`, { icon: '⚠️' })
      } else {
        toast.success(`Upload complete — ${data.stored} questions processed`)
      }
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Upload failed'))
    } finally {
      setUploading(false)
    }
  }

  function downloadSummary() {
    if (!result) return
    const lines = [
      result.dry_run ? `Upload PREVIEW (nothing was saved)` : `Upload Summary`,
      `==============`,
      `Trainer:   ${result.trainer}`,
      `Date/Time: ${result.timestamp}`,
      `Specialty: ${result.specialty}`,
      ``,
      `New questions created: ${result.created}`,
      `Questions updated:     ${result.updated}`,
      `Duplicates skipped:    ${result.duplicates}`,
      `Skipped (other):       ${result.skipped}`,
      `Errors:                ${result.errors.length}`,
      ...(result.created_ids.length ? [``, `New IDs:`, ...result.created_ids.map(id => `  ${id}`)] : []),
      ...(result.updated_ids.length ? [``, `Updated IDs:`, ...result.updated_ids.map(id => `  ${id}`)] : []),
      ...(result.duplicate_warnings.length ? [``, `Duplicate Warnings:`, ...result.duplicate_warnings.map(e => `  ${e}`)] : []),
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

          {/* Preview first. Uploading a sheet with existing Question_IDs
              overwrites those questions, and the only honest way to warn about
              that is to count the rows that would actually be replaced. */}
          <button
            style={{ ...s.btnOutline, opacity: uploading || !file ? 0.65 : 1 }}
            disabled={uploading || !file}
            title="Check what this file would do without saving anything"
            onClick={() => handleUpload(true)}
          >
            <Eye size={13} /> Preview
          </button>

          <button
            style={{ ...s.btnPrimary, opacity: uploading || !file ? 0.65 : 1 }}
            disabled={uploading || !file}
            onClick={() => handleUpload(false)}
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
              {result.dry_run
                ? <Eye size={18} color="#0369a1" />
                : <CheckCircle size={18} color="#16a34a" />}
              {/* A preview panel and a completed-upload panel look identical
                  otherwise, and mistaking one for the other means either
                  believing the bank grew when it did not, or uploading twice. */}
              <span style={s.cardTitle}>{result.dry_run ? 'Preview — nothing saved yet' : 'Upload Summary'}</span>
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
              <div style={{ fontSize: 26, fontWeight: 800, color: '#15803d' }}>{result.created}</div>
              <div style={{ fontSize: 11, color: '#166534', fontWeight: 600 }}>New Created</div>
            </div>
            <div style={{ ...s.statBox, background: '#ede9fe', borderColor: '#c4b5fd' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#5b21b6' }}>{result.updated}</div>
              <div style={{ fontSize: 11, color: '#4c1d95', fontWeight: 600 }}>Updated</div>
            </div>
            <div style={{ ...s.statBox, background: result.duplicates ? '#fef9c3' : '#f9fafb', borderColor: result.duplicates ? '#fde047' : '#e5e7eb' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: result.duplicates ? '#854d0e' : '#9ca3af' }}>{result.duplicates}</div>
              <div style={{ fontSize: 11, color: result.duplicates ? '#92400e' : '#9ca3af', fontWeight: 600 }}>Duplicates Skipped</div>
            </div>
            <div style={{ ...s.statBox, background: result.errors.length ? '#fee2e2' : '#f0fdf4', borderColor: result.errors.length ? '#fca5a5' : '#86efac' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: result.errors.length ? '#dc2626' : '#15803d' }}>{result.errors.length}</div>
              <div style={{ fontSize: 11, color: result.errors.length ? '#991b1b' : '#166534', fontWeight: 600 }}>Errors</div>
            </div>
          </div>

          {result.duplicate_warnings.length > 0 && (
            <div style={{ background: '#fefce8', border: '1px solid #fde047', borderRadius: 8, padding: '10px 14px', marginTop: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <AlertCircle size={13} color="#854d0e" />
                <span style={{ fontSize: 12, fontWeight: 700, color: '#854d0e' }}>Duplicate Questions Skipped</span>
              </div>
              {result.duplicate_warnings.slice(0, ROW_MSG_CAP).map((w, i) => (
                <div key={i} style={{ fontSize: 12, color: '#713f12', fontFamily: 'monospace', marginBottom: 2 }}>{w}</div>
              ))}
              {result.duplicate_warnings.length > ROW_MSG_CAP && (
                <div style={{ fontSize: 11, color: '#713f12', marginTop: 6, fontWeight: 700 }}>
                  … and {result.duplicate_warnings.length - ROW_MSG_CAP} more. Download the summary for the full list.
                </div>
              )}
            </div>
          )}

          {result.errors.length > 0 && (
            <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '10px 14px', marginTop: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <AlertCircle size={13} color="#c2410c" />
                <span style={{ fontSize: 12, fontWeight: 700, color: '#c2410c' }}>Row Errors</span>
              </div>
              {result.errors.slice(0, ROW_MSG_CAP).map((err, i) => (
                <div key={i} style={{ fontSize: 12, color: '#7c2d12', fontFamily: 'monospace', marginBottom: 2 }}>{err}</div>
              ))}
              {result.errors.length > ROW_MSG_CAP && (
                <div style={{ fontSize: 11, color: '#7c2d12', marginTop: 6, fontWeight: 700 }}>
                  … and {result.errors.length - ROW_MSG_CAP} more. Download the summary for the full list.
                </div>
              )}
            </div>
          )}

          {result.created_ids.length > 0 && (
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
              <strong style={{ color: '#15803d' }}>New:</strong> {result.created_ids.slice(0, 10).join(', ')}{result.created_ids.length > 10 ? ` … +${result.created_ids.length - 10} more` : ''}
            </div>
          )}
          {result.updated_ids.length > 0 && (
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
              <strong style={{ color: '#5b21b6' }}>Updated:</strong> {result.updated_ids.slice(0, 10).join(', ')}{result.updated_ids.length > 10 ? ` … +${result.updated_ids.length - 10} more` : ''}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  infoBox: { display: 'flex', gap: 10, background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: 10, padding: '12px 16px' },
  card: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', display: 'flex', flexDirection: 'column' as const, gap: 14, boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  resultCard: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', display: 'flex', flexDirection: 'column' as const, gap: 14, boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  cardTitle: { fontSize: 13, fontWeight: 800, color: '#374151', paddingLeft: 10, borderLeft: '3px solid #7c3aed' },
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
