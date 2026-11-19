import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'

/**
 * A POA box that knows the CMS exempt list.
 *
 * When the code beside it is POA exempt (`exempt` true, from /codes/describe),
 * the box shows E, greyed and locked, and sets the value to E itself — nobody
 * looks the code up in the CMS list or picks E by hand. If the code is then
 * changed to one that is not exempt, an E this box set is cleared again, so
 * the person must choose rather than inherit a wrong E.
 *
 * `exempt` undefined or null (list not loaded, code unknown, still loading)
 * leaves the box exactly as it always was: nothing is greyed on a guess.
 */
export function PoaSelect({ value, onChange, exempt, options, style, placeholder = 'POA…', disabled }: {
  value: string
  onChange: (v: string) => void
  exempt?: boolean | null
  options: Array<{ value: string; label: string }>
  style?: CSSProperties
  placeholder?: string
  disabled?: boolean
}) {
  const autoSet = useRef(false)
  // Runs after EVERY render, not on dependency change. Several rows can turn
  // exempt in one render, and a parent that rebuilds its list from that
  // render's copy keeps only the last row's E. With dependencies, the lost
  // rows would never retry — their own value never changed. Checked every
  // render, a lost E is simply set again; it stops once every row holds E.
  useEffect(() => {
    if (disabled) return
    if (exempt === true && (value || '').toUpperCase() !== 'E') {
      autoSet.current = true
      onChange('E')
    } else if (exempt === false && autoSet.current && (value || '').toUpperCase() === 'E') {
      autoSet.current = false
      onChange('')
    }
  })

  if (exempt === true) {
    return (
      <div
        title="This code is on the CMS POA exempt list — POA is reported as exempt (E)."
        style={{
          ...style,
          display: 'flex', alignItems: 'center', gap: 6,
          background: '#f3f4f6', color: '#6b7280', borderColor: '#e5e7eb',
          cursor: 'not-allowed', userSelect: 'none',
        }}
      >
        <span style={{ fontWeight: 700, color: '#374151' }}>E</span>
        <span style={{ fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>POA exempt</span>
      </div>
    )
  }
  return (
    <select style={style} value={value} onChange={e => { autoSet.current = false; onChange(e.target.value) }} disabled={disabled}>
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}
