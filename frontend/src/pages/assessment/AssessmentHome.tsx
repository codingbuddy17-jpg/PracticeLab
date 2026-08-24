import { useState } from 'react'
import { ArrowLeft, BarChart2, Lock, PlusSquare, Clock, Upload, Users, TrendingUp } from 'lucide-react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { PoolSummaryView } from './PoolSummaryView'
import { UploadView } from './UploadView'
import { QuestionBankView } from './QuestionBankView'
import { GenerateView } from './GenerateView'
import { AssessmentHistoryView } from './AssessmentHistoryView'
import { SessionsView } from './SessionsView'
import { AnalyticsView } from './AnalyticsView'

type Tab = 'summary' | 'upload' | 'bank' | 'generate' | 'sessions' | 'history' | 'analytics'

const TAB_IDS: Tab[] = ['summary', 'upload', 'bank', 'generate', 'sessions', 'history', 'analytics']
const DEFAULT_TAB: Tab = 'summary'

/** Every tab has a URL, so it can be opened, bookmarked and shared like one. */
export const tabPath = (tab: Tab) => `/trainer/assessment/${tab}`

export function AssessmentHome() {
  const navigate = useNavigate()

  // The tab lives in the URL rather than in state. It was component state, so
  // there was no address for "Sessions" — and a browser can only open a LINK in
  // a new tab. Now Cmd/Ctrl-click opens one in its own browser tab, leaving a
  // half-filled Generate form untouched in the original; the Back button steps
  // between tabs instead of leaving the module; and a tab can be bookmarked or
  // sent to someone.
  const { tab } = useParams<{ tab?: string }>()
  const activeTab: Tab = TAB_IDS.includes(tab as Tab) ? (tab as Tab) : DEFAULT_TAB
  // A specialty carried across tabs by the Pool Summary shortcuts, so
  // "this pool is thin" leads straight to fixing it rather than making the
  // trainer re-pick the specialty they were just looking at. Cleared on any
  // manual tab click, so it only ever applies to the jump that set it.
  const [handoffSpecialty, setHandoffSpecialty] = useState<string | undefined>()

  function jumpTo(target: Tab, specialty: string) {
    setHandoffSpecialty(specialty)
    navigate(tabPath(target))
  }

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'summary', label: 'Pool Summary', icon: <BarChart2 size={15} /> },
    { id: 'upload', label: 'Upload Questions', icon: <Upload size={15} /> },
    { id: 'bank', label: 'Question Bank', icon: <Lock size={15} /> },
    { id: 'generate', label: 'Generate', icon: <PlusSquare size={15} /> },
    { id: 'sessions', label: 'Sessions', icon: <Users size={15} /> },
    { id: 'history', label: 'History', icon: <Clock size={15} /> },
    { id: 'analytics', label: 'Analytics', icon: <TrendingUp size={15} /> },
  ]

  return (
    <div style={styles.container}>
      <div style={styles.blob1} />
      <div style={styles.blob2} />

      <div style={styles.topBar}>
        <div style={styles.topBarLeft}>
          <button style={styles.backBtn} onClick={() => navigate('/trainer')}>
            <ArrowLeft size={16} />
            Trainer Home
          </button>
          <div style={styles.divider} />
          <div style={styles.pageTitle}>Assessments</div>
        </div>
        <span style={styles.portalBadge}>MCQ Engine</span>
      </div>

      <div style={styles.tabBar}>
        {tabs.map(t => (
          <Link
            key={t.id}
            to={tabPath(t.id)}
            // A real href is what makes Cmd/Ctrl-click and "Open in new tab"
            // work. The handoff is cleared here so it only ever applies to the
            // jump that set it, never to a tab the trainer picked themselves.
            onClick={() => setHandoffSpecialty(undefined)}
            style={{
              ...styles.tabBtn,
              ...(activeTab === t.id ? styles.tabBtnActive : {}),
              textDecoration: 'none',
            }}
          >
            {t.icon}
            {t.label}
          </Link>
        ))}
      </div>

      <div style={styles.content}>
        {activeTab === 'summary' && <PoolSummaryView onJump={jumpTo} initialSpecialty={handoffSpecialty} />}
        {activeTab === 'upload' && <UploadView initialSpecialty={handoffSpecialty} onJump={jumpTo} />}
        {activeTab === 'bank' && <QuestionBankView />}
        {activeTab === 'generate' && <GenerateView initialSpecialty={handoffSpecialty} onJump={jumpTo} />}
        {activeTab === 'sessions' && <SessionsView />}
        {activeTab === 'history' && <AssessmentHistoryView />}
        {activeTab === 'analytics' && <AnalyticsView />}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: 'linear-gradient(135deg, #ede9fe 0%, #dbeafe 50%, #d1fae5 100%)', fontFamily: 'system-ui, sans-serif', position: 'relative', overflow: 'hidden' },
  blob1: { position: 'absolute', top: -80, left: -80, width: 340, height: 340, borderRadius: '50%', background: 'radial-gradient(circle, #a78bfa 0%, #7c3aed 60%, transparent 100%)', opacity: 0.2, filter: 'blur(60px)', pointerEvents: 'none' },
  blob2: { position: 'absolute', bottom: 40, right: -60, width: 280, height: 280, borderRadius: '50%', background: 'radial-gradient(circle, #60a5fa 0%, #3b82f6 60%, transparent 100%)', opacity: 0.18, filter: 'blur(60px)', pointerEvents: 'none' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 28px', background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.5)', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  topBarLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  backBtn: { display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontSize: 13, color: '#4b5563', fontWeight: 600 },
  divider: { width: 1, height: 20, background: '#e5e7eb' },
  pageTitle: { fontSize: 16, fontWeight: 800, color: '#111', letterSpacing: -0.3 },
  portalBadge: { fontSize: 11, fontWeight: 700, background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', color: '#fff', padding: '4px 12px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  // Same tab treatment as PracticeLab and the auditor. The accent colour
  // differs per module — that is identity — but the shape must not: three
  // different tab designs for one control read as three different products.
  // The 3px rule and the faint wash come from PracticeLab, where a 2px line
  // proved easy to miss against the bar's own 1px bottom border.
  tabBar: { display: 'flex', gap: 0, padding: '0 24px', alignItems: 'flex-end', background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderBottom: '1px solid #e5e7eb' },
  tabBtn: { display: 'flex', alignItems: 'center', gap: 6, position: 'relative' as const, padding: '13px 22px 11px', fontSize: 14, fontWeight: 700, letterSpacing: -0.1, color: '#64748b', background: 'none', border: 'none', borderBottom: '3px solid transparent', cursor: 'pointer', transition: 'color 0.15s, background 0.15s' },
  tabBtnActive: { color: '#7c3aed', borderBottom: '3px solid #7c3aed', background: 'rgba(124,58,237,0.07)', borderTopLeftRadius: 8, borderTopRightRadius: 8 },
  content: { maxWidth: 1100, margin: '0 auto', padding: '28px 24px' },
}
