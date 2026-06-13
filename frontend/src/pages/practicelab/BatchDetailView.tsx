import { useState, useEffect, useRef } from 'react'
import { Loader, Download, Upload, BarChart2, Search, CheckSquare, Square } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getBatch, gradeSubmissions, closeBatch, addBatchNote,
  downloadBatchExcel, downloadCycleExcel, downloadBatchResultsExcel,
  getBatchInsights, runAllocation, searchChartsForBatch,
} from '../../api'
import { SPECIALTY_COLORS } from '../../theme'
import { trainerName } from './shared'
import { InsightsPanel } from './InsightsPanel'
import styles from './styles'

function AllocationPanel({ batch, onDone }: { batch: any; onDone: () => void }) {
  const [form, setForm] = useState({
    charts_per_coder: batch.charts_per_coder,
    notes: '',
    assignMode: 'random' as 'random' | 'manual',
  })
  const [chartSearch, setChartSearch] = useState('')
  const [chartCatFilter, setChartCatFilter] = useState('')
  const [chartDiffFilter, setChartDiffFilter] = useState('')
  const [chartSearchResults, setChartSearchResults] = useState<any[]>([])
  const [selectedChartIds, setSelectedChartIds] = useState<Set<number>>(new Set())
  const [searchingCharts, setSearchingCharts] = useState(false)
  const [running, setRunning] = useState(false)

  const runChartSearch = async () => {
    setSearchingCharts(true)
    try {
      const res = await searchChartsForBatch(batch.specialty, chartSearch || undefined, chartCatFilter || undefined, chartDiffFilter || undefined)
      setChartSearchResults(res)
    } catch { toast.error('Chart search failed') }
    finally { setSearchingCharts(false) }
  }

  const toggleChart = (id: number) => {
    setSelectedChartIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleRun = async () => {
    if (form.assignMode === 'manual' && selectedChartIds.size === 0) return toast.error('Select at least one chart')
    setRunning(true)
    const tid = toast.loading('Running allocation…')
    try {
      const res = await runAllocation(batch.id, {
        charts_per_coder: form.charts_per_coder,
        manual_chart_ids: form.assignMode === 'manual' ? Array.from(selectedChartIds) : [],
        run_by: trainerName(),
        notes: form.notes || undefined,
      })
      toast.dismiss(tid)
      const assignedCount = Object.values(res.assigned).reduce((a: number, b: any) => a + b, 0)
      toast.success(`Cycle ${res.cycle_number} complete — ${assignedCount} charts assigned`)
      if (res.warnings.length) res.warnings.forEach((w: string) => toast(w, { icon: '⚠️', duration: 6000 }))
      onDone()
    } catch (err: any) {
      toast.dismiss(tid)
      toast.error(err?.response?.data?.detail || 'Allocation failed')
    } finally { setRunning(false) }
  }

  const nextCycle = (batch.allocation_cycles?.length || 0) + 1

  return (
    <div style={styles.allocationPanel}>
      <div style={{ fontWeight: 700, fontSize: 14, color: '#0f766e', marginBottom: 12 }}>
        Run Allocation — Cycle {nextCycle}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' as const, alignItems: 'flex-end', marginBottom: 12 }}>
        {form.assignMode === 'random' && (
          <div style={styles.formGroup}>
            <label style={styles.label}>Charts per Coder</label>
            <input type="number" min={1} max={20} style={{ ...styles.input, width: 80 }}
              value={form.charts_per_coder}
              onChange={e => setForm(f => ({ ...f, charts_per_coder: parseInt(e.target.value) || 1 }))} />
          </div>
        )}
        {form.assignMode === 'manual' && (
          <div style={styles.formGroup}>
            <label style={styles.label}>Max Charts per Coder</label>
            <input type="number" min={1} max={50} style={{ ...styles.input, width: 80 }}
              value={form.charts_per_coder}
              onChange={e => setForm(f => ({ ...f, charts_per_coder: parseInt(e.target.value) || 1 }))} />
          </div>
        )}
        <div style={styles.formGroup}>
          <label style={styles.label}>Assignment</label>
          <div style={styles.modeToggle}>
            <button style={form.assignMode === 'random' ? styles.modeTabActive : styles.modeTab} onClick={() => setForm(f => ({ ...f, assignMode: 'random' }))}>Random</button>
            <button style={form.assignMode === 'manual' ? styles.modeTabActive : styles.modeTab} onClick={() => { setForm(f => ({ ...f, assignMode: 'manual' })); runChartSearch() }}>Manual</button>
          </div>
        </div>
        <div style={{ ...styles.formGroup, flex: 1 }}>
          <label style={styles.label}>Notes <span style={styles.hint}>(optional)</span></label>
          <input style={styles.input} value={form.notes} placeholder="e.g. Week 2 push"
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
        </div>
      </div>
      {form.assignMode === 'manual' && (
        <div style={{ marginBottom: 12 }}>
          <div style={styles.chartSearchRow}>
            <input style={{ ...styles.input, flex: 1 }} placeholder="Chart number" value={chartSearch}
              onChange={e => setChartSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && runChartSearch()} />
            <input style={{ ...styles.input, flex: 1 }} placeholder="Category" value={chartCatFilter}
              onChange={e => setChartCatFilter(e.target.value)} onKeyDown={e => e.key === 'Enter' && runChartSearch()} />
            <select style={styles.select} value={chartDiffFilter} onChange={e => setChartDiffFilter(e.target.value)}>
              <option value="">All difficulties</option>
              {['Beginner', 'Intermediate', 'Advanced'].map(d => <option key={d}>{d}</option>)}
            </select>
            <button style={styles.outlineBtn} onClick={runChartSearch} disabled={searchingCharts}>
              {searchingCharts ? <Loader size={13} /> : <Search size={13} />} Search
            </button>
          </div>
          {selectedChartIds.size > 0 && (
            <div style={{ fontSize: 12, color: '#4f46e5', fontWeight: 700, marginBottom: 6 }}>
              {selectedChartIds.size} chart{selectedChartIds.size !== 1 ? 's' : ''} selected
              <button style={{ ...styles.clearSmallBtn, marginLeft: 10 }} onClick={() => setSelectedChartIds(new Set())}>Clear</button>
            </div>
          )}
          {chartSearchResults.length > 0 && (
            <div style={styles.chartPickerList}>
              <div style={styles.chartPickerListHeader}><span>Chart</span><span>Category</span><span>Difficulty</span><span></span></div>
              {chartSearchResults.map(c => {
                const selected = selectedChartIds.has(c.id)
                return (
                  <div key={c.id} style={{ ...styles.chartPickerRow, background: selected ? '#eef2ff' : '#fff' }} onClick={() => toggleChart(c.id)}>
                    <span style={styles.chartPickerNum}>{c.chart_number}</span>
                    <span style={styles.chartPickerCat}>{c.category}</span>
                    <span style={styles.chartPickerDiff}>{c.difficulty}</span>
                    <span>{selected ? <CheckSquare size={16} color="#4f46e5" /> : <Square size={16} color="#d1d5db" />}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10 }}>
        <button style={running ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn} disabled={running} onClick={handleRun}>
          {running ? <><Loader size={14} /> Running…</> : `▶ Run Cycle ${nextCycle}`}
        </button>
      </div>
    </div>
  )
}

export function BatchDetailView({ batchId, onDRGReview, onResults }: any) {
  const [batch, setBatch] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [grading, setGrading] = useState(false)
  const [gradingResult, setGradingResult] = useState<any>(null)
  const [showAllocationPanel, setShowAllocationPanel] = useState(false)
  const [closing, setClosing] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [showNoteBox, setShowNoteBox] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [insights, setInsights] = useState<any>(null)
  const [showInsights, setShowInsights] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadBatch() }, [batchId])

  async function loadBatch() {
    setLoading(true)
    try { setBatch(await getBatch(batchId)) } catch { toast.error('Failed to load batch') } finally { setLoading(false) }
  }

  async function handleGradeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setGrading(true)
    setGradingResult(null)
    const tid = toast.loading(`Grading ${files.length} file${files.length !== 1 ? 's' : ''}…`)
    try {
      const res = await gradeSubmissions(batchId, files)
      setGradingResult(res)
      toast.dismiss(tid)
      if (res.graded.length) toast.success(`${res.graded.length} submission${res.graded.length !== 1 ? 's' : ''} graded${res.errors.length ? ` · ${res.errors.length} skipped` : ''}`)
      if (res.errors.length) res.errors.forEach((e: string) => toast.error(e, { duration: 6000 }))
      loadBatch()
      if (res.graded.length) {
        getBatchInsights(batchId).then(ins => { setInsights(ins); if (ins.has_data) setShowInsights(true) }).catch(() => {})
      }
    } catch (err: any) {
      toast.dismiss(tid)
      toast.error(err?.response?.data?.detail || 'Grading failed')
    } finally {
      setGrading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleClose() {
    setClosing(true)
    try {
      await closeBatch(batchId, trainerName())
      toast.success('Batch closed')
      setConfirmingClose(false)
      loadBatch()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      const msg = typeof detail === 'object' ? detail.reason : (detail || 'Failed to close batch')
      toast.error(msg)
      loadBatch()
    } finally { setClosing(false) }
  }

  async function handleAddNote() {
    if (!noteText.trim()) return
    try {
      await addBatchNote(batchId, noteText.trim(), trainerName())
      toast.success('Note added')
      setNoteText('')
      setShowNoteBox(false)
      loadBatch()
    } catch { toast.error('Failed to add note') }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!batch) return <div style={styles.center}>Batch not found</div>

  const sc = SPECIALTY_COLORS[batch.specialty as keyof typeof SPECIALTY_COLORS]
  const isOpen = batch.status === 'Open'
  const isIP = batch.specialty === 'IP-DRG'
  const hasResults = batch.coders?.some((c: any) => c.charts?.some((ch: any) => ch.submission_status === 'Submitted'))
  const pendingDRG = isIP && (batch.pending_drg_review ?? 0) > 0
  const closeBlockers: string[] = []
  if ((batch.pending_submissions ?? 0) > 0) closeBlockers.push(`${batch.pending_submissions} chart(s) still pending submission`)
  if ((batch.pending_drg_review ?? 0) > 0) closeBlockers.push(`${batch.pending_drg_review} DRG review(s) unresolved`)

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' as const }}>
        <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151', fontSize: 13 }}>{batch.specialty}</span>
        <span style={styles.sectionTitle}>{batch.name}</span>
        <span style={{ fontSize: 12, fontWeight: 700, padding: '3px 12px', borderRadius: 20, border: '1.5px solid',
          color: isOpen ? '#2563eb' : '#16a34a', borderColor: isOpen ? '#2563eb' : '#16a34a' }}>{batch.status}</span>
        {isOpen && batch.days_open != null && (
          <span style={{ fontSize: 12, color: batch.days_open > 14 ? '#d97706' : '#6b7280' }}>
            {batch.days_open} day{batch.days_open !== 1 ? 's' : ''} open
          </span>
        )}
        {batch.force_closed && (
          <span style={{ fontSize: 11, background: '#fee2e2', color: '#dc2626', padding: '2px 10px', borderRadius: 20, fontWeight: 700 }}>Force-closed</span>
        )}
        <span style={{ fontSize: 12, color: '#9ca3af' }}>by {batch.created_by} · {new Date(batch.created_at).toLocaleDateString()}</span>
      </div>

      {batch.force_close_reason && <div style={styles.warnBox}>Force-close reason: {batch.force_close_reason}</div>}

      <div style={styles.cycleSection}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>Allocation Cycles ({batch.allocation_cycles?.length || 0})</span>
          {isOpen && (
            <button style={{ ...styles.primaryBtn, background: '#4f46e5' }} onClick={() => setShowAllocationPanel(p => !p)}>
              {showAllocationPanel ? '✕ Cancel' : '▶ Run New Cycle'}
            </button>
          )}
        </div>
        {showAllocationPanel && isOpen && <AllocationPanel batch={batch} onDone={() => { setShowAllocationPanel(false); loadBatch() }} />}
        {(batch.allocation_cycles || []).length === 0 && !showAllocationPanel && (
          <div style={{ fontSize: 13, color: '#9ca3af', padding: '12px 0' }}>No cycles yet — run the first allocation to assign charts.</div>
        )}
        {(batch.allocation_cycles || []).map((c: any) => (
          <div key={c.id} style={styles.cycleRow}>
            <div style={styles.cycleBadge}>Cycle {c.cycle_number}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{c.charts_per_coder} charts/coder · {c.assigned_count} assignments</div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>by {c.run_by} on {new Date(c.run_at).toLocaleDateString()}{c.notes && <span style={{ marginLeft: 8, color: '#6b7280' }}>— {c.notes}</span>}</div>
            </div>
            <button style={styles.outlineBtn} onClick={() => downloadCycleExcel(batchId, c.id)}><Download size={13} /> Cycle {c.cycle_number} Sheets</button>
          </div>
        ))}
        {(batch.allocation_cycles || []).length > 0 && (
          <div style={{ marginTop: 6 }}>
            <button style={{ ...styles.outlineBtn, fontSize: 12 }} onClick={() => downloadBatchExcel(batchId)}><Download size={13} /> All Cycles (ZIP)</button>
          </div>
        )}
      </div>

      <div style={styles.actionRow}>
        {isOpen && (
          <label style={grading ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
            {grading ? <><Loader size={14} /> Grading...</> : <><Upload size={15} /> Upload Returned Sheets</>}
            <input ref={fileRef} type="file" accept=".xlsx" multiple style={{ display: 'none' }} onChange={handleGradeUpload} disabled={grading} />
          </label>
        )}
        {hasResults && (
          <>
            {pendingDRG && (
              <button style={{ ...styles.primaryBtn, background: '#d97706' }} onClick={onDRGReview}>DRG Review Required</button>
            )}
            <button style={styles.outlineBtn} onClick={onResults}><BarChart2 size={15} /> View Results</button>
            <button style={{ ...styles.outlineBtn, color: '#4f46e5', borderColor: '#a5b4fc' }}
              onClick={() => {
                if (insights) { setShowInsights(s => !s) }
                else { getBatchInsights(batchId).then(ins => { setInsights(ins); setShowInsights(true) }).catch(() => toast.error('Failed to load insights')) }
              }}>
              ✦ {showInsights ? 'Hide Insights' : 'View Insights'}
            </button>
            <button style={styles.outlineBtn} onClick={() => downloadBatchResultsExcel(batchId)}><Download size={15} /> Export Results</button>
          </>
        )}
        {isOpen && closeBlockers.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#991b1b', fontWeight: 600 }}>Cannot close: {closeBlockers.join(' · ')}</span>
          </div>
        )}
        {isOpen && closeBlockers.length === 0 && !confirmingClose && (
          <button style={{ ...styles.outlineBtn, color: '#dc2626', borderColor: '#fca5a5', marginLeft: 'auto' }} onClick={() => setConfirmingClose(true)}>✕ Close Batch</button>
        )}
        {isOpen && closeBlockers.length === 0 && confirmingClose && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>Lock all results?</span>
            <button style={{ ...styles.primaryBtn, background: '#dc2626', padding: '5px 12px', fontSize: 12 }} disabled={closing} onClick={handleClose}>
              {closing ? 'Closing…' : 'Yes, Close'}
            </button>
            <button style={{ ...styles.outlineBtn, padding: '5px 12px', fontSize: 12 }} onClick={() => setConfirmingClose(false)}>Cancel</button>
          </div>
        )}
      </div>

      {gradingResult && (
        <div style={styles.infoBox}>
          <strong>Grading complete:</strong> {gradingResult.graded.length} submission(s) processed.
          {gradingResult.errors.length > 0 && (
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18, color: '#dc2626', fontSize: 12 }}>
              {gradingResult.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      {showInsights && insights?.has_data && <InsightsPanel insights={insights} onClose={() => setShowInsights(false)} />}

      <div style={styles.sectionHeader}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>Coders ({batch.coders?.length || 0})</span>
      </div>
      <div style={styles.table}>
        <div style={styles.tableHeader}><span>Coder</span><span>Emp ID</span><span>Charts Assigned</span><span>Submitted</span></div>
        {(batch.coders || []).map((c: any) => {
          const submitted = c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length
          return (
            <div key={c.name} style={styles.tableRow}>
              <span style={{ fontWeight: 600 }}>{c.name}</span>
              <span style={{ color: '#0f766e', fontWeight: 600 }}>{c.emp_id || '—'}</span>
              <span>{c.charts.length}</span>
              <span style={{ color: submitted > 0 ? '#16a34a' : '#9ca3af' }}>{submitted} / {c.charts.length}</span>
            </div>
          )
        })}
      </div>

      <div style={styles.cycleSection}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 13, color: '#374151' }}>Batch Log</span>
          <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '4px 10px' }} onClick={() => setShowNoteBox(p => !p)}>
            {showNoteBox ? 'Cancel' : '+ Add Note'}
          </button>
        </div>
        {showNoteBox && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <input style={{ ...styles.input, flex: 1 }} placeholder="Note for this batch…"
              value={noteText} onChange={e => setNoteText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddNote()} />
            <button style={styles.primaryBtn} onClick={handleAddNote}>Add</button>
          </div>
        )}
        {(batch.notes || []).length === 0 && !showNoteBox && <div style={{ fontSize: 12, color: '#9ca3af' }}>No notes yet.</div>}
        {(batch.notes || []).map((n: any, i: number) => (
          <div key={i} style={styles.noteRow}>
            <span style={{ fontSize: 13, flex: 1 }}>{n.text}</span>
            <span style={{ fontSize: 11, color: '#9ca3af', whiteSpace: 'nowrap' as const }}>{n.author} · {new Date(n.ts).toLocaleDateString()}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
