import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, Copy, Download, Eye,
  Loader, Plus, RefreshCw, Shuffle, Upload,
} from 'lucide-react'
import {
  createAuditBatch, getAuditBatch, getAuditPlantings, listAuditBatches,
  regenerateAssignment, runAuditAllocation,
} from '../../api/auditorApi'
import { downloadCoderListTemplate, getCategories, getPoolPreview, parseCoderList } from '../../api'
import { CoderPicker } from '../../components/CoderPicker'
import s from './styles'

const AUDITABLE = ['IP-DRG', 'SDS', 'ED Facility', 'Surgery', 'ED Single Path', 'Ancillary']

const MODES = [
  { key: 'auto', name: 'Automatic', blurb: 'The system decides the mix, the charts and the errors.' },
  { key: 'guided', name: 'Guided', blurb: 'You set how many of each type; the system picks which charts.' },
  { key: 'manual', name: 'Hand-picked', blurb: 'You choose the charts. The system still builds the errors.' },
]

type View = 'list' | 'create' | 'detail'

type StatusFilter = 'open' | 'closed' | 'all'

/**
 * Ageing groups, matching the coder batch home. A flat newest-first list looks
 * fine at a dozen batches and becomes unreadable at a hundred; grouping by
 * when something was created is how a trainer actually thinks about their
 * work in progress.
 */
const GROUP_ORDER = ['This Week', 'Last Week', 'This Month', 'Older']

function ageGroup(created?: string) {
  if (!created) return 'Older'
  const d = new Date(created)
  const now = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
  const daysToMonday = (now.getDay() + 6) % 7
  if (diff <= daysToMonday) return 'This Week'
  if (diff <= daysToMonday + 7) return 'Last Week'
  if (diff <= now.getDate() - 1) return 'This Month'
  return 'Older'
}

export function AuditBatches({ trainer }: { trainer: string }) {
  const [view, setView] = useState<View>('list')
  const [batches, setBatches] = useState<Record<string, any>[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  // Open by default — closed batches are the record, not the work.
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open')
  // Groups start collapsed, so the page opens as a short index rather than a
  // wall of rows.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    try { setBatches((await listAuditBatches()).batches) }
    catch { toast.error('Could not load audit batches') }
  }, [])

  useEffect(() => { load() }, [load])

  if (view === 'create') {
    return <CreateAuditBatch trainer={trainer}
      onDone={id => { load(); setSelected(id); setView('detail') }}
      onCancel={() => setView('list')} />
  }
  if (view === 'detail' && selected !== null) {
    return <AuditBatchDetail batchId={selected} trainer={trainer}
      onBack={() => { load(); setView('list') }} />
  }

  const openCount = batches.filter(b => b.status === 'Open').length
  const closedCount = batches.length - openCount

  const sorted = [...batches].sort((a, b) =>
    String(b.created_at || '').localeCompare(String(a.created_at || ''))
    || (Number(b.id) - Number(a.id)))

  const term = search.trim().toLowerCase()
  const filtered = sorted.filter(b => {
    if (statusFilter === 'open' && b.status !== 'Open') return false
    if (statusFilter === 'closed' && b.status === 'Open') return false
    if (term && !String(b.name).toLowerCase().includes(term)
      && !String(b.specialty).toLowerCase().includes(term)) return false
    return true
  })

  const groups = GROUP_ORDER
    .map(label => ({ label, items: filtered.filter(b => ageGroup(b.created_at as string) === label) }))
    .filter(g => g.items.length)

  const TABS: { key: StatusFilter; label: string; count: number; color: string; bg: string }[] = [
    { key: 'open', label: 'Open', count: openCount, color: '#1d4ed8', bg: '#eff6ff' },
    { key: 'closed', label: 'Closed', count: closedCount, color: '#15803d', bg: '#f0fdf4' },
    { key: 'all', label: 'All', count: batches.length, color: '#374151', bg: '#f8fafc' },
  ]

  return (
    <div>
      <div style={s.rowBetween}>
        <div style={s.h1}>Audit Batches</div>
        <button style={s.primaryBtn} onClick={() => setView('create')}>
          <Plus size={15} /> New Audit Batch
        </button>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 16, flexWrap: 'wrap' }}>
        {TABS.map(t => {
          const on = statusFilter === t.key
          return (
            <button key={t.key} onClick={() => setStatusFilter(t.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7, padding: '6px 13px',
                borderRadius: 8, cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
                border: `1px solid ${on ? t.color : '#e5e7eb'}`,
                background: on ? t.bg : '#fff', color: on ? t.color : '#6b7280',
              }}>
              {t.label}
              <span style={{ fontSize: 11, fontWeight: 700, opacity: 0.8 }}>{t.count}</span>
            </button>
          )
        })}
        <input style={{ ...s.input, width: 220, marginLeft: 'auto' }}
          placeholder="Search by name or specialty…"
          value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {filtered.length === 0 ? (
        <div style={s.empty}>
          {batches.length === 0 ? 'No audit batches yet.'
            : `No ${statusFilter === 'all' ? '' : statusFilter} batches match.`}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 16 }}>
          {groups.map(({ label, items }) => {
            const isCollapsed = collapsed[label] !== false
            return (
              <div key={label}>
                <button style={s.groupHead}
                  onClick={() => setCollapsed(p => ({ ...p, [label]: p[label] === false }))}>
                  {isCollapsed ? <ChevronRight size={14} color="#9ca3af" />
                    : <ChevronDown size={14} color="#9ca3af" />}
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280' }}>{label}</span>
                  <span style={s.groupCount}>{items.length}</span>
                  <span style={{ flex: 1, height: 1, background: '#f3f4f6' }} />
                </button>
                {!isCollapsed && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
                    {items.map(b => (
                      <button key={b.id as number} style={s.listRow}
                        onClick={() => { setSelected(b.id as number); setView('detail') }}>
                        <span style={{ fontWeight: 700, fontSize: 14 }}>{b.name as string}</span>
                        <span style={s.chip}>{b.specialty as string}</span>
                        <span style={{
                          ...s.chip,
                          background: b.status === 'Open' ? '#eff6ff' : '#f3f4f6',
                          color: b.status === 'Open' ? '#1d4ed8' : '#6b7280',
                        }}>{b.status as string}</span>
                        {b.days_open != null && (
                          <span style={{
                            fontSize: 11, fontWeight: 600,
                            color: Number(b.days_open) > 14 ? '#d97706' : '#9ca3af',
                          }}>
                            {b.days_open as number}d open
                          </span>
                        )}
                        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#6b7280' }}>
                          {b.auditors as number} auditor(s) · {b.assigned as number} assigned ·{' '}
                          {b.scored as number} scored
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── create ───────────────────────────────────────────────────────────────────

function CreateAuditBatch({ trainer, onDone, onCancel }: {
  trainer: string; onDone: (id: number) => void; onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('IP-DRG')
  const [categories, setCategories] = useState<string[]>([])
  const [available, setAvailable] = useState<string[]>([])
  const [chartsPer, setChartsPer] = useState(5)
  const [mode, setMode] = useState('guided')
  const [cleanShare, setCleanShare] = useState(50)
  const [quotaClean, setQuotaClean] = useState(2)
  const [quotaManual, setQuotaManual] = useState(1)
  const [quotaAuto, setQuotaAuto] = useState(2)
  const [tier, setTier] = useState('')
  const [busy, setBusy] = useState(false)

  // Roster entry mirrors the coder batch screen exactly — same picker, same
  // Quick Add / Upload List toggle, same Excel template. Auditors and coders
  // are the same people in the same directory, so a second way of entering
  // them would only invite two spellings of one person.
  const [auditors, setAuditors] = useState<{ name: string; emp_id: string }[]>([])
  const [rosterMode, setRosterMode] = useState<'quick' | 'upload'>('quick')
  const [quickRow, setQuickRow] = useState({ name: '', emp_id: '' })
  const [parsing, setParsing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const [pool, setPool] = useState<{ total_matching: number; with_answer_key: number } | null>(null)

  useEffect(() => {
    getCategories(specialty).then(c => setAvailable(c || []))
      .catch(() => setAvailable([]))
  }, [specialty])

  useEffect(() => {
    getPoolPreview(specialty, categories.join(',') || undefined)
      .then(setPool).catch(() => setPool(null))
  }, [specialty, categories])

  function addQuick() {
    const name = quickRow.name.trim()
    const emp_id = quickRow.emp_id.trim()
    if (!name || !emp_id) return toast.error('Enter both name and Emp ID')
    if (auditors.some(a => a.emp_id === emp_id)) return toast.error('Emp ID already added')
    setAuditors(prev => [...prev, { name, emp_id }])
    setQuickRow({ name: '', emp_id: '' })
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setParsing(true)
    try {
      const parsed = await parseCoderList(file)
      setAuditors(parsed)
      if (!parsed.length) {
        toast.error('No usable rows found — check that Name and Emp ID are both filled in below the header row')
      } else {
        toast.success(`${parsed.length} auditor(s) loaded`)
      }
    } catch (err) {
      const e2 = err as { response?: { data?: { detail?: string } } }
      toast.error(e2?.response?.data?.detail || 'Failed to parse the list')
    } finally {
      setParsing(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const guidedTotal = quotaClean + quotaManual + quotaAuto
  // A chart with no answer key has no truth to introduce errors in, so it is
  // excluded from the pool rather than assigned clean.
  const gradable = pool?.with_answer_key ?? 0
  const needed = auditors.length * chartsPer
  const shortfall = Math.max(0, needed - gradable)

  async function create() {
    if (!name.trim()) return toast.error('Name the batch')
    if (!auditors.length) return toast.error('Add at least one auditor')
    setBusy(true)
    try {
      const res = await createAuditBatch({
        name: name.trim(), specialty, categories, difficulties: [],
        charts_per_auditor: chartsPer, auditors, created_by: trainer,
        allocation_mode: mode, clean_share: cleanShare,
        quota_clean: mode === 'guided' ? quotaClean : null,
        quota_manual: mode === 'guided' ? quotaManual : null,
        quota_auto: mode === 'guided' ? quotaAuto : null,
        difficulty_tier: tier || null,
      })
      if (res.warning) toast(res.warning, { icon: '⚠️', duration: 6000 })
      toast.success('Audit batch created')
      onDone(res.batch_id)
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Could not create the batch')
    }
    setBusy(false)
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <button style={s.backBtn} onClick={onCancel}><ChevronLeft size={14} /> Back</button>
      <div style={s.h1}>New Audit Batch</div>

      <Field label="Batch name">
        <input style={s.input} value={name} onChange={e => setName(e.target.value)}
          placeholder="e.g. IP-DRG audit — August wave 1" />
      </Field>

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <Field label="Specialty">
          <select style={s.input} value={specialty} onChange={e => { setSpecialty(e.target.value); setCategories([]) }}>
            {AUDITABLE.map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
        <Field label="Charts per auditor">
          <input style={{ ...s.input, width: 90 }} type="number" min={1} value={chartsPer}
            onChange={e => setChartsPer(parseInt(e.target.value) || 1)} />
        </Field>
        <Field label="Difficulty of errors">
          <select style={s.input} value={tier} onChange={e => setTier(e.target.value)}>
            <option value="">Balanced</option>
            <option value="foundational">Foundational</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
        </Field>
      </div>
      {chartsPer < 5 && (
        <div style={s.warnBox}>
          <AlertTriangle size={14} color="#d97706" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Sessions this short report a score but withhold a pass/fail verdict — chart
            scores are quantised by error count, so a verdict on a handful of
            opportunities would be noise.</span>
        </div>
      )}

      {available.length > 0 && (
        <Field label="Categories (blank means all)">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {available.map(c => (
              <button key={c} style={{ ...s.toggleChip, ...(categories.includes(c) ? s.toggleChipOn : {}) }}
                onClick={() => setCategories(p => p.includes(c) ? p.filter(x => x !== c) : [...p, c])}>
                {c}
              </button>
            ))}
          </div>
        </Field>
      )}

      <Field label="How charts are chosen">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {MODES.map(m => (
            <button key={m.key} onClick={() => setMode(m.key)}
              style={{ ...s.modeCard, ...(mode === m.key ? s.modeCardOn : {}) }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{m.name}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>{m.blurb}</div>
            </button>
          ))}
        </div>
      </Field>

      {mode === 'guided' ? (
        <Field label="How many of each, per auditor">
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <Num label="Clean" value={quotaClean} onChange={setQuotaClean} />
            <Num label="Yours" value={quotaManual} onChange={setQuotaManual} />
            <Num label="System" value={quotaAuto} onChange={setQuotaAuto} />
            <span style={{ fontSize: 12, color: guidedTotal === chartsPer ? '#059669' : '#d97706' }}>
              {guidedTotal} of {chartsPer}
              {guidedTotal < chartsPer && ` — the remaining ${chartsPer - guidedTotal} will be system-generated`}
            </span>
          </div>
        </Field>
      ) : (
        <Field label="Share of charts with nothing wrong">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <input type="range" min={0} max={90} step={10} value={cleanShare}
              onChange={e => setCleanShare(parseInt(e.target.value))} style={{ flex: 1, maxWidth: 260 }} />
            <span style={{ fontWeight: 700, fontSize: 14 }}>{cleanShare}%</span>
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              {Math.floor(chartsPer * cleanShare / 100)} of {chartsPer} charts
            </span>
          </div>
          <div style={s.note}>
            Rounded down, so every session keeps at least one chart with something to find.
            Clean charts measure whether an auditor can leave a correct claim alone — they
            are drawn per auditor, and never the same chart numbers twice.
          </div>
        </Field>
      )}

      {pool && (
        <div style={{
          ...s.infoBox, marginBottom: 16,
          ...(shortfall > 0 ? { background: '#fffbeb', borderColor: '#fde68a', color: '#92400e' } : {}),
        }}>
          <div>
            <strong>Pool preview:</strong> {pool.total_matching} matching chart(s)
            {' · '}{pool.with_answer_key} with answer keys
          </div>
          {gradable === 0 ? (
            <div style={{ color: '#dc2626', marginTop: 6, fontWeight: 600 }}>
              ⚠ No chart here has an answer key, so there is nothing to introduce errors in.
              Upload keys before running allocation.
            </div>
          ) : auditors.length === 0 ? (
            <div style={{ marginTop: 6, color: '#6b7280' }}>
              Add auditors below to see whether the pool covers them.
            </div>
          ) : shortfall > 0 ? (
            <div style={{ marginTop: 6, fontWeight: 600 }}>
              ⚠ Short by {shortfall}. {auditors.length} auditor{auditors.length === 1 ? '' : 's'} ×{' '}
              {chartsPer} chart{chartsPer === 1 ? '' : 's'} = <strong>{needed} needed</strong>,{' '}
              {gradable} available. Widen the filters or add keys — allocation will otherwise
              give everyone what it can and stop short.
            </div>
          ) : (
            <div style={{ marginTop: 6, color: '#15803d', fontWeight: 600 }}>
              ✓ {auditors.length} auditor{auditors.length === 1 ? '' : 's'} × {chartsPer}{' '}
              chart{chartsPer === 1 ? '' : 's'} = {needed} needed. Pool is sufficient.
            </div>
          )}
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div style={s.label}>Auditors *</div>
          <div style={s.modeToggle}>
            <button style={rosterMode === 'quick' ? s.modeTabActive : s.modeTab}
              onClick={() => setRosterMode('quick')}>Quick Add</button>
            <button style={rosterMode === 'upload' ? s.modeTabActive : s.modeTab}
              onClick={() => setRosterMode('upload')}>Upload List</button>
          </div>
        </div>

        {rosterMode === 'quick' && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            {/* Picking someone already in the directory carries their Emp ID
                across, so a new spelling does not fork the history they have. */}
            <div style={{ flex: 1 }}>
              <CoderPicker
                value={quickRow.name}
                width="100%"
                allowFreeText
                placeholder="Auditor name — search or type a new one"
                onSelect={(name, empId) =>
                  setQuickRow(r => ({ ...r, name, emp_id: empId || r.emp_id }))}
              />
            </div>
            <input style={{ ...s.input, width: 130 }} placeholder="Emp ID"
              value={quickRow.emp_id}
              onChange={e => setQuickRow(r => ({ ...r, emp_id: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && addQuick()} />
            <button style={s.ghostBtn} onClick={addQuick}>+ Add</button>
          </div>
        )}

        {rosterMode === 'upload' && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <button style={s.ghostBtn} onClick={downloadCoderListTemplate}>
              <Download size={15} /> Download Template
            </button>
            <label style={{ ...s.primaryBtn, opacity: parsing ? 0.6 : 1 }}>
              {parsing ? <><Loader size={14} /> Parsing…</> : <><Upload size={15} /> Upload Filled List</>}
              <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                onChange={handleUpload} disabled={parsing} />
            </label>
          </div>
        )}

        {auditors.length > 0 && (
          <>
            <div style={s.rosterTable}>
              <div style={s.rosterHeader}><span>Auditor Name</span><span>Emp ID</span><span /></div>
              {auditors.map((a, i) => (
                <div key={i} style={s.rosterRow}>
                  <span>{a.name}</span>
                  <span style={{ fontWeight: 700, color: '#9333ea' }}>{a.emp_id}</span>
                  <button style={s.removeRow}
                    onClick={() => setAuditors(prev => prev.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
              <span style={{ fontSize: 11, color: '#9ca3af' }}>
                {auditors.length} auditor{auditors.length !== 1 ? 's' : ''} ready
              </span>
              <button
                style={{ ...s.ghostBtn, fontSize: 12, padding: '4px 10px', color: '#dc2626', borderColor: '#fca5a5' }}
                onClick={() => setAuditors([])}>Clear all</button>
            </div>
          </>
        )}
      </div>

      {/* Cancel sits beside the primary action as well as at the top, matching
          the coder batch screen — someone who has scrolled to the bottom of a
          long form should not have to scroll back up to abandon it. */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={create}>
          {busy ? 'Creating…' : 'Create Audit Batch'}
        </button>
        <button style={{ ...s.ghostBtn, opacity: busy ? 0.5 : 1 }} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── detail ───────────────────────────────────────────────────────────────────

function AuditBatchDetail({ batchId, trainer, onBack }: {
  batchId: number; trainer: string; onBack: () => void
}) {
  const [batch, setBatch] = useState<any>(null)
  const [errors, setPlantings] = useState<any[]>([])
  const [showPlantings, setShowPlantings] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setBatch(await getAuditBatch(batchId))
      setPlantings((await getAuditPlantings(batchId)).errors)
    } catch { toast.error('Could not load the batch') }
  }, [batchId])

  useEffect(() => { load() }, [load])

  async function allocate() {
    setBusy(true)
    try {
      const res = await runAuditAllocation(batchId, { run_by: trainer })
      toast.success(`Allocated ${res.charts_allocated} chart(s)`)
      ;(res.pool_notes || []).forEach((n: string) => toast(n, { icon: 'ℹ️', duration: 6000 }))
      load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Allocation failed')
    }
    setBusy(false)
  }

  async function reroll(assignmentId: number) {
    try {
      await regenerateAssignment(assignmentId, trainer)
      toast.success('Errors rerolled')
      load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Could not reroll')
    }
  }

  if (!batch) return <div style={s.empty}>Loading…</div>

  const codes = Object.values(batch.tokens_by_cycle || {}).flat() as any[]

  return (
    <div>
      <button style={s.backBtn} onClick={onBack}><ChevronLeft size={14} /> All audit batches</button>
      <div style={s.rowBetween}>
        <div>
          <div style={s.h1}>{batch.name}</div>
          <div style={s.sub}>
            {batch.specialty} · {batch.auditors.length} auditor(s) · {batch.allocation_mode} ·{' '}
            {batch.status}
          </div>
        </div>
        {batch.status === 'Open' && (
          <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={allocate}>
            <Shuffle size={15} /> {busy ? 'Allocating…' : 'Run allocation'}
          </button>
        )}
      </div>

      {codes.length > 0 && (
        <Panel title="Access codes">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {codes.map((c, i) => (
              <div key={i} style={s.codeRow}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{c.auditor_name}</span>
                <code style={s.codeChip}>{c.token}</code>
                <button style={s.iconBtn}
                  onClick={() => { navigator.clipboard.writeText(c.token); toast.success('Copied') }}>
                  <Copy size={13} />
                </button>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#6b7280' }}>{c.status}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {errors.length > 0 && (
        <Panel
          title={`Errors introduced (${errors.length} chart${errors.length !== 1 ? 's' : ''})`}
          right={
            <button style={s.linkBtn} onClick={() => setShowPlantings(v => !v)}>
              <Eye size={13} /> {showPlantings ? 'Hide' : 'Show'}
            </button>
          }
        >
          <div style={s.note}>
            Visible to you only. Reroll anything that looks wrong — possible until the
            auditor opens the chart, after which the claim is what they saw.
          </div>
          {showPlantings && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
              {errors.map(p => (
                <div key={p.assignment_id} style={s.errorRow}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{p.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{p.auditor_name}</span>
                    <span style={{ ...s.chip, background: SOURCE_BG[p.source], color: SOURCE_FG[p.source] }}>
                      {p.source === 'Clean' ? 'Clean — no errors' : p.source}
                    </span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>
                      {p.ground_truth.length} error(s)
                    </span>
                    {p.locked
                      ? <span style={{ ...s.chip, background: '#f3f4f6', color: '#6b7280' }}>Opened — locked</span>
                      : p.source !== 'Clean' && (
                        <button style={{ ...s.linkBtn, marginLeft: 'auto' }}
                          onClick={() => reroll(p.assignment_id)}>
                          <RefreshCw size={12} /> Reroll
                        </button>
                      )}
                  </div>
                  {p.ground_truth.length > 0 && (
                    <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {p.ground_truth.map((g: any, i: number) => (
                        <div key={i} style={{ fontSize: 11.5, color: '#4b5563' }}>
                          • <strong>{g.action}</strong> {g.section}
                          {g.field && g.field !== 'code' ? ` ${g.field}` : ''}
                          {g.line !== undefined && g.action !== 'Add' ? ` line ${g.line + 1}` : ''}
                          {' — '}
                          {g.action === 'Add' ? g.correct_value
                            : g.action === 'Delete' ? g.claim_value
                              : `${g.claim_value} should be ${g.correct_value}`}
                          {g.pcs_character ? ` (${g.pcs_character})` : ''}
                          {g.origin === 'observed' && (
                            <span style={s.observedTag}>
                              seen in {g.observed_coders} coder submission(s)
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      <Panel title="Assignments">
        {Object.keys(batch.assignments).length === 0 ? (
          <div style={s.empty}>Nothing allocated yet.</div>
        ) : Object.entries(batch.assignments).map(([auditor, rows]) => (
          <div key={auditor} style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>{auditor}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(rows as any[]).map(r => (
                <span key={r.assignment_id} style={{
                  ...s.chip,
                  background: r.scored ? '#d1fae5' : r.opened ? '#fef3c7' : '#f3f4f6',
                  color: r.scored ? '#059669' : r.opened ? '#b45309' : '#6b7280',
                }}>
                  {r.chart_number}
                </span>
              ))}
            </div>
          </div>
        ))}
      </Panel>
    </div>
  )
}

const SOURCE_BG: Record<string, string> = { Clean: '#eff6ff', Manual: '#f5f3ff', Auto: '#f0fdf4' }
const SOURCE_FG: Record<string, string> = { Clean: '#2563eb', Manual: '#7c3aed', Auto: '#059669' }

function Panel({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={s.panel}>
      <div style={s.panelHead}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span>
        {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
      </div>
      <div style={{ padding: '12px 16px' }}>{children}</div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={s.label}>{label}</div>
      {children}
    </div>
  )
}

function Num({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 3 }}>{label}</div>
      <input style={{ ...s.input, width: 74 }} type="number" min={0} value={value}
        onChange={e => onChange(Math.max(0, parseInt(e.target.value) || 0))} />
    </div>
  )
}
