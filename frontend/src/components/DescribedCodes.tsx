import type { ReactNode } from 'react'
import { useCodeDescriptions } from '../hooks/useCodeDescriptions'

/**
 * Looks up what a list of codes mean and hands a describe() to its children.
 *
 * For summary chips — "most missed: I50.9 (4×)" — where a leader reads codes
 * as coaching topics. The description goes in a hover title: the chips stay
 * compact, and the full text is one hover away. A component rather than a
 * hook at the call site, so it can sit inside a list or a branch without
 * moving a hook below an early return (React #310).
 *
 * No section is given: these lists mix diagnoses and procedures. The code
 * systems do not overlap in practice, and an unknown code is simply silent.
 */
export function DescribedCodes({ codes, children }: {
  codes: string[]
  children: (describe: (code: string) => string) => ReactNode
}) {
  const lookup = useCodeDescriptions(codes)
  return <>{children(code => lookup(code)?.description || '')}</>
}
