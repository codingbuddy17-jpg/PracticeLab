import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Download, FileText, KeyRound, Search, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  downloadAuditAnalytics, downloadAuditAuditorReportPdf, downloadAuditBatchReportPdf,
  getAuditByAuditor, getAuditByBatch, getAuditBySpecialty, getAuditChartSignals,
  getAuditDetection, getAuditOverview,
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
        if (t === 'Specialties' || t === 'Review Metrics') {
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
  const need = overview.opportunities_needed
  const has = overview.review_total ?? 0
  const pass = verdict === 'PASS'
  const accent = verdict ? (pass ? '#059669' : '#dc2626') : '#6b7280'
  const bg = verdict ? (pass ? '#f0fdf4' : '#fef2f2') : '#f8fafc'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
                  padding: '12px 16px', borderRadius: 12, background: bg,
                  border: `1px solid ${accent}33`, borderLeft: `4px solid ${accent}` }}>
      <span style={{ fontSize: 20, fontWeight: 800, color: accent, letterSpacing: -0.3 }}>
        {verdict || 'Verdict pending'}
      </span>
      <span style={{ fontSize: 12.5, color: '#4b5563', lineHeight: 1.5 }}>
        {verdict
          ? <>Audit Score {pct(overview.audit_score)} against a {threshold}% threshold.</>
          : <>Verdict pending. Audit Score {pct(overview.audit_score)} is directional until more charts are reviewed.</>}
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
            <Bar dataKey="audit_score" fill="#7c3aed" radius={[0, 5, 5, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
      <ScoreTable rows={rows} nameKey="specialty" threshold={threshold} />
    </div>
  )
}

function ErrorPatternsTab({ data, threshold }: { data: any; threshold: number }) {
  const [showAllInsights, setShowAllInsights] = useState(false)
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
              <thead><tr>{['Chart', 'Specialty', 'Attempts', 'Detection', 'Opportunity Mix', 'Missed', 'Overcalls', 'Signal', ''].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {shown.map(r => (
                  <tr key={r.chart_id}>
                    <td style={td}>
                      <strong>{r.chart_number}</strong>
                      <div style={muted}>{r.category}</div>
                    </td>
                    <td style={td}>{r.specialty}</td>
                    <td style={td}>{r.attempts}</td>
                    <td style={{ ...td, fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</td>
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
  return (
    <Panel title="Score Table">
      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>{['', 'Charts', 'Audit Score', 'Clean', 'Opportunity', 'Procedure', 'Add', 'Revise', 'Delete', 'Overcalls'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, ROW_CAP).map((r, i) => (
              <tr key={i}>
                <td style={td}><strong>{r[nameKey]}</strong></td>
                <td style={td}>{r.charts}</td>
                <td style={{ ...td, fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</td>
                <td style={td}>{pct(r.clean_accuracy)}</td>
                <td style={td}>{pct(r.opportunity_accuracy)}</td>
                <td style={td}><ProcedureCell row={r} /></td>
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
          <tr>{['Batch', 'Specialty', 'Auditors', 'Charts', 'Audit Score', 'Procedure', showPdf ? '' : null].filter(Boolean).map(h => <th key={String(h)} style={th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.batch_id}>
              <td style={td}><strong>{r.name}</strong><div style={muted}>{r.status}</div></td>
              <td style={td}>{r.specialty}</td>
              <td style={td}>{r.auditors}</td>
              <td style={td}>{r.charts}</td>
              <td style={{ ...td, fontWeight: 800, color: tone(r.audit_score, threshold) }}>{pct(r.audit_score)}</td>
              <td style={td}><ProcedureCell row={r} /></td>
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

function Metric({ label, value, tone: color, sub }: {
  label: string; value: any; tone?: string; sub?: React.ReactNode
}) {
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
