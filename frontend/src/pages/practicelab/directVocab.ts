/**
 * What a Formal Batch and a Direct Assignment each call the same machinery.
 *
 * Both run on Batch / BatchAllocationCycle / BatchChart, and that reuse is
 * deliberate — it is the reason results, grading and analytics behave
 * identically for both. The problem was that the cohort's vocabulary leaked
 * through: a trainer sending one coder two sepsis charts was asked to "Run
 * Cycle 1" and read "Allocation Cycles", which made a two-minute task look
 * like a programme of work.
 *
 * This is a LABEL MAP and nothing else. There is deliberately no branching
 * logic behind it — one set of behaviour, two vocabularies — because a genuine
 * fork is how a rule ends up fixed in the batch path and forgotten in the
 * direct one.
 */
export interface Vocab {
  /** The act of putting charts in front of coders. */
  assign: string
  /** The list of times that has happened. */
  assignments: string
  /** Doing it again, later. */
  assignAgain: string
  /** Creating the codes a coder uses to start work. */
  makeCodes: string
  /** Re-creating them. */
  remakeCodes: string
  /** The panel those codes live in. */
  codesPanel: string
  /** The record of what happened to this batch/assignment. */
  log: string
  /** Ending it. */
  close: string
  /** The thing itself, for prose. */
  noun: string
}

const BATCH: Vocab = {
  assign: 'Run Cycle',
  assignments: 'Allocation Cycles',
  assignAgain: 'Run New Cycle',
  makeCodes: 'Generate Practice Sessions',
  remakeCodes: 'Regenerate Sessions',
  codesPanel: 'Practice Sessions',
  log: 'Batch Log',
  close: 'Close Batch',
  noun: 'batch',
}

const DIRECT: Vocab = {
  assign: 'Assign Charts',
  assignments: 'Assigned Charts',
  assignAgain: 'Add Follow-up Charts',
  makeCodes: 'Create Access Codes',
  remakeCodes: 'Recreate Access Codes',
  codesPanel: 'Access Codes',
  log: 'Assignment Log',
  close: 'Close Assignment',
  noun: 'assignment',
}

export function vocab(isDirect: boolean | undefined): Vocab {
  return isDirect ? DIRECT : BATCH
}
