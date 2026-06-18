import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, AlertCircle, CheckCircle, Download, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentPoolPreview, generateAssessment, exportAssessmentPDF, exportAnswerKey } from '../../api'

const SPECIALTIES = [
  'ICD10CM', 'Surgery', 'ED Facility', 'ED Profee', 'Ancillary',
  'IP-DRG', 'E&M', 'E&M - Multispecialty', 'IVR', 'Anesthesia',
]

interface SpecialtyMixRow {
  specialty: string
  pct: number
  topicFilter: string
}

interface PoolRow {
  specialty: string
  active_count: number
  easy: number
  medium: number
  hard: number
}

interface GenerateResult {
  assessment_id: number
  assessment_name: string
  student_count: number
  total_questions: number
  students: string[]
  generated_at: string
}

const trainerName = () => localStorage.getItem('trainer_name') || 'Trainer'

export function GenerateView() {
  const [name, setName] = useState('')
  const [studentCount, setStudentCount] = useState(5)
  const [totalQuestions, setTotalQuestions] = useState(20)
  const [specialtyMix, setSpecialtyMix] = useState<SpecialtyMixRow[]>([
    { specialty: 'ICD10CM', pct: 50, topicFilter: '' },
    { specialty: 'Surgery', pct: 50, topicFilter: '' },
  ])
  const [diffMode, setDiffMode] = useState<'auto' | 'manual'>('auto')
  const [diffMix, setDiffMix] = useState({ easy: 33, medium: 34, hard: 33 })
  const [poolData, setPoolData] = useState<PoolRow[]>([])
  const [poolLoading, setPoolLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(null)

  const pctTotal = specialtyMix.reduce((s, r) => s + r.pct, 0)
  const diffTotal = diffMix.easy + diffMix.medium + diffMix.hard

  const pctValid = Math.abs(pctTotal - 100) < 1
  const diffValid = diffMode === 'auto' || Math.abs(diffTotal - 100) < 1

  const canGenerate = name.trim() && studentCount >= 1 && totalQuestions >= 1 &&
    specialtyMix.length > 0 && pctValid && diffValid

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

  function removeSpecialty(idx: number) {
    setSpecialtyMix(prev => prev.filter((_, i) => i !== idx))
  }

  function updateRow(idx: number, field: keyof SpecialtyMixRow, value: string | number) {
    setSpecialtyMix(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  async function handleGenerate() {
    if (!canGenerate) return
    setGenerating(true)
    try {
      const payload = {
        assessment_name: name.trim(),
        student_count: studentCount,
        total_questions: totalQuestions,
        specialty_mix: specialtyMix.map(r => ({
          specialty: r.specialty,
          pct: r.pct / 100,
          topic_filter: r.topicFilter,
        })),
        difficulty_mode: diffMode,
        difficulty_mix: diffMode === 'manual' ? {
          easy: diffMix.easy / 100,
          medium: diffMix.medium / 100,
          hard: diffMix.hard / 100,
        } : undefined,
        generated_by: trainerName(),
        save_config: true,
        config_name: name.trim(),
      }
      const res = await generateAssessment(payload)
      setResult(res)
      toast.success(`Assessment generated! ${res.total_questions} questions × ${res.student_count} students`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Success card */}
      {result && (
        <div style={{ background: 'linear-gradient(135deg, #d1fae5, #a7f3d0)', border: '1px solid #6ee7b7', borderRadius: 14, padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <CheckCircle size={20} color="#059669" />
            <div style={{ fontSize: 15, fontWeight: 800, color: '#064e3b' }}>Assessment Generated Successfully</div>
          </div>
          <div style={{ fontSize: 13, color: '#065f46', marginBottom: 16 }}>
            <strong>{result.assessment_name}</strong> — {result.total_questions} questions × {result.student_count} students
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              style={styles.btnPrimary}
              onClick={() => exportAssessmentPDF(result.assessment_id)}
            >
              <Download size={13} /> Export Student PDFs (ZIP)
            </button>
            <button
              style={{ ...styles.btnOutline }}
              onClick={() => exportAnswerKey(result.assessment_id)}
            >
              <Download size={13} /> Export Answer Key
            </button>
            <button
              style={{ ...styles.btnOutline, marginLeft: 'auto' }}
              onClick={() => setResult(null)}
            >
              Generate Another
            </button>
          </div>
        </div>
      )}

      {/* Form */}
      {!result && (
        <>
          {/* Basic settings */}
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
                <label style={styles.label}>Number of Students</label>
                <input
                  type="number"
                  style={{ ...styles.input, width: 100 }}
                  min={1}
                  value={studentCount}
                  onChange={e => setStudentCount(Number(e.target.value))}
                />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>Total Questions</label>
                <input
                  type="number"
                  style={{ ...styles.input, width: 100 }}
                  min={1}
                  value={totalQuestions}
                  onChange={e => setTotalQuestions(Number(e.target.value))}
                />
              </div>
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
                    <select
                      style={styles.input}
                      value={row.specialty}
                      onChange={e => updateRow(idx, 'specialty', e.target.value)}
                    >
                      {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <input
                        type="number"
                        style={{ ...styles.input, width: 70 }}
                        min={0}
                        max={100}
                        value={row.pct}
                        onChange={e => updateRow(idx, 'pct', Number(e.target.value))}
                      />
                      <span style={{ fontSize: 13, color: '#6b7280' }}>%</span>
                    </div>
                    <input
                      style={{ ...styles.input, flex: 1, minWidth: 140 }}
                      placeholder="Topic filter (optional)"
                      value={row.topicFilter}
                      onChange={e => updateRow(idx, 'topicFilter', e.target.value)}
                    />
                    {pool && (
                      <span style={{ fontSize: 11, color: short ? '#dc2626' : '#16a34a', fontWeight: 700, whiteSpace: 'nowrap' as const }}>
                        {short && <AlertCircle size={11} style={{ display: 'inline', marginRight: 3 }} />}
                        {pool.active_count} avail / need {need}
                      </span>
                    )}
                    <button
                      style={{ ...styles.actionBtn, color: '#dc2626' }}
                      onClick={() => removeSpecialty(idx)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Difficulty mode */}
          <div style={styles.panel}>
            <div style={styles.panelTitle}>Difficulty Distribution</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
              <button
                style={{ ...styles.modeBtn, ...(diffMode === 'auto' ? styles.modeBtnActive : {}) }}
                onClick={() => setDiffMode('auto')}
              >
                Auto-balance from pool
              </button>
              <button
                style={{ ...styles.modeBtn, ...(diffMode === 'manual' ? styles.modeBtnActive : {}) }}
                onClick={() => setDiffMode('manual')}
              >
                Manual split
              </button>
            </div>
            {diffMode === 'manual' && (
              <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                {(['easy', 'medium', 'hard'] as const).map(d => (
                  <div key={d} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 700, color: '#374151', textTransform: 'capitalize' as const }}>{d}</label>
                    <input
                      type="number"
                      style={{ ...styles.input, width: 60 }}
                      min={0} max={100}
                      value={diffMix[d]}
                      onChange={e => setDiffMix(prev => ({ ...prev, [d]: Number(e.target.value) }))}
                    />
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
                  <tr>
                    {['Specialty', 'Available', 'Need', 'Easy', 'Medium', 'Hard', 'Status'].map(h => (
                      <th key={h} style={styles.th}>{h}</th>
                    ))}
                  </tr>
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

          {/* Generate button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              style={{ ...styles.btnPrimary, fontSize: 15, padding: '12px 28px', opacity: canGenerate ? 1 : 0.5 }}
              disabled={!canGenerate || generating}
              onClick={handleGenerate}
            >
              {generating
                ? <><RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} /> Generating…</>
                : 'Generate Assessment'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: 'rgba(255,255,255,0.6)',
    backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
    border: '1px solid rgba(255,255,255,0.65)',
    borderRadius: 14, padding: '18px 20px',
  },
  panelTitle: { fontSize: 13, fontWeight: 800, color: '#374151', marginBottom: 14 },
  formGroup: { display: 'flex', flexDirection: 'column' as const, gap: 5 },
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  input: {
    padding: '8px 12px', border: '1px solid #e5e7eb',
    borderRadius: 8, fontSize: 13, background: '#fff', color: '#374151', outline: 'none',
  },
  btnOutline: {
    display: 'flex', alignItems: 'center', gap: 5,
    padding: '8px 14px', border: '1px solid #e5e7eb',
    borderRadius: 8, background: 'rgba(255,255,255,0.7)',
    cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151',
  },
  btnPrimary: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '9px 20px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
    color: '#fff', border: 'none', borderRadius: 9,
    cursor: 'pointer', fontSize: 13, fontWeight: 700,
  },
  modeBtn: {
    padding: '8px 16px', border: '1px solid #e5e7eb',
    borderRadius: 8, background: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 600, color: '#6b7280',
  },
  modeBtnActive: {
    background: 'rgba(124,58,237,0.1)',
    border: '1px solid rgba(124,58,237,0.3)',
    color: '#7c3aed',
  },
  actionBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 30, height: 30, borderRadius: 7,
    border: '1px solid #e5e7eb', background: 'none',
    cursor: 'pointer', color: '#4b5563',
  },
  th: {
    padding: '8px 12px', textAlign: 'left' as const,
    fontSize: 11, fontWeight: 700, color: '#6b7280',
    textTransform: 'uppercase' as const, letterSpacing: 0.4,
    borderBottom: '1px solid #f3f4f6',
  },
  td: { padding: '9px 12px', color: '#374151' },
}
