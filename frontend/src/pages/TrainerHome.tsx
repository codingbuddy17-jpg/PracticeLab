import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { FileText, BookOpen, GraduationCap, ChevronRight, ClipboardList, ClipboardCheck, AlertTriangle, Database } from 'lucide-react'
import { codeSetStatus } from '../api/codesApi'
import { getPLAnalyticsOverview, getChartStats, getAssessmentStats, getAssessmentOverview, listAuditBatches, listAuditKeySets, getAuditOverview } from '../api'

export function TrainerHome() {
  const [plStats, setPlStats] = useState<any>(null)
  const [chartStats, setChartStats] = useState<any>(null)
  const [assessmentStats, setAssessmentStats] = useState<{ totalActive: number; totalSpecialties: number } | null>(null)
  const [auditStats, setAuditStats] = useState<{ batches: number; open: number; scored: number; curated: number; accuracy: number | null; charts: number } | null>(null)
  const [assessOverview, setAssessOverview] = useState<any>(null)
  // Reference data freshness. Shown to TRAINERS only: they are the ones who
  // can act on it, and it is not something a coder or auditor mid-session
  // should be given to wonder about.
  const [codeSets, setCodeSets] = useState<any>(null)

  function load() {
    // scope=all. The default is batch work only, so this page reported three
    // batches while ten existed — seven direct assignments excluded with
    // nothing saying so. A landing page has no filters, so it must not
    // silently inherit one.
    getPLAnalyticsOverview({}, 'all').then(setPlStats).catch(() => {})
    getChartStats().then(setChartStats).catch(() => {})
    codeSetStatus().then(setCodeSets).catch(() => {})
    getAssessmentOverview().then(setAssessOverview).catch(() => {})
    // Auditor tiles fail quietly — a trainer home page must render even if one
    // module's stats endpoint is unavailable.
    Promise.all([listAuditBatches(), listAuditKeySets(), getAuditOverview()])
      .then(([b, k, o]) => {
        const batches = b.batches || []
        setAuditStats({
          batches: batches.length,
          open: batches.filter((x: Record<string, unknown>) => x.status === 'Open').length,
          scored: batches.reduce((n: number, x: Record<string, unknown>) => n + Number(x.scored || 0), 0),
          curated: new Set((k.sets || []).map((x: Record<string, unknown>) => x.chart_id)).size,
          accuracy: o?.audit_accuracy ?? null,
          charts: o?.charts ?? 0,
        })
      }).catch(() => {})
    getAssessmentStats()
      .then(rows => {
        const totalActive = rows.reduce((s, r) => s + r.active, 0)
        const totalSpecialties = rows.filter(r => r.active > 0).length
        setAssessmentStats({ totalActive, totalSpecialties })
      })
      .catch(() => {})
  }

  useEffect(() => {
    load()
    // These figures change while you are inside a module, and this page is
    // what you come back to. Refetching when the tab regains focus is the
    // cheapest way to be current at the only moment it matters — polling would
    // fire all day for a page nobody is looking at.
    const onFocus = () => { if (document.visibilityState === 'visible') load() }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
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

        {/* Reference code sets.
            The application cannot refresh these itself — they are loaded by a
            script somebody runs — so the failure is silence: nothing breaks
            when the data is a year old, and a trainer would go on seeing last
            year's descriptions with nothing ever saying so. This is the thing
            that says so. It is deliberately quiet when all is well. */}
        {codeSets?.needs_attention && (
          <div style={styles.codeSetBanner}>
            <AlertTriangle size={16} color="#b45309" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1 }}>
              <div style={styles.codeSetTitle}>
                {codeSets.any ? 'Code sets need refreshing' : 'CMS code sets have not been loaded'}
              </div>
              <div style={styles.codeSetBody}>
                {codeSets.any
                  ? 'Code descriptions, code completion and answer-key checks are running on older data.'
                  : 'Code descriptions, code completion and answer-key code checks are unavailable until these are loaded. Nothing else is affected.'}
                {' '}Ask whoever maintains the application to run the code-set ingest
                (documented in the migration runbook, section 8).
              </div>
              <div style={styles.codeSetRows}>
                {(codeSets.loaded || []).filter((r: any) => !r.current).map((r: any) => (
                  <div key={r.code_system} style={styles.codeSetRow}>
                    <span style={styles.codeSetDot} /> {r.note}
                  </div>
                ))}
                {(codeSets.missing || []).map((r: any) => (
                  <div key={r.code_system} style={styles.codeSetRow}>
                    <span style={styles.codeSetDot} /> {r.label} — never loaded
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {codeSets?.any && !codeSets.needs_attention && (
          <div style={styles.codeSetOk}>
            <Database size={13} color="#6b7280" />
            CMS code sets current ({codeSets.expected_edition}) ·{' '}
            {(codeSets.loaded || []).reduce((n: number, r: any) => n + (r.row_count || 0), 0).toLocaleString()} codes
          </div>
        )}

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
            {/* Matches the two other wide chips: a figure on the left, a bar
                on the right. The specialty NAMES lived here as a run-on list —
                accurate, unreadable at a glance, and out of step with every
                other tile on the page. Key coverage is the figure worth the
                space: charts without a key are inventory that looks like
                capacity until someone tries to build a batch from it. */}
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={styles.bentoPassRateNum}>{chartStats?.total_specialties ?? '—'}</div>
                <div style={styles.bentoStatLabel}>Specialties Covered</div>
                <div style={styles.bentoStatSub}>
                  {chartStats ? `${chartStats.charts_with_keys} of ${chartStats.total_charts} charts keyed` : '—'}
                </div>
              </div>
              {chartStats?.total_charts > 0 && (
                <div style={{ ...styles.bentoBarWrap, background: '#e0e7ff' }}>
                  <div style={{
                    ...styles.bentoBar, background: '#4f46e5',
                    width: `${Math.round(chartStats.charts_with_keys / chartStats.total_charts * 100)}%`,
                  }} />
                </div>
              )}
            </div>
          </Link>
        </div>

        {/* ── Practice Modules divider ─────────────────────────────────── */}
        <div style={styles.plDivider}>
          <span style={styles.plDividerLine} />
          <span style={styles.plDividerLabel}>Practice Modules</span>
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
            <div style={styles.bentoStatLabel}>Batches & Assignments</div>
            <div style={styles.bentoStatSub}>
              {plStats ? `${plStats.open_batches} open · ${plStats.complete_batches} closed` : '—'}
            </div>
          </Link>

          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(253,248,255,0.6)' }}>
            <div style={styles.bentoStatNum}>{plStats?.total_graded ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Charts Graded</div>
            <div style={styles.bentoStatSub}>batches and direct assignments</div>
          </Link>

          <Link to="/trainer/practicelab" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate }}>
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={styles.bentoPassRateNum}>
                  {plStats ? `${plStats.overall_pass_rate}%` : '—'}
                </div>
                <div style={styles.bentoStatLabel}>Chart Pass Rate</div>
              </div>
              {plStats && (
                <div style={styles.bentoBarWrap}>
                  <div style={{ ...styles.bentoBar, width: `${plStats.overall_pass_rate}%` }} />
                </div>
              )}
            </div>
          </Link>
        </div>

        {/* Auditor bento — its own full-width area below Coder, so it keeps all
            three stat cells. Rose/violet marks it apart from PracticeLab's teal;
            amber and red are avoided because they mean "needs attention"
            everywhere else in this app. */}
        <div style={{ ...styles.bentoGrid, marginTop: 10 }}>
          <Link to="/trainer/auditor" style={{ ...styles.bentoCell, ...styles.bentoCellMain, background: 'linear-gradient(145deg, #be185d 0%, #9333ea 100%)' }}>
            <div style={styles.bentoTag}>Chart Audit Engine</div>
            <div style={styles.bentoTitle}>
              <ClipboardCheck size={20} style={{ flexShrink: 0 }} />
              PracticeLab — Auditor
            </div>
            <div style={styles.bentoSubtitle}>
              Introduce errors · Allocate · Score findings · Detection patterns
            </div>
            <div style={styles.bentoCta}>
              Open <ChevronRight size={14} strokeWidth={2.5} />
            </div>
          </Link>

          <Link to="/trainer/auditor/batches" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(253,242,248,0.6)' }}>
            <div style={styles.bentoStatNum}>{auditStats?.batches ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Audit Batches</div>
            <div style={styles.bentoStatSub}>
              {auditStats ? `${auditStats.open} open · ${auditStats.scored} chart(s) scored` : '—'}
            </div>
          </Link>

          <Link to="/trainer/auditor/keys" style={{ ...styles.bentoCell, ...styles.bentoCellStat, background: 'rgba(250,245,255,0.6)' }}>
            <div style={styles.bentoStatNum}>{auditStats?.curated ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Curated Charts</div>
            <div style={styles.bentoStatSub}>charts with errors you authored</div>
          </Link>

          {/* Spans columns 2-3 on the second row, like the wide chip in every
              other bento. Using bentoCellStat here left the row ragged. */}
          <Link to="/trainer/auditor/analytics" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate, background: 'rgba(253,242,248,0.45)' }}>
            <div style={styles.bentoPassRateRow}>
              <div>
                <div style={{ ...styles.bentoPassRateNum, color: '#be185d' }}>
                  {auditStats?.accuracy != null ? `${auditStats.accuracy}%` : '—'}
                </div>
                <div style={styles.bentoStatLabel}>Audit Accuracy</div>
                <div style={styles.bentoStatSub}>
                  {auditStats?.charts ? `${auditStats.charts} chart(s) scored` : 'nothing scored yet'}
                </div>
              </div>
              {auditStats?.accuracy != null && (
                <div style={{ ...styles.bentoBarWrap, background: '#fce7f3' }}>
                  <div style={{ ...styles.bentoBar, background: '#be185d', width: `${auditStats.accuracy}%` }} />
                </div>
              )}
            </div>
          </Link>
        </div>

        {/* ── Assessment Modules divider ───────────────────────────────── */}
        <div style={styles.plDivider}>
          <span style={styles.plDividerLine} />
          <span style={styles.plDividerLabel}>Assessment Modules</span>
          <span style={styles.plDividerLine} />
        </div>

        {/* Assessment Management bento */}
        <div style={styles.bentoGrid}>
          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellMain, background: 'linear-gradient(145deg, #7c3aed 0%, #4f46e5 100%)' }}>
            <div style={styles.bentoTag}>MCQ Assessment Engine</div>
            <div style={styles.bentoTitle}>
              <ClipboardList size={20} style={{ flexShrink: 0 }} />
              Assessments
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
            <div style={styles.bentoStatNum}>{assessmentStats?.totalSpecialties ?? '—'}</div>
            <div style={styles.bentoStatLabel}>Specialties</div>
            <div style={styles.bentoStatSub}>with active questions</div>
          </Link>

          {/* Was a static "Generate" tile — a button dressed as a statistic,
              in the one slot on the row that could carry an outcome. */}
          <Link to="/trainer/assessment" style={{ ...styles.bentoCell, ...styles.bentoCellPassRate, background: 'rgba(245,243,255,0.45)' }}>
            <div style={{ ...styles.bentoPassRateRow }}>
              <div>
                <div style={{ ...styles.bentoPassRateNum, color: '#7c3aed' }}>
                  {assessOverview ? `${assessOverview.overall_pass_rate}%` : '—'}
                </div>
                <div style={styles.bentoStatLabel}>Clearance Rate</div>
                <div style={styles.bentoStatSub}>
                  {assessOverview
                    ? `${assessOverview.total_submitted} of ${assessOverview.total_sessions} sessions submitted`
                    : '—'}
                </div>
              </div>
              {assessOverview && (
                <div style={styles.bentoBarWrap}>
                  <div style={{ ...styles.bentoBar, width: `${assessOverview.overall_pass_rate}%`, background: '#7c3aed' }} />
                </div>
              )}
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
  codeSetBanner: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    background: 'rgba(255,251,235,0.9)', border: '1px solid #fcd34d',
    borderRadius: 10, padding: '12px 14px', marginBottom: 18,
  },
  codeSetTitle: { fontSize: 13, fontWeight: 700, color: '#92400e', marginBottom: 3 },
  codeSetBody: { fontSize: 12, color: '#78350f', lineHeight: 1.6 },
  codeSetRows: { display: 'flex', flexDirection: 'column' as const, gap: 2, marginTop: 6 },
  codeSetRow: { fontSize: 11, color: '#92400e', display: 'flex', alignItems: 'center', gap: 6 },
  codeSetDot: {
    width: 4, height: 4, borderRadius: 99, background: '#d97706',
    display: 'inline-block', flexShrink: 0,
  },
  // When everything is current this is a footnote, not an announcement.
  codeSetOk: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    fontSize: 11, color: '#6b7280', marginBottom: 16,
  },
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
