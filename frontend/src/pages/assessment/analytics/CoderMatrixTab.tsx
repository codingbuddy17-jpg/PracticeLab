import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { getAssessmentAnalyticsCoderMatrix } from '../../../api'
import type { AFilters } from '../../../api'

const NO_FILTERS: AFilters = {}
import { scoreColor, fmt, Panel, LoadingSpinner, EmptyState } from './helpers'
import { usePagination } from '../../../components/Paginator'

const PAGE_SIZE = 15

export function CoderMatrixTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

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

  const coders: any[] = data.coders
  const specialties: string[] = data.specialties

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

      <Panel title={`Coder × Specialty Matrix (${coders.length} coders, ${specialties.length} specialties)`}>
        <MatrixTable coders={coders} specialties={specialties} />
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
                <th key={sp} style={{ padding: '10px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, textAlign: 'center', whiteSpace: 'nowrap' as const }}>
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
                    {coder.coder_name}
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
