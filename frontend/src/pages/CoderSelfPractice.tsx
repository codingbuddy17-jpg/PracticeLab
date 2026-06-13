import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, BookOpen, Download, Upload, CheckCircle, AlertTriangle, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { downloadSelfPracticeTemplate, submitSelfPractice } from '../api'

type State = 'form' | 'submitting' | 'done'

export function CoderSelfPractice() {
  const navigate = useNavigate()
  const [coderName, setCoderName] = useState('')
  const [empId, setEmpId] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [state, setState] = useState<State>('form')
  const [result, setResult] = useState<{ graded: string[]; errors: string[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const valid = Array.from(incoming).filter(f => f.name.endsWith('.xlsx'))
    const invalid = Array.from(incoming).filter(f => !f.name.endsWith('.xlsx'))
    if (invalid.length) toast.error(`${invalid.length} file(s) skipped — only .xlsx accepted`)
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      const added = valid.filter(f => !names.has(f.name))
      if (added.length < valid.length) toast.error('Duplicate files skipped')
      return [...prev, ...added]
    })
  }

  const handleSubmit = async () => {
    if (!coderName.trim()) return toast.error('Enter your name')
    if (!empId.trim()) return toast.error('Enter your Emp ID')
    if (!files.length) return toast.error('Add at least one answer sheet')
    setState('submitting')
    const tid = toast.loading('Submitting your practice sheets…')
    try {
      const res = await submitSelfPractice(coderName.trim(), empId.trim(), files)
      toast.dismiss(tid)
      if (res.errors.length && !res.graded.length) {
        toast.error('No charts could be processed — check errors below')
      }
      setResult(res)
      setState('done')
    } catch (err: any) {
      toast.dismiss(tid)
      toast.error(err?.response?.data?.detail || 'Submission failed')
      setState('form')
    }
  }

  if (state === 'done' && result) {
    const hasGraded = result.graded.length > 0
    return (
      <div style={s.container}>
        <TopBar onBack={() => navigate('/')} />
        <div style={s.content}>
          <div style={s.doneCard}>
            {hasGraded ? (
              <>
                <div style={s.doneIcon}>🎉</div>
                <div style={s.doneTitle}>You're on fire! Submission received.</div>
                <div style={s.doneSub}>
                  <strong>{result.graded.length} chart{result.graded.length !== 1 ? 's' : ''}</strong> submitted successfully.
                  Your trainer will review your work and get back to you with scores and feedback.
                  Keep the coding momentum going! 🚀
                </div>
                <div style={s.chartList}>
                  {result.graded.map(cn => (
                    <span key={cn} style={s.chartChip}><CheckCircle size={12} /> {cn}</span>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div style={s.doneIcon}>⚠️</div>
                <div style={s.doneTitle}>Submission had issues</div>
                <div style={s.doneSub}>None of your charts could be processed. Check the errors below and try again.</div>
              </>
            )}

            {result.errors.length > 0 && (
              <div style={s.errorBox}>
                <div style={s.errorTitle}><AlertTriangle size={14} /> {result.errors.length} issue{result.errors.length !== 1 ? 's' : ''}</div>
                {result.errors.map((e, i) => <div key={i} style={s.errorLine}>{e}</div>)}
              </div>
            )}

            <button style={s.primaryBtn} onClick={() => { setState('form'); setFiles([]); setResult(null) }}>
              Submit More Charts
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={s.container}>
      <TopBar onBack={() => navigate('/')} />
      <div style={s.content}>
        <div style={s.card}>
          <div style={s.cardTitle}>Self Practice</div>
          <div style={s.cardSub}>Practice coding at your own pace. Download the template, fill your answers, and upload back. Your trainer will review and share feedback.</div>

          <div style={s.section}>
            <div style={s.sectionLabel}>Step 1 — Download the answer sheet template</div>
            <button style={s.outlineBtn} onClick={downloadSelfPracticeTemplate}>
              <Download size={15} /> Download Template
            </button>
            <div style={s.hint}>Opens an Excel file. Duplicate the coding tab for each chart you practice and rename each tab with the chart number (e.g. IP002, ED005).</div>
          </div>

          <div style={s.divider} />

          <div style={s.section}>
            <div style={s.sectionLabel}>Step 2 — Your details</div>
            <div style={s.fieldRow}>
              <div style={s.field}>
                <label style={s.label}>Your Name *</label>
                <input style={s.input} placeholder="e.g. Jane Smith" value={coderName} onChange={e => setCoderName(e.target.value)} />
              </div>
              <div style={s.field}>
                <label style={s.label}>Emp ID *</label>
                <input style={s.input} placeholder="e.g. EMP001" value={empId} onChange={e => setEmpId(e.target.value)} />
              </div>
            </div>
          </div>

          <div style={s.divider} />

          <div style={s.section}>
            <div style={s.sectionLabel}>Step 3 — Upload your completed sheet(s)</div>
            <div style={s.dropzone}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
              onClick={() => fileRef.current?.click()}>
              <Upload size={24} color="#4f46e5" />
              <div style={s.dropText}>Drop .xlsx files here or click to browse</div>
              <input ref={fileRef} type="file" multiple accept=".xlsx" style={{ display: 'none' }}
                onChange={e => handleFiles(e.target.files)} />
            </div>

            {files.length > 0 && (
              <div style={s.fileList}>
                {files.map((f, i) => (
                  <div key={i} style={s.fileRow}>
                    <CheckCircle size={14} color="#22c55e" />
                    <span style={s.fileName}>{f.name}</span>
                    <button style={s.removeBtn} onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button style={{ ...s.primaryBtn, opacity: state === 'submitting' ? 0.7 : 1 }}
            disabled={state === 'submitting'} onClick={handleSubmit}>
            {state === 'submitting' ? <><Loader size={14} /> Submitting…</> : 'Submit for Review'}
          </button>
        </div>
      </div>
    </div>
  )
}

function TopBar({ onBack }: { onBack: () => void }) {
  return (
    <div style={s.topBar}>
      <button style={s.backBtn} onClick={onBack}><ChevronLeft size={16} /> Back</button>
      <div style={s.logo}><BookOpen size={18} color="#4f46e5" /><span style={s.logoText}>PracticeLab</span></div>
      <span style={s.pageTitle}>Self Practice</span>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '13px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10 },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', fontSize: 13, color: '#374151' },
  logo: { display: 'flex', alignItems: 'center', gap: 6 },
  logoText: { fontWeight: 800, fontSize: 15, color: '#111' },
  pageTitle: { fontWeight: 700, fontSize: 17, color: '#111' },
  content: { maxWidth: 680, margin: '0 auto', padding: '32px 24px' },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 14, padding: 32, display: 'flex', flexDirection: 'column', gap: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' },
  cardTitle: { fontWeight: 800, fontSize: 20, color: '#111', marginBottom: 8 },
  cardSub: { fontSize: 14, color: '#6b7280', lineHeight: 1.6, marginBottom: 24 },
  section: { display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 24 },
  sectionLabel: { fontWeight: 700, fontSize: 13, color: '#4f46e5' },
  divider: { borderTop: '1px solid #f3f4f6', marginBottom: 24 },
  fieldRow: { display: 'flex', gap: 12 },
  field: { display: 'flex', flexDirection: 'column', gap: 5, flex: 1 },
  label: { fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  input: { padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 },
  hint: { fontSize: 12, color: '#9ca3af', lineHeight: 1.6 },
  dropzone: { border: '2px dashed #c7d2fe', borderRadius: 10, padding: '28px 20px', textAlign: 'center', cursor: 'pointer', background: '#fafafe', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 },
  dropText: { fontWeight: 600, fontSize: 14, color: '#374151' },
  fileList: { display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 },
  fileRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', background: '#f0fdf4', borderRadius: 7, border: '1px solid #bbf7d0' },
  fileName: { flex: 1, fontSize: 13, color: '#15803d', fontWeight: 500 },
  removeBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14 },
  primaryBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '11px 24px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, alignSelf: 'flex-start', marginTop: 8 },
  outlineBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '9px 18px', border: '1px solid #c7d2fe', background: '#eef2ff', color: '#4f46e5', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13, alignSelf: 'flex-start' },
  doneCard: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 14, padding: 36, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' },
  doneIcon: { fontSize: 48, lineHeight: 1 },
  doneTitle: { fontWeight: 800, fontSize: 22, color: '#111' },
  doneSub: { fontSize: 15, color: '#6b7280', lineHeight: 1.7, maxWidth: 440 },
  chartList: { display: 'flex', flexWrap: 'wrap' as const, gap: 8, justifyContent: 'center' },
  chartChip: { display: 'inline-flex', alignItems: 'center', gap: 5, background: '#dcfce7', color: '#15803d', fontSize: 13, fontWeight: 700, padding: '4px 12px', borderRadius: 20, border: '1px solid #86efac' },
  errorBox: { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '12px 16px', width: '100%', textAlign: 'left' as const },
  errorTitle: { display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13, color: '#dc2626', marginBottom: 6 },
  errorLine: { fontSize: 12, color: '#b91c1c', padding: '2px 0' },
}
