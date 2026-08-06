import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Trash2, AlertCircle, Download, RefreshCw, Users, Upload, Copy, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { errorMessage } from '../../api/errors'
import { getAssessmentPoolPreview, generateAssessment, parseCoderFile, downloadCoderTemplate, parseStandaloneQuestions } from '../../api'
import RandomisationStatsCard, { RandomisationStats } from '../../components/RandomisationStatsCard'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

interface SpecialtyMixRow { specialty: string; pct: number; topicFilter: string }
interface CoderRow { coder_name: string; employee_id: string }
interface PoolRow { specialty: string; active_count: number; easy: number; medium: number; hard: number; topics?: { topic: string; count: number }[] }
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
  randomisation_stats?: RandomisationStats | null
}

const trainerName = () => localStorage.getItem('trainer_name') || 'Trainer'

interface StandaloneRow {
  question_text: string; option_a: string; option_b: string
  option_c: string; option_d: string; correct_answer: string
  difficulty: string; topic: string
}

export function GenerateView({ initialSpecialty }: { initialSpecialty?: string } = {}) {
  // ── Mode ────────────────────────────────────────────────────────────────────
  const [mode, setMode] = useState<'standard' | 'standalone'>('standard')

  // ── Shared fields ────────────────────────────────────────────────────────────
  const [name, setName] = useState('')
  const [batchName, setBatchName] = useState('')
  const [durationMinutes, setDurationMinutes] = useState(60)
  const [totalQuestions, setTotalQuestions] = useState(20)
  const [randomise, setRandomise] = useState(true)
  const [coders, setCoders] = useState<CoderRow[]>([{ coder_name: '', employee_id: '' }])
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // ── Standard-mode fields ─────────────────────────────────────────────────────
  const [specialtyMix, setSpecialtyMix] = useState<SpecialtyMixRow[]>(
    initialSpecialty
      // Arrived from one specialty's pool readiness, so that specialty is the
      // whole paper — a 50/50 default would silently reintroduce a second
      // pool the trainer never checked.
      ? [{ specialty: initialSpecialty, pct: 100, topicFilter: '' }]
      : [
          { specialty: 'ICD10CM', pct: 50, topicFilter: '' },
          { specialty: 'Surgery', pct: 50, topicFilter: '' },
        ]
  )
  const [diffMode, setDiffMode] = useState<'auto' | 'manual'>('auto')
  const [diffMix, setDiffMix] = useState({ easy: 33, medium: 34, hard: 33 })
  const [poolData, setPoolData] = useState<PoolRow[]>([])
  const [poolLoading, setPoolLoading] = useState(false)
  const [poolError, setPoolError] = useState('')
  const [passThreshold, setPassThreshold] = useState(90)
  const [allowShortPool, setAllowShortPool] = useState(false)
  const [shortfalls, setShortfalls] = useState<
    { specialty: string; topic_filter: string | null; requested: number; available: number }[] | null
  >(null)

  // ── Standalone-mode fields ───────────────────────────────────────────────────
  const [standaloneQuestions, setStandaloneQuestions] = useState<StandaloneRow[]>([])
  const [standaloneFileName, setStandaloneFileName] = useState('')
  const [standaloneParseError, setStandaloneParseError] = useState('')
  const standaloneFileRef = useRef<HTMLInputElement>(null)

  // ── Derived ──────────────────────────────────────────────────────────────────
  const pctTotal = specialtyMix.reduce((s, r) => s + r.pct, 0)
  const diffTotal = diffMix.easy + diffMix.medium + diffMix.hard
  const validCoders = coders.filter(c => c.coder_name.trim())
  const pctValid = Math.abs(pctTotal - 100) < 1
  const diffValid = diffMode === 'auto' || Math.abs(diffTotal - 100) < 1

  const canGenerate = mode === 'standalone'
    ? name.trim() && validCoders.length >= 1 && standaloneQuestions.length >= totalQuestions
    : name.trim() && totalQuestions >= 1 && validCoders.length >= 1 && pctValid && diffValid && specialtyMix.length > 0

  // ── Standard pool preview ────────────────────────────────────────────────────
  const fetchPool = useCallback(() => {
    if (specialtyMix.length === 0 || mode === 'standalone') return
    setPoolLoading(true)
    // One pair per row. Joining these into comma-separated strings collided
    // with the commas inside a row's own topic filter, so the preview counted a
    // different pool from the one generation would draw from.
    getAssessmentPoolPreview(specialtyMix.map(r => ({
      specialty: r.specialty, topicFilter: r.topicFilter,
    })))
      .then(d => { setPoolData(d as PoolRow[]); setPoolError('') })
      .catch(e => { setPoolData([]); setPoolError(errorMessage(e, 'Could not read the question pool')) })
      .finally(() => setPoolLoading(false))
  }, [specialtyMix, mode])

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

  // ── Standalone question upload ────────────────────────────────────────────────
  async function handleStandaloneUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setStandaloneParseError('')
    try {
      const res = await parseStandaloneQuestions(f)
      if (res.errors.length) toast(`⚠ ${res.errors.length} row(s) skipped — check file`)
      setStandaloneQuestions(res.questions as StandaloneRow[])
      setStandaloneFileName(f.name)
      setTotalQuestions(res.count)
      toast.success(`${res.count} standalone questions loaded`)
    } catch (err: unknown) {
      const e2 = err as { response?: { data?: { detail?: string } } }
      setStandaloneParseError(e2?.response?.data?.detail || 'Failed to parse file. Use the question bank template format.')
    }
    if (standaloneFileRef.current) standaloneFileRef.current.value = ''
  }

  // ── Coder list upload ─────────────────────────────────────────────────────────
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

  // ── Generate ──────────────────────────────────────────────────────────────────
  async function handleGenerate(retryShort = false) {
    if (!canGenerate) return
    setGenerating(true)
    setShortfalls(null)
    try {
      const base = {
        assessment_name: name.trim(),
        batch_name: batchName.trim() || undefined,
        coders: validCoders.map(c => ({ coder_name: c.coder_name.trim(), employee_id: c.employee_id.trim() || null })),
        duration_minutes: durationMinutes,
        total_questions: totalQuestions,
        generated_by: trainerName(),
        randomise,
        // The bar this paper is judged against. The backend and analytics have
        // supported it for days; only the screen never asked.
        pass_threshold: passThreshold,
        allow_short_pool: retryShort || allowShortPool,
      }
      const payload = mode === 'standalone'
        ? { ...base, specialty_mix: [], standalone_questions: standaloneQuestions }
        : {
            ...base,
            specialty_mix: specialtyMix.map(r => ({ specialty: r.specialty, pct: r.pct / 100, topic_filter: r.topicFilter })),
            difficulty_mode: diffMode,
            difficulty_mix: diffMode === 'manual' ? { easy: diffMix.easy / 100, medium: diffMix.medium / 100, hard: diffMix.hard / 100 } : undefined,
            save_config: true,
            config_name: name.trim(),
          }
      const res = await generateAssessment(payload)
      setResult(res)
      // The backend has always returned these; the success screen never showed
      // them, so a paper served short looked like a clean run.
      if ((res.warnings || []).length) {
        toast((res.warnings || []).join(' '), { icon: '⚠️', duration: 8000 })
      } else {
        toast.success(`Assessment generated for ${res.coder_count} coders`)
      }
    } catch (e: unknown) {
      const detail = (e as any)?.response?.data?.detail
      // A shortfall refusal names the gap and offers a way through. The error
      // text used to say "re-submit with allow_short_pool", which was not
      // something a trainer could do from this screen.
      if (detail && typeof detail === 'object' && detail.shortfalls) {
        setShortfalls(detail.shortfalls)
        toast.error(detail.message || 'Not enough questions for this mix.')
      } else {
        toast.error(errorMessage(e, 'Generation failed'))
      }
    } finally { setGenerating(false) }
  }

  function copyToken(token: string) {
    navigator.clipboard.writeText(token)
    toast.success('Assessment ID copied')
  }

  function copyAllTokens() {
    if (!result) return
    const text = result.sessions.map((s: SessionResult) => `${s.coder_name}\t${s.employee_id || ''}\t${s.session_token}`).join('\n')
    navigator.clipboard.writeText(text)
    toast.success('All Assessment IDs copied')
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
            Assessment IDs valid for 8 hours from now. Share with coders to begin.
          </div>
          {result.randomisation_stats && (
            <RandomisationStatsCard stats={result.randomisation_stats} itemLabel="questions" />
          )}
        </div>

        <div style={styles.panel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={styles.panelTitle}>Assessment IDs — Share with Coders</div>
            <button style={styles.btnOutline} onClick={copyAllTokens}>
              <Copy size={12} /> Copy All
            </button>
          </div>

          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.thead}>
                  {['Coder Name', 'Employee ID', 'Assessment ID', ''].map(h => (
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
                        title="Copy Assessment ID"
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
          <button style={styles.btnOutline} onClick={() => { setResult(null); setName(''); setBatchName(''); setCoders([{ coder_name: '', employee_id: '' }]) }}>
            Generate Another Assessment
          </button>
        </div>
      </div>
    )
  }

  // ── Form ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ display: 'inline-flex', background: '#f3f4f6', borderRadius: 12, padding: 4, gap: 2 }}>
          {(['standard', 'standalone'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              padding: '8px 20px', border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 700,
              background: mode === m ? (m === 'standalone' ? 'linear-gradient(135deg,#7c3aed,#4f46e5)' : '#fff') : 'none',
              color: mode === m ? (m === 'standalone' ? '#fff' : '#374151') : '#6b7280',
              boxShadow: mode === m ? '0 2px 8px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.15s',
            }}>
              {m === 'standard' ? '📋 Standard' : '⚡ Standalone'}
            </button>
          ))}
        </div>
        {mode === 'standalone' && (
          <span style={{ fontSize: 12, color: '#7c3aed', fontWeight: 600, background: '#ede9fe', padding: '4px 12px', borderRadius: 20 }}>
            Custom questions — not saved to question bank
          </span>
        )}
      </div>

      {/* Assessment settings */}
      <div style={styles.panel}>
        <div style={styles.panelTitle}>Assessment Settings</div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' as const }}>
          <div style={styles.formGroup}>
            <label style={styles.label}>Assessment Name *</label>
            <input
              style={{ ...styles.input, width: 300 }}
              placeholder={mode === 'standalone' ? 'e.g. Client SOP Assessment — June 2026' : 'e.g. Q3 2026 ICD-10-CM Practice'}
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Batch / Cohort Name</label>
            <input
              style={{ ...styles.input, width: 220 }}
              placeholder="e.g. July 2026 Cohort"
              value={batchName}
              onChange={e => setBatchName(e.target.value)}
            />
          </div>
          {mode === 'standard' && (
            <div style={styles.formGroup}>
              <label style={styles.label}>Total Questions</label>
              <input type="number" style={{ ...styles.input, width: 100 }} min={1}
                value={totalQuestions} onChange={e => setTotalQuestions(Number(e.target.value))} />
            </div>
          )}
          <div style={styles.formGroup}>
            <label style={styles.label}>Duration (minutes)</label>
            <input type="number" style={{ ...styles.input, width: 100 }} min={5} max={480}
              value={durationMinutes} onChange={e => setDurationMinutes(Number(e.target.value))} />
          </div>
          <div style={styles.formGroup}>
            {/* Stored on the paper and used by every analytic. Until now the
                screen never asked, so every assessment silently took the
                platform default. */}
            <label style={styles.label}>Pass mark (%)</label>
            <input type="number" style={{ ...styles.input, width: 100 }} min={1} max={100}
              value={passThreshold}
              onChange={e => setPassThreshold(Math.min(100, Math.max(1, Number(e.target.value) || 1)))} />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Randomise per coder</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
              <div
                onClick={() => setRandomise(r => !r)}
                style={{
                  width: 42, height: 24, borderRadius: 12, cursor: 'pointer', position: 'relative',
                  background: randomise ? '#7c3aed' : '#d1d5db', transition: 'background 0.2s',
                }}
              >
                <div style={{
                  position: 'absolute', top: 3, left: randomise ? 21 : 3,
                  width: 18, height: 18, borderRadius: '50%', background: '#fff',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.2)', transition: 'left 0.2s',
                }} />
              </div>
              <span style={{ fontSize: 12, color: randomise ? '#7c3aed' : '#9ca3af', fontWeight: 600 }}>
                {randomise ? 'On — each coder gets a unique draw' : 'Off — all coders get the same set'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Standalone question upload */}
      {mode === 'standalone' && (
        <div style={styles.panel}>
          <div style={styles.panelTitle}>Upload Questions</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            Use the same Excel template format as the Question Bank. Questions will <strong>not</strong> be added to the bank — they are used only for this assessment.
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' as const }}>
            <input ref={standaloneFileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleStandaloneUpload} />
            <button style={styles.btnOutline} onClick={() => standaloneFileRef.current?.click()}>
              <Upload size={13} /> Upload Questions (.xlsx)
            </button>
            {standaloneQuestions.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#16a34a' }}>
                  ✓ {standaloneQuestions.length} questions loaded
                </span>
                <span style={{ fontSize: 12, color: '#9ca3af' }}>from {standaloneFileName}</span>
                <button style={{ ...styles.btnOutline, color: '#dc2626', borderColor: '#fca5a5', fontSize: 11 }}
                  onClick={() => { setStandaloneQuestions([]); setStandaloneFileName('') }}>
                  Clear
                </button>
              </div>
            )}
            {standaloneParseError && (
              <span style={{ fontSize: 12, color: '#dc2626' }}>{standaloneParseError}</span>
            )}
          </div>

          {standaloneQuestions.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', marginBottom: 6 }}>
                QUESTIONS PREVIEW (first 5 of {standaloneQuestions.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 6 }}>
                {standaloneQuestions.slice(0, 5).map((q, i) => (
                  <div key={i} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                    <span style={{ fontWeight: 700, color: '#374151', marginRight: 8 }}>Q{i + 1}.</span>
                    <span style={{ color: '#374151' }}>{q.question_text.slice(0, 100)}{q.question_text.length > 100 ? '…' : ''}</span>
                    <span style={{ marginLeft: 10, padding: '1px 7px', borderRadius: 10, fontSize: 11, fontWeight: 700,
                      background: q.difficulty === 'Easy' ? '#dcfce7' : q.difficulty === 'Hard' ? '#fee2e2' : '#fef9c3',
                      color: q.difficulty === 'Easy' ? '#16a34a' : q.difficulty === 'Hard' ? '#dc2626' : '#854d0e',
                    }}>{q.difficulty}</span>
                    {q.topic && <span style={{ marginLeft: 6, fontSize: 11, color: '#9ca3af' }}>{q.topic}</span>}
                  </div>
                ))}
                {standaloneQuestions.length > 5 && (
                  <div style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center' as const }}>
                    + {standaloneQuestions.length - 5} more questions
                  </div>
                )}
              </div>
              <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, color: '#6b7280' }}>Questions per coder:</span>
                <input type="number" style={{ ...styles.input, width: 80 }} min={1} max={standaloneQuestions.length}
                  value={totalQuestions} onChange={e => setTotalQuestions(Math.min(Number(e.target.value), standaloneQuestions.length))} />
                <span style={{ fontSize: 12, color: '#9ca3af' }}>of {standaloneQuestions.length} uploaded</span>
              </div>
            </div>
          )}
        </div>
      )}

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

      {/* Standard-mode panels: specialty mix, difficulty, pool preview */}
      {mode === 'standard' && <>
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

                {/* Typed topics have to match what the bank stores. "Sepsis"
                    against a bank holding "Sepsis & Shock" returns nothing and
                    looks like an empty pool rather than a spelling mismatch, so
                    the real topics are offered with their counts. Appends
                    rather than replaces, since commas here mean "any of these". */}
                {(pool?.topics || []).length > 0 && (
                  <select
                    style={{ ...styles.input, width: 150 }}
                    value=""
                    onChange={e => {
                      const picked = e.target.value
                      if (!picked) return
                      const current = row.topicFilter.split(',').map(t => t.trim()).filter(Boolean)
                      if (!current.some(t => t.toLowerCase() === picked.toLowerCase())) {
                        updateSpecialty(idx, 'topicFilter', [...current, picked].join(', '))
                      }
                    }}
                  >
                    <option value="">+ add topic…</option>
                    {(pool?.topics || []).map(t => (
                      <option key={t.topic} value={t.topic}>{t.topic} ({t.count})</option>
                    ))}
                  </select>
                )}
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
        <div style={{ display: 'inline-flex', background: '#f3f4f6', borderRadius: 10, padding: 3, gap: 2, marginBottom: 12 }}>
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
              {poolData.map((row, rowIdx) => {
                const mixRow = specialtyMix.find(r => r.specialty === row.specialty)
                const need = mixRow ? Math.round(totalQuestions * mixRow.pct / 100) : 0
                const ok = row.active_count >= need
                return (
                  <tr key={row.specialty} style={{ borderBottom: '1px solid #f3f4f6', background: rowIdx % 2 === 0 ? 'rgba(249,250,251,0.6)' : 'transparent' }}>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{row.specialty}</td>
                    <td style={{ ...styles.td, fontWeight: 700 }}>{row.active_count}</td>
                    <td style={styles.td}>{need}</td>
                    <td style={{ ...styles.td, color: '#16a34a' }}>{row.easy}</td>
                    <td style={{ ...styles.td, color: '#d97706' }}>{row.medium}</td>
                    <td style={{ ...styles.td, color: '#dc2626' }}>{row.hard}</td>
                    <td style={styles.td}>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: ok ? '#dcfce7' : '#fee2e2', color: ok ? '#16a34a' : '#dc2626', display: 'inline-block' }}>
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
      </>}

      {/* Generate */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 14 }}>
        {validCoders.length > 0 && (
          <div style={{ fontSize: 13, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Users size={13} />
            {validCoders.length} coder{validCoders.length > 1 ? 's' : ''} · {durationMinutes} min each
          </div>
        )}
        {shortfalls && (
          <div style={{ flexBasis: '100%', background: 'rgba(234,88,12,0.08)', border: '1px solid rgba(234,88,12,0.25)', borderRadius: 12, padding: '12px 16px', marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: '#c2410c', marginBottom: 6 }}>
              Not enough questions for this mix
            </div>
            {shortfalls.map((sf, i) => (
              <div key={i} style={{ fontSize: 12, color: '#7c2d12' }}>
                {sf.specialty}{sf.topic_filter ? ` (topic: ${sf.topic_filter})` : ''} — needs {sf.requested}, has {sf.available}
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <button style={styles.btnOutline} disabled={generating}
                onClick={() => handleGenerate(true)}>
                Generate a shorter paper anyway
              </button>
              <span style={{ fontSize: 11, color: '#9ca3af', alignSelf: 'center' }}>
                Or add questions, widen the topic filter, or lower the question count.
              </span>
            </div>
          </div>
        )}
        <button
          style={{ ...styles.btnPrimary, fontSize: 15, padding: '12px 28px', opacity: canGenerate ? 1 : 0.5 }}
          disabled={!canGenerate || generating}
          onClick={() => handleGenerate()}
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
  panel: { background: 'rgba(255,255,255,0.72)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '20px 22px', boxShadow: '0 4px 24px rgba(124,58,237,0.06), 0 1px 4px rgba(0,0,0,0.04)' },
  panelTitle: { fontSize: 13, fontWeight: 800, color: '#374151', marginBottom: 14, paddingLeft: 10, borderLeft: '3px solid #7c3aed' },
  formGroup: { display: 'flex', flexDirection: 'column' as const, gap: 5 },
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  input: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151', outline: 'none' },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' },
  btnPrimary: { display: 'flex', alignItems: 'center', gap: 6, padding: '9px 20px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  modeBtn: { padding: '7px 16px', border: '1px solid transparent', borderRadius: 8, background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#6b7280', transition: 'all 0.15s' },
  modeBtnActive: { background: '#fff', border: '1px solid rgba(124,58,237,0.18)', color: '#7c3aed', boxShadow: '0 1px 4px rgba(124,58,237,0.15)' },
  actionBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 7, border: '1px solid #e5e7eb', background: 'none', cursor: 'pointer', color: '#4b5563' },
  th: { padding: '9px 12px', textAlign: 'left' as const, fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, borderBottom: '2px solid #ede9fe', background: 'rgba(237,233,254,0.45)' },
  td: { padding: '9px 12px', color: '#374151' },
  tableWrap: { background: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.6)', borderRadius: 10, overflow: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 },
  thead: { background: 'rgba(249,250,251,0.8)' },
  tr: { borderBottom: '1px solid #f3f4f6' },
}
