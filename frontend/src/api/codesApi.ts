import api from './client'
import { adminAuth } from './adminAuth'

/**
 * Code descriptions — what a code actually says.
 *
 * ICD-10-CM, ICD-10-PCS and HCPCS Level II only. CPT descriptions are AMA
 * copyright and licensed per user, so a CPT line renders its code alone.
 *
 * Every call here is best-effort. The descriptions are reference data loaded
 * by a script that may not have been run, and a screen that cannot say what a
 * code means must still let someone do their work — so a failure resolves to
 * "no description" rather than an error.
 */

export type CodeInfo = {
  code: string
  system: string
  description: string
  short_description?: string | null
  chapter?: string | null
  chapter_no?: number | null
  billable?: boolean
}

export type DescribeResult = {
  descriptions: Record<string, CodeInfo>
  /** Which systems have rows. Empty when nothing was loaded. */
  systemsLoaded: Record<string, boolean>
}

export async function describeCodes(codes: string[], section?: string): Promise<DescribeResult> {
  const wanted = Array.from(new Set(codes.map(c => (c || '').trim()).filter(Boolean)))
  if (!wanted.length) return { descriptions: {}, systemsLoaded: {} }
  try {
    const { data } = await api.get('/codes/describe', {
      params: { codes: wanted.join(','), section },
    })
    return {
      descriptions: (data.descriptions || {}) as Record<string, CodeInfo>,
      systemsLoaded: (data.systems_loaded || {}) as Record<string, boolean>,
    }
  } catch {
    return { descriptions: {}, systemsLoaded: {} }
  }
}

export async function searchCodes(prefix: string, section?: string, limit = 8) {
  if ((prefix || '').replace(/\./g, '').length < 2) return [] as CodeInfo[]
  try {
    const { data } = await api.get('/codes/search', { params: { prefix, section, limit } })
    return (data.matches || []) as CodeInfo[]
  } catch {
    return [] as CodeInfo[]
  }
}

export async function codeSetStatus() {
  try {
    const { data } = await api.get('/codes/status')
    return data as { loaded: any[]; missing?: any[]; any: boolean; needs_attention?: boolean; expected_edition?: string }
  } catch {
    return { loaded: [], any: false }
  }
}

export type CodeSetIngestJob = {
  id: number
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at?: string | null
  loaded_by?: string
  returncode?: number | null
  message?: string
  log_tail?: string[]
}

export async function getCodeSetIngestJob() {
  const { data } = await api.get('/codes/ingest-job')
  return data.job as CodeSetIngestJob | null
}

export async function startCodeSetIngest(passphrase: string, loadedBy: string) {
  const { data } = await api.post('/codes/ingest-job',
    { loaded_by: loadedBy || 'admin UI' },
    adminAuth(passphrase),
  )
  return data.job as CodeSetIngestJob
}
