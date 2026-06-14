import { FileCheck } from 'lucide-react'
import { SPECIALTY_COLORS } from '../../theme'
import styles from './styles'

export function HomeView({ batches, overview, loading, onOpen, statusColor, onCreateBatch }: any) {
  if (loading) return (
    <div style={styles.center}>
      <div style={{ width: 24, height: 24, border: '3px solid #e5e7eb', borderTop: '3px solid #0f766e', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    </div>
  )

  const openBatches = batches.filter((b: any) => b.status === 'Open')
  const closedBatches = batches.filter((b: any) => b.status !== 'Open')

  return (
    <div>
      {overview && overview.total_batches > 0 && (
        <div style={styles.statsRow}>
          {[
            { label: 'Total Batches', value: overview.total_batches },
            { label: 'Open', value: overview.open_batches ?? overview.total_batches - overview.complete_batches, color: '#2563eb' },
            { label: 'Closed', value: overview.complete_batches, color: '#16a34a' },
            { label: 'Total Graded', value: overview.total_graded },
            { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%`, color: overview.overall_pass_rate >= 80 ? '#16a34a' : overview.overall_pass_rate >= 60 ? '#d97706' : '#dc2626' },
          ].map(s => (
            <div key={s.label} style={styles.statCard}>
              <div style={{ ...styles.statValue, color: (s as any).color || '#111' }}>{s.value}</div>
              <div style={styles.statLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Batches</span>
      </div>

      {batches.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={40} color="#d1d5db" />
          <p style={{ color: '#6b7280', marginBottom: 4 }}>No batches yet.</p>
          <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 16 }}>
            Start by uploading answer keys for your charts, then create a batch to assign them to coders.
          </p>
          <button style={styles.primaryBtn} onClick={onCreateBatch}>Create your first batch</button>
        </div>
      ) : (
        <div style={styles.batchList}>
          {openBatches.length > 0 && openBatches.map((b: any) => <BatchRow key={b.id} b={b} onOpen={onOpen} statusColor={statusColor} />)}
          {closedBatches.length > 0 && openBatches.length > 0 && (
            <div style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 1, padding: '10px 4px 4px' }}>Closed</div>
          )}
          {closedBatches.length > 0 && closedBatches.map((b: any) => <BatchRow key={b.id} b={b} onOpen={onOpen} statusColor={statusColor} />)}
        </div>
      )}
    </div>
  )
}

function BatchRow({ b, onOpen, statusColor }: any) {
  const sc = SPECIALTY_COLORS[b.specialty as keyof typeof SPECIALTY_COLORS]
  const isOpen = b.status === 'Open'

  // Derive a next-action hint for open batches
  let hint = ''
  if (isOpen) {
    if ((b.allocation_cycles ?? 0) === 0) hint = 'Run first cycle →'
    else if (b.days_open != null && b.days_open > 0) hint = 'Awaiting submissions'
  }

  return (
    <div className="pl-batch-row" style={styles.batchRow} onClick={() => onOpen(b.id)}>
      <div style={{ ...styles.batchAccent, background: sc?.bg || '#6b7280' }} />
      <div style={styles.batchInfo}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={styles.batchName}>{b.name}</div>
          {hint && (
            <span style={{ fontSize: 11, fontWeight: 700, color: '#4f46e5', background: '#eef2ff', padding: '2px 8px', borderRadius: 10 }}>{hint}</span>
          )}
        </div>
        <div style={styles.batchMeta}>
          <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151' }}>{b.specialty}</span>
          <span style={styles.metaText}>{b.coder_count} coder{b.coder_count !== 1 ? 's' : ''}</span>
          <span style={styles.metaText}>{b.allocation_cycles ?? 0} cycle{b.allocation_cycles !== 1 ? 's' : ''}</span>
          {b.days_open != null && (
            <span style={{ ...styles.metaText, color: b.days_open > 14 ? '#d97706' : '#6b7280' }}>open {b.days_open}d</span>
          )}
          <span style={styles.metaText}>by {b.created_by}</span>
          {b.force_closed && <span style={{ ...styles.metaText, color: '#dc2626', fontWeight: 700 }}>force-closed</span>}
        </div>
      </div>
      <span style={{ ...styles.statusPill, color: statusColor(b.status), borderColor: statusColor(b.status) }}>{b.status}</span>
    </div>
  )
}
