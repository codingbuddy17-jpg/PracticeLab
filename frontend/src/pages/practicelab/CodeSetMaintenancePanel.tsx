import { useEffect, useState } from 'react'
import { Database, Play, RefreshCw, X } from 'lucide-react'
import { codeSetStatus, getCodeSetIngestJob, startCodeSetIngest, CodeSetIngestJob } from '../../api/codesApi'

interface Props {
  onClose: () => void
}

export function CodeSetMaintenancePanel({ onClose }: Props) {
  const [codeSets, setCodeSets] = useState<any>(null)
  const [ingestJob, setIngestJob] = useState<CodeSetIngestJob | null>(null)
  const [passphrase, setPassphrase] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function load() {
    codeSetStatus().then(setCodeSets).catch(() => {})
    getCodeSetIngestJob().then(setIngestJob).catch(() => {})
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (ingestJob?.status !== 'running') return
    const timer = window.setInterval(() => {
      getCodeSetIngestJob()
        .then(job => {
          setIngestJob(job)
          if (job?.status && job.status !== 'running') codeSetStatus().then(setCodeSets).catch(() => {})
        })
        .catch(() => {})
    }, 4000)
    return () => window.clearInterval(timer)
  }, [ingestJob?.status])

  async function runIngest() {
    if (!passphrase.trim()) {
      setError('Enter the master passphrase.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const job = await startCodeSetIngest(passphrase.trim(), 'PracticeLab maintenance')
      setIngestJob(job)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Could not start the ingest.')
    } finally {
      setBusy(false)
    }
  }

  const totalRows = (codeSets?.loaded || []).reduce((n: number, r: any) => n + (r.row_count || 0), 0)

  return (
    <div style={s.overlay}>
      <div style={s.modal}>
        <div style={s.header}>
          <div style={s.titleWrap}>
            <Database size={18} color="#0f766e" />
            <div>
              <div style={s.title}>Code Set Maintenance</div>
              <div style={s.subTitle}>CMS ICD-10-CM, ICD-10-PCS and HCPCS reference data</div>
            </div>
          </div>
          <button style={s.closeBtn} onClick={onClose} title="Close">
            <X size={17} />
          </button>
        </div>

        {codeSets?.any && !codeSets.needs_attention && (
          <div style={s.okBox}>
            Current {codeSets.expected_edition} · {totalRows.toLocaleString()} rows loaded
          </div>
        )}
        {codeSets?.needs_attention && (
          <div style={s.warnBox}>
            {codeSets.any ? 'Code sets need refreshing.' : 'CMS code sets have not been loaded.'}
          </div>
        )}

        <div style={s.grid}>
          {(codeSets?.loaded || []).map((r: any) => (
            <div key={r.code_system} style={s.mini}>
              <span style={{ ...s.dot, background: r.current ? '#16a34a' : '#d97706' }} />
              <div>
                <div style={s.miniLabel}>{r.label}</div>
                <div style={s.miniSub}>{r.edition || 'not loaded'} · {(r.row_count || 0).toLocaleString()} rows</div>
              </div>
            </div>
          ))}
          {(codeSets?.missing || []).map((r: any) => (
            <div key={r.code_system} style={s.mini}>
              <span style={{ ...s.dot, background: '#dc2626' }} />
              <div>
                <div style={s.miniLabel}>{r.label}</div>
                <div style={s.miniSub}>not loaded</div>
              </div>
            </div>
          ))}
        </div>

        <div style={s.actions}>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Master passphrase"
            value={passphrase}
            onChange={e => setPassphrase(e.target.value)}
            style={s.pass}
          />
          <button style={s.refreshBtn} onClick={load} title="Refresh status">
            <RefreshCw size={14} />
          </button>
          <button
            style={{
              ...s.runBtn,
              opacity: busy || ingestJob?.status === 'running' ? 0.65 : 1,
              cursor: busy || ingestJob?.status === 'running' ? 'wait' : 'pointer',
            }}
            disabled={busy || ingestJob?.status === 'running'}
            onClick={runIngest}
          >
            <Play size={13} fill="currentColor" />
            {ingestJob?.status === 'running' ? 'Running...' : 'Run CMS Ingest'}
          </button>
        </div>

        {error && <div style={s.error}>{error}</div>}
        {ingestJob && (
          <div style={s.job}>
            <div style={s.jobLine}>
              <span style={{
                ...s.jobPill,
                background: ingestJob.status === 'completed' ? '#dcfce7' : ingestJob.status === 'failed' ? '#fee2e2' : '#ede9fe',
                color: ingestJob.status === 'completed' ? '#166534' : ingestJob.status === 'failed' ? '#991b1b' : '#5b21b6',
              }}>
                {ingestJob.status}
              </span>
              <span>{ingestJob.message || 'CMS code-set ingest job'}</span>
            </div>
            {!!ingestJob.log_tail?.length && (
              <pre style={s.log}>{ingestJob.log_tail.slice(-12).join('\n')}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(15,23,42,0.38)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '72px 20px 20px' },
  modal: { width: 'min(760px, 100%)', maxHeight: 'calc(100vh - 96px)', overflow: 'auto', background: '#fff', border: '1px solid #d1fae5', borderRadius: 10, boxShadow: '0 24px 60px rgba(15,23,42,0.25)', padding: 18 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 },
  titleWrap: { display: 'flex', alignItems: 'flex-start', gap: 10 },
  title: { fontSize: 15, fontWeight: 800, color: '#111827' },
  subTitle: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  closeBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: 6, cursor: 'pointer', color: '#64748b', display: 'flex' },
  okBox: { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', borderRadius: 8, padding: '9px 11px', fontSize: 12, fontWeight: 700, marginBottom: 12 },
  warnBox: { background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', borderRadius: 8, padding: '9px 11px', fontSize: 12, fontWeight: 700, marginBottom: 12 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8 },
  mini: { display: 'flex', alignItems: 'flex-start', gap: 8, padding: '9px 10px', border: '1px solid #e5e7eb', borderRadius: 8, background: '#f8fafc', minWidth: 0 },
  dot: { width: 7, height: 7, borderRadius: 99, flexShrink: 0, marginTop: 5 },
  miniLabel: { fontSize: 12, color: '#374151', fontWeight: 800, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  miniSub: { fontSize: 11, color: '#6b7280', marginTop: 1 },
  actions: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' },
  pass: { flex: '1 1 220px', minWidth: 180, border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13 },
  refreshBtn: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #d1d5db', background: '#fff', borderRadius: 8, padding: '8px 10px', cursor: 'pointer', color: '#475569' },
  runBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, border: 'none', background: '#0f766e', color: '#fff', borderRadius: 8, padding: '9px 13px', cursor: 'pointer', fontSize: 13, fontWeight: 800 },
  error: { fontSize: 12, color: '#dc2626', fontWeight: 700, marginTop: 8 },
  job: { background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, marginTop: 12, fontSize: 12, color: '#475569' },
  jobLine: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  jobPill: { borderRadius: 999, padding: '2px 8px', fontSize: 10, fontWeight: 900, textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  log: { margin: '9px 0 0', maxHeight: 150, overflow: 'auto', background: '#0f172a', color: '#d1fae5', borderRadius: 6, padding: 9, fontSize: 11, lineHeight: 1.45 },
}
