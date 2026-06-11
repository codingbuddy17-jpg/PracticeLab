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
