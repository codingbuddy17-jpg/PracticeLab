import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, BookOpen, Upload, CheckCircle, XCircle, ChevronDown, ChevronUp, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getSelfPracticeQueue, releaseSelfPractice, standaloneGrade } from '../api'
import { useLocalStorage } from '../hooks/useLocalStorage'

type Tab = 'queue' | 'standalone'

interface SPResult {
  chart_number: string
  specialty: string | null
  weighted_score: number | null
  pass_fail: 'PASS' | 'FAIL' | null
  dpo_dx_accuracy: number | null
  dpo_poa_accuracy: number | null
  dpo_proc_accuracy: number | null
  dpo_overall_accuracy: number | null
  error_message: string | null
  feedback_items: { section: string; issue: string; ak_code: string; coder_code: string }[]
}

interface SPSubmission {
  id: number
  coder_name: string
  emp_id: string
  status: string
  submitted_at: string
  reviewed_by: string | null
  trainer_feedback: string | null
  chart_count: number
  results: SPResult[]
}

export function TrainerSelfPractice() {
  const navigate = useNavigate()
  const [trainerName] = useLocalStorage<string>('trainer_name', '')
  const [tab, setTab] = useState<Tab>('queue')

  return (
    <div style={s.container}>
      <div style={s.topBar}>
        <button style={s.backBtn} onClick={() => navigate('/trainer')}><ChevronLeft size={16} /> Back</button>
        <div style={s.logo}><BookOpen size={18} color="#4f46e5" /><span style={s.logoText}>PracticeLab</span></div>
        <span style={s.pageTitle}>Self Practice</span>
        <div style={s.tabs}>
          <button style={tab === 'queue' ? s.tabActive : s.tab} onClick={() => setTab('queue')}>Review Queue</button>
          <button style={tab === 'standalone' ? s.tabActive : s.tab} onClick={() => setTab('standalone')}>Standalone Grade</button>
        </div>
      </div>

      {tab === 'queue'
        ? <QueueView trainerName={trainerName} />
        : <StandaloneView trainerName={trainerName} />
      }
    </div>
  )
}

function QueueView({ trainerName }: { trainerName: string }) {
  const [items, setItems] = useState<SPSubmission[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('pending_review')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({})
  const [releasing, setReleasing] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try { setItems(await getSelfPracticeQueue(filter)) }
    catch { toast.error('Failed to load queue') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [filter])

  const handleRelease = async (sub: SPSubmission) => {
    if (!trainerName) return toast.error('Set your trainer name in Upload Charts first')
    setReleasing(sub.id)
    const tid = toast.loading('Releasing results…')
    try {
      await releaseSelfPractice(sub.id, feedbacks[sub.id] || '', trainerName)
      toast.dismiss(tid)
      toast.success('Results released to coder')
      load()
      setExpanded(null)
    } catch {
      toast.dismiss(tid)
      toast.error('Failed to release')
    } finally { setReleasing(null) }
  }

  if (loading) return <div style={s.center}>Loading queue…</div>

  return (
    <div style={s.content}>
      <div style={s.filterRow}>
        <select style={s.select} value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="pending_review">Pending Review</option>
          <option value="released">Released</option>
          <option value="all">All</option>
        </select>
        <span style={s.count}>{items.length} submission{items.length !== 1 ? 's' : ''}</span>
      </div>

      {items.length === 0 ? (
        <div style={s.empty}>
          <BookOpen size={40} color="#e5e7eb" />
          <div style={s.emptyTitle}>No submissions here</div>
          <div style={s.emptySub}>Coder self-practice submissions will appear here once uploaded.</div>
        </div>
      ) : (
        <div style={s.list}>
          {items.map(sub => (
            <div key={sub.id} style={s.card}>
              <div style={s.cardHeader} onClick={() => setExpanded(expanded === sub.id ? null : sub.id)}>
                <div style={s.cardLeft}>
                  <span style={s.coderName}>{sub.coder_name}</span>
                  <span style={s.empId}>{sub.emp_id}</span>
                  <span style={{ ...s.statusBadge, background: sub.status === 'pending_review' ? '#fef3c7' : '#dcfce7', color: sub.status === 'pending_review' ? '#b45309' : '#15803d' }}>
                    {sub.status === 'pending_review' ? 'Pending Review' : 'Released'}
                  </span>
                  <span style={s.chartCount}>{sub.chart_count} chart{sub.chart_count !== 1 ? 's' : ''}</span>
                </div>
                <div style={s.cardRight}>
                  <span style={s.date}>{new Date(sub.submitted_at).toLocaleDateString()}</span>
                  {expanded === sub.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              </div>

              {expanded === sub.id && (
                <div style={s.cardBody}>
                  <ResultsTable results={sub.results} />

                  {sub.status === 'pending_review' && (
                    <div style={s.feedbackSection}>
                      <label style={s.label}>Feedback for coder (optional)</label>
                      <textarea style={s.textarea} rows={3}
                        placeholder="Overall comments, areas to improve, encouragement…"
                        value={feedbacks[sub.id] || ''}
                        onChange={e => setFeedbacks(f => ({ ...f, [sub.id]: e.target.value }))} />
                      <button style={{ ...s.releaseBtn, opacity: releasing === sub.id ? 0.7 : 1 }}
                        disabled={releasing === sub.id} onClick={() => handleRelease(sub)}>
                        {releasing === sub.id ? <><Loader size={14} /> Releasing…</> : <><CheckCircle size={14} /> Release Results to Coder</>}
                      </button>
                    </div>
                  )}

                  {sub.status === 'released' && sub.trainer_feedback && (
                    <div style={s.releasedFeedback}>
                      <strong>Feedback given:</strong> {sub.trainer_feedback}
                      <div style={s.releasedBy}>Released by {sub.reviewed_by}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ResultsTable({ results }: { results: SPResult[] }) {
  return (
    <div style={s.resultsTable}>
      <div style={s.resultsHeader}>
        <span>Chart</span><span>Specialty</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
      </div>
      {results.map((r, i) => (
        <div key={i} style={s.resultsRow}>
          <span style={s.chartNum}>{r.chart_number}</span>
          <span style={s.specialty}>{r.specialty || '—'}</span>
          <span style={s.score}>{r.weighted_score != null ? `${r.weighted_score}%` : r.error_message || '—'}</span>
          <span>
            {r.pass_fail
              ? <span style={{ color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626', fontWeight: 700 }}>{r.pass_fail}</span>
              : <span style={{ color: '#9ca3af' }}>—</span>}
          </span>
          <span style={s.acc}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
          <span style={s.acc}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
        </div>
      ))}
    </div>
  )
}

function StandaloneView({ trainerName }: { trainerName: string }) {
  const [files, setFiles] = useState<File[]>([])
  const [grading, setGrading] = useState(false)
  const [results, setResults] = useState<{ results: any[]; errors: string[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFiles = (fl: FileList | null) => {
    if (!fl) return
    const valid = Array.from(fl).filter(f => f.name.endsWith('.xlsx'))
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...valid.filter(f => !names.has(f.name))]
    })
  }

  const handleGrade = async () => {
    if (!trainerName) return toast.error('Set your trainer name in Upload Charts first')
    if (!files.length) return toast.error('Add at least one answer sheet')
    setGrading(true)
    const tid = toast.loading(`Grading ${files.length} file${files.length !== 1 ? 's' : ''}…`)
    try {
      const res = await standaloneGrade(trainerName, files)
      toast.dismiss(tid)
      if (res.results.length) toast.success(`${res.results.length} chart${res.results.length !== 1 ? 's' : ''} graded`)
      if (res.errors.length) res.errors.forEach((e: string) => toast.error(e, { duration: 6000 }))
      setResults(res)
    } catch (err: any) {
      toast.dismiss(tid)
      toast.error(err?.response?.data?.detail || 'Grading failed')
    } finally { setGrading(false) }
  }

  return (
    <div style={s.content}>
      <div style={s.infoBox}>
        Grade any completed answer sheet immediately without creating a batch. Charts must have answer keys in the system.
        The filename is used as the coder name (e.g. <code>JohnSmith_Assessment.xlsx</code>).
      </div>

      <div style={s.dropzone}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileRef.current?.click()}>
        <Upload size={26} color="#4f46e5" />
        <div style={s.dropText}>Drop completed answer sheets here or click to browse</div>
        <div style={s.dropSub}>Accepts .xlsx — one or multiple files</div>
        <input ref={fileRef} type="file" multiple accept=".xlsx" style={{ display: 'none' }}
          onChange={e => handleFiles(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div style={s.fileList}>
          {files.map((f, i) => (
            <div key={i} style={s.fileRow}>
              <CheckCircle size={14} color="#22c55e" />
              <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
              <button style={s.removeBtn} onClick={() => setFiles(p => p.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button style={{ ...s.primaryBtn, opacity: grading ? 0.7 : 1 }} disabled={grading} onClick={handleGrade}>
            {grading ? <><Loader size={14} /> Grading…</> : `Grade ${files.length} File${files.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}

      {results && (
        <div style={s.standaloneResults}>
          <div style={s.sectionLabel}>Results</div>
          <div style={s.resultsTable}>
            <div style={s.resultsHeader}>
              <span>Coder</span><span>Chart</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
            </div>
            {results.results.map((r: any, i: number) => (
              <div key={i} style={s.resultsRow}>
                <span style={s.coderName}>{r.coder_name}</span>
                <span style={s.chartNum}>{r.chart_number}</span>
                <span>{r.weighted_score != null ? `${r.weighted_score}%` : '—'}</span>
                <span style={{ color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626', fontWeight: 700 }}>{r.pass_fail || '—'}</span>
                <span style={s.acc}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
                <span style={s.acc}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
              </div>
            ))}
          </div>
          {results.errors.length > 0 && (
            <div style={s.errorBox}>
              {results.errors.map((e: string, i: number) => (
                <div key={i} style={s.errorLine}><XCircle size={12} color="#dc2626" /> {e}</div>
              ))}
            </div>
          )}
          <button style={s.outlineBtn} onClick={() => { setFiles([]); setResults(null) }}>Grade More</button>
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '13px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10, flexWrap: 'wrap' as const },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', fontSize: 13, color: '#374151' },
  logo: { display: 'flex', alignItems: 'center', gap: 6 },
  logoText: { fontWeight: 800, fontSize: 15, color: '#111' },
  pageTitle: { fontWeight: 700, fontSize: 17, color: '#111', flex: 1 },
  tabs: { display: 'flex', gap: 4, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' },
  tab: { padding: '7px 16px', border: 'none', background: '#fff', fontSize: 13, fontWeight: 600, color: '#6b7280', cursor: 'pointer' },
  tabActive: { padding: '7px 16px', border: 'none', background: '#4f46e5', fontSize: 13, fontWeight: 600, color: '#fff', cursor: 'pointer' },
  content: { maxWidth: 900, margin: '0 auto', padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 16 },
  center: { textAlign: 'center', padding: 60, color: '#9ca3af' },
  filterRow: { display: 'flex', alignItems: 'center', gap: 12 },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, background: '#fff' },
  count: { fontSize: 13, color: '#6b7280', marginLeft: 'auto' },
  empty: { textAlign: 'center', padding: '60px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 },
  emptyTitle: { fontWeight: 700, fontSize: 16, color: '#6b7280' },
  emptySub: { fontSize: 13, color: '#9ca3af', maxWidth: 340, lineHeight: 1.6 },
  list: { display: 'flex', flexDirection: 'column', gap: 10 },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', cursor: 'pointer', userSelect: 'none' as const },
  cardLeft: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const },
  cardRight: { display: 'flex', alignItems: 'center', gap: 10, color: '#9ca3af' },
  coderName: { fontWeight: 800, fontSize: 15, color: '#111' },
  empId: { fontSize: 12, color: '#6b7280', background: '#f3f4f6', padding: '2px 8px', borderRadius: 12 },
  statusBadge: { fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20 },
  chartCount: { fontSize: 12, color: '#6b7280' },
  date: { fontSize: 12, color: '#9ca3af' },
  cardBody: { borderTop: '1px solid #f3f4f6', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 16 },
  resultsTable: { border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' },
  resultsHeader: { display: 'grid', gridTemplateColumns: '100px 1fr 80px 80px 80px 80px', padding: '8px 14px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' },
  resultsRow: { display: 'grid', gridTemplateColumns: '100px 1fr 80px 80px 80px 80px', padding: '9px 14px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' },
  chartNum: { fontWeight: 700, color: '#1e40af' },
  specialty: { color: '#6b7280', fontSize: 12 },
  score: { fontWeight: 600 },
  acc: { color: '#6b7280', fontSize: 12 },
  feedbackSection: { display: 'flex', flexDirection: 'column', gap: 8 },
  label: { fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  textarea: { padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, resize: 'vertical' as const, fontFamily: 'system-ui, sans-serif' },
  releaseBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '9px 18px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13, alignSelf: 'flex-start' },
  releasedFeedback: { background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#15803d' },
  releasedBy: { fontSize: 11, color: '#6b7280', marginTop: 4 },
  infoBox: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#1e40af', lineHeight: 1.6 },
  dropzone: { border: '2px dashed #c7d2fe', borderRadius: 10, padding: '36px 20px', textAlign: 'center', cursor: 'pointer', background: '#fafafe', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 },
  dropText: { fontWeight: 700, fontSize: 15, color: '#374151' },
  dropSub: { fontSize: 12, color: '#9ca3af' },
  fileList: { display: 'flex', flexDirection: 'column', gap: 8 },
  fileRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 7 },
  removeBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14 },
  primaryBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '10px 22px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, alignSelf: 'flex-start' },
  outlineBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '9px 18px', border: '1px solid #c7d2fe', background: '#eef2ff', color: '#4f46e5', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13, alignSelf: 'flex-start' },
  standaloneResults: { display: 'flex', flexDirection: 'column', gap: 12 },
  sectionLabel: { fontWeight: 700, fontSize: 13, color: '#4f46e5' },
  errorBox: { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 4 },
  errorLine: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#b91c1c' },
}
