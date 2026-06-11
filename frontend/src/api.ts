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

export async function updateChart(chartId: number, actor: string, payload: Partial<{ category: string; difficulty: string; rationale: string }>) {
  const { data } = await api.patch(`/charts/${chartId}`, payload, { params: { actor } })
  return data as Chart
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

export async function uploadAnswerKeys(file: File, specialty: string, enteredBy: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('specialty', specialty)
  form.append('entered_by', enteredBy)
  const { data } = await api.post('/practicelab/answer-key/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { stored: string[]; skipped_duplicates: string[]; not_found: string[] }
}

export async function deleteAnswerKey(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/practicelab/answer-key/${chartId}`, { params: { passphrase } })
  return data
}

export async function getAnswerKeyStatus(specialty?: string) {
  const { data } = await api.get('/practicelab/answer-key/status', { params: { specialty } })
  return data as { total_charts: number; with_answer_key: number; without_answer_key: number }
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
  overcoding_penalty: boolean; passphrase: string; updated_by: string;
}) {
  const { data } = await api.put('/practicelab/config/scoring', payload)
  return data
}

export async function createBatch(payload: {
  name: string; specialty: string; categories: string[]; difficulties: string[];
  charts_per_coder: number; coders: { name: string; emp_id: string }[]; created_by: string;
}) {
  const { data } = await api.post('/practicelab/batches', payload)
  return data as { batch_id: number; name: string; pool_size: number }
}

export async function listBatches(status?: string, specialty?: string) {
  const { data } = await api.get('/practicelab/batches', { params: { status, specialty } })
  return data as Array<{
    id: number; name: string; specialty: string; charts_per_coder: number;
    status: string; created_by: string; created_at: string; coder_count: number;
  }>
}

export async function getBatch(batchId: number) {
  const { data } = await api.get(`/practicelab/batches/${batchId}`)
  return data
}

export function downloadBatchExcel(batchId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/generate-excel`, '_blank')
}

export async function gradeSubmissions(batchId: number, files: File[]) {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  const { data } = await api.post(`/practicelab/batches/${batchId}/grade`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { graded: string[]; errors: string[] }
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

export function downloadBatchResultsExcel(batchId: number) {
  window.open(`${import.meta.env.VITE_API_URL || '/api'}/practicelab/batches/${batchId}/results/export`, '_blank')
}

export async function getPLAnalyticsOverview() {
  const { data } = await api.get('/practicelab/analytics/overview')
  return data
}

export async function getPLAnalyticsBySpecialty() {
  const { data } = await api.get('/practicelab/analytics/by-specialty')
  return data
}

export async function getPLAnalyticsByChart() {
  const { data } = await api.get('/practicelab/analytics/by-chart')
  return data
}

export async function getPLAnalyticsByBatch() {
  const { data } = await api.get('/practicelab/analytics/by-batch')
  return data
}

export async function getCoderTrend(coderName: string) {
  const { data } = await api.get('/practicelab/analytics/coder-trend', { params: { coder_name: coderName } })
  return data
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
  return `/api/reports/export?${q.toString()}`
}
