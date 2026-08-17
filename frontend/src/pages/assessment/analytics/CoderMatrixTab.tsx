import { useState, useEffect, useMemo } from 'react'
import { Download, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { getAssessmentAnalyticsCoderMatrix, downloadAssessmentCoderMatrixXlsx } from '../../../api'
import type { AFilters } from '../../../api'
import { scoreColor, fmt, DEFAULT_PASS, Panel, LoadingSpinner, EmptyState, ReportButton } from './helpers'
import { usePagination } from '../../../components/Paginator'

const NO_FILTERS: AFilters = {}
const PAGE_SIZE = 15
type SortMode = 'gap' | 'score_asc' | 'score_desc' | 'assessments' | 'name'
type ColumnMode = 'gaps' | 'all' | 'selected'

export function CoderMatrixTab({ filters = NO_FILTERS }: { filters?: AFilters }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [belowOnly, setBelowOnly] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [sortMode, setSortMode] = useState<SortMode>('gap')
  const [columnMode, setColumnMode] = useState<ColumnMode>('gaps')
  const [selectedSpecialties, setSelectedSpecialties] = useState<string[]>([])

  useEffect(() => {
    setLoading(true)
    getAssessmentAnalyticsCoderMatrix(filters)
      .then(setData)
      .catch(() => toast.error('Failed to load coder matrix'))
      .finally(() => setLoading(false))
  }, [filters])

  const rawCoders: any[] = data?.coders || []
  const specialties: string[] = data?.specialties || []
  const bar: number = data?.default_pass_threshold ?? DEFAULT_PASS
  const gapSpecialties = useMemo(() => specialties.filter((sp: string) =>
    rawCoders.some((c: any) => (c.specialties?.[sp] ?? 100) < bar)
  ), [specialties, rawCoders, bar])
  const visibleSpecialties = useMemo(() => {
    if (columnMode === 'all') return specialties
    if (columnMode === 'selected') return selectedSpecialties.length ? selectedSpecialties : specialties
    return gapSpecialties.length ? gapSpecialties : specialties
  }, [columnMode, specialties, selectedSpecialties, gapSpecialties])

  if (loading) return <LoadingSpinner />
  if (!data || rawCoders.length === 0)
    return <EmptyState message="No coder matrix data yet. Submit some assessments first." />

  const q = search.trim().toLowerCase()
  const coders: any[] = rawCoders
    .filter((c: any) => {
      if (q && !`${c.coder_name} ${c.employee_id || ''}`.toLowerCase().includes(q)) return false
      if (belowOnly && !((c.gap_count || 0) > 0 || (c.avg_score != null && c.avg_score < bar))) return false
      return true
    })
    .sort((a: any, b: any) => {
      if (sortMode === 'name') return String(a.coder_name || '').localeCompare(String(b.coder_name || ''))
      if (sortMode === 'assessments') return (b.assessments_taken || 0) - (a.assessments_taken || 0)
      if (sortMode === 'score_desc') return (b.avg_score ?? -1) - (a.avg_score ?? -1)
      if (sortMode === 'score_asc') return (a.avg_score ?? 999) - (b.avg_score ?? 999)
      return ((b.gap_count || 0) - (a.gap_count || 0)) || ((a.avg_score ?? 999) - (b.avg_score ?? 999))
    })

  const narrowed = coders.length !== rawCoders.length

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
          Gap-first triage view. The workbook export still carries the full grid.
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
          Gaps only
        </label>

        <select value={sortMode} onChange={e => setSortMode(e.target.value as SortMode)}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff' }}>
          <option value="gap">Sort by gap count</option>
          <option value="score_asc">Sort by low score</option>
          <option value="score_desc">Sort by high score</option>
          <option value="assessments">Sort by assessments</option>
          <option value="name">Sort by coder</option>
        </select>

        <select value={columnMode} onChange={e => setColumnMode(e.target.value as ColumnMode)}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff' }}>
          <option value="gaps">Gap specialties</option>
          <option value="all">All specialties</option>
          <option value="selected">Selected specialties</option>
        </select>

        {columnMode === 'selected' && (
          <select value="" onChange={e => {
              const sp = e.target.value
              if (sp && !selectedSpecialties.includes(sp)) setSelectedSpecialties(prev => [...prev, sp])
            }}
            style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12, color: '#374151', background: '#fff', maxWidth: 190 }}>
            <option value="">Add specialty</option>
            {specialties.filter(sp => !selectedSpecialties.includes(sp)).map(sp => <option key={sp} value={sp}>{sp}</option>)}
          </select>
        )}

        {narrowed && (
          <span style={{ fontSize: 11, color: '#6b7280' }}>
            {coders.length} of {rawCoders.length} coders
          </span>
        )}

        <div style={{ marginLeft: 'auto' }}>
          <ReportButton
            label="Matrix (.xlsx)"
            icon={<Download size={13} />}
            busy={exporting}
            title="Every coder against every specialty — the whole grid, not just this page"
            onClick={handleExport}
          />
        </div>
      </div>

      {columnMode === 'selected' && selectedSpecialties.length > 0 && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 12 }}>
          {selectedSpecialties.map(sp => (
            <button key={sp} onClick={() => setSelectedSpecialties(prev => prev.filter(x => x !== sp))}
              title="Remove specialty"
              style={{ display: 'flex', alignItems: 'center', gap: 5, border: '1px solid #e5e7eb', background: '#fff', color: '#374151', borderRadius: 20, padding: '3px 8px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
              {sp} <X size={11} />
            </button>
          ))}
        </div>
      )}

      <Panel title={`Coder × Specialty Matrix (${coders.length} coder${coders.length === 1 ? '' : 's'}, ${visibleSpecialties.length} of ${specialties.length} specialties)`}>
        {coders.length === 0
          ? <EmptyState message={belowOnly && !q
              ? `No coder has a specialty gap below ${bar}%.`
              : `No coder matches “${search}”.`} />
          : <MatrixTable coders={coders} specialties={visibleSpecialties} bar={bar} />}
      </Panel>
    </div>
  )
}

function MatrixTable({ coders, specialties, bar }: { coders: any[]; specialties: string[]; bar: number }) {
  const { pageData, Paginator } = usePagination(coders, PAGE_SIZE)

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
              <th style={{ textAlign: 'left', padding: '10px 14px', color: '#6b7280', fontWeight: 700, fontSize: 11, whiteSpace: 'nowrap' as const, minWidth: 140 }}>Coder</th>
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Avg Score</th>
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Assessments</th>
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'center', whiteSpace: 'nowrap' as const }}>Gap Count</th>
              <th style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textAlign: 'left', whiteSpace: 'nowrap' as const }}>Weakest Specialty</th>
              {specialties.map((sp: string) => (
                <th key={sp} title={sp} style={{ padding: '10px 10px', color: '#6b7280', fontWeight: 700, fontSize: 10, textAlign: 'center', whiteSpace: 'nowrap' as const }}>
                  <div style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', margin: '0 auto' }}>{sp}</div>
                </th>
              ))}
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
                <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 800, fontSize: 14, color: scoreColor(coder.avg_score) }}>{fmt(coder.avg_score)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280', fontWeight: 600 }}>{coder.assessments_taken}</td>
                <td style={{ padding: '8px 12px', textAlign: 'center', color: (coder.gap_count || 0) > 0 ? '#dc2626' : '#16a34a', fontWeight: 800 }}>{coder.gap_count || 0}</td>
                <td style={{ padding: '8px 12px', color: '#374151', minWidth: 130 }}>
                  {coder.weakest_specialty ? (
                    <div title={`${coder.weakest_specialty.accuracy_pct}% · ${coder.weakest_specialty.correct}/${coder.weakest_specialty.total}`}>
                      <div style={{ fontWeight: 700, fontSize: 12 }}>{coder.weakest_specialty.specialty}</div>
                      <div style={{ fontSize: 10, color: scoreColor(coder.weakest_specialty.accuracy_pct), fontWeight: 700 }}>{coder.weakest_specialty.accuracy_pct}% · {coder.weakest_specialty.correct}/{coder.weakest_specialty.total}</div>
                    </div>
                  ) : <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
                {specialties.map((sp: string) => {
                  const acc: number | null = coder.specialties[sp]
                  const counts = coder.specialty_counts?.[sp]
                  const bg = acc == null ? '#f9fafb' : acc >= bar ? 'rgba(22,163,74,0.15)' : acc >= bar - 10 ? 'rgba(217,119,6,0.13)' : 'rgba(220,38,38,0.11)'
                  return (
                    <td key={sp} title={counts ? `${counts.correct}/${counts.total} correct` : undefined} style={{ padding: '7px 10px', textAlign: 'center', background: bg, borderLeft: '1px solid rgba(0,0,0,0.04)', minWidth: 76 }}>
                      {acc != null ? (
                        <div>
                          <div style={{ fontWeight: 800, fontSize: 12, color: scoreColor(acc, bar) }}>{acc}%</div>
                          {counts && <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600 }}>{counts.correct}/{counts.total}</div>}
                        </div>
                      ) : <span style={{ color: '#d1d5db' }}>—</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginator />
    </>
  )
}
