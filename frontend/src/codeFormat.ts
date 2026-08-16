/**
 * Shape checks for the codes a coder or an auditor types.
 *
 * One module, used by both working screens, because a rule that lives in two
 * places drifts — the specialty list already proved that here.
 *
 * These are FORMAT checks, not validity checks. Nothing here knows whether a
 * code exists, only whether it is shaped like the kind of code that box wants.
 * That is the whole intent: catch `J189` for `J18.9` and a four-digit CPT,
 * which score as wrong answers and quietly contaminate the measurement, while
 * staying out of the way of a real code this file has never heard of.
 *
 * So code checks WARN and never block. A new code set, a revision, or a
 * legitimate oddity must not be able to lock someone out of submitting their
 * work — this is a training tool, not a claims scrubber. Units and diagnosis
 * pointers are the exception and do block, because there is no such thing as a
 * non-numeric unit count.
 */

export type Check = { ok: boolean; hint?: string }

const OK: Check = { ok: true }
const bad = (hint: string): Check => ({ ok: false, hint })

/**
 * ICD-10-CM: a letter, a digit, one alphanumeric, then up to four more, with
 * or without the decimal point. `J18.9`, `J189`, `S72.001A`, `Z3A.01`.
 *
 * The dot really is optional, which it was not until a coder took a code from
 * the suggestion list and was told it looked wrong. Grading has always
 * stripped the point before comparing (norm_dx), and the form has always said
 * "dot optional" — the check was the only thing that disagreed, which is the
 * copy-describes-behaviour-the-code-lost trap in a third guise.
 *
 * Seven characters is the ceiling ignoring the dot — the dot is punctuation,
 * not a character of the code, which is why a length check alone gets this
 * wrong in both directions.
 */
const DX = /^[A-TV-Z][0-9][0-9A-Z](\.?[0-9A-Z]{1,4})?$/

/**
 * ICD-10-PCS: exactly seven characters, each a digit or a letter — NOT seven
 * digits. `0DTJ4ZZ`. I and O are excluded throughout the code set precisely
 * because they read as 1 and 0.
 */
const PCS = /^[0-9A-HJ-NP-Z]{7}$/

/**
 * CPT and HCPCS, all five characters:
 *   99213   Category I
 *   3006F   Category II, always ends F
 *   0075T   Category III, always ends T
 *   J1885   HCPCS Level II, a letter then four digits
 * "Five digits" would reject the last three, which are ordinary working codes.
 */
const CPT = /^(?:[0-9]{5}|[0-9]{4}[FTMU]|[A-CEGHJ-MPQRSTVW][0-9]{4})$/

/** Two characters. Often digits (25, 59) but just as often letters (LT, JW). */
const MODIFIER = /^[0-9A-Z]{2}$/

export function checkDx(raw: string): Check {
  const v = (raw || '').trim().toUpperCase()
  if (!v) return OK
  if (!DX.test(v)) return bad('Diagnosis codes look like J18.9 or S72.001A')
  return OK
}

export function checkPcs(raw: string): Check {
  const v = (raw || '').trim().toUpperCase()
  if (!v) return OK
  if (!PCS.test(v)) return bad('PCS codes are exactly 7 characters, e.g. 0DTJ4ZZ')
  return OK
}

export function checkCpt(raw: string): Check {
  const v = (raw || '').trim().toUpperCase()
  if (!v) return OK
  if (!CPT.test(v)) return bad('CPT codes are 5 characters, e.g. 99213, 0075T or J1885')
  return OK
}

export function checkModifier(raw: string): Check {
  const v = (raw || '').trim().toUpperCase()
  if (!v) return OK
  if (!MODIFIER.test(v)) return bad('Modifiers are 2 characters, e.g. 25 or LT')
  return OK
}

/** Blocking: a unit count is a whole number of times a service was performed. */
export function checkUnits(raw: string): Check {
  const v = (raw || '').trim()
  if (!v) return OK
  if (!/^[0-9]+$/.test(v)) return bad('Units must be a whole number')
  if (Number(v) < 1) return bad('Units must be at least 1')
  if (Number(v) > 999) return bad('Units above 999 are almost certainly a typo')
  return OK
}

/**
 * Blocking: numeric, comma separated, at most four — the same rule the coder
 * form's pointer parser already applies. Legacy letters A–L are accepted on
 * the way in and shown back as numbers, so old habits still work.
 */
export function checkPointers(raw: string): Check {
  const v = (raw || '').trim()
  if (!v) return OK
  const parts = v.toUpperCase().split(/[,\s]+/).filter(Boolean)
  if (parts.length > 4) return bad('At most 4 pointers per line')
  for (const p of parts) {
    const n = /^[A-L]$/.test(p) ? p.charCodeAt(0) - 64 : Number(p)
    if (!Number.isInteger(n) || n < 1 || n > 12) {
      return bad('Pointers are numbers 1-12, separated by commas')
    }
  }
  return OK
}

/**
 * The right check for a field, given the section it sits in. Sections come
 * from the API per specialty, so this maps rather than assumes: a PCS box in
 * an inpatient form and a CPT box in a surgery form are both "code".
 */
export function checkField(section: string, field: string, value: string): Check {
  const f = (field || 'code').toLowerCase()
  if (f === 'units') return checkUnits(value)
  if (f === 'modifier') return checkModifier(value)
  if (f === 'pointers' || f === 'dx_pointers') return checkPointers(value)
  if (f === 'poa' || f === 'ccmcc') return OK
  const s = (section || '').toUpperCase()
  if (s === 'PCS') return checkPcs(value)
  if (s === 'CPT') return checkCpt(value)
  if (s === 'PDX' || s === 'SDX') return checkDx(value)
  return OK
}

/** Whether a failed check should stop submission, or merely be pointed at. */
export function isBlocking(field: string): boolean {
  const f = (field || '').toLowerCase()
  return f === 'units' || f === 'pointers' || f === 'dx_pointers'
}


/**
 * The dotted form of a code, for putting into a box a person will read.
 *
 * Codes are stored and compared without the point, so a suggestion list built
 * from the code tables offers `M180`. That is a legal thing to type — grading
 * strips the point — but it is not how anyone writes a diagnosis, and it is
 * not how it appears on the answer key. Inserting `M18.0` matches both.
 *
 * ICD-10-CM only. PCS and HCPCS codes have no decimal point, and adding one
 * would produce something that is not a code at all.
 */
export function withDot(code: string, system?: string): string {
  const bare = (code || '').trim().toUpperCase().replace(/\./g, '')
  if (system && system !== 'ICD10CM') return bare
  if (bare.length <= 3 || !/^[A-TV-Z][0-9][0-9A-Z]/.test(bare)) return bare
  return bare.slice(0, 3) + '.' + bare.slice(3)
}
