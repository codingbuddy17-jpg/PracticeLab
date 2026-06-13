import { useState, useEffect } from 'react'
import { Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getScoringConfigs, updateScoringConfig } from '../../api'
import { trainerName } from './shared'
import styles from './styles'

const ALL_DRG_TRIGGERS = [
  { key: 'pdx_mismatch', label: 'PDx code or POA mismatch' },
  { key: 'ccmcc_missing', label: 'CC/MCC SDx from AK missing from coder' },
  { key: 'pcs_undercoded', label: 'PCS under-coded (missed AK procedures)' },
  { key: 'pcs_overcoded', label: 'PCS over-coded (extra procedures)' },
  { key: 'spurious_sdx', label: 'AK has no SDx but coder added SDx' },
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
  const [tab, setTab] = useState<'IP' | 'OP'>('IP')
  const [form, setForm] = useState<any>({})
  const [passphrase, setPassphrase] = useState('')
  const [saving, setSaving] = useState(false)
  const [showPassphrase, setShowPassphrase] = useState(false)

  useEffect(() => { loadConfigs() }, [])

  async function loadConfigs() {
    try {
      const data = await getScoringConfigs()
      setConfigs(data)
      setForm({ IP: { ...data.IP }, OP: { ...data.OP } })
    } catch { toast.error('Failed to load scoring config') }
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
        cpt_weight: tab === 'OP' ? f.cpt_weight : undefined,
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

  if (!form.IP || !form.OP) return <div style={styles.center}><Loader size={24} /></div>

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
        {(['IP', 'OP'] as const).map(t => (
          <button key={t} style={tab === t ? styles.chipActive : styles.chip} onClick={() => setTab(t)}>
            {t === 'IP' ? 'IP-DRG' : 'Outpatient (OP)'}
          </button>
        ))}
      </div>

      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Scoring Weights <span style={styles.hint}>(must sum to 100)</span></div>
        <div style={styles.weightGrid}>
          <WeightField label="PDx" value={f.pdx_weight} onChange={v => updateField(tab, 'pdx_weight', v)} />
          <WeightField label="SDx" value={f.sdx_weight} onChange={v => updateField(tab, 'sdx_weight', v)} />
          {tab === 'IP' && <>
            <WeightField label="PCS" value={f.pcs_weight} onChange={v => updateField(tab, 'pcs_weight', v)} />
            <WeightField label="DRG" value={f.drg_weight} onChange={v => updateField(tab, 'drg_weight', v)} />
          </>}
          {tab === 'OP' && <WeightField label="CPT" value={f.cpt_weight} onChange={v => updateField(tab, 'cpt_weight', v)} />}
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
            <span><strong>Weighted Scoring</strong> enabled (primary method, drives pass/fail)</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={f.dpo_enabled ?? true} onChange={e => updateField(tab, 'dpo_enabled', e.target.checked)} />
            <span><strong>DPO Accuracy</strong> enabled (supplementary, shows per-area accuracy %)</span>
          </label>
          {!(f.weighted_enabled ?? true) && !(f.dpo_enabled ?? true) && (
            <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must remain enabled</div>
          )}
        </div>
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            DPO Pass Threshold <span style={styles.hint}>(for supplementary reference only)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
              value={f.dpo_pass_threshold ?? 80} onChange={e => updateField(tab, 'dpo_pass_threshold', parseFloat(e.target.value) || 80)} />
            <span style={styles.hint}>% accuracy — shown alongside results but does not override weighted pass/fail</span>
          </div>
        </div>
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
    </div>
  )
}
