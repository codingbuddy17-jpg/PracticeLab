/**
 * How the master passphrase reaches the server.
 *
 * As a header, never a query parameter. It is the single shared credential
 * behind chart retirement, answer-key deletion, force-close and the question
 * bank, and a query string is written verbatim into server, proxy and CDN
 * access logs — and into browser history for anything opened as a URL.
 *
 * The backend accepts either, so a call site that has not migrated still
 * works; this exists so that new ones do not have to think about it.
 */
export const ADMIN_PASSPHRASE_HEADER = 'X-Admin-Passphrase'

export function adminAuth(passphrase?: string) {
  // Optional because several call sites take the passphrase as an optional
  // argument — the server refuses the request either way, and sending an empty
  // header would be a lie about what was supplied.
  return passphrase
    ? { headers: { [ADMIN_PASSPHRASE_HEADER]: passphrase } }
    : {}
}
