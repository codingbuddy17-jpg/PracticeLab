/// <reference types="vite/client" />
import api from './client'
import { adminAuth } from './adminAuth'
import { getPassphrase, rememberPassphrase } from './assessmentAuth'
import { downloadFile } from './download'

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
  const { data } = await api.get('/assessment/questions',
    { params, ...adminAuth(getPassphrase()) })
  return data as { total: number; page: number; page_size: number; results: unknown[] }
}

export async function verifyAssessmentPassphrase(trainerName: string, passphrase: string): Promise<boolean> {
  try {
    await api.post('/assessment/audit/verify-passphrase', null, {
      params: { trainer_name: trainerName }, ...adminAuth(passphrase),
    })
    rememberPassphrase(passphrase)
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
    params: { specialty: specialty || undefined }, ...adminAuth(passphrase),
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

export interface PoolReadiness {
  per_paper: number
  coders: number
  verdict: 'insufficient' | 'near_identical' | 'heavy_overlap' | 'workable' | 'strong'
  headline: string
  advice: string
  overlap_pct: number | null
  shared_questions: number | null
  uniqueness_pct: number | null
  pool_for_light_overlap: number
  pool_for_strong: number
}

export interface PoolSummary {
  specialty: string
  total_active: number
  total_inactive: number
  by_topic: { topic: string; count: number }[]
  by_difficulty: Record<string, number>
  readiness: PoolReadiness | Record<string, never>
  difficulty_outlook: {
    auto_mix_pct?: Record<string, number>
    short_buckets?: string[]
    notes?: string[]
  }
}

export async function getAssessmentPoolSummary(
  specialty: string,
  questionsPerPaper?: number,
  coders?: number,
) {
  const { data } = await api.get('/assessment/questions/pool-summary', {
    params: {
      specialty,
      ...(questionsPerPaper ? { questions_per_paper: questionsPerPaper } : {}),
      ...(coders ? { coders } : {}),
    },
  })
  return data as PoolSummary
}

/**
 * Blob downloads rather than window.open().
 *
 * Two gains. A failed export (wrong passphrase) now raises a message instead of
 * opening a blank tab showing the raw JSON error. And because this is an XHR
 * rather than a navigation, the passphrase no longer enters the browser's
 * history or the tab's address bar.
 *
 * It is still a query parameter on the wire, so it still reaches server access
 * logs. Moving it to a header would fix that, and needs the backend endpoints
 * to accept it there.
 */
export function exportAssessmentQuestions(specialty: string, passphrase: string, trainerName: string) {
  return downloadFile(
    '/assessment/questions/export',
    `${specialty.replace(/\s+/g, '_')}_Questions.xlsx`,
    { specialty, passphrase, trainer_name: trainerName },
  )
}

export function exportAllAssessmentQuestions(passphrase: string, trainerName: string, specialty?: string) {
  return downloadFile(
    '/assessment/questions/export-all',
    specialty ? `${specialty.replace(/\s+/g, '_')}_Questions.xlsx` : 'Assessment_Question_Bank.xlsx',
    { passphrase, trainer_name: trainerName, specialty: specialty || undefined },
  )
}

export async function uploadAssessmentQuestions(
  specialty: string, uploadedBy: string, file: File, dryRun = false,
) {
  const form = new FormData()
  form.append('specialty', specialty)
  form.append('uploaded_by', uploadedBy)
  form.append('file', file)
  // A preview reports exactly what a real upload would do, and writes nothing.
  if (dryRun) form.append('dry_run', 'true')
  const { data } = await api.post('/assessment/questions/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as {
    dry_run: boolean
    stored: number; stored_ids: string[]
    created: number; created_ids: string[]
    updated: number; updated_ids: string[]
    duplicates: number; duplicate_warnings: string[]
    skipped: number; errors: string[]
  }
}

export function downloadAssessmentTemplate(specialty: string): void {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/assessment/questions/template?specialty=${encodeURIComponent(specialty)}`, '_blank')
}

export async function updateQuestionStatus(questionId: string, status: string, updatedBy: string) {
  const { data } = await api.put(
    `/assessment/questions/${encodeURIComponent(questionId)}/status`,
    null,
    { params: { status, updated_by: updatedBy }, ...adminAuth(getPassphrase()) },
  )
  return data
}

export async function updateQuestion(questionId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/assessment/questions/${encodeURIComponent(questionId)}`,
    payload, adminAuth(getPassphrase()))
  return data
}

/**
 * Repeated params, one pair per mix row: ?specialty=A&topic_filter=x&specialty=B…
 *
 * These used to be comma-joined into single strings, which collided with the
 * commas INSIDE a row's own topic filter (where they mean "any of these"). The
 * preview then counted a different pool from the one generation would use.
 */
export async function getAssessmentPoolPreview(
  rows: { specialty: string; topicFilter?: string }[],
): Promise<unknown[]> {
  const qs = new URLSearchParams()
  for (const r of rows) {
    qs.append('specialty', r.specialty)
    qs.append('topic_filter', r.topicFilter || '')
  }
  const { data } = await api.get(`/assessment/pool-preview?${qs.toString()}`)
  return data
}

export async function generateAssessment(payload: Record<string, unknown>) {
  const { data } = await api.post('/assessment/generate', payload)
  return data
}

/**
 * Delete an assessment. Refused by default once anyone has sat it — `force`
 * with a written reason is the deliberate override, and is audit-logged.
 */
export async function deleteAssessment(
  assessmentId: number,
  opts: { passphrase: string; trainerName: string; force?: boolean; reason?: string },
) {
  const { data } = await api.delete(`/assessment/${assessmentId}`, {
    params: {
      passphrase: opts.passphrase,
      trainer_name: opts.trainerName,
      ...(opts.force ? { force: true, reason: opts.reason } : {}),
    },
  })
  return data as { deleted: number; sessions_removed: number; completed_removed: number }
}

export type AssessmentHistoryRow = {
    id: number
    assessment_name: string
    config_name: string | null
    batch_name: string | null
    /** null means the paper uses the platform default. */
    pass_threshold: number | null
    student_count: number
    questions_per_student: number
    generated_by: string
    generated_at: string | null
    status_counts?: { pending: number; in_progress: number; submitted: number; expired: number }
  }

export async function listAssessmentHistory(): Promise<AssessmentHistoryRow[]>
export async function listAssessmentHistory(params: { search?: string; page: number; page_size?: number }): Promise<{
  total: number; page: number; page_size: number; results: AssessmentHistoryRow[]
}>
export async function listAssessmentHistory(params?: { search?: string; page?: number; page_size?: number }) {
  const { data } = await api.get('/assessment/history', { params })
  return data
}

/** Open, like the other two Sessions-tab downloads. */
export function exportAssessmentPDF(assessmentId: number) {
  return downloadFile(`/assessment/${assessmentId}/export-pdf`,
    `Assessment_${assessmentId}_papers.zip`)
}

export function exportAnswerKey(assessmentId: number) {
  return downloadFile(`/assessment/${assessmentId}/export-answer-key`,
    `Assessment_${assessmentId}_Answer_Key.pdf`)
}

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

export async function listAssessmentSessions(assessmentId: number, params?: {
  search?: string; status?: string; page?: number; page_size?: number
}) {
  const { data } = await api.get(`/assessment/${assessmentId}/sessions`, { params })
  return data as {
    sessions: SessionRow[]
    pass_threshold: number
    total: number
    page: number
    page_size: number
    status_counts?: { pending: number; in_progress: number; submitted: number; expired: number; auto_submitted?: number }
  }
}

/** Per-question responses for every coder. */
export function downloadAssessmentResponsesXlsx(assessmentId: number) {
  return downloadFile(`/assessment/${assessmentId}/export-responses.xlsx`,
    `Assessment_${assessmentId}_Responses.xlsx`)
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
  /** A trainer has corrected at least one answer on this session. */
  corrected: boolean
  score_pct: number | null
  correct_count: number | null
  total_questions: number | null
  time_taken_seconds: number | null
}

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

/**
 * The window the trainer is looking through. Shared by every analytics tab so
 * one selection means the same thing everywhere.
 */
export interface AFilters {
  dateFrom?: string
  dateTo?: string
  batchName?: string
}

/** AFilters -> query params, omitting anything unset. */
export function afp(f: AFilters = {}) {
  return {
    ...(f.dateFrom ? { date_from: f.dateFrom } : {}),
    ...(f.dateTo ? { date_to: f.dateTo } : {}),
    ...(f.batchName ? { batch_name: f.batchName } : {}),
  }
}

export async function getAssessmentAnalyticsOverview(f: AFilters = {}) {
  const { data } = await api.get('/assessment/analytics/overview', { params: afp(f) })
  return data
}

export async function getAssessmentAnalyticsByAssessment(assessmentId: number) {
  const { data } = await api.get(`/assessment/analytics/assessment/${assessmentId}`)
  return data
}

export async function getAssessmentAnalyticsCoder(
  coderName: string,
  employeeId?: string,
  dateFrom?: string,
  dateTo?: string,
) {
  const { data } = await api.get('/assessment/analytics/coder', {
    params: {
      ...(coderName ? { coder_name: coderName } : {}),
      ...(employeeId ? { employee_id: employeeId } : {}),
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    },
  })
  return data
}

export async function getAssessmentAnalyticsBySpecialty(f: AFilters = {}) {
  const { data } = await api.get('/assessment/analytics/by-specialty', { params: afp(f) })
  return data
}

export async function getAssessmentAnalyticsByTopic(f: AFilters = {}) {
  const { data } = await api.get('/assessment/analytics/by-topic', { params: afp(f) })
  return data
}

export async function getAssessmentAnalyticsByBatch() {
  const { data } = await api.get('/assessment/analytics/by-batch')
  return data
}

export async function getAssessmentAnalyticsBatchDrill(batchName: string, batchKey?: string) {
  const { data } = await api.get('/assessment/analytics/batch-drill', {
    params: { batch_name: batchName, batch_key: batchKey || undefined },
  })
  return data
}

export async function getAssessmentAnalyticsCoderMatrix(f: AFilters = {}) {
  const { data } = await api.get('/assessment/analytics/coder-matrix', { params: afp(f) })
  return data
}

export async function getAssessmentQuestionSignals(f: AFilters = {}, minAttempts = 5) {
  const { data } = await api.get('/assessment/analytics/question-signals', {
    params: { ...afp(f), min_attempts: minAttempts },
  })
  return data
}

/**
 * Correct one graded answer. The justification is mandatory server-side — a
 * correction without a reason is indistinguishable from a mistake, and this is
 * the one place a coder's result can move after the fact.
 */
export async function overrideAssessmentAnswer(
  assessmentId: number, sessionId: number, questionIndex: number,
  body: { is_correct: boolean; reason: string; trainer_name: string },
  passphrase?: string,
) {
  const { data } = await api.post(
    `/assessment/${assessmentId}/session/${sessionId}/response/${questionIndex}/override`,
    body,
    adminAuth(passphrase ?? getPassphrase()),
  )
  return data as {
    is_correct: boolean; score_pct: number | null
    correct_count: number | null; total_questions: number | null
  }
}

export function downloadAssessmentCoderMatrixXlsx(f: AFilters = {}) {
  return downloadFile('/assessment/analytics/coder-matrix.xlsx',
                      'Assessment_Coder_Matrix.xlsx', afp(f))
}

export function downloadAssessmentCoderReport(
  coderName: string,
  employeeId?: string,
  dateFrom?: string,
  dateTo?: string,
  excludeSessionIds?: number[],
  batchName?: string,
) {
  return downloadFile(
    '/assessment/analytics/coder-report.pdf',
    `${coderName.replace(/\s+/g, '_')}_Assessment_Report.pdf`,
    {
      coder_name: coderName,
      employee_id: employeeId || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      batch_name: batchName || undefined,
      exclude_session_ids: excludeSessionIds?.length ? excludeSessionIds.join(',') : undefined,
    },
  )
}

export function downloadAssessmentBatchReport(batchName: string, batchKey?: string) {
  return downloadFile(
    '/assessment/analytics/batch-report.pdf',
    `${batchName.replace(/\s+/g, '_')}_Batch_Report.pdf`,
    { batch_name: batchName, batch_key: batchKey || undefined },
  )
}

export function downloadAssessmentBatchCoderReportsZip(batchName: string, batchKey?: string) {
  return downloadFile(
    '/assessment/analytics/batch-coder-reports.zip',
    `${batchName.replace(/\s+/g, '_')}_Coder_Reports.zip`,
    { batch_name: batchName, batch_key: batchKey || undefined },
  )
}

export async function parseStandaloneQuestions(file: File): Promise<{ questions: object[]; count: number; errors: string[] }> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/assessment/questions/parse-standalone', form)
  return data
}

/** Headline assessment figures for the trainer home. */
export async function getAssessmentOverview() {
  const { data } = await api.get('/assessment/analytics/overview')
  return data as {
    total_assessments: number; total_sessions: number; total_submitted: number
    unique_coders_assessed: number; overall_pass_rate: number
    avg_score: number; completion_rate: number
    /** The mark a paper is judged against when it does not set its own. */
    default_pass_threshold: number
  }
}
