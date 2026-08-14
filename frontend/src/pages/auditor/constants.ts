/**
 * The specialties the auditor module works on.
 *
 * Phase 1 is the abstract coding specialties — the ones where a claim has
 * enough structure to introduce a realistic error into. E/M and the
 * edits/denials specialties are deliberately absent.
 *
 * This list was copied into two screens before it was copied into a third;
 * it lives here so the copies cannot drift apart.
 */
export const AUDITABLE = [
  'IP-DRG', 'SDS', 'ED Facility', 'Surgery', 'ED Single Path', 'Ancillary',
] as const
