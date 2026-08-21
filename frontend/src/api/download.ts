import api from './client'

/**
 * Fetch a file and hand it to the browser as a download.
 *
 * window.open() sends the browser straight at the endpoint, so it cannot tell
 * a PDF from a 404: an error opens a blank tab showing raw JSON, and the user
 * reads it as the app breaking. Fetching first means a failure is a message the
 * caller can show.
 *
 * Two further reasons this matters here: several report URLs carried a
 * passphrase in the query string, where it lands in history and server logs;
 * and a blob download keeps the user on the page they were working in.
 *
 * Pass the master passphrase through `headers` (see adminAuth) rather than
 * `params`: a query string is written to access logs and, for anything opened
 * as a URL, to browser history.
 *
 * Throws with the server's `detail` when the request fails.
 */
export async function downloadFile(
  path: string,
  filename: string,
  params?: Record<string, string | number | undefined>,
  headers?: Record<string, string>,
) {
  let res
  try {
    res = await api.get(path, { params, headers, responseType: 'blob' })
  } catch (e: any) {
    throw new Error(await detailOf(e))
  }
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * An error body arrives as a Blob when responseType is 'blob', so the usual
 * `e.response.data.detail` is a Blob rather than a string and reads as
 * "[object Blob]" if used directly.
 */
async function detailOf(e: any): Promise<string> {
  const data = e?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      const d = parsed?.detail
      return typeof d === 'string' ? d : (d?.message || 'Download failed.')
    } catch {
      return 'Download failed.'
    }
  }
  return data?.detail?.message || data?.detail || e?.message || 'Download failed.'
}
