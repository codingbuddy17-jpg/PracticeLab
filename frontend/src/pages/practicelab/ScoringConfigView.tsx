import { useState, useEffect } from 'react'
import { Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getScoringConfigs, updateScoringConfig, getEMScoringConfig, updateEMScoringConfig } from '../../api'
import { trainerName } from './shared'
import styles from './styles'

const ALL_DRG_TRIGGERS = [
  { key: 'pdx_mismatch', label: 'PDx code or POA mismatch' },
  { key: 'ccmcc_missing', label: 'CC/MCC SDx from AK missing from coder' },
  { key: 'pcs_undercoded', label: 'PCS under-coded (missed AK procedures)' },
  { key: 'pcs_overcoded', label: 'PCS over-coded (extra procedures)' },
  // Off by default: a secondary that is not a CC/MCC cannot move the DRG, so it
  // needs no trainer decision. Kept selectable, with the caveat stated.
  { key: 'spurious_sdx', label: 'AK has no SDx but coder added SDx (does not affect DRG unless CC/MCC — off by default)' },
  { key: 'spurious_pcs', label: 'AK has no PCS but coder added PCS' },
]

function WeightField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <label style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>{label}</label>
      <input type="number" min={0} max={100} style={{ ...styles.input, width: 70, textAlign: 'center' }}
        value={value || 0} onChange={e => onChange(parseInt(e.target.value) || 0)} />
    </div>
  )
}

export function ScoringConfigView() {
  const [configs, setConfigs] = useState<any>(null)
  const [tab, setTab] = useState<'IP' | 'OP' | 'EDSP' | 'EM'>('IP')
  const [form, setForm] = useState<any>({})
  const [emForm, setEmForm] = useState<any>(null)
  const [passphrase, setPassphrase] = useState('')
  const [saving, setSaving] = useState(false)
  const [showPassphrase, setShowPassphrase] = useState(false)

  useEffect(() => { loadConfigs() }, [])

  async function loadConfigs() {
    try {
      const [data, emData] = await Promise.all([getScoringConfigs(), getEMScoringConfig()])
      setConfigs(data)
      setForm({ IP: { ...data.IP }, OP: { ...data.OP }, EDSP: { ...data.EDSP } })
      setEmForm({ ...emData })
    } catch { toast.error('Failed to load scoring config') }
  }

  function updateEmField(field: string, value: any) {
    setEmForm((f: any) => ({ ...f, [field]: value }))
  }

  function emLine1Sum() {
    if (!emForm) return 0
    return (emForm.em_level_weight || 0) + (emForm.cpt_weight || 0) + (emForm.dx_weight || 0)
  }
  function emLine2Sum() {
    if (!emForm) return 0
    return (emForm.copa_weight || 0) + (emForm.dr_weight || 0) + (emForm.risk_weight || 0)
  }
  function emLinesSumTo100() {
    if (!emForm) return false
    return Math.abs((emForm.line1_weight || 0) + (emForm.line2_weight || 0) - 100) < 0.1
  }

  async function handleSaveEM() {
    if (!passphrase) return toast.error('Enter master admin passphrase')
    if (!emLinesSumTo100()) return toast.error('Coding Accuracy + Reasoning Accuracy weights must sum to 100')
    const l1 = emForm.line1_weight || 0
    const l2 = emForm.line2_weight || 0
    if (Math.abs(emLine1Sum() - l1) > 0.5) return toast.error(`Coding Accuracy weights must sum to ${l1} (currently ${emLine1Sum().toFixed(2)})`)
    if (Math.abs(emLine2Sum() - l2) > 0.5) return toast.error(`Reasoning Accuracy weights must sum to ${l2} (currently ${emLine2Sum().toFixed(2)})`)
    setSaving(true)
    try {
      await updateEMScoringConfig({ ...emForm, passphrase, updated_by: trainerName() })
      toast.success('E/M scoring config saved')
      loadConfigs()
      setPassphrase('')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save')
    } finally { setSaving(false) }
  }

  function updateField(stype: string, field: string, value: any) {
    setForm((f: any) => ({ ...f, [stype]: { ...f[stype], [field]: value } }))
  }

  function toggleTrigger(key: string) {
    const current: string[] = form.IP?.drg_triggers || []
    const updated = current.includes(key) ? current.filter(k => k !== key) : [...current, key]
    updateField('IP', 'drg_triggers', updated)
  }

  function weightSum(stype: string) {
    const f = form[stype] || {}
    if (stype === 'IP') return (f.pdx_weight || 0) + (f.sdx_weight || 0) + (f.pcs_weight || 0) + (f.drg_weight || 0)
    if (stype === 'EDSP') return (f.pdx_weight || 0) + (f.sdx_weight || 0) + (f.facility_level_weight || 0) + (f.profee_level_weight || 0) + (f.cpt_weight || 0)
    return (f.pdx_weight || 0) + (f.sdx_weight || 0) + (f.cpt_weight || 0)
  }

  async function handleSave() {
    if (!passphrase) return toast.error('Enter master admin passphrase')
    const f = form[tab]
    const sum = weightSum(tab)
    if (sum !== 100) return toast.error(`Weights must sum to 100 (currently ${sum})`)
    if (!f.weighted_enabled && !f.dpo_enabled) return toast.error('At least one scoring method must be enabled')
    setSaving(true)
    try {
      await updateScoringConfig({
        specialty_type: tab,
        pdx_weight: f.pdx_weight,
        sdx_weight: f.sdx_weight,
        pcs_weight: tab === 'IP' ? f.pcs_weight : undefined,
        drg_weight: tab === 'IP' ? f.drg_weight : undefined,
        cpt_weight: tab === 'OP' || tab === 'EDSP' ? f.cpt_weight : undefined,
        facility_level_weight: tab === 'EDSP' ? f.facility_level_weight : undefined,
        profee_level_weight: tab === 'EDSP' ? f.profee_level_weight : undefined,
        pass_threshold: f.pass_threshold,
        drg_triggers: tab === 'IP' ? (f.drg_triggers || []) : [],
        overcoding_penalty: f.overcoding_penalty,
        weighted_enabled: f.weighted_enabled ?? true,
        dpo_enabled: f.dpo_enabled ?? true,
        dpo_pass_threshold: f.dpo_pass_threshold ?? 80,
        passphrase,
        updated_by: trainerName(),
      })
      toast.success(`${tab} scoring config saved`)
      loadConfigs()
      setPassphrase('')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save')
    } finally { setSaving(false) }
  }

  if (!form.IP || !form.OP || !form.EDSP || !emForm) return <div style={styles.center}><Loader size={24} /></div>

  const f = form[tab]
  const sum = weightSum(tab)

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Scoring Configuration</div>
      <div style={styles.warnBox}>
        ⚠ Changes apply to <strong>future batches only</strong>. In-progress and completed batches are not affected.
        Requires master admin passphrase.
      </div>

      <div style={styles.chipRow}>
        {(['IP', 'OP', 'EDSP', 'EM'] as const).map(t => (
          <button key={t} style={tab === t ? styles.chipActive : styles.chip} onClick={() => { setTab(t); setPassphrase('') }}>
            {t === 'IP' ? 'IP-DRG' : t === 'OP' ? 'Outpatient (OP)' : t === 'EDSP' ? 'ED Single Path' : 'E/M (MDM-based)'}
          </button>
        ))}
      </div>

      {/* ── E/M Config ── */}
      {tab === 'EM' && (<>
        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Score Line Weights
            <span style={styles.hint}> — must sum to 100</span>
          </div>
          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#1e3a5f', marginBottom: 4 }}>Coding Accuracy weight</div>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>E/M Level + CPT + Dx</div>
              <input type="number" min={0} max={100} style={{ ...styles.input, width: 80, textAlign: 'center' }}
                value={emForm.line1_weight} onChange={e => updateEmField('line1_weight', parseFloat(e.target.value) || 0)} />
            </div>
            <div style={{ fontSize: 22, fontWeight: 300, color: '#9ca3af', paddingBottom: 8 }}>+</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#7c3aed', marginBottom: 4 }}>Reasoning Accuracy weight</div>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>COPA + Data Review + Risk elements</div>
              <input type="number" min={0} max={100} style={{ ...styles.input, width: 80, textAlign: 'center' }}
                value={emForm.line2_weight} onChange={e => updateEmField('line2_weight', parseFloat(e.target.value) || 0)} />
            </div>
            <div style={{ paddingBottom: 8, fontSize: 13, fontWeight: 700,
              color: emLinesSumTo100() ? '#16a34a' : '#dc2626' }}>
              = {((emForm.line1_weight || 0) + (emForm.line2_weight || 0)).toFixed(1)} / 100 {emLinesSumTo100() ? '✓' : '⚠'}
            </div>
          </div>
        </div>

        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Coding Accuracy — Per-Metric Weights
            <span style={styles.hint}> — must sum to {emForm.line1_weight}</span>
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <WeightField label="E/M Level" value={emForm.em_level_weight}
              onChange={v => updateEmField('em_level_weight', v)} />
            <WeightField label="CPT Procedures" value={emForm.cpt_weight}
              onChange={v => updateEmField('cpt_weight', v)} />
            <WeightField label="Dx Coding" value={emForm.dx_weight}
              onChange={v => updateEmField('dx_weight', v)} />
            <div style={{ fontSize: 13, fontWeight: 700, paddingBottom: 4,
              color: Math.abs(emLine1Sum() - (emForm.line1_weight || 0)) < 0.5 ? '#16a34a' : '#dc2626' }}>
              = {emLine1Sum().toFixed(2)} / {emForm.line1_weight} {Math.abs(emLine1Sum() - (emForm.line1_weight || 0)) < 0.5 ? '✓' : '⚠'}
            </div>
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>
            CPT weight auto-redistributes to E/M Level and Dx equally when a chart has no procedure CPTs in the answer key.
          </div>
        </div>

        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Reasoning Accuracy — Per-Component Weights
            <span style={styles.hint}> — must sum to {emForm.line2_weight}</span>
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <WeightField label="COPA Elements" value={emForm.copa_weight}
              onChange={v => updateEmField('copa_weight', v)} />
            <WeightField label="Data Review Elements" value={emForm.dr_weight}
              onChange={v => updateEmField('dr_weight', v)} />
            <WeightField label="Risk Elements" value={emForm.risk_weight}
              onChange={v => updateEmField('risk_weight', v)} />
            <div style={{ fontSize: 13, fontWeight: 700, paddingBottom: 4,
              color: Math.abs(emLine2Sum() - (emForm.line2_weight || 0)) < 0.5 ? '#16a34a' : '#dc2626' }}>
              = {emLine2Sum().toFixed(2)} / {emForm.line2_weight} {Math.abs(emLine2Sum() - (emForm.line2_weight || 0)) < 0.5 ? '✓' : '⚠'}
            </div>
          </div>
        </div>

        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Pass Threshold</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
              value={emForm.pass_threshold} onChange={e => updateEmField('pass_threshold', parseFloat(e.target.value) || 80)} />
            <span style={styles.hint}>% minimum overall score to pass</span>
          </div>
        </div>

        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Overcoding Penalty</div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={emForm.overcoding_penalty}
              onChange={e => updateEmField('overcoding_penalty', e.target.checked)} />
            Penalize extra Dx or CPT codes submitted beyond the answer key count
          </label>
        </div>

        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>Master Admin Passphrase *</div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input type={showPassphrase ? 'text' : 'password'} style={{ ...styles.input, width: 220 }}
              placeholder="Enter passphrase to save" value={passphrase} onChange={e => setPassphrase(e.target.value)} />
            <button style={styles.outlineBtn} onClick={() => setShowPassphrase(s => !s)}>{showPassphrase ? 'Hide' : 'Show'}</button>
            <button style={saving ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn} disabled={saving} onClick={handleSaveEM}>
              {saving ? <><Loader size={14} /> Saving...</> : 'Save E/M Config'}
            </button>
          </div>
          {emForm.updated_by && (
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
              Last updated by {emForm.updated_by}{emForm.updated_at && ` on ${new Date(emForm.updated_at).toLocaleDateString()}`}
            </div>
          )}
        </div>
      </>)}

      {/* ── IP / OP Config ── */}
      {tab !== 'EM' && (<>
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Scoring Weights <span style={styles.hint}>(must sum to 100)</span></div>
        <div style={styles.weightGrid}>
          <WeightField label="PDx" value={f.pdx_weight} onChange={v => updateField(tab, 'pdx_weight', v)} />
          <WeightField label="SDx" value={f.sdx_weight} onChange={v => updateField(tab, 'sdx_weight', v)} />
          {tab === 'IP' && <>
            <WeightField label="PCS" value={f.pcs_weight} onChange={v => updateField(tab, 'pcs_weight', v)} />
            <WeightField label="DRG" value={f.drg_weight} onChange={v => updateField(tab, 'drg_weight', v)} />
          </>}
          {tab === 'EDSP' && <>
            <WeightField label="Facility Level" value={f.facility_level_weight}
              onChange={v => updateField(tab, 'facility_level_weight', v)} />
            <WeightField label="Profee Level" value={f.profee_level_weight}
              onChange={v => updateField(tab, 'profee_level_weight', v)} />
          </>}
          {tab === 'OP' && <WeightField label="CPT" value={f.cpt_weight} onChange={v => updateField(tab, 'cpt_weight', v)} />}
          {tab === 'EDSP' && <WeightField label="CPT" value={f.cpt_weight} onChange={v => updateField(tab, 'cpt_weight', v)} />}
        </div>
        <div style={{ fontSize: 13, fontWeight: 700, color: sum === 100 ? '#16a34a' : '#dc2626', marginTop: 6 }}>
          Total: {sum} / 100 {sum === 100 ? '✓' : '⚠ Must equal 100'}
        </div>
      </div>

      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Pass Threshold</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
            value={f.pass_threshold} onChange={e => updateField(tab, 'pass_threshold', parseInt(e.target.value) || 80)} />
          <span style={styles.hint}>% minimum to pass</span>
        </div>
      </div>

      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Overcoding Penalty</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
          <input type="checkbox" checked={f.overcoding_penalty} onChange={e => updateField(tab, 'overcoding_penalty', e.target.checked)} />
          Penalize extra codes submitted beyond the answer key count
        </label>
      </div>

      {tab === 'IP' && (
        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>DRG Auto-Flag Triggers
            <span style={styles.hint}> — any one active trigger flags the row for review</span>
          </div>
          {ALL_DRG_TRIGGERS.map(t => (
            <label key={t.key} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13, padding: '4px 0' }}>
              <input type="checkbox" checked={(f.drg_triggers || []).includes(t.key)} onChange={() => toggleTrigger(t.key)} />
              {t.label}
            </label>
          ))}
        </div>
      )}

      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Scoring Method Availability
          <span style={styles.hint}> — disabled methods cannot be selected when creating a batch</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={f.weighted_enabled ?? true} onChange={e => updateField(tab, 'weighted_enabled', e.target.checked)} />
            <span><strong>Grading Score</strong> enabled (primary method, drives pass/fail)</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={f.dpo_enabled ?? true} onChange={e => updateField(tab, 'dpo_enabled', e.target.checked)} />
            <span><strong>Accuracy (DPO)</strong> enabled (supplementary, shows per-area accuracy %)</span>
          </label>
          {!(f.weighted_enabled ?? true) && !(f.dpo_enabled ?? true) && (
            <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must remain enabled</div>
          )}
        </div>
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Accuracy (DPO) Pass Threshold <span style={styles.hint}>(for supplementary reference only)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
              value={f.dpo_pass_threshold ?? 80} onChange={e => updateField(tab, 'dpo_pass_threshold', parseFloat(e.target.value) || 80)} />
            <span style={styles.hint}>% accuracy — shown alongside results but does not override weighted pass/fail</span>
          </div>
        </div>
        {tab === 'OP' && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
            OP accuracy applies to ED Facility, SDS, Surgery, and Ancillary batches. ED Profee and E/M do not use supplementary accuracy.
          </div>
        )}
        {tab === 'EDSP' && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
            ED Single Path accuracy counts shared Dx, facility/profee levels, and additional CPTs. Diagnosis pointers are not used.
          </div>
        )}
      </div>

      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Master Admin Passphrase *</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <input type={showPassphrase ? 'text' : 'password'} style={{ ...styles.input, width: 220 }}
            placeholder="Enter passphrase to save" value={passphrase} onChange={e => setPassphrase(e.target.value)} />
          <button style={styles.outlineBtn} onClick={() => setShowPassphrase(s => !s)}>{showPassphrase ? 'Hide' : 'Show'}</button>
          <button style={saving ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn} disabled={saving} onClick={handleSave}>
            {saving ? <><Loader size={14} /> Saving...</> : 'Save Config'}
          </button>
        </div>
        {configs?.[tab]?.updated_by && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
            Last updated by {configs[tab].updated_by}{configs[tab].updated_at && ` on ${new Date(configs[tab].updated_at).toLocaleDateString()}`}
          </div>
        )}
      </div>
      </>)}
    </div>
  )
}
