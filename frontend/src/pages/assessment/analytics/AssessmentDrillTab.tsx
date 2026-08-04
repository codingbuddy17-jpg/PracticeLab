import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { getAssessmentAnalyticsByAssessment, listAssessmentHistory } from '../../../api'
import { scoreColor, bandColor, fmt, fmtTime, KpiCard, Panel, DiffBadge, PassBadge, LoadingSpinner, EmptyState, rateColor } from './helpers'
import { usePagination } from '../../../components/Paginator'

export function AssessmentDrillTab() {
  const [assessments, setAssessments] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [listLoading, setListLoading] = useState(true)

  useEffect(() => {
    listAssessmentHistory()
      .then(setAssessments)
      .catch(() => toast.error('Failed to load assessments'))
      .finally(() => setListLoading(false))
  }, [])

  useEffect(() => {
    if (selectedId == null) return
    setLoading(true)
    setData(null)
    getAssessmentAnalyticsByAssessment(selectedId)
      .then(setData)
      .catch(() => toast.error('Failed to load assessment analytics'))
      .finally(() => setLoading(false))
  }, [selectedId])

  return (
    <div>
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, fontWeight: 700, color: '#374151' }}>Select Assessment:</label>
          {listLoading ? (
            <span style={{ fontSize: 13, color: '#9ca3af' }}>Loading…</span>
          ) : (
            <select
              style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid #e5e7eb', fontSize: 13, background: 'white', cursor: 'pointer', minWidth: 300 }}
              value={selectedId ?? ''}
              onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Choose an assessment —</option>
              {assessments.map((a: any) => (
                <option key={a.id} value={a.id}>
                  {a.assessment_name} ({a.generated_at ? new Date(a.generated_at).toLocaleDateString() : '—'})
                </option>
              ))}
            </select>
          )}
        </div>
      </Panel>

      {loading && <LoadingSpinner />}
      {!loading && selectedId && !data && <EmptyState message="No data found for this assessment." />}
      {!loading && !selectedId && <EmptyState message="Select an assessment above to see detailed analytics." />}
      {data && !loading && <AssessmentDrillContent data={data} />}
    </div>
  )
}

function CoderResultsTable({ rows, passThreshold }: { rows: any[]; passThreshold?: number }) {
  const { pageData, Paginator } = usePagination(rows, 15)
  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
              {['Coder', 'Emp ID', 'Score', 'Correct', 'Time', 'Pass/Fail', 'Auto-submit'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '9px 12px', fontWeight: 600 }}>{row.coder_name}</td>
                <td style={{ padding: '9px 12px', color: '#6b7280' }}>{row.employee_id || '—'}</td>
                <td style={{ padding: '9px 12px', fontWeight: 800, color: scoreColor(row.score_pct, passThreshold) }}>{fmt(row.score_pct)}</td>
                <td style={{ padding: '9px 12px', color: '#374151' }}>{row.correct_count}/{row.total_questions}</td>
                <td style={{ padding: '9px 12px', color: '#6b7280' }}>{fmtTime(row.time_taken_seconds)}</td>
                <td style={{ padding: '9px 12px' }}><PassBadge pf={row.pass_fail} /></td>
                <td style={{ padding: '9px 12px' }}>
                  {row.auto_submitted && (
                    <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 20, fontWeight: 700 }}>Auto</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginator />
    </>
  )
}

function QuestionAccuracyTable({ rows }: { rows: any[] }) {
  const { pageData, Paginator } = usePagination(rows, 20)
  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
              {['Question', 'Topic', 'Difficulty', 'Accuracy', 'Responses'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#6b7280', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((q: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '9px 12px', minWidth: 320 }}>
                  <div style={{ fontWeight: 600, color: '#111', fontSize: 12 }}>{q.question_id}</div>
                  <div style={{ color: '#6b7280', fontSize: 11, marginTop: 2, lineHeight: 1.4 }}>{q.question_text}</div>
                </td>
                <td style={{ padding: '9px 12px', color: '#374151', fontSize: 12 }}>{q.topic}</td>
                <td style={{ padding: '9px 12px' }}><DiffBadge diff={q.difficulty} /></td>
                <td style={{ padding: '9px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 70, height: 6, background: '#f3f4f6', borderRadius: 3 }}>
                      {q.accuracy_pct != null && (
                        <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(q.accuracy_pct, 100)}%`, background: scoreColor(q.accuracy_pct) }} />
                      )}
                    </div>
                    <span style={{ fontWeight: 700, color: scoreColor(q.accuracy_pct), fontSize: 12 }}>
                      {q.accuracy_pct != null ? `${q.accuracy_pct}%` : '—'}
                    </span>
                  </div>
                </td>
                <td style={{ padding: '9px 12px', color: '#6b7280', fontSize: 12 }}>{q.correct}/{q.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginator />
    </>
  )
}

function AssessmentDrillContent({ data }: { data: any }) {
  return (
    <div>
      <Panel>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#111', marginBottom: 4 }}>{data.assessment_name}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>
              Generated by <strong>{data.generated_by}</strong> &nbsp;·&nbsp;
              {data.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'} &nbsp;·&nbsp;
              {data.total_questions} questions &nbsp;·&nbsp; {data.duration_minutes}min time limit
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 12, background: 'rgba(124,58,237,0.1)', borderRadius: 8, padding: '6px 12px', color: '#7c3aed', fontWeight: 700 }}>
              {data.total_submitted}/{data.total_sessions} submitted
            </div>
          </div>
        </div>
      </Panel>

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 22 }}>
        <KpiCard label="Avg Score" value={fmt(data.avg_score)} color={scoreColor(data.avg_score, data.pass_threshold)} />
        <KpiCard label="Pass Rate" value={fmt(data.pass_rate)} color={rateColor(data.pass_rate)} />
        <KpiCard label="Min Score" value={fmt(data.min_score)} color={scoreColor(data.min_score, data.pass_threshold)} />
        <KpiCard label="Max Score" value={fmt(data.max_score)} color={scoreColor(data.max_score, data.pass_threshold)} />
        <KpiCard label="Completion" value={fmt(data.completion_rate)} />
        <KpiCard label="Auto-submits" value={fmt(data.auto_submit_rate)} color={data.auto_submit_rate > 20 ? '#d97706' : undefined} />
      </div>

      {data.score_distribution && (
        <Panel title="Score Distribution">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.score_distribution} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="band" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip formatter={(v: any) => [v, 'Coders']} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(data.score_distribution as any[]).map((entry: any, i: number) => (
                  <Cell key={i} fill={bandColor(entry.band)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {data.coder_rows && data.coder_rows.length > 0 && (
        <Panel title="Coder Results">
          <CoderResultsTable rows={data.coder_rows} passThreshold={data.pass_threshold} />
        </Panel>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {data.topic_breakdown && data.topic_breakdown.length > 0 && (
          <Panel title="Accuracy by Topic">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(data.topic_breakdown as any[]).map((t: any, i: number) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ fontWeight: 600, color: '#374151' }}>{t.topic}</span>
                    <span style={{ color: scoreColor(t.avg_accuracy), fontWeight: 700 }}>
                      {t.avg_accuracy != null ? `${t.avg_accuracy}%` : '—'} ({t.question_count}q)
                    </span>
                  </div>
                  <div style={{ height: 7, background: '#f3f4f6', borderRadius: 4 }}>
                    {t.avg_accuracy != null && (
                      <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(t.avg_accuracy, 100)}%`, background: scoreColor(t.avg_accuracy), transition: 'width 0.5s' }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {data.difficulty_calibration && (
          <Panel title="Difficulty Calibration">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {(data.difficulty_calibration as any[]).map((d: any, i: number) => (
                <div key={i} style={{ background: 'rgba(249,250,251,0.8)', borderRadius: 10, padding: '12px 14px', border: '1px solid #f3f4f6' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <DiffBadge diff={d.difficulty} />
                    <span style={{ fontSize: 11, color: '#9ca3af' }}>{d.question_count} questions</span>
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                    <div>
                      <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600 }}>EXPECTED</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: '#6b7280' }}>{d.expected_accuracy}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600 }}>ACTUAL</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: scoreColor(d.actual_accuracy) }}>
                        {d.actual_accuracy != null ? `${d.actual_accuracy}%` : '—'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </div>

      {data.question_accuracy && data.question_accuracy.length > 0 && (
        <Panel title="Question Accuracy (Most-Missed First)">
          <QuestionAccuracyTable rows={data.question_accuracy} />
        </Panel>
      )}
    </div>
  )
}
