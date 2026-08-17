/**
 * E/M encounter categories — mirrors MDM_CATEGORIES and _CATEGORY_CODES in
 * backend/routers/practicelab_pkg/em_grading.py.
 *
 * The category decides what the screen asks for. Office, inpatient/observation
 * and emergency visits are levelled by the MDM tables, so those screens ask for
 * COPA / Data Review / Risk. A preventive visit is levelled by age and patient
 * type and critical care by the clock, so asking either of them for MDM
 * elements is asking about something that is not in the chart.
 *
 * On the answer-key screen the trainer may state the category. On the coder
 * screen it is derived from the code the coder themselves typed — deriving it
 * from the key would tell them what kind of encounter to expect, which is part
 * of what they are being assessed on.
 */
export type EMCategory =
  | 'office'
  | 'inpatient_observation'
  | 'emergency'
  | 'preventive'
  | 'critical_care'
  | 'other'

export const EM_CATEGORY_LABELS: Record<EMCategory, string> = {
  office: 'Office / outpatient',
  inpatient_observation: 'Inpatient & observation',
  emergency: 'Emergency department',
  preventive: 'Preventive medicine',
  critical_care: 'Critical care',
  other: 'Other',
}

export const EM_CATEGORY_ORDER: EMCategory[] = [
  'office', 'inpatient_observation', 'emergency',
  'preventive', 'critical_care', 'other',
]

const MDM_CATEGORIES: EMCategory[] = ['office', 'inpatient_observation', 'emergency']

/** Code lists per category. Spelled out, not range-matched — E/M numbering is
 *  not contiguous by category and a range test would swallow future additions. */
export const EM_CODES_BY_CATEGORY: Record<EMCategory, string[]> = {
  office: ['99202', '99203', '99204', '99205',
    '99211', '99212', '99213', '99214', '99215'],
  inpatient_observation: ['99221', '99222', '99223',
    '99231', '99232', '99233', '99234', '99235', '99236', '99238', '99239'],
  emergency: ['99281', '99282', '99283', '99284', '99285'],
  preventive: ['99381', '99382', '99383', '99384', '99385', '99386', '99387',
    '99391', '99392', '99393', '99394', '99395', '99396', '99397',
    '99401', '99402', '99403', '99404', '99411', '99412', '99429'],
  critical_care: ['99291', '99292',
    '99468', '99469', '99471', '99472', '99475', '99476',
    '99477', '99478', '99479', '99480'],
  other: [],
}

const CODE_TO_CATEGORY: Record<string, EMCategory> = {}
;(Object.keys(EM_CODES_BY_CATEGORY) as EMCategory[]).forEach(cat => {
  EM_CODES_BY_CATEGORY[cat].forEach(code => { CODE_TO_CATEGORY[code] = cat })
})

/** Anything unrecognised is 'other', never a guess. */
export function emCategory(code: string): EMCategory {
  return CODE_TO_CATEGORY[(code || '').trim().toUpperCase()] || 'other'
}

export function categoryUsesMdm(category: EMCategory): boolean {
  return MDM_CATEGORIES.includes(category)
}

/** A key's own category when it states one, otherwise derived from its code. */
export function resolveCategory(stored: string | null | undefined, code: string): EMCategory {
  const c = (stored || '').trim().toLowerCase() as EMCategory
  return EM_CATEGORY_ORDER.includes(c) ? c : emCategory(code)
}

