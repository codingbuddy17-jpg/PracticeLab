/**
 * Turn any thrown request error into something a trainer can act on.
 *
 * `err?.response?.data?.detail || 'Upload failed'` looks like it reports the
 * reason, but it collapses every case where `detail` is absent into one blank
 * message: the request never reached the server, the server replied with HTML
 * from a proxy rather than JSON, the body was rejected as too large, the
 * gateway timed out, or FastAPI returned a 422 whose `detail` is an array
 * rather than a string. All of those are different problems with different
 * fixes, and all of them read as "it just failed".
 */
export function errorMessage(e: any, fallback = 'Request failed'): string {
  // No response at all: blocked, offline, CORS, or the request was aborted.
  if (e?.response === undefined) {
    if (e?.code === 'ECONNABORTED') return 'The request timed out before the server replied.'
    return `Could not reach the server (${e?.message || 'network error'}). Check your connection and try again.`
  }

  const { status, data } = e.response

  // FastAPI validation errors: detail is a list of {loc, msg, type}.
  if (Array.isArray(data?.detail)) {
    const first = data.detail[0]
    const where = Array.isArray(first?.loc) ? first.loc.slice(1).join('.') : ''
    return `${first?.msg || 'Invalid request'}${where ? ` (field: ${where})` : ''}`
  }

  if (typeof data?.detail === 'string') return data.detail
  if (typeof data?.detail?.message === 'string') return data.detail.message
  if (typeof data === 'string' && data.trim() && !data.trim().startsWith('<')) return data

  // A body we cannot read — usually a proxy's HTML error page. The status is
  // then the only real information, so say what it means.
  if (status === 413) return 'The file is too large for the server to accept.'
  if (status === 502 || status === 503 || status === 504)
    return `The server did not finish in time (HTTP ${status}). If the file is large, try splitting it.`
  if (status >= 500) return `The server hit an error (HTTP ${status}). Nothing was saved.`

  return `${fallback} (HTTP ${status}).`
}
