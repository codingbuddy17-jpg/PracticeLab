import api from './client'

// ── shapes ───────────────────────────────────────────────────────────────────

export type ClaimLine = {
  code?: string
  poa?: string
  ccmcc?: string
  modifier?: string
  units?: number | string
  pointers?: string[]
}

export type Claim = {
  pdx_code: string
  pdx_poa: string
  sdx: ClaimLine[]
  pcs: ClaimLine[]
  cpt: ClaimLine[]
  facility_level?: string
  profee_level?: string
}

/**
 * What the auditor records. Deliberately the same shape the ground truth takes,
 * so scoring is a comparison rather than a translation.
 */
export type Finding = {
  section: string
  action: 'Add' | 'Revise' | 'Delete'
  field?: string
  line?: number
  claim_value?: string
  correct_value?: string
}

export type SectionSpec = {
  key: string
  actions: string[]
  fields: string[]
}

export type FormSpec = {
  specialty: string
  sections: SectionSpec[]
  supports_query: boolean
}

export type AuditChart = {
  chart_id: number
  chart_number: string
  category: string
  claim: Claim
  draft: {
    section_verdicts: Record<string, string>
    findings: Finding[]
    query_flag: boolean
    query_text: string | null
    auditor_notes: string | null
  } | null
}

export type AuditSessionData = {
  session_id: number
  auditor_name: string
  specialty: string
  status: string
  supports_query: boolean
  show_results: boolean
  submitted_at: string | null
  form?: FormSpec
  charts: AuditChart[]
  results?: AuditResultRow[]
}

/**
 * Note what is absent: no chart type, no source, no planting count. Charts
 * recycle through cycles, so telling an auditor a chart was clean hands them
 * the answer the next time they meet it.
 */
export type AuditResultRow = {
  chart_id: number
  chart_number: string
  audit_accuracy: number
  add_accuracy: number | null
  revise_accuracy: number | null
  delete_accuracy: number | null
  missed: Record<string, unknown>[]
  detected_not_corrected: Record<string, unknown>[]
  over_calls: number
  query_correct: boolean | null
}

export type AuditSummary = {
  charts: number
  audit_accuracy: number
  audit_accuracy_basis: string
  clean_charts: number
  opportunity_charts: number
  clean_accuracy: number | null
  opportunity_accuracy: number | null
  add_accuracy: number | null
  add_found: number
  add_planted: number
  revise_accuracy: number | null
  revise_found: number
  revise_planted: number
  delete_accuracy: number | null
  delete_found: number
  delete_planted: number
  component_basis: string
  drg_accuracy: number | null
  drg_impacting_found: number
  drg_impacting_planted: number
  query_accuracy: number | null
  query_charts: number
  query_correct: number
  over_calls: number
  detected_not_corrected: number
  opportunities: number
  pass_fail: string | null
  verdict_withheld_reason: string | null
}

export type ChartWork = {
  chart_id: number
  section_verdicts: Record<string, string>
  findings: Finding[]
  query_flag: boolean
  query_text?: string | null
  auditor_notes?: string | null
}

// ── auditor-facing ───────────────────────────────────────────────────────────

export async function openAuditSession(token: string): Promise<AuditSessionData> {
  const { data } = await api.get(`/auditor/sessions/by-token/${token}`)
  return data
}

export async function saveAuditDraft(sessionId: number, charts: ChartWork[]) {
  const { data } = await api.post(`/auditor/sessions/${sessionId}/save-draft`, { charts })
  return data
}

export async function submitAuditSession(sessionId: number, charts: ChartWork[]) {
  const { data } = await api.post(`/auditor/sessions/${sessionId}/submit`, { charts })
  return data as {
    submitted: boolean
    show_results: boolean
    summary: AuditSummary
    results: AuditResultRow[]
  }
}

// ── trainer-facing ───────────────────────────────────────────────────────────

export async function getAuditFormSpecs() {
  const { data } = await api.get('/auditor/form-spec')
  return data as { specialties: FormSpec[] }
}

export async function getAuditConfig() {
  const { data } = await api.get('/auditor/config')
  return data
}

export async function updateAuditConfig(payload: Record<string, unknown>) {
  const { data } = await api.put('/auditor/config', payload)
  return data
}

export async function listAuditBatches(status?: string) {
  const { data } = await api.get('/auditor/batches', { params: status ? { status } : {} })
  return data as { batches: Record<string, unknown>[] }
}

export async function getAuditBatch(batchId: number) {
  const { data } = await api.get(`/auditor/batches/${batchId}`)
  return data
}

export async function createAuditBatch(payload: Record<string, unknown>) {
  const { data } = await api.post('/auditor/batches', payload)
  return data
}

export async function runAuditAllocation(batchId: number, payload: Record<string, unknown>) {
  const { data } = await api.post(`/auditor/batches/${batchId}/run-allocation`, payload)
  return data
}

export async function getAuditPlantings(batchId: number, auditor?: string) {
  const { data } = await api.get(`/auditor/batches/${batchId}/plantings`,
    { params: auditor ? { auditor } : {} })
  return data
}

export async function regenerateAssignment(assignmentId: number, runBy: string) {
  const { data } = await api.post(`/auditor/assignments/${assignmentId}/regenerate`,
    { run_by: runBy })
  return data
}

export async function getAuditReview(sessionId: number) {
  const { data } = await api.get(`/auditor/sessions/${sessionId}/review`)
  return data
}

export async function listAuditKeySets(specialty?: string) {
  const { data } = await api.get('/auditor/keys', { params: specialty ? { specialty } : {} })
  return data
}

export async function getAuditKeysForChart(chartId: number) {
  const { data } = await api.get(`/auditor/keys/chart/${chartId}`)
  return data
}

export async function previewAuditKeySet(chartId: number, mutations: Finding[]) {
  const { data } = await api.post(`/auditor/keys/chart/${chartId}/preview`, { mutations })
  return data
}

export async function createAuditKeySet(chartId: number, payload: Record<string, unknown>) {
  const { data } = await api.post(`/auditor/keys/chart/${chartId}`, payload)
  return data
}

export async function updateAuditKeySet(setId: number, payload: Record<string, unknown>) {
  const { data } = await api.put(`/auditor/keys/${setId}`, payload)
  return data
}

export async function deleteAuditKeySet(setId: number, passphrase: string) {
  const { data } = await api.post(`/auditor/keys/${setId}/delete`, { passphrase })
  return data
}

// ── analytics ────────────────────────────────────────────────────────────────

export async function getAuditOverview(params: Record<string, unknown> = {}) {
  const { data } = await api.get('/auditor/analytics/overview', { params })
  return data
}

export async function getAuditByBatch(params: Record<string, unknown> = {}) {
  const { data } = await api.get('/auditor/analytics/by-batch', { params })
  return data as { batches: Record<string, any>[] }
}

export async function getAuditByAuditor(params: Record<string, unknown> = {}) {
  const { data } = await api.get('/auditor/analytics/by-auditor', { params })
  return data as { auditors: Record<string, any>[]; pass_threshold: number }
}

export async function getAuditDetection(params: Record<string, unknown> = {}) {
  const { data } = await api.get('/auditor/analytics/detection', { params })
  return data
}
