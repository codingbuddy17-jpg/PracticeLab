import { useState, useEffect, useRef } from 'react'
import { Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell,
} from 'recharts'
import {
  getPLAnalyticsOverview, getPLAnalyticsBySpecialty, getPLAnalyticsByChart,
  getPLAnalyticsByBatch, getCoderTrend, getCoderSummary, downloadCoderReportPdf,
  downloadCoderPerformanceXlsx, downloadBatchReportPdf, downloadBatchAnalyticsXlsx,
  getPLAnalyticsByCategory, getPLChartTeachingValue, getPLCoderMatrix, getPLChartDetail,
  getBatchEMBreakdown, getPLSpecialtyProfile,
  type PLFilters,
} from '../../api'
import { CoderPicker } from '../../components/CoderPicker'
import { round1 } from './shared'
import { barHeight, recent, extremes, tickInterval, axisLabel, TREND_WINDOWS } from './chartScale'
import styles from './styles'

// Share of charts expected to pass. A POPULATION target — deliberately not
// the per-chart pass_threshold, which is a score and a different scale.
const PASS_RATE_TARGET = 70

/**
 * What each label means. These describe the rule the backend actually applies;
 * "Too Easy" previously claimed "avg ≥90%" while the real cutoff is derived
 * from the chart's own pass mark — 90 for an IP chart, 95 for an OP one. A
 * legend that disagrees with the labelling is worse than no legend.
 */
const TEACHING_LABEL_META: Record<string, { color: string; bg: string; desc: string }> = {
  'High Confusion':{ color: '#92400e', bg: '#fef3c7', desc: 'Under half of attempts pass AND 3+ different codes are missed — the chart or its key may be ambiguous' },
  'High Fail':     { color: '#991b1b', bg: '#fee2e2', desc: 'Under half of attempts pass, but coders miss the same few codes — a genuine difficulty, not confusion' },
  'High Yield':    { color: '#166534', bg: '#dcfce7', desc: '50–80% of attempts pass with 2+ different codes missed — hard enough to teach from, not so hard it defeats everyone' },
  'Standard':      { color: '#374151', bg: '#f9fafb', desc: 'Typical performance — no strong teaching signal either way' },
  'Too Easy':      { color: '#1d4ed8', bg: '#dbeafe', desc: 'Average well above this chart\u2019s pass mark — suitable for beginner packs' },
  'Underused':     { color: '#6b7280', bg: '#f3f4f6', desc: 'Fewer than 2 graded attempts — not enough to judge' },
}

// Below this many graded charts, a percentage is one result away from moving
// double digits, so it is flagged rather than presented as a finding.
const LOW_SAMPLE = 10

const TAB_STORAGE_KEY = 'pl_analytics_tab'
// Persisted alongside the tab. Opening a batch from Analytics unmounts this
// view, so without it you came back to the right tab reading the wrong
// population — and nothing on screen would have told you it had reset.
const SCOPE_STORAGE_KEY = 'pl_analytics_scope'

// One height for every control in a search-and-actions row. The input, the
// primary button and the outline buttons all carry different padding and
// border widths, so without this they render at three near-but-not-equal
// heights — which is what reads as "misaligned".
const ctrlH: React.CSSProperties = { height: 38, paddingTop: 0, paddingBottom: 0 }

const sectionLabel: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: '#6b7280', marginBottom: 8,
  textTransform: 'uppercase', letterSpacing: 0.5,
}

/**
 * Search input with a clear button.
 *
 * Every search on this page was a plain <input>: the only way out was to
 * select the text and delete it. Typing is a filter you can see; an empty box
 * you have to manufacture is not an undo. The batch list and the coder picker
 * already had this — the ones added later did not, so the page taught two
 * different habits for the same control.
 */
function SearchBox({ value, onChange, placeholder, width = 220 }: {
  value: string; onChange: (v: string) => void; placeholder: string; width?: number
}) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <input
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === 'Escape') onChange('') }}
        style={{ padding: '5px 26px 5px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, width }}
      />
      {value && (
        <button onClick={() => onChange('')} title="Clear (Esc)"
          style={{ position: 'absolute', right: 6, background: 'none', border: 'none', cursor: 'pointer',
                   color: '#9ca3af', padding: 0, display: 'flex', alignItems: 'center', fontSize: 14, lineHeight: 1 }}>
          ×
        </button>
      )}
    </span>
  )
}

function Box({ label, value, color, hint }: { label: string; value: any; color?: string; hint?: string }) {
  return (
    <div style={styles.statCard}>
      <div style={{ ...styles.statValue, color: color || '#111' }}>{value}</div>
      <div style={styles.statLabel}>{label}</div>
      {hint && <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 2 }}>{hint}</div>}
    </div>
  )
}

export function PLAnalyticsView({ onOpenBatch }: { onOpenBatch?: (batchId: number) => void } = {}) {
  const [tab, setTab] = useState<'overview' | 'specialty' | 'chart' | 'batch' | 'coder' | 'category' | 'teaching' | 'matrix' | 'em_mdm'>(
    () => (localStorage.getItem(TAB_STORAGE_KEY) as any) || 'overview'
  )

  useEffect(() => { localStorage.setItem(TAB_STORAGE_KEY, tab) }, [tab])
  const [overview, setOverview] = useState<any>(null)
  const [bySpecialty, setBySpecialty] = useState<any[]>([])
  const [byChart, setByChart] = useState<any[]>([])
  const [byBatch, setByBatch] = useState<any[]>([])
  const [coderName, setCoderName] = useState('')
  const [coderTrend, setCoderTrend] = useState<any[]>([])
  const [coderSummary, setCoderSummary] = useState<any>(null)
  // The coder whose data is currently on screen — distinct from the text in
  // the input box, so a filter change can re-fetch the RIGHT coder.
  const [loadedCoder, setLoadedCoder] = useState('')
  // emp_id is the stable identity — see GradingResult.emp_id
  const [coderEmpId, setCoderEmpId] = useState<string | null>(null)
  const [loadedEmpId, setLoadedEmpId] = useState<string | null>(null)
  const [coderEmpty, setCoderEmpty] = useState(false)
  const [coderLoading, setCoderLoading] = useState(false)
  const [categoryData, setCategoryData] = useState<{ team: any[]; coder_category: any[]; coder_scope_note?: string } | null>(null)
  const [teachingData, setTeachingData] = useState<any[]>([])
  const [matrixData, setMatrixData] = useState<{ batches: any[]; coders: string[]; coder_emp_ids?: Record<string, string>; coder_names?: Record<string, string>; scope_note?: string; cells: any[] } | null>(null)
  const [teachingFilter, setTeachingFilter] = useState<string>('All')
  const [refreshing, setRefreshing] = useState(false)
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  const [chartDetail, setChartDetail] = useState<Record<string, any>>({})
  const [draftFilters, setDraftFilters] = useState<PLFilters>({})
  const [filters, setFilters] = useState<PLFilters>({})
  const [ipThreshold, setIpThreshold] = useState(80)
  const [opThreshold, setOpThreshold] = useState(90)
  const [emBatchId, setEmBatchId] = useState<number | null>(null)
  const [emBreakdown, setEmBreakdown] = useState<any>(null)
  const [emLoading, setEmLoading] = useState(false)

  // Score color derived from the active pass threshold
  function thresholdFor(specialty?: string): number {
    // Was a hardcoded list of "OP-like" specialties, which went stale the moment
    // Surgery and ED Single Path were added — both were then coloured against
    // the IP threshold (80) rather than OP (90). The backend now supplies the
    // map, so it cannot drift again.
    if (specialty && overview?.pass_thresholds?.[specialty] != null) {
      return overview.pass_thresholds[specialty]
    }
    return specialty === 'OP' ? opThreshold : ipThreshold
  }

  /**
   * Colour a POPULATION SHARE (what % of charts or coders passed).
   *
   * Distinct from sc() on purpose. sc() judges a SCORE against the specialty's
   * pass threshold; a share is a different scale entirely, and running it
   * through sc() painted an SDS specialty red at 85% of charts passing — a good
   * result — purely because 85 < the 90 score threshold.
   */
  function rc(v: number | null | undefined): string {
    if (v == null) return '#9ca3af'
    if (v >= PASS_RATE_TARGET) return '#16a34a'
    if (v >= PASS_RATE_TARGET * 0.7) return '#d97706'
    return '#dc2626'
  }

  /**
   * Colour a coder's score against the threshold the BACKEND resolved for
   * them. sc() infers a threshold from a specialty string, and a coder spans
   * several — every call in this tab passed no specialty at all, so an SDS
   * coder at 85% was coloured green against IP's 80 when their bar is 90.
   */
  function cc(v: number | null | undefined, threshold?: number): string {
    if (v == null) return '#9ca3af'
    const pt = threshold ?? 80
    return v >= pt ? '#16a34a' : v >= Math.round(pt * 0.75) ? '#d97706' : '#dc2626'
  }

  function sc(v: number | null | undefined, specialty?: string): string {
    if (v == null) return '#9ca3af'
    const pt = thresholdFor(specialty)
    const low = Math.round(pt * 0.75)
    return v >= pt ? '#16a34a' : v >= low ? '#d97706' : '#dc2626'
  }
  const [filterVersion, setFilterVersion] = useState(0)
  // Overview is batch work by default. Direct assignments were excluded with
  // no way to see them, so a coder who only practised that way was invisible.
  const [scope, setScope] = useState<'formal' | 'direct' | 'all'>(
    () => (localStorage.getItem(SCOPE_STORAGE_KEY) as any) || 'formal'
  )
  useEffect(() => { localStorage.setItem(SCOPE_STORAGE_KEY, scope) }, [scope])
  const [matrixCoderSearch, setMatrixCoderSearch] = useState('')
  // "Batch" is wrong wording under the Direct scope, where no row is a batch.
  const unitLabel = scope === 'direct' ? 'Assignment' : 'Batch'
  const unitPlural = scope === 'direct' ? 'direct assignments' : scope === 'all' ? 'batches or assignments' : 'batches'
  const [trendWindow, setTrendWindow] = useState<number | 'all'>(25)

  // Overview mini-trend: its own specialty filter and its own window.
  // Under the "Both" scope each point can be a batch OR a direct assignment,
  // so the window doubles — otherwise showing 3 points across two mixed
  // streams can mean only one or two of each, which is not a trend.
  const [miniSpecialty, setMiniSpecialty] = useState('')
  const miniPool = miniSpecialty ? byBatch.filter((b: any) => b.specialty === miniSpecialty) : byBatch
  const miniTrend = recent(miniPool, scope === 'all' ? 6 : 3)
  // Strongest and weakest categories, in score order. Taking the top N would
  // hide every struggling category the moment the list grew, which is the
  // opposite of what this page is for.
  const [profileSpecialty, setProfileSpecialty] = useState<string | null>(null)
  const [profile, setProfile] = useState<any>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [matrixShowAll, setMatrixShowAll] = useState(false)
  const [matrixBelowOnly, setMatrixBelowOnly] = useState(false)
  /**
   * What a column IS. Batches are events; specialties are buckets.
   *
   * Specialties by default: that axis has a natural ceiling — ten of them,
   * ever — while batch columns grow forever and are readable for about as
   * long as the last dozen. Specialty is also the only view where direct
   * assignments have a column to sit in.
   */
  const [matrixGroupBy, setMatrixGroupBy] = useState<'batch' | 'specialty'>('specialty')
  // How many batch columns to show when the axis is batches. Recency is the
  // only ordering that needs no explanation, so the window takes the latest N.
  const [matrixColWindow, setMatrixColWindow] = useState<number | 'all'>(10)
  const [heatmapCoderSearch, setHeatmapCoderSearch] = useState('')
  const [heatmapShowAll, setHeatmapShowAll] = useState(false)
  // Tab-local, like the Overview trend's picker: narrowing this tab should not
  // re-scope the other seven.
  const [topicSpecialty, setTopicSpecialty] = useState('')
  const [topicSearch, setTopicSearch] = useState('')
  const [topicShowAll, setTopicShowAll] = useState(false)
  const [heatmapShowAllCols, setHeatmapShowAllCols] = useState(false)

  // Topics are free text, so this list has no ceiling. Search + a visible cap
  // rather than a table that grows until it is unusable.
  const TOPIC_PAGE = 20
  const topicRows = (categoryData?.team ?? []).filter((r: any) =>
    !topicSearch.trim() || r.category.toLowerCase().includes(topicSearch.trim().toLowerCase()))
  const visibleTopics = topicShowAll ? topicRows : topicRows.slice(0, TOPIC_PAGE)
  const categoryChartRows = extremes(topicRows, (r: any) => r.avg_score)
  const [heatmapSort, setHeatmapSort] = useState<{ col: string; dir: 'asc' | 'desc' }>({ col: 'coder', dir: 'asc' })
  const [matrixSort, setMatrixSort] = useState<{ col: string; dir: 'asc' | 'desc' }>({ col: 'overall', dir: 'desc' })
  // Pages forward in blocks rather than a "Show all" that mounts every card.
  // At 2000 charts, "show all" is a request to render 2000 DOM subtrees.
  const [chartValuePage, setChartValuePage] = useState(1)
  const [chartValueSearch, setChartValueSearch] = useState('')
  const [chartValueSort, setChartValueSort] = useState<'score_asc' | 'attempts_desc' | 'score_desc'>('score_asc')

  const CODER_PAGE = 25
  const CHART_VALUE_PAGE = 24

  function sortIcon(col: string, active: { col: string; dir: string }) {
    if (active.col !== col) return <span style={{ color: '#d1d5db', fontSize: 10 }}> ⇅</span>
    return <span style={{ color: '#4f46e5', fontSize: 10 }}>{active.dir === 'asc' ? ' ↑' : ' ↓'}</span>
  }
  function toggleSort(col: string, current: { col: string; dir: 'asc' | 'desc' }, setter: (v: any) => void) {
    setter(current.col === col ? { col, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })
  }

  const SPECIALTIES = ['IP-DRG', 'ED Facility', 'ED Profee', 'ED Single Path', 'SDS', 'Surgery', 'Edits', 'Denials', 'Ancillary', 'E/M']
  const activeFilterCount = Object.values(filters).filter(Boolean).length

  function applyFilters() {
    setFilters({ ...draftFilters })
    setByChart([]); setCategoryData(null); setTeachingData([]); setMatrixData(null)
    setFilterVersion(v => v + 1)
  }

  function clearFilters() {
    setDraftFilters({})
    setFilters({})
    setByChart([]); setCategoryData(null); setTeachingData([]); setMatrixData(null)
    setFilterVersion(v => v + 1)
  }

  /**
   * Scope is a SERVER filter — every figure on these tabs is an aggregate
   * computed in SQL, so flipping it has to make the round trip. What was not
   * acceptable was blanking the whole page while it did: the spinner replaced
   * the tab bar and the scope switch itself, so the control you had just
   * clicked vanished under you.
   *
   * Two changes: results are cached per (filters, scope) so going back to a
   * scope you have already seen is instant, and a pending fetch now shows an
   * "Updating…" marker beside the switch while the current numbers stay on
   * screen, instead of unmounting the page.
   */
  const scopeCache = useRef<Record<string, [any, any[], any[]]>>({})

  useEffect(() => {
    const key = JSON.stringify([filters, scope])
    const hit = scopeCache.current[key]
    if (hit) {
      const [ov, sp, bt] = hit
      setOverview(ov); setBySpecialty(sp); setByBatch(bt)
    }
    setRefreshing(true)
    Promise.all([
      getPLAnalyticsOverview(filters, scope),
      getPLAnalyticsBySpecialty(filters, scope),
      getPLAnalyticsByBatch(filters, scope),
    ]).then(([ov, sp, bt]) => {
      scopeCache.current[key] = [ov, sp, bt]
      setOverview(ov); setBySpecialty(sp); setByBatch(bt)
      if (ov?.ip_pass_threshold) setIpThreshold(ov.ip_pass_threshold)
      if (ov?.op_pass_threshold) setOpThreshold(ov.op_pass_threshold)
    }).catch(() => toast.error('Failed to load analytics')).finally(() => setRefreshing(false))
  }, [filters, scope])

  // Reloads on scope and filter changes too — a profile left open while the
  // scope switch is flipped would otherwise contradict the table above it.
  useEffect(() => {
    if (!profileSpecialty) { setProfile(null); return }
    // Keeping stale data on screen is right for a scope change and wrong for a
    // specialty change — the second would show one specialty's numbers under
    // another's name until the fetch landed.
    setProfile((p: any) => (p && p.specialty === profileSpecialty ? p : null))
    setProfileLoading(true)
    getPLSpecialtyProfile(profileSpecialty, filters, scope)
      .then(setProfile)
      .catch(() => toast.error('Failed to load specialty profile'))
      .finally(() => setProfileLoading(false))
  }, [profileSpecialty, filters, scope])

  useEffect(() => {
    if ((tab === 'chart' || tab === 'category') && byChart.length === 0) getPLAnalyticsByChart(filters).then(setByChart).catch(() => {})
    if (tab === 'category' && !categoryData) getPLAnalyticsByCategory({ ...filters, specialty: topicSpecialty || filters.specialty }, scope).then(setCategoryData).catch(() => {})
    if (tab === 'teaching' && teachingData.length === 0) getPLChartTeachingValue(filters, scope).then(setTeachingData).catch(() => {})
    if ((tab === 'matrix' || tab === 'coder') && !matrixData) getPLCoderMatrix(filters, scope, matrixGroupBy).then(setMatrixData).catch(() => {})
  }, [tab, filterVersion])

  // Topic Mastery honours the scope switch now, so a change has to refetch it
  // rather than leaving stale rows under a new scope label.
  // Chart Signals honours the scope switch now — it always excluded direct
  // assignments, so it could disagree with every other tab without saying so.
  useEffect(() => {
    if (tab === 'teaching') getPLChartTeachingValue(filters, scope).then(setTeachingData).catch(() => {})
    if (tab === 'matrix') getPLCoderMatrix(filters, scope, matrixGroupBy).then(setMatrixData).catch(() => {})
  }, [scope, tab, filterVersion, matrixGroupBy])

  useEffect(() => {
    if (tab === 'category') {
      getPLAnalyticsByCategory({ ...filters, specialty: topicSpecialty || filters.specialty }, scope)
        .then(setCategoryData).catch(() => {})
    }
  }, [scope, tab, filterVersion, topicSpecialty])

  useEffect(() => {
    if (tab === 'em_mdm' && emBatchId) {
      setEmLoading(true)
      getBatchEMBreakdown(emBatchId).then(setEmBreakdown).catch(() => {}).finally(() => setEmLoading(false))
    }
  }, [tab, emBatchId])

  async function fetchCoder(name: string, empId: string | null = coderEmpId) {
    if (!name && !empId) return
    setCoderLoading(true)
    setCoderSummary(null)
    setCoderTrend([])
    setCoderEmpty(false)
    const [summary, trend] = await Promise.all([
      getCoderSummary(name, filters, empId).catch(() => null),
      getCoderTrend(name, filters, empId).catch(() => null),
    ])
    setLoadedCoder(name)
    setLoadedEmpId(empId)
    // An empty result under an active filter is a real answer, not a failure —
    // show it on screen rather than leaving the previous numbers up.
    setCoderEmpty(!summary && !trend?.length)
    if (summary) setCoderSummary(summary)
    if (trend) setCoderTrend(trend)
    setCoderLoading(false)
  }

  function loadCoderTrend() { fetchCoder(coderName.trim(), coderEmpId) }

  function jumpToCoder(name: string, empId: string | null = null) {
    setCoderName(name)
    setCoderEmpId(empId)
    setTab('coder')
    fetchCoder(name, empId)
  }

  // Re-fetch whenever the date/specialty filter changes. Without this the coder
  // tab kept showing unfiltered totals while the PDF button sent the NEW filter,
  // so the screen and the download disagreed — and an empty range only surfaced
  // as a blank tab from the download.
  useEffect(() => {
    if (loadedCoder || loadedEmpId) fetchCoder(loadedCoder, loadedEmpId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterVersion])

  async function toggleChartDetail(chartNumber: string) {
    if (expandedChart === chartNumber) { setExpandedChart(null); return }
    if (chartDetail[chartNumber]) { setExpandedChart(chartNumber); return }
    try {
      const d = await getPLChartDetail(chartNumber)
      setChartDetail(prev => ({ ...prev, [chartNumber]: d }))
      setExpandedChart(chartNumber)
    } catch { toast.error('Failed to load chart detail') }
  }

  const coderLink = (name: string) => (
    <button onClick={() => jumpToCoder(name)}
      style={{ background: 'none', border: 'none', padding: 0, color: '#4f46e5', fontWeight: 700, cursor: 'pointer', fontSize: 'inherit', textDecoration: 'underline' }}>
      {name}
    </button>
  )

  const TABS = [
    { key: 'overview', label: 'Overview' },
    { key: 'specialty', label: 'By Specialty' },
    { key: 'batch', label: 'By Batch' },
    { key: 'coder', label: 'Coder Profile' },
    { key: 'category', label: 'Topic Mastery' },
    { key: 'teaching', label: 'Chart Signals' },
    { key: 'matrix', label: 'Coder Matrix' },
    { key: 'chart', label: 'By Chart' },
    { key: 'em_mdm', label: 'E/M MDM' },
  ]

  // Only the very first load takes over the page. After that there is always
  // something real on screen to update in place.
  if (refreshing && !overview) return <div style={styles.center}><Loader size={24} /></div>

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={styles.sectionTitle}>Analytics</span>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '10px 14px', background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 8, flexWrap: 'wrap' as const }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginRight: 4 }}>Filter</span>
        <input type="date" style={{ ...styles.input, width: 140, fontSize: 12 }}
          value={draftFilters.from_date || ''}
          onChange={e => setDraftFilters(f => ({ ...f, from_date: e.target.value || undefined }))} />
        <span style={{ fontSize: 12, color: '#9ca3af' }}>→</span>
        <input type="date" style={{ ...styles.input, width: 140, fontSize: 12 }}
          value={draftFilters.to_date || ''}
          onChange={e => setDraftFilters(f => ({ ...f, to_date: e.target.value || undefined }))} />
        <select style={{ ...styles.select, fontSize: 12 }}
          value={draftFilters.specialty || ''}
          onChange={e => setDraftFilters(f => ({ ...f, specialty: e.target.value || undefined }))}>
          <option value="">All specialties</option>
          {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button style={styles.primaryBtn} onClick={applyFilters}>Apply</button>
        {activeFilterCount > 0 && (
          <button style={styles.outlineBtn} onClick={clearFilters}>
            Clear {activeFilterCount > 0 ? `(${activeFilterCount})` : ''}
          </button>
        )}
        {activeFilterCount > 0 && (
          <span style={{ fontSize: 11, color: '#4f46e5', fontWeight: 700 }}>Filtered view active</span>
        )}
        {/* Names what the file IS — one row per graded chart, every coder —
            rather than what someone might do with it afterwards. Honours the
            same filters as the charts above. */}
        <button
          style={{ ...styles.outlineBtn, marginLeft: 'auto' }}
          title="Excel: one row per graded chart, all coders, current filters applied"
          onClick={async () => {
            try { await downloadCoderPerformanceXlsx(filters) }
            catch { toast.error('No results match the current filter') }
          }}>
          Export All Results (.xlsx)
        </button>
      </div>

      <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', alignSelf: 'flex-start', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.key}
            style={tab === t.key ? { ...styles.modeTab, background: '#4f46e5', color: '#fff', padding: '7px 16px' } : { ...styles.modeTab, padding: '7px 16px' }}
            onClick={() => setTab(t.key as any)}>{t.label}</button>
        ))}
      </div>

      {/* Direct assignments are one-off charts, so folding them into batch
          trends by default would change what the trend line means. Offered as a
          switch instead of being silently absent.

          Rendered outside the tab bodies because all three scope-aware tabs are
          driven by the same state: it lived inside Overview, so By Specialty
          silently inherited whatever had been picked there with nothing on
          screen saying so. */}
      {(tab === 'overview' || tab === 'specialty' || tab === 'batch' || tab === 'category' || tab === 'teaching' || tab === 'matrix') && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const, marginBottom: 16 }}>
          <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
            {([['formal', 'Batches'], ['direct', 'Direct Assignments'], ['all', 'Both']] as const).map(([k, label]) => (
              <button key={k} onClick={() => setScope(k)}
                style={{
                  padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                  borderRight: k === 'all' ? 'none' : '1px solid #e5e7eb',
                  background: scope === k ? '#0f766e' : '#fff',
                  color: scope === k ? '#fff' : '#6b7280',
                }}>
                {label}
              </button>
            ))}
          </div>
          {refreshing && (
            <span style={{ fontSize: 11, color: '#0f766e', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <Loader size={12} /> Updating…
            </span>
          )}
          <span style={{ fontSize: 11, color: '#9ca3af' }}>
            {scope === 'formal' && 'Formal batch work only — direct assignments shown separately'}
            {scope === 'direct' && 'One-off direct assignments only'}
            {scope === 'all' && 'Batches and direct assignments combined'}
            {tab === 'overview' && ' · batch counts by created date, grading by graded date'}
          </span>
        </div>
      )}

      {tab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {!overview ? (
            <div style={styles.emptyState}>No grading data yet</div>
          ) : (
            <>
              <div style={styles.statsRow}>
                {[
                  { label: 'Total Batches', value: overview.total_batches },
                  { label: 'Open Batches', value: overview.open_batches ?? 0, color: '#2563eb' },
                  { label: 'Closed Batches', value: overview.complete_batches ?? 0, color: '#16a34a' },
                  { label: 'Total Graded', value: overview.total_graded },
                  { label: 'Graded Chart Pass Rate', value: `${overview.overall_pass_rate}%`, color: rc(overview.overall_pass_rate) },
                ].map(s => (
                  <div key={s.label} style={styles.statCard}>
                    <div style={{ ...styles.statValue, color: (s as any).color || '#111' }}>{s.value}</div>
                    <div style={styles.statLabel}>{s.label}</div>
                  </div>
                ))}
              </div>
              {/* Attention banner */}
              {overview.total_graded > 0 && (() => {
                // Two DIFFERENT signals, deliberately kept apart — they are not
                // measured on the same scale:
                //   avg_score  is a per-chart SCORE, so it is the thing
                //              pass_threshold governs and can be compared to it
                //   pass_rate  is the SHARE of charts that passed, a population
                //              figure; comparing it to a score threshold is a
                //              units error (85% of OP charts passing is healthy,
                //              yet 85 < 90 would flag it)
                const reasons = (s: any) => {
                  const out: string[] = []
                  const pt = thresholdFor(s.specialty)
                  if (s.avg_score < pt) out.push(`average score ${s.avg_score}% is below the ${pt}% pass mark`)
                  if (s.pass_rate < PASS_RATE_TARGET) out.push(`only ${s.pass_rate}% of charts passed`)
                  return out
                }
                const atRisk = bySpecialty
                  .map((s: any) => ({ ...s, why: reasons(s) }))
                  .filter((s: any) => s.why.length)
                if (!atRisk.length) return null
                return (
                  <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 10, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#92400e' }}>⚠ Needs attention</div>
                    {atRisk.map((s: any) => (
                      <div key={s.specialty} style={{ fontSize: 13, color: '#92400e' }}>
                        <strong>{s.specialty}</strong> — {s.why.join('; ')}
                        {s.pass_rate < 50 && <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, background: '#fecaca', color: '#991b1b', padding: '1px 8px', borderRadius: 10 }}>Critical</span>}
                      </div>
                    ))}
                  </div>
                )
              })()}

              {/* Mini batch trend. Its own specialty picker, deliberately not
                  the page-wide filter — narrowing this one chart should not
                  re-scope the tiles and the Needs-attention banner above it. */}
              {byBatch.length > 1 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' as const }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5 }}>
                      Pass rate trend — last {miniTrend.length} of {miniPool.length}
                      {miniSpecialty ? ` ${miniSpecialty}` : ''} {scope === 'direct' ? 'assignments' : 'batches'}
                    </div>
                    <select value={miniSpecialty} onChange={e => setMiniSpecialty(e.target.value)}
                      style={{ ...styles.select, marginLeft: 'auto', fontSize: 12, padding: '5px 10px' }}>
                      <option value="">All specialties</option>
                      {SPECIALTIES.filter(sp => byBatch.some((b: any) => b.specialty === sp)).map(sp => (
                        <option key={sp} value={sp}>{sp}</option>
                      ))}
                    </select>
                  </div>
                  {miniTrend.length === 0 ? (
                    <div style={{ ...styles.emptyState, margin: 0 }}>No graded {miniSpecialty} batches in range.</div>
                  ) : (
                  <ResponsiveContainer width="100%" height={100}>
                    <LineChart data={miniTrend.map((b: any) => ({ ...b, label: axisLabel(b.batch_name, 12) }))} margin={{ left: 0, right: 16, top: 4, bottom: 4 }}>
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                      <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} width={32} />
                      <Tooltip formatter={(v: any) => [`${v}%`, 'Pass Rate']} contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                      <Line type="monotone" dataKey="pass_rate" stroke="#16a34a" strokeWidth={2} dot={{ r: 4, fill: '#16a34a' }} />
                    </LineChart>
                  </ResponsiveContainer>
                  )}
                </div>
              )}

              {overview.total_graded === 0 ? (
                <div style={{ ...styles.warnBox, lineHeight: 1.6 }}>
                  No grading results yet. Run an allocation cycle inside a batch, then have coders complete their practice sessions to unlock analytics.
                </div>
              ) : (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px', display: 'flex', alignItems: 'center', gap: 32 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 4 }}>Overall Pass / Fail Split</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{overview.total_graded} graded submissions</div>
                  </div>
                  <PieChart width={180} height={180}>
                    <Pie data={[{ name: 'Passed', value: overview.total_passed }, { name: 'Failed', value: overview.total_graded - overview.total_passed }]}
                      cx={90} cy={90} innerRadius={52} outerRadius={80} paddingAngle={3} dataKey="value">
                      <Cell fill="#16a34a" /><Cell fill="#dc2626" />
                    </Pie>
                    <Tooltip formatter={(v: any, name: any) => [v, name]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'specialty' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>

          <div>
            <div style={{ fontSize: 14, fontWeight: 800, color: '#111', marginBottom: 4 }}>All Specialties Compared</div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>Only specialties with graded results appear here</div>
          </div>

          {bySpecialty.length === 0 ? <div style={styles.emptyState}>No specialty data yet — upload and grade at least one batch to see a breakdown here.</div> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Avg Grading Score & Pass Rate by Specialty</div>
                <ResponsiveContainer width="100%" height={Math.max(200, bySpecialty.length * 56)}>
                  <BarChart data={bySpecialty} layout="vertical" margin={{ left: 20, right: 50, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="specialty" width={110} tick={{ fontSize: 12, fontWeight: 600 }} />
                    <Tooltip formatter={(v: any, name: any) => [`${v}%`, name === 'avg_score' ? 'Avg Grading Score' : 'Pass Rate']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'avg_score' ? 'Avg Grading Score' : 'Pass Rate'} />
                    <Bar dataKey="avg_score" name="avg_score" radius={[0, 4, 4, 0]} fill="#4f46e5" fillOpacity={0.85} />
                    <Bar dataKey="pass_rate" name="pass_rate" radius={[0, 4, 4, 0]} fill="#16a34a" fillOpacity={0.85} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                {/* Pass Mark is shown because the two rate columns are NOT
                    comparable across rows without it — 85% average is a pass in
                    IP-DRG (80) and a fail in SDS (90), and the bar chart above
                    puts them side by side as though one bar were simply longer. */}
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 0.8fr 0.8fr 1.2fr 1.2fr 1fr' }}>
                  <span>Specialty</span><span>Graded</span><span>Pass Mark</span>
                  <span>Avg Grading Score</span><span>Chart Pass Rate</span><span></span>
                </div>
                {/* Weakest first — a trainer opens this tab to find where to
                    intervene, not to read an alphabetical list. */}
                {[...bySpecialty].sort((a: any, b: any) => a.avg_score - b.avg_score).map((r: any, i: number) => {
                  const pt = thresholdFor(r.specialty)
                  const needsReview = r.avg_score < pt || r.pass_rate < PASS_RATE_TARGET
                  const lowSample = r.total < LOW_SAMPLE
                  const isOpen = profileSpecialty === r.specialty
                  return (
                    <div key={r.specialty} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                      onClick={() => {
                        // Always select, never toggle off. Toggling made sense
                        // when the row expanded itself; against a panel further
                        // down the page, re-clicking the row you are studying
                        // silently emptied it.
                        setProfileSpecialty(r.specialty)
                        // A click that loads the panel off-screen looks like a
                        // click that did nothing — which is exactly how it read.
                        document.getElementById('pl-specialty-deepdive')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                      }}
                      style={{
                        ...styles.tableRow, gridTemplateColumns: '2fr 0.8fr 0.8fr 1.2fr 1.2fr 1fr',
                        cursor: 'pointer', alignItems: 'center',
                        // The selected row stays marked, so the panel below is
                        // visibly tied to a row rather than floating free.
                        background: isOpen ? '#ecfeff' : undefined,
                        boxShadow: isOpen ? 'inset 3px 0 0 #0f766e' : undefined,
                      }}>
                      {/* No ▸/▾ here. That marker means "expands in place" on
                          By Chart and By Category; this row sends you to a panel
                          further down, and borrowing the same glyph for a
                          different action is how the click came to feel broken. */}
                      <span style={{ fontWeight: 600, color: isOpen ? '#0f766e' : undefined }}>{r.specialty}</span>
                      <span>
                        {r.total}
                        {lowSample && <span title={`Fewer than ${LOW_SAMPLE} graded charts — these percentages move a lot on one result`}
                          style={{ marginLeft: 6, fontSize: 10, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '1px 6px', borderRadius: 8 }}>Low sample</span>}
                      </span>
                      <span style={{ color: '#6b7280' }}>{pt != null ? `${pt}%` : '—'}</span>
                      <span style={{ fontWeight: 700, color: sc(r.avg_score, r.specialty) }}>{r.avg_score}%</span>
                      <span style={{ fontWeight: 700, color: rc(r.pass_rate) }}>{r.pass_rate}%</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                        {needsReview
                          ? <span style={{ fontSize: 10, fontWeight: 700, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 10 }}>Needs review</span>
                          : <span />}
                        {/* Names the destination instead of implying expansion. */}
                        <span style={{ fontSize: 11, fontWeight: 700, color: isOpen ? '#0f766e' : '#9ca3af', whiteSpace: 'nowrap' as const }}>
                          {isOpen ? 'Shown below' : 'Deep dive ↓'}
                        </span>
                      </span>
                    </div>
                  )
                })}
              </div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>
                Pass Mark is the per-chart score a coder must reach. Chart Pass Rate is the share of graded
                charts that reached it — a population figure, not a score. Click any row to open that
                specialty in the Deep Dive below.
              </div>

            </div>
          )}

          {/* ── Deep dive ────────────────────────────────────────────────
              Below the comparison, not above it. The tab reads general →
              specific: find the weak specialty, then drill into it, which is
              also where a row click lands you.

              It sat above, directly beneath the scope switch, which made the
              switch look like it governed this panel — and the panel's first
              section, Library, is the one part of the tab scope does NOT
              affect (a chart exists however it was assigned).

              Not gated on there being grading data: library and readiness are
              real facts about a specialty before anyone has practised it, and
              "nothing has been attempted yet" is itself an answer. The
              selector lists every specialty for the same reason — the
              comparison above can only offer the graded ones. */}
          <div id="pl-specialty-deepdive" style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' as const }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: '#111' }}>Specialty Deep Dive</div>
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>Library, participation, outcome and standing for one specialty</div>
              </div>
              <select value={profileSpecialty || ''} onChange={e => setProfileSpecialty(e.target.value || null)}
                style={{ ...styles.select, minWidth: 200, marginLeft: 'auto' }}>
                <option value="">Select a specialty…</option>
                {SPECIALTIES.map(s => {
                  const graded = bySpecialty.find((r: any) => r.specialty === s)
                  return <option key={s} value={s}>{s}{graded ? ` (${graded.total} graded)` : ' (no grading yet)'}</option>
                })}
              </select>
              {profileSpecialty && (
                <button onClick={() => setProfileSpecialty(null)} style={{ ...styles.outlineBtn, padding: '6px 12px', fontSize: 12 }}>Clear</button>
              )}
            </div>

            {!profileSpecialty ? (
              <div style={{ ...styles.emptyState, margin: 0 }}>
                Pick a specialty above to see how many charts it has, how many are ready to practise,
                who has attempted them, how it compares with the other specialties, and which charts
                people are struggling on.
              </div>
            ) : !profile ? (
              // Same rule as the page: only an empty panel waits: a scope flip
              // with a profile already open updates it rather than clearing it.
              <div style={{ ...styles.emptyState, margin: 0 }}>Loading {profileSpecialty}…</div>
            ) : (
                  <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' as const }}>
                      <div style={{ fontSize: 15, fontWeight: 800, color: '#111' }}>{profile.specialty}</div>
                      <div style={{ fontSize: 11, color: '#6b7280' }}>
                        {profile.pass_threshold != null ? `pass mark ${profile.pass_threshold}%` : 'rubric-graded — no numeric pass mark'}
                        {' · '}{scope === 'formal' ? 'batch work' : scope === 'direct' ? 'direct assignments' : 'batches and direct'}
                      </div>
                    </div>

                    {/* Library — capacity, not outcome. A specialty can look
                        healthy on scores while having almost nothing left to
                        practise on, and nothing else in analytics shows that. */}
                    <div>
                      {/* Says so out loud: this is the one group the scope
                          switch does not move, and silent invariance under a
                          control is indistinguishable from a broken control. */}
                      <div style={sectionLabel}>
                        Library
                        <span style={{ marginLeft: 8, fontWeight: 600, textTransform: 'none' as const, letterSpacing: 0, color: '#9ca3af' }}>
                          — all charts, unaffected by the Batches / Direct filter
                        </span>
                      </div>
                      <div style={styles.statsRow}>
                        <Box label="Charts" value={profile.library.total_charts} />
                        <Box label="Ready to Practise" value={profile.library.practice_ready} color="#16a34a"
                          hint={profile.library.uses_answer_keys ? 'has a complete answer key' : 'rubric-graded — no key needed'} />
                        <Box label="Awaiting Key" value={profile.library.awaiting_key}
                          color={profile.library.awaiting_key > 0 ? '#d97706' : '#111'} hint="cannot be graded yet" />
                        <Box label="Charts Attempted" value={profile.activity.charts_attempted}
                          hint={`of ${profile.library.practice_ready} ready`} />
                      </div>
                    </div>

                    <div>
                      <div style={sectionLabel}>
                        Participation &amp; Outcome
                        <span style={{ marginLeft: 8, fontWeight: 600, textTransform: 'none' as const, letterSpacing: 0, color: '#9ca3af' }}>
                          — {scope === 'formal' ? 'batch work only' : scope === 'direct' ? 'direct assignments only' : 'batches and direct assignments'}
                        </span>
                      </div>
                      <div style={styles.statsRow}>
                        <Box label="Attempts" value={profile.activity.attempts} />
                        <Box label="Coders" value={profile.activity.coders} />
                        <Box label="Avg Grading Score" value={`${profile.performance.avg_score}%`}
                          color={sc(profile.performance.avg_score, profile.specialty)} hint="per-chart score" />
                        <Box label="Chart Pass Rate" value={`${profile.performance.chart_pass_rate}%`}
                          color={rc(profile.performance.chart_pass_rate)} hint="share of charts that passed" />
                        <Box label="Coders Clearing" value={`${profile.performance.coder_clear_rate}%`}
                          color={rc(profile.performance.coder_clear_rate)}
                          hint={`${profile.performance.coders_cleared} of ${profile.activity.coders} — ${profile.performance.coder_clear_rule}`} />
                      </div>
                    </div>

                    {/* The one figure a per-specialty view cannot work out for
                        itself: where this sits among the others. */}
                    <div>
                      <div style={sectionLabel}>Standing vs Other Specialties</div>
                      <div style={styles.statsRow}>
                        <Box label="Rank — Avg Score" value={profile.standing.rank_by_avg_score ? `#${profile.standing.rank_by_avg_score}` : '—'}
                          hint={`of ${profile.standing.peers} specialties`} />
                        <Box label="Rank — Pass Rate" value={profile.standing.rank_by_pass_rate ? `#${profile.standing.rank_by_pass_rate}` : '—'}
                          hint={`of ${profile.standing.peers} specialties`} />
                        <Box label="All-Specialty Avg Score" value={profile.standing.peer_avg_score != null ? `${profile.standing.peer_avg_score}%` : '—'}
                          hint={profile.standing.peer_avg_score != null
                            ? `${profile.performance.avg_score >= profile.standing.peer_avg_score ? '+' : ''}${(profile.performance.avg_score - profile.standing.peer_avg_score).toFixed(1)} pts vs this specialty` : ''} />
                      </div>
                    </div>

                    <div>
                      <div style={sectionLabel}>Chart Difficulty in Practice</div>
                      <div style={styles.statsRow}>
                        <Box label="Most Clear It" value={profile.charts.well_cleared} color="#16a34a"
                          hint={`≥${profile.charts.well_cleared_at}% of attempts passed`} />
                        <Box label="Most Struggle" value={profile.charts.struggling} color="#dc2626"
                          hint={`<${profile.charts.struggling_below}% of attempts passed`} />
                        <Box label="Too Few Attempts" value={profile.charts.low_sample}
                          hint={`under ${profile.charts.min_attempts} attempts — not rated`} />
                      </div>
                      {profile.charts.struggling_list.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                          <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>Hardest charts — candidates for a teaching session</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8 }}>
                            {profile.charts.struggling_list.map((c: any) => (
                              <span key={c.chart_number} style={{ fontSize: 11, background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca', padding: '3px 10px', borderRadius: 10 }}>
                                <strong>{c.chart_number}</strong> · {c.pass_rate}% passed · {c.attempts} attempts
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {profile.top_missed_codes.length > 0 && (
                      <div>
                        <div style={sectionLabel}>Most Missed Codes</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8 }}>
                          {profile.top_missed_codes.map((m: any) => (
                            <span key={m.code} style={{ fontSize: 11, background: '#eef2ff', color: '#3730a3', border: '1px solid #c7d2fe', padding: '3px 10px', borderRadius: 10 }}>
                              <strong>{m.code}</strong> · missed {m.count}×
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
            )}
          </div>
        </div>
      )}

      {tab === 'chart' && (
        <div>
          {byChart.length === 0 ? <div style={styles.emptyState}>No chart data yet — charts appear here once grading results are submitted.</div> : (
            <div style={styles.table}>
              <div style={{ ...styles.tableHeader, gridTemplateColumns: '120px 1fr 1fr 80px 90px' }}>
                <span>Chart</span><span>Category</span><span>Specialty</span>
                <span style={{ textAlign: 'center' as const }}>Attempts</span>
                <span style={{ textAlign: 'center' as const }}>Avg Grading Score</span>
              </div>
              {byChart.map((r: any, i: number) => (
                <div key={r.chart_number} style={{ borderBottom: '1px solid #f3f4f6', background: expandedChart === r.chart_number ? '#f5f3ff' : i % 2 === 1 ? '#f9fafb' : '#fff' }}>
                  {/* Main data row */}
                  <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 80px 90px', padding: '10px 16px', alignItems: 'center', cursor: 'pointer' }}
                    onClick={() => toggleChartDetail(r.chart_number)}>
                    <span style={{ fontWeight: 700, color: '#4f46e5', fontSize: 13 }}>{r.chart_number} {expandedChart === r.chart_number ? '▲' : '▼'}</span>
                    <span style={{ fontSize: 12, color: '#374151' }}>{r.category}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span style={{ fontSize: 13, textAlign: 'center' as const }}>{r.attempt_count}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, textAlign: 'center' as const, color: sc(r.avg_score, r.specialty) }}>{r.avg_score}%</span>
                  </div>
                  {/* Top missed badges — only when collapsed */}
                  {r.top_missed?.length > 0 && expandedChart !== r.chart_number && (
                    <div style={{ padding: '0 16px 8px 136px', display: 'flex', gap: 6, flexWrap: 'wrap' as const }}>
                      {r.top_missed.map(([code, cnt]: any) => (
                        <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '2px 8px', borderRadius: 10 }}>{code} {cnt}×</span>
                      ))}
                    </div>
                  )}
                  {expandedChart === r.chart_number && chartDetail[r.chart_number] && (
                    <div style={{ padding: '12px 16px', background: '#fafafa', borderTop: '1px solid #ede9fe' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>Coder breakdown</div>
                      {chartDetail[r.chart_number].coders.length === 0 ? (
                        <div style={{ fontSize: 12, color: '#9ca3af' }}>No graded results for this chart.</div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {chartDetail[r.chart_number].coders.slice(0, 8).map((c: any) => (
                            <div key={`${c.coder_name}-${c.batch_name}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 10px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12 }}>
                              <span style={{ minWidth: 140 }}>{coderLink(c.coder_name)}</span>
                              <span style={{ fontSize: 11, color: '#9ca3af', flex: 1 }}>{c.batch_name}</span>
                              <span style={{ fontWeight: 700, color: sc(c.total_score) }}>{c.total_score}%</span>
                              <span style={{ fontWeight: 700, fontSize: 11, color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{c.pass_fail}</span>
                              {c.missed_codes?.length > 0 && (
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' as const, alignItems: 'center' }}>
                                  {c.missed_codes.slice(0, 5).map((code: string) => (
                                    <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '1px 6px', borderRadius: 8 }}>{code}</span>
                                  ))}
                                  {c.missed_codes.length > 5 && (
                                    <span style={{ fontSize: 10, color: '#9ca3af' }}>+{c.missed_codes.length - 5} more</span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                          {chartDetail[r.chart_number].coders.length > 8 && (
                            <div style={{ fontSize: 11, color: '#6b7280', padding: '4px 10px' }}>
                              + {chartDetail[r.chart_number].coders.length - 8} more attempts — use Coder Matrix for full view
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'batch' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Under the Direct scope every row IS a direct assignment, so
              calling the column "Batch" describes nothing on screen. */}
          {/* The old copy said "close a batch after grading". Closing has
              nothing to do with it — the endpoint skips any batch with no
              scored results and includes open ones freely. It sent people to
              close batches to fix an emptiness that closing does not fix. */}
          {byBatch.length === 0 ? (
            <div style={styles.emptyState}>
              No graded {unitPlural} yet — this tab shows {unitPlural} that have at least one graded
              result, open or closed. Grade a submission to see trends over time.
            </div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' as const }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>Pass Rate &amp; Avg Grading Score Over {unitLabel === 'Assignment' ? 'Assignments' : 'Batches'}</div>
                  {/* A trend line stops being readable long before it stops
                      being drawable. Windowed to the most recent, because the
                      question a trend answers is "where is this heading". */}
                  <button
                    title="Export this table to Excel — same rows, filters and scope"
                    onClick={() => downloadBatchAnalyticsXlsx(filters, scope)}
                    style={{ ...styles.outlineBtn, fontSize: 12, padding: '5px 12px', marginLeft: byBatch.length > TREND_WINDOWS[0] ? 8 : 'auto' }}>
                    Export Table
                  </button>
                  {byBatch.length > TREND_WINDOWS[0] && (
                    <div style={{ display: 'flex', gap: 4, marginLeft: 'auto', alignItems: 'center' }}>
                      <span style={{ fontSize: 11, color: '#9ca3af' }}>Show last</span>
                      {[...TREND_WINDOWS, 'all' as const].map(w => (
                        <button key={String(w)} onClick={() => setTrendWindow(w)}
                          style={{
                            fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6, cursor: 'pointer',
                            border: '1px solid ' + (trendWindow === w ? '#0f766e' : '#e5e7eb'),
                            background: trendWindow === w ? '#0f766e' : '#fff',
                            color: trendWindow === w ? '#fff' : '#6b7280',
                          }}>{w === 'all' ? 'All' : w}</button>
                      ))}
                      <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 4 }}>of {byBatch.length}</span>
                    </div>
                  )}
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={recent(byBatch, trendWindow).map(b => ({ ...b, label: axisLabel(b.batch_name) }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={tickInterval(recent(byBatch, trendWindow).length)} angle={-20} textAnchor="end" height={52} />
                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any, name: any) => [`${v}%`, name === 'pass_rate' ? 'Pass Rate' : 'Avg Grading Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'pass_rate' ? 'Pass Rate' : 'Avg Grading Score'} />
                    <Line type="monotone" dataKey="pass_rate" stroke="#16a34a" strokeWidth={2.5} dot={{ r: 5, fill: '#16a34a' }} activeDot={{ r: 7 }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 5, fill: '#4f46e5' }} activeDot={{ r: 7 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '1.8fr 96px 90px 64px 64px 90px 90px 140px' }}>
                  <span>{unitLabel}</span><span>Specialty</span><span>Created</span>
                  <span>Coders</span><span>Charts</span>
                  <span>Avg Grading Score</span><span>Chart Pass Rate</span><span></span>
                </div>
                {/* Newest first here, oldest first in the chart above. A table
                    is read top-down for "what happened lately"; a trend line is
                    meaningless unless time runs left to right. */}
                {[...byBatch].reverse().map((r: any, i: number) => {
                  const pt = thresholdFor(r.specialty)
                  const belowTarget = r.avg_score < pt || r.pass_rate < PASS_RATE_TARGET
                  const lowSample = r.graded_count < LOW_SAMPLE
                  return (
                    <div key={r.batch_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, gridTemplateColumns: '1.8fr 96px 90px 64px 64px 90px 90px 140px', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' as const }}>
                        {r.batch_name}
                        {belowTarget && <span title={`Avg below the ${pt}% pass mark, or under ${PASS_RATE_TARGET}% of charts passing`}
                          style={{ fontSize: 10, fontWeight: 700, background: '#fef3c7', color: '#92400e', padding: '1px 7px', borderRadius: 10 }}>Below target</span>}
                        {lowSample && <span title={`Fewer than ${LOW_SAMPLE} graded charts — these percentages move a lot on one result`}
                          style={{ fontSize: 10, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '1px 7px', borderRadius: 10 }}>Low sample</span>}
                      </span>
                      <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                      <span style={{ fontSize: 12, color: '#6b7280' }} title={r.last_graded_at ? `Last graded ${r.last_graded_at.slice(0, 10)}` : undefined}>
                        {r.created_at ? r.created_at.slice(0, 10) : '—'}
                      </span>
                      <span>{r.coder_count}</span>
                      <span title={`${r.graded_count} graded results across ${r.chart_count} charts`}>{r.chart_count}</span>
                      <span style={{ fontWeight: 700, color: sc(r.avg_score, r.specialty) }}>{r.avg_score}%</span>
                      <span style={{ fontWeight: 700, color: rc(r.pass_rate) }}>{r.pass_rate}%</span>
                      <span style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        {/* Every row here has graded results by definition —
                            the endpoint skips batches without them — so this
                            is never the disabled case the batch list has. */}
                        <button title="Batch performance report (PDF)"
                          onClick={async () => {
                            try { await downloadBatchReportPdf(r.batch_id) }
                            catch { toast.error(`No report could be generated for ${r.batch_name}`) }
                          }}
                          style={{ fontSize: 11, fontWeight: 700, color: '#0f766e', background: 'none', border: '1px solid #99f6e4', borderRadius: 6, padding: '4px 9px', cursor: 'pointer' }}>
                          PDF
                        </button>
                        {onOpenBatch && (
                          <button onClick={() => onOpenBatch(r.batch_id)}
                            style={{ fontSize: 11, fontWeight: 700, color: '#4f46e5', background: 'none', border: '1px solid #e0e7ff', borderRadius: 6, padding: '4px 9px', cursor: 'pointer' }}>
                            Details →
                          </button>
                        )}
                      </span>
                    </div>
                  )
                })}
              </div>
              {/* The date column and the date filter are not the same field.
                  Saying so is the fix — switching the filter to graded_at would
                  be worse, since a batch would then half-appear whenever its
                  results straddled the range boundary. */}
              <div style={{ fontSize: 11, color: '#9ca3af' }}>
                Created is when the {unitLabel.toLowerCase()} was set up, and is also what the date filter
                above narrows on — not when the work was graded. Hover a date for the last graded date.
                Chart Pass Rate is the share of graded charts that passed; the {unitLabel.toLowerCase()}
                {' '}results screen reports a per-coder pass rate instead.
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'coder' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Buttons sized to match the input so the row reads as one control
              strip rather than three items of different heights. */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' as const }}>
            <CoderPicker
              value={coderName}
              empId={coderEmpId}
              width={320}
              onSelect={(name, empId) => {
                setCoderName(name)
                setCoderEmpId(empId)
                if (name) fetchCoder(name, empId)
              }}
            />
            <button style={{ ...styles.primaryBtn, ...ctrlH }} onClick={loadCoderTrend} disabled={coderLoading}>
              {coderLoading ? 'Loading…' : 'Look Up'}
            </button>
            {/* Only offered when there is something to put in the report — it used
                to stay clickable with no data in range and opened a blank tab. */}
            {(coderSummary || coderTrend.length > 0) && (
              <button style={{ ...styles.outlineBtn, ...ctrlH }} onClick={async () => {
                try {
                  await downloadCoderReportPdf(loadedCoder, filters, loadedEmpId)
                } catch {
                  toast.error('No report could be generated for this coder in the selected range')
                }
              }}>
                Download PDF Report
              </button>
            )}
            {(coderSummary || coderTrend.length > 0) && (
              <button style={{ ...styles.outlineBtn, ...ctrlH }}
                title="Excel: one row per graded chart for this coder"
                onClick={async () => {
                try { await downloadCoderPerformanceXlsx(filters, loadedCoder, loadedEmpId) }
                catch { toast.error('Could not export this coder') }
              }}>
                Export Results (.xlsx)
              </button>
            )}
            {activeFilterCount > 0 && (coderSummary || coderTrend.length > 0) && (
              <span style={{ fontSize: 11, color: '#6b7280' }}>
                Figures below reflect the active filter
              </span>
            )}
          </div>

          {coderLoading ? (
            <div style={styles.emptyState}><Loader size={18} /> Loading {loadedCoder || coderName}…</div>
          ) : coderEmpty ? (
            /* Distinct from the initial prompt: we DID look, and the filter
               excluded everything. Saying so here is what stops the download
               button being the first sign of it. */
            <div style={{ ...styles.emptyState, color: '#b45309' }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>
                No results for {loadedCoder} in the selected range
              </div>
              <div style={{ fontSize: 12 }}>
                {filters.from_date || filters.to_date
                  ? `Nothing graded between ${filters.from_date || 'the beginning'} and ${filters.to_date || 'today'}`
                  : 'This coder has no graded results'}
                {filters.specialty ? ` for ${filters.specialty}` : ''}.
                {activeFilterCount > 0 && ' Widen or clear the filter to see more.'}
              </div>
            </div>
          ) : !coderSummary && coderTrend.length === 0 ? (
            <div style={styles.emptyState}>Enter the coder's name and press Look Up to see their full performance profile — batch work and direct assignments together.</div>
          ) : (
            <>
              {/* Summary stat cards */}
              {coderSummary && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {/* Identity, what they work on, and whether they are current.
                      "Charts Completed: 40" says nothing about whether that is
                      40 IP-DRG charts or 40 across six specialties, and nothing
                      about whether the last one was last week or last year. */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const, fontSize: 12, color: '#6b7280' }}>
                    {coderSummary.emp_id && <span style={{ fontWeight: 600 }}>Emp ID: {coderSummary.emp_id}</span>}
                    {(coderSummary.specialty_mix || []).map((m: any) => (
                      <span key={m.specialty} style={{ fontSize: 11, fontWeight: 700, background: '#f1f5f9', color: '#475569', padding: '2px 9px', borderRadius: 10 }}>
                        {m.specialty} · {m.charts} chart{m.charts !== 1 ? 's' : ''}
                      </span>
                    ))}
                    {coderSummary.last_activity && (() => {
                      const days = Math.floor((Date.now() - new Date(coderSummary.last_activity).getTime()) / 86400000)
                      const stale = days > 60
                      return (
                        <span title="Most recent graded result"
                          style={{ fontSize: 11, fontWeight: 700, marginLeft: 'auto',
                                   color: stale ? '#92400e' : '#6b7280',
                                   background: stale ? '#fef3c7' : '#f8fafc',
                                   padding: '2px 9px', borderRadius: 10 }}>
                          Last graded {coderSummary.last_activity.slice(0, 10)}
                          {stale ? ` · ${days} days ago` : ''}
                        </span>
                      )
                    })()}
                  </div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>
                    Coder views include formal batch work and direct assignments together — team views exclude direct.
                  </div>
                  <div style={styles.statsRow}>
                    <div style={styles.statCard}>
                      <div style={styles.statValue}>{coderSummary.total_charts ?? 0}</div>
                      <div style={styles.statLabel}>Charts Completed</div>
                    </div>
                    <div style={styles.statCard}>
                      <div style={{ ...styles.statValue, color: '#16a34a' }}>{coderSummary.charts_passed ?? 0}</div>
                      <div style={styles.statLabel}>Charts Passed</div>
                    </div>
                    {coderSummary.weighted_accuracy != null && (
                      <div style={{ ...styles.statCard, background: '#fffbeb', borderLeft: '3px solid #f59e0b' }}>
                        <div style={{ ...styles.statValue, color: cc(coderSummary.weighted_accuracy, coderSummary.pass_threshold) }}>
                          {coderSummary.weighted_accuracy}%
                        </div>
                        <div style={styles.statLabel}>Grading Score</div>
                      </div>
                    )}
                    {coderSummary.cumulative_dpo?.overall_accuracy != null && (
                      <div style={{ ...styles.statCard, background: '#eef2ff', borderLeft: '3px solid #6366f1' }}>
                        <div style={{ ...styles.statValue, color: cc(coderSummary.cumulative_dpo.overall_accuracy, coderSummary.pass_threshold) }}>
                          {coderSummary.cumulative_dpo.overall_accuracy}%
                        </div>
                        <div style={styles.statLabel}>Overall accuracy (DPO)</div>
                      </div>
                    )}
                  </div>

                  {/* Accuracy breakdown */}
                  {coderSummary.cumulative_dpo && (coderSummary.cumulative_dpo.dx_accuracy != null || coderSummary.cumulative_dpo.proc_accuracy != null || coderSummary.cumulative_dpo.drg_accuracy != null) && (
                    <div style={{ background: '#f8faff', border: '1px solid #e0e7ff', borderRadius: 10, padding: '14px 18px' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' as const, letterSpacing: 0.6, marginBottom: 10 }}>
                        Element Accuracy
                        <span style={{ fontWeight: 600, textTransform: 'none' as const, letterSpacing: 0, color: '#9ca3af', marginLeft: 8 }}>
                          — batches and direct assignments in the selected date range, not all time
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' as const }}>
                        {coderSummary.cumulative_dpo.dx_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: cc(coderSummary.cumulative_dpo.dx_accuracy, coderSummary.pass_threshold) }}>{coderSummary.cumulative_dpo.dx_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>Diagnosis accuracy</div>
                          </div>
                        )}
                        {coderSummary.cumulative_dpo.proc_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: cc(coderSummary.cumulative_dpo.proc_accuracy, coderSummary.pass_threshold) }}>{coderSummary.cumulative_dpo.proc_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>{coderSummary.proc_label || 'Procedure accuracy'}</div>
                          </div>
                        )}
                        {coderSummary.cumulative_dpo.drg_accuracy != null && (
                          <div style={{ textAlign: 'center' as const }}>
                            <div style={{ fontSize: 20, fontWeight: 800, color: cc(coderSummary.cumulative_dpo.drg_accuracy, coderSummary.pass_threshold) }}>{coderSummary.cumulative_dpo.drg_accuracy}%</div>
                            <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>DRG accuracy</div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Top / Bottom categories */}
                  {coderSummary.by_category?.length > 0 && (() => {
                    const cats: any[] = coderSummary.by_category
                    const pt = coderSummary.pass_threshold ?? 90
                    const weak = cats.filter((c: any) => c.avg_score < pt)
                    const splitAt = Math.min(3, Math.floor(cats.length / 2))
                    const top = cats.slice(0, splitAt)
                    const bottom = weak.length > 0 ? weak.slice(-Math.min(3, weak.length)).reverse() : []
                    return (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '12px 14px' }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#166534', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 8 }}>Top Categories</div>
                          {top.map((c: any) => (
                            <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #dcfce7', fontSize: 12 }}>
                              <span style={{ fontWeight: 600, color: '#111' }}>
                                {c.category}
                                {c.charts < 3 && <span title="Only one or two charts — not enough to call this a strength"
                                  style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '1px 6px', borderRadius: 8 }}>thin</span>}
                              </span>
                              <span style={{ display: 'flex', gap: 8, color: '#6b7280' }}>
                                <span>{c.charts} charts</span>
                                <span style={{ fontWeight: 700, color: '#16a34a' }}>{c.avg_score}%</span>
                              </span>
                            </div>
                          ))}
                        </div>
                        <div style={{ background: bottom.length > 0 ? '#fff7ed' : '#f0fdf4', border: `1px solid ${bottom.length > 0 ? '#fed7aa' : '#bbf7d0'}`, borderRadius: 10, padding: '12px 14px' }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: bottom.length > 0 ? '#92400e' : '#166534', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 8 }}>Needs Work</div>
                          {bottom.length === 0 ? (
                            <div style={{ fontSize: 12, color: '#166534', fontWeight: 600 }}>None — every category is at or above {coderSummary.pass_threshold ?? 90}%</div>
                          ) : bottom.map((c: any) => (
                            <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #fde68a', fontSize: 12 }}>
                              <span style={{ fontWeight: 600, color: '#111' }}>
                                {c.category}
                                {c.charts < 3 && <span title="Only one or two charts — too thin to act on"
                                  style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '1px 6px', borderRadius: 8 }}>thin</span>}
                              </span>
                              <span style={{ display: 'flex', gap: 8, color: '#6b7280' }}>
                                <span>{c.charts} charts</span>
                                <span style={{ fontWeight: 700, color: cc(c.avg_score, pt) }}>{c.avg_score}%</span>
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })()}
                </div>
              )}

              {/* Score trend chart */}
              {coderTrend.length > 1 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>
                    Grading Score Trend — {coderName}
                    {coderTrend.length > 25 && <span style={{ fontWeight: 600, fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                      most recent 25 of {coderTrend.length} — full history in the table below
                    </span>}
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={recent(coderTrend, 25).map(r => ({ ...r, label: axisLabel(r.batch_name, 14) }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={tickInterval(Math.min(coderTrend.length, 25))} angle={-20} textAnchor="end" height={52} />
                      <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v: any) => [`${v}%`, 'Avg Grading Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                      <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 6, fill: '#4f46e5' }} activeDot={{ r: 8 }} name="Avg Grading Score" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Batch history table */}
              {(coderSummary?.batches?.length > 0 || coderTrend.length > 0) && (() => {
                const rows: any[] = coderSummary?.batches?.length ? coderSummary.batches : coderTrend
                return (
                  <div style={styles.table}>
                    <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 100px 100px 80px 80px 80px' }}>
                      <span>Batch</span><span>Specialty</span><span>Date</span><span>Charts</span><span>Avg Grading Score</span><span>Passed</span>
                    </div>
                    {rows.map((r: any, i: number) => {
                      const prev = rows[i - 1]
                      const delta = prev?.avg_score != null && r.avg_score != null ? round1(r.avg_score - prev.avg_score) : null
                      return (
                        <div key={r.batch_id} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 100px 100px 80px 80px 80px' }}>
                          <span style={{ fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' as const }}>
                            {r.batch_name}
                            {/* A coder's history mixes both by design; without
                                this a run of one-off charts reads as batch work. */}
                            {r.is_direct_assignment && <span style={{ fontSize: 9, fontWeight: 700, background: '#ede9fe', color: '#7c3aed', padding: '1px 6px', borderRadius: 8 }}>Direct</span>}
                          </span>
                          <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty || '—'}</span>
                          <span style={{ fontSize: 12, color: '#6b7280' }}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</span>
                          <span>{r.chart_count ?? r.charts ?? '—'}</span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                            <span style={{ fontWeight: 700, color: cc(r.avg_score, coderSummary?.pass_threshold) }}>{r.avg_score != null ? `${r.avg_score}%` : '—'}</span>
                            {delta != null && <span style={{ fontSize: 11, fontWeight: 700, color: delta > 0 ? '#16a34a' : delta < 0 ? '#dc2626' : '#9ca3af' }}>{delta > 0 ? '↑' : delta < 0 ? '↓' : '→'}{Math.abs(delta)}%</span>}
                          </span>
                          <span style={{ fontWeight: 700, color: '#16a34a' }}>{r.charts_passed != null ? `${r.charts_passed}/${r.chart_count ?? r.charts ?? '?'}` : '—'}</span>
                        </div>
                      )
                    })}
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}

      {/* C: Topic Mastery */}
      {tab === 'category' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* The specialty picker lives ABOVE the empty-state gate.
              Inside it, choosing a specialty with no data removed the picker
              along with everything else — the control that caused the empty
              state vanished with the results, so there was no way back to a
              specialty that had data short of reloading the app. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280' }}>Specialty</span>
            <select value={topicSpecialty} onChange={e => { setTopicSpecialty(e.target.value); setTopicShowAll(false) }}
              style={{ ...styles.select, fontSize: 12, padding: '5px 10px', minWidth: 180 }}>
              <option value="">All specialties</option>
              {SPECIALTIES.map(sp => <option key={sp} value={sp}>{sp}</option>)}
            </select>
            {topicSpecialty && (
              <button onClick={() => { setTopicSpecialty(''); setTopicShowAll(false) }}
                style={{ ...styles.outlineBtn, fontSize: 12, padding: '5px 12px' }}>
                Show all specialties
              </button>
            )}
          </div>

          {!categoryData ? <div style={styles.emptyState}>Loading…</div> : categoryData.team.length === 0 ? (
            <div style={{ ...styles.emptyState, lineHeight: 1.7 }}>
              {topicSpecialty ? (
                <>
                  <div style={{ fontWeight: 700, color: '#b45309' }}>No graded {topicSpecialty} work in range</div>
                  <div style={{ fontSize: 12 }}>
                    Pick another specialty above, or{' '}
                    <button onClick={() => { setTopicSpecialty(''); setTopicShowAll(false) }}
                      style={{ background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontWeight: 700, fontSize: 12, padding: 0 }}>
                      show all specialties
                    </button>.
                  </div>
                </>
              ) : 'No topic data yet — grade some batches first.'}
            </div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                {/* Categories are free text entered at chart upload, so this
                    axis has no natural ceiling — 60 of them produced a chart
                    taller than three screens. Cut to the extremes, which is
                    what a "who stands out" chart is for; the full list is the
                    table directly below, which scrolls. */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' as const }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>
                    Team Avg Grading Score by Topic
                    {categoryChartRows.length < topicRows.length && (
                      <span style={{ fontWeight: 600, fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                        strongest and weakest {categoryChartRows.length} of {topicRows.length} — all {topicRows.length} in the table below
                      </span>
                    )}
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={barHeight(categoryChartRows.length)}>
                  <BarChart data={categoryChartRows} layout="vertical" margin={{ left: 10, right: 40, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={140} />
                    <Tooltip formatter={(v: any) => [`${v}%`]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Bar dataKey="avg_score" name="Avg Grading Score" radius={[0, 4, 4, 0]}>
                      {categoryChartRows.map((entry: any, i: number) => {
                        // Each topic against its OWN pass mark; a fixed default
                        // colours a 90-threshold topic as if it were an 80.
                        const c = cc(entry.avg_score, entry.pass_threshold)
                        return <Cell key={i} fill={c === '#16a34a' ? '#22c55e' : c === '#d97706' ? '#f59e0b' : '#ef4444'} />
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
                <SearchBox width={240}
                  placeholder={`Search topics (${(categoryData.team || []).length} total)…`}
                  value={topicSearch}
                  onChange={v => { setTopicSearch(v); setTopicShowAll(false) }} />
                <span style={{ fontSize: 11, color: '#9ca3af' }}>
                  Showing {visibleTopics.length} of {topicRows.length}
                  {topicSpecialty ? ` in ${topicSpecialty}` : ''} · weakest first
                </span>
              </div>
              {/* Clickable topic rows with drill-through */}
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 80px 80px 90px 110px' }}>
                  <span>Topic</span><span>Attempts</span><span>Pass Mark</span>
                  <span>Avg Grading Score</span><span>Chart Pass Rate</span>
                </div>
                {visibleTopics.length === 0 && (
                  /* Search box stays put — same reason as the specialty picker. */
                  <div style={{ ...styles.emptyState, padding: '16px 0' }}>
                    No topics match "{topicSearch.trim()}"
                  </div>
                )}
                {visibleTopics.map((cat: any, i: number) => {
                  const isExp = expandedCategory === cat.category
                  const catCharts = byChart.filter((c: any) => c.category === cat.category).sort((a: any, b: any) => a.avg_score - b.avg_score)
                  const catCoders = categoryData.coder_category.filter((r: any) => r.category === cat.category).sort((a: any, b: any) => a.avg_score - b.avg_score)
                  return (
                    <div key={cat.category}>
                      <div className={!isExp ? (i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr') : ''} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 80px 80px 90px 110px', cursor: 'pointer', background: isExp ? '#f5f3ff' : undefined, alignItems: 'center' }}
                        onClick={() => setExpandedCategory(isExp ? null : cat.category)}>
                        <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' as const }}>
                          {cat.category} <span style={{ fontSize: 11, color: '#9ca3af' }}>{isExp ? '▲' : '▼'}</span>
                          {/* Topic names are free text and repeat across
                              specialties — "Sepsis" exists in IP-DRG and SDS,
                              graded against different pass marks. */}
                          {(cat.specialties || []).map((sp: string) => (
                            <span key={sp} style={{ fontSize: 9, fontWeight: 700, background: '#f1f5f9', color: '#475569', padding: '1px 6px', borderRadius: 8 }}>{sp}</span>
                          ))}
                        </span>
                        <span>
                          {cat.attempt_count}
                          {cat.attempt_count < LOW_SAMPLE && <span title={`Fewer than ${LOW_SAMPLE} attempts — these percentages move a lot on one result`}
                            style={{ marginLeft: 5, fontSize: 9, fontWeight: 700, background: '#f3f4f6', color: '#6b7280', padding: '1px 5px', borderRadius: 8 }}>thin</span>}
                        </span>
                        <span style={{ color: '#6b7280' }} title={cat.pass_threshold == null ? 'This topic spans specialties with different pass marks' : undefined}>
                          {cat.pass_threshold != null ? `${cat.pass_threshold}%` : 'mixed'}
                        </span>
                        <span style={{ fontWeight: 700, color: cc(cat.avg_score, cat.pass_threshold) }}>{cat.avg_score}%</span>
                        <span style={{ fontWeight: 700, color: rc(cat.pass_rate) }}>{cat.pass_rate}%</span>
                      </div>
                      {isExp && (
                        <div style={{ padding: '12px 16px', background: '#fafafa', borderBottom: '1px solid #ede9fe', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 8 }}>Weak charts in this topic</div>
                            {catCharts.length === 0 ? <div style={{ fontSize: 12, color: '#9ca3af' }}>No chart data yet</div> : <>
                            {catCharts.slice(0, 6).map((c: any) => (
                              <div key={c.chart_number} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                                <span style={{ fontWeight: 700, color: '#4f46e5', cursor: 'pointer' }} onClick={e => { e.stopPropagation(); setExpandedChart(c.chart_number); setTab('chart') }}>{c.chart_number}</span>
                                <span style={{ color: '#6b7280' }}>{c.attempt_count} attempts</span>
                                <span style={{ fontWeight: 700, color: sc(c.avg_score, c.specialty) }}>{c.avg_score}%</span>
                              </div>
                            ))}
                            {catCharts.length > 6 && (
                              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                                + {catCharts.length - 6} more chart{catCharts.length - 6 !== 1 ? 's' : ''} — see By Chart
                              </div>
                            )}
                            </>}
                          </div>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.4, marginBottom: 8 }}>Coders by performance</div>
                            {catCoders.length === 0 ? <div style={{ fontSize: 12, color: '#9ca3af' }}>No coder data yet</div> : (
                              <>
                                {catCoders.slice(0, 10).map((c: any) => (
                                  <div key={c.coder_name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                                    {coderLink(c.coder_name)}
                                    <span style={{ color: '#6b7280' }}>{c.attempt_count} charts</span>
                                    <span style={{ fontWeight: 700, color: sc(c.avg_score, c.specialty) }}>{c.avg_score}%</span>
                                  </div>
                                ))}
                                {catCoders.length > 10 && (
                                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                                    + {catCoders.length - 10} more coders — use Coder Matrix for full view
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {topicRows.length > visibleTopics.length && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>
                    {topicRows.length - visibleTopics.length} more topic{topicRows.length - visibleTopics.length !== 1 ? 's' : ''} not shown
                  </span>
                  <button onClick={() => setTopicShowAll(true)}
                    style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                    Show all {topicRows.length}
                  </button>
                </div>
              )}

              {categoryData.coder_scope_note && (
                <div style={{ fontSize: 11, color: '#6b7280', background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 14px' }}>
                  ℹ️ {categoryData.coder_scope_note}
                </div>
              )}
              {categoryData.coder_category.length > 0 && (() => {
                // Keyed on emp_id, not the typed name — "Asha R" and "asha  r"
                // were two rows for one person, each holding half their work.
                const idOf = (r: any) => r.emp_id || r.coder_name
                const nameOf: Record<string, string> = {}
                categoryData.coder_category.forEach((r: any) => { nameOf[idOf(r)] = r.coder_name })
                const allCoders = Array.from(new Set(categoryData.coder_category.map(idOf))) as string[]
                // Columns were every topic that exists. Rows were paged and
                // searchable; columns grew without limit, so 60 topics meant a
                // 60-column table scrolled sideways forever. Weakest first,
                // since that is what a planning view is read for.
                const HEATMAP_COLS = 12
                const allCats = topicRows.map((r: any) => r.category)
                const cats = heatmapShowAllCols ? allCats : allCats.slice(0, HEATMAP_COLS)
                const cellMap: Record<string, Record<string, any>> = {}
                categoryData.coder_category.forEach((r: any) => {
                  if (!cellMap[idOf(r)]) cellMap[idOf(r)] = {}
                  cellMap[idOf(r)][r.category] = r
                })
                const filteredCoders = heatmapCoderSearch.trim()
                  ? allCoders.filter(id => (nameOf[id] || id).toLowerCase().includes(heatmapCoderSearch.toLowerCase()))
                  : allCoders
                const sortedCoders = [...filteredCoders].sort((a, b) => {
                  const dir = heatmapSort.dir === 'asc' ? 1 : -1
                  if (heatmapSort.col === 'coder') return (nameOf[a] || a).localeCompare(nameOf[b] || b) * dir
                  const sa = cellMap[a]?.[heatmapSort.col]?.avg_score ?? -1
                  const sb = cellMap[b]?.[heatmapSort.col]?.avg_score ?? -1
                  return (sa - sb) * dir
                })
                const visibleCoders = heatmapShowAll ? sortedCoders : sortedCoders.slice(0, CODER_PAGE)
                const hiddenCount = sortedCoders.length - visibleCoders.length
                return (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap' as const, gap: 8 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>
                        Coder × Topic Heatmap
                        {cats.length < allCats.length && (
                          <span style={{ fontWeight: 600, fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                            weakest {cats.length} of {allCats.length} topics
                            <button onClick={() => setHeatmapShowAllCols(true)}
                              style={{ marginLeft: 6, fontSize: 11, color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700, padding: 0 }}>
                              show all
                            </button>
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {allCoders.length > CODER_PAGE && (
                          <SearchBox width={200}
                            placeholder={`Search coders (${allCoders.length} total)…`}
                            value={heatmapCoderSearch}
                            onChange={v => { setHeatmapCoderSearch(v); setHeatmapShowAll(false) }} />
                        )}
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>Showing {visibleCoders.length} of {filteredCoders.length}</span>
                      </div>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                        <thead>
                          <tr>
                            <th onClick={() => toggleSort('coder', heatmapSort, setHeatmapSort)} style={{ textAlign: 'left', padding: '6px 10px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' as const, cursor: 'pointer', userSelect: 'none' as const }}>
                              Coder{sortIcon('coder', heatmapSort)}
                            </th>
                            {cats.map((c: string) => (
                              <th key={c} onClick={() => toggleSort(c, heatmapSort, setHeatmapSort)} style={{ padding: '6px 8px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' as const, textAlign: 'center', fontWeight: 600, cursor: 'pointer', userSelect: 'none' as const }}>
                                {c}{sortIcon(c, heatmapSort)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {visibleCoders.map((coder: string, i: number) => (
                            <tr key={coder} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                              <td style={{ padding: '6px 10px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const }}>{coderLink(nameOf[coder] || coder)}</td>
                              {cats.map((cat: string) => {
                                const cell = cellMap[coder]?.[cat]
                                const score = cell?.avg_score
                                // cc() against the topic's own pass mark. sc()
                                // with no specialty fell through to IP's 80, so
                                // an SDS cell at 85 showed green against a bar
                                // of 90.
                                const _sc = cc(score, cell?.pass_threshold)
                                const bg = score == null ? 'transparent' : _sc === '#16a34a' ? '#dcfce7' : _sc === '#d97706' ? '#fef3c7' : '#fee2e2'
                                const color = score == null ? '#d1d5db' : _sc === '#16a34a' ? '#166534' : _sc === '#d97706' ? '#92400e' : '#991b1b'
                                return (
                                  <td key={cat} style={{ padding: '6px 8px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                    {score != null ? `${score}%` : '—'}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {hiddenCount > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 }}>
                        <span style={{ fontSize: 12, color: '#6b7280' }}>{hiddenCount} more coder{hiddenCount !== 1 ? 's' : ''} not shown</span>
                        <button onClick={() => setHeatmapShowAll(true)} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                          Show all {filteredCoders.length}
                        </button>
                      </div>
                    )}
                    {heatmapShowAll && allCoders.length > CODER_PAGE && (
                      <button onClick={() => setHeatmapShowAll(false)} style={{ marginTop: 8, fontSize: 12, color: '#6b7280', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer' }}>
                        Collapse to {CODER_PAGE}
                      </button>
                    )}
                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 8 }}>Green ≥{ipThreshold}% · Yellow {Math.round(ipThreshold * 0.75)}–{ipThreshold - 1}% · Red &lt;{Math.round(ipThreshold * 0.75)}% · — no data</div>
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}

      {/* D: Chart Signals */}
      {tab === 'teaching' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {teachingData.length === 0 ? <div style={styles.emptyState}>No chart grading data yet.</div> : (() => {
            const labels = Object.keys(TEACHING_LABEL_META)
            const filterOptions = ['All', ...labels]
            const q = chartValueSearch.trim().toLowerCase()
            const filtered = (teachingFilter === 'All' ? teachingData : teachingData.filter((c: any) => c.teaching_label === teachingFilter))
              .filter((c: any) => !q
                || c.chart_number.toLowerCase().includes(q)
                || (c.category || '').toLowerCase().includes(q))
              .slice()
              .sort((a: any, b: any) => {
                if (chartValueSort === 'score_asc') return a.avg_score - b.avg_score
                if (chartValueSort === 'score_desc') return b.avg_score - a.avg_score
                return b.attempt_count - a.attempt_count  // attempts_desc
              })
            const grouped: Record<string, any[]> = {}
            teachingData.forEach((c: any) => {
              if (!grouped[c.teaching_label]) grouped[c.teaching_label] = []
              grouped[c.teaching_label].push(c)
            })
            const summaryData = labels.map(l => ({ label: l, count: grouped[l]?.length || 0 })).filter(d => d.count > 0)
            return (
              <>
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Signal Distribution</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={summaryData} margin={{ left: 10, right: 20, top: 4, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                      <Bar dataKey="count" name="Charts" radius={[4, 4, 0, 0]}>
                        {summaryData.map((entry: any, i: number) => <Cell key={i} fill={TEACHING_LABEL_META[entry.label]?.color || '#6b7280'} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                {/* One toolbar, each control labelled with the job it does.
                    Three unlabelled rows of pills all looked like tabs, so it
                    was never obvious which was navigation and which was a
                    filter — they are visually identical and behave differently. */}
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5, width: 52 }}>Signal</span>
                    {filterOptions.map(opt => (
                      <button key={opt} onClick={() => { setTeachingFilter(opt); setChartValuePage(1) }}
                        title={TEACHING_LABEL_META[opt]?.desc}
                        style={{ padding: '4px 11px', borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                          background: teachingFilter === opt ? '#4f46e5' : '#f3f4f6',
                          color: teachingFilter === opt ? '#fff' : '#374151',
                          border: teachingFilter === opt ? '1px solid #4f46e5' : '1px solid #e5e7eb' }}>
                        {opt}{opt !== 'All' && grouped[opt] ? ` (${grouped[opt].length})` : ''}
                      </button>
                    ))}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5, width: 52 }}>Sort</span>
                    {[
                      { key: 'score_asc', label: 'Most problematic' },
                      { key: 'attempts_desc', label: 'Most attempted' },
                      { key: 'score_desc', label: 'Highest scoring' },
                    ].map(opt => (
                      <button key={opt.key} onClick={() => { setChartValueSort(opt.key as any); setChartValuePage(1) }}
                        style={{ fontSize: 12, padding: '4px 11px', borderRadius: 20, cursor: 'pointer', fontWeight: 600, border: '1px solid',
                          background: chartValueSort === opt.key ? '#4f46e5' : '#fff',
                          color: chartValueSort === opt.key ? '#fff' : '#6b7280',
                          borderColor: chartValueSort === opt.key ? '#4f46e5' : '#e5e7eb' }}>
                        {opt.label}
                      </button>
                    ))}
                    {/* At 2000 charts, scanning cards is not a way to find one. */}
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <SearchBox placeholder="Find a chart or topic…"
                        value={chartValueSearch}
                        onChange={v => { setChartValueSearch(v); setChartValuePage(1) }} />
                      {/* One undo for the strip. "All" resets the signal chips
                          and clearing the box resets the search, but sort had
                          no way back to its default at all — every option was
                          a selection, none of them was "none". */}
                      {(teachingFilter !== 'All' || chartValueSort !== 'score_asc' || chartValueSearch.trim()) && (
                        <button
                          title="Clear signal, sort and search on this tab"
                          onClick={() => {
                            setTeachingFilter('All')
                            setChartValueSort('score_asc')
                            setChartValueSearch('')
                            setChartValuePage(1)
                          }}
                          style={{ fontSize: 12, fontWeight: 700, color: '#dc2626', background: 'none',
                                   border: '1px solid #fecaca', borderRadius: 6, padding: '5px 11px', cursor: 'pointer' }}>
                          Reset
                        </button>
                      )}
                    </span>
                  </div>
                </div>
                {filtered.length === 0 ? (
                  <div style={styles.emptyState}>No charts in this category.</div>
                ) : (
                  <>
                    <div style={{ fontSize: 12, color: '#9ca3af' }}>
                      Showing {Math.min(chartValuePage * CHART_VALUE_PAGE, filtered.length)} of {filtered.length} charts
                      {chartValueSearch.trim() ? ` matching "${chartValueSearch.trim()}"` : ''}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
                      {filtered.slice(0, chartValuePage * CHART_VALUE_PAGE).map((c: any, i: number) => {
                        const meta = TEACHING_LABEL_META[c.teaching_label] || { color: '#374151', bg: '#f9fafb', desc: '' }
                        return (
                          <div key={i} style={{ background: meta.bg, border: `1px solid ${meta.color}30`, borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                              <span style={{ fontWeight: 700, fontSize: 13, color: '#111' }}>{c.chart_number}</span>
                              <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: '#fff', border: `1px solid ${meta.color}40`, borderRadius: 10, padding: '2px 8px' }}>{c.teaching_label}</span>
                            </div>
                            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{c.specialty} · {c.category}</div>
                            <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
                              <span><b style={{ color: '#111' }}>{c.attempt_count}</b> attempts</span>
                              <span title={c.pass_threshold ? `Pass mark ${c.pass_threshold}%` : undefined}>
                                <b style={{ color: cc(c.avg_score, c.pass_threshold) }}>{c.avg_score}%</b> avg
                              </span>
                              <span><b style={{ color: rc(c.pass_rate) }}>{c.pass_rate}%</b> pass</span>
                            </div>
                            {c.error_variety > 0 && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{c.error_variety} distinct error type{c.error_variety > 1 ? 's' : ''}</div>}
                          </div>
                        )
                      })}
                    </div>
                    {filtered.length > chartValuePage * CHART_VALUE_PAGE && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, paddingTop: 4 }}>
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>
                          {filtered.length - chartValuePage * CHART_VALUE_PAGE} more
                        </span>
                        <button onClick={() => setChartValuePage(n => n + 1)}
                          style={{ ...styles.outlineBtn, fontSize: 12, padding: '6px 14px' }}>
                          Load more
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )
          })()}
        </div>
      )}

      {/* E: Coder Matrix */}
      {tab === 'matrix' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!matrixData ? <div style={styles.emptyState}>Loading…</div> : matrixData.coders.length === 0 ? (
            <div style={styles.emptyState}>No closed batch results yet — close a batch to see the coder matrix.</div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' as const, gap: 8 }}>
                <div style={{ fontSize: 13, color: '#6b7280' }}>
                  Cross-batch performance grid — each cell is a coder's avg score for that batch, coloured against
                  that batch's own pass mark.
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                    {matrixData.scope_note || 'Closed formal batches only.'}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
                  {/* The column axis. Choosing it is the point: a batch is an
                      event and a specialty is a bucket, so they cannot share
                      one row of headers. */}
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5 }}>Columns</span>
                  <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                    {([['specialty', 'Specialty'], ['batch', 'Batch']] as const).map(([k, label]) => (
                      <button key={k} onClick={() => { setMatrixGroupBy(k); setMatrixShowAll(false) }}
                        title={k === 'batch'
                          ? 'Closed formal batches — each column a finished set. Readable for the last dozen or so.'
                          : 'One column per specialty — bounded, and the only axis direct assignments fit on'}
                        style={{ padding: '5px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                                 borderRight: k === 'batch' ? 'none' : '1px solid #e5e7eb',
                                 background: matrixGroupBy === k ? '#0f766e' : '#fff',
                                 color: matrixGroupBy === k ? '#fff' : '#6b7280' }}>
                        {label}
                      </button>
                    ))}
                  </div>
                  {/* Only batch columns need a window; specialties are bounded. */}
                  {matrixGroupBy === 'batch' && (matrixData.batches?.length ?? 0) > 5 && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontSize: 11, color: '#9ca3af' }}>Latest</span>
                      {([5, 10, 25, 'all'] as const).map(w => (
                        <button key={String(w)} onClick={() => setMatrixColWindow(w)}
                          style={{ fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6, cursor: 'pointer',
                                   border: '1px solid ' + (matrixColWindow === w ? '#0f766e' : '#e5e7eb'),
                                   background: matrixColWindow === w ? '#0f766e' : '#fff',
                                   color: matrixColWindow === w ? '#fff' : '#6b7280' }}>
                          {w === 'all' ? 'All' : w}
                        </button>
                      ))}
                    </span>
                  )}
                  {/* Finding who needs attention in a thousand rows is not a
                      scrolling job. */}
                  <button onClick={() => { setMatrixBelowOnly(v => !v); setMatrixShowAll(false) }}
                    style={{ fontSize: 12, fontWeight: 700, padding: '5px 12px', borderRadius: 20, cursor: 'pointer',
                             border: '1px solid ' + (matrixBelowOnly ? '#dc2626' : '#e5e7eb'),
                             background: matrixBelowOnly ? '#dc2626' : '#fff',
                             color: matrixBelowOnly ? '#fff' : '#6b7280' }}>
                    Below target only
                  </button>
                </div>
                {matrixData.coders.length > CODER_PAGE && (
                  <SearchBox placeholder={`Search coders (${matrixData.coders.length} total)…`}
                    value={matrixCoderSearch}
                    onChange={v => { setMatrixCoderSearch(v); setMatrixShowAll(false) }} />
                )}
              </div>
              {(() => {
                /**
                 * Identity and display name, tolerant of either payload shape.
                 *
                 * This tab briefly showed emp IDs with no scores: the UI had
                 * switched to keying rows on coder_id while a browser still
                 * held the previous bundle, so it matched cells by name
                 * against an id and found none. Nothing was wrong with either
                 * side on its own — they simply had to ship together.
                 *
                 * Cells carry coder_name, so the name is derivable from the
                 * data itself and the separate map is only a shortcut. Matching
                 * on either key removes the lockstep requirement entirely.
                 */
                const cellId = (c: any) => c.coder_id ?? c.coder_name
                const nameFromCells: Record<string, string> = {}
                matrixData.cells.forEach((c: any) => { nameFromCells[cellId(c)] = c.coder_name })
                const nameOfCoder = (cid: string) =>
                  matrixData.coder_names?.[cid] || nameFromCells[cid] || cid
                // Match name OR emp id — the row shows both, so either is a
                // reasonable thing to type.
                const mq = matrixCoderSearch.trim().toLowerCase()
                const searched = mq
                  ? matrixData.coders.filter((cid: string) =>
                      nameOfCoder(cid).toLowerCase().includes(mq)
                      || String(matrixData.coder_emp_ids?.[cid] || '').toLowerCase().includes(mq))
                  : matrixData.coders
                // "Below target" is per cell against that batch's own mark —
                // one blanket number would be wrong for half the columns.
                const isBelow = (cid: string) => matrixData.cells.some((c: any) => {
                  if (cellId(c) !== cid || c.avg_score == null) return false
                  const pt = matrixData.batches.find((b: any) => b.id === c.batch_id)?.pass_threshold
                  return pt != null && c.avg_score < pt
                })
                const filteredCoders = matrixBelowOnly ? searched.filter(isBelow) : searched
                // Newest columns first when capped: a wide grid is read for
                // what happened lately, not for what happened first.
                const allBatchCols = matrixData.batches
                const batchCols = (matrixGroupBy === 'specialty' || matrixColWindow === 'all')
                  ? allBatchCols
                  : allBatchCols.slice(-(matrixColWindow as number))
                const weightedOverall = new Map<string, number>()
                for (const coder of filteredCoders) {
                  const cells = matrixData.cells.filter((c: any) => cellId(c) === coder && c.avg_score != null)
                  const totalCharts = cells.reduce((s: number, c: any) => s + c.chart_count, 0)
                  const scoreSum = cells.reduce((s: number, c: any) => s + c.score_sum, 0)
                  weightedOverall.set(coder, totalCharts > 0 ? scoreSum / totalCharts : -1)
                }
                const sortedMatrixCoders = [...filteredCoders].sort((a: string, b: string) => {
                  const dir = matrixSort.dir === 'asc' ? 1 : -1
                  if (matrixSort.col === 'coder') return nameOfCoder(a).localeCompare(nameOfCoder(b)) * dir
                  if (matrixSort.col === 'overall') {
                    return ((weightedOverall.get(a) ?? -1) - (weightedOverall.get(b) ?? -1)) * dir
                  }
                  const batchId = Number(matrixSort.col)
                  const sa = matrixData.cells.find((c: any) => cellId(c) === a && c.batch_id === batchId)?.avg_score ?? -1
                  const sb = matrixData.cells.find((c: any) => cellId(c) === b && c.batch_id === batchId)?.avg_score ?? -1
                  return (sa - sb) * dir
                })
                const visibleCoders = matrixShowAll ? sortedMatrixCoders : sortedMatrixCoders.slice(0, CODER_PAGE)
                const hiddenCount = sortedMatrixCoders.length - visibleCoders.length
                return (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 12, color: '#9ca3af' }}>
                        Showing {visibleCoders.length} of {filteredCoders.length} coders
                        {matrixBelowOnly ? ' below target' : ''}
                        {batchCols.length < allBatchCols.length && (
                          <>{' · latest '}{batchCols.length} of {allBatchCols.length} batches</>
                        )}
                      </span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                        <thead>
                          <tr>
                            <th onClick={() => toggleSort('coder', matrixSort, setMatrixSort)} style={{ textAlign: 'left', padding: '7px 12px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' as const, fontWeight: 700, color: '#374151', cursor: 'pointer', userSelect: 'none' as const }}>
                              Coder{sortIcon('coder', matrixSort)}
                            </th>
                            {batchCols.map((b: any) => (
                              /* The aggregated direct column is styled apart
                                 so it is not read as just another batch. */
                              <th key={b.id} onClick={() => toggleSort(String(b.id), matrixSort, setMatrixSort)}
                                title={`${b.specialty}${b.pass_threshold ? ` · pass mark ${b.pass_threshold}%` : ''}`}
                                style={{ padding: '7px 10px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' as const, textAlign: 'center', fontWeight: 600, color: '#374151', minWidth: 80, cursor: 'pointer', userSelect: 'none' as const }}>
                                <div>{b.name.length > 14 ? b.name.slice(0, 14) + '…' : b.name}</div>
                                {/* Specialty on every batch column, so two
                                    columns are never compared without their
                                    different pass marks being visible. */}
                                <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af' }}>
                                  {matrixGroupBy === 'batch'
                                    ? `${b.specialty}${b.pass_threshold ? ` · ${b.pass_threshold}%` : ''}`
                                    : (b.pass_threshold ? `pass mark ${b.pass_threshold}%` : '')}
                                  {sortIcon(String(b.id), matrixSort)}
                                </div>
                              </th>
                            ))}
                            <th onClick={() => toggleSort('overall', matrixSort, setMatrixSort)} style={{ padding: '7px 10px', background: '#f1f5f9', borderBottom: '2px solid #e5e7eb', textAlign: 'center', fontWeight: 700, color: '#374151', minWidth: 70, cursor: 'pointer', userSelect: 'none' as const }}>
                              Overall{sortIcon('overall', matrixSort)}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleCoders.map((coder: string, i: number) => {
                            const coderCells = matrixData.cells.filter((c: any) => cellId(c) === coder)
                            const scoredCells = coderCells.filter((c: any) => c.avg_score != null)
                            const totalCharts = scoredCells.reduce((s: number, c: any) => s + c.chart_count, 0)
                            const scoreSum = scoredCells.reduce((s: number, c: any) => s + c.score_sum, 0)
                            const overall = totalCharts > 0 ? Math.round(scoreSum / totalCharts) : null
                            const cellMap: Record<number, any> = {}
                            coderCells.forEach((c: any) => { cellMap[c.batch_id] = c })
                            return (
                              <tr key={coder} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                                {/* Sticky, so the name stays visible once the
                                    batch columns push the grid sideways. */}
                                <td style={{ padding: '7px 12px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const,
                                             position: 'sticky', left: 0, zIndex: 1, background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                                  {coderLink(nameOfCoder(coder))}
                                  {matrixData.coder_emp_ids?.[coder] && matrixData.coder_emp_ids[coder] !== nameOfCoder(coder) && <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af' }}>{matrixData.coder_emp_ids[coder]}</div>}
                                </td>
                                {batchCols.map((b: any) => {
                                  const cell = cellMap[b.id]
                                  const score = cell?.avg_score
                                  // Against THIS batch's pass mark. A flat 80
                                  // showed an SDS batch green at 82 when its
                                  // bar is 90, and did the same for Surgery
                                  // and ED Single Path.
                                  const _c = cc(score, b.pass_threshold)
                                  const bg = score == null ? 'transparent' : _c === '#16a34a' ? '#dcfce7' : _c === '#d97706' ? '#fef3c7' : '#fee2e2'
                                  const color = score == null ? '#d1d5db' : _c === '#16a34a' ? '#166534' : _c === '#d97706' ? '#92400e' : '#991b1b'
                                  return (
                                    <td key={b.id}
                                      title={cell ? `${cell.charts_passed}/${cell.chart_count} charts passed (${cell.pass_rate}%) · pass mark ${b.pass_threshold ?? '—'}%` : undefined}
                                      style={{ padding: '7px 10px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                      {score != null ? (
                                        <div>
                                          <div>{score}%</div>
                                          {cell?.chart_count != null && <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>{cell.chart_count} charts</div>}
                                        </div>
                                      ) : '—'}
                                    </td>
                                  )
                                })}
                                {/* Overall spans whatever specialties this
                                    coder worked in, so it is coloured against
                                    a single mark only when they all agree. */}
                                {(() => {
                                  const marks = new Set(coderCells.map((c: any) =>
                                    matrixData.batches.find((bb: any) => bb.id === c.batch_id)?.pass_threshold).filter(Boolean))
                                  const oc = marks.size === 1 ? cc(overall, [...marks][0] as number) : cc(overall, undefined)
                                  const obg = overall == null ? 'transparent' : oc === '#16a34a' ? '#bbf7d0' : oc === '#d97706' ? '#fde68a' : '#fecaca'
                                  const ofg = overall == null ? '#d1d5db' : oc === '#16a34a' ? '#14532d' : oc === '#d97706' ? '#78350f' : '#7f1d1d'
                                  return (
                                <td title={marks.size > 1 ? 'Spans specialties with different pass marks' : undefined}
                                  style={{ padding: '7px 10px', textAlign: 'center', background: obg, color: ofg, fontWeight: 800, borderBottom: '1px solid #f3f4f6', borderLeft: '2px solid #e5e7eb' }}>
                                  {overall != null ? `${overall}%` : '—'}
                                </td>
                                  )
                                })()}
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    {hiddenCount > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 12, color: '#6b7280' }}>{hiddenCount} more coder{hiddenCount !== 1 ? 's' : ''} not shown</span>
                        <button onClick={() => setMatrixShowAll(true)} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                          Show all {filteredCoders.length}
                        </button>
                      </div>
                    )}
                    {matrixShowAll && matrixData.coders.length > CODER_PAGE && (
                      <button onClick={() => setMatrixShowAll(false)} style={{ fontSize: 12, color: '#6b7280', background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '4px 12px', cursor: 'pointer' }}>
                        Collapse to {CODER_PAGE}
                      </button>
                    )}
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>Green ≥80% · Yellow 60–79% · Red &lt;60%</div>
                  </>
                )
              })()}
            </>
          )}
        </div>
      )}
      {/* E/M MDM tab */}
      {tab === 'em_mdm' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Batch selector — filter byBatch for E/M specialty */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' as const }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Select E/M Batch:</span>
            <select
              style={{ ...styles.input, width: 320, fontSize: 13 }}
              value={emBatchId ?? ''}
              onChange={e => { setEmBatchId(e.target.value ? Number(e.target.value) : null); setEmBreakdown(null) }}
            >
              <option value="">— choose a batch —</option>
              {byBatch.filter((b: any) => (b.specialty || '').toUpperCase().includes('E/M') || (b.specialty || '').toUpperCase().includes('ED PROFEE')).map((b: any) => (
                <option key={b.batch_id || b.id} value={b.batch_id || b.id}>{b.batch_name || b.name} ({b.specialty})</option>
              ))}
            </select>
            {emBatchId && (
              <button onClick={() => { setEmLoading(true); getBatchEMBreakdown(emBatchId).then(setEmBreakdown).catch(() => {}).finally(() => setEmLoading(false)) }}
                style={{ ...styles.outlineBtn, fontSize: 12 }}>Refresh</button>
            )}
          </div>

          {!emBatchId && (
            <div style={styles.emptyState}>Select an E/M or ED Profee batch above to see MDM component analytics.</div>
          )}

          {emBatchId && emLoading && <div style={styles.center}><Loader size={20} /></div>}

          {emBatchId && !emLoading && emBreakdown && !emBreakdown.has_data && (
            <div style={styles.emptyState}>No submitted E/M results found for this batch yet.</div>
          )}

          {emBatchId && !emLoading && emBreakdown?.has_data && (() => {
            const t = emBreakdown.team
            const componentData = [
              { name: 'COPA', pct: t.copa_pct, fill: '#7c3aed' },
              { name: 'Data Review', pct: t.dr_pct, fill: '#0891b2' },
              { name: 'Risk', pct: t.risk_pct, fill: '#dc2626' },
              { name: 'E/M Level', pct: t.em_level_pct, fill: '#059669' },
            ]
            return (
              <>
                {/* Team KPI tiles */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                  {[
                    { label: 'Avg Total Score', value: `${t.avg_total}%`, color: t.avg_total >= 80 ? '#059669' : '#dc2626' },
                    { label: 'Coding Accuracy', value: `${t.avg_coding_accuracy.toFixed(1)} pts`, color: '#7c3aed' },
                    { label: 'Reasoning Accuracy', value: `${t.avg_reasoning_accuracy.toFixed(1)} pts`, color: '#0891b2' },
                    { label: 'Right Code, Wrong Reasoning', value: `${t.right_code_wrong_reasoning_count}`, color: '#f59e0b', sub: 'charts' },
                  ].map(tile => (
                    <div key={tile.label} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 800, color: tile.color }}>{tile.value}</div>
                      {tile.sub && <div style={{ fontSize: 11, color: '#9ca3af' }}>{tile.sub}</div>}
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{tile.label}</div>
                    </div>
                  ))}
                </div>

                {/* MDM Component accuracy bar chart */}
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 20px' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#111', marginBottom: 16 }}>MDM Component Level Accuracy — % of charts where derived level matched answer key</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={componentData} margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} width={40} />
                      <Tooltip formatter={(v: any) => [`${v}%`, 'Match Rate']} />
                      <Bar dataKey="pct" radius={[4, 4, 0, 0]}>
                        {componentData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Per-coder table */}
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
                  <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', fontSize: 14, fontWeight: 700, color: '#111' }}>Per-Coder MDM Breakdown</div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
                      <thead>
                        <tr style={{ background: '#f9fafb' }}>
                          {['Coder', 'Charts', 'Total %', 'Coding Acc.', 'Reasoning Acc.', 'COPA Match', 'DR Match', 'Risk Match', 'E/M Level', 'RCWR'].map(h => (
                            <th key={h} style={{ padding: '8px 10px', textAlign: h === 'Coder' ? 'left' : 'center', fontWeight: 700, color: '#374151', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' as const, fontSize: 11 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {emBreakdown.coders.map((c: any, i: number) => (
                          <tr key={c.coder_name} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                            <td style={{ padding: '7px 10px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' as const }}>{c.coder_name}</td>
                            <td style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', color: '#6b7280' }}>{c.chart_count}</td>
                            <td style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', fontWeight: 700, color: c.avg_total >= 80 ? '#059669' : '#dc2626' }}>{c.avg_total}%</td>
                            <td style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', color: '#7c3aed', fontWeight: 600 }}>{c.avg_coding_accuracy.toFixed(1)}</td>
                            <td style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', color: '#0891b2', fontWeight: 600 }}>{c.avg_reasoning_accuracy.toFixed(1)}</td>
                            {[c.copa_pct, c.dr_pct, c.risk_pct, c.em_level_pct].map((pct, j) => (
                              <td key={j} style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', fontWeight: 600, color: pct >= 80 ? '#059669' : pct >= 60 ? '#d97706' : '#dc2626' }}>{pct}%</td>
                            ))}
                            <td style={{ padding: '7px 10px', textAlign: 'center', borderBottom: '1px solid #f3f4f6', fontWeight: 700, color: c.right_code_wrong_reasoning_count > 0 ? '#f59e0b' : '#9ca3af' }}>
                              {c.right_code_wrong_reasoning_count > 0 ? `⚠ ${c.right_code_wrong_reasoning_count}` : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ padding: '8px 16px', fontSize: 11, color: '#9ca3af', borderTop: '1px solid #f3f4f6' }}>
                    RCWR = Right Code, Wrong Reasoning (E/M level correct but reasoning accuracy &lt;50%) · Match % = derived MDM level matched answer key
                  </div>
                </div>
              </>
            )
          })()}
        </div>
      )}

    </div>
  )
}
