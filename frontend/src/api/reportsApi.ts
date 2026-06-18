/// <reference types="vite/client" />
import api from './client'

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
