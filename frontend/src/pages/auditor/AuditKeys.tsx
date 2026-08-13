import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { ChevronLeft, Download, Eye, Plus, Save, Search, Trash2, X } from 'lucide-react'
import {
  createAuditKeySet, deleteAuditKeySet, downloadAuditKeys, getAuditKeysForChart,
  listAuditKeySets, previewAuditKeySet, updateAuditKeySet, Finding,
} from '../../api/auditorApi'
import { searchCharts } from '../../api'
import s from './styles'

/**
 * The trainer's audit keys.
 *
 * A set records what the AUDITOR must find, not what the system should break.
 * That direction is deliberate: it is the same shape the generator emits and
 * the same shape an auditor's own findings take, so scoring never translates
 * between two vocabularies — and a trainer authoring a set is writing the
 * answer rather than the sabotage.
 */

const ACTIONS = ['Add', 'Revise', 'Delete'] as const
const SECTION_LABEL: Record<string, string> = {
  PDx: 'Principal Dx', SDx: 'Secondary Dx', PCS: 'PCS', CPT: 'CPT',
}

export function AuditKeys({ trainer }: { trainer: string }) {
  const [chartId, setChartId] = useState<number | null>(null)
  const [sets, setSets] = useState<Record<string, any>[]>([])
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Record<string, any>[]>([])

  const load = useCallback(async () => {
    try { setSets((await listAuditKeySets()).sets) }
    catch { toast.error('Could not load the audit keys') }
  }, [])
  useEffect(() => { load() }, [load])

  async function search() {
    if (!query.trim()) return
    try {
      const res = await searchCharts({ q: query.trim(), limit: 20 } as never)
      setHits((res as { charts?: Record<string, any>[] }).charts || [])
    } catch { toast.error('Search failed') }
  }

  if (chartId !== null) {
    return <ChartKeyEditor chartId={chartId} trainer={trainer}
      onBack={() => { setChartId(null); load() }} />
  }

  return (
    <div>
      <div style={s.rowBetween}>
        <div style={s.h1}>Audit Keys</div>
        <button style={s.outlineBtn} title="Every authored set, one row per error"
          onClick={() => downloadAuditKeys()}>
          <Download size={15} /> Export (.xlsx)
        </button>
      </div>
      <div style={s.sub}>
        Author what an auditor should find on a chart. Stored sets are permanent and
        reusable; charts without one get their errors from the system instead.
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 18, maxWidth: 480 }}>
        <input style={s.input} placeholder="Find a chart by number…" value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()} />
        <button style={s.ghostBtn} onClick={search}><Search size={14} /> Search</button>
      </div>

      {hits.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
          {hits.map(c => (
            <button key={c.id as number} style={s.listRow} onClick={() => setChartId(c.id as number)}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{c.chart_number as string}</span>
              <span style={s.tag}>{c.specialty as string}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{c.category as string}</span>
              <span style={{ marginLeft: 'auto', ...s.linkBtn }}>Author errors →</span>
            </button>
          ))}
        </div>
      )}

      <div style={s.panel}>
        <div style={s.panelHead}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Curated charts ({sets.length})</span>
        </div>
        <div style={{ padding: '12px 16px' }}>
          {sets.length === 0 ? (
            <div style={s.empty}>
              Nothing authored yet. Every chart gets its errors from the system until you curate it.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {sets.map(k => (
                <button key={k.id as number} style={s.listRow}
                  onClick={() => setChartId(k.chart_id as number)}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{k.chart_number as string}</span>
                  <span style={{ fontSize: 13 }}>{k.name as string}</span>
                  <span style={s.tag}>{k.planting_count as number} error(s)</span>
                  {k.query_expected !== null && (
                    <span style={{ ...s.tag, background: '#fffbeb', color: '#b45309' }}>
                      query {k.query_expected ? 'expected' : 'not needed'}
                    </span>
                  )}
                  {(k.always_plant as boolean) && (
                    <span style={{ ...s.tag, background: '#fef2f2', color: '#dc2626' }}>always used</span>
                  )}
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>
                    {k.authored_by as string}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
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

  const load = useCallback(async () => {
    try { setData(await getAuditKeysForChart(chartId)) }
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
    if (!name.trim()) return toast.error('Name the set — a chart can hold several')
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

  const key = data.answer_key
  const sections: string[] = (data.form?.sections || []).map((x: any) => x.key)

  return (
    <div style={{ maxWidth: 900 }}>
      <button style={s.backBtn} onClick={onBack}><ChevronLeft size={14} /> Audit Keys</button>
      <div style={s.rowBetween}>
        <div>
          <div style={s.h1}>{data.chart_number}</div>
          <div style={s.sub}>{data.specialty}</div>
        </div>
        {!editing && data.has_answer_key && data.auditable && (
          <button style={s.primaryBtn} onClick={startNew}><Plus size={15} /> New error set</button>
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
              {editing.id ? 'Edit error set' : 'New error set'}
            </span>
            <button style={{ ...s.iconBtn, marginLeft: 'auto' }} onClick={() => setEditing(null)}>
              <X size={15} />
            </button>
          </div>
          <div style={{ padding: '14px 16px' }}>
            <div style={s.infoBox}>
              Describe what the auditor must <strong>find</strong>. An “Add” means the code is
              missing from what they see; a “Delete” means a spurious code is on their claim.
            </div>

            <div style={{ marginTop: 14, marginBottom: 12 }}>
              <div style={s.label}>Set name</div>
              <input style={{ ...s.input, maxWidth: 360 }} value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Foundational · DRG impact" />
              <div style={s.note}>
                A chart can hold several sets, and an auditor is given one they have not seen.
              </div>
            </div>

            <div style={s.label}>Errors</div>
            {mutations.map((m, i) => (
              <MutationRow key={i} m={m} sections={sections}
                onChange={next => setMutations(p => p.map((x, j) => j === i ? next : x))}
                onRemove={() => setMutations(p => p.filter((_, j) => j !== i))} />
            ))}
            <button style={{ ...s.ghostBtn, marginTop: 8 }}
              onClick={() => setMutations(p => [...p, { section: 'SDx', action: 'Add', correct_value: '' }])}>
              <Plus size={13} /> Add an error
            </button>

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
              Always use this set — exempt from the clean draw
            </label>
            <div style={s.note}>
              Use sparingly. A curated chart that never comes up clean becomes a tell.
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 20, alignItems: 'center', flexWrap: 'wrap' }}>
              <button style={s.ghostBtn} onClick={runPreview}><Eye size={14} /> Preview the claim</button>
              <input style={{ ...s.input, width: 200 }} type="password" placeholder="Passphrase"
                value={passphrase} onChange={e => setPassphrase(e.target.value)} />
              <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={save}>
                <Save size={14} /> {busy ? 'Saving…' : 'Save set'}
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
            <span style={{ fontWeight: 700, fontSize: 13 }}>Error sets ({data.sets.length})</span>
          </div>
          <div style={{ padding: '12px 16px' }}>
            {data.sets.length === 0 ? (
              <div style={s.empty}>
                None yet — this chart gets its errors from the system when it is allocated.
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

function MutationRow({ m, sections, onChange, onRemove }: {
  m: Finding; sections: string[]
  onChange: (m: Finding) => void; onRemove: () => void
}) {
  // PDx is single-valued: it can be wrong, but it cannot be absent or removed.
  const actions = m.section === 'PDx' ? ['Revise'] : ACTIONS
  return (
    <div style={s.mutRow}>
      <select style={s.select} value={m.section}
        onChange={e => onChange({ ...m, section: e.target.value, action: e.target.value === 'PDx' ? 'Revise' : m.action })}>
        {sections.map(x => <option key={x} value={x}>{SECTION_LABEL[x] || x}</option>)}
      </select>
      <select style={s.select} value={m.action}
        onChange={e => onChange({ ...m, action: e.target.value as Finding['action'] })}>
        {actions.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      {m.action === 'Revise' && (
        <>
          <select style={s.select} value={m.field || 'code'}
            onChange={e => onChange({ ...m, field: e.target.value })}>
            {['code', 'poa', 'ccmcc', 'modifier', 'units'].map(f => <option key={f}>{f}</option>)}
          </select>
          <input style={{ ...s.input, width: 74 }} type="number" min={0}
            placeholder="line" value={m.line ?? ''}
            onChange={e => onChange({ ...m, line: e.target.value === '' ? undefined : parseInt(e.target.value) })} />
        </>
      )}
      {m.action === 'Add' ? (
        <input style={{ ...s.input, width: 150 }} placeholder="code to find"
          value={m.correct_value || ''}
          onChange={e => onChange({ ...m, correct_value: e.target.value.toUpperCase() })} />
      ) : (
        <input style={{ ...s.input, width: 150 }}
          placeholder={m.action === 'Delete' ? 'spurious code' : 'wrong value shown'}
          value={m.claim_value || ''}
          onChange={e => onChange({ ...m, claim_value: e.target.value.toUpperCase() })} />
      )}
      <button style={s.iconBtn} onClick={onRemove}><X size={14} /></button>
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
      </div>
    </div>
  )
}
