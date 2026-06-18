import api from './client'

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
