import { useState } from 'react'
import { FileCheck, Search, X } from 'lucide-react'
import { SPECIALTY_COLORS } from '../../theme'
import styles from './styles'

type StatusFilter = 'open' | 'closed' | 'all'

export function HomeView({ batches, directAssignments, overview, loading, onOpen, statusColor, onCreateBatch, onCreateDirect }: any) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open')
  const [search, setSearch] = useState('')

  if (loading) return (
    <div style={styles.center}>
      <div style={{ width: 24, height: 24, border: '3px solid #e5e7eb', borderTop: '3px solid #0f766e', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    </div>
  )

  function filterList(list: any[]) {
    let out = list
    if (statusFilter === 'open')   out = out.filter((b: any) => b.status === 'Open')
    if (statusFilter === 'closed') out = out.filter((b: any) => b.status !== 'Open')
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      out = out.filter((b: any) =>
        b.name.toLowerCase().includes(q) ||
        b.specialty?.toLowerCase().includes(q) ||
        b.created_by?.toLowerCase().includes(q)
      )
    }
    return out
  }

  const openCount  = batches.filter((b: any) => b.status === 'Open').length
  const closedCount = batches.filter((b: any) => b.status !== 'Open').length
  const filteredBatches = filterList(batches)
  const filteredDirect  = filterList(directAssignments ?? [])

  const tabs: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'open',   label: 'Open',   count: openCount },
    { key: 'closed', label: 'Closed', count: closedCount },
    { key: 'all',    label: 'All',    count: batches.length },
  ]

  return (
    <div>
      {/* ── KPI strip ── */}
      {overview && overview.total_batches > 0 && (
        <div style={styles.statsRow}>
          {[
            { label: 'Total Batches',    value: overview.total_batches },
            { label: 'Open',             value: overview.open_batches ?? openCount, color: '#2563eb' },
            { label: 'Closed',           value: overview.complete_batches ?? closedCount, color: '#16a34a' },
            { label: 'Total Graded',     value: overview.total_graded },
            { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%`,
              color: overview.overall_pass_rate >= 80 ? '#16a34a' : overview.overall_pass_rate >= 60 ? '#d97706' : '#dc2626' },
          ].map(s => (
            <div key={s.label} style={styles.statCard}>
              <div style={{ ...styles.statValue, color: (s as any).color || '#111' }}>{s.value}</div>
              <div style={styles.statLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Filter bar: status tabs + search ── */}
      {batches.length > 0 && (
        <div style={s.filterBar}>
          {/* Status tabs */}
          <div style={s.statusTabs}>
            {tabs.map(t => (
              <button
                key={t.key}
                style={{ ...s.statusTab, ...(statusFilter === t.key ? s.statusTabActive : {}) }}
                onClick={() => setStatusFilter(t.key)}
              >
                {t.label}
                <span style={{ ...s.countBadge, ...(statusFilter === t.key ? s.countBadgeActive : {}) }}>
                  {t.count}
                </span>
              </button>
            ))}
          </div>

          {/* Search */}
          <div style={s.searchWrap}>
            <Search size={14} color="#9ca3af" style={{ flexShrink: 0 }} />
            <input
              style={s.searchInput}
              placeholder="Search by name, specialty, creator…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button style={s.clearBtn} onClick={() => setSearch('')}>
                <X size={13} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Batch list ── */}
      {batches.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={40} color="#d1d5db" />
          <p style={{ color: '#6b7280', marginBottom: 4 }}>No batches yet.</p>
          <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 16 }}>
            Start by uploading answer keys for your charts, then create a batch to assign them to coders.
          </p>
          <button style={styles.primaryBtn} onClick={onCreateBatch}>Create your first batch</button>
        </div>
      ) : filteredBatches.length === 0 ? (
        <div style={{ ...styles.empty, padding: '32px 0' }}>
          <p style={{ color: '#9ca3af', fontSize: 13 }}>
            {search ? `No batches match "${search}"` : `No ${statusFilter} batches.`}
          </p>
          {search && (
            <button style={{ ...styles.outlineBtn, fontSize: 12, marginTop: 4 }} onClick={() => setSearch('')}>
              Clear search
            </button>
          )}
        </div>
      ) : (
        <div style={styles.batchList}>
          {filteredBatches.map((b: any) => (
            <BatchRow key={b.id} b={b} onOpen={onOpen} statusColor={statusColor} />
          ))}
        </div>
      )}

      {/* ── Direct Assignments ── */}
      {((directAssignments?.length > 0) || onCreateDirect) && (
        <>
          <div style={{ ...styles.sectionHeader, marginTop: 32 }}>
            <span style={styles.sectionTitle}>Direct Assignments</span>
            {onCreateDirect && (
              <button
                style={{ ...styles.outlineBtn, fontSize: 12, color: '#4f46e5', borderColor: '#c7d2fe' }}
                onClick={onCreateDirect}
              >
                + New Assignment
              </button>
            )}
          </div>

          {!directAssignments?.length ? (
            <div style={{ fontSize: 12, color: '#9ca3af', padding: '8px 4px 4px' }}>
              No direct assignments yet — use this for one-off chart assignments to specific coder(s) without a full batch workflow.
            </div>
          ) : filteredDirect.length === 0 ? (
            <div style={{ fontSize: 13, color: '#9ca3af', padding: '12px 4px' }}>
              No {statusFilter !== 'all' ? statusFilter : ''} direct assignments
              {search ? ` matching "${search}"` : ''}.
            </div>
          ) : (
            <div style={styles.batchList}>
              {filteredDirect.map((b: any) => (
                <BatchRow key={b.id} b={b} onOpen={onOpen} statusColor={statusColor} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function BatchRow({ b, onOpen, statusColor }: any) {
  const sc = SPECIALTY_COLORS[b.specialty as keyof typeof SPECIALTY_COLORS]
  const isOpen = b.status === 'Open'

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
            <span style={{ fontSize: 11, fontWeight: 700, color: '#4f46e5', background: '#eef2ff', padding: '2px 8px', borderRadius: 10 }}>
              {hint}
            </span>
          )}
        </div>
        <div style={styles.batchMeta}>
          <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151' }}>{b.specialty}</span>
          <span style={styles.metaText}>{b.coder_count} coder{b.coder_count !== 1 ? 's' : ''}</span>
          <span style={styles.metaText}>{b.allocation_cycles ?? 0} cycle{b.allocation_cycles !== 1 ? 's' : ''}</span>
          {b.days_open != null && (
            <span style={{ ...styles.metaText, color: b.days_open > 14 ? '#d97706' : '#6b7280' }}>
              open {b.days_open}d
            </span>
          )}
          <span style={styles.metaText}>by {b.created_by}</span>
          {b.force_closed && (
            <span style={{ ...styles.metaText, color: '#dc2626', fontWeight: 700 }}>force-closed</span>
          )}
        </div>
      </div>
      <span style={{ ...styles.statusPill, color: statusColor(b.status), borderColor: statusColor(b.status) }}>
        {b.status}
      </span>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  filterBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  statusTabs: {
    display: 'flex',
    gap: 2,
    background: '#f1f5f9',
    borderRadius: 10,
    padding: 3,
  },
  statusTab: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 14px',
    borderRadius: 8,
    border: 'none',
    background: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    color: '#6b7280',
    transition: 'all 0.15s',
  },
  statusTabActive: {
    background: '#fff',
    color: '#111',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
  },
  countBadge: {
    fontSize: 11,
    fontWeight: 700,
    background: '#e2e8f0',
    color: '#64748b',
    padding: '1px 7px',
    borderRadius: 20,
    minWidth: 20,
    textAlign: 'center' as const,
  },
  countBadgeActive: {
    background: '#0f766e',
    color: '#fff',
  },
  searchWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    minWidth: 200,
    maxWidth: 340,
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: '7px 12px',
  },
  searchInput: {
    flex: 1,
    border: 'none',
    outline: 'none',
    fontSize: 13,
    color: '#111',
    background: 'transparent',
    fontFamily: 'system-ui, sans-serif',
  },
  clearBtn: {
    display: 'flex',
    alignItems: 'center',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: '#9ca3af',
    padding: 2,
  },
}
