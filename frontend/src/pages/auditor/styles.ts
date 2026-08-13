import type { CSSProperties } from 'react'

/** Shared styling for the trainer-facing auditor screens. Rose/violet marks
 *  this module apart from PracticeLab's teal and Assessment's indigo. */
const s: Record<string, CSSProperties> = {
  h1: { fontSize: 20, fontWeight: 800, color: '#111' },
  sub: { fontSize: 13, color: '#6b7280', marginTop: 2 },
  label: { fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 6 },
  note: { fontSize: 11.5, color: '#9ca3af', marginTop: 6, lineHeight: 1.5 },
  rowBetween: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' },
  empty: { fontSize: 13, color: '#9ca3af', padding: '24px 0' },

  input: {
    fontSize: 13, padding: '8px 11px', border: '1px solid #e5e7eb',
    borderRadius: 8, outline: 'none', background: '#fff', width: '100%',
    boxSizing: 'border-box', fontFamily: 'inherit',
  },
  primaryBtn: {
    display: 'flex', alignItems: 'center', gap: 7, padding: '10px 18px',
    border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13.5,
    fontWeight: 700, color: '#fff',
    background: 'linear-gradient(135deg, #be185d, #9333ea)',
  },
  ghostBtn: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
    border: '1px solid #e5e7eb', borderRadius: 8, cursor: 'pointer',
    fontSize: 12.5, fontWeight: 600, background: '#fff', color: '#374151',
  },
  backBtn: {
    display: 'flex', alignItems: 'center', gap: 4, border: 'none',
    background: 'none', color: '#6b7280', fontSize: 13, cursor: 'pointer',
    padding: 0, marginBottom: 14,
  },
  linkBtn: {
    display: 'inline-flex', alignItems: 'center', gap: 5, border: 'none',
    background: 'none', color: '#9333ea', fontSize: 12, fontWeight: 600,
    cursor: 'pointer', padding: 0,
  },
  iconBtn: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', padding: 3, display: 'flex' },
  dangerBtn: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
    border: '1px solid #fecaca', borderRadius: 8, cursor: 'pointer',
    fontSize: 12.5, fontWeight: 600, background: '#fff', color: '#dc2626',
  },

  listRow: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px',
    border: '1px solid #e5e7eb', borderRadius: 10, background: '#fff',
    cursor: 'pointer', textAlign: 'left', width: '100%', flexWrap: 'wrap',
  },
  chip: {
    fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6,
    background: '#f5f3ff', color: '#7c3aed', whiteSpace: 'nowrap',
  },
  toggleChip: {
    fontSize: 12, fontWeight: 600, padding: '6px 12px', borderRadius: 7,
    border: '1px solid #e5e7eb', background: '#fff', color: '#6b7280', cursor: 'pointer',
  },
  toggleChipOn: { borderColor: '#9333ea', background: '#faf5ff', color: '#7c3aed' },

  panel: { border: '1px solid #e5e7eb', borderRadius: 12, background: '#fff', marginTop: 16, overflow: 'hidden' },
  panelHead: { display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', background: '#fafafa', borderBottom: '1px solid #f3f4f6' },

  modeCard: {
    textAlign: 'left', padding: '11px 14px', border: '1.5px solid #e5e7eb',
    borderRadius: 10, background: '#fff', cursor: 'pointer', width: '100%',
  },
  modeCardOn: { borderColor: '#9333ea', background: '#faf5ff' },

  warnBox: {
    display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 12px',
    borderRadius: 8, background: '#fffbeb', border: '1px solid #fde68a',
    fontSize: 12, color: '#92400e', lineHeight: 1.5, marginBottom: 16,
  },
  infoBox: {
    display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 12px',
    borderRadius: 8, background: '#faf5ff', border: '1px solid #e9d5ff',
    fontSize: 12, color: '#6b21a8', lineHeight: 1.5,
  },

  codeRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: '1px solid #f3f4f6', borderRadius: 8 },
  codeChip: { fontFamily: 'ui-monospace, monospace', fontSize: 13, fontWeight: 700, background: '#f9fafb', padding: '4px 9px', borderRadius: 6 },
  errorRow: { padding: '10px 12px', border: '1px solid #f3f4f6', borderRadius: 9, background: '#fcfcfd' },
  observedTag: {
    marginLeft: 8, fontSize: 10, fontWeight: 700, color: '#059669',
    background: '#d1fae5', padding: '1px 7px', borderRadius: 5,
  },

  modeToggle: { display: 'flex', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden' },
  modeTab: { padding: '5px 14px', border: 'none', background: '#fff', fontSize: 12, fontWeight: 600, color: '#6b7280', cursor: 'pointer' },
  modeTabActive: { padding: '5px 14px', border: 'none', background: '#9333ea', fontSize: 12, fontWeight: 600, color: '#fff', cursor: 'pointer' },
  rosterTable: { border: '1px solid #e9d5ff', borderRadius: 8, overflow: 'hidden', marginTop: 8 },
  rosterHeader: { display: 'grid', gridTemplateColumns: '1fr 140px 32px', padding: '8px 14px', background: '#faf5ff', fontSize: 11, fontWeight: 700, color: '#6b21a8', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e9d5ff' },
  rosterRow: { display: 'grid', gridTemplateColumns: '1fr 140px 32px', padding: '8px 14px', borderBottom: '1px solid #faf5ff', fontSize: 13, alignItems: 'center' },
  removeRow: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14, padding: 0, lineHeight: 1 },

  mutRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid #f9fafb', flexWrap: 'wrap' },
  select: { fontSize: 12.5, padding: '7px 9px', border: '1px solid #e5e7eb', borderRadius: 7, background: '#fff' },
}

export default s
