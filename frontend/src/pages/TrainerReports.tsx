import { useState, useEffect } from 'react'
import { useSmartBack } from '../hooks/useSmartBack'
import { ChevronLeft, Download } from 'lucide-react'
import { getReportSummary, getReportCharts, buildExportUrl } from '../api'
import type { Specialty, Difficulty, ChartStatus } from '../types'
import { SPECIALTIES, DIFFICULTIES } from '../types'
const PAGE_SIZE = 50

export function TrainerReports() {
  const goBack = useSmartBack('/trainer/chart-management')
  const [summary, setSummary] = useState<{ active: number; retired: number; total: number } | null>(null)
  const [results, setResults] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)

  const [specialty, setSpecialty] = useState<Specialty | ''>('')
  const [difficulty, setDifficulty] = useState<Difficulty | ''>('')
  const [status, setStatus] = useState<ChartStatus | ''>('')
  const [uploadedBy, setUploadedBy] = useState('')

  useEffect(() => { getReportSummary().then(setSummary) }, [])

  useEffect(() => {
    getReportCharts({
      specialty: specialty || undefined,
      difficulty: difficulty || undefined,
      status: status || undefined,
      uploaded_by: uploadedBy || undefined,
      page,
      page_size: PAGE_SIZE,
    }).then(d => { setResults(d.results); setTotal(d.total) })
  }, [specialty, difficulty, status, uploadedBy, page])

  const exportUrl = buildExportUrl({
    specialty: specialty || undefined,
    difficulty: difficulty || undefined,
    status: status || undefined,
    uploaded_by: uploadedBy || undefined,
  })
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const firstShown = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastShown = Math.min(total, page * PAGE_SIZE)

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={() => goBack()}><ChevronLeft size={16} /> Back</button>
        <span style={styles.title}>Reports</span>
        <a href={exportUrl} download style={styles.exportBtn}><Download size={14} /> Export Excel</a>
      </div>

      <div style={styles.content}>
        {summary && (
          <div style={styles.summaryRow}>
            <div style={styles.summaryCard}><div style={styles.summaryNum}>{summary.active}</div><div style={styles.summaryLabel}>Active</div></div>
            <div style={styles.summaryCard}><div style={styles.summaryNum}>{summary.retired}</div><div style={styles.summaryLabel}>Retired</div></div>
            <div style={styles.summaryCard}><div style={styles.summaryNum}>{summary.total}</div><div style={styles.summaryLabel}>Total</div></div>
          </div>
        )}

        <div style={styles.filterRow}>
          <select style={styles.select} value={specialty} onChange={e => { setSpecialty(e.target.value as Specialty | ''); setPage(1) }}>
            <option value="">All Specialties</option>
            {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select style={styles.select} value={difficulty} onChange={e => { setDifficulty(e.target.value as Difficulty | ''); setPage(1) }}>
            <option value="">All Difficulties</option>
            {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <select style={styles.select} value={status} onChange={e => { setStatus(e.target.value as ChartStatus | ''); setPage(1) }}>
            <option value="">All Statuses</option>
            <option value="Active">Active</option>
            <option value="Retired">Retired</option>
          </select>
          <input style={styles.input} placeholder="Uploaded by" value={uploadedBy} onChange={e => { setUploadedBy(e.target.value); setPage(1) }} />
          <span style={styles.count}>
            {total} result{total !== 1 ? 's' : ''}
            {total > 0 && <span style={styles.range}> · {firstShown}-{lastShown}</span>}
          </span>
        </div>

        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>{['Chart #', 'Alias', 'Specialty', 'Category', 'Difficulty', 'Status', 'Uploaded By', 'Date', 'Views'].map(h => (
                <th key={h} style={styles.th}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {results.map((r: any) => (
                <tr key={r.id} style={styles.tr}>
                  <td style={styles.td}><strong>{r.chart_number}</strong></td>
                  <td style={styles.td}>{r.alias || <span style={{ color: '#d1d5db' }}>—</span>}</td>
                  <td style={styles.td}>{r.specialty}</td>
                  <td style={styles.td}>{r.category}</td>
                  <td style={styles.td}>{r.difficulty}</td>
                  <td style={styles.td}>{r.status}</td>
                  <td style={styles.td}>{r.uploaded_by}</td>
                  <td style={styles.td}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</td>
                  <td style={styles.td}>{r.view_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div style={styles.pagination}>
            <button style={styles.pageBtn} disabled={page === 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Prev</button>
            <span style={styles.pageInfo}>Page {page} of {totalPages}</span>
            <button style={styles.pageBtn} disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Next</button>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '6px 12px', cursor: 'pointer', fontSize: 13 },
  title: { fontWeight: 700, fontSize: 18 },
  exportBtn: { marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: '#16a34a', color: '#fff', borderRadius: 6, textDecoration: 'none', fontSize: 13, fontWeight: 600 },
  content: { maxWidth: 1100, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 },
  summaryRow: { display: 'flex', gap: 12 },
  summaryCard: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 24px', textAlign: 'center' },
  summaryNum: { fontSize: 28, fontWeight: 700, color: '#111' },
  summaryLabel: { fontSize: 12, color: '#6b7280', textTransform: 'uppercase' },
  filterRow: { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, background: '#fff' },
  input: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 },
  count: { fontSize: 13, color: '#6b7280', marginLeft: 'auto' },
  range: { color: '#9ca3af' },
  tableWrap: { overflowX: 'auto', background: '#fff', borderRadius: 8, border: '1px solid #e5e7eb' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '10px 14px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' },
  tr: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 14px', fontSize: 13, color: '#374151' },
  pagination: { display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10 },
  pageBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '6px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' },
  pageInfo: { fontSize: 12, color: '#6b7280', fontWeight: 600 },
}
