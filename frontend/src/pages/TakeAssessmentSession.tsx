import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle, AlertCircle, Clock, ChevronLeft, ChevronRight, Flag, Send } from 'lucide-react'
import toast from 'react-hot-toast'
import { getSessionInfo, startSession, saveAnswer, submitSession } from '../api'

interface Question {
  question_id: string
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  specialty?: string
  topic?: string
  difficulty?: string
}

type Screen = 'loading' | 'lobby' | 'taking' | 'review' | 'done' | 'error'

const ALERT_SECONDS = 10 * 60  // 10-minute pre-alert threshold

export function TakeAssessmentSession() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()

  const [screen, setScreen] = useState<Screen>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [sessionInfo, setSessionInfo] = useState<{ coder_name: string; total_questions: number; duration_minutes: number; status: string } | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [answers, setAnswers] = useState<Record<number, string | null>>({})
  const [currentIdx, setCurrentIdx] = useState(0)
  const [timeRemaining, setTimeRemaining] = useState(0)
  const [alertShown, setAlertShown] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const saveQueueRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  // ── Load session info on mount ───────────────────────────────────────────────
  useEffect(() => {
    if (!token) { setScreen('error'); setErrorMsg('No Assessment ID provided.'); return }
    getSessionInfo(token)
      .then(info => {
        setSessionInfo(info)
        if (info.status === 'submitted') {
          setScreen('done')
        } else if (info.status === 'in_progress') {
          // Resume — go straight to start
          handleStart(info)
        } else {
          setScreen('lobby')
        }
      })
      .catch((e: unknown) => {
        const err = e as { response?: { data?: { detail?: string } } }
        setErrorMsg(err?.response?.data?.detail || 'Could not load assessment. Check your Assessment ID.')
        setScreen('error')
      })
  }, [token])

  // ── Countdown timer ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (screen !== 'taking' && screen !== 'review') return
    if (timeRemaining <= 0) return

    const tick = setInterval(() => {
      setTimeRemaining(prev => {
        const next = prev - 1
        if (next === ALERT_SECONDS && !alertShown) {
          toast('10 minutes remaining!', { icon: '⏰', duration: 6000 })
          setAlertShown(true)
        }
        if (next <= 0) {
          clearInterval(tick)
          handleAutoSubmit()
          return 0
        }
        return next
      })
    }, 1000)

    return () => clearInterval(tick)
  }, [screen, timeRemaining])

  // ── Start / Resume ───────────────────────────────────────────────────────────
  async function handleStart(preloaded?: typeof sessionInfo) {
    setScreen('loading')
    try {
      const data = await startSession(token!)
      setQuestions(data.questions)
      const savedAnswers: Record<number, string | null> = {}
      if (data.saved_answers) {
        for (const [k, v] of Object.entries(data.saved_answers)) {
          savedAnswers[Number(k)] = v as string | null
        }
      }
      setAnswers(savedAnswers)
      setTimeRemaining(data.time_remaining_seconds)
      setScreen('taking')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setErrorMsg(err?.response?.data?.detail || 'Failed to start assessment.')
      setScreen('error')
    }
  }

  // ── Answer selection (with debounced auto-save) ──────────────────────────────
  const selectAnswer = useCallback((idx: number, letter: string | null) => {
    setAnswers(prev => ({ ...prev, [idx]: letter }))

    // Debounce server save by 1200ms — reduces server load without any UX impact
    if (saveQueueRef.current[idx]) clearTimeout(saveQueueRef.current[idx])
    saveQueueRef.current[idx] = setTimeout(() => {
      const q = questions[idx]
      if (!q) return
      saveAnswer(token!, idx, q.question_id, letter).catch(() => {
        toast.error('Auto-save failed — check your connection', { id: 'save-err' })
      })
    }, 1200)
  }, [questions, token])

  // ── Flush all pending debounced saves before submit ─────────────────────────
  // Throws if any save fails so the caller can block submission.
  async function flushPendingSaves(currentAnswers: Record<number, string | null>) {
    const pending = saveQueueRef.current
    const flushPromises: Promise<void>[] = []
    for (const idxStr of Object.keys(pending)) {
      const idx = Number(idxStr)
      clearTimeout(pending[idx])
      delete pending[idx]
      const q = questions[idx]
      if (q) {
        flushPromises.push(
          saveAnswer(token!, idx, q.question_id, currentAnswers[idx] ?? null).then(() => {})
        )
      }
    }
    if (flushPromises.length > 0) await Promise.all(flushPromises)
  }

  // ── Auto-submit on timer expiry ──────────────────────────────────────────────
  async function handleAutoSubmit() {
    toast('Time is up! Submitting your assessment…', { icon: '⏱️', duration: 4000 })
    try {
      await flushPendingSaves(answers)
      await submitSession(token!, true)
      setScreen('done')
    } catch { /* already submitted or network error */ }
  }

  // ── Manual submit ────────────────────────────────────────────────────────────
  async function handleSubmit() {
    setSubmitting(true)
    try {
      await flushPendingSaves(answers)
    } catch {
      setSubmitting(false)
      toast.error('Could not save your latest answer — check your connection and try submitting again.')
      return
    }
    try {
      await submitSession(token!, false)
      setScreen('done')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Submission failed. Try again.')
    } finally { setSubmitting(false) }
  }

  // ── Time formatting ──────────────────────────────────────────────────────────
  function formatTime(sec: number) {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const isLowTime = timeRemaining > 0 && timeRemaining <= ALERT_SECONDS
  const answeredCount = Object.values(answers).filter(v => v !== null && v !== undefined).length
  const currentQ = questions[currentIdx]
  // Only the options this question has. A True/False question fills A and B,
  // and rendering all four gave the coder two empty radio buttons to choose
  // between — unanswerable, and it looked broken.
  const ALL_OPTS: [string, keyof Question][] = [['A', 'option_a'], ['B', 'option_b'], ['C', 'option_c'], ['D', 'option_d']]
  const opts = currentQ
    ? ALL_OPTS.filter(([, key]) => String(currentQ[key] ?? '').trim() !== '')
    : ALL_OPTS


  // ─────────────────────────────────────────────────────────────────────────────
  // SCREENS
  // ─────────────────────────────────────────────────────────────────────────────

  if (screen === 'loading') {
    return (
      <div style={s.fullCenter}>
        <div style={{ fontSize: 14, color: '#6b7280' }}>Loading your assessment…</div>
      </div>
    )
  }

  if (screen === 'error') {
    return (
      <div style={s.fullCenter}>
        <div style={s.errorCard}>
          <AlertCircle size={32} color="#dc2626" />
          <div style={{ fontSize: 16, fontWeight: 700, color: '#111' }}>Unable to load assessment</div>
          <div style={{ fontSize: 14, color: '#6b7280', textAlign: 'center' }}>{errorMsg}</div>
          <button style={s.btnOutline} onClick={() => navigate('/take-assessment')}>← Back</button>
        </div>
      </div>
    )
  }

  if (screen === 'done') {
    return (
      <div style={s.fullCenter}>
        <div style={s.doneCard}>
          <CheckCircle size={48} color="#16a34a" />
          <div style={{ fontSize: 20, fontWeight: 800, color: '#111' }}>Assessment Submitted</div>
          <div style={{ fontSize: 14, color: '#6b7280', textAlign: 'center', lineHeight: 1.7 }}>
            Thank you, <strong>{sessionInfo?.coder_name}</strong>.<br />
            Your responses have been recorded.<br />
            Your trainer will share your results.
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>You may close this window.</div>
        </div>
      </div>
    )
  }

  if (screen === 'lobby') {
    return (
      <div style={s.fullCenter}>
        <div style={s.lobbyCard}>
          <div style={s.logoArea}>
            <Flag size={28} color="#7c3aed" />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#111' }}>Ready to Begin?</div>
          <div style={{ fontSize: 14, color: '#6b7280', textAlign: 'center' }}>
            Hello, <strong>{sessionInfo?.coder_name}</strong>
          </div>

          <div style={s.infoGrid}>
            <div style={s.infoCell}>
              <div style={s.infoCellVal}>{sessionInfo?.total_questions}</div>
              <div style={s.infoCellLabel}>Questions</div>
            </div>
            <div style={s.infoCell}>
              <div style={s.infoCellVal}>{sessionInfo?.duration_minutes} min</div>
              <div style={s.infoCellLabel}>Time Allowed</div>
            </div>
          </div>

          <div style={{ fontSize: 13, color: '#6b7280', textAlign: 'center', lineHeight: 1.7 }}>
            • Timer starts when you click <strong>Start Assessment</strong><br />
            • You can navigate freely and change answers<br />
            • Your progress is auto-saved — resuming is safe<br />
            • You will be alerted when 10 minutes remain<br />
            • Assessment auto-submits at time expiry
          </div>

          <button style={s.btnStart} onClick={() => handleStart()}>
            Start Assessment →
          </button>
        </div>
      </div>
    )
  }

  if (screen === 'review') {
    return (
      <div style={s.page}>
        <div style={s.topBar}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Review & Submit</div>
          <div style={{ ...s.timer, background: isLowTime ? '#fee2e2' : '#f3f4f6', color: isLowTime ? '#dc2626' : '#374151' }}>
            <Clock size={13} />
            {formatTime(timeRemaining)}
          </div>
        </div>

        <div style={s.reviewBody}>
          <div style={s.reviewCard}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#374151', marginBottom: 16 }}>
              {answeredCount} of {questions.length} answered
              {answeredCount < questions.length && (
                <span style={{ color: '#dc2626', marginLeft: 8 }}>
                  — {questions.length - answeredCount} unanswered
                </span>
              )}
            </div>

            <div style={s.reviewGrid}>
              {questions.map((q, i) => {
                const ans = answers[i]
                const answered = ans !== null && ans !== undefined
                return (
                  <button
                    key={i}
                    style={{ ...s.reviewQ, background: answered ? '#dcfce7' : '#fee2e2', borderColor: answered ? '#86efac' : '#fca5a5', color: answered ? '#15803d' : '#dc2626' }}
                    onClick={() => { setCurrentIdx(i); setScreen('taking') }}
                  >
                    <div style={{ fontWeight: 700 }}>Q{i + 1}</div>
                    <div style={{ fontSize: 11 }}>{answered ? `Ans: ${ans}` : 'Skipped'}</div>
                  </button>
                )
              })}
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <button style={s.btnOutline} onClick={() => setScreen('taking')}>
                <ChevronLeft size={13} /> Back to Questions
              </button>
              <button
                style={{ ...s.btnSubmit, opacity: submitting ? 0.65 : 1 }}
                disabled={submitting}
                onClick={handleSubmit}
              >
                <Send size={13} />
                {submitting ? 'Submitting…' : 'Final Submit'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // screen === 'taking'
  return (
    <div style={s.page}>
      {/* Top bar */}
      <div style={s.topBar}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
          {sessionInfo?.coder_name}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>
            {answeredCount}/{questions.length} answered
          </div>
          <div style={{ ...s.timer, background: isLowTime ? '#fee2e2' : '#f3f4f6', color: isLowTime ? '#dc2626' : '#374151' }}>
            <Clock size={13} />
            {formatTime(timeRemaining)}
            {isLowTime && <span style={{ fontSize: 11, fontWeight: 800 }}>!</span>}
          </div>
          <button style={s.btnReview} onClick={() => setScreen('review')}>
            Review & Submit →
          </button>
        </div>
      </div>

      <div style={s.body}>
        {/* Question palette */}
        <div style={s.palette}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
            Questions
          </div>
          <div style={s.paletteGrid}>
            {questions.map((_, i) => {
              const ans = answers[i]
              const answered = ans !== null && ans !== undefined
              const isCurrent = i === currentIdx
              return (
                <button
                  key={i}
                  style={{
                    ...s.paletteBtn,
                    background: isCurrent ? '#7c3aed' : answered ? '#dcfce7' : '#f9fafb',
                    color: isCurrent ? '#fff' : answered ? '#15803d' : '#374151',
                    border: isCurrent ? '2px solid #7c3aed' : answered ? '1px solid #86efac' : '1px solid #e5e7eb',
                    fontWeight: isCurrent ? 800 : 600,
                  }}
                  onClick={() => setCurrentIdx(i)}
                >
                  {i + 1}
                </button>
              )
            })}
          </div>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: '#9ca3af' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 12, height: 12, borderRadius: 3, background: '#7c3aed' }} /> Current
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 12, height: 12, borderRadius: 3, background: '#dcfce7', border: '1px solid #86efac' }} /> Answered
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 12, height: 12, borderRadius: 3, background: '#f9fafb', border: '1px solid #e5e7eb' }} /> Unanswered
            </div>
          </div>
        </div>

        {/* Question panel */}
        <div style={s.qPanel}>
          {currentQ && (
            <>
              <div style={s.qHeader}>
                <span style={s.qNumber}>Question {currentIdx + 1} of {questions.length}</span>
                {currentQ.difficulty && (
                  <span style={{ ...s.diffBadge, background: currentQ.difficulty === 'Easy' ? '#dcfce7' : currentQ.difficulty === 'Hard' ? '#fee2e2' : '#fef9c3', color: currentQ.difficulty === 'Easy' ? '#15803d' : currentQ.difficulty === 'Hard' ? '#dc2626' : '#854d0e' }}>
                    {currentQ.difficulty}
                  </span>
                )}
              </div>

              <div style={s.qText}>{currentQ.question_text}</div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 20 }}>
                {opts.map(([letter, key]) => {
                  const selected = answers[currentIdx] === letter
                  return (
                    <button
                      key={letter}
                      style={{ ...s.optBtn, ...(selected ? s.optBtnSelected : {}) }}
                      onClick={() => selectAnswer(currentIdx, selected ? null : letter)}
                    >
                      <div style={{ ...s.optLetter, background: selected ? '#7c3aed' : '#f3f4f6', color: selected ? '#fff' : '#374151' }}>
                        {letter}
                      </div>
                      <div style={{ flex: 1, textAlign: 'left', fontSize: 14, color: selected ? '#3730a3' : '#374151' }}>
                        {String(currentQ[key] || '')}
                      </div>
                      {selected && <CheckCircle size={16} color="#7c3aed" />}
                    </button>
                  )
                })}
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 24, justifyContent: 'space-between' }}>
                <button
                  style={{ ...s.navBtn, opacity: currentIdx === 0 ? 0.4 : 1 }}
                  disabled={currentIdx === 0}
                  onClick={() => setCurrentIdx(i => i - 1)}
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                {currentIdx < questions.length - 1 ? (
                  <button style={s.navBtn} onClick={() => setCurrentIdx(i => i + 1)}>
                    Next <ChevronRight size={14} />
                  </button>
                ) : (
                  <button style={s.btnReview} onClick={() => setScreen('review')}>
                    Review & Submit →
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}


const s: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', background: 'linear-gradient(135deg, #ede9fe 0%, #dbeafe 60%, #d1fae5 100%)', fontFamily: 'system-ui, sans-serif', display: 'flex', flexDirection: 'column' },
  fullCenter: { minHeight: '100vh', background: 'linear-gradient(135deg, #ede9fe 0%, #dbeafe 50%, #d1fae5 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 24px', background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.5)', boxShadow: '0 1px 4px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10 },
  timer: { display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', borderRadius: 20, fontSize: 14, fontWeight: 800, fontFamily: 'monospace' },
  btnReview: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 16px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  btnSubmit: { display: 'flex', alignItems: 'center', gap: 6, padding: '10px 24px', background: '#16a34a', color: '#fff', border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 14, fontWeight: 700 },
  btnOutline: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  body: { display: 'flex', flex: 1, maxWidth: 1100, margin: '0 auto', width: '100%', padding: '24px 16px', gap: 20 } as React.CSSProperties,
  palette: { width: 180, flexShrink: 0, background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 14, padding: '16px', alignSelf: 'flex-start', position: 'sticky', top: 70 },
  paletteGrid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 5 },
  paletteBtn: { width: '100%', aspectRatio: '1', borderRadius: 6, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  qPanel: { flex: 1, background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '28px 32px' },
  qHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  qNumber: { fontSize: 13, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5 },
  diffBadge: { fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20 },
  qText: { fontSize: 16, fontWeight: 600, color: '#111', lineHeight: 1.7 },
  optBtn: { display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', border: '2px solid #e5e7eb', borderRadius: 12, background: 'rgba(255,255,255,0.8)', cursor: 'pointer', transition: 'all 0.12s' },
  optBtnSelected: { border: '2px solid #7c3aed', background: '#ede9fe' },
  optLetter: { width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, flexShrink: 0 },
  navBtn: { display: 'flex', alignItems: 'center', gap: 5, padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8, background: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  errorCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 20, padding: '40px 36px', maxWidth: 400, textAlign: 'center' },
  doneCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 20, padding: '48px 40px', maxWidth: 420, textAlign: 'center' },
  lobbyCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 20, padding: '40px 36px', maxWidth: 460, width: '100%' },
  logoArea: { width: 60, height: 60, borderRadius: 16, background: 'linear-gradient(135deg, #ede9fe, #dbeafe)', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  infoGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, width: '100%' },
  infoCell: { background: '#f9fafb', borderRadius: 12, padding: '16px', textAlign: 'center', border: '1px solid #f3f4f6' },
  infoCellVal: { fontSize: 22, fontWeight: 800, color: '#7c3aed' },
  infoCellLabel: { fontSize: 12, color: '#6b7280', fontWeight: 600, marginTop: 2 },
  btnStart: { width: '100%', padding: '14px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 12, cursor: 'pointer', fontSize: 16, fontWeight: 800 },
  reviewBody: { display: 'flex', justifyContent: 'center', padding: '32px 16px' },
  reviewCard: { background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.7)', borderRadius: 16, padding: '28px 32px', width: '100%', maxWidth: 700 },
  reviewGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: 8 },
  reviewQ: { padding: '10px 6px', borderRadius: 10, border: '1px solid', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 },
}
