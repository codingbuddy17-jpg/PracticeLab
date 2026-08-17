/**
 * The specialties the auditor module works on.
 *
 * Every one of these has a claim with enough structure to introduce a
 * realistic error into. E/M and ED Profee are audited on the CODE — the level
 * chosen, its modifier, and the diagnoses supporting it — which is what an
 * auditor reviews in practice; the MDM elements behind the level are graded in
 * PracticeLab and are not part of the audit form.
 *
 * Edits and Denials are absent and stay absent: they are graded against a
 * rubric, not a claim, so there is nothing to introduce an error into.
 *
 * This list was copied into two screens before it was copied into a third; it
 * lives here so the copies cannot drift apart. It must also match
 * AUDITABLE_SPECIALTIES on the backend — a test asserts that, because the
 * specialty-sync checker does not cover this list.
 */
export const AUDITABLE = [
  'IP-DRG', 'SDS', 'ED Facility', 'Surgery', 'ED Single Path', 'Ancillary',
  'E/M', 'ED Profee',
] as const
