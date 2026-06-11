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

        {/* Bento grid */}
        <div style={styles.bentoGrid}>

          {/* Cell 1 — main identity cell */}
          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellMain }}>
            <div style={styles.bentoTag}>Assessment Engine</div>
            <div style={styles.bentoTitle}>
              <GraduationCap size={20} style={{ flexShrink: 0 }} />
              PracticeLab
            </div>
            <div style={styles.bentoSubtitle}>
              Create batches · Auto-grade · DRG review · Reports
            </div>
            <div style={styles.bentoCta}>
              Open <ChevronRight size={14} strokeWidth={2.5} />
            </div>
          </Link>

          {/* Cell 2 — Batches */}
          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: '#f8faff' }}>
            <div style={styles.bentoStatNum}>{plStats?.total_batches ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Total Batches</div>
            <div style={styles.bentoStatSub}>{plStats?.complete_batches ?? '—'} complete</div>
          </Link>

          {/* Cell 3 — Graded */}
          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: '#fdf8ff' }}>
            <div style={styles.bentoStatNum}>{plStats?.total_graded ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Submissions Graded</div>
            <div style={styles.bentoStatSub}>across all batches</div>
          </Link>

          {/* Cell 4 — Pass rate — spans full width of right column bottom */}
          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate }}>
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={styles.bentoPassRateNum}>
                  {plStats ? `${plStats.overall_pass_rate}%` : '—'}
                </div>
                <div style={styles.bentoStatLabel}>Overall Pass Rate</div>
              </div>
              {/* Mini bar */}
              {plStats && (
                <div style={styles.bentoBarWrap}>
                  <div style={{ ...styles.bentoBar, width: `${plStats.overall_pass_rate}%` }} />
                </div>
              )}
            </div>
          </Link>

        </div>
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

  // Bento grid
  bentoGrid: {
    display: 'grid',
    gridTemplateColumns: '1.6fr 1fr 1fr',
    gridTemplateRows: 'auto auto',
    gap: 10,
  },
  bentoCell: {
    borderRadius: 14, border: '1px solid #e5e7eb',
    textDecoration: 'none', color: 'inherit',
    padding: '22px 24px', display: 'flex', flexDirection: 'column',
    gap: 8, cursor: 'pointer',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
  },
  // Main cell — spans 2 rows
  bentoCellMain: {
    gridRow: '1 / 3',
    background: '#18181b',
    justifyContent: 'space-between',
    minHeight: 180,
  },
  bentoTag: {
    fontSize: 10, fontWeight: 700, letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
    color: '#71717a', alignSelf: 'flex-start',
  },
  bentoTitle: {
    display: 'flex', alignItems: 'center', gap: 10,
    fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.5,
  },
  bentoSubtitle: { fontSize: 12, color: '#52525b', lineHeight: 1.6 },
  bentoCta: {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', marginTop: 4,
    fontSize: 12, fontWeight: 700, color: '#fff',
    background: '#27272a', padding: '7px 14px',
    borderRadius: 8, border: '1px solid #3f3f46',
  },
  // Stat cells
  bentoCellStat: {
    display: 'flex', flexDirection: 'column', gap: 4,
    padding: '20px 22px',
  },
  bentoStatNum: { fontSize: 32, fontWeight: 800, color: '#111', letterSpacing: -1.5, lineHeight: 1 },
  bentoStatLabel: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  bentoStatSub: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
  // Pass rate cell — spans 2 cols
  bentoCellPassRate: {
    gridColumn: '2 / 4',
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
    padding: '18px 22px',
  },
  bentoPassRateRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20 },
  bentoPassRateNum: { fontSize: 32, fontWeight: 800, color: '#15803d', letterSpacing: -1.5, lineHeight: 1 },
  bentoBarWrap: { flex: 1, height: 8, background: '#dcfce7', borderRadius: 99, overflow: 'hidden' },
  bentoBar: { height: '100%', background: '#16a34a', borderRadius: 99, transition: 'width 0.6s ease' },
}
