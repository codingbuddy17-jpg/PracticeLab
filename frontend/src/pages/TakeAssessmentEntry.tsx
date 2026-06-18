import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, ArrowRight, AlertCircle } from 'lucide-react'
import { getSessionInfo } from '../api'

export function TakeAssessmentEntry() {
  const navigate = useNavigate()
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLookup() {
    const t = token.trim().toUpperCase()
    if (!t) { setError('Enter your session token'); return }
    setLoading(true)
    setError('')
    try {
      await getSessionInfo(t)
      navigate(`/take-assessment/${t}`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string }; status?: number } }
      setError(err?.response?.data?.detail || 'Session not found. Check your token and try again.')
    } finally { setLoading(false) }
  }

  return (
    <div style={s.page}>
      <div style={s.blob1} />
      <div style={s.blob2} />

      <div style={s.card}>
        <div style={s.iconWrap}>
          <ClipboardList size={32} color="#7c3aed" />
        </div>
        <div style={s.title}>Medical Coding Assessment</div>
        <div style={s.sub}>Enter your session token to begin your assessment.</div>

        <input
          style={s.input}
          placeholder="e.g. ASM-X7K2M9QP"
          value={token}
          onChange={e => { setToken(e.target.value.toUpperCase()); setError('') }}
          onKeyDown={e => e.key === 'Enter' && handleLookup()}
          autoFocus
        />

        {error && (
          <div style={s.errorBox}>
            <AlertCircle size={14} color="#dc2626" />
            <span>{error}</span>
          </div>
        )}

        <button
          style={{ ...s.btn, opacity: loading || !token.trim() ? 0.65 : 1 }}
          disabled={loading || !token.trim()}
          onClick={handleLookup}
        >
          {loading ? 'Checking…' : <><ArrowRight size={15} /> Find My Assessment</>}
        </button>

        <div style={s.note}>
          Your session token was provided by your trainer. It is valid for 8 hours from the time of generation.
        </div>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', background: 'linear-gradient(135deg, #ede9fe 0%, #dbeafe 50%, #d1fae5 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui, sans-serif', position: 'relative', overflow: 'hidden' },
  blob1: { position: 'absolute', top: -100, left: -100, width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, #a78bfa, #7c3aed, transparent)', opacity: 0.18, filter: 'blur(70px)', pointerEvents: 'none' },
  blob2: { position: 'absolute', bottom: -60, right: -60, width: 300, height: 300, borderRadius: '50%', background: 'radial-gradient(circle, #60a5fa, #3b82f6, transparent)', opacity: 0.15, filter: 'blur(60px)', pointerEvents: 'none' },
  card: { background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,0.8)', borderRadius: 20, padding: '40px 36px', width: '100%', maxWidth: 440, display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', boxShadow: '0 8px 40px rgba(124,58,237,0.12)' },
  iconWrap: { width: 64, height: 64, borderRadius: 18, background: 'linear-gradient(135deg, #ede9fe, #dbeafe)', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 22, fontWeight: 800, color: '#111', letterSpacing: -0.4, textAlign: 'center' },
  sub: { fontSize: 14, color: '#6b7280', textAlign: 'center', lineHeight: 1.5 },
  input: { width: '100%', padding: '12px 16px', border: '2px solid #e5e7eb', borderRadius: 10, fontSize: 16, fontFamily: 'monospace', letterSpacing: 1, textAlign: 'center', outline: 'none', boxSizing: 'border-box', background: '#fafafa' },
  errorBox: { display: 'flex', alignItems: 'center', gap: 8, background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#dc2626', width: '100%', boxSizing: 'border-box' },
  btn: { display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', width: '100%', padding: '13px', background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 15, fontWeight: 700 },
  note: { fontSize: 12, color: '#9ca3af', textAlign: 'center', lineHeight: 1.6 },
}
