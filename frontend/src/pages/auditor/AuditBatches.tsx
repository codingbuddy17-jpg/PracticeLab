import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  AlertTriangle, ChevronLeft, Copy, Eye, Plus, RefreshCw, Shuffle,
} from 'lucide-react'
import {
  createAuditBatch, getAuditBatch, getAuditPlantings, listAuditBatches,
  regenerateAssignment, runAuditAllocation,
} from '../../api/auditorApi'
import { getCategories } from '../../api'
import s from './styles'

const AUDITABLE = ['IP-DRG', 'SDS', 'ED Facility', 'Surgery', 'ED Single Path', 'Ancillary']

const MODES = [
  { key: 'auto', name: 'Automatic', blurb: 'The system decides the mix, the charts and the plantings.' },
  { key: 'guided', name: 'Guided', blurb: 'You set how many of each type; the system picks which charts.' },
  { key: 'manual', name: 'Hand-picked', blurb: 'You choose the charts. The system still builds the plantings.' },
]

type View = 'list' | 'create' | 'detail'

export function AuditBatches({ trainer }: { trainer: string }) {
  const [view, setView] = useState<View>('list')
  const [batches, setBatches] = useState<Record<string, any>[]>([])
  const [selected, setSelected] = useState<number | null>(null)

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

  return (
    <div>
      <div style={s.rowBetween}>
        <div>
          <div style={s.h1}>Audit Batches</div>
          <div style={s.sub}>Charts arrive pre-coded. Auditors find and fix what is wrong.</div>
        </div>
        <button style={s.primaryBtn} onClick={() => setView('create')}>
          <Plus size={15} /> New Audit Batch
        </button>
      </div>

      {batches.length === 0 ? (
        <div style={s.empty}>No audit batches yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 18 }}>
          {batches.map(b => (
            <button key={b.id as number} style={s.listRow}
              onClick={() => { setSelected(b.id as number); setView('detail') }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{b.name as string}</span>
              <span style={s.chip}>{b.specialty as string}</span>
              <span style={{ ...s.chip, background: b.status === 'Open' ? '#d1fae5' : '#f3f4f6',
                             color: b.status === 'Open' ? '#059669' : '#6b7280' }}>
                {b.status as string}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: 12, color: '#6b7280' }}>
                {b.auditors as number} auditor(s) · {b.assigned as number} assigned · {b.scored as number} scored
              </span>
            </button>
          ))}
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
  const [roster, setRoster] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getCategories(specialty).then(c => setAvailable(c || []))
      .catch(() => setAvailable([]))
  }, [specialty])

  const auditors = roster.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
    const [n, e] = line.split(',').map(x => (x || '').trim())
    return { name: n, emp_id: e || '' }
  })

  const guidedTotal = quotaClean + quotaManual + quotaAuto

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
        <Field label="Difficulty of plantings">
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
            scores are quantised by planting count, so a verdict on a handful of
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
            <Num label="Your plantings" value={quotaManual} onChange={setQuotaManual} />
            <Num label="System plantings" value={quotaAuto} onChange={setQuotaAuto} />
            <span style={{ fontSize: 12, color: guidedTotal === chartsPer ? '#059669' : '#d97706' }}>
              {guidedTotal} of {chartsPer}
              {guidedTotal < chartsPer && ` — the remaining ${chartsPer - guidedTotal} will be system-planted`}
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

      <Field label="Auditors — one per line, optionally “Name, EmpID”">
        <textarea style={{ ...s.input, height: 110, fontFamily: 'system-ui' }}
          value={roster} onChange={e => setRoster(e.target.value)}
          placeholder={'Asha R, E1024\nBo T, E1188'} />
        <div style={s.note}>{auditors.length} auditor(s)</div>
      </Field>

      <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={create}>
        {busy ? 'Creating…' : 'Create Audit Batch'}
      </button>
    </div>
  )
}

// ── detail ───────────────────────────────────────────────────────────────────

function AuditBatchDetail({ batchId, trainer, onBack }: {
  batchId: number; trainer: string; onBack: () => void
}) {
  const [batch, setBatch] = useState<any>(null)
  const [plantings, setPlantings] = useState<any[]>([])
  const [showPlantings, setShowPlantings] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setBatch(await getAuditBatch(batchId))
      setPlantings((await getAuditPlantings(batchId)).plantings)
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
      toast.success('Plantings rerolled')
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

      {plantings.length > 0 && (
        <Panel
          title={`What was planted (${plantings.length} chart${plantings.length !== 1 ? 's' : ''})`}
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
              {plantings.map(p => (
                <div key={p.assignment_id} style={s.plantRow}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{p.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{p.auditor_name}</span>
                    <span style={{ ...s.chip, background: SOURCE_BG[p.source], color: SOURCE_FG[p.source] }}>
                      {p.source === 'Clean' ? 'Clean — nothing planted' : p.source}
                    </span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>
                      {p.ground_truth.length} planting(s)
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
