import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Target } from 'lucide-react'
import {
  getAuditByAuditor, getAuditByBatch, getAuditDetection, getAuditOverview,
} from '../../api/auditorApi'
import s from './styles'

/**
 * Not a copy of the coder analytics. Those answer "which codes do people get
 * wrong"; these answer whether an auditor can find an error at all, whether
 * they can leave a correct claim alone, and which kinds of error slip past a
 * cohort.
 *
 * Every rate here prints its denominator. This codebase has already paid once
 * for a percentage that quietly meant something other than what it said.
 */

const TABS = ['Overview', 'Batches', 'Auditors', 'Detection Patterns'] as const
type Tab = typeof TABS[number]

export function AuditAnalytics() {
  const [tab, setTab] = useState<Tab>('Overview')
  const [overview, setOverview] = useState<any>(null)
  const [batches, setBatches] = useState<any[]>([])
  const [auditors, setAuditors] = useState<any[]>([])
  const [detection, setDetection] = useState<any>(null)

  const load = useCallback(async () => {
    try {
      const [o, b, a, d] = await Promise.all([
        getAuditOverview(), getAuditByBatch(), getAuditByAuditor(), getAuditDetection(),
      ])
      setOverview(o); setBatches(b.batches); setAuditors(a.auditors); setDetection(d)
    } catch { toast.error('Could not load audit analytics') }
  }, [])
  useEffect(() => { load() }, [load])

  if (!overview) return <div style={s.empty}>Loading…</div>
  if (!overview.charts) {
    return (
      <div>
        <div style={s.h1}>Audit Analytics</div>
        <div style={s.empty}>
          Nothing scored yet. Run an allocation and have an auditor submit, and these
          figures will fill in.
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={s.h1}>Audit Analytics</div>
      <div style={s.sub}>
        {overview.charts} chart(s) · {overview.auditors} auditor(s) · {overview.batches} batch(es)
      </div>

      <div style={{ display: 'flex', gap: 6, marginTop: 16, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ ...s.toggleChip, ...(tab === t ? s.toggleChipOn : {}) }}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'Overview' && <Overview o={overview} />}
      {tab === 'Batches' && <Rows rows={batches} nameKey="name" subKey="specialty" />}
      {tab === 'Auditors' && <Rows rows={auditors} nameKey="auditor_name" subKey="emp_id" />}
      {tab === 'Detection Patterns' && <Detection d={detection} />}
    </div>
  )
}

// ── overview ─────────────────────────────────────────────────────────────────

function Overview({ o }: { o: any }) {
  return (
    <>
      <div style={s.panel}>
        <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>Headline</span></div>
        <div style={{ padding: '16px' }}>
          <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <Big label="Audit accuracy" value={pct(o.audit_accuracy)} />
            <Big label="Clean charts" value={pct(o.clean_accuracy)} sub={`${o.clean_charts} chart(s) — restraint`} small />
            <Big label="Opportunity charts" value={pct(o.opportunity_accuracy)} sub={`${o.opportunity_charts} chart(s) — detection`} small />
          </div>
          <div style={s.note}>
            The headline averages chart scores; the split beneath it is what tells you
            whether someone is missing errors or inventing them. A passive auditor scores
            full marks on the left and nothing on the right.
          </div>
          {o.verdict_withheld_reason && <div style={{ ...s.warnBox, marginTop: 12 }}>{o.verdict_withheld_reason}</div>}
        </div>
      </div>

      <div style={s.panel}>
        <div style={s.panelHead}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>By what the auditor had to do</span>
        </div>
        <div style={{ padding: '16px' }}>
          <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
            {(['add', 'revise', 'delete'] as const).map(k => (
              <Big key={k} small label={k[0].toUpperCase() + k.slice(1)}
                value={pct(o[k].accuracy)}
                sub={o[k].planted ? `${o[k].found}/${o[k].planted}` : 'none planted'} />
            ))}
            <Big small label="DRG-impacting" value={pct(o.drg_accuracy)}
              sub={o.drg_planted ? `${o.drg_found}/${o.drg_planted}` : 'none planted'} />
            <Big small label="Query calls" value={pct(o.query_accuracy)}
              sub={o.query_charts ? `${o.query_correct}/${o.query_charts}` : 'none authored'} />
          </div>
          <div style={s.note}>
            Pooled — total found over total planted. Roughly three quarters of plantings
            are omissions, so a single figure would read high for someone who only ever
            hunts for missing codes. DRG impact is kept separate rather than blended in as
            a weight.
          </div>
        </div>
      </div>

      <div style={s.panel}>
        <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>Habits</span></div>
        <div style={{ padding: '16px' }}>
          <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
            <Big small label="Findings on nothing" value={String(o.over_calls)}
              sub={`across ${o.charts_with_over_calls} chart(s)`} />
            <Big small label="Found but corrected wrongly" value={String(o.detected_not_corrected)}
              sub="not scored — reported" />
            <Big small label="Opportunities" value={String(o.opportunities)} sub="total planted" />
          </div>
          <div style={s.note}>
            “Found 4 of 4, corrected 2” and “found 2 of 4” both score 50% and are entirely
            different conversations — which is why the second figure is reported rather
            than folded in.
          </div>
        </div>
      </div>
    </>
  )
}

// ── batch / auditor tables ───────────────────────────────────────────────────

function Rows({ rows, nameKey, subKey }: { rows: any[]; nameKey: string; subKey: string }) {
  if (!rows.length) return <div style={s.empty}>Nothing scored yet.</div>
  return (
    <div style={s.panel}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              {['', 'Charts', 'Audit', 'Clean', 'Opportunity', 'Add', 'Revise', 'Delete', 'Over-calls']
                .map(h => <th key={h} style={th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={td}>
                  <div style={{ fontWeight: 700 }}>{r[nameKey]}</div>
                  {r[subKey] && <div style={{ fontSize: 11, color: '#9ca3af' }}>{r[subKey]}</div>}
                </td>
                <td style={td}>{r.charts}</td>
                <td style={{ ...td, fontWeight: 700, color: tone(r.audit_accuracy) }}>{pct(r.audit_accuracy)}</td>
                <td style={td}>{pct(r.clean_accuracy)}</td>
                <td style={{ ...td, color: tone(r.opportunity_accuracy) }}>{pct(r.opportunity_accuracy)}</td>
                <td style={td}>{cell(r.add)}</td>
                <td style={td}>{cell(r.revise)}</td>
                <td style={td}>{cell(r.delete)}</td>
                <td style={td}>{r.over_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '10px 16px' }}>
        <div style={s.note}>
          Audit accuracy averages chart scores; the component columns pool findings over
          plantings, with the counts shown so a rate on two opportunities is not read like
          a rate on twenty. NA means nothing of that type was ever planted.
        </div>
      </div>
    </div>
  )
}

function cell(c: any) {
  if (!c || !c.planted) return <span style={{ color: '#9ca3af' }}>NA</span>
  return <span>{pct(c.accuracy)} <span style={{ color: '#9ca3af', fontSize: 11 }}>({c.found}/{c.planted})</span></span>
}

// ── detection patterns ───────────────────────────────────────────────────────

function Detection({ d }: { d: any }) {
  if (!d || !d.total_plantings) return <div style={s.empty}>Nothing planted and scored yet.</div>
  return (
    <>
      {d.weakest.length > 0 && (
        <div style={s.panel}>
          <div style={s.panelHead}>
            <Target size={14} color="#be185d" />
            <span style={{ fontWeight: 700, fontSize: 13 }}>What to teach next</span>
          </div>
          <div style={{ padding: '14px 16px' }}>
            {d.weakest.map((k: any) => (
              <div key={k.key} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <span style={{ fontWeight: 700, fontSize: 14, color: '#be185d' }}>{pct(k.accuracy)}</span>
                  <span style={{ fontSize: 13 }}>{k.label}</span>
                  <span style={{ fontSize: 11, color: '#9ca3af' }}>{k.found}/{k.planted} caught</span>
                </div>
                <Bar value={k.accuracy || 0} />
              </div>
            ))}
            <div style={s.note}>
              Only kinds planted at least {d.min_for_pattern} times appear here — a
              curriculum should not be built on a single miss.
            </div>
          </div>
        </div>
      )}

      <Bucket title="By kind of error" rows={d.by_kind}
        note="Worst first. This is the report the coder analytics has no equivalent of: it
              says which errors a cohort cannot see, rather than which codes they get wrong." />

      <Bucket title="Real errors versus generated ones" rows={d.by_origin}
        note="Plantings taken from what your own coders actually submitted, against ones
              the system invented. Only the first number describes the job — and it is
              usually the lower of the two." />

      <Bucket title="By section and action" rows={d.by_section}
        note="Where in a chart attention runs out." />

      {d.pcs_characters.length > 0 && (
        <Bucket title="PCS — which character was changed" rows={d.pcs_characters}
          note="A root-operation error and an approach error are different skills. This is
                the only place that distinction is visible." />
      )}
    </>
  )
}

function Bucket({ title, rows, note }: { title: string; rows: any[]; note: string }) {
  if (!rows?.length) return null
  return (
    <div style={s.panel}>
      <div style={s.panelHead}><span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span></div>
      <div style={{ padding: '14px 16px' }}>
        {rows.map(r => (
          <div key={r.key} style={{ marginBottom: 9 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: tone(r.accuracy), minWidth: 52 }}>
                {pct(r.accuracy)}
              </span>
              <span style={{ fontSize: 12.5 }}>{r.label}</span>
              <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 'auto' }}>
                {r.found} caught · {r.missed} missed
                {r.detected_not_corrected ? ` · ${r.detected_not_corrected} corrected wrongly` : ''}
                {' '}of {r.planted}
              </span>
            </div>
            <Bar value={r.accuracy || 0} />
          </div>
        ))}
        <div style={s.note}>{note}</div>
      </div>
    </div>
  )
}

function Bar({ value }: { value: number }) {
  return (
    <div style={{ height: 5, background: '#f3f4f6', borderRadius: 3, marginTop: 4, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${Math.max(0, Math.min(100, value))}%`, background: tone(value), borderRadius: 3 }} />
    </div>
  )
}

function Big({ label, value, sub, small }: { label: string; value: string; sub?: string; small?: boolean }) {
  return (
    <div style={{ minWidth: 104 }}>
      <div style={{ fontSize: small ? 22 : 34, fontWeight: 800, color: value === 'NA' ? '#9ca3af' : '#111', lineHeight: 1.1 }}>
        {value}
      </div>
      <div style={{ fontSize: 11.5, color: '#6b7280', fontWeight: 700, marginTop: 3 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#9ca3af' }}>{sub}</div>}
    </div>
  )
}

/** NA is a real value — a cohort that never met a spurious code has no Delete
 *  accuracy, and printing 0% would say something false about them. */
function pct(v: number | null | undefined) {
  return v === null || v === undefined ? 'NA' : `${v}%`
}

function tone(v: number | null | undefined) {
  if (v === null || v === undefined) return '#9ca3af'
  return v >= 90 ? '#059669' : v >= 70 ? '#d97706' : '#dc2626'
}

const th: React.CSSProperties = {
  textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#6b7280',
  padding: '10px 12px', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap',
}
const td: React.CSSProperties = {
  padding: '10px 12px', borderBottom: '1px solid #f9fafb', whiteSpace: 'nowrap',
}
