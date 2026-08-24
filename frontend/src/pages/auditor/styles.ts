import type { CSSProperties } from 'react'
import pl from '../practicelab/styles'

/**
 * The auditor screens reuse PracticeLab's style definitions rather than
 * declaring their own.
 *
 * They were written standalone first, which is why inputs, chips and buttons
 * came out subtly different sizes from the coder screens doing the same job.
 * Sharing the definitions makes divergence impossible: a control that means
 * the same thing in both modules IS the same control.
 *
 * Only genuinely new things are declared below — audit key rows, ageing group
 * headers, and the accents that mark this module apart.
 */
const auditorOnly: Record<string, CSSProperties> = {
  // Aliases, so existing markup resolves to the shared definitions.
  h1: pl.sectionTitle,
  sub: pl.helpText,
  ghostBtn: pl.outlineBtn,
  dangerBtn: pl.destructiveOutlineBtn,
  toggleChip: pl.chip,
  toggleChipOn: pl.chipActive,

  note: { fontSize: 11.5, color: '#9ca3af', marginTop: 6, lineHeight: 1.5 },
  rowBetween: {
    display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
    gap: 16, flexWrap: 'wrap',
  },
  listRow: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px',
    border: '1px solid #e5e7eb', borderRadius: 10, background: '#fff',
    cursor: 'pointer', textAlign: 'left', width: '100%', flexWrap: 'wrap',
  },
  backBtn: {
    display: 'flex', alignItems: 'center', gap: 4, border: 'none',
    background: 'none', color: '#6b7280', fontSize: 13, cursor: 'pointer',
    padding: 0, marginBottom: 14,
  },
  linkBtn: {
    display: 'inline-flex', alignItems: 'center', gap: 5, border: 'none',
    background: 'none', color: '#4f46e5', fontSize: 12, fontWeight: 600,
    cursor: 'pointer', padding: 0,
  },
  iconBtn: {
    border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af',
    padding: 3, display: 'flex',
  },

  // A status badge, distinct from pl.chip which is a clickable filter.
  tag: {
    fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6,
    background: '#ede9fe', color: '#4f46e5', whiteSpace: 'nowrap',
  },

  panel: {
    border: '1px solid #e5e7eb', borderRadius: 12, background: '#fff',
    marginTop: 16, overflow: 'hidden',
  },
  panelHead: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
    background: '#fafafa', borderBottom: '1px solid #f3f4f6',
  },
  modeCard: {
    textAlign: 'left', padding: '11px 14px', border: '1.5px solid #d1d5db',
    borderRadius: 10, background: '#fff', cursor: 'pointer', width: '100%',
  },
  modeCardOn: { border: '1.5px solid #4f46e5', background: '#ede9fe' },

  groupHead: {
    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
    padding: '7px 2px', border: 'none', background: 'none', cursor: 'pointer',
    textAlign: 'left',
  },
  groupCount: {
    fontSize: 10.5, fontWeight: 700, color: '#9ca3af', background: '#f3f4f6',
    borderRadius: 5, padding: '1px 7px',
  },

  codeRow: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
    border: '1px solid #f3f4f6', borderRadius: 8,
  },
  codeChip: {
    fontFamily: 'ui-monospace, monospace', fontSize: 13, fontWeight: 700,
    background: '#f9fafb', padding: '4px 9px', borderRadius: 6,
  },
  errorRow: {
    padding: '10px 12px', border: '1px solid #f3f4f6', borderRadius: 9,
    background: '#fcfcfd',
  },
  observedTag: {
    marginLeft: 8, fontSize: 10, fontWeight: 700, color: '#059669',
    background: '#d1fae5', padding: '1px 7px', borderRadius: 5,
  },

  // The roster table is the coder one — same grid, same proportions.
  rosterTable: pl.coderTable,
  rosterHeader: pl.coderTableHeader,
  rosterRow: pl.coderTableRow,
  removeRow: pl.removeCoder,

  mutRow: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0',
    borderBottom: '1px solid #f9fafb', flexWrap: 'wrap',
  },
}

const s: Record<string, CSSProperties> = { ...pl, ...auditorOnly }

export default s
