import { useState, useEffect } from 'react'
import { useSmartBack } from '../hooks/useSmartBack'
import { ChevronLeft, TrendingUp, TrendingDown, PieChart } from 'lucide-react'
import { getAnalytics } from '../api'

export function ChartLibraryAnalytics() {
  const goBack = useSmartBack('/trainer/chart-management')
  const [data, setData] = useState<any>(null)

  useEffect(() => { getAnalytics().then(setData) }, [])

  if (!data) return <div style={styles.center}>Loading analytics...</div>

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={() => goBack()}><ChevronLeft size={16} /> Back</button>
        <span style={styles.title}>Analytics</span>
      </div>
      <div style={styles.content}>

        {/* By specialty */}
        <Section icon={<PieChart size={18} color="#d97706" />} title="Charts by Specialty">
          <table style={styles.table}>
            <thead><tr>
              <th style={styles.th}>Specialty</th>
              <th style={styles.th}>Charts</th>
              <th style={styles.th}>Total Views</th>
            </tr></thead>
            <tbody>
              {data.by_specialty.map((r: any) => (
                <tr key={r.specialty} style={styles.tr}>
                  <td style={styles.td}>{r.specialty}</td>
                  <td style={styles.td}>{r.chart_count}</td>
                  <td style={styles.td}>{r.total_views}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <div style={styles.twoCol}>
          <Section icon={<TrendingUp size={18} color="#16a34a" />} title="Most Viewed">
            {data.most_viewed.map((r: any) => (
              <div key={r.chart_number} style={styles.analyticsRow}>
                <span style={styles.chartNum}>{r.chart_number}</span>
                <span style={styles.cat}>{r.category}</span>
                <span style={styles.views}>{r.views} views</span>
              </div>
            ))}
          </Section>
          <Section icon={<TrendingDown size={18} color="#dc2626" />} title="Least Viewed">
            {data.least_viewed.map((r: any) => (
              <div key={r.chart_number} style={styles.analyticsRow}>
                <span style={styles.chartNum}>{r.chart_number}</span>
                <span style={styles.cat}>{r.category}</span>
                <span style={styles.views}>{r.views} views</span>
              </div>
            ))}
          </Section>
        </div>

      </div>
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 15 }}>{icon}{title}</div>
      {children}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '6px 12px', cursor: 'pointer', fontSize: 13 },
  title: { fontWeight: 700, fontSize: 18 },
  content: { maxWidth: 1000, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 20 },
  twoCol: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '8px 12px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '8px 12px', fontSize: 13 },
  analyticsRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid #f3f4f6' },
  chartNum: { fontWeight: 700, fontSize: 13, minWidth: 60 },
  cat: { flex: 1, fontSize: 13, color: '#6b7280' },
  views: { fontSize: 13, color: '#374151', fontWeight: 600 },
  center: { textAlign: 'center', padding: 80, color: '#9ca3af', fontFamily: 'system-ui' },
}
