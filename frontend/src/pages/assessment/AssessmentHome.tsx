import { useState } from 'react'
import { ArrowLeft, BarChart2, Lock, PlusSquare, Clock, Upload, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { PoolSummaryView } from './PoolSummaryView'
import { UploadView } from './UploadView'
import { QuestionBankView } from './QuestionBankView'
import { GenerateView } from './GenerateView'
import { AssessmentHistoryView } from './AssessmentHistoryView'
import { SessionsView } from './SessionsView'

type Tab = 'summary' | 'upload' | 'bank' | 'generate' | 'sessions' | 'history'

export function AssessmentHome() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('summary')

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'summary', label: 'Pool Summary', icon: <BarChart2 size={15} /> },
    { id: 'upload', label: 'Upload Questions', icon: <Upload size={15} /> },
    { id: 'bank', label: 'Question Bank', icon: <Lock size={15} /> },
    { id: 'generate', label: 'Generate', icon: <PlusSquare size={15} /> },
    { id: 'sessions', label: 'Sessions', icon: <Users size={15} /> },
    { id: 'history', label: 'History', icon: <Clock size={15} /> },
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
        {tabs.map(tab => (
          <button
            key={tab.id}
            style={{ ...styles.tabBtn, ...(activeTab === tab.id ? styles.tabBtnActive : {}) }}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      <div style={styles.content}>
        {activeTab === 'summary' && <PoolSummaryView />}
        {activeTab === 'upload' && <UploadView />}
        {activeTab === 'bank' && <QuestionBankView />}
        {activeTab === 'generate' && <GenerateView />}
        {activeTab === 'sessions' && <SessionsView />}
        {activeTab === 'history' && <AssessmentHistoryView />}
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
  tabBar: { display: 'flex', gap: 4, padding: '12px 28px', background: 'rgba(255,255,255,0.5)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderBottom: '1px solid rgba(255,255,255,0.4)' },
  tabBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 10, border: '1px solid transparent', background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#6b7280', transition: 'all 0.15s' },
  tabBtnActive: { background: 'rgba(124,58,237,0.1)', border: '1px solid rgba(124,58,237,0.2)', color: '#7c3aed' },
  content: { maxWidth: 1100, margin: '0 auto', padding: '28px 24px' },
}
