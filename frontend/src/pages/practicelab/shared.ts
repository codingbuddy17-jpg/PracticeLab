export function trainerName() {
  return localStorage.getItem('trainer_name') || 'Trainer'
}

export const SPECIALTIES = ['IP-DRG', 'ED Facility', 'ED Profee', 'SDS', 'Edits', 'Denials', 'Ancillary', 'E/M']
export const DIFFICULTIES = ['Beginner', 'Intermediate', 'Advanced']

export function round1(n: number) { return Math.round(n * 10) / 10 }

export const ISSUE_COLORS: Record<string, string> = {
  Missed: '#dc2626', Over_coded: '#d97706', Wrong_Code: '#7c3aed',
  Wrong_POA: '#0891b2', Wrong_Modifier: '#6b7280',
}
