/// <reference types="vite/client" />
import api from './client'

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

export function exportAllAssessmentQuestions(passphrase: string, trainerName: string, specialty?: string): void {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ passphrase, trainer_name: trainerName })
  if (specialty) params.set('specialty', specialty)
  window.open(`${base}/assessment/questions/export-all?${params}`, '_blank')
}

export async function uploadAssessmentQuestions(specialty: string, uploadedBy: string, file: File) {
  const form = new FormData()
  form.append('specialty', specialty)
  form.append('uploaded_by', uploadedBy)
  form.append('file', file)
  const { data } = await api.post('/assessment/questions/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as {
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

export async function getAssessmentAnalyticsOverview() {
  const { data } = await api.get('/assessment/analytics/overview')
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
      coder_name: coderName,
      ...(employeeId ? { employee_id: employeeId } : {}),
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    },
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

export function downloadAssessmentCoderReport(
  coderName: string,
  employeeId?: string,
  dateFrom?: string,
  dateTo?: string,
  excludeSessionIds?: number[],
) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ coder_name: coderName })
  if (employeeId) params.set('employee_id', employeeId)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (excludeSessionIds && excludeSessionIds.length > 0)
    params.set('exclude_session_ids', excludeSessionIds.join(','))
  window.open(`${base}/assessment/analytics/coder-report.pdf?${params}`)
}

export function downloadAssessmentBatchReport(batchName: string) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ batch_name: batchName })
  window.open(`${base}/assessment/analytics/batch-report.pdf?${params}`)
}

export function downloadAssessmentBatchCoderReportsZip(batchName: string) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const params = new URLSearchParams({ batch_name: batchName })
  window.open(`${base}/assessment/analytics/batch-coder-reports.zip?${params}`)
}

export async function parseStandaloneQuestions(file: File): Promise<{ questions: object[]; count: number; errors: string[] }> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/assessment/questions/parse-standalone', form)
  return data
}
