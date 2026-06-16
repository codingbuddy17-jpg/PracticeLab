import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Cell, PieChart, Pie,
} from 'recharts'
import { ISSUE_COLORS } from './shared'
import styles from './styles'

export function InsightsPanel({ insights, onClose }: { insights: any; onClose: () => void }) {
  const { batch_summary: bs, team_errors: te, category_performance: cp, chart_signals: cs, coder_insights: ci, is_ip,
    top_categories: topCats, bottom_categories: bottomCats, top_performers: topPerf, bottom_performers: bottomPerf,
    score_distribution: scoreDist } = insights
  const [expandedCoder, setExpandedCoder] = useState<string | null>(null)
  const [selectedBucket, setSelectedBucket] = useState<string | null>(null)

  function buildCopyText() {
    const lines: string[] = [
      `BATCH INSIGHTS — ${insights.batch_name}`,
      `Specialty: ${insights.specialty}`,
      '',
      'SUMMARY',
      `Coders: ${bs.n_coders}  |  Charts Coded: ${bs.n_distinct_charts}  |  Total Graded: ${bs.total_graded}`,
      `Pass Rate: ${bs.pass_rate}% (${bs.passed}/${bs.total_graded} passed)${bs.pass_rate_delta != null ? `  vs prior batch: ${bs.pass_rate_delta > 0 ? '+' : ''}${bs.pass_rate_delta}%` : ''}`,
      `Avg Score: ${bs.avg_score}%`,
      '',
    ]
    if (scoreDist?.length) {
      lines.push('SCORE DISTRIBUTION (cumulative chart-weighted score)')
      scoreDist.forEach((b: any) => lines.push(`  ${b.label}: ${b.count} coder${b.count !== 1 ? 's' : ''} (${b.coders.join(', ')})`))
      lines.push('')
    }
    if (topPerf?.length) {
      lines.push('TOP PERFORMERS')
      topPerf.forEach((c: any) => lines.push(`  ${c.coder_name}: ${c.avg_score}%`))
      lines.push('')
    }
    if (bottomPerf?.length) {
      lines.push('NEEDS ATTENTION (LOWEST SCORES)')
      bottomPerf.forEach((c: any) => lines.push(`  ${c.coder_name}: ${c.avg_score}%`))
      lines.push('')
    }
    if (topCats?.length) {
      lines.push('TOP CATEGORIES (BEST CODED)')
      topCats.forEach((c: any) => lines.push(`  ${c.category}: ${c.avg_score}% avg, ${c.pass_rate}% pass rate`))
      lines.push('')
    }
    if (bottomCats?.length) {
      lines.push('BOTTOM CATEGORIES (NEEDS WORK)')
      bottomCats.forEach((c: any) => lines.push(`  ${c.category}: ${c.avg_score}% avg, ${c.pass_rate}% pass rate`))
      lines.push('')
    }
    if (te.by_issue_type.length) {
      lines.push('TOP ERROR TYPES (team-wide)')
      te.by_issue_type.slice(0, 4).forEach((e: any) => lines.push(`  ${e.type}: ${e.count} occurrences (${e.pct}%)`))
      lines.push('')
    }
    if (te.top_missed_codes.length) {
      lines.push('TOP MISSED CODES')
      te.top_missed_codes.slice(0, 5).forEach((m: any) => lines.push(`  ${m.code} — missed ${m.count}×`))
      lines.push('')
    }
    if (cp.length) {
      lines.push('LOWEST PERFORMING CATEGORIES')
      cp.slice(0, 3).forEach((c: any) => lines.push(`  ${c.category}: ${c.avg_score}% avg, ${c.pass_rate}% pass rate`))
      lines.push('')
    }
    lines.push('PER-CODER SUMMARY')
    ci.forEach((c: any) => {
      lines.push(`  ${c.coder_name}: ${c.avg_score}% avg${c.score_delta != null ? ` (${c.score_delta > 0 ? '+' : ''}${c.score_delta} vs prior)` : ''} — ${c.dominant_weakness ? `weakness: ${c.dominant_weakness}` : 'no dominant weakness'}`)
      if (c.top_missed_codes.length) lines.push(`    Top missed: ${c.top_missed_codes.join(', ')}`)
    })
    return lines.join('\n')
  }

  const deltaColor = (d: number | null) => d == null ? '#6b7280' : d > 0 ? '#16a34a' : d < 0 ? '#dc2626' : '#6b7280'
  const deltaLabel = (d: number | null) => d == null ? '' : `${d > 0 ? '+' : ''}${d}%`

  const recommendations = (() => {
    const recs: { icon: string; text: string; type: 'warn' | 'info' | 'ok' }[] = []
    if (bs.pass_rate < 70)
      recs.push({ icon: '⚠', type: 'warn', text: `Pass rate is ${bs.pass_rate}% — below 70% threshold. Schedule a retraining session before the next batch.` })
    if (bs.pass_rate >= 85 && bs.pass_rate_delta != null && bs.pass_rate_delta > 0)
      recs.push({ icon: '✓', type: 'ok', text: `Pass rate improved by ${bs.pass_rate_delta}% vs the prior batch — team is trending in the right direction.` })
    const topError = te.by_issue_type[0]
    if (topError && topError.pct >= 40)
      recs.push({ icon: '↗', type: 'info', text: `"${topError.type.replace(/_/g, ' ')}" accounts for ${topError.pct}% of all errors. Focus next feedback session on this pattern.` })
    const topMissed = te.top_missed_codes[0]
    if (topMissed && topMissed.count >= 3)
      recs.push({ icon: '↗', type: 'info', text: `Code ${topMissed.code} was missed ${topMissed.count} times across the team. Verify the answer key and add to training materials.` })
    const worstCat = cp[0]
    if (worstCat && worstCat.pass_rate < 60)
      recs.push({ icon: '⚠', type: 'warn', text: `${worstCat.category} has a ${worstCat.pass_rate}% pass rate — lowest of all categories. Consider a focused drill pack.` })
    const sortedCoders = [...ci].sort((a: any, b: any) => a.avg_score - b.avg_score)
    const worstCoder = sortedCoders[0]
    if (worstCoder && worstCoder.avg_score < 65 && ci.length > 1)
      recs.push({ icon: '⚠', type: 'warn', text: `${worstCoder.coder_name} scored ${worstCoder.avg_score}% — significantly below team average. Recommend a targeted 1:1 feedback session.` })
    return recs
  })()

  return (
    <div style={{ background: '#f8faff', border: '1.5px solid #a5b4fc', borderRadius: 12, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 800, color: '#312e81' }}>✦ Batch Insights</span>
          <span style={{ fontSize: 12, color: '#6b7280' }}>{insights.batch_name}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...styles.outlineBtn, fontSize: 12, color: '#4f46e5', borderColor: '#a5b4fc', padding: '5px 12px' }}
            onClick={() => { navigator.clipboard.writeText(buildCopyText()); toast.success('Copied to clipboard') }}>
            Copy Summary
          </button>
          <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '5px 12px' }} onClick={onClose}>✕ Close</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
        {[
          { label: 'Coders', value: bs.n_coders, color: '#111' },
          { label: 'Distinct Charts', value: bs.n_distinct_charts, color: '#111' },
          { label: 'Total Attempts', value: bs.total_graded, color: '#111' },
          { label: 'Chart Pass Rate', value: `${bs.pass_rate}%`, color: bs.pass_rate >= 80 ? '#16a34a' : bs.pass_rate >= 60 ? '#d97706' : '#dc2626' },
          { label: 'Avg Score', value: `${bs.avg_score}%`, color: '#111' },
          { label: 'Passed', value: bs.passed, color: '#16a34a' },
          { label: 'Failed', value: bs.failed, color: '#dc2626' },
        ].map(s => (
          <div key={s.label} style={{ background: '#fff', border: '1px solid #e0e7ff', borderRadius: 8, padding: '12px 14px', textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
        {bs.pass_rate_delta != null && (
          <div style={{ background: '#fff', border: '1px solid #e0e7ff', borderRadius: 8, padding: '12px 14px', textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: deltaColor(bs.pass_rate_delta) }}>{deltaLabel(bs.pass_rate_delta)}</div>
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>vs Prior Batch</div>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>{bs.prior_batch_name}</div>
          </div>
        )}
      </div>
      {bs.total_graded > bs.n_distinct_charts && (
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: -8 }}>
          {bs.n_distinct_charts} distinct chart{bs.n_distinct_charts !== 1 ? 's' : ''} were coded by {bs.n_coders} coder{bs.n_coders !== 1 ? 's' : ''}, producing {bs.total_graded} graded attempts ({bs.passed} passed, {bs.failed} failed).
        </div>
      )}

      {scoreDist?.length > 0 && (() => {
        const active = scoreDist.find((b: any) => b.label === selectedBucket)
        return (
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' as const }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 4 }}>Score Distribution</div>
                <div style={{ fontSize: 11, color: '#9ca3af' }}>Cumulative chart-weighted score per coder</div>
                <div style={{ fontSize: 11, color: '#a5b4fc', marginTop: 4, fontStyle: 'italic' as const }}>Click a segment or row to see coder names</div>
              </div>
              <PieChart width={160} height={160}>
                <Pie data={scoreDist} dataKey="count" nameKey="label" cx={80} cy={80} innerRadius={40} outerRadius={70} paddingAngle={3}
                  onClick={(d: any) => setSelectedBucket(prev => prev === d.label ? null : d.label)}
                  style={{ cursor: 'pointer' }}>
                  {scoreDist.map((b: any) => (
                    <Cell key={b.label} fill={b.color} stroke={selectedBucket === b.label ? '#111' : undefined} strokeWidth={selectedBucket === b.label ? 2 : 0} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: any, _n: any, p: any) => [`${v} coder${v !== 1 ? 's' : ''} — click for names`, p.payload.label]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              </PieChart>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {scoreDist.map((b: any) => (
                  <div key={b.label} onClick={() => setSelectedBucket(prev => prev === b.label ? null : b.label)}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, cursor: 'pointer', padding: '2px 6px', borderRadius: 6, background: selectedBucket === b.label ? '#f5f3ff' : 'transparent' }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: b.color, flexShrink: 0 }} />
                    <span style={{ fontWeight: 700, color: '#111' }}>{b.count}</span>
                    <span style={{ color: '#6b7280' }}>coder{b.count !== 1 ? 's' : ''} scored <b style={{ color: b.color }}>{b.label}</b></span>
                  </div>
                ))}
              </div>
            </div>
            {active && (
              <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 10, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: active.color, textTransform: 'uppercase' as const, letterSpacing: 0.4 }}>{active.label}:</span>
                {active.coders.map((name: string) => (
                  <span key={name} style={{ fontSize: 12, fontWeight: 600, background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 12, padding: '3px 10px' }}>{name}</span>
                ))}
              </div>
            )}
          </div>
        )
      })()}

      {recommendations.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', textTransform: 'uppercase' as const, letterSpacing: 0.5 }}>Recommendations</div>
          {recommendations.map((r, i) => (
            <div key={i} style={{
              display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 14px', borderRadius: 8, fontSize: 13,
              background: r.type === 'warn' ? '#fff7ed' : r.type === 'ok' ? '#f0fdf4' : '#eff6ff',
              border: `1px solid ${r.type === 'warn' ? '#fed7aa' : r.type === 'ok' ? '#bbf7d0' : '#bfdbfe'}`,
            }}>
              <span style={{ fontSize: 15, flexShrink: 0, marginTop: 1 }}>{r.icon}</span>
              <span style={{ color: r.type === 'warn' ? '#92400e' : r.type === 'ok' ? '#166534' : '#1e40af', lineHeight: 1.5 }}>{r.text}</span>
            </div>
          ))}
        </div>
      )}

      {(topPerf?.length > 0 || bottomPerf?.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {topPerf?.length > 0 && (
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#166534', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 10 }}>Top Performers</div>
              {topPerf.map((c: any, i: number) => (
                <div key={c.coder_name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: i < topPerf.length - 1 ? '1px solid #dcfce7' : 'none' }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: '#16a34a', width: 18 }}>#{i + 1}</span>
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.coder_name}</span>
                  <span style={{ fontWeight: 800, fontSize: 14, color: '#16a34a' }}>{c.avg_score}%</span>
                </div>
              ))}
            </div>
          )}
          {bottomPerf?.length > 0 && (
            <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#92400e', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 10 }}>Needs Attention</div>
              {bottomPerf.map((c: any, i: number) => (
                <div key={c.coder_name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: i < bottomPerf.length - 1 ? '1px solid #fde68a' : 'none' }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: '#dc2626', width: 18 }}>#{i + 1}</span>
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.coder_name}</span>
                  <span style={{ fontWeight: 800, fontSize: 14, color: c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(topCats?.length > 0 || bottomCats?.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {topCats?.length > 0 && (
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#166534', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 10 }}>Top Categories — Best Coded</div>
              {topCats.map((c: any, i: number) => (
                <div key={c.category} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: i < topCats.length - 1 ? '1px solid #dcfce7' : 'none' }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: '#16a34a', width: 18 }}>#{i + 1}</span>
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.category}</span>
                  <span style={{ fontSize: 11, color: '#6b7280' }}>{c.attempt_count} attempts</span>
                  <span style={{ fontWeight: 800, fontSize: 14, color: '#16a34a' }}>{c.avg_score}%</span>
                </div>
              ))}
            </div>
          )}
          {bottomCats?.length > 0 && (
            <div style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#dc2626', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 10 }}>Bottom Categories — Needs Work</div>
              {bottomCats.map((c: any, i: number) => (
                <div key={c.category} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: i < bottomCats.length - 1 ? '1px solid #fee2e2' : 'none' }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: '#dc2626', width: 18 }}>#{i + 1}</span>
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.category}</span>
                  <span style={{ fontSize: 11, color: '#6b7280' }}>{c.attempt_count} attempts</span>
                  <span style={{ fontWeight: 800, fontSize: 14, color: c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 12 }}>Team Error Patterns</div>
          {te.total_feedback_items === 0 ? (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>No errors recorded</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={Math.max(120, te.by_issue_type.length * 38)}>
                <BarChart data={te.by_issue_type.map((e: any) => ({ ...e, label: e.type.replace(/_/g, ' ') }))}
                  layout="vertical" margin={{ left: 8, right: 40, top: 2, bottom: 2 }}>
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="label" width={96} tick={{ fontSize: 11, fontWeight: 600 }} />
                  <Tooltip formatter={(v: any, _: any, p: any) => [`${p.payload.count} errors (${v}%)`, 'Share']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Bar dataKey="pct" radius={[0, 6, 6, 0]}>
                    {te.by_issue_type.map((e: any) => <Cell key={e.type} fill={ISSUE_COLORS[e.type] || '#6b7280'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
                {te.by_section.map((s: any) => (
                  <span key={s.section} style={{ fontSize: 11, fontWeight: 700, background: '#dbeafe', color: '#1d4ed8', padding: '2px 10px', borderRadius: 10 }}>
                    {s.section} {s.count}×
                  </span>
                ))}
              </div>
              {te.top_missed_codes.length > 0 && (
                <>
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 10, marginBottom: 6 }}>Top missed codes</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {te.top_missed_codes.map((m: any) => (
                      <span key={m.code} style={{ fontSize: 11, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '2px 10px', borderRadius: 10 }}>
                        {m.code} {m.count}×
                      </span>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>

        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 12 }}>Category Performance</div>
          {cp.length === 0 ? (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>No data</div>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(140, cp.length * 40)}>
              <BarChart data={cp} layout="vertical" margin={{ left: 8, right: 40, top: 2, bottom: 2 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="category" width={100} tick={{ fontSize: 11, fontWeight: 600 }} />
                <Tooltip formatter={(v: any, _name: any, p: any) => [`${v}% avg · ${p.payload.pass_rate}% pass rate · ${p.payload.attempt_count} attempts`, 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="avg_score" radius={[0, 6, 6, 0]}>
                  {cp.map((c: any) => <Cell key={c.category} fill={c.avg_score < 60 ? '#dc2626' : c.avg_score < 80 ? '#d97706' : '#16a34a'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {(cs.high_fail.length > 0 || cs.all_pass.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {cs.high_fail.length > 0 && (
            <div style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#dc2626', marginBottom: 8 }}>High Failure Rate Charts</div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 8 }}>≥50% coders failed — review answer key or chart quality</div>
              {cs.high_fail.map((c: any) => (
                <div key={c.chart_number} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid #fee2e2', fontSize: 12 }}>
                  <span style={{ fontWeight: 700, color: '#111' }}>{c.chart_number}</span>
                  <span style={{ color: '#6b7280' }}>{c.category}</span>
                  <span style={{ fontWeight: 700, color: '#dc2626' }}>{c.fail_rate}% fail</span>
                </div>
              ))}
            </div>
          )}
          {cs.all_pass.length > 0 && (
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#16a34a', marginBottom: 8 }}>All Coders Passed</div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 8 }}>Good for beginner packs or baseline measurement</div>
              {cs.all_pass.map((c: any) => (
                <div key={c.chart_number} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid #d1fae5', fontSize: 12 }}>
                  <span style={{ fontWeight: 700, color: '#111' }}>{c.chart_number}</span>
                  <span style={{ color: '#6b7280' }}>{c.category}</span>
                  <span style={{ color: '#16a34a', fontWeight: 600 }}>{c.coder_count} coders</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 10 }}>Per-Coder Insights</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ci.map((c: any) => (
            <div key={c.coder_name} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', cursor: 'pointer' }}
                onClick={() => setExpandedCoder(expandedCoder === c.coder_name ? null : c.coder_name)}>
                <span style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>{c.coder_name}</span>
                <span style={{ fontSize: 18, fontWeight: 800, color: c.avg_score >= 80 ? '#16a34a' : '#dc2626' }}>{c.avg_score}%</span>
                {c.score_delta != null && <span style={{ fontSize: 12, fontWeight: 700, color: deltaColor(c.score_delta) }}>{deltaLabel(c.score_delta)}</span>}
                <span style={{ fontSize: 11, color: '#6b7280' }}>{c.vs_team_avg > 0 ? '+' : ''}{c.vs_team_avg}% vs team</span>
                {c.dominant_weakness && (
                  <span style={{ fontSize: 11, fontWeight: 700, background: '#fef3c7', color: '#92400e', padding: '2px 9px', borderRadius: 10 }}>{c.dominant_weakness} weakness</span>
                )}
                <span style={{ fontSize: 12, color: '#9ca3af' }}>{expandedCoder === c.coder_name ? '▲' : '▼'}</span>
              </div>
              {expandedCoder === c.coder_name && (
                <div style={{ borderTop: '1px solid #f3f4f6', padding: '12px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, background: '#fafafa' }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Error Profile</div>
                    {Object.keys(c.error_profile).length === 0 ? (
                      <div style={{ fontSize: 12, color: '#9ca3af' }}>No errors — clean coding</div>
                    ) : Object.entries(c.error_profile).map(([type, d]: any) => (
                      <div key={type} style={{ marginBottom: 7 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                          <span style={{ fontSize: 11, fontWeight: 600, color: ISSUE_COLORS[type] || '#374151' }}>{type.replace(/_/g, ' ')}</span>
                          <span style={{ fontSize: 11, color: '#6b7280' }}>{d.count} ({d.pct}%)</span>
                        </div>
                        <div style={{ height: 4, background: '#f3f4f6', borderRadius: 3 }}>
                          <div style={{ height: 4, width: `${d.pct}%`, background: ISSUE_COLORS[type] || '#374151', borderRadius: 3 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Section Error Profile</div>
                    {Object.keys(c.section_errors).length >= 2 ? (
                      <ResponsiveContainer width="100%" height={160}>
                        <RadarChart data={Object.entries(c.section_errors).map(([sec, cnt]) => ({ section: sec, errors: cnt }))}>
                          <PolarGrid />
                          <PolarAngleAxis dataKey="section" tick={{ fontSize: 11, fontWeight: 700 }} />
                          <PolarRadiusAxis tick={{ fontSize: 9 }} />
                          <Radar dataKey="errors" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.25} />
                          <Tooltip formatter={(v: any) => [v, 'Errors']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                        </RadarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                        {Object.entries(c.section_errors).map(([sec, cnt]: any) => (
                          <div key={sec} style={{ textAlign: 'center', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '6px 12px' }}>
                            <div style={{ fontSize: 16, fontWeight: 800, color: '#1d4ed8' }}>{cnt}</div>
                            <div style={{ fontSize: 10, color: '#6b7280' }}>{sec}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, marginTop: 4 }}>
                      {Object.entries(c.section_errors).map(([sec, cnt]: any) => (
                        <div key={sec} style={{ textAlign: 'center', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '4px 10px' }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: '#1d4ed8' }}>{cnt}</div>
                          <div style={{ fontSize: 10, color: '#6b7280' }}>{sec}</div>
                        </div>
                      ))}
                    </div>
                    {c.top_missed_codes.length > 0 && (
                      <>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Top Missed Codes</div>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {c.top_missed_codes.map((code: string) => (
                            <span key={code} style={{ fontSize: 11, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '2px 10px', borderRadius: 10 }}>{code}</span>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
