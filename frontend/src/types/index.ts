export type Specialty =
  | 'IP-DRG'
  | 'ED Facility'
  | 'ED Profee'
  | 'SDS'
  | 'Edits'
  | 'Denials'
  | 'Ancillary'
  | 'E/M'
  | 'Surgery'
  | 'ED Single Path'

export type Difficulty = 'Beginner' | 'Intermediate' | 'Advanced'
export type ChartStatus = 'Active' | 'Retired'

export interface ChartFile {
  id: number
  storage_key: string
  original_filename: string
  page_order: number
  total_pages: number
  uploaded_by: string
  uploaded_at: string
}

export interface Chart {
  id: number
  chart_number: string
  alias: string | null
  specialty: Specialty
  category: string
  difficulty: Difficulty
  status: ChartStatus
  uploaded_by: string
  view_count: number
  created_at: string
  updated_at: string | null
  files: ChartFile[]
}

export interface ChartWithRationale extends Chart {
  rationale: string | null
  audit_logs: AuditLog[]
}

export interface AuditLog {
  id: number
  action: string
  actor: string
  details: string | null
  created_at: string
}

export interface SearchResult {
  total: number
  page: number
  page_size: number
  results: Chart[]
}

export interface BulkUploadResult {
  filename: string
  chart_number: string | null
  status: 'success' | 'error'
  message: string
}

export interface BulkUploadMeta {
  uploaded_by: string
  specialty: Specialty
  category: string
  difficulty: Difficulty
  rationale?: string
  alias?: string
}

export const SPECIALTIES: Specialty[] = [
  'IP-DRG', 'ED Facility', 'ED Profee', 'SDS', 'Edits', 'Denials', 'Ancillary', 'E/M'
]

export const DIFFICULTIES: Difficulty[] = ['Beginner', 'Intermediate', 'Advanced']

export const SPECIALTY_PREFIX: Record<string, Specialty> = {
  'IP': 'IP-DRG',
  'EDP': 'ED Profee',
  'ED': 'ED Facility',
  'SDS': 'SDS',
  'EDT': 'Edits',
  'DEN': 'Denials',
  'ANC': 'Ancillary',
  'EM': 'E/M',
}

export function detectSpecialtyFromFilename(filename: string): Specialty | null {
  const stem = filename.split('.')[0].toUpperCase()
  // longest prefix match first
  for (const prefix of Object.keys(SPECIALTY_PREFIX).sort((a, b) => b.length - a.length)) {
    if (stem.startsWith(prefix)) return SPECIALTY_PREFIX[prefix]
  }
  return null
}
