import { useState, useEffect, useRef } from 'react'
import { Loader, Download, Upload, BarChart2, Search, CheckSquare, Square, CheckCircle, Circle, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getBatch, gradeSubmissions, closeBatch, addBatchNote,
  downloadBatchExcel, downloadCycleExcel, downloadBatchResultsExcel,
  getBatchInsights, runAllocation, searchChartsForBatch, getCategories,
  addCodersToBatch,
} from '../../api'
import { SPECIALTY_COLORS } from '../../theme'
import { trainerName } from './shared'
import { InsightsPanel } from './InsightsPanel'
import styles from './styles'

function AllocationPanel({ batch, onDone }: { batch: any; onDone: () => void }) {
  const allCoderNames: string[] = (batch.coders || []).map((c: any) => c.coder_name)
  const [form, setForm] = useState({
    charts_per_coder: batch.charts_per_coder,
    notes: '',
    assignMode: 'random' as 'random' | 'manual',
  })
  const [includedCoders, setIncludedCoders] = useState<Set<string>>(new Set(allCoderNames))

  const toggleCoder = (name: string) =>
    setIncludedCoders(prev => { const n = new Set(prev); n.has(name) ? n.delete(name) : n.add(name); return n })
  const [chartSearch, setChartSearch] = useState('')
  const [chartCatFilter, setChartCatFilter] = useState('')
  const [knownCategories, setKnownCategories] = useState<string[]>([])

  useEffect(() => { getCategories(batch.specialty).then(setKnownCategories).catch(() => {}) }, [])
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
      const excludedCoders = allCoderNames.filter(n => !includedCoders.has(n))
      const res = await runAllocation(batch.id, {
        charts_per_coder: form.charts_per_coder,
        manual_chart_ids: form.assignMode === 'manual' ? Array.from(selectedChartIds) : [],
        run_by: trainerName(),
        notes: form.notes || undefined,
        exclude_coders: excludedCoders,
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
            <input list="cat-suggestions" style={{ ...styles.input, flex: 1 }} placeholder="Category" value={chartCatFilter}
              onChange={e => setChartCatFilter(e.target.value)} onKeyDown={e => e.key === 'Enter' && runChartSearch()} />
            <datalist id="cat-suggestions">{knownCategories.map(c => <option key={c} value={c} />)}</datalist>
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
      {allCoderNames.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#374151', marginBottom: 6 }}>
            Include Coders <span style={{ fontWeight: 400, color: '#9ca3af' }}>(uncheck absent coders)</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 8 }}>
            {allCoderNames.map(name => {
              const checked = includedCoders.has(name)
              return (
                <div key={name} onClick={() => toggleCoder(name)} style={{
                  display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                  padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                  background: checked ? '#ecfdf5' : '#f9fafb',
                  border: `1px solid ${checked ? '#6ee7b7' : '#e5e7eb'}`,
                  color: checked ? '#065f46' : '#9ca3af',
                  userSelect: 'none' as const,
                }}>
                  {checked ? <CheckSquare size={13} color="#059669" /> : <Square size={13} color="#d1d5db" />}
                  {name}
                </div>
              )
            })}
          </div>
          {includedCoders.size === 0 && (
            <div style={{ fontSize: 11, color: '#dc2626', marginTop: 4 }}>Select at least one coder to run the cycle.</div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10 }}>
        <button style={(running || includedCoders.size === 0) ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
          disabled={running || includedCoders.size === 0} onClick={handleRun}>
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
  const [pendingRegrade, setPendingRegrade] = useState<File[] | null>(null)
  const [regradeConflicts, setRegradeConflicts] = useState<{ coder: string; chart: string }[] | null>(null)
  const [showAllocationPanel, setShowAllocationPanel] = useState(false)
  const [closing, setClosing] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [showNoteBox, setShowNoteBox] = useState(false)
  const [showAddCoder, setShowAddCoder] = useState(false)
  const [newCoders, setNewCoders] = useState([{ name: '', emp_id: '' }])
  const [addingCoders, setAddingCoders] = useState(false)
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
      toast.dismiss(tid)
      if (res.needs_confirmation) {
        setPendingRegrade(files)
        setRegradeConflicts(res.conflicts || [])
        return
      }
      setGradingResult(res)
      const missingKeys = (res.errors as string[]).filter(e => e.includes('no answer key'))
      const otherErrors = (res.errors as string[]).filter(e => !e.includes('no answer key'))
      if (res.graded.length) toast.success(`${res.graded.length} chart${res.graded.length !== 1 ? 's' : ''} graded${res.errors.length ? ` · ${res.errors.length} skipped` : ''}`)
      if (missingKeys.length) toast(`${missingKeys.length} chart${missingKeys.length !== 1 ? 's' : ''} skipped — answer key missing. Upload keys then re-grade.`, { icon: '🔑', duration: 8000 })
      if (otherErrors.length) otherErrors.forEach((e: string) => toast.error(e, { duration: 6000 }))
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

  async function handleRegradeConfirm() {
    if (!pendingRegrade) return
    const files = pendingRegrade
    setPendingRegrade(null)
    setRegradeConflicts(null)
    setGrading(true)
    setGradingResult(null)
    const tid = toast.loading(`Re-grading ${files.length} file${files.length !== 1 ? 's' : ''}…`)
    try {
      const res = await gradeSubmissions(batchId, files, true)
      setGradingResult(res)
      toast.dismiss(tid)
      const missingKeys2 = (res.errors as string[]).filter(e => e.includes('no answer key'))
      const otherErrors2 = (res.errors as string[]).filter(e => !e.includes('no answer key'))
      if (res.graded.length) toast.success(`${res.graded.length} chart${res.graded.length !== 1 ? 's' : ''} re-graded${res.errors.length ? ` · ${res.errors.length} skipped` : ''}`)
      if (missingKeys2.length) toast(`${missingKeys2.length} chart${missingKeys2.length !== 1 ? 's' : ''} skipped — answer key missing. Upload keys then re-grade.`, { icon: '🔑', duration: 8000 })
      if (otherErrors2.length) otherErrors2.forEach((e: string) => toast.error(e, { duration: 6000 }))
      loadBatch()
      if (res.graded.length) {
        getBatchInsights(batchId).then(ins => { setInsights(ins); if (ins.has_data) setShowInsights(true) }).catch(() => {})
      }
    } catch (err: any) {
      toast.dismiss(tid)
      toast.error(err?.response?.data?.detail || 'Re-grading failed')
    } finally {
      setGrading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!batch) return <div style={styles.center}>Batch not found</div>

  const sc = SPECIALTY_COLORS[batch.specialty as keyof typeof SPECIALTY_COLORS]
  const isOpen = batch.status === 'Open'
  const isIP = batch.specialty === 'IP-DRG'
  const totalCoders = batch.coders?.length || 0
  const totalAssigned = batch.coders?.reduce((sum: number, c: any) => sum + c.charts.length, 0) || 0
  const totalSubmitted = batch.coders?.reduce((sum: number, c: any) => sum + c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length, 0) || 0
  const hasCycles = (batch.allocation_cycles?.length || 0) > 0
  const hasResults = totalSubmitted > 0
  const pendingDRG = isIP && (batch.pending_drg_review ?? 0) > 0
  const pendingSubs = batch.pending_submissions ?? 0
  const closeBlockers: string[] = []
  if (pendingSubs > 0) closeBlockers.push(`${pendingSubs} chart(s) still pending submission`)
  if ((batch.pending_drg_review ?? 0) > 0) closeBlockers.push(`${batch.pending_drg_review} DRG review(s) unresolved`)
  const canClose = isOpen && closeBlockers.length === 0 && hasResults

  // Progression steps
  const steps = [
    { label: 'Run Cycle', done: hasCycles, active: !hasCycles },
    { label: 'Download Sheets', done: hasCycles, active: hasCycles && totalSubmitted === 0 },
    { label: 'Upload Returns', done: totalSubmitted > 0, active: hasCycles && totalSubmitted === 0 },
    ...(isIP ? [{ label: 'DRG Review', done: !pendingDRG && hasResults, active: pendingDRG }] : []),
    { label: 'View Results', done: false, active: hasResults && !pendingDRG },
    { label: 'Close Batch', done: !isOpen, active: canClose },
  ]

  return (
    <div style={styles.section}>
      {/* Re-grade confirmation dialog */}
      {regradeConflicts && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 460, width: '90%', boxShadow: '0 8px 32px rgba(0,0,0,0.18)' }}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Re-grade existing submissions?</div>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
              The following sheets have already been graded in this batch. Re-grading will overwrite their previous results.
            </div>
            <div style={{ background: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb', padding: '8px 12px', marginBottom: 18, maxHeight: 180, overflowY: 'auto' }}>
              {regradeConflicts.map((c, i) => (
                <div key={i} style={{ fontSize: 13, padding: '3px 0', borderBottom: i < regradeConflicts.length - 1 ? '1px solid #f0f0f0' : undefined }}>
                  <span style={{ fontWeight: 600 }}>{c.coder}</span> — Chart {c.chart}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button style={styles.outlineBtn} onClick={() => { setPendingRegrade(null); setRegradeConflicts(null); if (fileRef.current) fileRef.current.value = '' }}>Cancel</button>
              <button style={styles.warningBtn} onClick={handleRegradeConfirm}>Re-grade (overwrite)</button>
            </div>
          </div>
        </div>
      )}
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

      {/* Progression tracker */}
      {isOpen && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 10, padding: '10px 16px', marginBottom: 14, flexWrap: 'wrap' as const }}>
          {steps.map((step, i) => (
            <div key={step.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {i > 0 && <span style={{ color: '#d1d5db', fontSize: 14, margin: '0 4px' }}>→</span>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5,
                padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: step.done ? '#dcfce7' : step.active ? '#eff6ff' : '#f3f4f6',
                color: step.done ? '#166534' : step.active ? '#1d4ed8' : '#9ca3af',
                border: `1px solid ${step.done ? '#bbf7d0' : step.active ? '#bfdbfe' : '#e5e7eb'}`,
              }}>
                {step.done
                  ? <CheckCircle size={12} />
                  : step.active
                    ? <Circle size={12} style={{ opacity: 0.7 }} />
                    : <Circle size={12} style={{ opacity: 0.3 }} />
                }
                {step.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Live status counts */}
      {isOpen && hasCycles && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' as const, marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 14px', fontSize: 13 }}>
            <span style={{ fontWeight: 700, color: '#111' }}>{totalSubmitted}</span>
            <span style={{ color: '#6b7280' }}>of</span>
            <span style={{ fontWeight: 700, color: '#111' }}>{totalAssigned}</span>
            <span style={{ color: '#6b7280' }}>charts submitted</span>
            {totalAssigned > 0 && (
              <span style={{ fontWeight: 700, color: totalSubmitted === totalAssigned ? '#16a34a' : '#d97706', marginLeft: 4 }}>
                ({Math.round(totalSubmitted / totalAssigned * 100)}%)
              </span>
            )}
          </div>
          {pendingDRG && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '6px 14px', fontSize: 13 }}>
              <AlertCircle size={14} color="#d97706" />
              <span style={{ fontWeight: 700, color: '#92400e' }}>{batch.pending_drg_review} DRG review{batch.pending_drg_review !== 1 ? 's' : ''} pending</span>
            </div>
          )}
          {canClose && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '6px 14px', fontSize: 13 }}>
              <CheckCircle size={14} color="#16a34a" />
              <span style={{ fontWeight: 700, color: '#166534' }}>Ready to close</span>
            </div>
          )}
          {isOpen && closeBlockers.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '6px 14px', fontSize: 13 }}>
              <AlertCircle size={14} color="#dc2626" />
              <span style={{ color: '#991b1b', fontWeight: 600 }}>{closeBlockers.join(' · ')}</span>
            </div>
          )}
        </div>
      )}

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
          <div style={{ fontSize: 13, color: '#6b7280', padding: '14px 16px', background: '#f8fafc', borderRadius: 8, border: '1px dashed #e5e7eb' }}>
            No cycles yet. Click <strong>Run New Cycle</strong> above to assign charts to coders and generate their answer sheets.
          </div>
        )}
        {(batch.allocation_cycles || []).map((c: any) => (
          <div key={c.id} style={styles.cycleRow}>
            <div style={styles.cycleBadge}>{c.cycle_number === 0 ? 'Legacy' : `Cycle ${c.cycle_number}`}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{c.assigned_count} assignment{c.assigned_count !== 1 ? 's' : ''}{c.assigned_count > 0 ? ` · ${c.charts_per_coder} charts/coder` : ' — pool exhausted'}</div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>by {c.run_by} on {new Date(c.run_at).toLocaleDateString()}{c.notes && <span style={{ marginLeft: 8, color: '#6b7280' }}>— {c.notes}</span>}</div>
            </div>
            {c.assigned_count > 0 && (
              <button style={styles.outlineBtn} title={`Download a ZIP of all coder Excel answer sheets for Cycle ${c.cycle_number}`}
                onClick={() => downloadCycleExcel(batchId, c.id)}><Download size={13} /> {c.cycle_number === 0 ? 'Legacy Sheets' : `Cycle ${c.cycle_number} Sheets`}</button>
            )}
          </div>
        ))}
        {(batch.allocation_cycles || []).some((c: any) => c.assigned_count > 0) && (
          <div style={{ marginTop: 6 }}>
            <button style={{ ...styles.outlineBtn, fontSize: 12 }} title="Download answer sheets for ALL cycles bundled into one ZIP"
              onClick={() => downloadBatchExcel(batchId)}><Download size={13} /> All Cycles (ZIP)</button>
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
              <button style={styles.warningBtn} onClick={onDRGReview}>DRG Review Required</button>
            )}
            <button style={styles.outlineBtn} onClick={onResults}><BarChart2 size={15} /> View Results</button>
            <button style={{ ...styles.outlineBtn, color: '#4f46e5', borderColor: '#a5b4fc' }}
              onClick={() => {
                if (insights) { setShowInsights(s => !s) }
                else { getBatchInsights(batchId).then(ins => { setInsights(ins); setShowInsights(true) }).catch(() => toast.error('Failed to load insights')) }
              }}>
              ✦ {showInsights ? 'Hide Insights' : 'View Insights'}
            </button>
            <button style={styles.outlineBtn} title="Download per-coder scores, pass/fail, and feedback detail as Excel (.xlsx)"
              onClick={() => downloadBatchResultsExcel(batchId)}><Download size={15} /> Export Results (.xlsx)</button>
          </>
        )}
        {isOpen && closeBlockers.length === 0 && !confirmingClose && (
          <button style={{ ...styles.destructiveOutlineBtn, marginLeft: 'auto' }} onClick={() => setConfirmingClose(true)}>✕ Close Batch</button>
        )}
        {isOpen && closeBlockers.length === 0 && confirmingClose && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>Lock all results?</span>
            <button style={{ ...styles.destructiveBtn, padding: '5px 12px', fontSize: 12 }} disabled={closing} onClick={handleClose}>
              {closing ? 'Closing…' : 'Yes, Close'}
            </button>
            <button style={{ ...styles.outlineBtn, padding: '5px 12px', fontSize: 12 }} onClick={() => setConfirmingClose(false)}>Cancel</button>
          </div>
        )}
      </div>

      {gradingResult && (() => {
        const missingKeyErrs = (gradingResult.errors as string[]).filter((e: string) => e.includes('no answer key'))
        const otherErrs = (gradingResult.errors as string[]).filter((e: string) => !e.includes('no answer key'))
        return (
          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
            <div style={styles.infoBox}>
              <strong>Grading complete:</strong> {gradingResult.graded.length} chart{gradingResult.graded.length !== 1 ? 's' : ''} graded
              {gradingResult.errors.length > 0 && <span style={{ color: '#6b7280' }}> · {gradingResult.errors.length} skipped</span>}
            </div>
            {missingKeyErrs.length > 0 && (
              <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '12px 14px' }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: '#92400e', marginBottom: 6 }}>
                  🔑 {missingKeyErrs.length} chart{missingKeyErrs.length !== 1 ? 's' : ''} skipped — answer key not found
                </div>
                <div style={{ fontSize: 12, color: '#78350f', marginBottom: 8 }}>
                  Upload answer keys for these charts in the Answer Keys section, then re-upload this grading sheet.
                </div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#92400e' }}>
                  {missingKeyErrs.map((e: string, i: number) => {
                    const match = e.match(/no answer key for (.+)$/)
                    return <li key={i}>{match ? match[1] : e}</li>
                  })}
                </ul>
              </div>
            )}
            {otherErrs.length > 0 && (
              <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '12px 14px' }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: '#dc2626', marginBottom: 6 }}>Other errors ({otherErrs.length})</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#dc2626' }}>
                  {otherErrs.map((e: string, i: number) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}
          </div>
        )
      })()}

      {showInsights && insights?.has_data && <InsightsPanel insights={insights} batchId={batchId} onClose={() => setShowInsights(false)} />}

      <div style={styles.sectionHeader}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>Coders ({batch.coders?.length || 0})</span>
        {batch.status === 'Open' && (
          <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '4px 10px' }} onClick={() => { setShowAddCoder(p => !p); setNewCoders([{ name: '', emp_id: '' }]) }}>
            {showAddCoder ? 'Cancel' : '+ Add Coder'}
          </button>
        )}
      </div>

      {showAddCoder && (
        <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: 16, marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 10 }}>Add coder(s) to this batch</div>
          {newCoders.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
              <input
                style={{ ...styles.input, flex: 2, margin: 0, fontSize: 13 }}
                placeholder="Coder name *"
                value={row.name}
                onChange={e => setNewCoders(prev => prev.map((r, j) => j === i ? { ...r, name: e.target.value } : r))}
              />
              <input
                style={{ ...styles.input, flex: 1, margin: 0, fontSize: 13 }}
                placeholder="Emp ID (optional)"
                value={row.emp_id}
                onChange={e => setNewCoders(prev => prev.map((r, j) => j === i ? { ...r, emp_id: e.target.value } : r))}
              />
              {newCoders.length > 1 && (
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 18, lineHeight: 1, padding: '0 4px' }}
                  onClick={() => setNewCoders(prev => prev.filter((_, j) => j !== i))}>×</button>
              )}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '5px 10px' }} onClick={() => setNewCoders(prev => [...prev, { name: '', emp_id: '' }])}>+ Add row</button>
            <button
              style={addingCoders ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
              disabled={addingCoders || newCoders.every(r => !r.name.trim())}
              onClick={async () => {
                const valid = newCoders.filter(r => r.name.trim())
                if (!valid.length) return
                setAddingCoders(true)
                try {
                  const res = await addCodersToBatch(batchId, valid)
                  if (res.added.length) toast.success(`Added: ${res.added.join(', ')}`)
                  if (res.skipped_duplicates.length) toast(`Already in batch (skipped): ${res.skipped_duplicates.join(', ')}`, { icon: 'ℹ️' })
                  setShowAddCoder(false)
                  setNewCoders([{ name: '', emp_id: '' }])
                  loadBatch()
                } catch (err: any) {
                  toast.error(err?.response?.data?.detail || 'Failed to add coders')
                } finally { setAddingCoders(false) }
              }}>
              {addingCoders ? <><Loader size={13} /> Adding...</> : 'Add to Batch'}
            </button>
          </div>
          <p style={{ fontSize: 11, color: '#9ca3af', margin: '8px 0 0' }}>New coders will be included in the next allocation cycle run.</p>
        </div>
      )}

      <div style={styles.table}>
        <div style={styles.tableHeader}><span>Coder</span><span>Emp ID</span><span>Charts Assigned</span><span>Submitted</span></div>
        {(batch.coders || []).map((c: any, i: number) => {
          const submitted = c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length
          return (
            <div key={c.name} className={i % 2 === 1 ? 'pl-tr-alt' : 'pl-tr'} style={styles.tableRow}>
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
