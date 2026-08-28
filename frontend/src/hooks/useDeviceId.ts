/**
 * A stable id for THIS browser, so a session can be held by one device.
 *
 * The access code was the whole credential, so the same code opened on a
 * second machine worked there too — both live on the same session at once.
 * The server refuses the second one while the first is active; this is what
 * lets it tell them apart.
 *
 * It identifies a browser, not a person: it is random, carries nothing about
 * the user, and is worth nothing to anyone who reads it. Losing it — a cleared
 * profile, a private window — costs a coder nothing beyond waiting out the
 * idle window, because the claim expires rather than locking.
 */
const KEY = 'practicelab_device_id'

export function deviceId(): string {
  try {
    let id = localStorage.getItem(KEY)
    if (!id) {
      id = (crypto?.randomUUID?.() ?? `d${Date.now()}${Math.random().toString(36).slice(2)}`)
      localStorage.setItem(KEY, id)
    }
    return id
  } catch {
    // Private mode or blocked storage. A per-tab id still separates two
    // machines, which is the case this exists for; it just will not survive a
    // reload, and the coder waits out the idle window instead.
    const w = window as any
    w.__pl_device ||= `t${Math.random().toString(36).slice(2)}`
    return w.__pl_device
  }
}
