import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import { errorMessage } from '../../api/errors'
import { getAssessmentAuditLogs } from '../../api'

interface LogRow {
  id: number
  trainer_name: string
  action: string
  specialty: string | null
  details: string | null
  created_at: string
}

const ACTION_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  upload:     { bg: '#dbeafe', text: '#1d4ed8', label: 'Upload' },
  download:   { bg: '#dcfce7', text: '#15803d', label: 'Download' },
  edit:       { bg: '#fef9c3', text: '#854d0e', label: 'Edit' },
  retire:     { bg: '#fee2e2', text: '#991b1b', label: 'Retire' },
  reactivate: { bg: '#d1fae5', text: '#065f46', label: 'Reactivate' },
  view_bank:  { bg: '#ede9fe', text: '#6d28d9', label: 'View Bank' },
  generate:   { bg: '#f0fdf4', text: '#15803d', label: 'Generate' },
}

export function AuditLogView({ passphrase }: { passphrase: string }) {
  const [logs, setLogs] = useState<LogRow[]>([])
  const [loading, setLoading] = useState(true)
  const [specialtyFilter, setSpecialtyFilter] = useState('')
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    setError('')
    getAssessmentAuditLogs(passphrase, specialtyFilter || undefined)
      .then(setLogs)
      // The endpoint IS passphrase-gated, so a wrong or expired passphrase is
      // exactly when this used to show an empty log — indistinguishable from
      // "nothing has happened yet", which is the opposite of what an audit
      // trail is for.
      .catch(e => { setLogs([]); setError(errorMessage(e, 'Could not load the audit log')) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [specialtyFilter])

  const SPECIALTIES = [
    'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
    'IP-DRG', 'E/M', 'E/M - Multispecialty', 'IVR', 'Anesthesia',
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
        <select style={s.select} value={specialtyFilter} onChange={e => setSpecialtyFilter(e.target.value)}>
          <option value="">All Specialties</option>
          {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
        </select>
        <button style={s.btnOutline} onClick={load} disabled={loading}>
          <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
          Refresh
        </button>
        <span style={{ fontSize: 12, color: '#9ca3af', marginLeft: 'auto' }}>{logs.length} entries (latest first)</span>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              {['Time', 'Trainer', 'Action', 'Specialty', 'Details'].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map(row => {
              const ast = ACTION_STYLE[row.action] || { bg: '#f3f4f6', text: '#374151', label: row.action }
              const dt = new Date(row.created_at)
              return (
                <tr key={row.id} style={s.tr}>
                  <td style={{ ...s.td, whiteSpace: 'nowrap' as const, color: '#6b7280', fontSize: 12 }}>
                    <div>{dt.toLocaleDateString()}</div>
                    <div style={{ color: '#9ca3af' }}>{dt.toLocaleTimeString()}</div>
                  </td>
                  <td style={{ ...s.td, fontWeight: 600 }}>{row.trainer_name}</td>
                  <td style={s.td}>
                    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: ast.bg, color: ast.text, whiteSpace: 'nowrap' as const }}>
                      {ast.label}
                    </span>
                  </td>
                  <td style={{ ...s.td, fontSize: 12 }}>{row.specialty || '—'}</td>
                  <td style={{ ...s.td, fontSize: 12, color: '#6b7280', maxWidth: 300 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
                      {row.details || '—'}
                    </div>
                  </td>
                </tr>
              )
            })}
            {/* An empty log and an unreadable log mean opposite things. */}
            {error && !loading && (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#b91c1c', fontSize: 13, fontWeight: 600 }}>
                {error}
                <button onClick={load} style={{ marginLeft: 10, padding: '4px 10px', borderRadius: 7, border: '1px solid rgba(220,38,38,0.3)', background: '#fff', color: '#b91c1c', cursor: 'pointer', fontSize: 12, fontWeight: 700 }}>Retry</button>
              </td></tr>
            )}
            {logs.length === 0 && !loading && !error && (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 13 }}>No audit entries yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151' },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  tableWrap: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, overflow: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  th: { padding: '10px 14px', textAlign: 'left' as const, fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', color: '#374151', verticalAlign: 'top' as const },
}
