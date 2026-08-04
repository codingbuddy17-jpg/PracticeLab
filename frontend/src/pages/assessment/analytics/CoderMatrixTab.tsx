import { useState, useEffect } from 'react'
import { Download, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentAnalyticsCoderMatrix, downloadAssessmentCoderMatrixXlsx } from '../../../api'
import type { AFilters } from '../../../api'
import { scoreColor, fmt, DEFAULT_PASS, Panel, LoadingSpinner, EmptyState } from './helpers'
import { usePagination } from '../../../components/Paginator'

const NO_FILTERS: AFilters = {}
const PAGE_SIZE = 15

export function CoderMatrixTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [belowOnly, setBelowOnly] = useState(false)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    setLoading(true)
    getAssessmentAnalyticsCoderMatrix(filters)
      .then(setData)
      .catch(() => toast.error('Failed to load coder matrix'))
      .finally(() => setLoading(false))
  }, [filters])

  if (loading) return <LoadingSpinner />
  if (!data || !data.coders || data.coders.length === 0)
    return <EmptyState message="No coder matrix data yet. Submit some assessments first." />

  const specialties: string[] = data.specialties
  const bar: number = data.default_pass_threshold ?? DEFAULT_PASS

  const q = search.trim().toLowerCase()
  const coders: any[] = data.coders.filter((c: any) => {
    if (q && !`${c.coder_name} ${c.employee_id || ''}`.toLowerCase().includes(q)) return false
    // "Below the bar" compares a coder's own SCORE against a score threshold —
    // not against the population target, which is a different scale.
    if (belowOnly && !(c.avg_score != null && c.avg_score < bar)) return false
    return true
  })

  const narrowed = coders.length !== data.coders.length

  async function handleExport() {
    setExporting(true)
    try {
      await downloadAssessmentCoderMatrixXlsx(filters)
    } catch (e: any) {
      toast.error(e.message || 'Export failed.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div>
      <Panel>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
          Each cell shows a coder's accuracy on that specialty across all assessments.
          Color intensity indicates performance — <span style={{ color: '#dc2626', fontWeight: 700 }}>red = gap area</span>,{' '}
          <span style={{ color: '#d97706', fontWeight: 700 }}>amber = developing</span>,{' '}
          <span style={{ color: '#16a34a', fontWeight: 700 }}>green = strong</span>.
        </div>
      </Panel>

      {/* Controls sit above the grid, so a search that matches nothing still
          leaves the box that would clear it on screen. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <div style={{ position: 'relative' }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setSearch('') }}
            placeholder="Find a coder or employee ID…"
            style={{ padding: '6px 26px 6px 11px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, minWidth: 220 }}
          />
          {search && (
            <button onClick={() => setSearch('')} title="Clear"
              style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', display: 'flex', padding: 0 }}>
              <X size={13} />
            </button>
          )}
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6b7280', cursor: 'pointer', fontWeight: 600 }}>
          <input type="checkbox" checked={belowOnly} onChange={e => setBelowOnly(e.target.checked)} />
          Below {bar}% only
        </label>

        {narrowed && (
          <span style={{ fontSize: 11, color: '#6b7280' }}>
            {coders.length} of {data.coders.length} coders
          </span>
        )}

        <button onClick={handleExport} disabled={exporting}
          title="Every coder against every specialty — the whole grid, not just this page"
          style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, padding: '6px 13px', borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff', color: '#374151', cursor: 'pointer', fontSize: 12, fontWeight: 700 }}>
          <Download size={13} /> {exporting ? 'Preparing…' : 'Export (.xlsx)'}
        </button>
      </div>

      <Panel title={`Coder × Specialty Matrix (${coders.length} coder${coders.length === 1 ? '' : 's'}, ${specialties.length} specialties)`}>
        {coders.length === 0
          ? <EmptyState message={belowOnly && !q
              ? `No coder is averaging below ${bar}%.`
              : `No coder matches “${search}”.`} />
          : <MatrixTable coders={coders} specialties={specialties} />}
      </Panel>
    </div>
  )
}

function MatrixTable({ coders, specialties }: { coders: any[]; specialties: string[] }) {
  const { pageData, Paginator } = usePagination(coders, PAGE_SIZE)

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
              <th style={{ textAlign: 'left', padding: '10px 14px', color: '#6b7280', fontWeight: 700, fontSize: 11, whiteSpace: 'nowrap' as const, minWidth: 140 }}>Coder</th>
              {specialties.map((sp: string) => (
                <th key={sp} title={sp} style={{ padding: '10px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, textAlign: 'center', whiteSpace: 'nowrap' as const }}>
                  <div style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', margin: '0 auto' }}>{sp}</div>
                </th>
              ))}
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Avg Score</th>
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Assessments</th>
            </tr>
          </thead>
          <tbody>
            {pageData.map((coder: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '8px 14px', fontWeight: 700, color: '#111', whiteSpace: 'nowrap' as const }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 26, height: 26, borderRadius: '50%', flexShrink: 0, background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 11, fontWeight: 800 }}>
                      {coder.coder_name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      {coder.coder_name}
                      {/* Two coders can share a name; the id is what tells them apart. */}
                      {coder.employee_id && (
                        <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600 }}>{coder.employee_id}</div>
                      )}
                    </div>
                  </div>
                </td>
                {specialties.map((sp: string) => {
                  const acc: number | null = coder.specialties[sp]
                  const bg = acc == null ? '#f9fafb' : acc >= 90 ? 'rgba(22,163,74,0.15)' : acc >= 80 ? 'rgba(217,119,6,0.13)' : 'rgba(220,38,38,0.11)'
                  return (
                    <td key={sp} style={{ padding: '8px 10px', textAlign: 'center', background: bg, fontWeight: 700, fontSize: 12, color: scoreColor(acc), borderLeft: '1px solid rgba(0,0,0,0.04)' }}>
                      {acc != null ? `${acc}%` : <span style={{ color: '#d1d5db' }}>—</span>}
                    </td>
                  )
                })}
                <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 800, fontSize: 14, color: scoreColor(coder.avg_score) }}>{fmt(coder.avg_score)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280', fontWeight: 600 }}>{coder.assessments_taken}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginator />
    </>
  )
}
