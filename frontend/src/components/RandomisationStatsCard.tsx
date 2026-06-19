/**
 * Displays randomisation quality stats for an assessment generation
 * or a batch allocation cycle. Used in SessionsView and BatchDetailView.
 */
import React, { useState } from 'react'

interface PerCoder {
  name: string
  uniqueness_pct: number
  shared_items: (number | string)[]
}

interface TopOverlap {
  coder_a: string
  coder_b: string
  shared_count: number
  overlap_pct: number
}

export interface RandomisationStats {
  avg_uniqueness_pct: number
  pool_utilisation_pct: number
  total_pool: number
  total_used: number
  coder_count: number
  items_per_coder: number
  per_coder: PerCoder[]
  top_overlaps: TopOverlap[]
}

interface Props {
  stats: RandomisationStats
  itemLabel?: string   // 'questions' or 'charts'
}

function Badge({ pct }: { pct: number | null | undefined }) {
  const safe = pct ?? 0
  const color = safe >= 80 ? '#16a34a' : safe >= 60 ? '#d97706' : '#dc2626'
  const bg    = safe >= 80 ? '#f0fdf4' : safe >= 60 ? '#fffbeb' : '#fef2f2'
  const border = safe >= 80 ? '#bbf7d0' : safe >= 60 ? '#fde68a' : '#fecaca'
  if (pct == null) return <span style={{ color: '#9ca3af', fontSize: 13 }}>—</span>
  return (
    <span style={{
      display: 'inline-block', fontWeight: 700, fontSize: 13,
      color, background: bg, border: `1px solid ${border}`,
      borderRadius: 6, padding: '2px 8px',
    }}>
      {safe.toFixed(1)}%
    </span>
  )
}

export default function RandomisationStatsCard({ stats, itemLabel = 'items' }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (!stats) return null

  const perCoder = Array.isArray(stats.per_coder) ? stats.per_coder : []
  const topOverlaps = Array.isArray(stats.top_overlaps) ? stats.top_overlaps : []

  return (
    <div style={{
      background: '#f8fafc', border: '1px solid #e2e8f0',
      borderRadius: 8, padding: '12px 16px', marginTop: 12,
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: '#374151' }}>
          Randomisation Quality
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, color: '#6b7280' }}>Avg uniqueness</span>
          <Badge pct={stats.avg_uniqueness_pct} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, color: '#6b7280' }}>Pool utilisation</span>
          <Badge pct={stats.pool_utilisation_pct} />
        </div>

        <span style={{ fontSize: 12, color: '#9ca3af' }}>
          {stats.total_used} of {stats.total_pool} {itemLabel} used
          · {stats.coder_count} coders · {stats.items_per_coder} {itemLabel} each
        </span>

        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            marginLeft: 'auto', background: 'none', border: 'none',
            cursor: 'pointer', fontSize: 12, color: '#6366f1', fontWeight: 600,
          }}
        >
          {expanded ? 'Hide detail ▲' : 'Show detail ▼'}
        </button>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ marginTop: 12 }}>

          {/* Per-coder table */}
          <div style={{ fontSize: 12, color: '#374151', fontWeight: 600, marginBottom: 6 }}>
            Per-coder uniqueness
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f1f5f9' }}>
                <th style={th}>Coder</th>
                <th style={th}>Uniqueness</th>
                <th style={th}>Unique {itemLabel}</th>
                <th style={th}>Shared with others</th>
              </tr>
            </thead>
            <tbody>
              {perCoder.map(c => {
                const unique = Math.round((stats.items_per_coder ?? 0) * (c.uniqueness_pct ?? 0) / 100)
                const sharedItems = Array.isArray(c.shared_items) ? c.shared_items : []
                return (
                  <tr key={c.name} style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <td style={td}>{c.name}</td>
                    <td style={td}><Badge pct={c.uniqueness_pct} /></td>
                    <td style={{ ...td, color: '#374151' }}>{unique} / {stats.items_per_coder ?? 0}</td>
                    <td style={{ ...td, color: sharedItems.length ? '#dc2626' : '#9ca3af' }}>
                      {sharedItems.length ? `${sharedItems.length} shared` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Overlapping pairs */}
          {topOverlaps.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: '#374151', fontWeight: 600, marginBottom: 6 }}>
                Highest overlap pairs
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f1f5f9' }}>
                    <th style={th}>Coder A</th>
                    <th style={th}>Coder B</th>
                    <th style={th}>Shared</th>
                    <th style={th}>Overlap %</th>
                  </tr>
                </thead>
                <tbody>
                  {topOverlaps.map((o, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                      <td style={td}>{o.coder_a}</td>
                      <td style={td}>{o.coder_b}</td>
                      <td style={td}>{o.shared_count}</td>
                      <td style={td}><Badge pct={100 - o.overlap_pct} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                * Badge shows uniqueness (100% − overlap%) for consistency with above.
              </div>
            </div>
          )}

          {topOverlaps.length === 0 && (
            <div style={{ fontSize: 12, color: '#16a34a', marginTop: 8, fontWeight: 600 }}>
              ✓ No overlap — all coders received fully unique sets.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const th: React.CSSProperties = {
  textAlign: 'left', padding: '4px 8px', fontWeight: 600,
  color: '#374151', borderBottom: '1px solid #d1d5db',
}
const td: React.CSSProperties = {
  padding: '4px 8px', color: '#6b7280',
}
