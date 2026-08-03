/// <reference types="vite/client" />
import api from './client'

export function downloadAnswerKeyTemplate(specialty: string) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/answer-key/template?specialty=${specialty}`)
}

export async function uploadAnswerKeys(file: File, specialty: string, enteredBy: string, replace = false, passphrase = '') {
  const form = new FormData()
  form.append('file', file)
  form.append('specialty', specialty)
  form.append('entered_by', enteredBy)
  form.append('replace', String(replace))
  form.append('passphrase', passphrase)
  const { data } = await api.post('/practicelab/answer-key/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { stored: string[]; replaced: string[]; skipped_duplicates: string[]; not_found: string[]; wrong_specialty: string[] }
}

export function downloadAnswerKeyExport(passphrase: string, specialty?: string) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ passphrase })
  if (specialty) params.set('specialty', specialty)
  window.open(`${base}/practicelab/answer-key/export?${params}`)
}

export async function deleteAnswerKey(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/practicelab/answer-key/${chartId}`, { params: { passphrase } })
  return data
}

export async function getAnswerKeyStatus(specialty?: string) {
  const { data } = await api.get('/practicelab/answer-key/status', { params: { specialty } })
  return data as { total_charts: number; with_answer_key: number; without_answer_key: number }
}

export async function getAnswerKeyList(specialty?: string) {
  const { data } = await api.get('/practicelab/answer-key/list', { params: { specialty } })
  return data as { chart_id: number; chart_number: string; specialty: string; category: string; entered_by: string; created_at: string | null }[]
}

export async function getChartsMissingKeys(specialty?: string) {
  const { data } = await api.get('/practicelab/answer-key/missing', { params: { specialty } })
  return data as { chart_id: number; chart_number: string; specialty: string; category: string; can_purge: boolean }[]
}

export async function getPoolPreview(specialty: string, categories?: string, difficulties?: string) {
  const { data } = await api.get('/practicelab/batches/pool-preview', {
    params: { specialty, categories, difficulties },
  })
  return data as { total_matching: number; with_answer_key: number }
}

export function downloadCoderListTemplate() {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/coders/template`)
}

export async function parseCoderList(file: File): Promise<{ name: string; emp_id: string }[]> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/practicelab/coders/parse', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getScoringConfigs() {
  const { data } = await api.get('/practicelab/config/scoring')
  return data
}

export async function updateScoringConfig(payload: {
  specialty_type: string; pdx_weight: number; sdx_weight: number;
  pcs_weight?: number; drg_weight?: number; cpt_weight?: number;
  facility_level_weight?: number; profee_level_weight?: number;
  pass_threshold: number; drg_triggers: string[];
  overcoding_penalty: boolean;
  weighted_enabled: boolean; dpo_enabled: boolean; dpo_pass_threshold: number;
  passphrase: string; updated_by: string;
}) {
  const { data } = await api.put('/practicelab/config/scoring', payload)
  return data
}

export async function searchChartsForBatch(specialty: string, q?: string, category?: string, difficulty?: string) {
  const { data } = await api.get('/practicelab/batches/chart-search', { params: { specialty, q, category, difficulty } })
  return data as { id: number; chart_number: string; specialty: string; category: string; difficulty: string }[]
}

export async function createBatch(payload: {
  name: string; specialty: string; categories: string[]; difficulties: string[];
  charts_per_coder: number; coders: { name: string; emp_id: string }[]; created_by: string;
  use_weighted?: boolean; use_dpo?: boolean; is_direct_assignment?: boolean;
}) {
  const { data } = await api.post('/practicelab/batches', payload)
  return data as { batch_id: number; name: string; warning?: string; skipped_duplicates?: string[] }
}

export async function runAllocation(batchId: number, payload: {
  charts_per_coder?: number; manual_chart_ids?: number[]; run_by: string; notes?: string; exclude_coders?: string[];
}) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/run-allocation`, payload)
  return data as { cycle_id: number; cycle_number: number; assigned: Record<string, number>; warnings: string[] }
}

export async function closeBatch(batchId: number, closedBy: string) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/close`, { closed_by: closedBy })
  return data
}

export async function forceCloseBatch(batchId: number, payload: { closed_by: string; passphrase: string; reason: string }) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/force-close`, payload)
  return data
}

export async function addBatchNote(batchId: number, text: string, author: string) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/notes`, { text, author })
  return data
}

export async function addCodersToBatch(batchId: number, coders: { name: string; emp_id: string }[]) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/coders`, { coders })
  return data as { added: string[]; skipped_duplicates: string[] }
}

export async function getAdminOpenBatches(passphrase: string) {
  const { data } = await api.get('/practicelab/admin/open-batches', { params: { passphrase } })
  return data as Array<{
    id: number; name: string; specialty: string; created_by: string; created_at: string;
    days_open: number; coder_count: number; allocation_cycles: number; total_assigned: number; graded_count: number;
  }>
}

/**
 * A page of batches, newest first, with the pre-paging total.
 *
 * The total has to come from the server: a page cannot say how many rows there
 * were, and a "Load more" that cannot tell you what is left is a button you
 * have to press to find out whether pressing it does anything.
 */
export async function listBatchesPage(opts: {
  directOnly?: boolean; search?: string; limit?: number; offset?: number; status?: string
} = {}) {
  const res = await api.get('/practicelab/batches', {
    params: {
      direct_only: opts.directOnly, search: opts.search || undefined,
      limit: opts.limit, offset: opts.offset, status: opts.status,
    },
  })
  const total = Number(res.headers['x-total-count'] ?? (res.data as any[]).length)
  return { items: res.data as any[], total }
}

export async function listBatches(status?: string, specialty?: string, directOnly?: boolean) {
  const { data } = await api.get('/practicelab/batches', { params: { status, specialty, direct_only: directOnly } })
  return data as Array<{
    id: number; name: string; specialty: string; charts_per_coder: number;
    status: string; created_by: string; created_at: string; coder_count: number;
    is_direct_assignment?: boolean;
  }>
}

export async function getBatch(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}`)
  return data
}

export async function getDRGReview(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}/drg-review`)
  return data
}

export async function submitDRGDecision(resultId: number, drgError: boolean, reviewer: string) {
  const { data } = await api.post(`/practicelab/results/${resultId}/drg-decision`, {
    drg_error: drgError, reviewer,
  })
  return data
}

export async function getBatchResults(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}/results`)
  return data
}

export async function getBatchInsights(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}/insights`)
  return data
}

export function downloadBatchResultsExcel(batchId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/results/export`, '_blank')
}

export interface EDRubricPayload {
  coder_name: string
  chart_id: number
  review_pass: boolean
  research_coding_pass: boolean
  research_payer_pass: boolean
  research_nuances_pass: boolean
  resolution_pass: boolean
  rationale_tier: 'acceptable' | 'needs_improvement' | 'not_acceptable'
  trainer_note?: string
  graded_by: string
  regrade?: boolean
}

export async function gradeEDChart(batchId: number, payload: EDRubricPayload) {
  const { data } = await api.post(`/practicelab/batches/${batchId}/grade-ed`, payload)
  return data
}

export async function getEDGrades(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}/ed-grades`)
  return data as Array<{
    result_id: number
    coder_name: string
    chart_id: number
    total_score: number
    pass_fail: string | null
    graded_at: string | null
    rubric: {
      review_pass: boolean
      research_coding_pass: boolean
      research_payer_pass: boolean
      research_nuances_pass: boolean
      resolution_pass: boolean
      rationale_tier: string
      trainer_note: string | null
      graded_by: string
    } | null
  }>
}

export interface PLFilters {
  from_date?: string
  to_date?: string
  specialty?: string
}

function fp(f: PLFilters) {
  const p: Record<string, string> = {}
  if (f.from_date) p.from_date = f.from_date
  if (f.to_date) p.to_date = f.to_date
  if (f.specialty) p.specialty = f.specialty
  return p
}

export async function getPLAnalyticsOverview(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/overview', { params: { ...fp(f), scope } })
  return data
}

export async function getPLAnalyticsBySpecialty(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/by-specialty', { params: { ...fp(f), scope } })
  return data
}

export async function getPLSpecialtyProfile(specialty: string, f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/specialty-profile', { params: { ...fp(f), specialty, scope } })
  return data
}

export async function getPLAnalyticsByChart(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/by-chart', { params: fp(f) })
  return data
}

export async function getPLAnalyticsByBatch(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/by-batch', { params: { ...fp(f), scope } })
  return data
}

export async function getCoderTrend(coderName: string, f: PLFilters = {}, empId?: string | null) {
  const { data } = await api.get('/practicelab/analytics/coder-trend', { params: { coder_name: coderName, emp_id: empId || undefined, ...fp(f) } })
  return data
}

export async function getCoderSummary(coderName: string, f: PLFilters = {}, empId?: string | null) {
  const { data } = await api.get('/practicelab/analytics/coder-summary', { params: { coder_name: coderName, emp_id: empId || undefined, ...fp(f) } })
  return data
}

/**
 * Fetches the report as a blob rather than window.open()-ing the URL.
 *
 * window.open sends the browser to the endpoint directly, so a 404 (no results
 * in the selected range) rendered the raw JSON error in a blank tab. Fetching
 * lets the caller surface a normal message instead.
 *
 * Throws with the server's detail message when there is nothing to report.
 */
export async function downloadCoderReportPdf(coderName: string, f: PLFilters = {}, empId?: string | null) {
  const { data } = await api.get('/practicelab/analytics/coder-report.pdf', {
    params: { coder_name: coderName, emp_id: empId || undefined, ...fp(f) },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${coderName.replace(/\s+/g, '_')}_Performance_Report.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function downloadSessionCoderReportPdf(sessionId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/practice-sessions/${sessionId}/coder-report.pdf`, '_blank')
}

/**
 * Fetches before opening, so a failure surfaces as a message rather than a new
 * tab containing an error page. window.open() cannot tell success from a 500 —
 * it hands the response to the browser either way.
 */
export async function downloadBatchReportPdf(batchId: number) {
  const res = await api.get(`/practicelab/batches/${batchId}/insights/report.pdf`,
                            { responseType: 'blob' })
  const url = URL.createObjectURL(res.data as Blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export async function getPLAnalyticsByCategory(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/by-category', { params: { ...fp(f), scope } })
  return data as { team: any[]; coder_category: any[] }
}

export async function getPLChartTeachingValue(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const { data } = await api.get('/practicelab/analytics/chart-teaching-value', { params: { ...fp(f), scope } })
  return data as any[]
}

export async function getPLCoderMatrix(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal',
                                      groupBy: 'batch' | 'specialty' = 'batch') {
  const { data } = await api.get('/practicelab/analytics/coder-matrix', { params: { ...fp(f), scope, group_by: groupBy } })
  return data as { batches: any[]; coders: string[]; coder_emp_ids?: Record<string, string>; cells: any[] }
}

export async function getPLChartDetail(chartNumber: string) {
  const { data } = await api.get(`/practicelab/analytics/chart-detail/${encodeURIComponent(chartNumber)}`)
  return data as { chart_number: string; coders: { coder_name: string; batch_name: string; total_score: number; pass_fail: string; missed_codes: string[] }[] }
}

// ── E/M MDM API ──────────────────────────────────────────────────────────────

export async function getEMAnswerKey(chartId: number) {
  const { data } = await api.get(`/practicelab/em/answer-key/${chartId}`)
  return data
}

export async function listEMAnswerKeys() {
  const { data } = await api.get('/practicelab/em/answer-key/list')
  return data as any[]
}

export async function upsertEMAnswerKey(payload: Record<string, any>) {
  const { data } = await api.post('/practicelab/em/answer-key', payload)
  return data as { status: string; copa_level: string; dr_level: string; risk_level: string }
}

export async function deleteEMAnswerKey(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/practicelab/em/answer-key/${chartId}`, { params: { passphrase } })
  return data
}

export async function getEMScoringConfig() {
  const { data } = await api.get('/practicelab/em/scoring-config')
  return data
}

export async function updateEMScoringConfig(payload: Record<string, any>) {
  const { data } = await api.put('/practicelab/em/scoring-config', payload)
  return data
}

export function downloadEMAnswerKeyTemplate() {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/em/answer-key/template`)
}

export async function uploadEMAnswerKeys(
  file: File,
  enteredBy: string,
  replace: boolean,
  passphrase: string,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('entered_by', enteredBy)
  form.append('replace', String(replace))
  form.append('passphrase', passphrase)
  const { data } = await api.post('/practicelab/em/answer-key/upload', form)
  return data as {
    stored: string[]
    replaced: string[]
    skipped_duplicates: string[]
    not_found: string[]
  }
}

export async function getBatchEMBreakdown(batchId: number) {
  const { data } = await api.get(`/practicelab/practice-sessions/batch/${batchId}/em-breakdown`)
  return data as {
    has_data: boolean
    team: {
      chart_count: number; avg_total: number
      avg_coding_accuracy: number; avg_reasoning_accuracy: number
      copa_pct: number; dr_pct: number; risk_pct: number; em_level_pct: number
      right_code_wrong_reasoning_count: number; pass_count: number
    }
    coders: Array<{
      coder_name: string; chart_count: number; avg_total: number
      avg_coding_accuracy: number; avg_reasoning_accuracy: number
      copa_pct: number; dr_pct: number; risk_pct: number; em_level_pct: number
      right_code_wrong_reasoning_count: number; pass_count: number
    }>
  }
}

// ── In-interface answer key editing ─────────────────────────────────────────

export interface AnswerKeyDetail {
  chart_id: number; chart_number: string; specialty: string; category: string
  exists: boolean; is_ip: boolean; uses_pointers: boolean; single_path: boolean
  pdx_code: string; pdx_poa: string
  sdx: Array<{ code: string; poa?: string; ccmcc?: string }>
  pcs: Array<{ code: string }>
  cpt: Array<{ code: string; modifier?: string; pointers?: string[] }>
  facility_level: string | null; profee_level: string | null
  entered_by: string | null
}

export interface AnswerKeyImpact {
  total_results: number; coders_affected: number
  batches: Array<{ batch_id: number; name: string; status: string; results: number }>
  closed_batches: number; drg_decisions_preserved: number
  released_to_coders: number; blocked: boolean
}

export async function getAnswerKeyDetail(chartId: number) {
  const { data } = await api.get(`/practicelab/answer-key/${chartId}/detail`)
  return data as AnswerKeyDetail
}

export async function getAnswerKeyImpact(chartId: number) {
  const { data } = await api.get(`/practicelab/answer-key/${chartId}/impact`)
  return data as AnswerKeyImpact
}

export async function saveAnswerKeyInline(chartId: number, payload: {
  pdx_code: string; pdx_poa?: string
  sdx: Array<{ code: string; poa?: string; ccmcc?: string }>
  pcs: Array<{ code: string }>
  cpt: Array<{ code: string; modifier?: string; pointers?: string[] }>
  facility_level?: string | null; profee_level?: string | null
  entered_by: string; passphrase?: string; regrade_closed?: boolean
}) {
  const { data } = await api.put(`/practicelab/answer-key/${chartId}`, payload)
  return data as { saved: boolean; created: boolean; regraded: number; skipped_closed: number; sessions: number }
}

// ── Coder directory ─────────────────────────────────────────────────────────

export interface CoderDirectoryEntry {
  coder_name: string
  emp_id: string | null
  result_count: number
  last_activity: string | null
  /** Populated only when one emp_id has been spelled more than one way. */
  name_variants: string[]
}

export async function searchCoders(q?: string, limit = 50) {
  const { data } = await api.get('/practicelab/coders', { params: { q, limit } })
  return data as { coders: CoderDirectoryEntry[]; total: number }
}

/**
 * Coder performance: one row per graded chart, three sheets.
 * Blob-fetched rather than window.open()'d so an error is a message, not a
 * blank tab rendering JSON.
 */
export async function downloadCoderPerformanceXlsx(f: PLFilters = {}, coderName?: string, empId?: string | null) {
  const { data } = await api.get('/practicelab/analytics/coder-performance.xlsx', {
    params: { ...fp(f), coder_name: coderName || undefined, emp_id: empId || undefined },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = coderName
    ? `CoderPerformance_${coderName.replace(/\s+/g, '_')}.xlsx`
    : 'CoderPerformance.xlsx'
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

/**
 * The batch list panel as Excel — the rows on screen, one per batch.
 * Honours the panel's filters and deliberately ignores its paging.
 */
export function downloadBatchListXlsx(opts: { status?: string; search?: string; specialty?: string } = {}) {
  const p = new URLSearchParams()
  if (opts.status) p.set('status', opts.status)
  if (opts.search?.trim()) p.set('search', opts.search.trim())
  if (opts.specialty) p.set('specialty', opts.specialty)
  // Query built outside the template literal — a nested one here reads as a
  // different path to anything scanning these calls, including our own
  // UI -> API contract check.
  const qs = p.toString() ? `?${p.toString()}` : ''
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/export.xlsx` + qs, '_blank')
}

/** The Analytics -> By Batch table as Excel: same rows, filters and scope. */
export function downloadBatchAnalyticsXlsx(f: PLFilters = {}, scope: 'formal' | 'direct' | 'all' = 'formal') {
  const p = new URLSearchParams({ ...fp(f), scope })
  const qs = p.toString() ? `?${p.toString()}` : ''
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/analytics/by-batch.xlsx` + qs, '_blank')
}
