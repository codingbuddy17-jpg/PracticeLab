import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { AlertTriangle, Download, FileText, KeyRound, Search, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  downloadAuditAnalytics, downloadAuditAuditorReportPdf, downloadAuditBatchReportPdf,
  downloadAuditBatchResults,
  getAuditByAuditor, getAuditByBatch, getAuditBySpecialty, getAuditChartSignals,
  getAuditDetection, getAuditOverview, getAuditPattern,
} from '../../api/auditorApi'
import s from './styles'
import { AUDITABLE } from './constants'

const TABS = ['Overview', 'Review Metrics', 'Auditors', 'Batches', 'Specialties', 'Error Patterns', 'Chart Signals'] as const
type Tab = typeof TABS[number]
type Filters = { from_date?: string; to_date?: string; specialty?: string }

const ROW_CAP = 40

const keyLinkStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11,
  fontWeight: 700, color: '#7c3aed', textDecoration: 'none',
  border: '1px solid #ddd6fe', background: '#f5f3ff',
  padding: '4px 9px', borderRadius: 7, whiteSpace: 'nowrap',
}
const AUDITOR_MATCH_CAP = 20
const SIGNAL_META: Record<string, { color: string; bg: string }> = {
  'Correction Risk': { color: '#be123c', bg: '#fff1f2' },
  'Overcall Risk': { color: '#c2410c', bg: '#fff7ed' },
  'Detection Difficulty': { color: '#b91c1c', bg: '#fee2e2' },
  'Monitor': { color: '#a16207', bg: '#fef9c3' },
  'Early Signal': { color: '#6b7280', bg: '#f3f4f6' },
  'Stable': { color: '#047857', bg: '#ecfdf5' },
}
const SIGNAL_DEFINITION: Record<string, string> = {
  'Review Priority Charts': 'Charts with missed findings, over-calls, or corrections that were found but fixed incorrectly.',
  'Stable Charts': 'Charts without chart-level audit signals in the selected scope.',
  'Highest Miss Risk': 'The chart with the highest count of introduced findings that auditors did not catch.',
  'Highest Overcall Risk': 'The chart with the highest count of auditor findings on lines that did not need correction.',
  'Signal Distribution': 'How charts in the selected scope are classified for trainer review.',
  'Chart Signal Matrix': 'Chart-level evidence showing where auditors miss, over-call, or correct findings incorrectly.',
  'Error Detection Rate': 'Introduced findings caught by auditors. This is not the weighted Audit Score.',
  'Stability': 'A chart-level steadiness score based on low miss, overcall, and correction-risk rates.',
  'Miss Risk': 'Introduced findings missed divided by total introduced findings.',
  'Overcall Risk': 'Auditor over-calls divided by chart attempts.',
  'Correction Risk': 'Findings detected but corrected incorrectly divided by total introduced findings.',
  'Priority': 'The strongest chart-level signal for trainer review.',
  'Correction Risk status': 'Auditors often find the issue but enter the wrong correction.',
  'Overcall Risk status': 'Auditors often flag codes or fields that should have been left alone.',
  'Detection Difficulty': 'Auditors are missing a meaningful share of introduced findings.',
  'Monitor': 'A signal exists, but it is not yet strong enough for a higher-risk label.',
  'Early Signal': 'A signal exists, but there are too few attempts to treat it as established.',
  'Stable': 'No chart-level audit signal is currently present.',
  'Established': 'Three or more attempts are available for this chart.',
  'Early': 'Fewer than three attempts are available for this chart.',
}

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
  const [batchSort, setBatchSort] = useState('weakest')
  const [batchMatched, setBatchMatched] = useState(0)
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
        if (t === 'Specialties' || t === 'Review Metrics') {
          const sp = await getAuditBySpecialty(filters)
          if (cancelled) return
          setSpecialties(sp.specialties)
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
    if (tab !== 'Batches') return
    let cancelled = false
    const t = setTimeout(() => {
      getAuditByBatch({
        ...filters,
        search: batchSearch.trim() || undefined,
        sort: batchSort,
        limit: 200,
      }).then(b => {
        if (!cancelled) {
          setBatches(b.batches)
          setBatchMatched(b.matched ?? b.batches.length)
          setLoaded(prev => ({ ...prev, Batches: true }))
        }
      }).catch(() => { if (!cancelled) toast.error('Could not search batches') })
    }, batchSearch ? 250 : 0)
    return () => { cancelled = true; clearTimeout(t) }
  }, [tab, filters, batchSearch, batchSort])

  useEffect(() => {
    if (tab !== 'Chart Signals') return
    let cancelled = false
    const t = setTimeout(() => {
      getAuditChartSignals({ ...filters, search: chartSearch.trim() || undefined })
        .then(ch => {
          if (!cancelled) {
            setChartSignals(ch)
            setLoaded(prev => ({ ...prev, 'Chart Signals': true }))
          }
        })
        .catch(() => { if (!cancelled) toast.error('Could not search chart signals') })
    }, chartSearch ? 250 : 0)
    return () => { cancelled = true; clearTimeout(t) }
  }, [tab, filters, chartSearch])

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
  // Weekly, so the label is the week beginning rather than a single day.
  const trend = (overview?.trend || []).map((p: any) => ({
    label: shortDate(p.date), score: p.score, charts: p.charts,
    detection: p.detection, review: p.review,
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
          {refreshing && <div style={s.sub}>Updating...</div>}
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
            <OverviewTab overview={overview} trend={trend}
              cleanOpportunity={cleanOpportunity} threshold={threshold} />
          )}
          {tab === 'Review Metrics' && (
            <ReviewMetricsTab overview={overview} specialties={specialties} threshold={threshold} />
          )}
          {tab === 'Auditors' && (
            <AuditorsTab rows={auditors} matched={auditorMatched}
              query={auditorSearch} setQuery={setAuditorSearch}
              selected={selectedAuditor} setSelected={setSelectedAuditor}
              profile={auditorProfile} filters={filters} threshold={threshold}
              cohort={overview} />
          )}
          {tab === 'Batches' && <BatchesTab rows={batches} matched={batchMatched}
            query={batchSearch} setQuery={setBatchSearch}
            sort={batchSort} setSort={setBatchSort} threshold={threshold} />}
          {tab === 'Specialties' && <SpecialtiesTab rows={specialties} threshold={threshold} />}
          {tab === 'Error Patterns' && <ErrorPatternsTab data={detection} threshold={threshold} filters={filters} />}
          {tab === 'Chart Signals' && <ChartSignalsTab data={chartSignals} query={chartSearch} setQuery={setChartSearch} threshold={threshold} />}
        </>
      )}
    </div>
  )
}

/**
 * A capped list that can be grown, rather than one that silently stops.
 *
 * A hard cap with a "showing 40 of 300" note is honest but leaves a trainer
 * with no way to reach row 41 except by guessing a search term. This keeps the
 * page short by default and lets them ask for more, which is the rule the
 * revamp note set: search, caps, pagination or show-more — never a bare cap.
 */
function useShowMore<T>(rows: T[], step = ROW_CAP) {
  const [limit, setLimit] = useState(step)
  useEffect(() => { setLimit(step) }, [rows.length, step])
  const shown = rows.slice(0, limit)
  const more = rows.length - shown.length
  const control = more > 0 ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
      <button style={s.outlineBtn} onClick={() => setLimit(n => n + step)}>
        Show {Math.min(step, more)} more
      </button>
      <span style={s.note}>{shown.length} of {rows.length} shown</span>
    </div>
  ) : rows.length > step ? (
    <div style={s.note}>All {rows.length} shown.</div>
  ) : null
  return { shown, control }
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

const SECTION_LABEL: Record<string, string> = {
  PDx: 'PDx Score', SDx: 'SDx Score', PCS: 'PCS Score', CPT: 'CPT Score',
}
const SECTION_TONE: Record<string, string> = {
  PDx: '#4338ca', SDx: '#5b21b6', PCS: '#0f766e', CPT: '#0e7490',
}

/**
 * POA and modifiers — reported, never in the denominator.
 *
 * Each is an attribute OF a code line rather than a line of its own. Counting
 * them as opportunities doubled the denominator with judgements that are
 * almost never wrong, which let an auditor who flagged nothing score too high
 * and pass. They still get a percentage where they are real gradeable work.
 */
function AttributeMetrics({ attributes }: { attributes: any }) {
  const order = ['POA', 'Modifier']
  return (
    <>
      {order.filter(k => attributes?.[k]?.total).map(k => (
        <Metric key={k} label={`${k} Score`} value={pct(attributes[k].score)}
          tone="#475569" sub={`${attributes[k].correct} of ${attributes[k].total}`} />
      ))}
    </>
  )
}

/**
 * Section cards follow the DATA, not a fixed list.
 *
 * PCS was the only section scored and its card rendered unconditionally, so
 * the eight specialties that code procedures as CPT saw a permanently blank
 * "PCS Score: NA" and no score at all for the procedure work they actually
 * do. Rendering only sections that have had an error introduced makes the row
 * adapt on its own: an inpatient cohort shows PCS, an outpatient one shows
 * CPT, and filtering the specialty at the top reshapes it with no mapping to
 * keep in step.
 */
function SectionMetrics({ sections }: { sections: any }) {
  const order = ['PDx', 'SDx', 'PCS', 'CPT']
  return (
    <>
      {order.filter(k => (sections?.[k]?.total || 0) > 0).map(k => (
        <Metric key={k} label={SECTION_LABEL[k]} value={pct(sections[k].score)}
          tone={SECTION_TONE[k]}
          sub={`${sections[k].correct} of ${sections[k].total} lines`} />
      ))}
    </>
  )
}

function Verdict({ overview, threshold }: { overview: any; threshold: number }) {
  const verdict = overview.pass_fail as string | null
  const pass = verdict === 'PASS'
  const accent = verdict ? (pass ? '#059669' : '#dc2626') : '#6b7280'
  const bg = verdict ? (pass ? '#f0fdf4' : '#fef2f2') : '#f8fafc'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
                  padding: '12px 16px', borderRadius: 12, background: bg,
                  border: `1px solid ${accent}33`, borderLeft: `4px solid ${accent}` }}>
      <span style={{ fontSize: 20, fontWeight: 800, color: accent, letterSpacing: -0.3 }}>
        {verdict || 'No scored audits yet'}
      </span>
      <span style={{ fontSize: 12.5, color: '#4b5563', lineHeight: 1.5 }}>
        {verdict
          ? <>Audit Score {pct(overview.audit_score)} against a {threshold}% threshold.</>
          : <>Submit an audit to calculate the Audit Score.</>}
      </span>
    </div>
  )
}

function OverviewTab({ overview, trend, cleanOpportunity, threshold }: {
  overview: any; trend: any[]; cleanOpportunity: any[]; threshold: number
}) {
  return (
    <div style={stackStyle}>
      <Verdict overview={overview} threshold={threshold} />
      <div style={metricGridStyle}>
        <Metric label="Auditors Tested" value={overview.auditors || 0} tone="#475569" />
        <Metric label="Overall Audit Score" value={pct(overview.audit_score)}
          tone={tone(overview.audit_score, threshold)} />
        <Metric label="Error Detection Rate" value={pct(overview.audit_accuracy)}
          tone={tone(overview.audit_accuracy, threshold)} />
        <Metric label="Review Score" value={pct(overview.review_score)}
          tone={tone(overview.review_score, threshold)} />
        <Metric label="Clean Chart Score" value={pct(overview.clean_accuracy)} tone="#2563eb" />
        <Metric label="Opp Chart Score" value={pct(overview.opportunity_accuracy)} tone="#7c3aed" />
        <Metric label="Total Pass Rate" value={pct(overview.pass_rate)}
          tone={tone(overview.pass_rate, 70)}
          sub={`${overview.pass_count || 0}/${overview.verdict_count || 0}`} />
      </div>

      <div style={chartGridStyle}>
        <Panel title="Audit Score Trend — by week">
          {trend.length > 1 ? (
            <ResponsiveContainer width="100%" height={190}>
              <LineChart data={trend} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} width={34} />
                <Tooltip contentStyle={tooltipStyle}
                  formatter={(v: any) => [`${v}%`, 'Audit Score']}
                  labelFormatter={(l: any) => `Week of ${l}`} />
                <Line type="monotone" dataKey="score" stroke="#7c3aed" strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div style={s.empty}>Need at least two scored days for trend.</div>}
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

      <Panel title="Risk Signals">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>
          <RiskRow label="Missed Errors" value={missedTotal(overview)} color="#dc2626" />
          <RiskRow label="Found, Corrected Wrongly" value={overview.detected_not_corrected || 0} color="#7c3aed" />
          <RiskRow label="Overcalls" value={overview.over_calls || 0} color="#ea580c" />
        </div>
      </Panel>
    </div>
  )
}

function ReviewMetricsTab({ overview, specialties, threshold }: {
  overview: any; specialties: any[]; threshold: number
}) {
  const [selectedSpecialty, setSelectedSpecialty] = useState('')
  const [focus, setFocus] = useState<any>({ kind: 'action', key: 'add' })
  const scoped = specialties.find(r => r.specialty === selectedSpecialty) || overview
  const actionRows = ['add', 'revise', 'delete'].map(k => actionMetric(scoped, k))
  const sectionRows = sectionMetricRows(scoped)
  const attributeRows = attributeMetricRows(scoped)
  const active = metricBody(scoped, focus)

  return (
    <div style={stackStyle}>
      {specialties.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <select style={{ ...s.input, width: 210 }} value={selectedSpecialty}
            onChange={e => {
              setSelectedSpecialty(e.target.value)
              setFocus({ kind: 'action', key: 'add' })
            }}>
            <option value="">All specialties</option>
            {specialties.map(r => <option key={r.specialty} value={r.specialty}>{r.specialty}</option>)}
          </select>
        </div>
      )}

      <div style={metricGridStyle}>
        <Metric label="Charts Reviewed" value={scoped.charts || 0} tone="#475569" />
        <Metric label="Review Score" value={pct(scoped.review_score)}
          tone={tone(scoped.review_score, threshold)} />
        <Metric label="Error Detection Rate" value={pct(scoped.audit_accuracy)}
          tone={tone(scoped.audit_accuracy, threshold)} />
      </div>

      <div style={chartGridStyle}>
        <Panel title="Action Scores">
          <MetricDrillGrid rows={actionRows} focus={focus} setFocus={setFocus} threshold={threshold} />
        </Panel>
        <Panel title="Code Family Scores">
          {sectionRows.length
            ? <MetricDrillGrid rows={sectionRows} focus={focus} setFocus={setFocus} threshold={threshold} />
            : <div style={s.empty}>No code-family review metrics in scope.</div>}
        </Panel>
      </div>

      <div style={chartGridStyle}>
        <Panel title="Attribute Scores">
          {attributeRows.length
            ? <MetricDrillGrid rows={attributeRows} focus={focus} setFocus={setFocus} threshold={threshold} />
            : <div style={s.empty}>No POA or modifier review metrics in scope.</div>}
        </Panel>
        <Panel title={active.title}>
          <MetricDetail body={active} threshold={threshold} />
        </Panel>
      </div>
    </div>
  )
}

function MetricDrillGrid({ rows, focus, setFocus, threshold }: {
  rows: any[]; focus: any; setFocus: (v: any) => void; threshold: number
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: 8 }}>
      {rows.map(r => {
        const on = focus.kind === r.kind && focus.key === r.key
        return (
          <button key={`${r.kind}-${r.key}`} onClick={() => setFocus({ kind: r.kind, key: r.key })}
            style={{
              ...drillCardStyle,
              borderColor: on ? '#7c3aed' : '#e5e7eb',
              background: on ? '#f5f3ff' : '#fff',
            }}>
            <span style={{ fontSize: 20, fontWeight: 900, color: tone(r.score, threshold) }}>{pct(r.score)}</span>
            <span style={{ fontSize: 11, fontWeight: 900, color: '#4b5563' }}>{r.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function MetricDetail({ body, threshold }: { body: any; threshold: number }) {
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 32, fontWeight: 900, color: tone(body.score, threshold), lineHeight: 1 }}>
          {pct(body.score)}
        </span>
        <span style={{ fontSize: 12, color: '#4b5563' }}>{body.basis}</span>
      </div>
      <div style={{ height: 8, background: '#f3f4f6', borderRadius: 6, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.max(0, Math.min(100, body.score || 0))}%`,
                      background: tone(body.score, threshold), borderRadius: 6 }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
        {body.facts.map((f: any) => (
          <div key={f.label} style={factStyle}>
            <div style={{ fontSize: 17, fontWeight: 900 }}>{f.value}</div>
            <div style={muted}>{f.label}</div>
          </div>
        ))}
      </div>
      <div style={s.note}>{body.note}</div>
    </div>
  )
}

function actionMetric(row: any, key: string) {
  const body = row?.[key] || {}
  const label = key === 'add' ? 'Add Score' : key === 'revise' ? 'Revise Score' : 'Delete Score'
  return {
    kind: 'action', key, label,
    score: body.accuracy,
    basis: body.planted ? `${body.found || 0}/${body.planted} found and fixed` : 'NA',
  }
}

function sectionMetricRows(row: any) {
  return ['PDx', 'SDx', 'PCS', 'CPT']
    .filter(k => row?.sections?.[k]?.total)
    .map(k => ({
      kind: 'section', key: k, label: SECTION_LABEL[k],
      score: row.sections[k].score,
      basis: `${row.sections[k].correct}/${row.sections[k].total} correct`,
    }))
}

function attributeMetricRows(row: any) {
  const rows = ['POA', 'Modifier']
    .filter(k => row?.attributes?.[k]?.total)
    .map(k => ({
      kind: 'attribute', key: k, label: `${k} Score`,
      score: row.attributes[k].score,
      basis: `${row.attributes[k].correct}/${row.attributes[k].total} correct`,
    }))
  if (row?.specialty === 'IP-DRG' && row.query_charts) {
    rows.push({
      kind: 'attribute', key: 'Query', label: 'Query Score',
      score: row.query_accuracy,
      basis: `${row.query_correct || 0}/${row.query_charts} correct`,
    })
  }
  return rows
}

function metricBody(row: any, focus: any) {
  if (focus.kind === 'section') {
    const body = row?.sections?.[focus.key] || {}
    return {
      title: `${SECTION_LABEL[focus.key] || focus.key} Detail`,
      score: body.score,
      basis: body.total ? `${body.correct || 0} of ${body.total} code-line judgements correct` : 'No reviewed lines',
      facts: [
        { label: 'Correct', value: body.correct || 0 },
        { label: 'Reviewed', value: body.total || 0 },
        { label: 'Missed/Wrong', value: Math.max(0, (body.total || 0) - (body.correct || 0)) },
      ],
      note: sectionNote(focus.key),
    }
  }
  if (focus.kind === 'attribute') {
    if (focus.key === 'Query') {
      return {
        title: 'Query Detail',
        score: row?.query_accuracy,
        basis: row?.query_charts ? `${row.query_correct || 0} of ${row.query_charts} query calls correct` : 'No reviewed queries',
        facts: [
          { label: 'Correct', value: row?.query_correct || 0 },
          { label: 'Reviewed', value: row?.query_charts || 0 },
          { label: 'Missed/Wrong', value: Math.max(0, (row?.query_charts || 0) - (row?.query_correct || 0)) },
        ],
        note: 'Query score is shown with IP-DRG specialty metrics because the query judgement is separate from diagnosis and procedure line scoring.',
      }
    }
    const body = row?.attributes?.[focus.key] || {}
    return {
      title: `${focus.key} Detail`,
      score: body.score,
      basis: body.total ? `${body.correct || 0} of ${body.total} attribute judgements correct` : 'No reviewed attributes',
      facts: [
        { label: 'Correct', value: body.correct || 0 },
        { label: 'Reviewed', value: body.total || 0 },
        { label: 'Missed/Wrong', value: Math.max(0, (body.total || 0) - (body.correct || 0)) },
      ],
      note: `${focus.key} is reported separately from the code-line score so a small attribute denominator does not hide or inflate the main review metric.`,
    }
  }
  const body = row?.[focus.key] || {}
  const label = focus.key === 'add' ? 'Add' : focus.key === 'revise' ? 'Revise' : 'Delete'
  return {
    title: `${label} Detail`,
    score: body.accuracy,
    basis: body.planted ? `${body.found || 0} of ${body.planted} introduced ${label.toLowerCase()} errors found and fixed` : 'No introduced errors',
    facts: [
      { label: 'Found', value: body.found || 0 },
      { label: 'Introduced', value: body.planted || 0 },
      { label: 'Missed/Wrong', value: Math.max(0, (body.planted || 0) - (body.found || 0)) },
    ],
    note: actionNote(focus.key),
  }
}

function actionNote(key: string) {
  if (key === 'add') return 'Add measures whether auditors caught omitted codes and supplied the correct missing code back.'
  if (key === 'revise') return 'Revise measures whether auditors caught an existing code or attribute that needed correction.'
  return 'Delete measures whether auditors identified spurious codes that should not have been present.'
}

function sectionNote(key: string) {
  if (key === 'PCS') return 'PCS is the inpatient procedure review score.'
  if (key === 'CPT') return 'CPT is the outpatient procedure review score.'
  if (key === 'PDx') return 'PDx isolates principal diagnosis judgement, including wrong principal or swapped diagnosis issues.'
  return 'SDx isolates secondary diagnosis judgement, including omitted, substituted and CC/MCC-bearing diagnosis lines.'
}

/**
 * One auditor against the cohort they sat with.
 *
 * A bare "82%" is a number; "82%, cohort 89%" is a coaching conversation. The
 * cohort figure is the page-level overview, which carries the same date and
 * specialty filters but no auditor — so the comparison is always like for
 * like, and follows the filter bar.
 */
function Versus({ mine, cohort }: { mine: number | null | undefined; cohort: number | null | undefined }) {
  if (mine === null || mine === undefined || cohort === null || cohort === undefined) return null
  const d = Math.round((mine - cohort) * 10) / 10
  const colour = d > 0 ? '#059669' : d < 0 ? '#dc2626' : '#6b7280'
  return (
    <span>
      cohort {pct(cohort)}{' '}
      <strong style={{ color: colour }}>{d > 0 ? '+' : ''}{d}</strong>
    </span>
  )
}

function AuditorsTab({ rows, matched, query, setQuery, selected, setSelected, profile,
                      filters, threshold, cohort }: {
  rows: any[]; matched: number; query: string; setQuery: (v: string) => void
  selected: any; setSelected: (r: any) => void; profile: any; filters: Filters
  threshold: number; cohort: any
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
                <span style={{ fontSize: 11, color: '#6b7280' }}>{r.emp_id || 'No Emp ID'}</span>
                <span style={{ fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</span>
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
                <Metric label="Audit Score" value={pct(profile.overview.audit_score)}
                  tone={tone(profile.overview.audit_score, threshold)}
                  sub={<Versus mine={profile.overview.audit_score} cohort={cohort?.audit_score} />} />
                <Metric label="Review Score" value={pct(profile.overview.review_score)}
                  tone={tone(profile.overview.review_score, threshold)}
                  sub={<Versus mine={profile.overview.review_score} cohort={cohort?.review_score} />} />
                <Metric label="Error Detection Rate" value={pct(profile.overview.audit_accuracy)}
                  tone={tone(profile.overview.audit_accuracy, threshold)}
                  sub={<Versus mine={profile.overview.audit_accuracy} cohort={cohort?.audit_accuracy} />} />
                <Metric label="Clean Chart Score" value={pct(profile.overview.clean_accuracy)} tone="#2563eb"
                  sub={<Versus mine={profile.overview.clean_accuracy} cohort={cohort?.clean_accuracy} />} />
                <Metric label="Opportunity Chart Score" value={pct(profile.overview.opportunity_accuracy)} tone="#7c3aed"
                  sub={<Versus mine={profile.overview.opportunity_accuracy} cohort={cohort?.opportunity_accuracy} />} />
                <SectionMetrics sections={profile.overview.sections} />
                <Metric label="Found, Corrected Wrongly" value={profile.overview.detected_not_corrected || 0} tone="#7c3aed" />
                <Metric label="Overcalls" value={profile.overview.over_calls || 0} tone="#ea580c" />
              </div>
              <KnowledgeGaps rows={selected?.knowledge_gaps} />
              <CompactBatchTable rows={profile.batches} threshold={threshold} />
            </div>
          )}
        </Panel>
      )}
    </div>
  )
}

function BatchesTab({ rows, matched, query, setQuery, sort, setSort, threshold }: {
  rows: any[]; matched: number; query: string; setQuery: (v: string) => void
  sort: string; setSort: (v: string) => void; threshold: number
}) {
  const { shown, control } = useShowMore(rows)
  const scored = rows.filter(r => r.audit_score !== null && r.audit_score !== undefined)
  const avgScore = scored.length
    ? scored.reduce((sum, r) => sum + Number(r.audit_score || 0), 0) / scored.length
    : null
  const lowest = scored.slice().sort((a, b) => Number(a.audit_score) - Number(b.audit_score))[0]
  const highest = scored.slice().sort((a, b) => Number(b.audit_score) - Number(a.audit_score))[0]
  const auditorEntries = rows.reduce((sum, r) => sum + Number(r.auditors || 0), 0)
  return (
    <Panel title="Batch Performance">
      <div style={metricGridStyle}>
        <Metric label="Batches Reviewed" value={matched || rows.length} tone="#7c3aed" />
        <Metric label="Average Audit Score" value={pct(avgScore)} tone={tone(avgScore, threshold)} />
        <Metric label="Lowest Batch" value={lowest?.name || 'NA'} tone="#dc2626"
          sub={lowest ? pct(lowest.audit_score) : undefined} />
        <Metric label="Highest Batch" value={highest?.name || 'NA'} tone="#059669"
          sub={highest ? pct(highest.audit_score) : undefined} />
        <Metric label="Auditor Entries" value={auditorEntries} tone="#2563eb" />
      </div>
      <div style={filterBarStyle}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search batch or specialty..." />
        <select value={sort} onChange={e => setSort(e.target.value)}
          style={{ ...s.input, width: 170 }}>
          <option value="weakest">Weakest score</option>
          <option value="latest">Latest scored</option>
          <option value="auditors">Most auditors</option>
          <option value="charts">Most charts</option>
        </select>
        {query.trim() && <span style={s.note}>{rows.length} of {matched || rows.length} matched</span>}
      </div>
      <CompactBatchTable rows={shown} showActions threshold={threshold} />
      {control}
    </Panel>
  )
}

function SpecialtiesTab({ rows, threshold }: { rows: any[]; threshold: number }) {
  if (!rows.length) return <div style={s.empty}>No specialty data yet.</div>
  return (
    <div style={stackStyle}>
      <Panel title="Specialty Scores">
        <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 68)}>
          <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 40, top: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="specialty" width={120} tick={{ fontSize: 11, fontWeight: 700 }} />
            <Tooltip formatter={(v: any, name: any) => [`${v}%`, name]} contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="audit_score" name="Audit Score" fill="#7c3aed" radius={[0, 5, 5, 0]} />
            <Bar dataKey="review_score" name="Review Score" fill="#2563eb" radius={[0, 5, 5, 0]} />
            <Bar dataKey="audit_accuracy" name="Error Detection Rate" fill="#059669" radius={[0, 5, 5, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
      <ScoreTable rows={rows} nameKey="specialty" threshold={threshold} />
    </div>
  )
}

function ErrorPatternsTab({ data, threshold, filters }: {
  data: any; threshold: number; filters: Filters
}) {
  const [showAllInsights, setShowAllInsights] = useState(false)
  const [drill, setDrill] = useState<Record<string, string> | null>(null)
  const drillKind = (r: any) => setDrill({ kind: String(r.key) })
  if (!data || !data.total_plantings) return <div style={s.empty}>No scored error patterns yet.</div>
  const notes = [...(data.commentary || []), ...(showAllInsights ? (data.commentary_more || []) : [])]
  return (
    <div style={stackStyle}>
      {notes.length > 0 && (
        <Panel title="Error Insights">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {notes.map((n: any, i: number) => <InsightRow key={i} note={n} />)}
          </div>
          {data.commentary_more?.length > 0 && (
            <button onClick={() => setShowAllInsights(v => !v)}
              style={{ ...miniBtn, marginTop: 10 }}>
              {showAllInsights ? 'Show fewer' : `${data.commentary_more.length} more`}
            </button>
          )}
        </Panel>
      )}
      {/*
        The scan window, stated BEFORE the figures it governs. This sat at the
        very bottom, under four bar lists, where a reader met every number
        before learning it described a slice.
      */}
      {data.truncated && (
        <div style={s.warnBox}>
          <AlertTriangle size={14} color="#d97706" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            Read from the most recent {data.charts_scanned} of {data.charts_available}{' '}
            scored charts. Narrow the date filter to read an earlier period.
          </span>
        </div>
      )}
      <div style={metricGridStyle}>
        <Metric label="Errors Introduced" value={data.total_plantings} tone="#7c3aed" />
        <Metric label="Charts Scored" value={data.charts_available} tone="#2563eb" />
        <Metric label="Training Signals" value={data.weakest?.length || 0} tone="#dc2626"
          sub={`patterns seen ${data.min_for_pattern}+ times and under 60%`} />
      </div>

      <OriginComparison rows={data.by_origin} threshold={threshold} />

      {drill && (
        <PatternDrill query={drill} filters={filters} threshold={threshold}
          onClose={() => setDrill(null)} />
      )}

      <Bucket threshold={threshold} minForPattern={data.min_for_pattern}
        onDrill={drillKind} title="What To Train Next" rows={data.weakest}
        empty="No repeated weak pattern has crossed the training threshold." />
      <Bucket threshold={threshold} minForPattern={data.min_for_pattern}
        onDrill={drillKind} title="Detection by Error Type" rows={data.by_kind} />
      <SectionActionMatrix m={data.section_matrix} threshold={threshold}
        minForPattern={data.min_for_pattern} onDrill={setDrill} />
      {/* Detection by which way the level error went.
          Auditors are trained to look for upcoding, because that is what
          payers audit for. Downcoding is revenue quietly left on the table
          with nobody watching — so if detection is lopsided, it shows here. */}
      {data.by_level_direction?.length > 0 && (
        <Bucket threshold={threshold} minForPattern={data.min_for_pattern}
          onDrill={drillKind} title="E/M Level Errors by Direction"
          rows={data.by_level_direction} />
      )}
      {data.pcs_characters?.length > 0 && (
        <Bucket threshold={threshold} minForPattern={data.min_for_pattern}
          onDrill={drillKind} title="PCS Character" rows={data.pcs_characters} />
      )}
      {/* The other axis: which body of knowledge, rather than which mechanic.
          "Root operation errors are missed" says what to drill; "obstetric
          diagnoses are missed" says who to put on which charts. Diagnosis
          sections only — PCS and CPT have no ICD chapter. */}
      {data.by_chapter?.length > 0 && (
        <Bucket threshold={threshold} minForPattern={data.min_for_pattern}
          title="Diagnosis Chapter" rows={data.by_chapter}
          empty="No diagnosis chapter has enough introduced errors to read yet." />
      )}
    </div>
  )
}

function ChartSignalsTab({ data, query, setQuery, threshold }: {
  data: any; query: string; setQuery: (v: string) => void; threshold: number
}) {
  const rows: any[] = data?.charts || []
  const { shown, control } = useShowMore(rows)
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
  const distribution = (data?.priority_distribution || []).map((r: any) => ({
    ...r,
    fill: SIGNAL_META[r.label]?.color || '#6b7280',
  }))
  return (
    <div style={stackStyle}>
      <div style={metricGridStyle}>
        <Metric label="Review Priority Charts" value={reviewNeeded} tone={reviewNeeded ? '#dc2626' : '#059669'}
          title={SIGNAL_DEFINITION['Review Priority Charts']}
          sub={`of ${data?.charts_total ?? 0} charts`} />
        <Metric label="Stable Charts" value={stable} tone="#059669"
          title={SIGNAL_DEFINITION['Stable Charts']} />
        <Metric label="Highest Miss Risk" value={highestMiss?.chart_number || 'NA'} tone="#dc2626"
          title={SIGNAL_DEFINITION['Highest Miss Risk']}
          sub={highestMiss ? `${highestMiss.count} missed` : undefined} />
        <Metric label="Highest Overcall Risk" value={highestOvercall?.chart_number || 'NA'} tone="#ea580c"
          title={SIGNAL_DEFINITION['Highest Overcall Risk']}
          sub={highestOvercall ? `${highestOvercall.count} overcalls` : undefined} />
      </div>

      {distribution.length > 0 && (
        <Panel title="Signal Distribution" titleText={SIGNAL_DEFINITION['Signal Distribution']}>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={distribution} margin={{ left: 8, right: 20, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={34} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Charts" radius={[4, 4, 0, 0]}>
                {distribution.map((r: any) => <Cell key={r.label} fill={r.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      <Panel title="Chart Signal Matrix" titleText={SIGNAL_DEFINITION['Chart Signal Matrix']}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search chart, category or specialty..." />
        {!shown.length ? <div style={s.empty}>No chart-level audit signals yet.</div> : (
          <div style={{ overflowX: 'auto', marginTop: 12 }}>
            <table style={tableStyle}>
              <thead><tr>{['Chart', 'Specialty', 'Attempts', 'Error Detection Rate', 'Stability', 'Miss Risk', 'Overcall Risk', 'Correction Risk', 'Priority', ''].map(h => (
                <th key={h} style={th} title={SIGNAL_DEFINITION[h]}>
                  {h}
                </th>
              ))}</tr></thead>
              <tbody>
                {shown.map(r => (
                  <tr key={r.chart_id}>
                    <td style={td}>
                      <strong>{r.chart_number}</strong>
                      <div style={muted}>{r.category}</div>
                    </td>
                    <td style={td}>{r.specialty}</td>
                    <td style={td} title={SIGNAL_DEFINITION[r.confidence]}>
                      <strong>{r.attempts}</strong>
                      <div style={muted}>{r.confidence}</div>
                    </td>
                    <td style={{ ...td, fontWeight: 800, color: tone(r.detection_score, threshold) }}>{pct(r.detection_score)}</td>
                    <td style={{ ...td, fontWeight: 800, color: tone(r.stability_score, threshold) }}>{pct(r.stability_score)}</td>
                    <td style={{ ...td, color: r.miss_risk ? '#dc2626' : '#6b7280', fontWeight: r.miss_risk ? 800 : 500 }}>
                      {pct(r.miss_risk)}
                      <div style={muted}>{r.missed || 0} missed</div>
                    </td>
                    <td style={{ ...td, color: r.overcall_rate ? '#ea580c' : '#6b7280', fontWeight: r.overcall_rate ? 800 : 500 }}>
                      {pct(r.overcall_rate)}
                      <div style={muted}>{r.over_calls || 0} overcalls</div>
                    </td>
                    <td style={{ ...td, color: r.correction_risk ? '#be123c' : '#6b7280', fontWeight: r.correction_risk ? 800 : 500 }}>
                      {pct(r.correction_risk)}
                      <div style={muted}>{r.detected_not_corrected || 0} fixed wrongly</div>
                    </td>
                    <td style={td}>
                      <span style={{
                        ...signalChipStyle,
                        color: SIGNAL_META[r.review_priority]?.color || '#374151',
                        background: SIGNAL_META[r.review_priority]?.bg || '#f3f4f6',
                        border: `1px solid ${(SIGNAL_META[r.review_priority]?.color || '#9ca3af')}33`,
                      }} title={SIGNAL_DEFINITION[`${r.review_priority} status`] || SIGNAL_DEFINITION[r.review_priority] || SIGNAL_DEFINITION.Priority}>
                        {r.review_priority || r.signal}
                      </span>
                      <div style={muted}>
                        {(r.clean_charts || 0)} clean · {(r.opportunity_charts || 0)} opportunity
                      </div>
                      {/* What this chart's errors are ABOUT — the signal says
                          it produces misses, this says what kind. Absent when
                          they share no theme, which is common and honest. */}
                      {r.focus && (
                        <div style={{ ...muted, color: '#0f766e' }}>
                          {r.focus.kind}: <strong>{r.focus.label}</strong> ({r.focus.count})
                        </div>
                      )}
                    </td>
                    {/*
                      A signal says a chart keeps producing misses. The next
                      question is always whether the introduced error is unfair
                      or the answer key is wrong, and that was a manual hunt
                      through another tab. This lands on the chart's authored
                      errors directly.
                    */}
                    <td style={td}>
                      <Link
                        to={`/trainer/auditor/keys?chart=${r.chart_id}&specialty=${encodeURIComponent(r.specialty || '')}`}
                        title="Open the errors authored for this chart"
                        style={keyLinkStyle}>
                        <KeyRound size={12} /> Key
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {control}
        {capped && (
          <div style={s.note}>
            {data.charts_total} charts match in total; the server sends the
            weakest {rows.length}. Refine search to narrow the list.
          </div>
        )}
      </Panel>
    </div>
  )
}

/**
 * The procedure score for a row, whichever kind of procedure that row codes.
 *
 * This column was hardcoded to PCS and printed "NA" for every specialty except
 * IP-DRG — nine rows of nothing in a ten-row table. Inpatient work is PCS,
 * everything else is CPT, and the cell says which so the two are never read as
 * the same number.
 */
function ProcedureCell({ row }: { row: any }) {
  const ip = row.specialty === 'IP-DRG'
  const sec = row.sections?.[ip ? 'PCS' : 'CPT']
  if (!sec || !sec.total) return <span style={muted}>NA</span>
  return (
    <span>
      <strong>{pct(sec.score)}</strong>
      <span style={{ ...muted, marginLeft: 5 }}>{ip ? 'PCS' : 'CPT'}</span>
    </span>
  )
}

function ScoreTable({ rows, nameKey, threshold = 90 }: {
  rows: any[]; nameKey: string; threshold?: number
}) {
  const { shown: visible, control } = useShowMore(rows)
  const headerDefs: Record<string, string> = {
    'Audit Score': 'Weighted score used for the auditor training verdict.',
    'Review Score': 'Code-line review score: how often audited lines were judged correctly.',
    'Error Detection Rate': 'Introduced findings caught by auditors. This is not the weighted Audit Score.',
    'Clean Chart Score': 'Performance on charts with no introduced errors.',
    'Opportunity Chart Score': 'Performance on charts with introduced errors.',
    'PCS/CPT Score': 'Procedure-family score: PCS for IP-DRG, CPT for outpatient specialties.',
    Overcalls: 'Auditor findings on lines that did not need correction.',
  }
  return (
    <Panel title="Score Table">
      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>{['Specialty', 'Charts', 'Auditors', 'Batches', 'Audit Score', 'Review Score', 'Error Detection Rate', 'Clean Chart Score', 'Opportunity Chart Score', 'PCS/CPT Score', 'Overcalls'].map(h => (
              <th key={h} style={th} title={headerDefs[h]}>{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {visible.map((r, i) => (
              <tr key={i}>
                <td style={td}><strong>{r[nameKey]}</strong></td>
                <td style={td}>{r.charts}</td>
                <td style={td}>{r.auditors}</td>
                <td style={td}>{r.batches}</td>
                <td style={{ ...td, fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</td>
                <td style={{ ...td, fontWeight: 800, color: tone(r.review_score, threshold) }}>{pct(r.review_score)}</td>
                <td style={{ ...td, fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</td>
                <td style={td}>{pct(r.clean_accuracy)}</td>
                <td style={td}>{pct(r.opportunity_accuracy)}</td>
                <td style={td}><ProcedureCell row={r} /></td>
                <td style={td}>{r.over_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {control}
    </Panel>
  )
}

function CompactBatchTable({ rows, showActions = false, threshold = 90 }: {
  rows: any[]; showActions?: boolean; threshold?: number
}) {
  if (!rows?.length) return <div style={s.empty}>No batches in scope.</div>
  return (
    <div style={{ overflowX: 'auto', marginTop: 12 }}>
      <table style={tableStyle}>
        <thead>
          <tr>{['Batch', 'Specialty', 'Auditors', 'Charts', 'Audit Score', 'Review Score', 'Error Detection Rate', 'Clean', 'Opportunity', 'Procedure', 'Last Scored', showActions ? '' : null].filter(Boolean).map(h => <th key={String(h)} style={th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.batch_id}>
              <td style={td}><strong>{r.name}</strong><div style={muted}>{r.status}</div></td>
              <td style={td}>{r.specialty}</td>
              <td style={td}>{r.auditors}</td>
              <td style={td}>{r.charts}</td>
              <td style={{ ...td, fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</td>
              <td style={{ ...td, fontWeight: 800, color: tone(r.review_score, threshold) }}>{pct(r.review_score)}</td>
              <td style={{ ...td, fontWeight: 800, color: tone(r.audit_accuracy, threshold) }}>{pct(r.audit_accuracy)}</td>
              <td style={td}>{pct(r.clean_accuracy)}</td>
              <td style={td}>{pct(r.opportunity_accuracy)}</td>
              <td style={td}><ProcedureCell row={r} /></td>
              <td style={td}>{shortDateTime(r.scored_at)}</td>
              {showActions && (
                <td style={{ ...td, textAlign: 'right' }}>
                  <span style={{ display: 'inline-flex', gap: 6 }}>
                    <button style={miniBtn} onClick={() => downloadAuditBatchReportPdf(r.batch_id)}>PDF</button>
                    <button style={miniBtn} onClick={() => downloadAuditBatchResults(r.batch_id)}>Workbook</button>
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Section down, action across — read either way.
 *
 * This was a flat list of "SDx · Revise" rows, which answers only the question
 * it was built for. The two a trainer asks next — how are we on SDx overall,
 * and are Revises worse than Deletes everywhere — need the margins, and a list
 * of compound strings has none. The matrix carries both and takes less room.
 *
 * Cells are coloured by detection rate and carry their volume, because a cell
 * at 50% over four errors and one at 50% over ninety are different facts.
 */
/**
 * One pattern, drilled: who misses it, where it lives, and whether it is
 * improving.
 *
 * The tab could say a pattern slips past 70% of the time and then stopped —
 * a diagnosis with no treatment plan. Every pattern row and every matrix cell
 * opens this, so "so who?" is one click rather than a different tab and a
 * guess.
 */
function PatternDrill({ query, filters, threshold, onClose }: {
  query: Record<string, string>; filters: Filters; threshold: number
  onClose: () => void
}) {
  const [data, setData] = useState<any>(null)
  const key = JSON.stringify(query)
  useEffect(() => {
    setData(null)
    getAuditPattern({ ...filters, ...query })
      .then(setData)
      .catch(() => toast.error('Could not load that pattern'))
  }, [key, filters])

  return (
    <Panel title={data ? `${data.label} — who misses it` : 'Loading pattern...'}
      right={<button style={miniBtn} onClick={onClose}>Close</button>}>
      {!data ? <div style={s.empty}>Loading...</div> : !data.planted ? (
        <div style={s.empty}>Nothing of this kind in the current scope.</div>
      ) : (
        <div style={stackStyle}>
          <div style={metricGridStyle}>
            <Metric label="Detection" value={pct(data.accuracy)}
              tone={tone(data.accuracy, threshold)}
              sub={`${data.found} of ${data.planted} caught`} />
            <Metric label="Missed" value={data.missed} tone="#dc2626" />
            <Metric label="Fixed Wrongly" value={data.detected_not_corrected}
              tone={ACTION_TONE.wrongFix} />
          </div>

          {data.trend?.length > 1 && (
            <div>
              <div style={{ ...s.note, marginTop: 0 }}>Detection on this pattern, by week</div>
              <ResponsiveContainer width="100%" height={150}>
                <LineChart data={data.trend.map((t: any) => ({
                  label: shortDate(t.week_of), score: t.accuracy,
                }))} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`}
                    tick={{ fontSize: 10 }} width={34} />
                  <Tooltip contentStyle={tooltipStyle}
                    formatter={(v: any) => [`${v}%`, 'Detection']}
                    labelFormatter={(l: any) => `Week of ${l}`} />
                  <Line type="monotone" dataKey="score" stroke="#7c3aed"
                    strokeWidth={2.5} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table style={tableStyle}>
              <thead><tr>{['Auditor', 'Detection', 'Caught', 'Missed', 'Fixed wrongly']
                .map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {data.auditors.map((a: any) => (
                  <tr key={a.auditor_key}>
                    <td style={td}>
                      <strong>{a.auditor_name}</strong>
                      {a.emp_id && <div style={muted}>{a.emp_id}</div>}
                    </td>
                    <td style={{ ...td, fontWeight: 800, color: tone(a.accuracy, threshold) }}>
                      {pct(a.accuracy)}
                    </td>
                    <td style={td}>{a.found}/{a.planted}</td>
                    <td style={{ ...td, color: a.missed ? '#dc2626' : '#6b7280' }}>{a.missed}</td>
                    <td style={{ ...td, color: a.detected_not_corrected ? ACTION_TONE.wrongFix : '#6b7280' }}>
                      {a.detected_not_corrected}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.charts?.length > 0 && (
            <div style={s.note}>
              Worst charts for this pattern:{' '}
              {data.charts.slice(0, 6).map((c: any) => (
                <Link key={c.chart_id} style={{ ...keyLinkStyle, marginRight: 6 }}
                  to={`/trainer/auditor/keys?chart=${c.chart_id}`}>
                  {c.chart_number} {pct(c.accuracy)}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  )
}

function SectionActionMatrix({ m, threshold, minForPattern = 0, onDrill }: {
  m: any; threshold: number; minForPattern?: number
  onDrill?: (q: Record<string, string>) => void
}) {
  if (!m?.sections?.length) return null
  const cell = (c: any, isTotal = false) => {
    if (!c || !c.planted) return <span style={muted}>—</span>
    const thin = !isTotal && minForPattern > 0 && c.planted < minForPattern
    return (
      <span style={{ opacity: thin ? 0.5 : 1 }}>
        <strong style={{ color: tone(c.accuracy, threshold) }}>{pct(c.accuracy)}</strong>
        <span style={{ ...muted, marginLeft: 5 }}>{c.found}/{c.planted}</span>
        {c.detected_not_corrected > 0 && (
          <div style={{ fontSize: 10, color: ACTION_TONE.wrongFix, fontWeight: 700 }}>
            {c.detected_not_corrected} fixed wrongly
          </div>
        )}
      </span>
    )
  }
  return (
    <Panel title="Detection by section and action">
      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={th}></th>
              {m.actions.map((a: string) => <th key={a} style={th}>{a}</th>)}
              <th style={{ ...th, borderLeft: '2px solid #e5e7eb' }}>All actions</th>
            </tr>
          </thead>
          <tbody>
            {m.sections.map((sec: string) => (
              <tr key={sec}>
                <td style={{ ...td, fontWeight: 800 }}>{sec}</td>
                {m.actions.map((a: string) => (
                  <td key={a} style={{ ...td, cursor: m.cells[sec]?.[a] && onDrill ? 'pointer' : 'default' }}
                    title={m.cells[sec]?.[a] && onDrill ? 'See who misses this' : undefined}
                    onClick={() => m.cells[sec]?.[a] && onDrill?.({ section: sec, action: a })}>
                    {cell(m.cells[sec]?.[a])}
                  </td>
                ))}
                <td style={{ ...td, borderLeft: '2px solid #e5e7eb' }}>
                  {cell(m.section_totals[sec], true)}
                </td>
              </tr>
            ))}
            <tr>
              <td style={{ ...td, fontWeight: 800, borderTop: '2px solid #e5e7eb' }}>
                All sections
              </td>
              {m.actions.map((a: string) => (
                <td key={a} style={{ ...td, borderTop: '2px solid #e5e7eb' }}>
                  {cell(m.action_totals[a], true)}
                </td>
              ))}
              <td style={{ ...td, borderTop: '2px solid #e5e7eb',
                           borderLeft: '2px solid #e5e7eb' }}>
                {cell(m.total, true)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function Bucket({ title, rows, empty, threshold = 90, minForPattern = 0, onDrill }: {
  title: string; rows: any[]; empty?: string; threshold?: number
  minForPattern?: number; onDrill?: (row: any) => void
}) {
  const { shown, control } = useShowMore(rows || [])
  if (!rows?.length) return empty ? <Panel title={title}><div style={s.empty}>{empty}</div></Panel> : null
  return (
    <Panel title={title}>
      {shown.map(r => {
        const planted = r.planted || 0
        // Below the pattern threshold this is an anecdote, not a curriculum.
        // Shown, because hiding it would misrepresent the total, but dimmed so
        // a 3-sample row cannot be mistaken for a 300-sample one.
        const thin = minForPattern > 0 && planted < minForPattern
        const wrongFix = r.detected_not_corrected || 0
        const found = r.found || 0
        const missed = Math.max(0, planted - found - wrongFix)
        const pctOf = (n: number) => planted ? (n / planted) * 100 : 0
        return (
          <div key={r.key} onClick={() => onDrill?.(r)}
            title={onDrill ? 'See who misses this' : undefined}
            style={{ marginBottom: 12, opacity: thin ? 0.55 : 1,
                     cursor: onDrill ? 'pointer' : 'default' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ minWidth: 54, fontWeight: 800, color: tone(r.accuracy, threshold) }}>
                {pct(r.accuracy)}
              </span>
              <span style={{ fontSize: 12.5 }}>{r.label}</span>
              {thin && <span style={{ ...s.tag, background: '#f3f4f6', color: '#6b7280' }}>
                too few to teach from
              </span>}
              <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 'auto' }}>
                {found} caught
                {wrongFix > 0 && <> · <strong style={{ color: ACTION_TONE.wrongFix }}>
                  {wrongFix} fixed wrongly</strong></>}
                {' '}· {missed} missed · {planted} introduced
              </span>
            </div>
            {/*
              Three segments, not one accuracy bar. "40% caught" hides the
              difference between an auditor who cannot SEE the error and one
              who sees it and gets the fix wrong — the same 40%, and entirely
              different coaching. The split was already in the payload and only
              the total was drawn.
            */}
            <div style={{ display: 'flex', height: 7, borderRadius: 4, overflow: 'hidden',
                          marginTop: 5, background: '#f3f4f6' }}>
              <div style={{ width: `${pctOf(found)}%`, background: '#059669' }} />
              <div style={{ width: `${pctOf(wrongFix)}%`, background: ACTION_TONE.wrongFix }} />
              <div style={{ width: `${pctOf(missed)}%`, background: '#dc2626' }} />
            </div>
          </div>
        )
      })}
      {control}
    </Panel>
  )
}

const ACTION_TONE = { wrongFix: '#7c3aed' }

/**
 * The comparison this module exists to make, given its own panel.
 *
 * Auditors tend to do better on errors the system invented than on the ones
 * their own coders actually made, and only the second number describes the
 * job. It was the third of four identical bar lists, which read as no more
 * important than PCS character breakdowns.
 */
function OriginComparison({ rows, threshold }: { rows: any[]; threshold: number }) {
  if (!rows?.length) return null
  const find = (k: string) => rows.find(r => r.key === k)
  const observed = find('observed')
  const synthetic = find('synthetic')
  if (!observed || !synthetic) return null
  const gap = Math.round(((synthetic.accuracy || 0) - (observed.accuracy || 0)) * 10) / 10
  return (
    <Panel title="Real coder errors vs generated">
      <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <Metric label="Errors your coders really made" value={pct(observed.accuracy)}
          tone={tone(observed.accuracy, threshold)}
          sub={`${observed.found} of ${observed.planted} caught`} />
        <Metric label="System-generated errors" value={pct(synthetic.accuracy)}
          tone={tone(synthetic.accuracy, threshold)}
          sub={`${synthetic.found} of ${synthetic.planted} caught`} />
      </div>
      <div style={s.note}>
        {gap > 3
          ? `Auditors are ${gap} points worse on the mistakes your own coders make. `
            + 'That gap is the one worth closing — the generated set is practice, '
            + 'the observed set is the job.'
          : gap < -3
            ? `Auditors are ${Math.abs(gap)} points better on real coder errors than `
              + 'on generated ones, which is the right way round.'
            : 'Auditors perform about the same on both, so the generated set is a '
              + 'fair proxy for the real work.'}
      </div>
    </Panel>
  )
}

/**
 * The themes running through what an auditor MISSED.
 *
 * Not what they saw. A caught planting is not a gap, and mixing the two would
 * rank someone's strongest area beside their weakest purely on volume.
 * Absent when nothing clears the threshold, which is a real answer at small
 * volumes rather than an empty box.
 */
function KnowledgeGaps({ rows }: { rows?: any[] }) {
  if (!rows?.length) return null
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 6 }}>
        Knowledge areas to coach
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8 }}>
        {rows.map(g => (
          <span key={g.kind + g.label} style={{ fontSize: 12, background: '#f0fdfa', color: '#0f766e', border: '1px solid #99f6e4', padding: '4px 11px', borderRadius: 10 }}>
            <span style={{ color: '#5eead4' }}>{g.kind}</span>{' '}
            <strong>{g.label}</strong> · {g.count} missed
          </span>
        ))}
      </div>
    </div>
  )
}

function Panel({ title, titleText, right, children }: {
  title: string; titleText?: string; right?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div style={s.panel}>
      <div style={s.panelHead}>
        <span title={titleText} style={{ fontWeight: 800, fontSize: 13 }}>{title}</span>
        {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function Metric({ label, value, tone: color, sub, title }: {
  label: string; value: any; tone?: string; sub?: React.ReactNode; title?: string
}) {
  return (
    <div style={metricStyle} title={title}>
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

function InsightRow({ note }: { note: any }) {
  const meta: Record<string, { c: string; bg: string }> = {
    focus: { c: '#3730a3', bg: '#eef2ff' },
    coaching: { c: '#1d4ed8', bg: '#dbeafe' },
    warn: { c: '#92400e', bg: '#fef3c7' },
    good: { c: '#166534', bg: '#dcfce7' },
    info: { c: '#374151', bg: '#f9fafb' },
  }
  const m = meta[note?.kind] || meta.info
  return (
    <div style={{ background: m.bg, border: `1px solid ${m.c}22`, borderRadius: 8,
                  padding: '9px 12px', fontSize: 12.5, color: m.c, lineHeight: 1.45 }}>
      {note?.text}
    </div>
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

function shortDateTime(iso?: string | null) {
  if (!iso) return 'NA'
  const d = new Date(iso)
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

const muted: React.CSSProperties = { fontSize: 11, color: '#9ca3af' }
const tooltipStyle: React.CSSProperties = { fontSize: 12, borderRadius: 8 }
const stackStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }
const chartGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }
const metricGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }
const metricStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', padding: '14px 16px' }
const drillCardStyle: React.CSSProperties = { textAlign: 'left', border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', padding: 12, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 4, minHeight: 92 }
const factStyle: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 8, background: '#f8fafc', padding: '10px 12px' }
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
