import type { Specialty } from './types'

// Ten specialties, spread deliberately around the hue wheel.
//
// The set had grown by addition and four of them had ended up inside a 20
// degree arc of blue-violet: E/M, IP-DRG, Edits and ED Single Path were 4
// degrees apart at the closest, and IP-DRG and Edits shared a chip fill
// outright. Chips render as `light` filled with `bg` as the text, so an
// identical fill makes two specialties one glance apart.
//
// Minimum separation is now 24 degrees. Most entries barely moved — Ancillary,
// SDS and ED Facility are within a degree of where they were — because the
// crowded arcs were opened up rather than the whole palette reassigned, and a
// colour someone has already learned is worth keeping.
//
// The three ED specialties share a name stem and are the easiest to confuse by
// reading, so they are deliberately far apart by hue rather than adjacent.
//
// Every pairing clears 4.6:1 as text on its own fill, and 5.0:1 as white on the
// solid colour, which is the other way these are used.
export const SPECIALTY_COLORS: Record<Specialty, { bg: string; text: string; border: string; light: string }> = {
  'IP-DRG':          { bg: '#215bca', text: '#fff', border: '#215bca', light: '#dfe9fb' },
  'ED Facility':     { bg: '#c1231f', text: '#fff', border: '#c1231f', light: '#fbdfdf' },
  'ED Profee':       { bg: '#a2561a', text: '#fff', border: '#a2561a', light: '#fbebdf' },
  'SDS':             { bg: '#187691', text: '#fff', border: '#187691', light: '#dff5fb' },
  'Edits':           { bg: '#8421ca', text: '#fff', border: '#8421ca', light: '#f0dffb' },
  'Denials':         { bg: '#886916', text: '#fff', border: '#886916', light: '#fbf4df' },
  'Ancillary':       { bg: '#157f39', text: '#fff', border: '#157f39', light: '#dffbe8' },
  'E/M':             { bg: '#1b6ea7', text: '#fff', border: '#1b6ea7', light: '#dff0fb' },
  'Surgery':         { bg: '#c11f54', text: '#fff', border: '#c11f54', light: '#fbdfe8' },
  'ED Single Path':  { bg: '#b81e8f', text: '#fff', border: '#b81e8f', light: '#fbdff4' },
}

export const DIFFICULTY_COLORS = {
  Beginner:     { bg: '#dcfce7', text: '#166534' },
  Intermediate: { bg: '#fef9c3', text: '#854d0e' },
  Advanced:     { bg: '#fee2e2', text: '#991b1b' },
}

// ── Review screens ────────────────────────────────────────────────────────────
// One vocabulary of result colours for every screen that marks work against a
// key: the practice review (trainer modal, coder results, Excel export) and the
// auditor review. Green is right, red is an error the score paid for, orange is
// something added that the key lacks, amber is a line that matched but differs
// in a detail (POA, modifier, pointer, units). Before this the four screens
// each kept their own greens and reds and a PASS badge in three shades.
export const REVIEW_STATUS = {
  correct:   { label: '✓ Correct',      color: '#047857', bg: '#ecfdf5' },
  wrong:     { label: '✗ Wrong code',   color: '#b91c1c', bg: '#fef2f2' },
  missed:    { label: '✗ Missed',       color: '#b91c1c', bg: '#fef2f2' },
  extra:     { label: '+ Extra',        color: '#9a3412', bg: '#fff7ed' },
  different: { label: '≠ Differs',      color: '#92400e', bg: '#fffbeb' },
  order:     { label: '↕ Order only',   color: '#1e40af', bg: '#eff6ff' },
  info:      { label: '',               color: '#6b7280', bg: 'transparent' },
} as const

/** Score colour on review screens: the 80% pass line, the same everywhere. */
export function reviewScoreColor(score: number | null | undefined) {
  if (score === null || score === undefined) return '#9ca3af'
  return score >= 80 ? REVIEW_STATUS.correct.color : REVIEW_STATUS.missed.color
}

export function passFailStyle(pf: string | null | undefined) {
  return pf === 'PASS' ? REVIEW_STATUS.correct : pf === 'FAIL' ? REVIEW_STATUS.missed : REVIEW_STATUS.info
}
