/// <reference types="vite/client" />
import api from './client'
import { adminAuth } from './adminAuth'
import type { Chart, ChartWithRationale, SearchResult, BulkUploadResult, BulkUploadMeta } from '../types'

/**
 * Chart search. `include_trainer_fields: true` adds difficulty, which the
 * server withholds by default — it is trainer metadata and the coder-facing
 * library must not receive it.
 */
export async function searchCharts(params: Record<string, string | number | boolean | undefined>): Promise<SearchResult> {
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

/**
 * One chart by id. Needed to open the viewer from a link, where the chart is
 * not already in the loaded search results — a shared URL, or a reload.
 */
export async function getChart(chartId: number): Promise<Chart> {
  const { data } = await api.get(`/charts/${chartId}`)
  return data
}

export async function getChartTrainer(chartId: number): Promise<ChartWithRationale> {
  const { data } = await api.get(`/charts/${chartId}/trainer`)
  return data
}

export async function updateChart(chartId: number, actor: string, payload: Partial<{ category: string; difficulty: string; rationale: string; alias: string }>, passphrase?: string) {
  const { data } = await api.patch(`/charts/${chartId}`, payload, { params: { actor }, ...adminAuth(passphrase) })
  return data as Chart
}

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
  const { data } = await api.post(`/charts/${chartId}/retire`, null, { params: { actor }, ...adminAuth(passphrase) })
  return data
}

export async function restoreChart(chartId: number, actor: string, passphrase?: string) {
  const { data } = await api.post(`/charts/${chartId}/restore`, null, { params: { actor }, ...adminAuth(passphrase) })
  return data
}

export async function previewChartNumbers(items: { filename: string; specialty: string }[]): Promise<{ filename: string; specialty: string; assigned_number: string }[]> {
  const { data } = await api.post('/upload/preview', items)
  return data
}

export async function bulkUpload(
  files: File[],
  metaList: BulkUploadMeta[],
  signal?: AbortSignal,
): Promise<BulkUploadResult[]> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('metadata', JSON.stringify(metaList))
  const { data } = await api.post('/upload/bulk', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
  })
  return data
}

/**
 * Swap a chart's pages for a corrected copy. The chart number, answer key,
 * audit history and every grading result stay attached — only the images
 * change. The reason is required and lands in the audit log.
 */
export async function replaceChartFiles(
  chartId: number, files: File[], uploadedBy: string, reason: string, passphrase?: string,
): Promise<{ message: string; pages_removed: number; pages_added: number; grading_results_kept: number }> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('uploaded_by', uploadedBy)
  form.append('reason', reason)
  if (passphrase) form.append('passphrase', passphrase)
  const { data } = await api.post(`/upload/${chartId}/replace-files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function addFilesToChart(chartId: number, files: File[], uploadedBy: string, passphrase?: string): Promise<{ message: string }> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('uploaded_by', uploadedBy)
  if (passphrase) form.append('passphrase', passphrase)
  const { data } = await api.post(`/upload/${chartId}/add-files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function purgeChart(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/charts/${chartId}/purge`, adminAuth(passphrase))
  return data
}

export async function getChartStats(): Promise<{
  total_charts: number; open_feedback: number; total_specialties: number
  specialties: { specialty: string; charts: number }[]
  charts_with_keys: number; charts_without_keys: number
}> {
  const { data } = await api.get('/charts/stats')
  return data
}
