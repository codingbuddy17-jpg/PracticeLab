import { useEffect, useRef, useState } from 'react'
import { CodeInfo, describeCodes } from '../api/codesApi'

/**
 * Descriptions for whatever codes are currently on screen.
 *
 * Batched and cached rather than fetched per code. A claim carries ten or
 * twenty codes and a coder retypes one of them a character at a time, so the
 * naive version would be a request per code per keystroke. This asks only for
 * codes it has never seen, and keeps what it learns for the life of the screen
 * — a code's description does not change while someone is looking at it.
 *
 * Codes that come back unknown are remembered as unknown, so an unrecognised
 * code is asked about once rather than on every render.
 */
export function useCodeDescriptions(codes: string[], section?: string) {
  const cache = useRef<Record<string, CodeInfo | null>>({})
  const inFlight = useRef<Set<string>>(new Set())
  const [, bump] = useState(0)

  const wanted = Array.from(new Set(
    codes.map(c => (c || '').trim().toUpperCase().replace(/\./g, '')).filter(Boolean)))
  const key = wanted.join(',')

  useEffect(() => {
    const missing = wanted.filter(
      c => !(c in cache.current) && !inFlight.current.has(c))
    if (!missing.length) return
    missing.forEach(c => inFlight.current.add(c))
    let cancelled = false
    describeCodes(missing, section).then(found => {
      if (cancelled) return
      missing.forEach(c => {
        // null, not undefined: "asked and there is none" is different from
        // "not asked yet", and only the second should trigger another request.
        cache.current[c] = found[c] || null
        inFlight.current.delete(c)
      })
      bump(n => n + 1)
    })
    return () => { cancelled = true; missing.forEach(c => inFlight.current.delete(c)) }
  }, [key, section])   // eslint-disable-line react-hooks/exhaustive-deps

  return (code: string): CodeInfo | null => {
    const bare = (code || '').trim().toUpperCase().replace(/\./g, '')
    return bare ? (cache.current[bare] ?? null) : null
  }
}
