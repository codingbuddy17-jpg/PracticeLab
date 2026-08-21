import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, Settings } from 'lucide-react'
import { AuditBatches } from './auditor/AuditBatches'
import { AuditKeys } from './auditor/AuditKeys'
import { AuditConfig } from './auditor/AuditConfig'
import { AuditAnalytics } from './auditor/AuditAnalytics'
import { trainerName } from './practicelab/shared'

/**
 * PracticeLab — Auditor. A sibling of the coder module that shares charts and
 * answer keys with it and nothing else: separate storage, separate screens,
 * separate analytics, so audit work can never leak into coder reporting.
 */

// Score Config is not day-to-day work — set once, revisited rarely — so it sits
// behind the settings control rather than taking a quarter of the tab row.
const TABS = [
  { key: 'batches', label: 'Audit Batches' },
  { key: 'keys', label: 'Audit Keys' },
  { key: 'analytics', label: 'Analytics' },
] as const

type TabKey = typeof TABS[number]['key'] | 'config'

const KNOWN: string[] = [...TABS.map(t => t.key), 'config']

export function TrainerAuditor() {
  const { tab } = useParams<{ tab?: string }>()
  const active = (tab && KNOWN.includes(tab) ? tab : 'batches') as TabKey

  // Same source the PracticeLab screens read. A separate key here would mean a
  // trainer who set their name once still shows up as "Trainer" on audit work.
  const trainer = trainerName()

  return (
    <div style={st.page}>
      <header style={st.header}>
        <Link to="/trainer" style={st.back}><ChevronLeft size={15} /> Trainer</Link>
        <div style={st.brand}>PracticeLab — Auditor</div>
      </header>

      <nav style={st.tabs}>
        {/* Links, not buttons. The URL was already right — /trainer/auditor/keys
            — but a button navigating in its onClick gives the browser nothing
            to act on, so Cmd/Ctrl-click and "Open in new tab" did nothing. The
            Assessment module has done it this way from the start. */}
        {TABS.map(t => (
          <Link
            key={t.key}
            to={`/trainer/auditor/${t.key}`}
            style={{ ...st.tab, ...(t.key === active ? st.tabOn : {}), textDecoration: 'none' }}
          >
            {t.label}
          </Link>
        ))}
        <Link
          to="/trainer/auditor/config"
          title="Score Config"
          style={{ ...st.settingsBtn, ...(active === 'config' ? st.settingsBtnOn : {}), textDecoration: 'none' }}
        >
          <Settings size={15} /> Score Config
        </Link>
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
  brand: { fontSize: 16, fontWeight: 800, color: '#111' },
  tabs: {
    display: 'flex', gap: 6, padding: '12px 26px 0', background: '#fff',
    borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap', alignItems: 'center',
  },
  tab: {
    padding: '9px 15px', border: 'none', borderBottom: '2px solid transparent',
    background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#6b7280',
  },
  tabOn: { color: '#be185d', borderBottom: '2px solid #be185d' },
  settingsBtn: {
    marginLeft: 'auto', marginBottom: 8, display: 'flex', alignItems: 'center',
    gap: 6, padding: '7px 13px', border: '1px solid #e5e7eb', borderRadius: 8,
    background: '#fff', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
    color: '#6b7280',
  },
  settingsBtnOn: { borderColor: '#be185d', color: '#be185d', background: '#fdf2f8' },
  main: { padding: '26px', maxWidth: 1180, margin: '0 auto' },
}
