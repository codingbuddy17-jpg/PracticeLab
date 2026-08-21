import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ChevronDown, ChevronLeft, ChevronRight, Download, Eye, Plus, Save, Trash2, X,
} from 'lucide-react'
import {
  createAuditKeySet, deleteAuditKeySet, downloadAuditKeys, getAuditKeyStatus,
  getAuditKeysForChart, getUncuratedCharts, listAuditKeySets, previewAuditKeySet,
  setAuditCcBoundary, updateAuditKeySet, Finding,
} from '../../api/auditorApi'
import { ISSUE_COLORS } from '../practicelab/shared'
import s from './styles'
import { AUDITABLE } from './constants'
import { CodeCaption } from '../../components/CodeCaption'
import { useCodeDescriptions } from '../../hooks/useCodeDescriptions'

/**
 * The trainer's audit keys.
 *
 * A set records what the AUDITOR must find, not what the system should break.
 * That direction is deliberate: it is the same shape the generator emits and
 * the same shape an auditor's own findings take, so scoring never translates
 * between two vocabularies — and a trainer authoring a set is writing the
 * answer rather than the sabotage.
 */

const SECTION_LABEL: Record<string, string> = {
  PDx: 'Principal Dx', SDx: 'Secondary Dx', PCS: 'PCS', CPT: 'CPT',
  MDM: 'MDM',
}


/**
 * Laid out like the coder Answer Keys screen: pick a specialty, see coverage,
 * work the table. The gap list below it is the point of the page — it says
 * which charts are still running on generated errors and could carry authored
 * ones instead.
 */
export function AuditKeys({ trainer }: { trainer: string }) {
  // Deep-linkable: Chart Signals sends a trainer straight to the errors
  // authored for a chart it has flagged, because the next question after "this
  // chart keeps being missed" is always "is the key wrong?". Reading it from
  // the URL rather than a prop keeps the link shareable and survives a reload.
  const [params, setParams] = useSearchParams()
  const linkedChart = Number(params.get('chart')) || null
  const linkedSpecialty = params.get('specialty')

  const [specialty, setSpecialty] = useState(linkedSpecialty || 'IP-DRG')
  const [chartId, setChartId] = useState<number | null>(linkedChart)
  const [sets, setSets] = useState<Record<string, any>[]>([])
  const [status, setStatus] = useState<any>(null)
  const [uncurated, setUncurated] = useState<Record<string, any>[]>([])
  const [showUncurated, setShowUncurated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [exportPass, setExportPass] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [k, st] = await Promise.all([
        listAuditKeySets(specialty), getAuditKeyStatus(specialty),
      ])
      setSets(k.sets)
      setStatus(st)
    } catch { toast.error('Could not load audit keys') }
    finally { setLoading(false) }
  }, [specialty])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!showUncurated) return
    getUncuratedCharts(specialty).then(r => setUncurated(r.charts)).catch(() => setUncurated([]))
  }, [showUncurated, specialty, sets.length])

  if (chartId !== null) {
    return <ChartKeyEditor chartId={chartId} trainer={trainer}
      onBack={() => {
        setChartId(null)
        // Drop the deep link too, or Back reopens the editor it just closed.
        if (params.get('chart')) setParams({}, { replace: true })
        load()
      }} />
  }

  const COLS = '130px 1fr 90px 1fr 150px'

  return (
    <div>
      <div style={s.h1}>Audit Keys</div>
      <p style={s.helpText}>
        Errors you author here are permanent and reusable. A chart without a set still
        gets audited — the system generates its errors instead — so this is where you
        curate the charts worth teaching from, not a prerequisite for running a batch.
      </p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 16, marginBottom: 16 }}>
        <div>
          <label style={s.label}>Specialty type</label>
          <select style={s.select} value={specialty} onChange={e => setSpecialty(e.target.value)}>
            {AUDITABLE.map(x => <option key={x}>{x}</option>)}
          </select>
        </div>
        <input style={{ ...s.input, width: 170 }} type="password" placeholder="Passphrase"
          value={exportPass} onChange={e => setExportPass(e.target.value)} />
        <button style={s.outlineBtn}
          title="This file contains every authored error, so it needs the passphrase"
          onClick={() => exportPass.trim()
            ? downloadAuditKeys(exportPass, specialty)
            : toast.error('Passphrase required — this export is the answers')}>
          <Download size={15} /> Export Keys (.xlsx)
        </button>
      </div>

      {status && (
        <div style={{ ...s.statsRow, marginBottom: 20 }}>
          <div style={s.statCard}>
            <div style={s.statValue}>{status.auditable}</div>
            <div style={s.statLabel}>Auditable Charts</div>
          </div>
          <div style={s.statCard}>
            <div style={{ ...s.statValue, color: '#16a34a' }}>{status.curated}</div>
            <div style={s.statLabel}>With Authored Errors</div>
          </div>
          <div style={s.statCard}>
            <div style={{ ...s.statValue, color: '#d97706' }}>{status.uncurated}</div>
            <div style={s.statLabel}>System-Generated Only</div>
          </div>
          <div style={s.statCard}>
            <div style={{ ...s.statValue, color: status.no_answer_key ? '#dc2626' : '#9ca3af' }}>
              {status.no_answer_key}
            </div>
            <div style={s.statLabel}>Not Auditable</div>
          </div>
        </div>
      )}

      {status?.no_answer_key > 0 && (
        <div style={{ ...s.warnBox, marginBottom: 16 }}>
          <strong>{status.no_answer_key} chart(s) in {specialty} have no answer key</strong>, so
          they can be neither curated here nor allocated for audit — there is no truth to
          introduce errors into. Upload their answer keys first.
        </div>
      )}

      {loading ? (
        <div style={s.empty}>Loading…</div>
      ) : sets.length === 0 ? (
        <div style={s.emptyState}>
          No authored errors for {specialty} yet. Every chart in this specialty is
          audited with system-generated errors.
        </div>
      ) : (
        <div style={s.table}>
          <div style={{ ...s.tableHeader, gridTemplateColumns: COLS }}>
            <span>Chart</span><span>Version</span><span>Errors</span>
            <span>Authored By</span><span />
          </div>
          {sets.map((k, i) => (
            <div key={k.id as number} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
              style={{ ...s.tableRow, gridTemplateColumns: COLS }}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{k.chart_number as string}</span>
              <span style={{ fontSize: 12.5 }}>
                {k.name as string}
                {k.always_plant ? <span style={{ ...s.tag, marginLeft: 6, background: '#fef2f2', color: '#dc2626' }}>always used</span> : null}
                {k.query_expected !== null && k.query_expected !== undefined
                  ? <span style={{ ...s.tag, marginLeft: 6, background: '#fffbeb', color: '#b45309' }}>
                      query {k.query_expected ? 'expected' : 'not needed'}
                    </span>
                  : null}
              </span>
              <span style={{ fontSize: 12 }}>{k.planting_count as number}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{k.authored_by as string}</span>
              <span style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                <button style={{ ...s.outlineBtn, padding: '4px 10px', fontSize: 12 }}
                  title={`Edit the errors on ${k.chart_number}`}
                  onClick={() => setChartId(k.chart_id as number)}>
                  Edit
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* The curation to-do list — the equivalent of "charts without keys" on
          the coder screen, and the reason to come back to this page. */}
      <div style={{ marginTop: 24 }}>
        <button style={s.groupHead} onClick={() => setShowUncurated(v => !v)}>
          {showUncurated ? <ChevronDown size={14} color="#9ca3af" />
            : <ChevronRight size={14} color="#9ca3af" />}
          <span style={{ fontSize: 13, fontWeight: 700, color: '#374151' }}>
            Charts running on generated errors
          </span>
          {status && <span style={s.groupCount}>{status.uncurated}</span>}
          <span style={{ flex: 1, height: 1, background: '#f3f4f6' }} />
        </button>
        {showUncurated && (
          uncurated.length === 0 ? (
            <div style={s.emptyState}>Every auditable chart in {specialty} has authored errors.</div>
          ) : (
            <div style={s.table}>
              <div style={{ ...s.tableHeader, gridTemplateColumns: '130px 1fr 1fr 150px' }}>
                <span>Chart</span><span>Category</span><span>Difficulty</span><span /></div>
              {uncurated.map((c, i) => (
                <div key={c.chart_id as number} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'}
                  style={{ ...s.tableRow, gridTemplateColumns: '130px 1fr 1fr 150px' }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{c.chart_number as string}</span>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>{(c.category as string) || '—'}</span>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>{(c.difficulty as string) || '—'}</span>
                  <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button style={{ ...s.outlineBtn, padding: '4px 10px', fontSize: 12 }}
                      onClick={() => setChartId(c.chart_id as number)}>
                      <Plus size={13} /> Author errors
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  )
}

// ── one chart ────────────────────────────────────────────────────────────────

function ChartKeyEditor({ chartId, trainer, onBack }: {
  chartId: number; trainer: string; onBack: () => void
}) {
  const [data, setData] = useState<any>(null)
  const [editing, setEditing] = useState<any>(null)
  const [name, setName] = useState('')
  const [mutations, setMutations] = useState<Finding[]>([])
  const [queryExpected, setQueryExpected] = useState<boolean | null>(null)
  const [queryRationale, setQueryRationale] = useState('')
  const [alwaysPlant, setAlwaysPlant] = useState(false)
  const [passphrase, setPassphrase] = useState('')
  const [preview, setPreview] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [ccBoundary, setCcBoundary] = useState<string | null>(null)

  /**
   * Mark, or unmark, this chart as a close call on critical care.
   *
   * Passphrase-gated like everything else that changes what auditors will be
   * asked. The checkbox reflects what the server accepted rather than what was
   * clicked — a refusal must not leave the box looking set.
   */
  async function saveCcBoundary(value: string) {
    if (!passphrase.trim()) {
      toast.error('Passphrase required to change what auditors are asked')
      return
    }
    try {
      const res = await setAuditCcBoundary(chartId, value, passphrase)
      setCcBoundary(res.cc_boundary)
      toast.success(res.cc_boundary
        ? 'Marked as a close call — the 99285 vs 99291 question can now be asked'
        : 'Mark removed')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not save')
    }
  }

  const load = useCallback(async () => {
    try {
      const fresh = await getAuditKeysForChart(chartId)
      setData(fresh)
      setCcBoundary(fresh.cc_boundary ?? null)
    }
    catch { toast.error('Could not load this chart') }
  }, [chartId])
  useEffect(() => { load() }, [load])

  function startNew() {
    setEditing({ id: null })
    setName(''); setMutations([]); setQueryExpected(null)
    setQueryRationale(''); setAlwaysPlant(false); setPreview(null)
  }

  function startEdit(k: any) {
    setEditing(k)
    setName(k.name); setMutations(k.mutations || [])
    setQueryExpected(k.query_expected); setQueryRationale(k.query_rationale || '')
    setAlwaysPlant(!!k.always_plant); setPreview(null)
  }

  async function runPreview() {
    try {
      const res = await previewAuditKeySet(chartId, mutations)
      setPreview(res)
      if (res.warning) toast(res.warning, { icon: '⚠️', duration: 6000 })
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Preview failed')
    }
  }

  async function save() {
    if (!name.trim()) return toast.error('Give this version a name — one chart can carry several')
    if (!passphrase.trim()) return toast.error('Passphrase required')
    setBusy(true)
    const payload = {
      name: name.trim(), mutations, query_expected: queryExpected,
      query_rationale: queryRationale || null, always_plant: alwaysPlant,
      notes: null, authored_by: trainer, passphrase,
    }
    try {
      if (editing?.id) await updateAuditKeySet(editing.id, payload)
      else await createAuditKeySet(chartId, payload)
      toast.success(editing?.id ? 'Set updated — future allocations only' : 'Set saved')
      setEditing(null); load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Could not save')
    }
    setBusy(false)
  }

  async function remove(k: any) {
    if (!passphrase.trim()) return toast.error('Passphrase required to delete')
    try {
      await deleteAuditKeySet(k.id, passphrase)
      toast.success('Deleted — assignments already made keep their copy')
      load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Could not delete')
    }
  }

  if (!data) return <div style={s.empty}>Loading…</div>

  const atCap = data.sets.length >= (data.max_versions || 3)
  // Everything except the one being edited — comparing a version to itself
  // tells a trainer nothing.
  const others = editing
    ? data.sets.filter((x: any) => x.id !== editing.id)
    : data.sets
  const key = data.answer_key
  const sections: string[] = (data.form?.sections || []).map((x: any) => x.key)
  // Only ED charts can carry the 99285/99291 question, so the control only
  // appears where it means something.
  const edCodes = new Set(['99281', '99282', '99283', '99284', '99285', '99291', '99292'])
  const isEdChart = (key?.cpt || []).some((c: any) =>
    edCodes.has(String(c?.code || '').trim().toUpperCase()))

  return (
    <div style={{ maxWidth: 900 }}>
      <button style={s.backBtn} onClick={onBack}><ChevronLeft size={14} /> Audit Keys</button>
      <div style={s.rowBetween}>
        <div>
          <div style={s.h1}>{data.chart_number}</div>
          <div style={s.sub}>{data.specialty}</div>
          {/* Whether the generator may ask the hardest question in the ED on
              this chart. Only a trainer who has read it can say — an answer
              key states the right code, not whether the call was a close one.
              Left unmarked, the swap is never planted. */}
          {isEdChart && (
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 7, marginTop: 8, fontSize: 12, color: '#374151', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={ccBoundary === 'borderline'}
                onChange={e => saveCcBoundary(e.target.checked ? 'borderline' : '')}
              />
              <span>
                Critical care is a close call on this chart
                <span style={{ color: '#9ca3af' }}>
                  {' '}— lets the generator ask 99285 vs 99291
                </span>
              </span>
            </label>
          )}
        </div>
        {!editing && data.has_answer_key && data.auditable && (
          atCap ? (
            <span style={{ fontSize: 12, color: '#92400e', maxWidth: 280, textAlign: 'right' }}>
              At the limit of {data.max_versions} versions — edit or delete one to add another.
            </span>
          ) : (
            <button style={s.primaryBtn} onClick={startNew}>
              <Plus size={15} /> New version ({data.sets.length} of {data.max_versions})
            </button>
          )
        )}
      </div>

      {!data.auditable && (
        <div style={s.warnBox}>
          This specialty cannot be audited — Edits &amp; Denials are rubric-graded with no
          coded key to introduce errors in, and E/M needs its own audit design.
        </div>
      )}
      {!data.has_answer_key && (
        <div style={s.warnBox}>
          This chart has no answer key, so there is no truth to introduce errors in.
        </div>
      )}

      {key && (
        <div style={s.panel}>
          <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>Answer key</span></div>
          <div style={{ padding: '12px 16px', fontSize: 12.5, color: '#374151', lineHeight: 1.8 }}>
            <div><strong>PDx</strong> <code>{key.pdx_code || '—'}</code> {key.pdx_poa && `(POA ${key.pdx_poa})`}</div>
            <div><strong>SDx</strong> {(key.sdx || []).map((r: any, i: number) =>
              <code key={i} style={{ marginRight: 6 }}>{r.code}{r.ccmcc && r.ccmcc !== '-' ? `·${r.ccmcc}` : ''}</code>) || '—'}</div>
            {(key.pcs || []).length > 0 && <div><strong>PCS</strong> {key.pcs.map((r: any, i: number) => <code key={i} style={{ marginRight: 6 }}>{r.code}</code>)}</div>}
            {(key.cpt || []).length > 0 && <div><strong>CPT</strong> {key.cpt.map((r: any, i: number) => <code key={i} style={{ marginRight: 6 }}>{r.code}{r.modifier ? `-${r.modifier}` : ''}</code>)}</div>}
          </div>
        </div>
      )}

      {editing ? (
        <div style={s.panel}>
          <div style={s.panelHead}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>
              {editing.id ? 'Edit version' : 'New version'}
            </span>
            <button style={{ ...s.iconBtn, marginLeft: 'auto' }} onClick={() => setEditing(null)}>
              <X size={15} />
            </button>
          </div>
          <div style={{ padding: '14px 16px' }}>
            <div style={s.infoBox}>
              Mark what should be <strong>wrong</strong> on the claim this auditor receives.
              Everything you mark here is something they have to find.
            </div>

            {/* What is already on this chart, while you name the new one. A
                trainer naming a version blind is how two of them end up
                describing the same errors. */}
            {others.length > 0 && (
              <div style={{ ...s.infoBox, marginTop: 14 }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>
                  Already on {data.chart_number}:
                </div>
                {others.map((o: any) => (
                  <div key={o.id} style={{ fontSize: 12 }}>
                    • <strong>{o.name}</strong> — {o.planting_count} error(s)
                    {(o.mutations || []).length > 0 && (
                      <span style={{ color: '#6b7280' }}>
                        {' '}({(o.mutations || []).map((m: any) =>
                          `${m.action} ${m.section}`).join(', ')})
                      </span>
                    )}
                  </div>
                ))}
                <div style={{ fontSize: 11.5, marginTop: 4 }}>
                  Make this one different — an auditor who meets the chart again should
                  face something they have not already worked through.
                </div>
              </div>
            )}

            <div style={{ marginTop: 14, marginBottom: 12 }}>
              <div style={s.label}>Name this version</div>
              <input style={{ ...s.input, maxWidth: 360 }} value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Missed CC/MCC · Wrong root operation · Foundational" />
              <div style={s.note}>
                One chart can carry several versions — the same chart broken in different
                ways. An auditor who meets it again is given a version they have not seen,
                so the chart can be reused without testing their memory.
              </div>
            </div>

            {/* Direct manipulation of the answer key rather than abstract
                form rows. You act on the code you can see, so there is no line
                number to get wrong and no way to name a code the chart does not
                have. Colours are the app's existing ISSUE_COLORS, so an error
                marked here reads the same as the equivalent coder mistake in
                the results and analytics screens. */}
            <div style={s.label}>Mark the errors on this chart</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 8 }}>
              {(data.form?.sections || []).map((spec: any) => (
                <KeySection key={spec.key} spec={spec} answerKey={key}
                  mutations={mutations} setMutations={setMutations} />
              ))}
            </div>

            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 12 }}>
              {ACTION_LEGEND.map(a => (
                <span key={a.action} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: '#6b7280' }}>
                  <span style={{ width: 9, height: 9, borderRadius: 2, background: a.color, display: 'inline-block' }} />
                  <strong style={{ color: a.color }}>{a.action}</strong> — {a.blurb}
                </span>
              ))}
            </div>
            <div style={s.note}>
              {mutations.length === 0
                ? 'No errors yet. A set with none is a correct claim that still needs a query.'
                : `${mutations.length} error(s) — the auditor must find every one.`}
            </div>

            {data.supports_query && (
              <div style={{ marginTop: 18 }}>
                <div style={s.label}>Should this chart go for a physician query?</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[{ v: null, l: 'Not assessed' }, { v: false, l: 'No' }, { v: true, l: 'Yes' }].map(o => (
                    <button key={String(o.v)}
                      style={{ ...s.toggleChip, ...(queryExpected === o.v ? s.toggleChipOn : {}) }}
                      onClick={() => setQueryExpected(o.v as boolean | null)}>{o.l}</button>
                  ))}
                </div>
                <div style={s.note}>
                  Only a trainer who read the chart can answer this — the system cannot tell
                  whether documentation supported a code. “Not assessed” scores as NA rather
                  than as “no query needed”.
                </div>
                {queryExpected !== null && (
                  <input style={{ ...s.input, marginTop: 8, maxWidth: 480 }}
                    placeholder="Why (for your own reference)…"
                    value={queryRationale} onChange={e => setQueryRationale(e.target.value)} />
                )}
              </div>
            )}

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 12.5, cursor: 'pointer' }}>
              <input type="checkbox" checked={alwaysPlant} onChange={e => setAlwaysPlant(e.target.checked)} />
              Always use this version — never hand this chart over clean
            </label>
            <div style={s.note}>
              Use sparingly. Normally any chart can come up clean, which is what stops
              auditors learning which chart numbers are worth skimming.
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 20, alignItems: 'center', flexWrap: 'wrap' }}>
              <button style={s.ghostBtn} onClick={runPreview}><Eye size={14} /> Preview the claim</button>
              <input style={{ ...s.input, width: 200 }} type="password" placeholder="Passphrase"
                value={passphrase} onChange={e => setPassphrase(e.target.value)} />
              <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={save}>
                <Save size={14} /> {busy ? 'Saving…' : 'Save version'}
              </button>
              <button style={{ ...s.ghostBtn, opacity: busy ? 0.5 : 1 }} disabled={busy}
                onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>

            {preview && <ClaimPreview preview={preview} />}
          </div>
        </div>
      ) : (
        <div style={s.panel}>
          <div style={s.panelHead}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>
              Versions on this chart ({data.sets.length} of {data.max_versions})
            </span>
          </div>
          <div style={{ padding: '12px 16px' }}>
            {data.sets.length === 0 ? (
              <div style={s.empty}>
                None yet — this chart gets its errors from the system when it is allocated.
                Author a version to control exactly what an auditor has to find.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {data.sets.map((k: any) => (
                  <div key={k.id} style={s.errorRow}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>{k.name}</span>
                      <span style={s.tag}>{k.planting_count} error(s)</span>
                      {k.always_plant && <span style={{ ...s.tag, background: '#fef2f2', color: '#dc2626' }}>always used</span>}
                      <button style={{ ...s.linkBtn, marginLeft: 'auto' }} onClick={() => startEdit(k)}>Edit</button>
                      <button style={s.iconBtn} onClick={() => remove(k)}><Trash2 size={14} /></button>
                    </div>
                    {(k.mutations || []).map((m: any, i: number) => (
                      <div key={i} style={{ fontSize: 11.5, color: '#4b5563', marginTop: 3 }}>
                        • <strong>{m.action}</strong> {SECTION_LABEL[m.section] || m.section}
                        {m.field && m.field !== 'code' ? ` ${m.field}` : ''}
                        {' — '}
                        {m.action === 'Add' ? m.correct_value
                          : m.action === 'Delete' ? m.claim_value
                            : `show ${m.claim_value}`}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
            <input style={{ ...s.input, width: 200, marginTop: 12 }} type="password"
              placeholder="Passphrase (to delete)" value={passphrase}
              onChange={e => setPassphrase(e.target.value)} />
          </div>
        </div>
      )}
    </div>
  )
}

const ACTION_COLORS: Record<string, string> = {
  // The app's existing issue palette, from practicelab/shared. An omission is
  // the same red a coder's Missed shows in; a wrong code the same violet; a
  // spurious code the same amber as Over_coded.
  Add: ISSUE_COLORS.Missed,
  Revise: ISSUE_COLORS.Wrong_Code,
  Delete: ISSUE_COLORS.Over_coded,
}
const ACTION_BG: Record<string, string> = {
  Add: '#fef2f2', Revise: '#f5f3ff', Delete: '#fffbeb',
}
const ACTION_LEGEND = [
  { action: 'Add', color: ACTION_COLORS.Add, blurb: 'code removed; auditor must add it back' },
  { action: 'Revise', color: ACTION_COLORS.Revise, blurb: 'value altered; auditor must correct it' },
  { action: 'Delete', color: ACTION_COLORS.Delete, blurb: 'spurious code; auditor must remove it' },
]

const SECTION_ROWS: Record<string, string> = { SDx: 'sdx', PCS: 'pcs', CPT: 'cpt' }

/** One coding section of the answer key, with an action beside every line. */
function KeySection({ spec, answerKey, mutations, setMutations }: {
  spec: any; answerKey: any
  mutations: Finding[]; setMutations: (f: (m: Finding[]) => Finding[]) => void
}) {
  const key = spec.key
  if (key === 'MDM') {
    return <MdmKeySection spec={spec} answerKey={answerKey}
      mutations={mutations} setMutations={setMutations} />
  }
  const isPdx = key === 'PDx'
  const rows: any[] = isPdx
    ? (answerKey?.pdx_code ? [{ code: answerKey.pdx_code, poa: answerKey.pdx_poa }] : [])
    : (answerKey?.[SECTION_ROWS[key]] || [])

  // What the key's own codes say. This is a KEY screen, so a description is a
  // check rather than a study aid: a trainer authoring a planted error is
  // looking at the code they believe is correct, and a wrong key grades
  // everyone against it silently. Asked for the section's own system.
  const describe = useCodeDescriptions(rows.map((r: any) => String(r.code || '')), key)

  const mine = mutations.filter(m => m.section === key)
  const spurious = mine.filter(m => m.action === 'Delete')

  function find(action: string, line: number, field?: string) {
    return mine.find(m => m.action === action && m.line === line
      && (field === undefined || (m.field || 'code') === field))
  }

  function toggleOmit(line: number, code: string) {
    setMutations(prev => {
      const hit = prev.find(m => m.section === key && m.action === 'Add' && m.line === line)
      if (hit) return prev.filter(m => m !== hit)
      // Removing a code and revising it at once would be two errors on one
      // line, which makes the correct finding ambiguous.
      const rest = prev.filter(m => !(m.section === key && m.line === line))
      return [...rest, { section: key, action: 'Add', line, correct_value: code }]
    })
  }

  function setRevision(line: number, field: string, value: string, correct: string) {
    setMutations(prev => {
      const rest = prev.filter(m => !(m.section === key && m.action === 'Revise'
        && m.line === line && (m.field || 'code') === field))
      const omit = prev.find(m => m.section === key && m.action === 'Add' && m.line === line)
      const cleaned = omit ? rest.filter(m => m !== omit) : rest
      if (!value.trim()) return cleaned
      return [...cleaned, {
        section: key, action: 'Revise', field, line,
        claim_value: value.trim(), correct_value: correct,
      }]
    })
  }

  function addSpurious() {
    setMutations(prev => [...prev, { section: key, action: 'Delete', claim_value: '' }])
  }
  function setSpurious(index: number, value: string) {
    setMutations(prev => {
      const targets = prev.filter(m => m.section === key && m.action === 'Delete')
      const target = targets[index]
      return prev.map(m => m === target ? { ...m, claim_value: value.toUpperCase() } : m)
    })
  }
  function removeSpurious(index: number) {
    setMutations(prev => {
      const targets = prev.filter(m => m.section === key && m.action === 'Delete')
      return prev.filter(m => m !== targets[index])
    })
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ ...s.panelHead, marginTop: 0 }}>
        <span style={{ fontWeight: 700, fontSize: 12.5 }}>{SECTION_LABEL[key] || key}</span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>{rows.length} code(s) on the key</span>
        {spec.actions.includes('Delete') && (
          <button style={{ ...s.linkBtn, marginLeft: 'auto', color: ACTION_COLORS.Delete }}
            onClick={addSpurious}>
            <Plus size={12} /> Add a spurious code
          </button>
        )}
      </div>
      <div style={{ padding: '8px 12px' }}>
        {rows.length === 0 && (
          <div style={{ fontSize: 12, color: '#9ca3af', padding: '6px 0' }}>
            Nothing on the answer key for this section.
          </div>
        )}
        {rows.map((row: any, i: number) => {
          const omitted = !!find('Add', i)
          const revisions = spec.fields.map((f: string) => find('Revise', i, f)).filter(Boolean)
          const touched = omitted || revisions.length > 0
          const colour = omitted ? ACTION_COLORS.Add
            : revisions.length ? ACTION_COLORS.Revise : undefined
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '7px 8px',
              borderRadius: 7, flexWrap: 'wrap',
              background: touched ? (omitted ? ACTION_BG.Add : ACTION_BG.Revise) : 'transparent',
              borderLeft: `3px solid ${colour || 'transparent'}`,
            }}>
              <span style={{ fontSize: 11, color: '#9ca3af', width: 16 }}>{i + 1}</span>
              <code style={{
                fontFamily: 'ui-monospace, monospace', fontSize: 13, fontWeight: 700,
                textDecoration: omitted ? 'line-through' : 'none',
                color: omitted ? ACTION_COLORS.Add : '#111',
              }}>{row.code}</code>
              {row.ccmcc && row.ccmcc !== '-' && (
                <span style={{ ...s.tag, background: '#fee2e2', color: '#b91c1c' }}>{row.ccmcc}</span>
              )}
              {row.poa && <span style={{ ...s.tag, background: '#f0fdf4', color: '#15803d' }}>POA {row.poa}</span>}
              {row.modifier && <span style={s.tag}>{row.modifier}</span>}
              <div style={{ flexBasis: '100%', order: 99 }}>
                <CodeCaption code={row.code} describe={describe} />
              </div>

              <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                {revisions.map((r: any) => (
                  <span key={r.field} style={{ fontSize: 11, color: ACTION_COLORS.Revise, fontWeight: 600 }}>
                    {r.field}: {r.correct_value || '—'} → <strong>{r.claim_value}</strong>
                  </span>
                ))}
                {spec.fields.map((f: string) => (
                  <input key={f} style={{
                    ...s.input, width: f === 'code' ? 110 : 68, padding: '4px 8px',
                    fontSize: 12, textTransform: 'uppercase',
                    borderColor: find('Revise', i, f) ? ACTION_COLORS.Revise : '#d1d5db',
                  }}
                    placeholder={f === 'code' ? 'wrong code' : `wrong ${f}`}
                    title={`Show a wrong ${f} on the claim instead of ${row[f] || '—'}`}
                    disabled={omitted}
                    value={find('Revise', i, f)?.claim_value || ''}
                    onChange={e => setRevision(i, f, e.target.value, String(row[f] ?? ''))} />
                ))}
                {spec.actions.includes('Add') && (
                  <button
                    title={omitted ? 'Keep this code on the claim' : 'Remove it — the auditor must add it back'}
                    onClick={() => toggleOmit(i, row.code)}
                    style={{
                      padding: '4px 10px', borderRadius: 6, fontSize: 11.5, fontWeight: 700,
                      cursor: 'pointer',
                      border: `1px solid ${omitted ? ACTION_COLORS.Add : '#d1d5db'}`,
                      background: omitted ? ACTION_COLORS.Add : '#fff',
                      color: omitted ? '#fff' : '#6b7280',
                    }}>
                    {omitted ? 'Omitted' : 'Omit'}
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {spurious.map((m, i) => (
          <div key={`sp${i}`} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '7px 8px',
            borderRadius: 7, background: ACTION_BG.Delete,
            borderLeft: `3px solid ${ACTION_COLORS.Delete}`, marginTop: 4,
          }}>
            <span style={{ ...s.tag, background: '#fef3c7', color: ACTION_COLORS.Delete }}>
              Spurious
            </span>
            <input style={{ ...s.input, width: 130, padding: '4px 8px', fontSize: 12, textTransform: 'uppercase' }}
              placeholder="code to insert" value={m.claim_value || ''}
              onChange={e => setSpurious(i, e.target.value)} autoFocus={!m.claim_value} />
            <span style={{ fontSize: 11, color: '#92400e' }}>
              appears on the claim; the auditor must delete it
            </span>
            <button style={{ ...s.iconBtn, marginLeft: 'auto' }} onClick={() => removeSpurious(i)}>
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function MdmKeySection({ spec, answerKey, mutations, setMutations }: {
  spec: any; answerKey: any
  mutations: Finding[]; setMutations: (f: (m: Finding[]) => Finding[]) => void
}) {
  const mdm: Record<string, string> = answerKey?.mdm || {}
  const values: Record<string, string[]> = spec.field_values || {}
  const labels: Record<string, string> = spec.field_labels || {}
  const mine = mutations.filter(m => m.section === 'MDM')

  function revision(field: string) {
    return mine.find(m => m.action === 'Revise' && (m.field || '') === field)
  }

  function setWrong(field: string, current: string, value: string) {
    setMutations(prev => {
      const rest = prev.filter(m => !(m.section === 'MDM'
        && m.action === 'Revise' && (m.field || '') === field))
      if (!value || value === current) return rest
      return [...rest, {
        section: 'MDM', action: 'Revise', field, line: 0,
        claim_value: value, correct_value: current,
      }]
    })
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ ...s.panelHead, marginTop: 0 }}>
        <span style={{ fontWeight: 700, fontSize: 12.5 }}>{SECTION_LABEL.MDM || 'MDM'}</span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>reasoning levels on the key</span>
      </div>
      <div style={{ padding: '8px 12px', display: 'grid', gap: 8 }}>
        {spec.fields.map((field: string) => {
          const current = mdm[field] || ''
          const r = revision(field)
          return (
            <div key={field} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '7px 8px',
              borderRadius: 7, flexWrap: 'wrap',
              background: r ? ACTION_BG.Revise : 'transparent',
              borderLeft: `3px solid ${r ? ACTION_COLORS.Revise : 'transparent'}`,
            }}>
              <span style={{ minWidth: 170, fontSize: 12.5, fontWeight: 700, color: '#374151' }}>
                {labels[field] || field}
              </span>
              <span style={s.tag}>{current || 'No level'}</span>
              <select
                style={{ ...s.input, width: 150, padding: '4px 8px', fontSize: 12 }}
                value={r?.claim_value || ''}
                disabled={!current}
                onChange={e => setWrong(field, current, e.target.value)}
                title={`Show a wrong ${labels[field] || field} level on the claim`}
              >
                <option value="">No planted error</option>
                {(values[field] || []).filter(v => v !== current).map(v => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
              {r && (
                <span style={{ fontSize: 11, color: ACTION_COLORS.Revise, fontWeight: 600 }}>
                  auditor should change {r.claim_value} to {r.correct_value}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ClaimPreview({ preview }: { preview: any }) {
  const c = preview.claim || {}
  return (
    <div style={{ ...s.panel, marginTop: 16 }}>
      <div style={s.panelHead}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>
          What the auditor will see — {preview.planting_count} finding(s) expected
        </span>
      </div>
      <div style={{ padding: '12px 16px', fontSize: 12.5, lineHeight: 1.8 }}>
        <div><strong>PDx</strong> <code>{c.pdx_code || '—'}</code></div>
        <div><strong>SDx</strong> {(c.sdx || []).map((r: any, i: number) =>
          <code key={i} style={{ marginRight: 6 }}>{r.code}</code>)}</div>
        {(c.pcs || []).length > 0 && <div><strong>PCS</strong> {c.pcs.map((r: any, i: number) => <code key={i} style={{ marginRight: 6 }}>{r.code}</code>)}</div>}
        {(c.cpt || []).length > 0 && <div><strong>CPT</strong> {c.cpt.map((r: any, i: number) => <code key={i} style={{ marginRight: 6 }}>{r.code}{r.modifier ? `-${r.modifier}` : ''}</code>)}</div>}
        {c.mdm && Object.keys(c.mdm).length > 0 && (
          <div><strong>MDM</strong> {Object.entries(c.mdm).map(([k, v]: any) =>
            <span key={k} style={{ marginRight: 8 }}>{k}: <code>{v || '—'}</code></span>)}</div>
        )}
      </div>
    </div>
  )
}
