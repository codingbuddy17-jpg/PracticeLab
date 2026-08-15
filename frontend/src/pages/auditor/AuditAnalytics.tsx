import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Download, FileText, Search, X } from 'lucide-react'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  downloadAuditAnalytics, downloadAuditAuditorReportPdf, downloadAuditBatchReportPdf,
  getAuditByAuditor, getAuditByBatch, getAuditBySpecialty, getAuditChartSignals,
  getAuditDetection, getAuditOverview,
} from '../../api/auditorApi'
import s from './styles'
import { AUDITABLE } from './constants'

const TABS = ['Overview', 'Auditors', 'Batches', 'Specialties', 'Error Patterns', 'Chart Signals'] as const
type Tab = typeof TABS[number]
type Filters = { from_date?: string; to_date?: string; specialty?: string }

const ROW_CAP = 40
const AUDITOR_MATCH_CAP = 20

export function AuditAnalytics() {
  const [tab, setTab] = useState<Tab>('Overview')
  const [overview, setOverview] = useState<any>(null)
  const [specialties, setSpecialties] = useState<any[]>([])
  const [batches, setBatches] = useState<any[]>([])
  const [auditors, setAuditors] = useState<any[]>([])
  const [chartSignals, setChartSignals] = useState<any>(null)
  const [detection, setDetection] = useState<any>(null)
  const [draft, setDraft] = useState<Filters>({})
  const [filters, setFilters] = useState<Filters>({})
  const [refreshing, setRefreshing] = useState(false)
  const [auditorSearch, setAuditorSearch] = useState('')
  const [selectedAuditor, setSelectedAuditor] = useState<any>(null)
  const [auditorProfile, setAuditorProfile] = useState<any>(null)
  const [batchSearch, setBatchSearch] = useState('')
  const [chartSearch, setChartSearch] = useState('')
  const [auditorMatched, setAuditorMatched] = useState(0)

  // Overview carries the header counts, the verdict and the trend, so it loads
  // for every tab. Everything else is fetched the first time its tab is
  // opened: all six endpoints used to fire on every filter change to render
  // one visible panel, nine round trips once an auditor was selected.
  const [loaded, setLoaded] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      const o = await getAuditOverview(filters)
      setOverview(o)
    } catch { toast.error('Could not load audit analytics') }
    setRefreshing(false)
  }, [filters])

  useEffect(() => { load() }, [load])

  // A filter change invalidates every cached tab, not just the visible one.
  useEffect(() => { setLoaded({}) }, [filters])

  useEffect(() => {
    let cancelled = false
    async function fetchFor(t: Tab) {
      if (loaded[t]) return
      try {
        if (t === 'Overview') {
          const [sp, d] = await Promise.all([
            getAuditBySpecialty(filters), getAuditDetection(filters)])
          if (cancelled) return
          setSpecialties(sp.specialties); setDetection(d)
        } else if (t === 'Specialties') {
          const sp = await getAuditBySpecialty(filters)
          if (cancelled) return
          setSpecialties(sp.specialties)
        } else if (t === 'Batches') {
          const b = await getAuditByBatch(filters)
          if (cancelled) return
          setBatches(b.batches)
        } else if (t === 'Error Patterns') {
          const d = await getAuditDetection(filters)
          if (cancelled) return
          setDetection(d)
        } else if (t === 'Chart Signals') {
          const ch = await getAuditChartSignals(filters)
          if (cancelled) return
          setChartSignals(ch)
        }
        if (!cancelled) setLoaded(prev => ({ ...prev, [t]: true }))
      } catch { if (!cancelled) toast.error(`Could not load ${t}`) }
    }
    fetchFor(tab)
    return () => { cancelled = true }
  }, [tab, filters, loaded])

  // Auditors search the server rather than a loaded page, so someone past the
  // cap is still findable. Debounced, because it fires per keystroke.
  useEffect(() => {
    if (tab !== 'Auditors') return
    let cancelled = false
    const t = setTimeout(() => {
      getAuditByAuditor({ ...filters, search: auditorSearch.trim() || undefined, limit: 50 })
        .then(a => { if (!cancelled) { setAuditors(a.auditors); setAuditorMatched(a.matched ?? a.auditors.length) } })
        .catch(() => { if (!cancelled) toast.error('Could not search auditors') })
    }, auditorSearch ? 250 : 0)
    return () => { cancelled = true; clearTimeout(t) }
  }, [tab, filters, auditorSearch])

  useEffect(() => {
    if (!selectedAuditor) { setAuditorProfile(null); return }
    const auditor = selectedAuditor.auditor_key || selectedAuditor.auditor_name
    Promise.all([
      getAuditOverview({ ...filters, auditor }),
      getAuditByBatch({ ...filters, auditor, limit: 300 }),
    ]).then(([o, b]) => setAuditorProfile({ overview: o, batches: b.batches }))
      .catch(() => toast.error('Could not load auditor profile'))
  }, [selectedAuditor, filters])

  const activeFilters = Object.values(filters).filter(Boolean).length
  // Bucketed by the day charts were scored, computed in SQL. It used to be
  // built from the by-batch list, which is ordered by batch id — creation
  // sequence, not time — so the line ignored the date filter entirely.
  const trend = (overview?.trend || []).map((p: any) => ({
    label: shortDate(p.date), score: p.score, charts: p.charts,
  }))
  const threshold = overview?.pass_threshold ?? 90
  const cleanOpportunity = [
    { name: 'Clean', score: overview?.clean_accuracy ?? 0, fill: '#2563eb' },
    { name: 'Opportunity', score: overview?.opportunity_accuracy ?? 0, fill: '#7c3aed' },
  ]

  function applyFilters() {
    setFilters({ ...draft })
    setSelectedAuditor(null)
  }

  function clearFilters() {
    setDraft({})
    setFilters({})
    setSelectedAuditor(null)
  }

  if (!overview) return <div style={s.empty}>Loading...</div>

  return (
    <div>
      <div style={s.rowBetween}>
        <div>
          <div style={s.h1}>Audit Analytics</div>
          <div style={s.sub}>
            {overview.charts || 0} chart(s) · {overview.auditors || 0} auditor(s) · {overview.batches || 0} batch(es)
            {refreshing && <span style={{ marginLeft: 8, color: '#7c3aed', fontWeight: 700 }}>Updating...</span>}
          </div>
        </div>
        <button style={s.outlineBtn} onClick={() => downloadAuditAnalytics(filters)}>
          <Download size={15} /> Export Workbook
        </button>
      </div>

      <GlobalFilters draft={draft} setDraft={setDraft} apply={applyFilters}
        clear={clearFilters} active={activeFilters} />

      {!overview.charts ? (
        <div style={s.empty}>
          {activeFilters ? 'Nothing scored matches the current filters.' : 'Nothing scored yet.'}
        </div>
      ) : (
        <>
          <div style={tabBarStyle}>
            {TABS.map(t => (
              <button key={t} onClick={() => setTab(t)}
                style={tab === t ? tabOnStyle : tabStyle}>
                {t}
              </button>
            ))}
          </div>

          {tab === 'Overview' && (
            <OverviewTab overview={overview} trend={trend} cleanOpportunity={cleanOpportunity}
              specialties={specialties} detection={detection} threshold={threshold} />
          )}
          {tab === 'Auditors' && (
            <AuditorsTab rows={auditors} matched={auditorMatched}
              query={auditorSearch} setQuery={setAuditorSearch}
              selected={selectedAuditor} setSelected={setSelectedAuditor}
              profile={auditorProfile} filters={filters} threshold={threshold} />
          )}
          {tab === 'Batches' && <BatchesTab rows={batches} query={batchSearch} setQuery={setBatchSearch} threshold={threshold} />}
          {tab === 'Specialties' && <SpecialtiesTab rows={specialties} threshold={threshold} />}
          {tab === 'Error Patterns' && <ErrorPatternsTab data={detection} threshold={threshold} />}
          {tab === 'Chart Signals' && <ChartSignalsTab data={chartSignals} query={chartSearch} setQuery={setChartSearch} threshold={threshold} />}
        </>
      )}
    </div>
  )
}

function GlobalFilters({ draft, setDraft, apply, clear, active }: {
  draft: Filters
  setDraft: React.Dispatch<React.SetStateAction<Filters>>
  apply: () => void
  clear: () => void
  active: number
}) {
  return (
    <div style={filterBarStyle}>
      <span style={{ fontSize: 12, fontWeight: 800, color: '#6b7280' }}>Filter</span>
      <input type="date" style={{ ...s.input, width: 140, fontSize: 12 }}
        value={draft.from_date || ''}
        onChange={e => setDraft(f => ({ ...f, from_date: e.target.value || undefined }))} />
      <span style={{ fontSize: 12, color: '#9ca3af' }}>to</span>
      <input type="date" style={{ ...s.input, width: 140, fontSize: 12 }}
        value={draft.to_date || ''}
        onChange={e => setDraft(f => ({ ...f, to_date: e.target.value || undefined }))} />
      <select style={{ ...s.input, width: 'auto', minWidth: 150, fontSize: 12 }}
        value={draft.specialty || ''}
        onChange={e => setDraft(f => ({ ...f, specialty: e.target.value || undefined }))}>
        <option value="">All specialties</option>
        {AUDITABLE.map(x => <option key={x} value={x}>{x}</option>)}
      </select>
      <button style={s.primaryBtn} onClick={apply}>Apply</button>
      {active > 0 && (
        <button style={s.outlineBtn} onClick={clear}>
          <X size={13} /> Clear ({active})
        </button>
      )}
    </div>
  )
}

/**
 * The verdict, and the opportunity count that gates it.
 *
 * The API has always returned pass_fail, verdict_withheld_reason and
 * opportunities; nothing rendered them. So a trainer was told at batch
 * creation that a verdict needs N opportunities, then had no way to see how
 * many they had, whether the cohort passed, or why no verdict appeared — the
 * one number the whole rule turns on was invisible.
 */
function Verdict({ overview, threshold }: { overview: any; threshold: number }) {
  const verdict = overview.pass_fail as string | null
  const need = overview.opportunities_needed
  const has = overview.opportunities ?? 0
  const pass = verdict === 'PASS'
  const accent = verdict ? (pass ? '#059669' : '#dc2626') : '#6b7280'
  const bg = verdict ? (pass ? '#f0fdf4' : '#fef2f2') : '#f8fafc'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
                  padding: '12px 16px', borderRadius: 12, background: bg,
                  border: `1px solid ${accent}33`, borderLeft: `4px solid ${accent}` }}>
      <span style={{ fontSize: 20, fontWeight: 800, color: accent, letterSpacing: -0.3 }}>
        {verdict || 'No verdict'}
      </span>
      <span style={{ fontSize: 12.5, color: '#4b5563', lineHeight: 1.5 }}>
        {verdict
          ? <>Audit Score {pct(overview.audit_accuracy)} against a {threshold}% threshold,
              over {has} opportunities.</>
          : <>{overview.verdict_withheld_reason || 'Not enough opportunities yet.'}{' '}
              <strong>{has}</strong> opportunit{has === 1 ? 'y' : 'ies'} so far
              {need ? <> of the <strong>{need}</strong> a verdict needs</> : null}.
              Scores and every figure below are still valid.</>}
      </span>
      {!verdict && need > 0 && (
        <span style={{ marginLeft: 'auto', minWidth: 130 }}>
          <span style={{ display: 'block', height: 6, borderRadius: 3, background: '#e5e7eb' }}>
            <span style={{ display: 'block', height: 6, borderRadius: 3, background: '#7c3aed',
                           width: `${Math.min(100, Math.round(has / need * 100))}%` }} />
          </span>
        </span>
      )}
    </div>
  )
}

function OverviewTab({ overview, trend, cleanOpportunity, specialties, detection, threshold }: {
  overview: any; trend: any[]; cleanOpportunity: any[]; specialties: any[]
  detection: any; threshold: number
}) {
  return (
    <div style={stackStyle}>
      <Verdict overview={overview} threshold={threshold} />
      <div style={metricGridStyle}>
        <Metric label="Audit Score" value={pct(overview.audit_accuracy)} tone={tone(overview.audit_accuracy, threshold)} />
        <Metric label="Clean Chart Score" value={pct(overview.clean_accuracy)} tone="#2563eb" />
        <Metric label="Opportunity Chart Score" value={pct(overview.opportunity_accuracy)} tone="#7c3aed" />
        <Metric label="PCS Score" value={pct(overview.pcs?.accuracy)} tone="#0f766e" sub={countSub(overview.pcs)} />
        <Metric label="Query Score" value={pct(overview.query_accuracy)} tone="#475569"
          sub={overview.query_charts ? `${overview.query_correct}/${overview.query_charts}` : 'NA'} />
      </div>

      <div style={chartGridStyle}>
        <Panel title="Audit Score Trend">
          {trend.length > 1 ? (
            <ResponsiveContainer width="100%" height={190}>
              <LineChart data={trend} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} width={34} />
                <Tooltip formatter={(v: any) => [`${v}%`, 'Audit Score']} contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="score" stroke="#7c3aed" strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div style={s.empty}>Need at least two scored batches for trend.</div>}
        </Panel>

        <Panel title="Clean vs Opportunity">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={cleanOpportunity} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} width={34} />
              <Tooltip formatter={(v: any) => [`${v}%`, 'Score']} contentStyle={tooltipStyle} />
              <Bar dataKey="score" radius={[5, 5, 0, 0]}>
                {cleanOpportunity.map((r: any) => <Cell key={r.name} fill={r.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div style={chartGridStyle}>
        <Panel title="Specialty Mix">
          <ResponsiveContainer width="100%" height={190}>
            <PieChart>
              <Pie data={specialties.map((r: any) => ({ name: r.specialty, value: r.charts }))}
                dataKey="value" nameKey="name" outerRadius={74}>
                {specialties.map((_, i) => <Cell key={i} fill={palette[i % palette.length]} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Risk Signals">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <RiskRow label="Missed Errors" value={missedTotal(overview)} color="#dc2626" />
            <RiskRow label="Overcalls" value={overview.over_calls || 0} color="#ea580c" />
            <RiskRow label="Detected, Not Corrected" value={overview.detected_not_corrected || 0} color="#7c3aed" />
            {detection?.weakest?.slice(0, 3).map((r: any) => (
              <RiskRow key={r.key} label={r.label} value={pct(r.accuracy)} color={tone(r.accuracy, threshold)} />
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}

function AuditorsTab({ rows, matched, query, setQuery, selected, setSelected, profile,
                      filters, threshold }: {
  rows: any[]; matched: number; query: string; setQuery: (v: string) => void
  selected: any; setSelected: (r: any) => void; profile: any; filters: Filters
  threshold: number
}) {
  // The server has already searched and ordered these — weakest first — so
  // this only decides how many to draw. Filtering here would limit search to
  // whatever happened to be loaded.
  const shown = rows.slice(0, query.trim() ? AUDITOR_MATCH_CAP : 10)
  return (
    <div style={stackStyle}>
      <Panel title="Find Auditor">
        <SearchInput value={query} onChange={setQuery} placeholder="Search name or Emp ID..." />
        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 8 }}>
          {shown.map(r => {
            const on = selected?.auditor_key === r.auditor_key
            return (
              <button key={r.auditor_key || r.auditor_name} onClick={() => setSelected(r)}
                style={{ ...auditorCardStyle, borderColor: on ? '#7c3aed' : '#e5e7eb', background: on ? '#f5f3ff' : '#fff' }}>
                <span style={{ fontWeight: 800 }}>{r.auditor_name}</span>
                <span style={{ fontSize: 11, color: '#6b7280' }}>{r.emp_id || 'No Emp ID'} · {r.charts} chart(s)</span>
                <span style={{ fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</span>
              </button>
            )
          })}
        </div>
        {matched > shown.length && (
          <div style={s.note}>
            Showing {shown.length} of {matched} {query.trim() ? 'matches' : 'auditors'}
            {query.trim() ? '. Keep typing to narrow.' : ' — weakest first. Search to reach the rest.'}
          </div>
        )}
      </Panel>

      {selected && (
        <Panel title="Auditor Profile"
          right={<button style={s.outlineBtn}
            onClick={() => downloadAuditAuditorReportPdf(selected.auditor_key || selected.auditor_name, filters)}>
            <FileText size={14} /> PDF
          </button>}>
          {!profile ? <div style={s.empty}>Loading profile...</div> : (
            <div style={stackStyle}>
              <div style={metricGridStyle}>
                <Metric label="Audit Score" value={pct(profile.overview.audit_accuracy)} tone={tone(profile.overview.audit_accuracy, threshold)} />
                <Metric label="Clean Chart Score" value={pct(profile.overview.clean_accuracy)} tone="#2563eb" />
                <Metric label="Opportunity Chart Score" value={pct(profile.overview.opportunity_accuracy)} tone="#7c3aed" />
                <Metric label="PCS Score" value={pct(profile.overview.pcs?.accuracy)} tone="#0f766e" sub={countSub(profile.overview.pcs)} />
                <Metric label="Overcalls" value={profile.overview.over_calls || 0} tone="#ea580c" />
              </div>
              <CompactBatchTable rows={profile.batches} threshold={threshold} />
            </div>
          )}
        </Panel>
      )}
    </div>
  )
}

function BatchesTab({ rows, query, setQuery, threshold }: {
  rows: any[]; query: string; setQuery: (v: string) => void; threshold: number
}) {
  const q = query.trim().toLowerCase()
  const filtered = rows.filter(r => !q || (r.name || '').toLowerCase().includes(q)
    || (r.specialty || '').toLowerCase().includes(q))
  const shown = filtered.slice(0, ROW_CAP)
  return (
    <Panel title="Batch Performance">
      <SearchInput value={query} onChange={setQuery} placeholder="Search batch or specialty..." />
      <CompactBatchTable rows={shown} showPdf threshold={threshold} />
      {filtered.length > shown.length && <div style={s.note}>Showing {shown.length} of {filtered.length} rows.</div>}
    </Panel>
  )
}

function SpecialtiesTab({ rows, threshold }: { rows: any[]; threshold: number }) {
  if (!rows.length) return <div style={s.empty}>No specialty data yet.</div>
  return (
    <div style={stackStyle}>
      <Panel title="Specialty Scores">
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 48)}>
          <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 40, top: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="specialty" width={120} tick={{ fontSize: 11, fontWeight: 700 }} />
            <Tooltip formatter={(v: any) => [`${v}%`, 'Audit Score']} contentStyle={tooltipStyle} />
            <Bar dataKey="audit_accuracy" fill="#7c3aed" radius={[0, 5, 5, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
      <ScoreTable rows={rows} nameKey="specialty" threshold={threshold} />
    </div>
  )
}

function ErrorPatternsTab({ data, threshold }: { data: any; threshold: number }) {
  if (!data || !data.total_plantings) return <div style={s.empty}>No scored error patterns yet.</div>
  return (
    <div style={stackStyle}>
      <SignalNote
        title="Auditor Detection Patterns"
        text="This tab reads the errors intentionally introduced into audit charts and shows what auditors caught, missed, or detected but corrected incorrectly."
      />
      <div style={metricGridStyle}>
        <Metric label="Errors Introduced" value={data.total_plantings} tone="#7c3aed" />
        <Metric label="Charts Scored" value={data.charts_available} tone="#2563eb" />
        <Metric label="Training Signals" value={data.weakest?.length || 0} tone="#dc2626" />
      </div>
      <Bucket threshold={threshold} title="What To Train Next" rows={data.weakest} empty="No repeated weak pattern has crossed the training threshold." />
      <Bucket threshold={threshold} title="Detection by Error Type" rows={data.by_kind} />
      <Bucket threshold={threshold} title="Real vs Generated Detection" rows={data.by_origin} />
      <Bucket threshold={threshold} title="Detection by Section and Action" rows={data.by_section} />
      {data.pcs_characters?.length > 0 && <Bucket threshold={threshold} title="PCS Character" rows={data.pcs_characters} />}
      {data.truncated && <div style={s.warnBox}>Showing the most recent {data.charts_scanned} of {data.charts_available} scored charts.</div>}
    </div>
  )
}

function ChartSignalsTab({ data, query, setQuery, threshold }: {
  data: any; query: string; setQuery: (v: string) => void; threshold: number
}) {
  const rows: any[] = data?.charts || []
  const q = query.trim().toLowerCase()
  const filtered = rows.filter(r => !q
    || (r.chart_number || '').toLowerCase().includes(q)
    || (r.category || '').toLowerCase().includes(q)
    || (r.specialty || '').toLowerCase().includes(q))
  const shown = filtered.slice(0, ROW_CAP)
  // These four come from the SERVER, computed over every chart in scope. They
  // used to be derived from `rows`, which is a capped page — so at any real
  // size "Charts With Signals" undercounted and "Most Missed" could name a
  // chart that merely happened to be loaded. Counting loaded rows instead of
  // the query is a defect this codebase has now paid for three times.
  const reviewNeeded = data?.charts_with_signals ?? 0
  const stable = data?.charts_stable ?? 0
  const highestMiss = data?.most_missed
  const highestOvercall = data?.most_over_called
  const capped = (data?.charts_total || 0) > rows.length
  return (
    <div style={stackStyle}>
      <SignalNote
        title="Chart-Level Audit Signals"
        text="This view highlights audit charts that repeatedly produce missed introduced errors, overcalls, or wrong corrections. It is a review queue, not a verdict that the chart is bad."
      />
      <div style={metricGridStyle}>
        <Metric label="Charts With Signals" value={reviewNeeded} tone={reviewNeeded ? '#dc2626' : '#059669'}
          sub={`of ${data?.charts_total ?? 0} charts`} />
        <Metric label="Stable Charts" value={stable} tone="#059669" />
        <Metric label="Most Missed" value={highestMiss?.chart_number || 'NA'} tone="#dc2626"
          sub={highestMiss ? `${highestMiss.count} missed` : undefined} />
        <Metric label="Most Overcalled" value={highestOvercall?.chart_number || 'NA'} tone="#ea580c"
          sub={highestOvercall ? `${highestOvercall.count} overcalls` : undefined} />
      </div>
      <Panel title="Signal Evidence">
        <SearchInput value={query} onChange={setQuery} placeholder="Search chart, category or specialty..." />
        {!shown.length ? <div style={s.empty}>No chart-level audit signals yet.</div> : (
          <div style={{ overflowX: 'auto', marginTop: 12 }}>
            <table style={tableStyle}>
              <thead><tr>{['Chart', 'Specialty', 'Attempts', 'Audit Score', 'Opportunity Mix', 'Missed', 'Overcalls', 'Signal'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {shown.map(r => (
                  <tr key={r.chart_id}>
                    <td style={td}>
                      <strong>{r.chart_number}</strong>
                      <div style={muted}>{r.category}</div>
                    </td>
                    <td style={td}>{r.specialty}</td>
                    <td style={td}>{r.attempts}</td>
                    <td style={{ ...td, fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</td>
                    <td style={td}>
                      <span style={{ color: '#2563eb', fontWeight: 700 }}>{r.clean_charts || 0}</span>
                      <span style={muted}> clean · </span>
                      <span style={{ color: '#7c3aed', fontWeight: 700 }}>{r.opportunity_charts || 0}</span>
                      <span style={muted}> opportunity</span>
                    </td>
                    <td style={{ ...td, color: r.missed ? '#dc2626' : '#6b7280', fontWeight: r.missed ? 800 : 500 }}>{r.missed}</td>
                    <td style={{ ...td, color: r.over_calls ? '#ea580c' : '#6b7280', fontWeight: r.over_calls ? 800 : 500 }}>{r.over_calls}</td>
                    <td style={td}>
                      <SignalChips text={r.signal} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(filtered.length > shown.length || capped) && (
          <div style={s.note}>
            Showing {shown.length} of {filtered.length} loaded
            {capped ? ` — ${data.charts_total} charts match in total; search to reach the rest` : ''}.
          </div>
        )}
      </Panel>
    </div>
  )
}

function ScoreTable({ rows, nameKey, threshold = 90 }: {
  rows: any[]; nameKey: string; threshold?: number
}) {
  return (
    <Panel title="Score Table">
      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>{['', 'Charts', 'Audit Score', 'Clean', 'Opportunity', 'PCS', 'Add', 'Revise', 'Delete', 'Overcalls'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, ROW_CAP).map((r, i) => (
              <tr key={i}>
                <td style={td}><strong>{r[nameKey]}</strong><div style={muted}>{r.batches} batch(es) · {r.auditors} auditor(s)</div></td>
                <td style={td}>{r.charts}</td>
                <td style={{ ...td, fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</td>
                <td style={td}>{pct(r.clean_accuracy)}</td>
                <td style={td}>{pct(r.opportunity_accuracy)}</td>
                <td style={td}>{r.specialty === 'IP-DRG' ? cell(r.pcs) : 'NA'}</td>
                <td style={td}>{cell(r.add)}</td>
                <td style={td}>{cell(r.revise)}</td>
                <td style={td}>{cell(r.delete)}</td>
                <td style={td}>{r.over_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function CompactBatchTable({ rows, showPdf = false, threshold = 90 }: {
  rows: any[]; showPdf?: boolean; threshold?: number
}) {
  if (!rows?.length) return <div style={s.empty}>No batches in scope.</div>
  return (
    <div style={{ overflowX: 'auto', marginTop: 12 }}>
      <table style={tableStyle}>
        <thead>
          <tr>{['Batch', 'Specialty', 'Auditors', 'Charts', 'Audit Score', 'PCS', showPdf ? '' : null].filter(Boolean).map(h => <th key={String(h)} style={th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.batch_id}>
              <td style={td}><strong>{r.name}</strong><div style={muted}>{r.status}</div></td>
              <td style={td}>{r.specialty}</td>
              <td style={td}>{r.auditors}</td>
              <td style={td}>{r.charts}</td>
              <td style={{ ...td, fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</td>
              <td style={td}>{r.specialty === 'IP-DRG' ? cell(r.pcs) : 'NA'}</td>
              {showPdf && (
                <td style={{ ...td, textAlign: 'right' }}>
                  <button style={miniBtn} onClick={() => downloadAuditBatchReportPdf(r.batch_id)}>PDF</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Bucket({ title, rows, empty, threshold = 90 }: {
  title: string; rows: any[]; empty?: string; threshold?: number
}) {
  if (!rows?.length) return empty ? <Panel title={title}><div style={s.empty}>{empty}</div></Panel> : null
  return (
    <Panel title={title}>
      {rows.slice(0, ROW_CAP).map(r => (
        <div key={r.key} style={{ marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ minWidth: 54, fontWeight: 800, color: tone(r.accuracy, threshold) }}>{pct(r.accuracy)}</span>
            <span style={{ fontSize: 12.5 }}>{r.label}</span>
            <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 'auto' }}>
              {r.found} caught · {r.missed} missed · {r.planted} introduced
            </span>
          </div>
          <div style={{ height: 5, background: '#f3f4f6', borderRadius: 3, overflow: 'hidden', marginTop: 4 }}>
            <div style={{ height: '100%', width: `${Math.max(0, Math.min(100, r.accuracy || 0))}%`,
                          background: tone(r.accuracy, threshold), borderRadius: 3 }} />
          </div>
        </div>
      ))}
      {rows.length > ROW_CAP && <div style={s.note}>Showing {ROW_CAP} of {rows.length} rows.</div>}
    </Panel>
  )
}

function Panel({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={s.panel}>
      <div style={s.panelHead}>
        <span style={{ fontWeight: 800, fontSize: 13 }}>{title}</span>
        {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function Metric({ label, value, tone: color, sub }: { label: string; value: any; tone?: string; sub?: string }) {
  return (
    <div style={metricStyle}>
      <div style={{ fontSize: 24, fontWeight: 900, color: color || '#111827', lineHeight: 1 }}>{value}</div>
      <div style={{ marginTop: 5, fontSize: 11, fontWeight: 800, color: '#6b7280' }}>{label}</div>
      {sub && <div style={muted}>{sub}</div>}
    </div>
  )
}

function RiskRow({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 8, height: 8, borderRadius: 4, background: color }} />
      <span style={{ fontSize: 12, color: '#374151', flex: 1 }}>{label}</span>
      <span style={{ fontWeight: 800, color }}>{value}</span>
    </div>
  )
}

function SignalNote({ title, text }: { title: string; text: string }) {
  return (
    <div style={noteBoxStyle}>
      <div style={{ fontSize: 12, fontWeight: 900, color: '#5b21b6' }}>{title}</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, lineHeight: 1.45 }}>{text}</div>
    </div>
  )
}

function SignalChips({ text }: { text: string }) {
  return (
    <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
      {(text || 'stable').split(' · ').map(part => {
        const red = part.includes('miss')
        const orange = part.includes('over')
        const violet = part.includes('wrong')
        return (
          <span key={part} style={{
            ...signalChipStyle,
            background: red ? '#fee2e2' : orange ? '#ffedd5' : violet ? '#f5f3ff' : '#ecfdf5',
            color: red ? '#991b1b' : orange ? '#9a3412' : violet ? '#6d28d9' : '#047857',
          }}>{part}</span>
        )
      })}
    </span>
  )
}

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div style={{ position: 'relative', maxWidth: 340 }}>
      <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: '#9ca3af' }} />
      <input style={{ ...s.input, width: '100%', paddingLeft: 30 }} value={value}
        placeholder={placeholder} onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === 'Escape') onChange('') }} />
      {value && <button style={clearBtnStyle} onClick={() => onChange('')}><X size={13} /></button>}
    </div>
  )
}

function pct(v: number | null | undefined) {
  return v === null || v === undefined ? 'NA' : `${Number(v).toFixed(Number.isInteger(v) ? 0 : 1)}%`
}

/**
 * Colour a score against the CONFIGURED pass threshold, not a literal.
 *
 * This hardcoded 90/70. `pass_threshold` is a real column a trainer can
 * change, and both this API and the scorer already honour it — so moving it to
 * 85 left every colour on the dashboard still judging against 90, silently
 * disagreeing with the verdict printed beside it. "Borderline" is the band
 * from two-thirds of the threshold up to it.
 */
function tone(v: number | null | undefined, threshold = 90) {
  if (v === null || v === undefined) return '#9ca3af'
  if (v >= threshold) return '#059669'
  return v >= threshold * 0.78 ? '#d97706' : '#dc2626'
}

/** "2026-08-15" -> "15 Aug", for a dense trend axis. */
function shortDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return isNaN(d.getTime()) ? iso
    : `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`
}

function cell(c: any) {
  if (!c || !c.planted) return <span style={{ color: '#9ca3af' }}>NA</span>
  return <span>{pct(c.accuracy)} <span style={muted}>({c.found}/{c.planted})</span></span>
}

function countSub(c: any) {
  return c?.planted ? `${c.found}/${c.planted}` : 'NA'
}

function missedTotal(o: any) {
  return ['add', 'revise', 'delete'].reduce((n, k) => n + Math.max(0, (o[k]?.planted || 0) - (o[k]?.found || 0)), 0)
}

function short(text: string, n: number) {
  return text.length > n ? `${text.slice(0, n - 1)}...` : text
}

const palette = ['#7c3aed', '#2563eb', '#0f766e', '#db2777', '#ea580c', '#64748b', '#16a34a']
const muted: React.CSSProperties = { fontSize: 11, color: '#9ca3af' }
const tooltipStyle: React.CSSProperties = { fontSize: 12, borderRadius: 8 }
const stackStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }
const chartGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }
const metricGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }
const metricStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', padding: '14px 16px' }
const noteBoxStyle: React.CSSProperties = { border: '1px solid #ddd6fe', borderRadius: 8, background: '#faf5ff', padding: '10px 12px' }
const filterBarStyle: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'center', padding: '10px 14px', background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 16, marginBottom: 10, flexWrap: 'wrap' }
const tabBarStyle: React.CSSProperties = { display: 'flex', border: '1px solid #c4b5fd', borderRadius: 10, overflow: 'hidden', flexWrap: 'wrap', background: '#faf5ff', marginTop: 12 }
const tabStyle: React.CSSProperties = { padding: '8px 14px', border: 'none', background: 'transparent', color: '#6b7280', fontSize: 13, fontWeight: 800, cursor: 'pointer' }
const tabOnStyle: React.CSSProperties = { ...tabStyle, background: '#7c3aed', color: '#fff' }
const auditorCardStyle: React.CSSProperties = { textAlign: 'left', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, background: '#fff', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 4 }
const clearBtnStyle: React.CSSProperties = { position: 'absolute', right: 8, top: 8, border: 'none', background: 'none', color: '#9ca3af', cursor: 'pointer', padding: 0 }
const tableStyle: React.CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }
const th: React.CSSProperties = { textAlign: 'left', fontSize: 11, fontWeight: 800, color: '#6b7280', padding: '10px 12px', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' }
const td: React.CSSProperties = { padding: '10px 12px', borderBottom: '1px solid #f9fafb', whiteSpace: 'nowrap' }
const miniBtn: React.CSSProperties = { fontSize: 11, fontWeight: 800, color: '#7c3aed', background: '#fff', border: '1px solid #ddd6fe', borderRadius: 6, padding: '4px 9px', cursor: 'pointer' }
const signalChipStyle: React.CSSProperties = { fontSize: 10.5, fontWeight: 800, padding: '2px 7px', borderRadius: 6, whiteSpace: 'nowrap' }
