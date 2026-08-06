import { useState, useEffect } from 'react'
import { X, Plus, Loader, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getAnswerKeyDetail, getAnswerKeyImpact, saveAnswerKeyInline,
  type AnswerKeyDetail, type AnswerKeyImpact,
} from '../../api'
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
  const [cpt, setCpt] = useState<Array<{ code: string; modifier?: string; pointers?: string[] }>>([])
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
        cpt: detail?.is_ip ? [] : cpt.filter(c => c.code.trim()),
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
        toast.error(msg)
      }
    } finally {
      setSaving(false)
    }
  }

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

  const rowStyle = { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }
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
        <div style={{ ...rowStyle, marginBottom: 12 }}>
          <input style={{ ...inp, flex: 1 }} placeholder="e.g. J18.9" value={pdx}
            onChange={e => setPdx(e.target.value)} />
          {detail.is_ip && (
            <select style={{ ...styles.select, marginBottom: 0, width: 110 }} value={pdxPoa}
              onChange={e => setPdxPoa(e.target.value)}>
              {POA_OPTIONS.map(o => <option key={o} value={o}>{o || 'POA'}</option>)}
            </select>
          )}
        </div>

        {/* SDx */}
        <div style={styles.label}>Secondary Diagnoses</div>
        {sdx.map((s, i) => (
          <div key={i} style={rowStyle}>
            <input style={{ ...inp, flex: 1 }} placeholder="e.g. E11.9" value={s.code}
              onChange={e => setSdx(sdx.map((x, j) => j === i ? { ...x, code: e.target.value } : x))} />
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
                <input style={{ ...inp, flex: 1 }} placeholder="e.g. 0BHN3BZ" value={p.code}
                  onChange={e => setPcs(pcs.map((x, j) => j === i ? { code: e.target.value } : x))} />
                <button onClick={() => setPcs(pcs.filter((_, j) => j !== i))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={14} /></button>
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
                <input style={{ ...inp, width: 130 }} placeholder="e.g. 27447" value={c.code}
                  onChange={e => setCpt(cpt.map((x, j) => j === i ? { ...x, code: e.target.value } : x))} />
                <input style={{ ...inp, flex: 1 }} placeholder="Modifier" value={c.modifier || ''}
                  onChange={e => setCpt(cpt.map((x, j) => j === i ? { ...x, modifier: e.target.value } : x))} />
                {detail.uses_pointers && (
                  <input style={{ ...inp, width: 130, textTransform: 'uppercase' }} placeholder="Dx ptrs 1,2"
                    value={(c.pointers || []).join(',')}
                    onChange={e => setCpt(cpt.map((x, j) => j === i ? {
                      ...x,
                      pointers: e.target.value.toUpperCase().replace(/[^0-9A-L,\s]/g, '')
                        .split(/[,\s]+/).filter(Boolean).slice(0, 4),
                    } : x))} />
                )}
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
