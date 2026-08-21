import { useState, useEffect } from 'react'
import { X, Plus, Loader, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getAnswerKeyDetail, getAnswerKeyImpact, saveAnswerKeyInline,
  type AnswerKeyDetail, type AnswerKeyImpact,
} from '../../api'
import { CodeSuggest } from '../../components/CodeSuggest'
import { CodeCaption } from '../../components/CodeCaption'
import { useCodeDescriptions } from '../../hooks/useCodeDescriptions'
import { errorMessage } from '../../api/errors'
import { trainerName } from './shared'
import styles from './styles'

const POA_OPTIONS = ['', 'Y', 'N', 'U', 'W', '1']
const CCMCC_OPTIONS = ['', 'MCC', 'CC', '-']

/**
 * In-interface answer key editor — for quick/ad-hoc charts and for correcting
 * existing keys. Bulk entry stays on the Excel route.
 *
 * Editing a key that has already graded work is the risky part, so the impact
 * is shown before saving rather than discovered afterwards.
 */
export function AnswerKeyEditor({ chartId, onClose, onSaved }: {
  chartId: number; onClose: () => void; onSaved: () => void
}) {
  const [detail, setDetail] = useState<AnswerKeyDetail | null>(null)
  const [impact, setImpact] = useState<AnswerKeyImpact | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [passphrase, setPassphrase] = useState('')
  const [regradeClosed, setRegradeClosed] = useState(false)

  const [pdx, setPdx] = useState('')
  const [pdxPoa, setPdxPoa] = useState('')
  const [sdx, setSdx] = useState<Array<{ code: string; poa?: string; ccmcc?: string }>>([])
  const [pcs, setPcs] = useState<Array<{ code: string }>>([])
  // units is a string so an empty box stays empty. Absence means "do not grade
  // units on this line", which is not the same claim as an explicit 1.
  const [cpt, setCpt] = useState<Array<{ code: string; modifier?: string; pointers?: string[]; units?: number | string }>>([])
  const [facilityLevel, setFacilityLevel] = useState('')
  const [profeeLevel, setProfeeLevel] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const d = await getAnswerKeyDetail(chartId)
        if (!alive) return
        setDetail(d)
        setPdx(d.pdx_code || ''); setPdxPoa(d.pdx_poa || '')
        setSdx(d.sdx || []); setPcs(d.pcs || []); setCpt(d.cpt || [])
        setFacilityLevel(d.facility_level || ''); setProfeeLevel(d.profee_level || '')
        if (d.exists) setImpact(await getAnswerKeyImpact(chartId))
      } catch {
        toast.error('Could not load this answer key')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [chartId])

  async function save() {
    if (!pdx.trim()) { toast.error('Principal / first-listed diagnosis is required'); return }
    if (detail?.exists && !passphrase.trim()) {
      toast.error('Editing an existing key requires the master passphrase'); return
    }
    setSaving(true)
    try {
      const res = await saveAnswerKeyInline(chartId, {
        pdx_code: pdx.trim(),
        pdx_poa: detail?.is_ip ? pdxPoa : '',
        sdx: sdx.filter(s => s.code.trim()),
        pcs: detail?.is_ip ? pcs.filter(p => p.code.trim()) : [],
        cpt: detail?.is_ip ? [] : cpt.filter(c => c.code.trim()).map(c => {
          const { units, ...rest } = c
          const n = parseInt(String(units ?? ''), 10)
          return n >= 1 ? { ...rest, units: n } : rest
        }),
        facility_level: detail?.single_path ? facilityLevel.trim() || null : null,
        profee_level: detail?.single_path ? profeeLevel.trim() || null : null,
        entered_by: trainerName(),
        passphrase,
        regrade_closed: regradeClosed,
      })
      const bits = [res.created ? 'Answer key created' : 'Answer key updated']
      if (res.regraded) bits.push(`${res.regraded} result(s) re-graded`)
      if (res.skipped_closed) bits.push(`${res.skipped_closed} left untouched in closed batches`)
      toast.success(bits.join(' · '))
      onSaved(); onClose()
    } catch (e: any) {
      const status = e?.response?.status
      const msg = e?.response?.data?.detail || 'Could not save'
      if (status === 409) {
        // Closed batches would be rewritten — make it an explicit second choice
        setRegradeClosed(true)
        toast(msg + '  Tick the closed-batch box and save again if you intend to.',
              { duration: 10000, icon: '⚠️' })
      } else {
        toast.error(errorMessage(e, msg))
      }
    } finally {
      setSaving(false)
    }
  }

  // These four sit ABOVE the early returns deliberately. Hooks must run in
  // the same order on every render, and the `if (loading) return` below means
  // the first render would run none of them and the second four — React error
  // #310, which crashed this editor for anyone who opened it.
  // One batched lookup per code system. Asked separately because a modifier
  // and a procedure share a numeric shape, and a seven-character string must
  // not be allowed to match something in the wrong table.
  const describeDx = useCodeDescriptions([pdx, ...sdx.map(x => x.code)], 'SDx')
  const describePcs = useCodeDescriptions(pcs.map(x => x.code), 'PCS')
  const describeCpt = useCodeDescriptions(cpt.map(x => x.code), 'CPT')
  const describeMod = useCodeDescriptions(
    cpt.flatMap(x => (x.modifier || '').split(/[,\s]+/).filter(Boolean)), 'MODIFIER')

  if (loading) {
    return (
      <div style={styles.modalOverlay}>
        <div style={{ ...styles.modalBox, minWidth: 420, textAlign: 'center' }}>
          <Loader size={20} /> Loading key…
        </div>
      </div>
    )
  }
  if (!detail) return null

  // flexWrap so a description sits on its own full-width line under the row's
  // controls rather than squeezing the code box.
  const rowStyle = { display: 'flex', gap: 8, alignItems: 'center',
                     flexWrap: 'wrap' as const, marginBottom: 6 }
  const inp = { ...styles.input, marginBottom: 0 }

  return (
    <div style={styles.modalOverlay}>
      <div style={{ ...styles.modalBox, minWidth: 640, maxWidth: 760, maxHeight: '86vh', overflowY: 'auto' as const }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={styles.modalTitle}>
            {detail.exists ? 'Edit' : 'Create'} Answer Key — {detail.chart_number}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af' }}>
            <X size={18} />
          </button>
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 14 }}>
          {detail.specialty}{detail.category ? ` · ${detail.category}` : ''}
        </div>

        {/* Impact — shown before saving, not after */}
        {impact && impact.total_results > 0 && (
          <div style={{
            background: impact.blocked ? '#fef2f2' : '#fffbeb',
            border: `1px solid ${impact.blocked ? '#fecaca' : '#fde68a'}`,
            borderRadius: 8, padding: '10px 12px', marginBottom: 14, fontSize: 12.5,
            color: impact.blocked ? '#991b1b' : '#92400e',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, marginBottom: 4 }}>
              <AlertTriangle size={14} /> This key has already graded work
            </div>
            <div>
              <strong>{impact.total_results}</strong> result(s) across{' '}
              <strong>{impact.batches.length}</strong> batch(es),{' '}
              <strong>{impact.coders_affected}</strong> coder(s). Saving re-grades them
              and the new scores flow straight into reports and analytics.
            </div>
            {impact.drg_decisions_preserved > 0 && (
              <div style={{ marginTop: 4 }}>
                {impact.drg_decisions_preserved} trainer DRG decision(s) will be preserved.
              </div>
            )}
            {impact.released_to_coders > 0 && (
              <div style={{ marginTop: 4 }}>
                ⚠️ {impact.released_to_coders} result(s) were already visible to coders — their score may change.
              </div>
            )}
            {impact.closed_batches > 0 && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, cursor: 'pointer', fontWeight: 600 }}>
                <input type="checkbox" checked={regradeClosed} onChange={e => setRegradeClosed(e.target.checked)} />
                Also re-grade {impact.closed_batches} closed batch(es) — rewrites closed history
              </label>
            )}
          </div>
        )}

        {/* ED Single Path levels */}
        {detail.single_path && (
          <>
            <div style={styles.label}>ED Levels</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
              <input style={{ ...inp, flex: 1 }} placeholder="Facility level e.g. 99283"
                value={facilityLevel} onChange={e => setFacilityLevel(e.target.value)} />
              <input style={{ ...inp, flex: 1 }} placeholder="Professional level e.g. 99284"
                value={profeeLevel} onChange={e => setProfeeLevel(e.target.value)} />
            </div>
          </>
        )}

        {/* PDx */}
        <div style={styles.label}>{detail.is_ip ? 'Principal Diagnosis' : 'First-Listed Diagnosis'}</div>
        <div style={{ ...rowStyle, marginBottom: 2 }}>
          <CodeSuggest style={{ ...inp, flex: 1 }} section="PDx"
            placeholder="e.g. J18.9" value={pdx} onChange={setPdx} />
          {detail.is_ip && (
            <select style={{ ...styles.select, marginBottom: 0, width: 110 }} value={pdxPoa}
              onChange={e => setPdxPoa(e.target.value)}>
              {POA_OPTIONS.map(o => <option key={o} value={o}>{o || 'POA'}</option>)}
            </select>
          )}
        </div>
        <div style={{ marginBottom: 12 }}>
          <CodeCaption code={pdx} describe={describeDx} system="ICD10CM" />
        </div>

        {/* SDx */}
        <div style={styles.label}>Secondary Diagnoses</div>
        {sdx.map((s, i) => (
          <div key={i} style={rowStyle}>
            <CodeSuggest style={{ ...inp, flex: 1 }} section="SDx"
              placeholder="e.g. E11.9" value={s.code}
              onChange={v => setSdx(sdx.map((x, j) => j === i ? { ...x, code: v } : x))} />
            {detail.is_ip && (
              <>
                <select style={{ ...styles.select, marginBottom: 0, width: 90 }} value={s.poa || ''}
                  onChange={e => setSdx(sdx.map((x, j) => j === i ? { ...x, poa: e.target.value } : x))}>
                  {POA_OPTIONS.map(o => <option key={o} value={o}>{o || 'POA'}</option>)}
                </select>
                <select style={{ ...styles.select, marginBottom: 0, width: 100 }} value={s.ccmcc || ''}
                  onChange={e => setSdx(sdx.map((x, j) => j === i ? { ...x, ccmcc: e.target.value } : x))}>
                  {CCMCC_OPTIONS.map(o => <option key={o} value={o}>{o || 'CC/MCC'}</option>)}
                </select>
              </>
            )}
            <button onClick={() => setSdx(sdx.filter((_, j) => j !== i))}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={14} /></button>
            <div style={{ flexBasis: '100%' }}>
              <CodeCaption code={s.code} describe={describeDx} system="ICD10CM" />
            </div>
          </div>
        ))}
        <button style={{ ...styles.outlineBtn, marginBottom: 12 }}
          onClick={() => setSdx([...sdx, { code: '', poa: '', ccmcc: '' }])}>
          <Plus size={13} /> Add diagnosis
        </button>

        {/* PCS (IP) or CPT (everything else) */}
        {detail.is_ip ? (
          <>
            <div style={styles.label}>PCS Procedures</div>
            {pcs.map((p, i) => (
              <div key={i} style={rowStyle}>
                <CodeSuggest style={{ ...inp, flex: 1 }} section="PCS"
                  placeholder="e.g. 0BHN3BZ" value={p.code}
                  onChange={v => setPcs(pcs.map((x, j) => j === i ? { code: v } : x))} />
                <button onClick={() => setPcs(pcs.filter((_, j) => j !== i))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={14} /></button>
                <div style={{ flexBasis: '100%' }}>
                  <CodeCaption code={p.code} describe={describePcs} system="ICD10PCS" />
                </div>
              </div>
            ))}
            <button style={{ ...styles.outlineBtn, marginBottom: 12 }}
              onClick={() => setPcs([...pcs, { code: '' }])}><Plus size={13} /> Add procedure</button>
          </>
        ) : (
          <>
            <div style={styles.label}>
              CPT Procedures{detail.uses_pointers ? ' — with Dx pointers' : ''}
            </div>
            {detail.uses_pointers && (
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>
                Pointers are numbers into the Dx list above — 1 = {detail.is_ip ? 'PDx' : 'first-listed'},
                2 = 1st secondary, 3 = 2nd… Up to 4 per line, first is primary.
              </div>
            )}
            {cpt.map((c, i) => (
              <div key={i} style={rowStyle}>
                <CodeSuggest style={{ ...inp, width: 130 }} section="CPT"
                  placeholder="e.g. 27447" value={c.code}
                  onChange={v => setCpt(cpt.map((x, j) => j === i ? { ...x, code: v } : x))} />
                <CodeSuggest style={{ ...inp, flex: 1 }} section="MODIFIER"
                  placeholder="Modifier" value={c.modifier || ''}
                  onChange={v => setCpt(cpt.map((x, j) => j === i ? { ...x, modifier: v } : x))} />
                {detail.uses_units && (
                  <input style={{ ...inp, width: 78 }} placeholder="Units" inputMode="numeric"
                    title="Leave blank unless the count matters — a blank line is not graded on units."
                    value={c.units ?? ''}
                    onChange={e => setCpt(cpt.map((x, j) => j === i ? {
                      ...x, units: e.target.value.replace(/[^0-9]/g, '').slice(0, 3),
                    } : x))} />
                )}
                {detail.uses_pointers && (
                  <input style={{ ...inp, width: 130, textTransform: 'uppercase' }} placeholder="Dx ptrs 1,2"
                    value={(c.pointers || []).join(',')}
                    onChange={e => setCpt(cpt.map((x, j) => j === i ? {
                      ...x,
                      pointers: e.target.value.toUpperCase().replace(/[^0-9A-L,\s]/g, '')
                        .split(/[,\s]+/).filter(Boolean).slice(0, 4),
                    } : x))} />
                )}
                <div style={{ flexBasis: '100%' }}>
                  {/* AMA CPT is unlicensed and absent, so most procedure lines
                      stay bare. HCPCS Level II codes typed here DO resolve, and
                      a modifier's meaning comes from the same file — the only
                      thing in the app that explains one. */}
                  <CodeCaption code={c.code} describe={describeCpt} />
                  <CodeCaption code={c.modifier || ''} describe={describeMod} />
                </div>
                <button onClick={() => setCpt(cpt.filter((_, j) => j !== i))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={14} /></button>
              </div>
            ))}
            <button style={{ ...styles.outlineBtn, marginBottom: 12 }}
              onClick={() => setCpt([...cpt, { code: '', modifier: '', pointers: [] }])}>
              <Plus size={13} /> Add CPT
            </button>
          </>
        )}

        {/* Existing keys are locked behind the same gate as the Excel replace path */}
        {detail.exists && (
          <>
            <div style={styles.label}>Master passphrase</div>
            <input type="password" autoComplete="new-password" style={{ ...inp, marginBottom: 14 }} value={passphrase}
              placeholder="Required to change an existing key"
              onChange={e => setPassphrase(e.target.value)} />
          </>
        )}

        <div style={styles.modalActions}>
          <button style={styles.outlineBtn} onClick={onClose} disabled={saving}>Cancel</button>
          <button style={{ ...styles.primaryBtn, opacity: saving ? 0.6 : 1 }} disabled={saving} onClick={save}>
            {saving ? <><Loader size={14} /> Saving…</> : detail.exists ? 'Save & re-grade' : 'Create key'}
          </button>
        </div>
      </div>
    </div>
  )
}
