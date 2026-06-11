import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Upload, BarChart2, FileText, Settings, BookOpen, Flag, GraduationCap, ChevronRight } from 'lucide-react'
import { getUnresolvedCount, getPLAnalyticsOverview } from '../api'

export function TrainerHome() {
  const [unresolvedCount, setUnresolvedCount] = useState(0)
  const [plStats, setPlStats] = useState<{ total_batches: number; complete_batches: number; total_graded: number; overall_pass_rate: number } | null>(null)

  useEffect(() => {
    getUnresolvedCount().then(setUnresolvedCount).catch(() => {})
    getPLAnalyticsOverview().then(setPlStats).catch(() => {})
  }, [])

  const cards = [
    { to: '/trainer/upload', icon: <Upload size={24} />, title: 'Upload Charts', desc: 'Bulk upload new charts with metadata', color: '#4f46e5', light: '#ede9fe', badge: null },
    { to: '/trainer/charts', icon: <Settings size={24} />, title: 'Manage Charts', desc: 'Edit, retire, restore and add files to charts', color: '#0891b2', light: '#cffafe', badge: null },
    { to: '/trainer/reports', icon: <FileText size={24} />, title: 'Reports', desc: 'Filter, view and export the chart library', color: '#16a34a', light: '#dcfce7', badge: null },
    { to: '/trainer/analytics', icon: <BarChart2 size={24} />, title: 'Analytics', desc: 'Most viewed, least viewed, specialty breakdown', color: '#d97706', light: '#fef3c7', badge: null },
    { to: '/trainer/feedback', icon: <Flag size={24} />, title: 'Feedback', desc: 'Review issues flagged by coders on charts', color: '#dc2626', light: '#fee2e2', badge: unresolvedCount > 0 ? unresolvedCount : null },
  ]

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <div style={styles.logo}>
          <BookOpen size={22} color="#4f46e5" />
          <span style={styles.logoText}>PracticeLab</span>
        </div>
        <span style={styles.portalBadge}>Trainer Portal</span>
      </div>

      <div style={styles.content}>
        <div style={styles.welcomeText}>What would you like to do?</div>

        {/* Utility tools grid */}
        <div style={styles.grid}>
          {cards.map(c => (
            <Link key={c.to} to={c.to} style={styles.card}>
              <div style={styles.cardTop}>
                <div style={{ ...styles.iconWrap, background: c.light, color: c.color }}>{c.icon}</div>
                {c.badge !== null && <span style={styles.cardBadge}>{c.badge}</span>}
              </div>
              <div style={styles.cardTitle}>{c.title}</div>
              <div style={styles.cardDesc}>{c.desc}</div>
            </Link>
          ))}
        </div>

        {/* PracticeLab featured banner */}
        <div style={styles.plDivider}>
          <span style={styles.plDividerLine} />
          <span style={styles.plDividerLabel}>Assessment Module</span>
          <span style={styles.plDividerLine} />
        </div>

        <Link to="/trainer/practicelab" style={styles.plBanner}>
          {/* Left dark panel */}
          <div style={styles.plLeft}>
            <div style={styles.plIconWrap}>
              <GraduationCap size={28} color="#fff" />
            </div>
            <div>
              <div style={styles.plTitle}>PracticeLab</div>
              <div style={styles.plDesc}>Assessment Engine</div>
            </div>
          </div>

          {/* Right white panel — stats */}
          <div style={styles.plRight}>
            <div style={styles.plStats}>
              {[
                { val: plStats?.total_batches ?? '—', label: 'Batches' },
                { val: plStats?.complete_batches ?? '—', label: 'Complete' },
                { val: plStats?.total_graded ?? '—', label: 'Graded' },
                { val: plStats ? `${plStats.overall_pass_rate}%` : '—', label: 'Pass Rate' },
              ].map((s, i) => (
                <div key={i} style={styles.plStat}>
                  <span style={styles.plStatVal}>{s.val}</span>
                  <span style={styles.plStatLabel}>{s.label}</span>
                </div>
              ))}
            </div>
            <div style={styles.plCta}>
              Open <ChevronRight size={15} strokeWidth={2.5} />
            </div>
          </div>
        </Link>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 28px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoText: { fontWeight: 800, fontSize: 18, color: '#111', letterSpacing: -0.5 },
  portalBadge: { fontSize: 12, fontWeight: 700, background: '#ede9fe', color: '#4f46e5', padding: '4px 12px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  content: { maxWidth: 860, margin: '0 auto', padding: '40px 24px' },
  welcomeText: { fontSize: 22, fontWeight: 800, color: '#111', marginBottom: 24, letterSpacing: -0.5 },

  // Utility cards
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 16 },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '22px 18px', display: 'flex', flexDirection: 'column', gap: 10, textDecoration: 'none', color: 'inherit', cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', transition: 'box-shadow 0.15s' },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  iconWrap: { width: 46, height: 46, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  cardBadge: { background: '#fee2e2', color: '#dc2626', fontSize: 12, fontWeight: 800, padding: '3px 9px', borderRadius: 20, minWidth: 24, textAlign: 'center' as const },
  cardTitle: { fontWeight: 800, fontSize: 15, color: '#111' },
  cardDesc: { fontSize: 13, color: '#6b7280', lineHeight: 1.5 },

  // Divider
  plDivider: { display: 'flex', alignItems: 'center', gap: 12, margin: '28px 0 20px' },
  plDividerLine: { flex: 1, height: 1, background: '#e5e7eb' },
  plDividerLabel: { fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 1, whiteSpace: 'nowrap' as const },

  // PracticeLab banner — split layout
  plBanner: {
    display: 'flex', alignItems: 'stretch', textDecoration: 'none',
    borderRadius: 16, overflow: 'hidden',
    border: '1px solid #e5e7eb',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    transition: 'box-shadow 0.2s',
    cursor: 'pointer',
  },
  // Dark left panel
  plLeft: {
    display: 'flex', flexDirection: 'column', justifyContent: 'center',
    gap: 14, padding: '28px 30px',
    background: '#0f172a', flexShrink: 0, minWidth: 200,
  },
  plIconWrap: {
    width: 48, height: 48, borderRadius: 12,
    background: 'rgba(255,255,255,0.1)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  plTitle: { fontWeight: 800, fontSize: 20, color: '#fff', letterSpacing: -0.5, lineHeight: 1 },
  plDesc: { fontSize: 12, color: '#94a3b8', fontWeight: 500, letterSpacing: 0.3 },
  // White right panel
  plRight: {
    flex: 1, display: 'flex', alignItems: 'center',
    justifyContent: 'space-between',
    padding: '24px 28px', background: '#fff',
  },
  plStats: { display: 'flex', gap: 36 },
  plStat: { display: 'flex', flexDirection: 'column', gap: 3 },
  plStatVal: { fontSize: 28, fontWeight: 800, color: '#111', letterSpacing: -1, lineHeight: 1 },
  plStatLabel: { fontSize: 11, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.6 },
  plCta: {
    display: 'flex', alignItems: 'center', gap: 4,
    fontSize: 13, fontWeight: 700, color: '#0f172a',
    background: '#f1f5f9', padding: '8px 16px',
    borderRadius: 8, flexShrink: 0,
  },
}
