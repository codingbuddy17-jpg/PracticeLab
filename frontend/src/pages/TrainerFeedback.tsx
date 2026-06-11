import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, BookOpen, CheckCircle, RotateCcw, Flag } from 'lucide-react'
import toast from 'react-hot-toast'
import { getFeedback, resolveFeedback, reopenFeedback } from '../api'
import { useLocalStorage } from '../hooks/useLocalStorage'

type FeedbackStatus = 'Open' | 'Resolved'

interface FeedbackItem {
  id: number
  chart_id: number
  chart_number: string
  reporter: string
  issues: string
  notes: string | null
  status: FeedbackStatus
  resolved_by: string | null
  resolved_at: string | null
  created_at: string
}

export function TrainerFeedback() {
  const navigate = useNavigate()
  const [trainerName] = useLocalStorage<string>('trainer_name', '')
  const [status, setStatus] = useState<FeedbackStatus | ''>('Open')
  const [chartFilter, setChartFilter] = useState('')
  const [items, setItems] = useState<FeedbackItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getFeedback({
        status: status || undefined,
        chart_number: chartFilter || undefined,
        page: 1,
        page_size: 100,
      })
      setItems(res.results)
      setTotal(res.total)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [status, chartFilter])

  const handleResolve = async (item: FeedbackItem) => {
    const resolver = trainerName || prompt('Your name:') || ''
    if (!resolver) return
    try {
      await resolveFeedback(item.id, resolver)
      toast.success(`Marked as resolved`)
      load()
    } catch { toast.error('Failed to resolve') }
  }

  const handleReopen = async (item: FeedbackItem) => {
    try {
      await reopenFeedback(item.id)
      toast.success('Reopened')
      load()
    } catch { toast.error('Failed to reopen') }
  }

  const openCount = items.filter(i => i.status === 'Open').length

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={() => navigate('/trainer')}><ChevronLeft size={16} /> Back</button>
        <div style={styles.logo}><BookOpen size={18} color="#4f46e5" /><span style={styles.logoText}>PracticeLab</span></div>
        <span style={styles.title}>Feedback</span>
        {openCount > 0 && <span style={styles.badge}>{openCount} open</span>}
      </div>

      <div style={styles.content}>
        <div style={styles.filterRow}>
          <select style={styles.select} value={status} onChange={e => setStatus(e.target.value as FeedbackStatus | '')}>
            <option value="Open">Open</option>
            <option value="Resolved">Resolved</option>
            <option value="">All</option>
          </select>
          <input
            style={styles.input}
            placeholder="Filter by chart number"
            value={chartFilter}
            onChange={e => setChartFilter(e.target.value)}
          />
          <span style={styles.count}>{total} item{total !== 1 ? 's' : ''}</span>
        </div>

        {loading ? (
          <div style={styles.center}>Loading...</div>
        ) : items.length === 0 ? (
          <div style={styles.emptyState}>
            <Flag size={40} color="#e5e7eb" />
            <div style={styles.emptyTitle}>No feedback yet</div>
            <div style={styles.emptySub}>Coders can flag charts with issues while viewing them.</div>
          </div>
        ) : (
          <div style={styles.list}>
            {items.map(item => (
              <div key={item.id} style={{ ...styles.card, borderLeft: `4px solid ${item.status === 'Open' ? '#ef4444' : '#22c55e'}` }}>
                <div style={styles.cardHeader}>
                  <div style={styles.cardLeft}>
                    <span style={styles.chartNum}>{item.chart_number}</span>
                    <span style={{ ...styles.statusBadge, background: item.status === 'Open' ? '#fee2e2' : '#dcfce7', color: item.status === 'Open' ? '#dc2626' : '#16a34a' }}>
                      {item.status}
                    </span>
                  </div>
                  <div style={styles.cardRight}>
                    <span style={styles.metaText}>Reported by <strong>{item.reporter}</strong></span>
                    <span style={styles.metaText}>{item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}</span>
                  </div>
                </div>

                <div style={styles.issuesList}>
                  {item.issues.split(', ').map((issue, i) => (
                    <span key={i} style={styles.issueChip}>{issue}</span>
                  ))}
                </div>

                {item.notes && <div style={styles.notes}>📝 {item.notes}</div>}

                {item.status === 'Resolved' && item.resolved_by && (
                  <div style={styles.resolvedNote}>
                    ✓ Resolved by <strong>{item.resolved_by}</strong>
                    {item.resolved_at ? ` on ${new Date(item.resolved_at).toLocaleDateString()}` : ''}
                  </div>
                )}

                <div style={styles.cardActions}>
                  {item.status === 'Open' ? (
                    <button style={styles.resolveBtn} onClick={() => handleResolve(item)}>
                      <CheckCircle size={14} /> Mark Resolved
                    </button>
                  ) : (
                    <button style={styles.reopenBtn} onClick={() => handleReopen(item)}>
                      <RotateCcw size={14} /> Reopen
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '13px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10 },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', fontSize: 13, color: '#374151' },
  logo: { display: 'flex', alignItems: 'center', gap: 6 },
  logoText: { fontWeight: 800, fontSize: 15, color: '#111' },
  title: { fontWeight: 700, fontSize: 17, color: '#111' },
  badge: { background: '#fee2e2', color: '#dc2626', fontSize: 12, fontWeight: 700, padding: '3px 10px', borderRadius: 20 },
  content: { maxWidth: 860, margin: '0 auto', padding: '24px' },
  filterRow: { display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, background: '#fff' },
  input: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 },
  count: { fontSize: 13, color: '#6b7280', marginLeft: 'auto' },
  center: { textAlign: 'center', padding: 60, color: '#9ca3af' },
  emptyState: { textAlign: 'center', padding: '60px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: 700, color: '#6b7280' },
  emptySub: { fontSize: 13, color: '#9ca3af', maxWidth: 340, lineHeight: 1.6 },
  list: { display: 'flex', flexDirection: 'column', gap: 12 },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  cardLeft: { display: 'flex', alignItems: 'center', gap: 10 },
  cardRight: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 },
  chartNum: { fontWeight: 800, fontSize: 16, color: '#111' },
  statusBadge: { fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20 },
  metaText: { fontSize: 12, color: '#9ca3af' },
  issuesList: { display: 'flex', flexWrap: 'wrap', gap: 6 },
  issueChip: { fontSize: 12, background: '#f3f4f6', color: '#374151', padding: '3px 10px', borderRadius: 20, border: '1px solid #e5e7eb' },
  notes: { fontSize: 13, color: '#6b7280', background: '#f9fafb', padding: '8px 12px', borderRadius: 6 },
  resolvedNote: { fontSize: 12, color: '#16a34a' },
  cardActions: { display: 'flex', gap: 8, paddingTop: 4 },
  resolveBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#dcfce7', color: '#16a34a', border: '1px solid #86efac', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  reopenBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#f3f4f6', color: '#6b7280', border: '1px solid #e5e7eb', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
}
