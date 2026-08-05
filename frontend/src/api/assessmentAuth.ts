/**
 * The trainer passphrase, remembered for one browser session.
 *
 * Several trainer screens need it — the question bank, the answer-key and
 * paper exports — and before this each held its own copy in component state,
 * so a passphrase typed on one screen was unknown to the next. That is why the
 * export buttons could not be passphrase-gated without breaking them.
 *
 * sessionStorage rather than localStorage on purpose: this is the master
 * passphrase, and it should not outlive the tab. It is deliberately not an
 * auth token — the platform has no accounts — so treat it as "the secret this
 * trainer has already proved they know", nothing stronger.
 */
const KEY = 'assessment_passphrase'

export function getPassphrase(): string {
  try {
    return sessionStorage.getItem(KEY) || ''
  } catch {
    return ''   // private browsing, or storage disabled
  }
}

export function rememberPassphrase(passphrase: string): void {
  try {
    sessionStorage.setItem(KEY, passphrase)
  } catch {
    /* non-fatal: the caller still holds it for this screen */
  }
}

export function forgetPassphrase(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to do */
  }
}

/** True when a passphrase has been verified somewhere this session. */
export function hasPassphrase(): boolean {
  return getPassphrase().length > 0
}
