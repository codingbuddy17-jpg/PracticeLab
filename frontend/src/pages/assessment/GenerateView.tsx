import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Trash2, AlertCircle, Download, RefreshCw, Users, Upload, Copy, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentPoolPreview, generateAssessment, parseCoderFile, downloadCoderTemplate } from '../../api'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

interface SpecialtyMixRow { specialty: string; pct: number; topicFilter: string }
interface CoderRow { coder_name: string; employee_id: string }
interface PoolRow { specialty: string; active_count: number; easy: number; medium: number; hard: number }
interface SessionResult { coder_name: string; employee_id: string | null; session_token: string }
interface GenerateResult {
  assessment_id: number
  assessment_name: string
  coder_count: number
  total_questions: number
  duration_minutes: number
  expires_at: string
  sessions: SessionResult[]
  generated_at: string
}

const trainerName = () => localStorage.getItem('trainer_name') || 'Trainer'

export function GenerateView() {
  const [name, setName] = useState('')
  const [durationMinutes, setDurationMinutes] = useState(60)
  const [totalQuestions, setTotalQuestions] = useState(20)
  const [specialtyMix, setSpecialtyMix] = useState<SpecialtyMixRow[]>([
    { specialty: 'ICD10CM', pct: 50, topicFilter: '' },
    { specialty: 'Surgery', pct: 50, topicFilter: '' },
  ])
  const [coders, setCoders] = useState<CoderRow[]>([{ coder_name: '', employee_id: '' }])
  const [diffMode, setDiffMode] = useState<'auto' | 'manual'>('auto')
  const [diffMix, setDiffMix] = useState({ easy: 33, medium: 34, hard: 33 })
  const [poolData, setPoolData] = useState<PoolRow[]>([])
  const [poolLoading, setPoolLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const pctTotal = specialtyMix.reduce((s, r) => s + r.pct, 0)
  const diffTotal = diffMix.easy + diffMix.medium + diffMix.hard
  const validCoders = coders.filter(c => c.coder_name.trim())

  const pctValid = Math.abs(pctTotal - 100) < 1
  const diffValid = diffMode === 'auto' || Math.abs(diffTotal - 100) < 1
  const canGenerate = name.trim() && totalQuestions >= 1 && validCoders.length >= 1 && pctValid && diffValid && specialtyMix.length > 0

  const fetchPool = useCallback(() => {
    if (specialtyMix.length === 0) return
    setPoolLoading(true)
    const specs = specialtyMix.map(r => r.specialty)
    const topics = specialtyMix.map(r => r.topicFilter).join(',')
    getAssessmentPoolPreview(specs, topics)
      .then(d => setPoolData(d as PoolRow[]))
      .catch(() => {})
      .finally(() => setPoolLoading(false))
  }, [specialtyMix])

  useEffect(() => {
    const timer = setTimeout(fetchPool, 400)
    return () => clearTimeout(timer)
  }, [fetchPool])

  function addSpecialty() {
    const used = new Set(specialtyMix.map(r => r.specialty))
    const next = SPECIALTIES.find(s => !used.has(s))
    if (!next) { toast.error('All specialties already added'); return }
    setSpecialtyMix(prev => [...prev, { specialty: next, pct: 0, topicFilter: '' }])
  }

  function updateSpecialty(idx: number, field: keyof SpecialtyMixRow, value: string | number) {
    setSpecialtyMix(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  async function handleParseFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    try {
      const result = await parseCoderFile(f)
      setCoders(result.coders.map(c => ({ coder_name: c.coder_name, employee_id: c.employee_id || '' })))
      toast.success(`Loaded ${result.count} coders`)
    } catch { toast.error('Failed to parse file') }
    if (fileRef.current) fileRef.current.value = ''
  }

  async function handleGenerate() {
    if (!canGenerate) return
    setGenerating(true)
    try {
      const payload = {
        assessment_name: name.trim(),
        coders: validCoders.map(c => ({ coder_name: c.coder_name.trim(), employee_id: c.employee_id.trim() || null })),
        duration_minutes: durationMinutes,
        total_questions: totalQuestions,
        specialty_mix: specialtyMix.map(r => ({ specialty: r.specialty, pct: r.pct / 100, topic_filter: r.topicFilter })),
        difficulty_mode: diffMode,
        difficulty_mix: diffMode === 'manual' ? { easy: diffMix.easy / 100, medium: diffMix.medium / 100, hard: diffMix.hard / 100 } : undefined,
        generated_by: trainerName(),
        save_config: true,
        config_name: name.trim(),
      }
      const res = await generateAssessment(payload)
      setResult(res)
      toast.success(`Assessment generated for ${res.coder_count} coders`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Generation failed')
    } finally { setGenerating(false) }
  }

  function copyToken(token: string) {
    navigator.clipboard.writeText(token)
    toast.success('Token copied')
  }

  function copyAllTokens() {
    if (!result) return
    const text = result.sessions.map(s => `${s.coder_name}\t${s.employee_id || ''}\t${s.session_token}`).join('\n')
    navigator.clipboard.writeText(text)
    toast.success('All tokens copied')
  }

  // ── Success screen ────────────────────────────────────────────────────────────
  if (result) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ background: 'linear-gradient(135deg, #d1fae5, #a7f3d0)', border: '1px solid #6ee7b7', borderRadius: 14, padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <CheckCircle size={20} color="#059669" />
            <div style={{ fontSize: 15, fontWeight: 800, color: '#064e3b' }}>Assessment Generated</div>
          </div>
          <div style={{ fontSize: 13, color: '#065f46' }}>
            <strong>{result.assessment_name}</strong> — {result.total_questions} questions × {result.coder_count} coders × {result.duration_minutes} min
          </div>
          <div style={{ fontSize: 12, color: '#047857', marginTop: 4 }}>
            Session tokens valid for 8 hours from now. Share tokens with coders to begin.
          </div>
        </div>

        <div style={styles.panel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={styles.panelTitle}>Session Tokens — Share with Coders</div>
            <button style={styles.btnOutline} onClick={copyAllTokens}>
              <Copy size={12} /> Copy All
            </button>
          </div>

          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.thead}>
                  {['Coder Name', 'Employee ID', 'Session Token', ''].map(h => (
                    <th key={h} style={styles.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.sessions.map((s, i) => (
                  <tr key={i} style={styles.tr}>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{s.coder_name}</td>
                    <td style={{ ...styles.td, color: '#6b7280', fontSize: 12 }}>{s.employee_id || '—'}</td>
                    <td style={styles.td}>
                      <code style={{ fontSize: 13, background: '#f3f4f6', padding: '3px 8px', borderRadius: 5, letterSpacing: 0.5 }}>
                        {s.session_token}
                      </code>
                    </td>
                    <td style={styles.td}>
                      <button
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', padding: 4 }}
                        onClick={() => copyToken(s.session_token)}
                        title="Copy token"
                      >
                        <Copy size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 10 }}>
            Coders access their assessment at <strong>/take-assessment</strong> on this portal.
            Results appear in the <strong>Sessions</strong> tab as coders submit.
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button style={styles.btnOutline} onClick={() => { setResult(null); setName(''); setCoders([{ coder_name: '', employee_id: '' }]) }}>
            Generate Another Assessment
          </button>
        </div>
      </div>
    )
  }

  // ── Form ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Assessment settings */}
      <div style={styles.panel}>
        <div style={styles.panelTitle}>Assessment Settings</div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' as const }}>
          <div style={styles.formGroup}>
            <label style={styles.label}>Assessment Name *</label>
            <input
              style={{ ...styles.input, width: 300 }}
              placeholder="e.g. Q3 2026 ICD-10-CM Practice"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Total Questions</label>
            <input type="number" style={{ ...styles.input, width: 100 }} min={1}
              value={totalQuestions} onChange={e => setTotalQuestions(Number(e.target.value))} />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Duration (minutes)</label>
            <input type="number" style={{ ...styles.input, width: 100 }} min={5} max={480}
              value={durationMinutes} onChange={e => setDurationMinutes(Number(e.target.value))} />
          </div>
        </div>
      </div>

      {/* Coders */}
      <div style={styles.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={styles.panelTitle}>
            Coders
            <span style={{ fontSize: 11, fontWeight: 600, color: '#7c3aed', marginLeft: 10, background: '#ede9fe', padding: '2px 8px', borderRadius: 10 }}>
              {validCoders.length} added
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={styles.btnOutline} onClick={() => downloadCoderTemplate()}>
              <Download size={12} /> Template
            </button>
            <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleParseFile} />
            <button style={styles.btnOutline} onClick={() => fileRef.current?.click()}>
              <Upload size={12} /> Upload List
            </button>
            <button style={styles.btnOutline} onClick={() => setCoders(c => [...c, { coder_name: '', employee_id: '' }])}>
              <Plus size={12} /> Add Row
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 28px', gap: 6, marginBottom: 6 }}>
          <div style={styles.label}>Coder Name *</div>
          <div style={styles.label}>Employee ID</div>
          <div />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 6, maxHeight: 240, overflowY: 'auto' as const }}>
          {coders.map((c, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 28px', gap: 6 }}>
              <input style={styles.input} placeholder="Full name"
                value={c.coder_name}
                onChange={e => setCoders(prev => prev.map((r, idx) => idx === i ? { ...r, coder_name: e.target.value } : r))} />
              <input style={styles.input} placeholder="EMP001"
                value={c.employee_id}
                onChange={e => setCoders(prev => prev.map((r, idx) => idx === i ? { ...r, employee_id: e.target.value } : r))} />
              <button
                style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 6, cursor: 'pointer', color: '#dc2626', fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                onClick={() => setCoders(prev => prev.filter((_, idx) => idx !== i))}
                disabled={coders.length === 1}
              >×</button>
            </div>
          ))}
        </div>
      </div>

      {/* Specialty mix */}
      <div style={styles.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={styles.panelTitle}>Specialty Mix</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: pctValid ? '#16a34a' : '#dc2626' }}>
              Total: {pctTotal}% {pctValid ? '✓' : '(must = 100%)'}
            </span>
            <button style={styles.btnOutline} onClick={addSpecialty}>
              <Plus size={13} /> Add Specialty
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 10, marginTop: 10 }}>
          {specialtyMix.map((row, idx) => {
            const need = Math.round(totalQuestions * row.pct / 100)
            const pool = poolData.find(p => p.specialty === row.specialty)
            const short = pool && pool.active_count < need
            return (
              <div key={idx} style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' as const }}>
                <select style={styles.input} value={row.specialty}
                  onChange={e => updateSpecialty(idx, 'specialty', e.target.value)}>
                  {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <input type="number" style={{ ...styles.input, width: 70 }} min={0} max={100}
                    value={row.pct} onChange={e => updateSpecialty(idx, 'pct', Number(e.target.value))} />
                  <span style={{ fontSize: 13, color: '#6b7280' }}>%</span>
                </div>
                <input style={{ ...styles.input, flex: 1, minWidth: 160 }}
                  placeholder="Topics, comma-separated (optional)"
                  value={row.topicFilter}
                  onChange={e => updateSpecialty(idx, 'topicFilter', e.target.value)} />
                {pool && (
                  <span style={{ fontSize: 11, color: short ? '#dc2626' : '#16a34a', fontWeight: 700, whiteSpace: 'nowrap' as const }}>
                    {short && <AlertCircle size={11} style={{ display: 'inline', marginRight: 3 }} />}
                    {pool.active_count} avail / need {need}
                  </span>
                )}
                <button style={{ ...styles.actionBtn, color: '#dc2626' }} onClick={() => setSpecialtyMix(prev => prev.filter((_, i) => i !== idx))}>
                  <Trash2 size={13} />
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Difficulty */}
      <div style={styles.panel}>
        <div style={styles.panelTitle}>Difficulty Distribution</div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
          {(['auto', 'manual'] as const).map(m => (
            <button key={m} style={{ ...styles.modeBtn, ...(diffMode === m ? styles.modeBtnActive : {}) }} onClick={() => setDiffMode(m)}>
              {m === 'auto' ? 'Auto-balance from pool' : 'Manual split'}
            </button>
          ))}
        </div>
        {diffMode === 'manual' && (
          <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
            {(['easy', 'medium', 'hard'] as const).map(d => (
              <div key={d} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: '#374151', textTransform: 'capitalize' as const }}>{d}</label>
                <input type="number" style={{ ...styles.input, width: 60 }} min={0} max={100}
                  value={diffMix[d]} onChange={e => setDiffMix(prev => ({ ...prev, [d]: Number(e.target.value) }))} />
                <span style={{ fontSize: 12, color: '#6b7280' }}>%</span>
              </div>
            ))}
            <span style={{ fontSize: 12, fontWeight: 700, color: diffValid ? '#16a34a' : '#dc2626' }}>
              Total: {diffTotal}% {diffValid ? '✓' : '(must = 100%)'}
            </span>
          </div>
        )}
      </div>

      {/* Pool preview */}
      <div style={styles.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={styles.panelTitle}>Pool Preview</div>
          {poolLoading && <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite', color: '#6b7280' }} />}
        </div>
        {poolData.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 }}>
            <thead>
              <tr>{['Specialty', 'Available', 'Need', 'Easy', 'Medium', 'Hard', 'Status'].map(h => (
                <th key={h} style={styles.th}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {poolData.map(row => {
                const mixRow = specialtyMix.find(r => r.specialty === row.specialty)
                const need = mixRow ? Math.round(totalQuestions * mixRow.pct / 100) : 0
                const ok = row.active_count >= need
                return (
                  <tr key={row.specialty} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={styles.td}>{row.specialty}</td>
                    <td style={{ ...styles.td, fontWeight: 700 }}>{row.active_count}</td>
                    <td style={styles.td}>{need}</td>
                    <td style={styles.td}>{row.easy}</td>
                    <td style={styles.td}>{row.medium}</td>
                    <td style={styles.td}>{row.hard}</td>
                    <td style={styles.td}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: ok ? '#16a34a' : '#dc2626' }}>
                        {ok ? '✓ OK' : '⚠ Short'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: 13, color: '#9ca3af', textAlign: 'center' as const, padding: 20 }}>
            {poolLoading ? 'Loading…' : 'Add specialties above to see pool sizes'}
          </div>
        )}
      </div>

      {/* Generate */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 14 }}>
        {validCoders.length > 0 && (
          <div style={{ fontSize: 13, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Users size={13} />
            {validCoders.length} coder{validCoders.length > 1 ? 's' : ''} · {durationMinutes} min each
          </div>
        )}
        <button
          style={{ ...styles.btnPrimary, fontSize: 15, padding: '12px 28px', opacity: canGenerate ? 1 : 0.5 }}
          disabled={!canGenerate || generating}
          onClick={handleGenerate}
        >
          {generating
            ? <><RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} /> Generating…</>
            : 'Generate & Create Sessions'}
        </button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, padding: '18px 20px' },
  panelTitle: { fontSize: 13, fontWeight: 800, color: '#374151', marginBottom: 14 },
  formGroup: { display: 'flex', flexDirection: 'column' as const, gap: 5 },
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  input: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151', outline: 'none' },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' },
  btnPrimary: { display: 'flex', alignItems: 'center', gap: 6, padding: '9px 20px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  modeBtn: { padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#6b7280' },
  modeBtnActive: { background: 'rgba(124,58,237,0.1)', border: '1px solid rgba(124,58,237,0.3)', color: '#7c3aed' },
  actionBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 7, border: '1px solid #e5e7eb', background: 'none', cursor: 'pointer', color: '#4b5563' },
  th: { padding: '8px 12px', textAlign: 'left' as const, fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, borderBottom: '1px solid #f3f4f6' },
  td: { padding: '9px 12px', color: '#374151' },
  tableWrap: { background: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.6)', borderRadius: 10, overflow: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  tr: { borderBottom: '1px solid #f3f4f6' },
}
