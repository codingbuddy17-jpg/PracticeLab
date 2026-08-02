import { useState, useEffect, useRef } from 'react'
import { Search, X, AlertTriangle } from 'lucide-react'
import { searchCoders, type CoderDirectoryEntry } from '../api'

/**
 * Server-side coder search.
 *
 * Replaces a <datalist> fed from the coder-matrix endpoint, which had two
 * problems: it rendered every coder into the DOM at once, and its source is
 * restricted to CLOSED, non-direct batches — so anyone appearing only in an
 * open batch or a direct assignment could not be selected at all.
 *
 * Selecting returns emp_id alongside the name, because emp_id is the stable
 * identity: free-text names fork one person's history across spellings and
 * merge two people who happen to share a name.
 */
export function CoderPicker({
  value, empId, onSelect, placeholder = 'Search coder by name or Emp ID…',
  width = 300, allowFreeText = false, autoFocus = false,
}: {
  value: string
  empId?: string | null
  onSelect: (coderName: string, empId: string | null) => void
  placeholder?: string
  width?: number | string
  /** Batch enrolment adds people who are not in the directory yet. */
  allowFreeText?: boolean
  autoFocus?: boolean
}) {
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<CoderDirectoryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setQuery(value) }, [value])

  // Debounced so typing does not fire a request per keystroke
  useEffect(() => {
    if (!open) return
    const id = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await searchCoders(query.trim() || undefined, 25)
        setResults(r.coders)
        setTotal(r.total)
        setHighlight(0)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 220)
    return () => clearTimeout(id)
  }, [query, open])

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function choose(c: CoderDirectoryEntry) {
    setQuery(c.coder_name)
    onSelect(c.coder_name, c.emp_id)
    setOpen(false)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight(h => Math.min(h + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') {
      if (results[highlight]) { e.preventDefault(); choose(results[highlight]) }
      else if (allowFreeText && query.trim()) { setOpen(false); onSelect(query.trim(), null) }
    } else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={boxRef} style={{ position: 'relative', width }}>
      <div style={{ position: 'relative' }}>
        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af', pointerEvents: 'none' }} />
        <input
          style={{
            width: '100%', height: 38, padding: '0 30px', border: '1px solid #d1d5db',
            borderRadius: 8, fontSize: 13, outline: 'none', boxSizing: 'border-box',
          }}
          placeholder={placeholder}
          value={query}
          autoFocus={autoFocus}
          onChange={e => { setQuery(e.target.value); setOpen(true); if (allowFreeText) onSelect(e.target.value, null) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); onSelect('', null); setOpen(false) }}
            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 0, display: 'flex' }}
            title="Clear"
          ><X size={14} /></button>
        )}
      </div>

      {/* Absolutely positioned so it does not add to the control's height.
          In flow it made the picker taller the moment a coder was selected,
          and any row centred on the picker — the Look Up and export buttons —
          shifted down to re-centre against the taller block. */}
      <div style={{
        position: 'absolute', top: '100%', left: 0, marginTop: 3,
        fontSize: 11, color: '#6b7280', whiteSpace: 'nowrap',
        visibility: empId && !open ? 'visible' : 'hidden',
      }}>
        Emp ID: {empId || '\u00a0'}
      </div>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, zIndex: 50,
          background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.10)', maxHeight: 300, overflowY: 'auto',
        }}>
          {loading && <div style={{ padding: '10px 12px', fontSize: 12, color: '#9ca3af' }}>Searching…</div>}

          {!loading && results.length === 0 && (
            <div style={{ padding: '10px 12px', fontSize: 12, color: '#9ca3af' }}>
              {allowFreeText
                ? 'No match — press Enter to use this name as a new coder'
                : 'No coder matches that search'}
            </div>
          )}

          {results.map((c, i) => (
            <div
              key={`${c.emp_id || c.coder_name}-${i}`}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => choose(c)}
              style={{
                padding: '8px 12px', cursor: 'pointer',
                background: i === highlight ? '#f1f5f9' : '#fff',
                borderBottom: '1px solid #f8fafc',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{c.coder_name}</span>
                {c.emp_id && (
                  <span style={{ fontSize: 11, background: '#eef2ff', color: '#4f46e5', borderRadius: 4, padding: '1px 6px', fontWeight: 700 }}>
                    {c.emp_id}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                {c.result_count} result{c.result_count !== 1 ? 's' : ''}
                {c.last_activity && ` · last ${new Date(c.last_activity).toLocaleDateString()}`}
                {c.result_count === 0 && ' · not yet graded'}
              </div>
              {/* One person spelled several ways — show it rather than let the
                  trainer inherit a split history without knowing. */}
              {c.name_variants.length > 1 && (
                <div style={{ fontSize: 10.5, color: '#b45309', marginTop: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <AlertTriangle size={11} /> also recorded as {c.name_variants.filter(v => v !== c.coder_name).join(', ')}
                </div>
              )}
            </div>
          ))}

          {!loading && total > results.length && (
            <div style={{ padding: '6px 12px', fontSize: 11, color: '#9ca3af', borderTop: '1px solid #f1f5f9' }}>
              Showing {results.length} of {total} — keep typing to narrow
            </div>
          )}
        </div>
      )}
    </div>
  )
}
