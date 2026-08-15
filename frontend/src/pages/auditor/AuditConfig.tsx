import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Save } from 'lucide-react'
import { getAuditConfig, updateAuditConfig } from '../../api/auditorApi'
import s from './styles'

const MIX_LABELS: Record<string, string> = {
  mix_omit_sdx: 'Omit a secondary diagnosis',
  mix_omit_proc: 'Omit a procedure',
  mix_modifier_missing: 'Modifier missing',
  mix_modifier_wrong: 'Modifier wrong',
  mix_substitute: 'Substitute a diagnosis (prefix family)',
  mix_substitute_pcs: 'Change one PCS character',
  mix_swap_pdx: 'Swap principal with a secondary',
  mix_units: 'Wrong units',
  mix_poa: 'Flip a POA indicator',
  mix_spurious: 'Add a spurious code',
}

const REVENUE_ELEMENTS = [
  { key: 'pdx', label: 'Principal diagnosis' },
  { key: 'ccmcc_sdx', label: 'CC/MCC secondary' },
  { key: 'pcs', label: 'PCS' },
  { key: 'cpt', label: 'CPT' },
  { key: 'modifier', label: 'Modifier' },
  { key: 'units', label: 'Units' },
]

export function AuditConfig({ trainer }: { trainer: string }) {
  const [cfg, setCfg] = useState<any>(null)
  const [passphrase, setPassphrase] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setCfg(await getAuditConfig()) }
    catch { toast.error('Could not load audit config') }
  }, [])
  useEffect(() => { load() }, [load])

  if (!cfg) return <div style={s.empty}>Loading…</div>

  const componentTotal = cfg.add_weight + cfg.revise_weight + cfg.delete_weight
  const mixTotal = Object.values(cfg.mix as Record<string, number>)
    .reduce((a, b) => a + (b || 0), 0)

  function set(field: string, value: unknown) {
    setCfg((c: any) => ({ ...c, [field]: value }))
  }
  function setMix(field: string, value: number) {
    setCfg((c: any) => ({ ...c, mix: { ...c.mix, [field]: value } }))
  }
  function toggleRevenue(key: string) {
    const cur: string[] = cfg.revenue_elements || []
    set('revenue_elements', cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key])
  }

  async function save() {
    if (!passphrase.trim()) return toast.error('Passphrase required')
    if (componentTotal !== 100) return toast.error(`Add + Revise + Delete must total 100 (currently ${componentTotal})`)
    if (mixTotal !== 100) return toast.error(`Error weights must total 100 (currently ${mixTotal})`)
    setBusy(true)
    try {
      setCfg(await updateAuditConfig({ ...cfg, updated_by: trainer, passphrase }))
      toast.success('Saved — applies to audits scored from now on')
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'Could not save')
    }
    setBusy(false)
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={s.h1}>Audit Scoring</div>
      <div style={s.sub}>
        Changes apply to audits scored afterwards. Results already stored keep the scores
        they were given, so tuning a weight can never restate a closed batch.
      </div>

      <Block title="What the score is made of"
        note="Renormalised over the components a chart actually carries — a chart with no
              spurious codes splits Delete's share between Add and Revise rather than
              penalising an opportunity that never existed.">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Num label="Add" value={cfg.add_weight} onChange={v => set('add_weight', v)} />
          <Num label="Revise" value={cfg.revise_weight} onChange={v => set('revise_weight', v)} />
          <Num label="Delete" value={cfg.delete_weight} onChange={v => set('delete_weight', v)} />
          <Total n={componentTotal} />
        </div>
      </Block>

      <Block title="Cost of raising a finding on something that was correct"
        note="One deduction per chart, sized by the worst category touched — not one per
              finding. The same on clean charts and charts carrying errors.">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Num label="Revenue-impacting %" value={cfg.over_call_revenue_pct}
            onChange={v => set('over_call_revenue_pct', v)} />
          <Num label="Non-revenue %" value={cfg.over_call_non_revenue_pct}
            onChange={v => set('over_call_non_revenue_pct', v)} />
        </div>
        <div style={{ ...s.label, marginTop: 14 }}>Which elements count as revenue-impacting</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {REVENUE_ELEMENTS.map(e => (
            <button key={e.key} onClick={() => toggleRevenue(e.key)}
              style={{ ...s.toggleChip, ...((cfg.revenue_elements || []).includes(e.key) ? s.toggleChipOn : {}) }}>
              {e.label}
            </button>
          ))}
        </div>
      </Block>

      <Block title="Physician query"
        note="Binary per chart, so a fixed deduction rather than a fourth weighted
              component. Only scoreable where a trainer authored the answer.">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Num label="Missed a needed query %" value={cfg.query_missed_pct}
            onChange={v => set('query_missed_pct', v)} />
          <Num label="Raised an unnecessary one %" value={cfg.query_unnecessary_pct}
            onChange={v => set('query_unnecessary_pct', v)} />
        </div>
      </Block>

      <Block title="Passing"
        note="The verdict is decided on the Audit Score — the Error Detection Rate and
              the Review Score blended by the weights below, renormalised if a session
              has only one of them. Neither works alone: detection is quantised by error
              count, and review starts high because most lines on any chart are correct.
              Judged on the session, never per chart.">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Num label="Pass threshold %" value={cfg.pass_threshold}
            onChange={v => set('pass_threshold', v)} />
          <Num label="Min code lines for a verdict" value={cfg.min_review_opportunities}
            onChange={v => set('min_review_opportunities', v)} width={120} />
          <Num label="Detection weight %" value={cfg.detection_weight}
            onChange={v => set('detection_weight', v)} />
          <Num label="Review weight %" value={cfg.review_weight}
            onChange={v => set('review_weight', v)} />
        </div>
      </Block>

      <Block title="How the system introduces errors"
        note="Weighted from observed audit practice: omissions dominate, and secondary
              diagnoses are what coders rush. Must total 100; renormalised per chart over
              the errors that chart can actually support.">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
          {Object.keys(MIX_LABELS).map(f => (
            <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <input style={{ ...s.input, width: 64 }} type="number" min={0}
                value={cfg.mix[f] ?? 0}
                onChange={e => setMix(f, parseInt(e.target.value) || 0)} />
              <span style={{ fontSize: 12.5, color: '#374151' }}>{MIX_LABELS[f]}</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10 }}><Total n={mixTotal} /></div>
      </Block>

      <Block title="Density and sources"
        note="No ceiling applies to errors you author yourself — a set you wrote has a
              reason behind it. These govern generation only.">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Num label="Max errors per chart" value={cfg.max_auto_plantings}
            onChange={v => set('max_auto_plantings', v)} width={110} />
          <Num label="Max share of a section %" value={cfg.max_section_share}
            onChange={v => set('max_section_share', v)} width={110} />
          <Num label="CC/MCC preference" value={cfg.ccmcc_preference}
            onChange={v => set('ccmcc_preference', v)} width={110} />
        </div>
      </Block>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 20, flexWrap: 'wrap' }}>
        <input style={{ ...s.input, width: 220 }} type="password" placeholder="Passphrase"
          value={passphrase} onChange={e => setPassphrase(e.target.value)} />
        <button style={{ ...s.primaryBtn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={save}>
          <Save size={15} /> {busy ? 'Saving…' : 'Save configuration'}
        </button>
      </div>
    </div>
  )
}

function Block({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <div style={s.panel}>
      <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span></div>
      <div style={{ padding: '14px 16px' }}>
        {children}
        <div style={s.note}>{note}</div>
      </div>
    </div>
  )
}

function Num({ label, value, onChange, width = 84 }: {
  label: string; value: number; onChange: (n: number) => void; width?: number
}) {
  return (
    <div>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 3 }}>{label}</div>
      <input style={{ ...s.input, width }} type="number" min={0} value={value ?? 0}
        onChange={e => onChange(Math.max(0, parseInt(e.target.value) || 0))} />
    </div>
  )
}

function Total({ n }: { n: number }) {
  return (
    <span style={{ fontSize: 12.5, fontWeight: 700, color: n === 100 ? '#059669' : '#dc2626' }}>
      Total {n}{n !== 100 ? ' — must be 100' : ' ✓'}
    </span>
  )
}
