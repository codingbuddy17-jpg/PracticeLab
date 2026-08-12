import { Loader, AlertCircle, CheckCircle, XCircle } from 'lucide-react'

/**
 * Fallback bar for a SCORE, used only until the backend's resolved threshold
 * arrives. Every assessment carries its own pass mark now, so prefer the
 * `default_pass_threshold` / `pass_threshold` the API returns.
 */
export const DEFAULT_PASS = 90

/**
 * Share of coders expected to pass. A POPULATION target — deliberately not the
 * per-paper pass mark, which is a score and a different scale.
 */
export const PASS_RATE_TARGET = 70

/**
 * Colour a SCORE (what one coder scored on one paper) against its own bar.
 *
 * Pass the threshold the backend resolved for that assessment; without one it
 * falls back to DEFAULT_PASS so nothing moves underneath existing views.
 */
export function scoreColor(v: number | null | undefined, threshold?: number | null): string {
  if (v == null) return '#9ca3af'
  const bar = threshold ?? DEFAULT_PASS
  if (v >= bar) return '#16a34a'
  if (v >= bar - 10) return '#d97706'
  return '#dc2626'
}

/**
 * Colour a POPULATION SHARE (what % of coders passed).
 *
 * Distinct from scoreColor() on purpose. A share and a score are different
 * scales, and running a share through the 90 score bar painted a cohort red at
 * 85% of coders passing — a good result — purely because 85 < 90.
 */
export function rateColor(v: number | null | undefined): string {
  if (v == null) return '#9ca3af'
  if (v >= PASS_RATE_TARGET) return '#16a34a'
  if (v >= PASS_RATE_TARGET * 0.7) return '#d97706'
  return '#dc2626'
}

export function bandColor(band: string): string {
  if (band === '90-100') return '#16a34a'
  if (band === '80-89') return '#d97706'
  return '#dc2626'
}

export function fmt(v: number | null | undefined, suffix = '%'): string {
  if (v == null) return '—'
  return `${v}${suffix}`
}

export function fmtTime(sec: number | null | undefined): string {
  if (sec == null) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

export function KpiCard({ label, value, color, icon }: { label: string; value: string; color?: string; icon?: React.ReactNode }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.72)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.6)',
      padding: '18px 22px',
      minWidth: 130,
      flex: 1,
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {icon && <span style={{ color: '#7c3aed' }}>{icon}</span>}
        <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || '#111', letterSpacing: -0.5 }}>
        {value}
      </div>
    </div>
  )
}

export function DiffBadge({ diff }: { diff: string }) {
  const colors: Record<string, { bg: string; color: string }> = {
    Easy: { bg: '#dcfce7', color: '#166534' },
    Medium: { bg: '#fef9c3', color: '#854d0e' },
    Hard: { bg: '#fee2e2', color: '#991b1b' },
  }
  const c = colors[diff] || { bg: '#f3f4f6', color: '#374151' }
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: c.bg, color: c.color }}>
      {diff}
    </span>
  )
}

export function PassBadge({ pf }: { pf: string }) {
  const pass = pf === 'PASS'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
      background: pass ? '#dcfce7' : '#fee2e2',
      color: pass ? '#166534' : '#991b1b',
    }}>
      {pass ? <CheckCircle size={10} /> : <XCircle size={10} />}
      {pf}
    </span>
  )
}

export function Panel({ title, children, style }: { title?: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.68)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderRadius: 16,
      border: '1px solid rgba(255,255,255,0.55)',
      padding: '20px 24px',
      boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
      marginBottom: 22,
      ...style,
    }}>
      {title && <div style={{ fontSize: 14, fontWeight: 800, color: '#111', marginBottom: 16, letterSpacing: -0.2 }}>{title}</div>}
      {children}
    </div>
  )
}

export function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '60px 0', color: '#7c3aed' }}>
      <Loader size={28} style={{ animation: 'spin 1s linear infinite' }} />
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '60px 24px', color: '#9ca3af', gap: 12,
      background: 'rgba(255,255,255,0.5)', borderRadius: 16,
      border: '1px dashed #e5e7eb',
    }}>
      <AlertCircle size={32} />
      <div style={{ fontSize: 14, fontWeight: 600 }}>{message}</div>
    </div>
  )
}

export const inputStyle: React.CSSProperties = {
  padding: '9px 14px', borderRadius: 10, border: '1px solid #e5e7eb',
  fontSize: 13, outline: 'none', minWidth: 220,
}

export const searchBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6,
  padding: '9px 20px', borderRadius: 10,
  background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
  color: '#fff', border: 'none', cursor: 'pointer',
  fontSize: 13, fontWeight: 700,
}

/**
 * One look for every report this module produces.
 *
 * The four downloads — matrix XLSX, coder PDF, batch PDF, batch coder ZIP —
 * had three different visual treatments between them: two competing gradients
 * and a plain outline button, in three different corners. Same kind of action,
 * three appearances, which is most of why the reports felt scattered across
 * the module rather than being a set.
 *
 * They stay in their tabs deliberately. A batch report belongs beside the
 * batch and a coder report beside the coder; collecting them into one Reports
 * screen would separate each report from the thing it is about. What they
 * needed was to look like one family, not to live in one place.
 */
export function ReportButton({ label, icon, onClick, busy, disabled, title, error, tone = 'primary' }: {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  busy?: boolean
  disabled?: boolean
  title?: string
  error?: string | null
  /** 'primary' for the report itself, 'secondary' for a companion export. */
  tone?: 'primary' | 'secondary'
}) {
  const off = !!disabled || !!busy
  const primary = tone === 'primary'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'flex-end' }}>
      <button
        onClick={onClick}
        disabled={off}
        title={title}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
          padding: '8px 15px', borderRadius: 9, fontSize: 12, fontWeight: 700,
          cursor: off ? 'not-allowed' : 'pointer',
          border: primary ? 'none' : '1px solid #e5e7eb',
          background: off
            ? '#e5e7eb'
            : primary ? 'linear-gradient(135deg, #7c3aed, #4f46e5)' : '#fff',
          color: off ? '#9ca3af' : primary ? '#fff' : '#374151',
          opacity: busy ? 0.85 : 1,
        }}>
        {busy ? <Loader size={13} /> : icon}
        {/* One word for the wait, everywhere. Three tabs said three things. */}
        {busy ? 'Preparing…' : label}
      </button>
      {error && (
        <div style={{ fontSize: 11, color: '#b91c1c', fontWeight: 600, maxWidth: 280, textAlign: 'right' }}>
          {error}
        </div>
      )}
    </div>
  )
}
