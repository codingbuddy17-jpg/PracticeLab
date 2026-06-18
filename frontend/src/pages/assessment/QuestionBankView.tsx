import { useState, useEffect, useRef } from 'react'
import { Upload, Download, ChevronDown, ChevronUp, CheckCircle, XCircle, RefreshCw, Trash2, Edit2, X, Check } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getAssessmentStats,
  listAssessmentQuestions,
  uploadAssessmentQuestions,
  downloadAssessmentTemplate,
  updateQuestionStatus,
  updateQuestion,
} from '../../api'

interface QuestionStat {
  specialty: string
  total: number
  active: number
  inactive: number
}

interface Question {
  id: number
  question_id: string
  specialty: string
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_answer: string
  difficulty: string
  topic: string | null
  question_type: string
  status: string
  last_used_at: string | null
  uploaded_by: string | null
  created_at: string | null
}

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

const DIFF_COLORS: Record<string, { bg: string; text: string }> = {
  Easy: { bg: '#dcfce7', text: '#166534' },
  Medium: { bg: '#fef9c3', text: '#854d0e' },
  Hard: { bg: '#fee2e2', text: '#991b1b' },
}

const trainerName = () => localStorage.getItem('trainer_name') || 'Trainer'

export function QuestionBankView() {
  const [stats, setStats] = useState<QuestionStat[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  // Filters
  const [filterSpecialty, setFilterSpecialty] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterStatus, setFilterStatus] = useState('Active')
  const [filterTopic, setFilterTopic] = useState('')
  const [search, setSearch] = useState('')

  // Upload state
  const [uploadSpecialty, setUploadSpecialty] = useState('ICD10CM')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<Partial<Question>>({})

  function loadStats() {
    getAssessmentStats().then(setStats).catch(() => {})
  }

  function loadQuestions() {
    setLoading(true)
    listAssessmentQuestions({
      specialty: filterSpecialty || undefined,
      difficulty: filterDifficulty || undefined,
      status: filterStatus || undefined,
      topic: filterTopic || undefined,
      search: search || undefined,
      page,
      page_size: 50,
    })
      .then(data => {
        setQuestions(data.results as Question[])
        setTotal(data.total)
      })
      .catch(() => toast.error('Failed to load questions'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadStats() }, [])
  useEffect(() => { setPage(1) }, [filterSpecialty, filterDifficulty, filterStatus, filterTopic, search])
  useEffect(() => { loadQuestions() }, [filterSpecialty, filterDifficulty, filterStatus, filterTopic, search, page])

  async function handleUpload() {
    if (!uploadFile) { toast.error('Select a file first'); return }
    setUploading(true)
    try {
      const result = await uploadAssessmentQuestions(uploadSpecialty, trainerName(), uploadFile)
      toast.success(`Uploaded ${result.stored} questions`)
      if (result.errors?.length) toast.error(`${result.errors.length} row errors — check console`)
      setUploadFile(null)
      if (fileRef.current) fileRef.current.value = ''
      loadStats()
      loadQuestions()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleStatusToggle(q: Question) {
    const newStatus = q.status === 'Active' ? 'Inactive' : 'Active'
    try {
      await updateQuestionStatus(q.question_id, newStatus, trainerName())
      toast.success(`${q.question_id} → ${newStatus}`)
      loadQuestions()
      loadStats()
    } catch {
      toast.error('Failed to update status')
    }
  }

  function startEdit(q: Question) {
    setEditingId(q.question_id)
    setEditDraft({
      question_text: q.question_text,
      option_a: q.option_a, option_b: q.option_b,
      option_c: q.option_c, option_d: q.option_d,
      correct_answer: q.correct_answer,
      difficulty: q.difficulty,
      topic: q.topic || '',
      question_type: q.question_type,
    })
  }

  async function saveEdit(qid: string) {
    try {
      await updateQuestion(qid, editDraft)
      toast.success('Question updated')
      setEditingId(null)
      loadQuestions()
    } catch {
      toast.error('Failed to save')
    }
  }

  const totalActive = stats.reduce((s, x) => s + x.active, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Stats row */}
      <div style={styles.statsRow}>
        <div style={{ ...styles.statCard, background: 'linear-gradient(135deg,#7c3aed,#4f46e5)', color: '#fff' }}>
          <div style={styles.statNum}>{totalActive}</div>
          <div style={styles.statLabel}>Active Questions</div>
        </div>
        {stats.map(s => (
          <div key={s.specialty} style={styles.statCard}>
            <div style={styles.statNum}>{s.active}</div>
            <div style={styles.statLabel}>{s.specialty}</div>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>{s.inactive} inactive</div>
          </div>
        ))}
      </div>

      {/* Upload section */}
      <div style={styles.panel}>
        <div style={styles.panelTitle}>Upload Questions (.xlsx)</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'center' }}>
          <select
            style={styles.select}
            value={uploadSpecialty}
            onChange={e => setUploadSpecialty(e.target.value)}
          >
            {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <button style={styles.btnOutline} onClick={() => downloadAssessmentTemplate(uploadSpecialty)}>
            <Download size={13} /> Template
          </button>

          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            style={{ display: 'none' }}
            onChange={e => setUploadFile(e.target.files?.[0] || null)}
          />
          <button style={styles.btnOutline} onClick={() => fileRef.current?.click()}>
            <Upload size={13} /> {uploadFile ? uploadFile.name : 'Choose File'}
          </button>

          <button
            style={{ ...styles.btnPrimary, opacity: uploading ? 0.6 : 1 }}
            disabled={uploading || !uploadFile}
            onClick={handleUpload}
          >
            {uploading ? <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={13} />}
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'center' }}>
        <input
          style={{ ...styles.select, flex: '1 1 160px', minWidth: 160 }}
          placeholder="Search questions…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select style={styles.select} value={filterSpecialty} onChange={e => setFilterSpecialty(e.target.value)}>
          <option value="">All Specialties</option>
          {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select style={styles.select} value={filterDifficulty} onChange={e => setFilterDifficulty(e.target.value)}>
          <option value="">All Difficulties</option>
          <option value="Easy">Easy</option>
          <option value="Medium">Medium</option>
          <option value="Hard">Hard</option>
        </select>
        <select style={styles.select} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">All Status</option>
          <option value="Active">Active</option>
          <option value="Inactive">Inactive</option>
        </select>
        <input
          style={styles.select}
          placeholder="Topic filter…"
          value={filterTopic}
          onChange={e => setFilterTopic(e.target.value)}
        />
      </div>

      {/* Table */}
      <div style={styles.tableWrap}>
        {loading && <div style={styles.loadingOverlay}>Loading…</div>}
        <table style={styles.table}>
          <thead>
            <tr style={styles.thead}>
              {['QID', 'Specialty', 'Question', 'Diff', 'Topic', 'Type', 'Status', 'Last Used', ''].map(h => (
                <th key={h} style={styles.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {questions.map(q => (
              <>
                <tr key={q.question_id} style={styles.tr}>
                  <td style={{ ...styles.td, fontFamily: 'monospace', fontSize: 11 }}>{q.question_id}</td>
                  <td style={styles.td}><span style={styles.specBadge}>{q.specialty}</span></td>
                  <td style={{ ...styles.td, maxWidth: 280 }}>
                    <div style={styles.truncate}>{q.question_text}</div>
                  </td>
                  <td style={styles.td}>
                    <span style={{ ...styles.diffBadge, background: DIFF_COLORS[q.difficulty]?.bg || '#f3f4f6', color: DIFF_COLORS[q.difficulty]?.text || '#374151' }}>
                      {q.difficulty}
                    </span>
                  </td>
                  <td style={styles.td}>{q.topic || '—'}</td>
                  <td style={styles.td}>{q.question_type}</td>
                  <td style={styles.td}>
                    <span style={{ ...styles.statusDot, background: q.status === 'Active' ? '#dcfce7' : '#fee2e2', color: q.status === 'Active' ? '#166534' : '#991b1b' }}>
                      {q.status}
                    </span>
                  </td>
                  <td style={{ ...styles.td, fontSize: 11, color: '#9ca3af' }}>
                    {q.last_used_at ? new Date(q.last_used_at).toLocaleDateString() : 'Never'}
                  </td>
                  <td style={{ ...styles.td, whiteSpace: 'nowrap' as const }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        style={styles.actionBtn}
                        title="Edit"
                        onClick={() => editingId === q.question_id ? setEditingId(null) : startEdit(q)}
                      >
                        <Edit2 size={13} />
                      </button>
                      <button
                        style={{ ...styles.actionBtn, color: q.status === 'Active' ? '#dc2626' : '#16a34a' }}
                        title={q.status === 'Active' ? 'Retire' : 'Reactivate'}
                        onClick={() => handleStatusToggle(q)}
                      >
                        {q.status === 'Active' ? <XCircle size={13} /> : <CheckCircle size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
                {editingId === q.question_id && (
                  <tr key={`${q.question_id}-edit`}>
                    <td colSpan={9} style={{ padding: '16px 20px', background: '#faf5ff', borderBottom: '1px solid #e5e7eb' }}>
                      <EditInlineForm
                        draft={editDraft}
                        setDraft={setEditDraft}
                        onSave={() => saveEdit(q.question_id)}
                        onCancel={() => setEditingId(null)}
                      />
                    </td>
                  </tr>
                )}
              </>
            ))}
            {questions.length === 0 && !loading && (
              <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 13 }}>No questions found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 50 && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
          <button style={styles.btnOutline} disabled={page === 1} onClick={() => setPage(p => p - 1)}>Prev</button>
          <span style={{ fontSize: 13, color: '#6b7280' }}>Page {page} of {Math.ceil(total / 50)}</span>
          <button style={styles.btnOutline} disabled={page >= Math.ceil(total / 50)} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      )}
    </div>
  )
}

function EditInlineForm({
  draft,
  setDraft,
  onSave,
  onCancel,
}: {
  draft: Partial<Question>
  setDraft: React.Dispatch<React.SetStateAction<Partial<Question>>>
  onSave: () => void
  onCancel: () => void
}) {
  const input = (field: keyof Question, label: string, wide = false) => (
    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: wide ? '1 1 100%' : '1 1 200px' }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>{label}</label>
      <input
        style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
        value={(draft[field] as string) || ''}
        onChange={e => setDraft(d => ({ ...d, [field]: e.target.value }))}
      />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const }}>
        {input('question_text', 'Question Text', true)}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const }}>
        {input('option_a', 'Option A')}
        {input('option_b', 'Option B')}
        {input('option_c', 'Option C')}
        {input('option_d', 'Option D')}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: '0 0 120px' }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>Correct Answer</label>
          <select
            style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
            value={draft.correct_answer || 'A'}
            onChange={e => setDraft(d => ({ ...d, correct_answer: e.target.value }))}
          >
            {['A', 'B', 'C', 'D'].map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: '0 0 120px' }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>Difficulty</label>
          <select
            style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
            value={draft.difficulty || 'Medium'}
            onChange={e => setDraft(d => ({ ...d, difficulty: e.target.value }))}
          >
            {['Easy', 'Medium', 'Hard'].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: '0 0 160px' }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>Type</label>
          <select
            style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
            value={draft.question_type || 'Conceptual'}
            onChange={e => setDraft(d => ({ ...d, question_type: e.target.value }))}
          >
            {['Conceptual', 'Scenario', 'Rule-based'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        {input('topic', 'Topic')}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingBottom: 2 }}>
          <button
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 16px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 }}
            onClick={onSave}
          >
            <Check size={13} /> Save
          </button>
          <button
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', background: 'none', border: '1px solid #e5e7eb', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: '#6b7280' }}
            onClick={onCancel}
          >
            <X size={13} /> Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  statsRow: { display: 'flex', gap: 10, overflowX: 'auto' as const, paddingBottom: 4 },
  statCard: {
    flex: '0 0 auto', minWidth: 100,
    background: 'rgba(255,255,255,0.6)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 12, padding: '14px 16px',
  },
  statNum: { fontSize: 24, fontWeight: 800, color: '#111', letterSpacing: -1 },
  statLabel: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  panel: {
    background: 'rgba(255,255,255,0.55)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 14, padding: '18px 20px',
    display: 'flex', flexDirection: 'column' as const, gap: 14,
  },
  panelTitle: { fontSize: 13, fontWeight: 800, color: '#374151' },
  select: {
    padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 8,
    fontSize: 13, background: '#fff', color: '#374151',
    outline: 'none',
  },
  btnOutline: {
    display: 'flex', alignItems: 'center', gap: 5,
    padding: '8px 14px', border: '1px solid #e5e7eb',
    borderRadius: 8, background: 'rgba(255,255,255,0.7)',
    cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151',
  },
  btnPrimary: {
    display: 'flex', alignItems: 'center', gap: 5,
    padding: '8px 18px', background: '#7c3aed', color: '#fff',
    border: 'none', borderRadius: 8, cursor: 'pointer',
    fontSize: 13, fontWeight: 700,
  },
  tableWrap: {
    background: 'rgba(255,255,255,0.6)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 14, overflow: 'auto',
    position: 'relative' as const,
  },
  loadingOverlay: {
    position: 'absolute' as const, inset: 0,
    background: 'rgba(255,255,255,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 13, color: '#6b7280', zIndex: 2,
  },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  th: {
    padding: '10px 14px', textAlign: 'left' as const,
    fontSize: 11, fontWeight: 700, color: '#6b7280',
    textTransform: 'uppercase' as const, letterSpacing: 0.4,
    borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const,
  },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', color: '#374151', verticalAlign: 'top' as const },
  truncate: {
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
    maxWidth: 280,
  },
  specBadge: {
    fontSize: 10, fontWeight: 700, padding: '2px 8px',
    borderRadius: 20, background: '#ede9fe', color: '#4f46e5',
    whiteSpace: 'nowrap' as const,
  },
  diffBadge: {
    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
  },
  statusDot: {
    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
  },
  actionBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, borderRadius: 7,
    border: '1px solid #e5e7eb', background: 'none',
    cursor: 'pointer', color: '#4b5563',
  },
}
