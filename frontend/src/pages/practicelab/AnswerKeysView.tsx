import { useState, useEffect, useRef } from 'react'
import { Download, Upload, Loader, Trash2, X, AlertTriangle, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getAnswerKeyStatus, getAnswerKeyList, getChartsMissingKeys,
  downloadAnswerKeyTemplate, uploadAnswerKeys, deleteAnswerKey, purgeChart,
  downloadAnswerKeyExport,
} from '../../api'
import { trainerName, SPECIALTIES } from './shared'
import styles from './styles'

interface AKRow {
  chart_id: number
  chart_number: string
  specialty: string
  category: string
  entered_by: string
  created_at: string | null
}

interface PassphraseDialog {
  mode: 'delete-ak' | 'purge-chart'
  chartId: number
  chartNumber: string
}

export function AnswerKeysView() {
  const [status, setStatus] = useState<any>(null)
  const [specialty, setSpecialty] = useState('IP-DRG')
  const [uploading, setUploading] = useState(false)
  const [akList, setAkList] = useState<AKRow[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [dialog, setDialog] = useState<PassphraseDialog | null>(null)
  const [passphrase, setPassphrase] = useState('')
  const [acting, setActing] = useState(false)
  const [pendingCharts, setPendingCharts] = useState<string[]>([])
  const [replaceMode, setReplaceMode] = useState(false)
  const [exportPassphrase, setExportPassphrase] = useState('')
  const [showExportPrompt, setShowExportPrompt] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const replaceRef = useRef<HTMLInputElement>(null)
  const ppRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadAll() }, [specialty])
  useEffect(() => { if (dialog) setTimeout(() => ppRef.current?.focus(), 50) }, [dialog])

  async function loadAll() {
    try { setStatus(await getAnswerKeyStatus(specialty)) } catch { toast.error('Could not load status') }
    setListLoading(true)
    try { setAkList(await getAnswerKeyList(specialty)) } catch { toast.error('Could not load answer key list') }
    finally { setListLoading(false) }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>, pp?: string) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const isIP = specialty === 'IP-DRG'
      const res = await uploadAnswerKeys(file, isIP ? 'IP' : 'OP', trainerName(), replaceMode, pp || '')
      if (res.stored.length) toast.success(`Saved ${res.stored.length} new key${res.stored.length !== 1 ? 's' : ''}`)
      if (res.replaced?.length) toast.success(`Replaced ${res.replaced.length} existing key${res.replaced.length !== 1 ? 's' : ''}`)
      if (res.skipped_duplicates.length) toast(`Already exist, skipped ${res.skipped_duplicates.length} (use Replace mode to overwrite)`, { icon: 'ℹ️' })
      if (res.not_found.length) setPendingCharts(res.not_found)
      if (!res.stored.length && !res.replaced?.length && !res.skipped_duplicates.length && !res.not_found.length) {
        toast.error('No usable rows found in this file — check that it has data below the header row')
      }
      setReplaceMode(false)
      loadAll()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
      if (replaceRef.current) replaceRef.current.value = ''
    }
  }

  function handleExport() {
    if (!exportPassphrase.trim()) { toast.error('Enter the master passphrase'); return }
    downloadAnswerKeyExport(exportPassphrase.trim(), specialty !== 'All' ? specialty : undefined)
    setShowExportPrompt(false)
    setExportPassphrase('')
  }

  function openDialog(mode: PassphraseDialog['mode'], chartId: number, chartNumber: string) {
    setPassphrase('')
    setDialog({ mode, chartId, chartNumber })
  }

  async function confirmAction() {
    if (!dialog || !passphrase.trim()) return
    setActing(true)
    try {
      if (dialog.mode === 'delete-ak') {
        await deleteAnswerKey(dialog.chartId, passphrase)
        toast.success(`Answer key for ${dialog.chartNumber} deleted`)
      } else {
        await purgeChart(dialog.chartId, passphrase)
        toast.success(`Chart ${dialog.chartNumber} permanently deleted`)
      }
      setDialog(null)
      loadAll()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Action failed — check passphrase')
    } finally {
      setActing(false)
    }
  }

  const isIP = specialty === 'IP-DRG'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Answer Keys</span>
      </div>
      <p style={styles.helpText}>
        Answer keys are stored permanently per chart and reused across all batches automatically.
        Charts must be uploaded first — answer keys are linked by system-assigned chart numbers.
        Deleting a key requires the master passphrase and allows re-uploading a corrected version.
      </p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 20 }}>
        <div>
          <label style={styles.label}>Specialty type</label>
          <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value)}>
            {SPECIALTIES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <button style={styles.outlineBtn} onClick={() => downloadAnswerKeyTemplate(isIP ? 'IP' : 'OP')}>
          <Download size={15} /> Blank Template
        </button>
        <button style={{ ...styles.outlineBtn, color: '#16a34a', borderColor: '#86efac' }} onClick={() => setShowExportPrompt(s => !s)}>
          <Download size={15} /> Export All Keys
        </button>
        <label style={uploading ? { ...styles.primaryBtn, opacity: 0.6 } : replaceMode ? { ...styles.primaryBtn, background: '#dc2626', borderColor: '#dc2626' } : styles.primaryBtn}>
          {uploading ? <><Loader size={14} /> Uploading...</> : replaceMode ? <><RefreshCw size={15} /> Upload & Replace</> : <><Upload size={15} /> Upload Filled Key</>}
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={e => handleUpload(e, replaceRef.current?.value || '')} disabled={uploading} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6b7280', cursor: 'pointer', userSelect: 'none' as const }}>
          <input type="checkbox" checked={replaceMode} onChange={e => setReplaceMode(e.target.checked)} />
          Replace existing
        </label>
      </div>

      {/* Replace mode passphrase prompt */}
      {replaceMode && (
        <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
          <AlertTriangle size={15} color="#d97706" />
          <span style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>Replace mode: existing keys will be overwritten. Enter master passphrase to unlock:</span>
          <input
            ref={replaceRef}
            type="password"
            placeholder="Master passphrase"
            style={{ ...styles.input, width: 200, fontSize: 12, margin: 0 }}
            onKeyDown={e => { if (e.key === 'Enter' && fileRef.current) fileRef.current.click() }}
          />
          <span style={{ fontSize: 11, color: '#9ca3af' }}>Then choose your file above</span>
        </div>
      )}

      {/* Export passphrase prompt */}
      {showExportPrompt && (
        <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
          <span style={{ fontSize: 12, color: '#166534', fontWeight: 600 }}>Master passphrase required to export:</span>
          <input
            type="password"
            placeholder="Enter passphrase"
            style={{ ...styles.input, width: 200, fontSize: 12, margin: 0 }}
            value={exportPassphrase}
            onChange={e => setExportPassphrase(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleExport()}
            autoFocus
          />
          <button style={styles.primaryBtn} onClick={handleExport}><Download size={14} /> Download</button>
          <button style={styles.outlineBtn} onClick={() => { setShowExportPrompt(false); setExportPassphrase('') }}>Cancel</button>
        </div>
      )}

      {status && (
        <div style={{ ...styles.statsRow, marginBottom: 20 }}>
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

      {/* Pending charts banner — keys uploaded before charts exist */}
      {pendingCharts.length > 0 && (
        <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 10, padding: '14px 16px', marginBottom: 20, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <AlertTriangle size={18} color="#d97706" style={{ flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#92400e', marginBottom: 4 }}>
              {pendingCharts.length} answer key{pendingCharts.length !== 1 ? 's' : ''} not saved — chart numbers not found in the chart bank
            </div>
            <div style={{ fontSize: 12, color: '#78350f', lineHeight: 1.6, marginBottom: 8 }}>
              Answer keys must be uploaded after their charts. Upload the charts first (the system assigns their chart numbers),
              then return here and upload this answer key file again using the correct system-assigned chart numbers.
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
              {pendingCharts.map(cn => (
                <span key={cn} style={{ fontSize: 12, fontWeight: 700, background: '#fef3c7', color: '#92400e', border: '1px solid #fcd34d', padding: '2px 10px', borderRadius: 20 }}>{cn}</span>
              ))}
            </div>
          </div>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 2, flexShrink: 0 }} onClick={() => setPendingCharts([])}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Per-chart list */}
      <div style={{ fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 8 }}>
        Charts with answer keys {akList.length > 0 && <span style={{ fontWeight: 400, color: '#9ca3af' }}>({akList.length})</span>}
      </div>

      {listLoading ? (
        <div style={styles.center}><Loader size={20} /></div>
      ) : akList.length === 0 ? (
        <div style={styles.emptyState}>No answer keys for this specialty yet.</div>
      ) : (
        <div style={styles.table}>
          <div style={{ ...styles.tableHeader, gridTemplateColumns: '130px 1fr 1fr 1fr 80px' }}>
            <span>Chart</span><span>Category</span><span>Entered By</span><span>Date</span><span></span>
          </div>
          {akList.map((row, i) => (
            <div key={row.chart_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
              style={{ ...styles.tableRow, gridTemplateColumns: '130px 1fr 1fr 1fr 80px' }}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{row.chart_number}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{row.category || '—'}</span>
              <span style={{ fontSize: 12 }}>{row.entered_by}</span>
              <span style={{ fontSize: 12, color: '#9ca3af' }}>
                {row.created_at ? new Date(row.created_at).toLocaleDateString() : '—'}
              </span>
              <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  style={{ ...styles.destructiveOutlineBtn, padding: '4px 10px', fontSize: 12 }}
                  title={`Delete answer key for ${row.chart_number}`}
                  onClick={() => openDialog('delete-ak', row.chart_id, row.chart_number)}>
                  <Trash2 size={13} />
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Charts without keys — purge candidates */}
      {status && status.without_answer_key > 0 && (
        <div style={{ marginTop: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 4 }}>
            Charts without answer keys
            <span style={{ fontWeight: 400, color: '#9ca3af', marginLeft: 6 }}>({status.without_answer_key})</span>
          </div>
          <p style={{ ...styles.helpText, marginBottom: 12 }}>
            Charts with no answer key and no grading history can be permanently deleted (purged)
            to free up the chart number. Charts that were graded must be retired instead.
          </p>
          <ChartsWithoutKeys specialty={specialty} onPurge={openDialog} />
        </div>
      )}

      {/* Passphrase dialog */}
      {dialog && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={e => e.target === e.currentTarget && setDialog(null)}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 380, boxShadow: '0 8px 40px rgba(0,0,0,0.18)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <AlertTriangle size={20} color="#dc2626" />
              <span style={{ fontWeight: 700, fontSize: 15 }}>
                {dialog.mode === 'delete-ak' ? 'Delete Answer Key' : 'Permanently Delete Chart'}
              </span>
              <button style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}
                onClick={() => setDialog(null)}><X size={18} /></button>
            </div>
            <p style={{ fontSize: 13, color: '#374151', marginBottom: 16 }}>
              {dialog.mode === 'delete-ak'
                ? <>Deleting the answer key for <strong>{dialog.chartNumber}</strong> allows re-uploading a corrected version. This does not delete the chart itself.</>
                : <>Permanently deleting <strong>{dialog.chartNumber}</strong> frees the chart number for reuse. This cannot be undone.</>
              }
            </p>
            <label style={styles.label}>Master passphrase</label>
            <input
              ref={ppRef}
              type="password"
              style={{ ...styles.input, marginBottom: 16 }}
              placeholder="Enter passphrase to confirm"
              value={passphrase}
              onChange={e => setPassphrase(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && confirmAction()}
            />
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button style={styles.outlineBtn} onClick={() => setDialog(null)}>Cancel</button>
              <button
                style={acting ? { ...styles.destructiveBtn, opacity: 0.6 } : styles.destructiveBtn}
                disabled={acting || !passphrase.trim()}
                onClick={confirmAction}>
                {acting ? <><Loader size={14} /> Working...</> : dialog.mode === 'delete-ak' ? 'Delete Key' : 'Purge Chart'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ChartsWithoutKeys({ specialty, onPurge }: {
  specialty: string
  onPurge: (mode: 'purge-chart', chartId: number, chartNumber: string) => void
}) {
  const [charts, setCharts] = useState<{ chart_id: number; chart_number: string; category: string; can_purge: boolean }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getChartsMissingKeys(specialty).then(setCharts).catch(() => {}).finally(() => setLoading(false))
  }, [specialty])

  if (loading) return <div style={{ padding: '12px 0' }}><Loader size={18} /></div>
  if (charts.length === 0) return null

  return (
    <div style={styles.table}>
      <div style={{ ...styles.tableHeader, gridTemplateColumns: '130px 1fr 1fr 80px' }}>
        <span>Chart</span><span>Category</span><span>Purgeable</span><span></span>
      </div>
      {charts.map((c, i) => (
        <div key={c.chart_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
          style={{ ...styles.tableRow, gridTemplateColumns: '130px 1fr 1fr 80px' }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{c.chart_number}</span>
          <span style={{ fontSize: 12, color: '#6b7280' }}>{c.category || '—'}</span>
          <span style={{ fontSize: 12 }}>
            {c.can_purge
              ? <span style={{ color: '#16a34a', fontWeight: 600 }}>Yes</span>
              : <span style={{ color: '#d97706' }} title="Has grading history — retire instead">Has history</span>
            }
          </span>
          <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
            {c.can_purge && (
              <button
                style={{ ...styles.destructiveOutlineBtn, padding: '4px 10px', fontSize: 12 }}
                title={`Permanently delete ${c.chart_number}`}
                onClick={() => onPurge('purge-chart', c.chart_id, c.chart_number)}>
                <Trash2 size={13} />
              </button>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}
