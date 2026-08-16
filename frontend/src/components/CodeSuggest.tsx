import { useEffect, useRef, useState } from 'react'
import { CodeInfo, searchCodes } from '../api/codesApi'
import { withDot } from '../codeFormat'

/**
 * A code box that finishes the code you have started typing.
 *
 * PREFIX ONLY. Completing a code someone has already decided on saves them the
 * last two characters and the typo that comes with them; searching by
 * description would answer the coding question itself, which is the thing a
 * graded session exists to measure. That line is held in the API — this box
 * cannot search descriptions even if it wanted to.
 *
 * Everything about it is optional. It is an ordinary input that sometimes
 * offers help: the list appears at two characters, closes on Escape, and never
 * appears at all if nobody has run the code-set ingest. Typing straight through
 * it works exactly as it did before this existed, which matters because the
 * suggestions must never be load-bearing.
 */

const MIN_CHARS = 2
const DEBOUNCE_MS = 180

type Props = {
  value: string
  onChange: (v: string) => void
  section?: string
  style?: React.CSSProperties
  placeholder?: string
  maxLength?: number
  autoFocus?: boolean
  upper?: boolean
  onEnter?: () => void
  disabled?: boolean
}

export function CodeSuggest({ value, onChange, section, style, placeholder,
                             maxLength, autoFocus, upper = true, onEnter,
                             disabled }: Props) {
  const [matches, setMatches] = useState<CodeInfo[]>([])
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  // Set while a suggestion is being taken, so the fetch that the resulting
  // onChange would trigger does not immediately reopen the list underneath the
  // code that was just chosen.
  const justPicked = useRef(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (justPicked.current) { justPicked.current = false; return }
    const stem = (value || '').replace(/\./g, '')
    if (stem.length < MIN_CHARS) { setMatches([]); setOpen(false); return }
    // Debounced: a coder types a seven-character PCS code in about a second,
    // and one request per keystroke would be seven for one code.
    let live = true
    const timer = setTimeout(() => {
      searchCodes(stem, section).then(found => {
        if (!live) return
        // An exact and only match is not a suggestion — it is what they typed.
        const useful = found.filter(m => m.code !== stem)
        setMatches(useful)
        setCursor(0)
        setOpen(useful.length > 0)
      })
    }, DEBOUNCE_MS)
    return () => { live = false; clearTimeout(timer) }
  }, [value, section])

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  function take(code: string) {
    justPicked.current = true
    onChange(code)
    setOpen(false)
    setMatches([])
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || !matches.length) {
      // Enter still belongs to the form when there is no list to choose from.
      if (e.key === 'Enter' && onEnter) { e.preventDefault(); onEnter() }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault(); setCursor(c => (c + 1) % matches.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault(); setCursor(c => (c - 1 + matches.length) % matches.length)
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      // Enter takes the highlighted code. Tab does too, then carries on to the
      // next field — the same thing every other autocomplete does.
      e.preventDefault()
      take(withDot(matches[cursor].code, matches[cursor].system))
    } else if (e.key === 'Escape') {
      e.preventDefault(); setOpen(false)
    }
  }

  return (
    <div ref={box} style={{ position: 'relative' }}>
      <input
        style={style}
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        autoFocus={autoFocus}
        disabled={disabled}
        autoComplete="off"
        onChange={e => onChange(upper ? e.target.value.toUpperCase() : e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
      />
      {open && (
        <ul style={sg.list}>
          {matches.map((m, i) => (
            <li
              key={m.code}
              onMouseDown={e => { e.preventDefault(); take(withDot(m.code, m.system)) }}
              onMouseEnter={() => setCursor(i)}
              style={{ ...sg.item, background: i === cursor ? '#eef2ff' : '#fff' }}
            >
              <span style={sg.code}>{withDot(m.code, m.system)}</span>
              <span style={sg.desc}>{m.description}</span>
              {/* A category heading is a real row but not something anyone
                  codes to, so it is offered and marked rather than hidden. */}
              {!m.billable && <span style={sg.header}>heading</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const sg = {
  list: {
    position: 'absolute', top: '100%', left: 0, zIndex: 40,
    minWidth: '100%', maxWidth: 420, maxHeight: 240, overflowY: 'auto',
    margin: '3px 0 0', padding: 4, listStyle: 'none',
    background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
    boxShadow: '0 8px 24px rgba(15,23,42,0.12)',
  },
  item: {
    display: 'flex', alignItems: 'baseline', gap: 8,
    padding: '5px 8px', borderRadius: 5, cursor: 'pointer',
  },
  code: {
    fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: '#111',
    flexShrink: 0,
  },
  desc: {
    fontSize: 11, color: '#4b5563', overflow: 'hidden',
    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  header: {
    fontSize: 9, color: '#9ca3af', border: '1px solid #e5e7eb',
    borderRadius: 4, padding: '0 4px', marginLeft: 'auto', flexShrink: 0,
  },
} as const
