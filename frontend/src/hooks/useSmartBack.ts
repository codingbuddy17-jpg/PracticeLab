import { useNavigate, useLocation } from 'react-router-dom'

/**
 * Back that returns where you came from, with a sensible fallback.
 *
 * Hardcoding a destination assumes one origin. The Chart Management sub-pages
 * all pointed at the trainer home, so leaving Manage Charts skipped the hub of
 * six cards you arrived through — and Feedback, which is reachable from BOTH
 * the hub and the trainer home, sent you to the wrong one half the time.
 *
 * `location.key` is "default" only when this is the first entry in the history
 * stack — a fresh tab, a deep link, or a reload. In that case there is nothing
 * to go back to, so the fallback is used.
 */
export function useSmartBack(fallback: string) {
  const navigate = useNavigate()
  const location = useLocation()
  return () => {
    if (location.key && location.key !== 'default') navigate(-1)
    else navigate(fallback)
  }
}
