import type { Specialty } from './types'

export const SPECIALTY_COLORS: Record<Specialty, { bg: string; text: string; border: string; light: string }> = {
  'IP-DRG':      { bg: '#4f46e5', text: '#fff', border: '#4f46e5', light: '#ede9fe' },
  'ED Facility': { bg: '#dc2626', text: '#fff', border: '#dc2626', light: '#fee2e2' },
  'ED Profee':   { bg: '#ea580c', text: '#fff', border: '#ea580c', light: '#ffedd5' },
  'SDS':         { bg: '#0891b2', text: '#fff', border: '#0891b2', light: '#cffafe' },
  'Edits':       { bg: '#7c3aed', text: '#fff', border: '#7c3aed', light: '#ede9fe' },
  'Denials':     { bg: '#d97706', text: '#fff', border: '#d97706', light: '#fef3c7' },
  'Ancillary':   { bg: '#16a34a', text: '#fff', border: '#16a34a', light: '#dcfce7' },
  'E/M':         { bg: '#2563eb', text: '#fff', border: '#2563eb', light: '#dbeafe' },
  'Surgery':     { bg: '#be123c', text: '#fff', border: '#be123c', light: '#ffe4e6' },
  'ED Single Path': { bg: '#9333ea', text: '#fff', border: '#9333ea', light: '#f3e8ff' },
}

export const DIFFICULTY_COLORS = {
  Beginner:     { bg: '#dcfce7', text: '#166534' },
  Intermediate: { bg: '#fef9c3', text: '#854d0e' },
  Advanced:     { bg: '#fee2e2', text: '#991b1b' },
}
