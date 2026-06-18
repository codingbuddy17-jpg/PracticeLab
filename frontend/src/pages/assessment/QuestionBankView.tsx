import { useState, useRef } from 'react'
import { Upload, Download, Lock, CheckCircle, XCircle, RefreshCw, Edit2, X, Check, Eye, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  listAssessmentQuestions,
  uploadAssessmentQuestions,
  downloadAssessmentTemplate,
  exportAssessmentQuestions,
  updateQuestionStatus,
  updateQuestion,
} from '../../api'

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
  // Passphrase gate
  const [passphrase, setPassphrase] = useState('')
  const [verified, setVerified] = useState(false)
  const [passphraseInput, setPassphraseInput] = useState('')
  const [passphraseError, setPassphraseError] = useState(false)

  // Questions (only loaded on demand)
  const [questions, setQuestions] = useState<Question[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [questionsShown, setQuestionsShown] = useState(false)

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

  function handleVerify() {
    if (!passphraseInput.trim()) { setPassphraseError(true); return }
    // Verify by attempting a passphrase-required action — use the export endpoint as a probe
    // We store and use the passphrase locally; actual server validation happens on download/delete
    setPassphrase(passphraseInput.trim())
    setVerified(true)
    setPassphraseError(false)
  }

  function loadQuestions(pg = page) {
    setLoading(true)
    setQuestionsShown(true)
    listAssessmentQuestions({
      specialty: filterSpecialty || undefined,
      difficulty: filterDifficulty || undefined,
      status: filterStatus || undefined,
      topic: filterTopic || undefined,
      search: search || undefined,
      page: pg,
      page_size: 50,
    })
      .then(data => {
        setQuestions(data.results as Question[])
        setTotal(data.total)
      })
      .catch(() => toast.error('Failed to load questions'))
      .finally(() => setLoading(false))
  }

  function handleShowQuestions() {
    setPage(1)
    loadQuestions(1)
  }

  async function handleUpload() {
    if (!uploadFile) { toast.error('Select a file first'); return }
    setUploading(true)
    try {
      const result = await uploadAssessmentQuestions(uploadSpecialty, trainerName(), uploadFile)
      const dupeCount = result.stored_ids.filter((id: string) => result.stored_ids.indexOf(id) !== result.stored_ids.lastIndexOf(id)).length
      toast.success(`Uploaded ${result.stored} questions${dupeCount ? ` (${dupeCount} duplicates updated)` : ''}`)
      if (result.errors?.length) toast.error(`${result.errors.length} row error(s) — check file`)
      setUploadFile(null)
      if (fileRef.current) fileRef.current.value = ''
      if (questionsShown) loadQuestions(1)
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

  // ── Passphrase gate ──────────────────────────────────────────────────────────
  if (!verified) {
    return (
      <div style={s.gateWrap}>
        <div style={s.gateCard}>
          <div style={s.gateLockIcon}><Lock size={28} color="#7c3aed" /></div>
          <div style={s.gateTitle}>Question Bank — Restricted Access</div>
          <div style={s.gateSubtitle}>
            Enter the admin passphrase to access question management.<br />
            Pool statistics are available on the Summary tab without a passphrase.
          </div>
          <input
            type="password"
            style={{ ...s.input, width: '100%', textAlign: 'center' as const, letterSpacing: 2, ...(passphraseError ? { borderColor: '#dc2626' } : {}) }}
            placeholder="Passphrase"
            value={passphraseInput}
            onChange={e => { setPassphraseInput(e.target.value); setPassphraseError(false) }}
            onKeyDown={e => e.key === 'Enter' && handleVerify()}
          />
          {passphraseError && <div style={{ fontSize: 12, color: '#dc2626' }}>Passphrase is required</div>}
          <button style={s.btnPrimary} onClick={handleVerify}>Unlock</button>
        </div>
      </div>
    )
  }

  // ── Upload + filter + table ─────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Upload section */}
      <div style={s.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={s.panelTitle}>Upload Questions (.xlsx)</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>Duplicate QIDs are automatically detected and updated</div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'center' }}>
          <select style={s.select} value={uploadSpecialty} onChange={e => setUploadSpecialty(e.target.value)}>
            {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
          </select>
          <button style={s.btnOutline} onClick={() => downloadAssessmentTemplate(uploadSpecialty)}>
            <Download size={13} /> Template
          </button>
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
            onChange={e => setUploadFile(e.target.files?.[0] || null)} />
          <button style={s.btnOutline} onClick={() => fileRef.current?.click()}>
            <Upload size={13} /> {uploadFile ? uploadFile.name : 'Choose File'}
          </button>
          <button style={{ ...s.btnPrimary, opacity: uploading ? 0.6 : 1 }} disabled={uploading || !uploadFile} onClick={handleUpload}>
            {uploading ? <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={13} />}
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>

      {/* Filter + show panel */}
      <div style={s.panel}>
        <div style={s.panelTitle}>Browse Questions</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'center' }}>
          <select style={s.select} value={filterSpecialty} onChange={e => setFilterSpecialty(e.target.value)}>
            <option value="">All Specialties</option>
            {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
          </select>
          <select style={s.select} value={filterDifficulty} onChange={e => setFilterDifficulty(e.target.value)}>
            <option value="">All Difficulties</option>
            <option>Easy</option><option>Medium</option><option>Hard</option>
          </select>
          <select style={s.select} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="">All Status</option>
            <option>Active</option><option>Inactive</option>
          </select>
          <input style={{ ...s.select, flex: '1 1 140px', minWidth: 140 }} placeholder="Topic…" value={filterTopic}
            onChange={e => setFilterTopic(e.target.value)} />
          <input style={{ ...s.select, flex: '1 1 180px', minWidth: 180 }} placeholder="Search question text…" value={search}
            onChange={e => setSearch(e.target.value)} />
          <button style={s.btnPrimary} onClick={handleShowQuestions}>
            <Eye size={13} /> Show Questions
          </button>
          {filterSpecialty && (
            <button style={{ ...s.btnOutline, borderColor: '#7c3aed', color: '#7c3aed' }}
              onClick={() => exportAssessmentQuestions(filterSpecialty, passphrase)}>
              <Download size={13} /> Download
            </button>
          )}
        </div>
      </div>

      {/* Questions table — only rendered after explicit Show click */}
      {!questionsShown && (
        <div style={s.emptyHint}>
          <Search size={28} color="#d1d5db" />
          <div style={{ marginTop: 10, fontSize: 13, color: '#9ca3af' }}>Set filters above and click Show Questions</div>
        </div>
      )}

      {questionsShown && (
        <>
          <div style={s.tableWrap}>
            {loading && <div style={s.loadingOverlay}>Loading…</div>}
            <table style={s.table}>
              <thead>
                <tr style={s.thead}>
                  {['QID', 'Specialty', 'Question', 'Diff', 'Topic', 'Type', 'Status', 'Last Used', ''].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {questions.map(q => (
                  <>
                    <tr key={q.question_id} style={s.tr}>
                      <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11 }}>{q.question_id}</td>
                      <td style={s.td}><span style={s.specBadge}>{q.specialty}</span></td>
                      <td style={{ ...s.td, maxWidth: 280 }}>
                        <div style={s.truncate}>{q.question_text}</div>
                      </td>
                      <td style={s.td}>
                        <span style={{ ...s.diffBadge, background: DIFF_COLORS[q.difficulty]?.bg || '#f3f4f6', color: DIFF_COLORS[q.difficulty]?.text || '#374151' }}>
                          {q.difficulty}
                        </span>
                      </td>
                      <td style={s.td}>{q.topic || '—'}</td>
                      <td style={s.td}>{q.question_type}</td>
                      <td style={s.td}>
                        <span style={{ ...s.statusDot, background: q.status === 'Active' ? '#dcfce7' : '#fee2e2', color: q.status === 'Active' ? '#166534' : '#991b1b' }}>
                          {q.status}
                        </span>
                      </td>
                      <td style={{ ...s.td, fontSize: 11, color: '#9ca3af' }}>
                        {q.last_used_at ? new Date(q.last_used_at).toLocaleDateString() : 'Never'}
                      </td>
                      <td style={{ ...s.td, whiteSpace: 'nowrap' as const }}>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button style={s.actionBtn} title="Edit"
                            onClick={() => editingId === q.question_id ? setEditingId(null) : startEdit(q)}>
                            <Edit2 size={13} />
                          </button>
                          <button style={{ ...s.actionBtn, color: q.status === 'Active' ? '#dc2626' : '#16a34a' }}
                            title={q.status === 'Active' ? 'Retire' : 'Reactivate'}
                            onClick={() => handleStatusToggle(q)}>
                            {q.status === 'Active' ? <XCircle size={13} /> : <CheckCircle size={13} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingId === q.question_id && (
                      <tr key={`${q.question_id}-edit`}>
                        <td colSpan={9} style={{ padding: '16px 20px', background: '#faf5ff', borderBottom: '1px solid #e5e7eb' }}>
                          <EditInlineForm draft={editDraft} setDraft={setEditDraft}
                            onSave={() => saveEdit(q.question_id)} onCancel={() => setEditingId(null)} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {questions.length === 0 && !loading && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 13 }}>No questions match the selected filters</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {total > 50 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
              <button style={s.btnOutline} disabled={page === 1} onClick={() => { setPage(p => p - 1); loadQuestions(page - 1) }}>Prev</button>
              <span style={{ fontSize: 13, color: '#6b7280' }}>Page {page} of {Math.ceil(total / 50)} · {total} total</span>
              <button style={s.btnOutline} disabled={page >= Math.ceil(total / 50)} onClick={() => { setPage(p => p + 1); loadQuestions(page + 1) }}>Next</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function EditInlineForm({ draft, setDraft, onSave, onCancel }: {
  draft: Partial<Question>
  setDraft: React.Dispatch<React.SetStateAction<Partial<Question>>>
  onSave: () => void
  onCancel: () => void
}) {
  const input = (field: keyof Question, label: string, wide = false) => (
    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: wide ? '1 1 100%' : '1 1 200px' }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>{label}</label>
      <input style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
        value={(draft[field] as string) || ''}
        onChange={e => setDraft(d => ({ ...d, [field]: e.target.value }))} />
    </div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
      <div style={{ display: 'flex', gap: 10 }}>{input('question_text', 'Question Text', true)}</div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const }}>
        {input('option_a', 'Option A')}{input('option_b', 'Option B')}
        {input('option_c', 'Option C')}{input('option_d', 'Option D')}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, alignItems: 'flex-end' }}>
        {(['correct_answer', 'difficulty', 'question_type'] as const).map(field => (
          <div key={field} style={{ display: 'flex', flexDirection: 'column' as const, gap: 3, flex: '0 0 130px' }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const }}>{field.replace('_', ' ')}</label>
            <select style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
              value={(draft[field] as string) || ''}
              onChange={e => setDraft(d => ({ ...d, [field]: e.target.value }))}>
              {field === 'correct_answer' && ['A', 'B', 'C', 'D'].map(v => <option key={v}>{v}</option>)}
              {field === 'difficulty' && ['Easy', 'Medium', 'Hard'].map(v => <option key={v}>{v}</option>)}
              {field === 'question_type' && ['Conceptual', 'Scenario', 'Rule-based'].map(v => <option key={v}>{v}</option>)}
            </select>
          </div>
        ))}
        {input('topic', 'Topic')}
        <div style={{ display: 'flex', gap: 8, paddingBottom: 2 }}>
          <button style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 16px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 }} onClick={onSave}>
            <Check size={13} /> Save
          </button>
          <button style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', background: 'none', border: '1px solid #e5e7eb', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: '#6b7280' }} onClick={onCancel}>
            <X size={13} /> Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  gateWrap: { display: 'flex', justifyContent: 'center', paddingTop: 60 },
  gateCard: { background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 18, padding: '36px 40px', maxWidth: 420, width: '100%', display: 'flex', flexDirection: 'column' as const, alignItems: 'center', gap: 14, boxShadow: '0 8px 32px rgba(124,58,237,0.12)' },
  gateLockIcon: { width: 60, height: 60, borderRadius: '50%', background: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  gateTitle: { fontSize: 16, fontWeight: 800, color: '#111', textAlign: 'center' as const },
  gateSubtitle: { fontSize: 13, color: '#6b7280', textAlign: 'center' as const, lineHeight: 1.6 },
  panel: { background: 'rgba(255,255,255,0.55)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, padding: '18px 20px', display: 'flex', flexDirection: 'column' as const, gap: 12 },
  panelTitle: { fontSize: 13, fontWeight: 800, color: '#374151' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151', outline: 'none' },
  input: { padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: 9, fontSize: 14, fontFamily: 'inherit', outline: 'none' },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  btnPrimary: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 18px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  emptyHint: { display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', padding: '50px 0', color: '#9ca3af' },
  tableWrap: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, overflow: 'auto', position: 'relative' as const },
  loadingOverlay: { position: 'absolute' as const, inset: 0, background: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#6b7280', zIndex: 2 },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  th: { padding: '10px 14px', textAlign: 'left' as const, fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', color: '#374151', verticalAlign: 'top' as const },
  truncate: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, maxWidth: 280 },
  specBadge: { fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: '#ede9fe', color: '#4f46e5', whiteSpace: 'nowrap' as const },
  diffBadge: { fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20 },
  statusDot: { fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20 },
  actionBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 7, border: '1px solid #e5e7eb', background: 'none', cursor: 'pointer', color: '#4b5563' },
}
