import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { FileText, BookOpen, GraduationCap, ChevronRight, ClipboardList } from 'lucide-react'
import { getPLAnalyticsOverview, getChartStats, getAssessmentStats } from '../api'

export function TrainerHome() {
  const [plStats, setPlStats] = useState<{ total_batches: number; complete_batches: number; total_graded: number; overall_pass_rate: number } | null>(null)
  const [chartStats, setChartStats] = useState<{ total_charts: number; open_feedback: number; total_specialties: number } | null>(null)
  const [assessmentStats, setAssessmentStats] = useState<{ totalActive: number } | null>(null)

  useEffect(() => {
    getPLAnalyticsOverview().then(setPlStats).catch(() => {})
    getChartStats().then(setChartStats).catch(() => {})
    getAssessmentStats()
      .then(rows => {
        const totalActive = rows.reduce((s, r) => s + r.active, 0)
        setAssessmentStats({ totalActive })
      })
      .catch(() => {})
  }, [])

  return (
    <div style={styles.container}>
      {/* Decorative blobs */}
      <div style={styles.blob1} />
      <div style={styles.blob2} />
      <div style={styles.blob3} />

      <div style={styles.topBar}>
        <div style={styles.logo}>
          <BookOpen size={22} color="#4f46e5" />
          <span style={styles.logoText}>PracticeLab</span>
        </div>
        <span style={styles.portalBadge}>Trainer Portal</span>
      </div>

      <div style={styles.content}>
        <div style={styles.welcomeText}>What would you like to do?</div>

        {/* ── Chart Management divider ────────────────────────────────── */}
        <div style={styles.plDivider}>
          <span style={styles.plDividerLine} />
          <span style={styles.plDividerLabel}>Chart Management</span>
          <span style={styles.plDividerLine} />
        </div>

        {/* Chart Management bento */}
        <div style={styles.bentoGrid}>
          <Link to="/trainer/chart-management" style={{ ...styles.bentoCell, ...styles.bentoCellMain, background: 'linear-gradient(145deg, #4f46e5 0%, #0891b2 100%)' }}>
            <div style={styles.bentoTag}>Chart Library Engine</div>
            <div style={styles.bentoTitle}>
              <FileText size={20} style={{ flexShrink: 0 }} />
              Chart Management
            </div>
            <div style={styles.bentoSubtitle}>
              Upload · Manage · Answer Keys · Reports · Analytics · Feedback
            </div>
            <div style={styles.bentoCta}>
              Open <ChevronRight size={14} strokeWidth={2.5} />
            </div>
          </Link>

          <Link to="/trainer/chart-management" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(238,242,255,0.6)' }}>
            <div style={styles.bentoStatNum}>{chartStats?.total_charts ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Active Charts</div>
            <div style={styles.bentoStatSub}>in the library</div>
          </Link>

          <Link to="/trainer/feedback" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: chartStats && chartStats.open_feedback > 0 ? 'rgba(254,226,226,0.5)' : 'rgba(240,253,244,0.5)' }}>
            <div style={{ ...styles.bentoStatNum, color: chartStats && chartStats.open_feedback > 0 ? '#dc2626' : '#15803d' }}>{chartStats?.open_feedback ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Open Feedback</div>
            <div style={styles.bentoStatSub}>{chartStats?.open_feedback ? 'needs review' : 'all clear'}</div>
          </Link>

          <Link to="/trainer/chart-management" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate, background: 'rgba(238,242,255,0.45)' }}>
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={styles.bentoPassRateNum}>{chartStats?.total_specialties ?? '—'}</div>
                <div style={styles.bentoStatLabel}>Specialties Covered</div>
              </div>
              <div style={{ fontSize: 12, color: '#4f46e5', fontWeight: 600 }}>
                ICD-10 · Surgery · ED · IP-DRG · more
              </div>
            </div>
          </Link>
        </div>

        {/* ── Assessment Modules divider ───────────────────────────────── */}
        <div style={styles.plDivider}>
          <span style={styles.plDividerLine} />
          <span style={styles.plDividerLabel}>Assessment Modules</span>
          <span style={styles.plDividerLine} />
        </div>

        {/* PracticeLab bento */}
        <div style={styles.bentoGrid}>
          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellMain, background: 'linear-gradient(145deg, #0d9488 0%, #0891b2 100%)' }}>
            <div style={styles.bentoTag}>Chart Coding Engine</div>
            <div style={styles.bentoTitle}>
              <GraduationCap size={20} style={{ flexShrink: 0 }} />
              PracticeLab
            </div>
            <div style={styles.bentoSubtitle}>
              Create batches · Auto-grade · DRG review · Reports
            </div>
            <div style={styles.bentoCta}>
              Open <ChevronRight size={14} strokeWidth={2.5} />
            </div>
          </Link>

          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(238,242,255,0.6)' }}>
            <div style={styles.bentoStatNum}>{plStats?.total_batches ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Total Batches</div>
            <div style={styles.bentoStatSub}>{plStats?.complete_batches ?? '—'} complete</div>
          </Link>

          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(253,248,255,0.6)' }}>
            <div style={styles.bentoStatNum}>{plStats?.total_graded ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Submissions Graded</div>
            <div style={styles.bentoStatSub}>across all batches</div>
          </Link>

          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate }}>
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={styles.bentoPassRateNum}>
                  {plStats ? `${plStats.overall_pass_rate}%` : '—'}
                </div>
                <div style={styles.bentoStatLabel}>Overall Pass Rate</div>
              </div>
              {plStats && (
                <div style={styles.bentoBarWrap}>
                  <div style={{ ...styles.bentoBar, width: `${plStats.overall_pass_rate}%` }} />
                </div>
              )}
            </div>
          </Link>
        </div>

        {/* Assessment Management bento */}
        <div style={{ ...styles.bentoGrid, marginTop: 10 }}>
          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellMain, background: 'linear-gradient(145deg, #7c3aed 0%, #4f46e5 100%)' }}>
            <div style={styles.bentoTag}>MCQ Assessment Engine</div>
            <div style={styles.bentoTitle}>
              <ClipboardList size={20} style={{ flexShrink: 0 }} />
              Assessment Management
            </div>
            <div style={styles.bentoSubtitle}>
              Question Banks · Generate · Export
            </div>
            <div style={styles.bentoCta}>
              Open <ChevronRight size={14} strokeWidth={2.5} />
            </div>
          </Link>

          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(245,243,255,0.6)' }}>
            <div style={{ ...styles.bentoStatNum, color: '#7c3aed' }}>{assessmentStats?.totalActive ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Active Questions</div>
            <div style={styles.bentoStatSub}>across all specialties</div>
          </Link>

          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(238,242,255,0.6)' }}>
            <div style={styles.bentoStatNum}>10</div>
            <div style={styles.bentoStatLabel}>Specialties</div>
            <div style={styles.bentoStatSub}>ICD-10 · Surgery · ED · more</div>
          </Link>

          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate, background: 'rgba(245,243,255,0.45)' }}>
            <div style={{ ...styles.bentoPassRateRow }}>
              <div>
                <div style={{ ...styles.bentoPassRateNum, color: '#7c3aed' }}>Generate</div>
                <div style={styles.bentoStatLabel}>Per-student shuffled MCQ tests</div>
              </div>
              <div style={{ fontSize: 12, color: '#7c3aed', fontWeight: 600 }}>
                PDF Export · Answer Keys
              </div>
            </div>
          </Link>
        </div>

      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: 'linear-gradient(135deg, #dbeafe 0%, #ede9fe 40%, #d1fae5 100%)', fontFamily: 'system-ui, sans-serif', position: 'relative', overflow: 'hidden' },
  blob1: { position: 'absolute', top: -80, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, #818cf8 0%, #6366f1 60%, transparent 100%)', opacity: 0.25, filter: 'blur(60px)', pointerEvents: 'none' },
  blob2: { position: 'absolute', top: 160, right: -60, width: 300, height: 300, borderRadius: '50%', background: 'radial-gradient(circle, #34d399 0%, #059669 60%, transparent 100%)', opacity: 0.2, filter: 'blur(60px)', pointerEvents: 'none' },
  blob3: { position: 'absolute', bottom: 40, left: '38%', width: 280, height: 280, borderRadius: '50%', background: 'radial-gradient(circle, #f472b6 0%, #a855f7 60%, transparent 100%)', opacity: 0.18, filter: 'blur(60px)', pointerEvents: 'none' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 28px', background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.5)', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoText: { fontWeight: 800, fontSize: 18, color: '#111', letterSpacing: -0.5 },
  portalBadge: { fontSize: 12, fontWeight: 700, background: '#ede9fe', color: '#4f46e5', padding: '4px 12px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  content: { maxWidth: 860, margin: '0 auto', padding: '40px 24px' },
  welcomeText: { fontSize: 22, fontWeight: 800, color: '#111', marginBottom: 24, letterSpacing: -0.5 },


  // Divider
  plDivider: { display: 'flex', alignItems: 'center', gap: 12, margin: '28px 0 20px' },
  plDividerLine: { flex: 1, height: 1, background: '#e5e7eb' },
  plDividerLabel: { fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 1, whiteSpace: 'nowrap' as const },

  // Bento grid
  bentoGrid: {
    display: 'grid',
    gridTemplateColumns: '1.6fr 1fr 1fr',
    gridTemplateRows: 'auto auto',
    gap: 10,
  },
  bentoCell: {
    borderRadius: 16, border: '1px solid rgba(255,255,255,0.65)',
    textDecoration: 'none', color: 'inherit',
    padding: '22px 24px', display: 'flex', flexDirection: 'column',
    gap: 8, cursor: 'pointer',
    transition: 'border-color 0.15s, box-shadow 0.2s',
    boxShadow: '0 8px 32px rgba(99,102,241,0.1), 0 1px 0 rgba(255,255,255,0.8) inset',
    backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
  },
  bentoCellMain: {
    gridRow: '1 / 3',
    justifyContent: 'space-between',
    minHeight: 180,
    border: 'none',
  },
  bentoTag: {
    fontSize: 10, fontWeight: 700, letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
    color: 'rgba(255,255,255,0.55)', alignSelf: 'flex-start',
  },
  bentoTitle: {
    display: 'flex', alignItems: 'center', gap: 10,
    fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.5,
  },
  bentoSubtitle: { fontSize: 12, color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 },
  bentoCta: {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', marginTop: 4,
    fontSize: 12, fontWeight: 700, color: '#fff',
    background: 'rgba(255,255,255,0.18)', padding: '7px 14px',
    borderRadius: 8, border: '1px solid rgba(255,255,255,0.25)',
  },
  bentoCellStat: {
    display: 'flex', flexDirection: 'column', gap: 4,
    padding: '20px 22px',
  },
  bentoStatNum: { fontSize: 32, fontWeight: 800, color: '#111', letterSpacing: -1.5, lineHeight: 1 },
  bentoStatLabel: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  bentoStatSub: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
  bentoCellPassRate: {
    gridColumn: '2 / 4',
    background: 'rgba(240,253,244,0.45)',
    border: '1px solid rgba(255,255,255,0.65)',
    padding: '18px 22px',
  },
  bentoPassRateRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20 },
  bentoPassRateNum: { fontSize: 32, fontWeight: 800, color: '#15803d', letterSpacing: -1.5, lineHeight: 1 },
  bentoBarWrap: { flex: 1, height: 8, background: '#dcfce7', borderRadius: 99, overflow: 'hidden' },
  bentoBar: { height: '100%', background: '#16a34a', borderRadius: 99, transition: 'width 0.6s ease' },
}
