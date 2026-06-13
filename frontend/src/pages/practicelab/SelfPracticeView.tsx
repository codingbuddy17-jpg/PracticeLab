import { useState, useEffect, useRef } from 'react'
import { Upload, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getSelfPracticeQueue, releaseSelfPractice, standaloneGrade } from '../../api'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell,
} from 'recharts'
import { ISSUE_COLORS } from './shared'
import styles from './styles'

function StandaloneInsights({ results }: { results: any[] }) {
  if (!results.length) return null
  const scored = results.filter(r => r.weighted_score != null)
  if (!scored.length) return null

  const passed = scored.filter(r => r.pass_fail === 'PASS').length
  const avgScore = Math.round(scored.reduce((s, r) => s + r.weighted_score, 0) / scored.length)
  const passRate = Math.round(passed / scored.length * 100)

  const issueCounts: Record<string, number> = {}
  const sectionCounts: Record<string, number> = {}
  const missedCodes: Record<string, number> = {}
  for (const r of results) {
    for (const f of r.feedback_items || []) {
      const issue = f.issue || f.issue_type || ''
      const section = f.section || ''
      if (issue) issueCounts[issue] = (issueCounts[issue] || 0) + 1
      if (section) sectionCounts[section] = (sectionCounts[section] || 0) + 1
      if ((issue === 'Missed' || issue === 'missed') && f.ak_code) {
        missedCodes[f.ak_code] = (missedCodes[f.ak_code] || 0) + 1
      }
    }
  }
  const totalFb = Object.values(issueCounts).reduce((a, b) => a + b, 0)
  const topIssues = Object.entries(issueCounts).sort((a, b) => b[1] - a[1])
  const topMissed = Object.entries(missedCodes).sort((a, b) => b[1] - a[1]).slice(0, 6)

  return (
    <div style={{ background: '#f8faff', border: '1.5px solid #a5b4fc', borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: '#312e81' }}>✦ Grading Summary</div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {[
          { label: 'Charts Graded', value: scored.length, color: '#111' },
          { label: 'Passed', value: passed, color: '#16a34a' },
          { label: 'Failed', value: scored.length - passed, color: '#dc2626' },
          { label: 'Pass Rate', value: `${passRate}%`, color: passRate >= 80 ? '#16a34a' : passRate >= 60 ? '#d97706' : '#dc2626' },
          { label: 'Avg Score', value: `${avgScore}%`, color: '#111' },
        ].map(s => (
          <div key={s.label} style={{ background: '#fff', border: '1px solid #e0e7ff', borderRadius: 8, padding: '10px 14px', textAlign: 'center', minWidth: 90 }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>
      {totalFb > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 14px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 10 }}>Error Breakdown</div>
            <ResponsiveContainer width="100%" height={Math.max(100, topIssues.length * 36)}>
              <BarChart data={topIssues.map(([type, count]) => ({ label: type.replace(/_/g, ' '), count, pct: Math.round(count / totalFb * 100), type }))}
                layout="vertical" margin={{ left: 8, right: 36, top: 2, bottom: 2 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="label" width={90} tick={{ fontSize: 11, fontWeight: 600 }} />
                <Tooltip formatter={(v: any, _: any, p: any) => [`${p.payload.count} (${v}%)`, 'Share']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="pct" radius={[0, 5, 5, 0]}>
                  {topIssues.map(([type]) => <Cell key={type} fill={ISSUE_COLORS[type] || '#6b7280'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 8 }}>
              {Object.entries(sectionCounts).map(([sec, cnt]) => (
                <span key={sec} style={{ fontSize: 10, fontWeight: 700, background: '#dbeafe', color: '#1d4ed8', padding: '1px 8px', borderRadius: 10 }}>{sec} {cnt}×</span>
              ))}
            </div>
          </div>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 14px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 10 }}>Top Missed Codes</div>
            {topMissed.length === 0 ? (
              <div style={{ fontSize: 12, color: '#9ca3af' }}>None</div>
            ) : topMissed.map(([code, cnt]) => (
              <div key={code} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                <span style={{ fontWeight: 700, color: '#dc2626' }}>{code}</span>
                <span style={{ color: '#6b7280' }}>{cnt}×</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SPQueuePanel({ trainerName }: { trainerName: string }) {
  const [items, setItems] = useState<any[]>([])
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

  const handleRelease = async (sub: any) => {
    if (!trainerName) return toast.error('Set your trainer name in Upload Charts first')
    setReleasing(sub.id)
    const tid = toast.loading('Releasing…')
    try {
      await releaseSelfPractice(sub.id, feedbacks[sub.id] || '', trainerName)
      toast.dismiss(tid); toast.success('Results released')
      load(); setExpanded(null)
    } catch { toast.dismiss(tid); toast.error('Failed to release') }
    finally { setReleasing(null) }
  }

  if (loading) return <div style={styles.emptyState}>Loading…</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <select style={styles.select} value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="pending_review">Pending Review</option>
          <option value="released">Released</option>
          <option value="all">All</option>
        </select>
        <span style={styles.hint}>{items.length} submission{items.length !== 1 ? 's' : ''}</span>
      </div>
      {items.length === 0 ? (
        <div style={styles.emptyState}>No submissions in this view.</div>
      ) : items.map(sub => (
        <div key={sub.id} style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden', background: '#fff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', cursor: 'pointer' }}
            onClick={() => setExpanded(expanded === sub.id ? null : sub.id)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontWeight: 800, fontSize: 15 }}>{sub.coder_name}</span>
              <span style={{ fontSize: 12, color: '#6b7280', background: '#f3f4f6', padding: '2px 8px', borderRadius: 12 }}>{sub.emp_id}</span>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: sub.status === 'pending_review' ? '#fef3c7' : '#dcfce7', color: sub.status === 'pending_review' ? '#b45309' : '#15803d' }}>
                {sub.status === 'pending_review' ? 'Pending' : 'Released'}
              </span>
              <span style={styles.hint}>{sub.chart_count} chart{sub.chart_count !== 1 ? 's' : ''}</span>
            </div>
            <span style={styles.hint}>{new Date(sub.submitted_at).toLocaleDateString()}</span>
          </div>
          {expanded === sub.id && (
            <div style={{ borderTop: '1px solid #f3f4f6', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr 70px 70px 80px 80px', padding: '7px 12px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' }}>
                  <span>Chart</span><span>Specialty</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
                </div>
                {sub.results.map((r: any, i: number) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '100px 1fr 70px 70px 80px 80px', padding: '8px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' }}>
                    <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty || '—'}</span>
                    <span>{r.weighted_score != null ? `${r.weighted_score}%` : '—'}</span>
                    <span style={{ fontWeight: 700, color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{r.pass_fail || '—'}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
                  </div>
                ))}
              </div>
              {sub.status === 'pending_review' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={styles.label}>Feedback for coder (optional)</label>
                  <textarea style={{ ...styles.input, resize: 'vertical' as const, fontFamily: 'system-ui', minHeight: 70 }} rows={3}
                    placeholder="Overall comments, areas to improve…"
                    value={feedbacks[sub.id] || ''}
                    onChange={e => setFeedbacks(f => ({ ...f, [sub.id]: e.target.value }))} />
                  <button style={{ ...styles.primaryBtn, opacity: releasing === sub.id ? 0.7 : 1, alignSelf: 'flex-start' }}
                    disabled={releasing === sub.id} onClick={() => handleRelease(sub)}>
                    {releasing === sub.id ? 'Releasing…' : '✓ Release Results'}
                  </button>
                </div>
              )}
              {sub.status === 'released' && sub.trainer_feedback && (
                <div style={{ fontSize: 13, color: '#15803d', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '10px 14px' }}>
                  <strong>Feedback:</strong> {sub.trainer_feedback}
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>Released by {sub.reviewed_by}</div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function SPStandalonePanel({ trainerName }: { trainerName: string }) {
  const [files, setFiles] = useState<File[]>([])
  const [grading, setGrading] = useState(false)
  const [results, setResults] = useState<any | null>(null)
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
      res.errors.forEach((e: string) => toast.error(e, { duration: 6000 }))
      setResults(res)
    } catch (err: any) {
      toast.dismiss(tid); toast.error(err?.response?.data?.detail || 'Grading failed')
    } finally { setGrading(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={styles.infoBox}>
        Grade any completed answer sheet immediately — no batch needed. Charts must have answer keys. Filename is used as coder name.
      </div>
      <div style={styles.dropzone} onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileRef.current?.click()}>
        <Upload size={22} color="#4f46e5" />
        <div style={{ fontWeight: 600, fontSize: 14, color: '#374151' }}>Drop completed answer sheets or click to browse</div>
        <div style={{ fontSize: 12, color: '#9ca3af' }}>Accepts .xlsx</div>
        <input ref={fileRef} type="file" multiple accept=".xlsx" style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
      </div>
      {files.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {files.map((f, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 7 }}>
              <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
              <button style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af' }} onClick={() => setFiles(p => p.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button style={{ ...styles.primaryBtn, opacity: grading ? 0.7 : 1 }} disabled={grading} onClick={handleGrade}>
            {grading ? <><Loader size={13} /> Grading…</> : `Grade ${files.length} File${files.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}
      {results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <StandaloneInsights results={results.results} />
          <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '140px 100px 70px 70px 80px 80px', padding: '7px 12px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' }}>
              <span>Coder</span><span>Chart</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
            </div>
            {results.results.map((r: any, i: number) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '140px 100px 70px 70px 80px 80px', padding: '8px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' }}>
                <span style={{ fontWeight: 600 }}>{r.coder_name}</span>
                <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                <span>{r.weighted_score != null ? `${r.weighted_score}%` : '—'}</span>
                <span style={{ fontWeight: 700, color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{r.pass_fail || '—'}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
              </div>
            ))}
          </div>
          <button style={styles.outlineBtn} onClick={() => { setFiles([]); setResults(null) }}>Grade More</button>
        </div>
      )}
    </div>
  )
}

export function SelfPracticeView() {
  const [tab, setTab] = useState<'queue' | 'standalone'>('queue')
  const name = localStorage.getItem('trainer_name') || ''

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={styles.sectionTitle}>Self Practice</div>
        <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden' }}>
          <button style={tab === 'queue' ? { ...styles.navBtn, background: '#4f46e5', color: '#fff', border: 'none' } : styles.navBtn}
            onClick={() => setTab('queue')}>Review Queue</button>
          <button style={tab === 'standalone' ? { ...styles.navBtn, background: '#4f46e5', color: '#fff', border: 'none' } : styles.navBtn}
            onClick={() => setTab('standalone')}>Standalone Grade</button>
        </div>
      </div>
      {tab === 'queue' ? <SPQueuePanel trainerName={name} /> : <SPStandalonePanel trainerName={name} />}
    </div>
  )
}
