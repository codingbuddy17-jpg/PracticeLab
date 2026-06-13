import { FileCheck } from 'lucide-react'
import { SPECIALTY_COLORS } from '../../theme'
import styles from './styles'

export function HomeView({ batches, overview, loading, onOpen, statusColor, onCreateBatch }: any) {
  if (loading) return (
    <div style={styles.center}>
      <div style={{ width: 24, height: 24, border: '3px solid #e5e7eb', borderTop: '3px solid #0f766e', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    </div>
  )
  return (
    <div>
      {overview && (
        <div style={styles.statsRow}>
          {[
            { label: 'Total Batches', value: overview.total_batches },
            { label: 'Open', value: overview.open_batches ?? overview.total_batches - overview.complete_batches },
            { label: 'Closed', value: overview.complete_batches },
            { label: 'Total Graded', value: overview.total_graded },
            { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%` },
          ].map(s => (
            <div key={s.label} style={styles.statCard}>
              <div style={styles.statValue}>{s.value}</div>
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
          <p>No batches yet.</p>
          <button style={styles.primaryBtn} onClick={onCreateBatch}>Create your first batch</button>
        </div>
      ) : (
        <div style={styles.batchList}>
          {batches.map((b: any) => {
            const sc = SPECIALTY_COLORS[b.specialty as keyof typeof SPECIALTY_COLORS]
            return (
              <div key={b.id} style={styles.batchRow} onClick={() => onOpen(b.id)}>
                <div style={{ ...styles.batchAccent, background: sc?.bg || '#6b7280' }} />
                <div style={styles.batchInfo}>
                  <div style={styles.batchName}>{b.name}</div>
                  <div style={styles.batchMeta}>
                    <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151' }}>{b.specialty}</span>
                    <span style={styles.metaText}>{b.coder_count} coders</span>
                    <span style={styles.metaText}>{b.allocation_cycles ?? 0} cycle{b.allocation_cycles !== 1 ? 's' : ''}</span>
                    {b.days_open != null && <span style={{ ...styles.metaText, color: b.days_open > 14 ? '#d97706' : '#6b7280' }}>open {b.days_open}d</span>}
                    <span style={styles.metaText}>by {b.created_by}</span>
                    {b.force_closed && <span style={{ ...styles.metaText, color: '#dc2626', fontWeight: 700 }}>force-closed</span>}
                  </div>
                </div>
                <span style={{ ...styles.statusPill, color: statusColor(b.status), borderColor: statusColor(b.status) }}>{b.status}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
