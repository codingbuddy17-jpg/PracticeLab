import { CodeInfo } from '../api/codesApi'

/**
 * What a code says, under the box it was typed into.
 *
 * The distinction this exists for: `CodeSuggest` shows descriptions while
 * someone is TYPING, which helps them pick. This shows the description of the
 * code that is already there, which is what lets someone check a code they did
 * not just enter — reopening a saved answer key, or reading a claim.
 *
 * On a coder screen a description is a study aid. On a KEY screen it is a
 * check, and a wrong key is worse than a wrong answer because it silently
 * grades everyone against it.
 *
 * Renders nothing rather than a placeholder when there is no description:
 * CPT is unlicensed and absent by design, and an empty row under every
 * procedure line would read as breakage.
 */
export function CodeCaption({ code, describe, system }: {
  code: string
  /** The lookup from useCodeDescriptions. */
  describe?: ((code: string) => CodeInfo | null) & {
    knownAbsent?: (code: string, system: string) => boolean
  }
  /**
   * The code system, when the caller wants "that is not a real code" said as
   * well. Only ever said when the table was actually loaded — otherwise an
   * absent description means nobody ran the ingest.
   */
  system?: string
}) {
  if (!describe) return null
  const info = describe(code || '')
  if (!info) {
    if (code && system && describe.knownAbsent?.(code, system)) {
      return (
        <div style={notFound}>{code} is not in the {label(system)} list</div>
      )
    }
    return null
  }
  // The long description, not the short one: the short form is abbreviated for
  // narrow print columns ("Ketorolac tromethamine inj") and there is room here.
  return <div style={caption} title={info.description}>{info.description}</div>
}

function label(system: string): string {
  return system === 'ICD10CM' ? 'ICD-10-CM'
    : system === 'ICD10PCS' ? 'ICD-10-PCS'
    : system === 'HCPCSMOD' ? 'HCPCS modifier'
    : 'HCPCS'
}

const caption: React.CSSProperties = {
  fontSize: 11.5, color: '#475569', lineHeight: 1.4, marginTop: 4,
  padding: '4px 8px', background: '#f8fafc',
  border: '1px solid #e2e8f0', borderRadius: 6,
}

const notFound: React.CSSProperties = {
  fontSize: 11, color: '#b45309', fontWeight: 600, lineHeight: 1.4,
  marginTop: 4, padding: '4px 8px', background: '#fffbeb',
  border: '1px solid #fde68a', borderRadius: 6,
}
