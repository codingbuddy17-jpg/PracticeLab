import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { BarChart3, ChevronLeft, ClipboardCheck, KeyRound, Layers, SlidersHorizontal } from 'lucide-react'
import { AuditBatches } from './auditor/AuditBatches'
import { AuditKeys } from './auditor/AuditKeys'
import { AuditConfig } from './auditor/AuditConfig'
import { AuditAnalytics } from './auditor/AuditAnalytics'

/**
 * PracticeLab — Auditor. A sibling of the coder module that shares charts and
 * answer keys with it and nothing else: separate storage, separate screens,
 * separate analytics, so audit work can never leak into coder reporting.
 */

const TABS = [
  { key: 'batches', label: 'Audit Batches', icon: Layers },
  { key: 'keys', label: 'Planting Library', icon: KeyRound },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'config', label: 'Scoring', icon: SlidersHorizontal },
] as const

type TabKey = typeof TABS[number]['key']

export function TrainerAuditor() {
  const { tab } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const active = (TABS.some(t => t.key === tab) ? tab : 'batches') as TabKey

  // Persisted so a trainer is not retyping their name on every screen — the
  // same convention the PracticeLab views already use.
  const [trainer, setTrainer] = useState(
    () => localStorage.getItem('trainerName') || 'Trainer')
  useEffect(() => { localStorage.setItem('trainerName', trainer) }, [trainer])

  return (
    <div style={st.page}>
      <header style={st.header}>
        <Link to="/trainer" style={st.back}><ChevronLeft size={15} /> Trainer</Link>
        <div style={st.brandWrap}>
          <ClipboardCheck size={20} color="#be185d" />
          <div>
            <div style={st.brand}>PracticeLab — Auditor</div>
            <div style={st.tagline}>Charts arrive coded. Auditors find what is wrong.</div>
          </div>
        </div>
        <input
          style={st.nameInput}
          value={trainer}
          onChange={e => setTrainer(e.target.value)}
          aria-label="Your name"
        />
      </header>

      <nav style={st.tabs}>
        {TABS.map(t => {
          const Icon = t.icon
          const on = t.key === active
          return (
            <button
              key={t.key}
              onClick={() => navigate(`/trainer/auditor/${t.key}`)}
              style={{ ...st.tab, ...(on ? st.tabOn : {}) }}
            >
              <Icon size={14} /> {t.label}
            </button>
          )
        })}
      </nav>

      <main style={st.main}>
        {active === 'batches' && <AuditBatches trainer={trainer} />}
        {active === 'keys' && <AuditKeys trainer={trainer} />}
        {active === 'analytics' && <AuditAnalytics />}
        {active === 'config' && <AuditConfig trainer={trainer} />}
      </main>
    </div>
  )
}

const st: Record<string, React.CSSProperties> = {
  page: { fontFamily: 'system-ui, sans-serif', minHeight: '100vh', background: '#f9fafb' },
  header: {
    display: 'flex', alignItems: 'center', gap: 18, padding: '16px 26px',
    background: '#fff', borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap',
  },
  back: { display: 'flex', alignItems: 'center', gap: 3, color: '#6b7280', fontSize: 13, textDecoration: 'none' },
  brandWrap: { display: 'flex', alignItems: 'center', gap: 10 },
  brand: { fontSize: 16, fontWeight: 800, color: '#111' },
  tagline: { fontSize: 12, color: '#9ca3af' },
  nameInput: {
    marginLeft: 'auto', fontSize: 12.5, padding: '7px 11px',
    border: '1px solid #e5e7eb', borderRadius: 8, width: 160, outline: 'none',
  },
  tabs: { display: 'flex', gap: 6, padding: '12px 26px 0', background: '#fff', borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap' },
  tab: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '9px 15px',
    border: 'none', borderBottom: '2px solid transparent', background: 'none',
    cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#6b7280',
  },
  tabOn: { color: '#be185d', borderBottomColor: '#be185d' },
  main: { padding: '26px', maxWidth: 1180, margin: '0 auto' },
}
