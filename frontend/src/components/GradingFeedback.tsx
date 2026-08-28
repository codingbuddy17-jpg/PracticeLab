/**
 * What went wrong on one graded chart, grouped so it can be read.
 *
 * The old list was one flat run of lines reading
 *   • [SDx] Wrong_POA — submitted: Z93.1 | expected: Z93.1
 * which says a code is wrong while showing the same code on both sides, gives
 * no hint that the POA is the thing that differs, and mixes diagnoses,
 * procedures and over-coding into one undifferentiated column.
 *
 * Three things fix that. Findings are grouped by what they are about, so a
 * coder sees "four POA errors" rather than four lines among twelve. Each kind
 * of finding says the thing that is actually wrong — a POA error compares POA
 * values, not codes. And a code that carries CC or MCC weight is marked,
 * because on an inpatient chart that is what moves the DRG, and it is the
 * difference between a scoring slip and a reimbursement one.
 */

const SECTION_STYLE: Record<string, { label: string; fg: string; bg: string; line: string }> = {
  PDx: { label: 'Principal Diagnosis', fg: '#9333ea', bg: '#faf5ff', line: '#e9d5ff' },
  POA: { label: 'Present on Admission', fg: '#0369a1', bg: '#f0f9ff', line: '#bae6fd' },
  SDx: { label: 'Secondary Diagnoses', fg: '#0f766e', bg: '#f0fdfa', line: '#99f6e4' },
  PCS: { label: 'Procedures', fg: '#b45309', bg: '#fffbeb', line: '#fde68a' },
  CPT: { label: 'CPT', fg: '#be185d', bg: '#fdf2f8', line: '#fbcfe8' },
  DRG: { label: 'DRG', fg: '#dc2626', bg: '#fef2f2', line: '#fecaca' },
}
const FALLBACK = { label: 'Other', fg: '#475569', bg: '#f8fafc', line: '#e2e8f0' }

export type Finding = {
  section: string
  issue?: string
  issue_type?: string
  ak_code?: string
  coder_code?: string
  detail?: string
}

/** "POA: Y vs N" — the grader's own wording for the two values. */
function poaPair(detail?: string): { expected: string; submitted: string } | null {
  const m = /POA:\s*([A-Z0-9]*)\s*vs\s*([A-Z0-9]*)/i.exec(detail || '')
  return m ? { expected: m[1] || '—', submitted: m[2] || '—' } : null
}

/** CC / MCC weight for a code, from the answer key that was graded against. */
function ccmccOf(code: string | undefined, key: any[]): string | null {
  if (!code || !Array.isArray(key)) return null
  const norm = (c: string) => (c || '').replace(/[.\s]/g, '').toUpperCase()
  const hit = key.find((k: any) => norm(k?.code) === norm(code))
  const v = (hit?.ccmcc || '').toUpperCase()
  return v === 'CC' || v === 'MCC' ? v : null
}

function Code({ children, muted }: { children: any; muted?: boolean }) {
  return (
    <code style={{
      fontSize: 11.5, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      background: muted ? 'transparent' : 'rgba(0,0,0,0.045)',
      padding: muted ? 0 : '1px 5px', borderRadius: 4,
      color: muted ? '#9ca3af' : '#111',
    }}>{children}</code>
  )
}

function Weight({ value }: { value: string }) {
  // MCC outranks CC and moves the DRG further, so they are not the same badge.
  const mcc = value === 'MCC'
  return (
    <span title={mcc ? 'Major complication or comorbidity — moves the DRG' : 'Complication or comorbidity — can move the DRG'}
      style={{
        fontSize: 9.5, fontWeight: 800, letterSpacing: 0.3, padding: '1px 5px',
        borderRadius: 4, marginLeft: 6,
        background: mcc ? '#fee2e2' : '#fef3c7',
        color: mcc ? '#b91c1c' : '#92400e',
        border: `1px solid ${mcc ? '#fca5a5' : '#fcd34d'}`,
      }}>{value}</span>
  )
}

function Row({ f, keyList, describe }: {
  f: Finding; keyList: any[]; describe?: (code: string, section: string) => { description: string } | null
}) {
  const issue = f.issue || f.issue_type || ''
  const poa = poaPair(f.detail)
  const weight = ccmccOf(f.ak_code || f.coder_code, keyList)
  const label = issue.replace(/_/g, ' ')

  let body
  if (poa) {
    // The code is right; the POA is not. Comparing codes here says nothing.
    body = (
      <>
        <Code>{f.coder_code || f.ak_code}</Code>
        <span style={{ color: '#6b7280', margin: '0 8px' }}>coded</span>
        <Code>{poa.submitted}</Code>
        <span style={{ color: '#6b7280', margin: '0 6px' }}>→ should be</span>
        <Code>{poa.expected}</Code>
      </>
    )
  } else if (issue === 'Missed') {
    body = <><span style={{ color: '#6b7280', marginRight: 8 }}>not coded</span><Code>{f.ak_code}</Code></>
  } else if (issue === 'Over_coded') {
    body = <span style={{ color: '#6b7280' }}>{f.detail || 'extra code(s) submitted'}</span>
  } else {
    body = (
      <>
        <Code>{f.coder_code || '—'}</Code>
        <span style={{ color: '#6b7280', margin: '0 6px' }}>→ should be</span>
        <Code>{f.ak_code || '—'}</Code>
        {f.detail && <span style={{ color: '#9ca3af', marginLeft: 8, fontSize: 11 }}>{f.detail}</span>}
      </>
    )
  }

  // What the codes MEAN, under the finding rather than inside it: the line
  // stays scannable, and two long descriptions read better stacked than run
  // together. A code with no description simply has no line — CPT is the usual
  // case, those being AMA-licensed and absent here.
  const sect = f.section || ''
  const said = describe && f.coder_code ? describe(f.coder_code, sect) : null
  const meant = describe && f.ak_code && f.ak_code !== f.coder_code ? describe(f.ak_code, sect) : null

  return (
    <div style={{ padding: '4px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 9.5, fontWeight: 800, letterSpacing: 0.3, textTransform: 'uppercase',
          color: '#6b7280', background: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 4, padding: '1px 5px', minWidth: 68, textAlign: 'center',
        }}>{label}</span>
        <span style={{ display: 'flex', alignItems: 'center' }}>{body}</span>
        {weight && <Weight value={weight} />}
      </div>
      {(said || meant) && (
        <div style={{ marginLeft: 78, marginTop: 2, display: 'flex', flexDirection: 'column', gap: 1 }}>
          {said && <div style={{ fontSize: 11, color: '#6b7280' }}>
            <Code muted>{f.coder_code}</Code> {said.description}</div>}
          {meant && <div style={{ fontSize: 11, color: '#6b7280' }}>
            <Code muted>{f.ak_code}</Code> {meant.description}</div>}
        </div>
      )}
    </div>
  )
}

export function GradingFeedback({ feedback, sdxKey = [], pdxKey = [], describe }: {
  feedback: Finding[]
  sdxKey?: any[]
  pdxKey?: any[]
  /** Optional code lookup. The coder's own results screen shows what each
      code means; the trainer's batch view does not need it. */
  describe?: (code: string, section: string) => { description: string } | null
}) {
  if (!feedback?.length) return null

  // POA errors are pulled out of their section: they are their own kind of
  // mistake with their own coaching, and burying them among missed codes was
  // what made twelve findings unreadable.
  const buckets: Record<string, Finding[]> = {}
  for (const f of feedback) {
    const issue = f.issue || f.issue_type || ''
    const bucket = issue === 'Wrong_POA' ? 'POA' : (f.section || 'Other')
    ;(buckets[bucket] ||= []).push(f)
  }
  const order = ['PDx', 'POA', 'SDx', 'PCS', 'CPT', 'DRG']
  const groups = Object.keys(buckets).sort(
    (a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99))
  const keyList = [...(pdxKey || []), ...(sdxKey || [])]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
      {groups.map(name => {
        const s = SECTION_STYLE[name] || FALLBACK
        const rows = buckets[name]
        return (
          <div key={name} style={{
            background: s.bg, border: `1px solid ${s.line}`, borderLeft: `3px solid ${s.fg}`,
            borderRadius: 8, padding: '8px 12px',
          }}>
            <div style={{
              fontSize: 10, fontWeight: 800, letterSpacing: 0.5, textTransform: 'uppercase',
              color: s.fg, marginBottom: 4,
            }}>
              {s.label}
              <span style={{ fontWeight: 700, marginLeft: 6, opacity: 0.75 }}>
                {rows.length} {rows.length === 1 ? 'finding' : 'findings'}
              </span>
            </div>
            {rows.map((f, i) => <Row key={i} f={f} keyList={keyList} describe={describe} />)}
          </div>
        )
      })}
    </div>
  )
}
