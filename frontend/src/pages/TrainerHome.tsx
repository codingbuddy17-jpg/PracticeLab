import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Upload, BarChart2, FileText, Settings, BookOpen, Flag } from 'lucide-react'
import { getUnresolvedCount } from '../api'

export function TrainerHome() {
  const [unresolvedCount, setUnresolvedCount] = useState(0)

  useEffect(() => {
    getUnresolvedCount().then(setUnresolvedCount).catch(() => {})
  }, [])

  const cards = [
    { to: '/trainer/upload', icon: <Upload size={26} />, title: 'Upload Charts', desc: 'Bulk upload new charts with metadata', color: '#4f46e5', light: '#ede9fe', badge: null },
    { to: '/trainer/charts', icon: <Settings size={26} />, title: 'Manage Charts', desc: 'Edit, retire, restore and add files to charts', color: '#0891b2', light: '#cffafe', badge: null },
    { to: '/trainer/reports', icon: <FileText size={26} />, title: 'Reports', desc: 'Filter, view and export the chart library', color: '#16a34a', light: '#dcfce7', badge: null },
    { to: '/trainer/analytics', icon: <BarChart2 size={26} />, title: 'Analytics', desc: 'Most viewed, least viewed, specialty breakdown', color: '#d97706', light: '#fef3c7', badge: null },
    { to: '/trainer/feedback', icon: <Flag size={26} />, title: 'Feedback', desc: 'Review issues flagged by coders on charts', color: '#dc2626', light: '#fee2e2', badge: unresolvedCount > 0 ? unresolvedCount : null },
  ]

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <div style={styles.logo}><BookOpen size={22} color="#4f46e5" /><span style={styles.logoText}>Chart Viewer</span></div>
        <span style={styles.portalBadge}>Trainer Portal</span>
      </div>
      <div style={styles.content}>
        <div style={styles.welcomeText}>What would you like to do?</div>
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
  content: { maxWidth: 780, margin: '0 auto', padding: '40px 24px' },
  welcomeText: { fontSize: 22, fontWeight: 800, color: '#111', marginBottom: 24, letterSpacing: -0.5 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 18 },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '24px 20px', display: 'flex', flexDirection: 'column', gap: 10, textDecoration: 'none', color: 'inherit', cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', transition: 'box-shadow 0.15s, transform 0.1s' },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  iconWrap: { width: 50, height: 50, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  cardBadge: { background: '#fee2e2', color: '#dc2626', fontSize: 12, fontWeight: 800, padding: '3px 9px', borderRadius: 20, minWidth: 24, textAlign: 'center' as const },
  cardTitle: { fontWeight: 800, fontSize: 16, color: '#111' },
  cardDesc: { fontSize: 13, color: '#6b7280', lineHeight: 1.5 },
}
