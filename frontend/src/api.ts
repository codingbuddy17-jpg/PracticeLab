/// <reference types="vite/client" />
import axios from 'axios'
import type { Chart, ChartWithRationale, SearchResult, BulkUploadResult, BulkUploadMeta } from './types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
})

// ── Coder ────────────────────────────────────────────────────────────────────

export async function searchCharts(params: Record<string, string | number | undefined>): Promise<SearchResult> {
  const { data } = await api.get('/charts/search', { params })
  return data
}

export async function getChartPages(chartId: number, viewer = 'anonymous') {
  const { data } = await api.get(`/charts/${chartId}/pages`, { params: { viewer } })
  return data as { chart_number: string; pages: { page: number; url: string }[] }
}

export async function getCategories(specialty?: string): Promise<string[]> {
  const { data } = await api.get('/charts/categories', { params: { specialty } })
  return data
}

export async function searchInChart(chartId: number, q: string) {
  const { data } = await api.get(`/charts/${chartId}/text-search`, { params: { q } })
  return data as { query: string; matching_pages: number[]; total_matches: number }
}

// ── Trainer ──────────────────────────────────────────────────────────────────

export async function getChartTrainer(chartId: number): Promise<ChartWithRationale> {
  const { data } = await api.get(`/charts/${chartId}/trainer`)
  return data
}

export async function updateChart(chartId: number, actor: string, payload: Partial<{ category: string; difficulty: string; rationale: string; alias: string }>) {
  const { data } = await api.patch(`/charts/${chartId}`, payload, { params: { actor } })
  return data as Chart
}

// ── Coding Resources ──────────────────────────────────────────────────────────

export async function getResources() {
  const { data } = await api.get('/resources')
  return data as { id: number; title: string; description: string | null; url: string; created_by: string; sort_order: number; created_at: string }[]
}

export async function createResource(payload: { title: string; description?: string; url: string; created_by: string; sort_order?: number }) {
  const { data } = await api.post('/resources', payload)
  return data
}

export async function deleteResource(id: number) {
  const { data } = await api.delete(`/resources/${id}`)
  return data
}

export async function retireChart(chartId: number, actor: string, passphrase?: string) {
  const { data } = await api.post(`/charts/${chartId}/retire`, null, { params: { actor, passphrase } })
  return data
}

export async function restoreChart(chartId: number, actor: string, passphrase?: string) {
  const { data } = await api.post(`/charts/${chartId}/restore`, null, { params: { actor, passphrase } })
  return data
}

export async function previewChartNumbers(items: { filename: string; specialty: string }[]): Promise<{ filename: string; specialty: string; assigned_number: string }[]> {
  const { data } = await api.post('/upload/preview', items)
  return data
}

export async function bulkUpload(files: File[], metaList: BulkUploadMeta[]): Promise<BulkUploadResult[]> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('metadata', JSON.stringify(metaList))
  const { data } = await api.post('/upload/bulk', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function addFilesToChart(chartId: number, files: File[], uploadedBy: string): Promise<{ message: string }> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('uploaded_by', uploadedBy)
  const { data } = await api.post(`/upload/${chartId}/add-files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Feedback ─────────────────────────────────────────────────────────────────

export async function submitFeedback(payload: { chart_id: number; reporter: string; issues: string[]; notes?: string }) {
  const { data } = await api.post('/feedback/', payload)
  return data
}

export async function getFeedback(params: Record<string, string | number | undefined>) {
  const { data } = await api.get('/feedback/', { params })
  return data
}

export async function getUnresolvedCount(): Promise<number> {
  const { data } = await api.get('/feedback/unresolved-count')
  return data.count
}

export async function resolveFeedback(id: number, resolver: string) {
  const { data } = await api.post(`/feedback/${id}/resolve`, null, { params: { resolver } })
  return data
}

export async function reopenFeedback(id: number) {
  const { data } = await api.post(`/feedback/${id}/reopen`)
  return data
}

// ── PracticeLab ──────────────────────────────────────────────────────────────

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

export async function purgeChart(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/charts/${chartId}/purge`, { params: { passphrase } })
  return data
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

export function downloadCycleExcel(batchId: number, cycleId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/cycles/${cycleId}/generate-excel`, '_blank')
}

export async function getAdminOpenBatches(passphrase: string) {
  const { data } = await api.get('/practicelab/admin/open-batches', { params: { passphrase } })
  return data as Array<{
    id: number; name: string; specialty: string; created_by: string; created_at: string;
    days_open: number; coder_count: number; allocation_cycles: number; total_assigned: number; graded_count: number;
  }>
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

export function downloadBatchExcel(batchId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/generate-excel`, '_blank')
}

export async function gradeSubmissions(batchId: number, files: File[], regrade = false) {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  const { data } = await api.post(`/practicelab/batches/${batchId}/grade`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: regrade ? { regrade: true } : undefined,
  })
  return data as { graded: string[]; errors: string[]; needs_confirmation?: boolean; conflicts?: { coder: string; chart: string }[] }
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

export async function getPLAnalyticsOverview(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/overview', { params: fp(f) })
  return data
}

export async function getPLAnalyticsBySpecialty(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/by-specialty', { params: fp(f) })
  return data
}

export async function getPLAnalyticsByChart(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/by-chart', { params: fp(f) })
  return data
}

export async function getPLAnalyticsByBatch(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/by-batch', { params: fp(f) })
  return data
}

export async function getCoderTrend(coderName: string, f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/coder-trend', { params: { coder_name: coderName, ...fp(f) } })
  return data
}

export async function getCoderSummary(coderName: string, f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/coder-summary', { params: { coder_name: coderName, ...fp(f) } })
  return data
}

export function downloadCoderReportPdf(coderName: string, f: PLFilters = {}) {
  const params = new URLSearchParams({ coder_name: coderName, ...(fp(f) as Record<string, string>) })
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/analytics/coder-report.pdf?${params.toString()}`, '_blank')
}

export function downloadBatchReportPdf(batchId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/insights/report.pdf`, '_blank')
}

export async function getPLAnalyticsByCategory(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/by-category', { params: fp(f) })
  return data as { team: any[]; coder_category: any[] }
}

export async function getPLChartTeachingValue(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/chart-teaching-value', { params: fp(f) })
  return data as any[]
}

export async function getPLCoderMatrix(f: PLFilters = {}) {
  const { data } = await api.get('/practicelab/analytics/coder-matrix', { params: fp(f) })
  return data as { batches: any[]; coders: string[]; coder_emp_ids?: Record<string, string>; cells: any[] }
}

export async function getPLChartDetail(chartNumber: string) {
  const { data } = await api.get(`/practicelab/analytics/chart-detail/${encodeURIComponent(chartNumber)}`)
  return data as { chart_number: string; coders: { coder_name: string; batch_name: string; total_score: number; pass_fail: string; missed_codes: string[] }[] }
}

// ── Self-Practice ─────────────────────────────────────────────────────────────

export function downloadSelfPracticeTemplate() {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/self-practice/template`, '_blank')
}

export async function submitSelfPractice(coderName: string, empId: string, files: File[]) {
  const form = new FormData()
  form.append('coder_name', coderName)
  form.append('emp_id', empId)
  files.forEach(f => form.append('files', f))
  const { data } = await api.post('/practicelab/self-practice/submit', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { submission_id: number | null; graded: string[]; errors: string[] }
}

export async function getSelfPracticeQueue(status = 'pending_review') {
  const { data } = await api.get('/practicelab/self-practice/queue', { params: { status } })
  return data
}

export async function releaseSelfPractice(submissionId: number, trainerFeedback: string, reviewedBy: string) {
  const { data } = await api.post(`/practicelab/self-practice/${submissionId}/release`, {
    trainer_feedback: trainerFeedback,
    reviewed_by: reviewedBy,
  })
  return data
}

export async function standaloneGrade(trainerName: string, files: File[]) {
  const form = new FormData()
  form.append('trainer_name', trainerName)
  files.forEach(f => form.append('files', f))
  const { data } = await api.post('/practicelab/standalone/grade', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { results: any[]; errors: string[] }
}

// ── Reports ──────────────────────────────────────────────────────────────────

export async function getReportSummary() {
  const { data } = await api.get('/reports/summary')
  return data as { active: number; retired: number; total: number }
}

export async function getReportCharts(params: Record<string, string | undefined>) {
  const { data } = await api.get('/reports/charts', { params })
  return data
}

export async function getAnalytics() {
  const { data } = await api.get('/reports/analytics')
  return data
}

export function buildExportUrl(params: Record<string, string | undefined>) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][])
  return `${import.meta.env.VITE_API_URL || '/api'}/reports/export?${q.toString()}`
}

// ── Charts stats ──────────────────────────────────────────────────────────────

export async function getChartStats(): Promise<{ total_charts: number; open_feedback: number; total_specialties: number }> {
  const { data } = await api.get('/charts/stats')
  return data
}

// ── Assessment ────────────────────────────────────────────────────────────────

export interface AssessmentQuestionStat {
  specialty: string
  total: number
  active: number
  inactive: number
}

export async function getAssessmentStats(): Promise<AssessmentQuestionStat[]> {
  const { data } = await api.get('/assessment/questions/stats')
  return data
}

export interface ListQuestionsParams {
  specialty?: string
  difficulty?: string
  status?: string
  topic?: string
  search?: string
  page?: number
  page_size?: number
}

export async function listAssessmentQuestions(params?: ListQuestionsParams) {
  const { data } = await api.get('/assessment/questions', { params })
  return data as { total: number; page: number; page_size: number; results: unknown[] }
}

export async function verifyAssessmentPassphrase(trainerName: string, passphrase: string): Promise<boolean> {
  try {
    await api.post('/assessment/audit/verify-passphrase', null, {
      params: { trainer_name: trainerName, passphrase },
    })
    return true
  } catch {
    return false
  }
}

export async function logAssessmentAction(entry: {
  trainer_name: string
  action: string
  specialty?: string
  details?: string
}) {
  await api.post('/assessment/audit/log', entry).catch(() => {})
}

export async function getAssessmentAuditLogs(passphrase: string, specialty?: string) {
  const { data } = await api.get('/assessment/audit/logs', {
    params: { passphrase, specialty: specialty || undefined },
  })
  return data as Array<{
    id: number
    trainer_name: string
    action: string
    specialty: string | null
    details: string | null
    created_at: string
  }>
}

export async function getAssessmentPoolSummary(specialty: string) {
  const { data } = await api.get('/assessment/questions/pool-summary', { params: { specialty } })
  return data as {
    specialty: string
    total_active: number
    by_topic: { topic: string; count: number }[]
    by_difficulty: Record<string, number>
  }
}

export function exportAssessmentQuestions(specialty: string, passphrase: string, trainerName: string): void {
  const base = import.meta.env.VITE_API_URL || '/api'
  window.open(`${base}/assessment/questions/export?specialty=${encodeURIComponent(specialty)}&passphrase=${encodeURIComponent(passphrase)}&trainer_name=${encodeURIComponent(trainerName)}`, '_blank')
}

export async function uploadAssessmentQuestions(specialty: string, uploadedBy: string, file: File) {
  const form = new FormData()
  form.append('specialty', specialty)
  form.append('uploaded_by', uploadedBy)
  form.append('file', file)
  const { data } = await api.post('/assessment/questions/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { stored: number; stored_ids: string[]; skipped: number; errors: string[] }
}

export function downloadAssessmentTemplate(specialty: string): void {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/assessment/questions/template?specialty=${encodeURIComponent(specialty)}`, '_blank')
}

export async function updateQuestionStatus(questionId: string, status: string, updatedBy: string) {
  const { data } = await api.put(
    `/assessment/questions/${encodeURIComponent(questionId)}/status`,
    null,
    { params: { status, updated_by: updatedBy } },
  )
  return data
}

export async function updateQuestion(questionId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/assessment/questions/${encodeURIComponent(questionId)}`, payload)
  return data
}

export async function getAssessmentPoolPreview(specialties: string[], topicFilters?: string): Promise<unknown[]> {
  const { data } = await api.get('/assessment/pool-preview', {
    params: {
      specialty: specialties.join(','),
      topic_filter: topicFilters || undefined,
    },
  })
  return data
}

export async function generateAssessment(payload: Record<string, unknown>) {
  const { data } = await api.post('/assessment/generate', payload)
  return data
}

export async function listAssessmentHistory() {
  const { data } = await api.get('/assessment/history')
  return data as Array<{
    id: number
    assessment_name: string
    config_name: string | null
    student_count: number
    questions_per_student: number
    generated_by: string
    generated_at: string | null
  }>
}

export function exportAssessmentPDF(assessmentId: number): void {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/assessment/${assessmentId}/export-pdf`, '_blank')
}

export function exportAnswerKey(assessmentId: number): void {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/assessment/${assessmentId}/export-answer-key`, '_blank')
}

// ── Assessment Sessions (trainer-side) ────────────────────────────────────────

export interface CoderItem { coder_name: string; employee_id?: string }

export async function createAssessmentSessions(
  assessmentId: number, durationMinutes: number, coders: CoderItem[]
) {
  const { data } = await api.post('/assessment/sessions/create', {
    assessment_id: assessmentId,
    duration_minutes: durationMinutes,
    coders,
  })
  return data
}

export async function listAssessmentSessions(assessmentId: number) {
  const { data } = await api.get(`/assessment/${assessmentId}/sessions`)
  return data as { sessions: SessionRow[] }
}

export async function deleteAssessmentSessions(assessmentId: number) {
  const { data } = await api.delete(`/assessment/${assessmentId}/sessions`)
  return data
}

export async function parseCoderFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/assessment/sessions/parse-coders', form)
  return data as { coders: CoderItem[]; count: number }
}

export function downloadCoderTemplate(): void {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/assessment/sessions/parse-coders`, '_blank')
}

export interface SessionRow {
  session_id: number
  session_token: string
  coder_name: string
  employee_id: string | null
  status: string
  duration_minutes: number
  expires_at: string
  started_at: string | null
  submitted_at: string | null
  auto_submitted: boolean
  score_pct: number | null
  correct_count: number | null
  total_questions: number | null
  time_taken_seconds: number | null
}

// ── Assessment Take (coder-facing) ────────────────────────────────────────────

export async function getSessionInfo(token: string) {
  const { data } = await api.get(`/assessment/take/${token}`)
  return data
}

export async function startSession(token: string) {
  const { data } = await api.post(`/assessment/take/${token}/start`)
  return data
}

export async function saveAnswer(token: string, questionIndex: number, questionId: string, selectedAnswer: string | null) {
  const { data } = await api.post(`/assessment/take/${token}/answer`, {
    question_index: questionIndex,
    question_id: questionId,
    selected_answer: selectedAnswer,
  })
  return data
}

export async function submitSession(token: string, autoSubmitted = false) {
  const { data } = await api.post(`/assessment/take/${token}/submit`, { auto_submitted: autoSubmitted })
  return data
}

// ── Assessment Analytics ──────────────────────────────────────────────────────

export async function getAssessmentAnalyticsOverview() {
  const { data } = await api.get('/assessment/analytics/overview')
  return data
}

export async function getAssessmentAnalyticsByAssessment(assessmentId: number) {
  const { data } = await api.get(`/assessment/analytics/assessment/${assessmentId}`)
  return data
}

export async function getAssessmentAnalyticsCoder(coderName: string, employeeId?: string) {
  const { data } = await api.get('/assessment/analytics/coder', {
    params: { coder_name: coderName, ...(employeeId ? { employee_id: employeeId } : {}) },
  })
  return data
}

export async function getAssessmentAnalyticsBySpecialty() {
  const { data } = await api.get('/assessment/analytics/by-specialty')
  return data
}

export async function getAssessmentAnalyticsByTopic() {
  const { data } = await api.get('/assessment/analytics/by-topic')
  return data
}

export async function getAssessmentAnalyticsByBatch() {
  const { data } = await api.get('/assessment/analytics/by-batch')
  return data
}

export async function getAssessmentAnalyticsBatchDrill(batchName: string) {
  const { data } = await api.get(`/assessment/analytics/batch-drill/${encodeURIComponent(batchName)}`)
  return data
}

export async function getAssessmentAnalyticsCoderMatrix() {
  const { data } = await api.get('/assessment/analytics/coder-matrix')
  return data
}

export function downloadAssessmentCoderReport(coderName: string, employeeId?: string) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ coder_name: coderName })
  if (employeeId) params.set('employee_id', employeeId)
  window.open(`${base}/assessment/analytics/coder-report.pdf?${params}`)
}

export function downloadAssessmentBatchReport(batchName: string) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ batch_name: batchName })
  window.open(`${base}/assessment/analytics/batch-report.pdf?${params}`)
}
