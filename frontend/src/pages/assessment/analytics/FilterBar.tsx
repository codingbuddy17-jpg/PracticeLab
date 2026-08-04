import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { getAssessmentAnalyticsByBatch } from '../../../api'
import type { AFilters } from '../../../api'

const PRESETS: { label: string; days: number | null }[] = [
  { label: 'All time', days: null },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
  { label: '12 months', days: 365 },
]

function daysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

/**
 * The window every analytics tab reads through.
 *
 * Rendered above the tab content, never inside it, so that a filter which
 * returns nothing still leaves the trainer a way back — a control placed
 * inside the region its own value can empty is how a filter becomes a trap.
 *
 * There is no specialty filter here on purpose: a paper carries a specialty
 * MIX, so "this is an IP-DRG assessment" is not a fact about a session. The
 * By Specialty and By Topic tabs answer that at the level where it is well
 * defined — the individual response.
 */
export function FilterBar({ value, onChange }: {
  value: AFilters
  onChange: (f: AFilters) => void
}) {
  const [batches, setBatches] = useState<string[]>([])

  useEffect(() => {
    getAssessmentAnalyticsByBatch()
      .then((d: any) => setBatches((d.batches || []).map((b: any) => b.batch_name).filter(Boolean)))
      .catch(() => {})   // the filter still works without the batch list
  }, [])

  const active = !!(value.dateFrom || value.dateTo || value.batchName)
  const activePreset = PRESETS.find(p =>
    p.days === null ? !value.dateFrom : value.dateFrom === daysAgo(p.days)
  )

  const set = (patch: Partial<AFilters>) => onChange({ ...value, ...patch })

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(10px)',
      WebkitBackdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.6)',
      borderRadius: 12, padding: '10px 14px', marginBottom: 18,
    }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4 }}>
        Period
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        {PRESETS.map(p => {
          const on = activePreset?.label === p.label
          return (
            <button
              key={p.label}
              onClick={() => set({ dateFrom: p.days === null ? undefined : daysAgo(p.days), dateTo: undefined })}
              style={{
                padding: '5px 11px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                cursor: 'pointer',
                border: on ? '1px solid rgba(124,58,237,0.35)' : '1px solid #e5e7eb',
                background: on ? 'rgba(124,58,237,0.1)' : '#fff',
                color: on ? '#7c3aed' : '#6b7280',
              }}
            >
              {p.label}
            </button>
          )
        })}
      </div>

      <input type="date" value={value.dateFrom || ''} max={value.dateTo || undefined}
        onChange={e => set({ dateFrom: e.target.value || undefined })}
        style={inputStyle} title="From (inclusive)" />
      <span style={{ color: '#9ca3af', fontSize: 12 }}>to</span>
      <input type="date" value={value.dateTo || ''} min={value.dateFrom || undefined}
        onChange={e => set({ dateTo: e.target.value || undefined })}
        style={inputStyle} title="To (inclusive)" />

      {batches.length > 0 && (
        <select value={value.batchName || ''}
          onChange={e => set({ batchName: e.target.value || undefined })}
          style={{ ...inputStyle, minWidth: 150 }}>
          <option value="">All batches</option>
          {batches.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      )}

      {active && (
        <button onClick={() => onChange({})}
          style={{
            display: 'flex', alignItems: 'center', gap: 4, marginLeft: 'auto',
            padding: '5px 10px', borderRadius: 8, border: '1px solid #e5e7eb',
            background: '#fff', color: '#6b7280', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
          }}>
          <X size={12} /> Clear
        </button>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  padding: '5px 9px',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  fontSize: 12,
  color: '#374151',
  background: '#fff',
}
