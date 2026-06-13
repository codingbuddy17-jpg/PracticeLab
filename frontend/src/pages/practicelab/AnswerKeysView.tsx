import { useState, useEffect, useRef } from 'react'
import { Download, Upload, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAnswerKeyStatus, downloadAnswerKeyTemplate, uploadAnswerKeys } from '../../api'
import { trainerName, SPECIALTIES } from './shared'
import styles from './styles'

export function AnswerKeysView() {
  const [status, setStatus] = useState<any>(null)
  const [specialty, setSpecialty] = useState('IP-DRG')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadStatus() }, [specialty])

  async function loadStatus() {
    try { setStatus(await getAnswerKeyStatus(specialty)) } catch { toast.error('Could not load answer key status') }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const isIP = specialty === 'IP-DRG'
      const res = await uploadAnswerKeys(file, isIP ? 'IP' : 'OP', trainerName())
      if (res.stored.length) toast.success(`Stored: ${res.stored.join(', ')}`)
      if (res.skipped_duplicates.length) toast(`Skipped (already exist): ${res.skipped_duplicates.join(', ')}`, { icon: '⚠️' })
      if (res.not_found.length) toast.error(`Chart numbers not found: ${res.not_found.join(', ')}`)
      loadStatus()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const isIP = specialty === 'IP-DRG'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Answer Keys</span>
      </div>
      <p style={styles.helpText}>
        Answer keys are stored permanently per chart. Once stored, only a master admin can delete them.
        Keys are reused across all batches automatically.
      </p>

      <div>
        <label style={styles.label}>Specialty type</label>
        <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value)}>
          {SPECIALTIES.map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {status && (
        <div style={styles.statsRow}>
          <div style={styles.statCard}>
            <div style={styles.statValue}>{status.total_charts}</div>
            <div style={styles.statLabel}>Total Charts</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: '#16a34a' }}>{status.with_answer_key}</div>
            <div style={styles.statLabel}>Have Answer Key</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: '#dc2626' }}>{status.without_answer_key}</div>
            <div style={styles.statLabel}>Missing Key</div>
          </div>
        </div>
      )}

      <div style={styles.actionRow}>
        <button style={styles.outlineBtn} onClick={() => downloadAnswerKeyTemplate(isIP ? 'IP' : 'OP')}>
          <Download size={15} /> Download Blank Template ({isIP ? 'IP' : 'OP'})
        </button>
        <label style={uploading ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
          {uploading ? <><Loader size={14} /> Uploading...</> : <><Upload size={15} /> Upload Filled Key</>}
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleUpload} disabled={uploading} />
        </label>
      </div>

      <div style={styles.infoBox}>
        <strong>How it works:</strong>
        <ol style={{ margin: '8px 0 0 0', paddingLeft: 20, lineHeight: 1.8, fontSize: 13 }}>
          <li>Download the blank template for your specialty type</li>
          <li>Fill one row per chart — Chart_Number must match exactly what's in PracticeLab</li>
          <li>Upload the filled template — keys are stored permanently</li>
          <li>Duplicate chart numbers are skipped with a warning</li>
        </ol>
      </div>
    </div>
  )
}
