import { useState } from 'react'
import { Trash2, RefreshCw, Copy, Clock, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  listAssessmentHistory,
  listAssessmentSessions, deleteAssessmentSessions,
  SessionRow,
} from '../../api'
import RandomisationStatsCard, { RandomisationStats } from '../../components/RandomisationStatsCard'

const STATUS_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  pending:      { bg: '#fef9c3', text: '#854d0e', label: 'Pending' },
  in_progress:  { bg: '#dbeafe', text: '#1d4ed8', label: 'In Progress' },
  submitted:    { bg: '#dcfce7', text: '#15803d', label: 'Submitted' },
  expired:      { bg: '#f3f4f6', text: '#6b7280', label: 'Expired' },
  auto_submitted: { bg: '#ede9fe', text: '#6d28d9', label: 'Auto-submitted' },
}

interface Assessment { id: number; assessment_name: string; config_name?: string | null; student_count?: number; generated_by?: string; generated_at?: string | null; questions_per_student?: number; randomisation_stats?: RandomisationStats | null }

export function SessionsView() {
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [selectedId, setSelectedId] = useState<number | ''>('')
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [loadingAssessments, setLoadingAssessments] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(false)

  async function loadAssessments() {
    setLoadingAssessments(true)
    try {
      const data = await listAssessmentHistory()
      setAssessments(data)
    } catch { toast.error('Failed to load assessments') }
    finally { setLoadingAssessments(false) }
  }

  async function loadSessions(id: number) {
    setLoadingSessions(true)
    try {
      const data = await listAssessmentSessions(id)
      setSessions(data.sessions)
    } catch { toast.error('Failed to load sessions') }
    finally { setLoadingSessions(false) }
  }

  function handleSelectAssessment(id: number | '') {
    setSelectedId(id)
    setSessions([])
    if (id) loadSessions(id as number)
  }

  async function handleDelete() {
    if (!selectedId) return
    if (!confirm('Delete all sessions for this assessment? This cannot be undone if no submissions exist.')) return
    try {
      await deleteAssessmentSessions(selectedId as number)
      setSessions([])
      toast.success('Sessions deleted')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Failed to delete sessions')
    }
  }

  function copyToken(token: string) {
    navigator.clipboard.writeText(token)
    toast.success('Token copied')
  }

  const hasSessions = sessions.length > 0
  const pending = sessions.filter(s => s.status === 'pending').length
  const inProgress = sessions.filter(s => s.status === 'in_progress').length
  const submitted = sessions.filter(s => s.status === 'submitted' || s.status === 'auto_submitted').length
  const selectedAssessment = assessments.find(a => a.id === selectedId) ?? null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Assessment selector */}
      <div style={s.card}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' as const }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={s.label}>Select Assessment</label>
            <select
              style={s.select}
              value={selectedId}
              onFocus={() => { if (!assessments.length) loadAssessments() }}
              onChange={e => handleSelectAssessment(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">— Choose an assessment —</option>
              {assessments.map(a => (
                <option key={a.id} value={a.id}>{a.assessment_name} (#{a.id})</option>
              ))}
            </select>
          </div>
          {selectedId && (
            <>
              <button style={s.btnOutline} onClick={() => loadSessions(selectedId as number)} disabled={loadingSessions}>
                <RefreshCw size={13} style={loadingSessions ? { animation: 'spin 1s linear infinite' } : {}} />
                Refresh
              </button>
              {hasSessions && (
                <button style={s.btnDanger} onClick={handleDelete}>
                  <Trash2 size={13} /> Delete Sessions
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Randomisation stats — shown once an assessment is selected */}
      {selectedAssessment?.randomisation_stats && (
        <RandomisationStatsCard
          stats={selectedAssessment.randomisation_stats}
          itemLabel="questions"
        />
      )}

      {/* Sessions table */}
      {hasSessions && (
        <>
          {/* Summary stats */}
          <div style={{ display: 'flex', gap: 12 }}>
            {[
              { label: 'Total', value: sessions.length, bg: 'rgba(255,255,255,0.85)', color: '#374151', border: '1px solid #d1d5db' },
              { label: 'Pending', value: pending, bg: '#fef9c3', color: '#854d0e', border: '1px solid #fde68a' },
              { label: 'In Progress', value: inProgress, bg: '#bfdbfe', color: '#1e40af', border: '1px solid #93c5fd' },
              { label: 'Submitted', value: submitted, bg: '#dcfce7', color: '#15803d', border: '1px solid #86efac' },
            ].map(stat => (
              <div key={stat.label} style={{ ...s.statBox, background: stat.bg, color: stat.color, border: stat.border }}>
                <div style={{ fontSize: 22, fontWeight: 800 }}>{stat.value}</div>
                <div style={{ fontSize: 11, fontWeight: 600 }}>{stat.label}</div>
              </div>
            ))}
          </div>

          <div style={s.tableWrap}>
            <table style={s.table}>
              <thead>
                <tr style={s.thead}>
                  {['Coder', 'Emp ID', 'Session Token', 'Status', 'Score', 'Time Taken', 'Submitted'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sessions.map(row => {
                  const ast = STATUS_STYLE[row.status] || STATUS_STYLE.pending
                  const timeTaken = row.time_taken_seconds
                    ? `${Math.floor(row.time_taken_seconds / 60)}m ${row.time_taken_seconds % 60}s`
                    : '—'
                  return (
                    <tr key={row.session_id} style={s.tr}>
                      <td style={{ ...s.td, fontWeight: 600 }}>{row.coder_name}</td>
                      <td style={{ ...s.td, fontSize: 12, color: '#6b7280' }}>{row.employee_id || '—'}</td>
                      <td style={s.td}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <code style={{ fontSize: 12, background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
                            {row.session_token}
                          </code>
                          <button
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 2 }}
                            onClick={() => copyToken(row.session_token)}
                            title="Copy token"
                          >
                            <Copy size={12} />
                          </button>
                        </div>
                      </td>
                      <td style={s.td}>
                        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: ast.bg, color: ast.text, whiteSpace: 'nowrap' as const }}>
                          {ast.label}
                        </span>
                      </td>
                      <td style={{ ...s.td, fontWeight: 700, color: row.score_pct !== null ? (row.score_pct >= 90 ? '#15803d' : row.score_pct >= 80 ? '#d97706' : '#dc2626') : '#9ca3af' }}>
                        {row.score_pct !== null ? `${row.score_pct}%` : '—'}
                        {row.correct_count !== null && row.total_questions !== null && (
                          <span style={{ fontSize: 11, fontWeight: 400, color: '#9ca3af', marginLeft: 4 }}>
                            ({row.correct_count}/{row.total_questions})
                          </span>
                        )}
                      </td>
                      <td style={{ ...s.td, fontSize: 12, color: '#6b7280' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Clock size={11} />
                          {timeTaken}
                        </div>
                      </td>
                      <td style={{ ...s.td, fontSize: 12, color: '#6b7280' }}>
                        {row.submitted_at
                          ? new Date(row.submitted_at).toLocaleString()
                          : '—'}
                        {row.auto_submitted && (
                          <span style={{ fontSize: 10, marginLeft: 4, color: '#7c3aed' }}>(auto)</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ fontSize: 12, color: '#9ca3af', display: 'flex', alignItems: 'center', gap: 6 }}>
            <AlertCircle size={12} />
            Share session tokens with coders. They access the assessment at <strong>/take-assessment</strong> on this portal.
          </div>
        </>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  card: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 14, boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  cardTitle: { fontSize: 13, fontWeight: 800, color: '#374151', paddingLeft: 10, borderLeft: '3px solid #7c3aed' },
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4 },
  select: { padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151', width: '100%', marginTop: 4 },
  input: { padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, fontFamily: 'inherit', background: '#fff', width: '100%' },
  field: { display: 'flex', flexDirection: 'column', gap: 4 },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' },
  btnDanger: { display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px', background: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  statBox: { flex: 1, borderRadius: 10, padding: '12px 16px', textAlign: 'center' as const },
  tableWrap: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, overflow: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  th: { padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', color: '#374151', verticalAlign: 'middle' },
}
