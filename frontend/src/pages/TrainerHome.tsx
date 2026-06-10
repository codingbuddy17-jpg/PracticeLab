import { Link } from 'react-router-dom'
import { Upload, BarChart2, FileText, Settings } from 'lucide-react'

export function TrainerHome() {
  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <span style={styles.title}>Chart Viewer — Trainer Portal</span>
      </div>
      <div style={styles.grid}>
        <Link to="/trainer/upload" style={styles.card}>
          <Upload size={28} color="#4f46e5" />
          <div style={styles.cardTitle}>Upload Charts</div>
          <div style={styles.cardDesc}>Bulk upload new charts with metadata</div>
        </Link>
        <Link to="/trainer/charts" style={styles.card}>
          <Settings size={28} color="#0891b2" />
          <div style={styles.cardTitle}>Manage Charts</div>
          <div style={styles.cardDesc}>Edit, retire, restore and add files to charts</div>
        </Link>
        <Link to="/trainer/reports" style={styles.card}>
          <FileText size={28} color="#16a34a" />
          <div style={styles.cardTitle}>Reports</div>
          <div style={styles.cardDesc}>Filter, view and export the chart library</div>
        </Link>
        <Link to="/trainer/analytics" style={styles.card}>
          <BarChart2 size={28} color="#d97706" />
          <div style={styles.cardTitle}>Analytics</div>
          <div style={styles.cardDesc}>Most viewed, least viewed, specialty breakdown</div>
        </Link>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { padding: '16px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  title: { fontWeight: 700, fontSize: 20 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 20, padding: 32, maxWidth: 900, margin: '0 auto' },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column', gap: 8, textDecoration: 'none', color: 'inherit', cursor: 'pointer', transition: 'box-shadow 0.15s' },
  cardTitle: { fontWeight: 700, fontSize: 16, color: '#111' },
  cardDesc: { fontSize: 13, color: '#6b7280', lineHeight: 1.5 },
}
