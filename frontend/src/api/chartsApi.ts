/// <reference types="vite/client" />
import api from './client'
import type { Chart, ChartWithRationale, SearchResult, BulkUploadResult, BulkUploadMeta } from '../types'

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

export async function getChartTrainer(chartId: number): Promise<ChartWithRationale> {
  const { data } = await api.get(`/charts/${chartId}/trainer`)
  return data
}

export async function updateChart(chartId: number, actor: string, payload: Partial<{ category: string; difficulty: string; rationale: string; alias: string }>) {
  const { data } = await api.patch(`/charts/${chartId}`, payload, { params: { actor } })
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

export async function addFilesToChart(chartId: number, files: File[], uploadedBy: string): Promise<{ message: string }> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  form.append('uploaded_by', uploadedBy)
  const { data } = await api.post(`/upload/${chartId}/add-files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function purgeChart(chartId: number, passphrase: string) {
  const { data } = await api.delete(`/charts/${chartId}/purge`, { params: { passphrase } })
  return data
}

export async function getChartStats(): Promise<{ total_charts: number; open_feedback: number; total_specialties: number }> {
  const { data } = await api.get('/charts/stats')
  return data
}
