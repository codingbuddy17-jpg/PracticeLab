import { useState } from 'react'
import toast from 'react-hot-toast'
import { FileCheck, Search, X, ChevronDown, ChevronRight, FileText, Download } from 'lucide-react'
import { SPECIALTY_COLORS } from '../../theme'
import styles from './styles'
import { downloadBatchReportPdf, downloadBatchListXlsx } from '../../api'

type StatusFilter = 'open' | 'closed' | 'all'

// ── Date grouping ─────────────────────────────────────────────────────────────
function getGroup(dateStr: string): string {
  if (!dateStr) return 'Older'
  const d    = new Date(dateStr)
  const now  = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
  const dow  = now.getDay()                        // 0=Sun
  const daysToMonday = dow === 0 ? 6 : dow - 1    // how many days ago was Monday
  if (diff <= daysToMonday)     return 'This Week'
  if (diff <= daysToMonday + 7) return 'Last Week'
  if (diff <= now.getDate() - 1) return 'This Month'
  return 'Older'
}

const GROUP_ORDER = ['This Week', 'Last Week', 'This Month', 'Older']

function groupBatches(list: any[]) {
  const map: Record<string, any[]> = {}
  for (const b of list) {
    const g = getGroup(b.created_at)
    if (!map[g]) map[g] = []
    map[g].push(b)
  }
  return GROUP_ORDER.filter(g => map[g]?.length).map(g => ({ label: g, items: map[g] }))
}

// ── Main component ────────────────────────────────────────────────────────────
export function HomeView({ batches, directAssignments, overview, loading, onOpen, statusColor, onCreateBatch,
                           search, onSearch, total, loaded, onLoadMore }: any) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open')
  const setSearch = onSearch
  const [collapsed, setCollapsed]       = useState<Record<string, boolean>>({})

  if (loading) return (
    <div style={styles.center}>
      <div style={{ width: 24, height: 24, border: '3px solid #e5e7eb', borderTop: '3px solid #0f766e', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    </div>
  )

  function filterList(list: any[]) {
    let out = list
    if (statusFilter === 'open')   out = out.filter((b: any) => b.status === 'Open')
    if (statusFilter === 'closed') out = out.filter((b: any) => b.status !== 'Open')
    // Name and creator are matched on the server so a search reaches batches
    // that were never loaded. Specialty is matched here as well, so typing
    // "SDS" still narrows what is on screen.
    if (search?.trim()) {
      const q = search.trim().toLowerCase()
      out = out.filter((b: any) =>
        b.name.toLowerCase().includes(q) ||
        b.specialty?.toLowerCase().includes(q) ||
        b.created_by?.toLowerCase().includes(q)
      )
    }
    return out
  }

  function toggleGroup(label: string) {
    setCollapsed(prev => ({ ...prev, [label]: prev[label] === false }))
  }

  // Merge direct assignments into the main list with a flag
  // Both lists arrive newest-first, but concatenating two sorted lists does
  // not give a sorted list — every direct assignment landed after every batch,
  // so inside "This Week" the order was by type, not by date.
  const allBatches = [
    ...batches,
    ...(directAssignments ?? []).map((b: any) => ({ ...b, _direct: true })),
  ].sort((a: any, b: any) =>
    String(b.created_at || '').localeCompare(String(a.created_at || '')) || (b.id - a.id))

  const openCount   = allBatches.filter((b: any) => b.status === 'Open').length
  const closedCount = allBatches.filter((b: any) => b.status !== 'Open').length
  const filtered    = filterList(allBatches)
  const groups      = groupBatches(filtered)

  const TAB_CFG: { key: StatusFilter; label: string; count: number; color: string; activeBg: string; activeBorder: string }[] = [
    { key: 'open',   label: 'Open',   count: openCount,        color: '#1d4ed8', activeBg: '#eff6ff', activeBorder: '#3b82f6' },
    { key: 'closed', label: 'Closed', count: closedCount,      color: '#15803d', activeBg: '#f0fdf4', activeBorder: '#22c55e' },
    // allBatches, not batches: Open and Closed above already count assignments
    // too, and the list below shows both. Counting formal batches here alone
    // put "Open 16 · Closed 7 · All 3" on one row.
    { key: 'all',    label: 'All',    count: allBatches.length, color: '#374151', activeBg: '#f8fafc', activeBorder: '#94a3b8' },
  ]

  return (
    <div>
      {/* ── KPI strip ── */}
      {overview && overview.total_batches > 0 && (
        <div style={styles.statsRow}>
          {[
            // The same population as the chips and the list beneath them —
            // batches and direct assignments together. These read from the
            // server's batch-only overview, so the strip said 3 while the row
            // under it said 16 open.
            { label: 'Batches & Assignments', value: allBatches.length },
            { label: 'Open',              value: openCount,   color: '#2563eb' },
            { label: 'Closed',            value: closedCount, color: '#16a34a' },
            { label: 'Total Graded',      value: overview.total_graded },
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

      {/* ── Filter bar ── */}
      {batches.length > 0 && (
        <div style={s.filterBar}>
          {/* Coloured status tabs */}
          <div style={s.tabGroup}>
            {TAB_CFG.map(t => {
              const active = statusFilter === t.key
              return (
                <button
                  key={t.key}
                  onClick={() => setStatusFilter(t.key)}
                  style={{
                    ...s.tab,
                    ...(active ? {
                      background: t.activeBg,
                      border: `1.5px solid ${t.activeBorder}`,
                      color: t.color,
                    } : {}),
                  }}
                >
                  {t.label}
                  <span style={{
                    ...s.badge,
                    background: active ? t.color : '#e5e7eb',
                    color: active ? '#fff' : '#6b7280',
                  }}>
                    {t.count}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Search */}
          <div style={s.searchWrap}>
            <Search size={13} color="#9ca3af" style={{ flexShrink: 0 }} />
            <input
              style={s.searchInput}
              placeholder="Search name, specialty, creator…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button style={s.clearBtn} onClick={() => setSearch('')}><X size={12} /></button>
            )}
          </div>

          {/* Exports THIS list — the columns on screen, one row per batch.
              Separate from the coder-performance export in Analytics, which is
              one row per graded result and answers a
              different question. Filters carry over; paging does not, since a
              page is a screen limit rather than something you asked for. */}
          <button
            title="Export this list to Excel — current filters, all matching rows"
            onClick={() => downloadBatchListXlsx({
              status: statusFilter === 'all' ? undefined : statusFilter === 'open' ? 'Open' : 'Closed',
              search,
            })}
            style={{ ...styles.outlineBtn, fontSize: 12, padding: '6px 12px' }}
          >
            <Download size={13} /> Export List
          </button>
        </div>
      )}

      {/* ── Batch groups ── */}
      {allBatches.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={36} color="#d1d5db" />
          <p style={{ color: '#6b7280', marginBottom: 4, fontSize: 14 }}>No batches yet.</p>
          <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 16 }}>
            Upload answer keys for your charts, then create a batch to assign them to coders.
          </p>
          <button style={styles.primaryBtn} onClick={onCreateBatch}>Create your first batch</button>
        </div>
      ) : groups.length === 0 ? (
        <div style={{ ...styles.empty, padding: '28px 0' }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {groups.map(({ label, items }) => {
            // Everything used to be collapsed on arrival, so the default view
            // of this screen was a stack of headers and no batches at all.
            // The newest non-empty group opens by default; `groups` has already
            // dropped the empty ones, so groups[0] is whichever category is
            // actually the most recent one — This Week, or This Month, or
            // Older if that is all there is. An explicit toggle still wins,
            // which is why this reads `undefined` rather than falsy.
            const isCollapsed = collapsed[label] !== undefined
              ? collapsed[label]
              : label !== groups[0]?.label
            return (
              <div key={label}>
                {/* Group header */}
                <button style={s.groupHeader} onClick={() => toggleGroup(label)}>
                  {isCollapsed
                    ? <ChevronRight size={14} color="#9ca3af" />
                    : <ChevronDown size={14} color="#9ca3af" />
                  }
                  <span style={s.groupLabel}>{label}</span>
                  <span style={s.groupCount}>{items.length}</span>
                  <span style={s.groupLine} />
                </button>

                {/* Group rows */}
                {!isCollapsed && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
                    {items.map((b: any) => (
                      <BatchRow key={b.id} b={b} onOpen={onOpen} statusColor={statusColor} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Paging. States what is loaded against what exists, so the count on
          screen is never mistaken for the total. */}
      {total > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '14px 0 4px' }}>
          <span style={{ fontSize: 11, color: '#9ca3af' }}>
            Showing {Math.min(loaded, total)} of {total}
            {search?.trim() ? ` matching "${search.trim()}"` : ''}
            {' · newest first'}
          </span>
          {loaded < total && (
            <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '6px 14px' }} onClick={onLoadMore}>
              Load more
            </button>
          )}
        </div>
      )}

    </div>
  )
}

// ── Compact batch row ─────────────────────────────────────────────────────────
function BatchRow({ b, onOpen, statusColor }: any) {
  const sc     = SPECIALTY_COLORS[b.specialty as keyof typeof SPECIALTY_COLORS]
  const isOpen = b.status === 'Open'
  const graded = b.graded_count ?? 0

  let hint = ''
  if (isOpen) {
    if ((b.allocation_cycles ?? 0) === 0) hint = 'Run first cycle'
    else if (b.days_open != null && b.days_open > 0) hint = 'Awaiting submissions'
  }

  return (
    <div
      className="pl-batch-row"
      style={{ ...s.row, ...(b._direct ? s.rowDirect : {}) }}
      onClick={() => onOpen(b.id)}
    >
      {/* Left accent */}
      <div style={{ ...s.accent, background: sc?.bg || '#94a3b8' }} />

      {/* Main info */}
      <div style={s.info}>
        <div style={s.nameRow}>
          <span style={s.name}>{b.name}</span>
          {b._direct && <span style={{ ...s.hint, color: '#7c3aed', background: '#ede9fe' }}>Direct</span>}
          {hint && <span style={s.hint}>{hint}</span>}
        </div>
        <div style={s.meta}>
          <span style={{ ...s.specialtyBadge, background: sc?.light || '#f1f5f9', color: sc?.bg || '#475569' }}>
            {b.specialty}
          </span>
          <span style={s.dot}>·</span>
          <span style={s.metaItem}>{b.coder_count} coder{b.coder_count !== 1 ? 's' : ''}</span>
          <span style={s.dot}>·</span>
          <span style={s.metaItem}>{b.allocation_cycles ?? 0} cycle{b.allocation_cycles !== 1 ? 's' : ''}</span>
          {b.days_open != null && (
            <>
              <span style={s.dot}>·</span>
              <span style={{ ...s.metaItem, color: b.days_open > 14 ? '#d97706' : '#9ca3af' }}>
                {b.days_open}d open
              </span>
            </>
          )}
          <span style={s.dot}>·</span>
          <span style={s.metaItem}>{b.created_by}</span>
          {b.force_closed && <><span style={s.dot}>·</span><span style={{ ...s.metaItem, color: '#dc2626', fontWeight: 700 }}>force-closed</span></>}
        </div>
      </div>

      {/* Status pill — direct assignments use amber/slate instead of blue/green */}
      <span style={{
        ...s.statusPill,
        ...(b._direct
          ? b.status === 'Open'
            ? { color: '#92400e', borderColor: '#fbbf24', background: '#fffbeb' }
            : { color: '#374151', borderColor: '#9ca3af', background: '#f9fafb' }
          : { color: statusColor(b.status), borderColor: statusColor(b.status), background: b.status === 'Open' ? '#eff6ff' : '#f0fdf4' }
        ),
      }}>
        {b.status}
      </span>

      {/* Performance report. Disabled rather than hidden when nothing has been
          graded — a missing button leaves you wondering where it went, a
          disabled one that says why does not. The PDF is built from grading
          results, so with none it would be an empty document. */}
      <button
        title={graded > 0
          ? `Performance report — ${graded} graded result${graded !== 1 ? 's' : ''}`
          : 'No graded results yet — nothing to report on'}
        disabled={graded === 0}
        onClick={async e => {
          e.stopPropagation()
          try { await downloadBatchReportPdf(b.id) }
          catch { toast.error(`No report could be generated for ${b.name}`) }
        }}
        style={{
          ...s.reportBtn,
          ...(graded === 0
            ? { color: '#d1d5db', borderColor: '#f3f4f6', cursor: 'not-allowed' }
            : { color: '#4f46e5', borderColor: '#c7d2fe', cursor: 'pointer' }),
        }}
      >
        <FileText size={13} /> Report
      </button>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  // Filter bar
  filterBar: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' as const },
  tabGroup:  { display: 'flex', gap: 6 },
  tab: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '5px 12px', borderRadius: 8,
    border: '1.5px solid #e5e7eb', background: '#fff',
    cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#6b7280',
    transition: 'all 0.15s',
  },
  badge: {
    fontSize: 10, fontWeight: 700, padding: '1px 6px',
    borderRadius: 20, minWidth: 18, textAlign: 'center' as const,
    transition: 'all 0.15s',
  },
  searchWrap: {
    display: 'flex', alignItems: 'center', gap: 7,
    flex: 1, minWidth: 180, maxWidth: 300,
    background: '#fff', border: '1px solid #e5e7eb',
    borderRadius: 7, padding: '5px 10px',
  },
  searchInput: {
    flex: 1, border: 'none', outline: 'none',
    fontSize: 12, color: '#111', background: 'transparent',
    fontFamily: 'system-ui, sans-serif',
  },
  clearBtn: { display: 'flex', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 1 },

  // Group header
  groupHeader: {
    display: 'flex', alignItems: 'center', gap: 6,
    width: '100%', background: 'none', border: 'none',
    cursor: 'pointer', padding: '6px 2px', marginBottom: 4,
    textAlign: 'left' as const,
  },
  groupLabel: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.8 },
  groupCount: { fontSize: 10, fontWeight: 700, color: '#9ca3af', background: '#f1f5f9', padding: '1px 6px', borderRadius: 10 },
  groupLine:  { flex: 1, height: 1, background: '#f1f5f9' },

  // Batch row — compact
  row: {
    display: 'flex', alignItems: 'center', gap: 0,
    background: '#fff', border: '1px solid #f1f5f9',
    borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
    transition: 'border-color 0.12s, box-shadow 0.12s',
  },
  rowDirect: {},
  accent: { width: 3, alignSelf: 'stretch', flexShrink: 0 },
  info:   { flex: 1, padding: '10px 14px', display: 'flex', flexDirection: 'column' as const, gap: 3 },

  nameRow: { display: 'flex', alignItems: 'center', gap: 8 },
  name:    { fontWeight: 700, fontSize: 13, color: '#111', lineHeight: 1.3 },
  hint:    { fontSize: 10, fontWeight: 700, color: '#4f46e5', background: '#eef2ff', padding: '1px 7px', borderRadius: 8 },

  meta:    { display: 'flex', flexWrap: 'wrap' as const, alignItems: 'center', gap: 4 },
  dot:     { fontSize: 10, color: '#d1d5db' },
  metaItem:{ fontSize: 11, color: '#9ca3af' },
  specialtyBadge: {
    fontSize: 10, fontWeight: 700, padding: '1px 7px',
    borderRadius: 10, display: 'inline-flex', alignItems: 'center',
  },
  reportBtn: {
    display: 'flex', alignItems: 'center', gap: 5, padding: '5px 11px', borderRadius: 7,
    border: '1px solid', background: '#fff', fontSize: 11, fontWeight: 700, flexShrink: 0,
  },
  statusPill: {
    fontSize: 11, fontWeight: 700, padding: '3px 10px',
    borderRadius: 20, border: '1px solid', marginRight: 12,
    whiteSpace: 'nowrap' as const, flexShrink: 0,
  },
}
