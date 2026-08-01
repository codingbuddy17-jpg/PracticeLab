import { useState, useEffect } from 'react'
import { Loader, Download, BarChart2, Search, CheckSquare, Square, CheckCircle, Circle, AlertCircle, ChevronDown, ChevronRight, Key, Copy, Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import RandomisationStatsCard from '../../components/RandomisationStatsCard'
import { CoderPicker } from '../../components/CoderPicker'
import {
  getBatch, closeBatch, addBatchNote,
  downloadBatchResultsExcel,
  getBatchInsights, runAllocation, searchChartsForBatch, getCategories,
  addCodersToBatch, gradeEDChart, getEDGrades, EDRubricPayload,
  downloadSessionCoderReportPdf,
} from '../../api'
import api from '../../api/client'
import { SPECIALTY_COLORS } from '../../theme'
import { trainerName } from './shared'
import { InsightsPanel } from './InsightsPanel'
import styles from './styles'

const IS_ED = (specialty: string) => specialty === 'Edits' || specialty === 'Denials'

const RATIONALE_LABELS: Record<string, string> = {
  acceptable: 'Acceptable (5%)',
  needs_improvement: 'Needs Improvement (2.5%)',
  not_acceptable: 'Not Acceptable (0%)',
}

function EDGradingPanel({ batch, onGraded }: { batch: any; onGraded: () => void }) {
  const assignments: Array<{ coder_name: string; chart_id: number; chart_number: string }> =
    (batch.allocation_cycles || []).flatMap((c: any) =>
      (c.assignments || []).map((a: any) => ({
        coder_name: a.coder_name,
        chart_id: a.chart_id,
        chart_number: a.chart_number,
      }))
    )

  const coders: string[] = Array.from(new Set(assignments.map(a => a.coder_name)))
  const [selectedCoder, setSelectedCoder] = useState(coders[0] || '')
  const [existingGrades, setExistingGrades] = useState<Record<string, any>>({})
  const [forms, setForms] = useState<Record<string, any>>({})
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [expandedNote, setExpandedNote] = useState<string | null>(null)

  const coderAssignments = assignments.filter(a => a.coder_name === selectedCoder)

  useEffect(() => {
    getEDGrades(batch.id).then(grades => {
      const map: Record<string, any> = {}
      grades.forEach(g => { map[`${g.coder_name}__${g.chart_id}`] = g })
      setExistingGrades(map)
    }).catch(() => {})
  }, [batch.id])

  function getForm(chartId: number) {
    const key = `${selectedCoder}__${chartId}`
    if (forms[key]) return forms[key]
    const existing = existingGrades[key]?.rubric
    return {
      review_pass: existing?.review_pass ?? false,
      research_coding_pass: existing?.research_coding_pass ?? false,
      research_payer_pass: existing?.research_payer_pass ?? false,
      research_nuances_pass: existing?.research_nuances_pass ?? false,
      resolution_pass: existing?.resolution_pass ?? false,
      rationale_tier: existing?.rationale_tier ?? 'not_acceptable',
      trainer_note: existing?.trainer_note ?? '',
    }
  }

  function setForm(chartId: number, patch: any) {
    const key = `${selectedCoder}__${chartId}`
    setForms(prev => ({ ...prev, [key]: { ...getForm(chartId), ...patch } }))
  }

  async function handleSubmit(chartId: number, regrade = false) {
    const key = `${selectedCoder}__${chartId}`
    const form = getForm(chartId)
    setSubmitting(key)
    try {
      const payload: EDRubricPayload = {
        coder_name: selectedCoder,
        chart_id: chartId,
        ...form,
        graded_by: trainerName(),
        regrade,
      }
      const res = await gradeEDChart(batch.id, payload)
      if (res.needs_confirmation) {
        if (window.confirm(`This chart already has a score of ${res.existing_score}. Re-grade and overwrite?`)) {
          await handleSubmit(chartId, true)
        }
        return
      }
      toast.success(`Graded: ${res.total_score}% — ${res.pass_fail}`)
      const updated = await getEDGrades(batch.id)
      const map: Record<string, any> = {}
      updated.forEach(g => { map[`${g.coder_name}__${g.chart_id}`] = g })
      setExistingGrades(map)
      setForms(prev => { const n = { ...prev }; delete n[key]; return n })
      onGraded()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save grade')
    } finally {
      setSubmitting(null)
    }
  }

  if (assignments.length === 0) {
    return (
      <div style={{ fontSize: 13, color: '#6b7280', padding: '14px 16px', background: '#f8fafc', borderRadius: 8, border: '1px dashed #e5e7eb' }}>
        No charts assigned yet — run an allocation cycle first.
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' as const, marginBottom: 14 }}>
        {coders.map(c => (
          <button key={c} onClick={() => setSelectedCoder(c)}
            style={{ padding: '5px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: '1.5px solid',
              background: selectedCoder === c ? '#eff6ff' : '#f9fafb',
              color: selectedCoder === c ? '#1d4ed8' : '#374151',
              borderColor: selectedCoder === c ? '#93c5fd' : '#e5e7eb' }}>
            {c}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
        {coderAssignments.map(({ chart_id, chart_number }) => {
          const key = `${selectedCoder}__${chart_id}`
          const form = getForm(chart_id)
          const existing = existingGrades[key]
          const isGraded = !!existing
          const isBusy = submitting === key
          const noteKey = `${key}__note`

          return (
            <div key={chart_id} style={{ border: `1.5px solid ${isGraded ? '#bbf7d0' : '#e5e7eb'}`, borderRadius: 10, padding: 14, background: isGraded ? '#f0fdf4' : '#fff' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>Chart {chart_number}</span>
                {isGraded && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: existing.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>
                      {existing.total_score}% — {existing.pass_fail}
                    </span>
                    {existing.rubric?.trainer_note && (
                      <button onClick={() => setExpandedNote(expandedNote === noteKey ? null : noteKey)}
                        style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, border: '1px solid #93c5fd', background: '#eff6ff', color: '#1d4ed8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}>
                        {expandedNote === noteKey ? <ChevronDown size={11} /> : <ChevronRight size={11} />} Trainer Note
                      </button>
                    )}
                  </div>
                )}
              </div>

              {isGraded && expandedNote === noteKey && existing.rubric?.trainer_note && (
                <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#1e40af', marginBottom: 10 }}>
                  {existing.rubric.trainer_note}
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 20px', marginBottom: 10 }}>
                {[
                  ['review_pass', 'Review (30%) — EOB, letters, records reviewed'],
                  ['research_coding_pass', 'Research: Coding Accuracy (10%)'],
                  ['research_payer_pass', 'Research: Payer Policies (10%)'],
                  ['research_nuances_pass', 'Research: Client/Claim Nuances (10%)'],
                  ['resolution_pass', 'Resolution (35%)'],
                ].map(([field, label]) => (
                  <label key={field} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, cursor: 'pointer', userSelect: 'none' as const }}>
                    <input type="checkbox" checked={!!(form as any)[field]}
                      onChange={e => setForm(chart_id, { [field]: e.target.checked })} />
                    {label}
                  </label>
                ))}
                <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>Rationale Writing (5%)</span>
                  <select value={form.rationale_tier} onChange={e => setForm(chart_id, { rationale_tier: e.target.value })}
                    style={{ ...styles.select, fontSize: 12, padding: '4px 8px' }}>
                    {Object.entries(RATIONALE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                  Trainer Note <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional — visible to coder)</span>
                </label>
                <textarea value={form.trainer_note} onChange={e => setForm(chart_id, { trainer_note: e.target.value })}
                  rows={2} placeholder="Feedback for the coder on this case..."
                  style={{ ...styles.input, width: '100%', resize: 'vertical' as const, fontSize: 12, margin: 0 }} />
              </div>

              <button disabled={isBusy} onClick={() => handleSubmit(chart_id)}
                style={{ ...(isBusy ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn), fontSize: 12, padding: '6px 14px' }}>
                {isBusy ? <><Loader size={12} /> Saving…</> : isGraded ? 'Update Grade' : 'Save Grade'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

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
              {selectedChartIds.size} chart{selectedChartIds.size !== 1 ? 's' : ''} selected — assigned to every included coder below (up to Max Charts per Coder, skipping any already assigned to them)
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

  useEffect(() => { loadBatch() }, [batchId])

  async function loadBatch() {
    setLoading(true)
    try { setBatch(await getBatch(batchId)) } catch { toast.error('Failed to load batch') } finally { setLoading(false) }
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
  const isED = IS_ED(batch.specialty)
  const totalCoders = batch.coders?.length || 0
  const totalAssigned = batch.coders?.reduce((sum: number, c: any) => sum + c.charts.length, 0) || 0
  const totalSubmitted = batch.coders?.reduce((sum: number, c: any) => sum + c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length, 0) || 0
  const hasCycles = (batch.allocation_cycles?.length || 0) > 0
  const isDirectAssignment = !!batch.is_direct_assignment
  const hasResults = isDirectAssignment
    ? (batch.direct_graded_count || 0) > 0
    : totalSubmitted > 0
  const pendingDRG = isIP && (batch.pending_drg_review ?? 0) > 0
  const pendingSubs = batch.pending_submissions ?? 0
  const closeBlockers: string[] = []
  if (!isDirectAssignment) {
    if (pendingSubs > 0) closeBlockers.push(`${pendingSubs} chart(s) still pending submission`)
    if ((batch.pending_drg_review ?? 0) > 0) closeBlockers.push(`${batch.pending_drg_review} DRG review(s) unresolved`)
  }
  const canClose = isOpen && closeBlockers.length === 0 && (hasResults || isDirectAssignment)

  // Progression steps
  const steps = [
    { label: 'Run Cycle', done: hasCycles, active: !hasCycles },
    ...(isDirectAssignment || !isED
      ? [{ label: 'Generate Sessions', done: totalSubmitted > 0, active: hasCycles && totalSubmitted === 0 },
         ...(isIP && !isDirectAssignment ? [{ label: 'DRG Review', done: !pendingDRG && hasResults, active: pendingDRG }] : [])]
      : [{ label: 'Grade Cases', done: totalSubmitted > 0, active: hasCycles && totalSubmitted === 0 }]
    ),
    { label: 'View Results', done: false, active: hasResults && !pendingDRG },
    { label: isDirectAssignment ? 'Close Assignment' : 'Close Batch', done: !isOpen, active: canClose },
  ]

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
            No cycles yet. Click <strong>Run New Cycle</strong> above to assign charts to coders{isED ? ' — then grade each case using the rubric below.' : ' — coders complete charts in their practice sessions.'}
          </div>
        )}
        {(batch.allocation_cycles || []).map((c: any) => (
          <div key={c.id} style={{ ...styles.cycleRow, flexDirection: 'column', alignItems: 'stretch', gap: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={styles.cycleBadge}>{c.cycle_number === 0 ? 'Legacy' : `Cycle ${c.cycle_number}`}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{c.assigned_count} assignment{c.assigned_count !== 1 ? 's' : ''}{c.assigned_count > 0 ? ` · ${c.charts_per_coder} charts/coder` : ' — pool exhausted'}</span>
                  {/* A short allocation used to be visible only as a toast, so a
                      cycle that shorted three coders looked identical to a clean
                      one the next time anyone opened the batch. */}
                  {(c.warnings || []).length > 0 && (
                    <span style={{ fontSize: 11, fontWeight: 700, background: '#fef3c7', color: '#92400e', border: '1px solid #fcd34d', borderRadius: 20, padding: '1px 9px' }}>
                      ⚠️ {c.warnings.length} allocated short
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: '#9ca3af' }}>by {c.run_by} on {new Date(c.run_at).toLocaleDateString()}{c.notes && <span style={{ marginLeft: 8, color: '#6b7280' }}>— {c.notes}</span>}</div>
                {(c.warnings || []).length > 0 && (
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 11, color: '#92400e' }}>
                    {c.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                  </ul>
                )}
              </div>
            </div>
            {c.randomisation_stats && (
              <RandomisationStatsCard stats={c.randomisation_stats} itemLabel="charts" />
            )}
          </div>
        ))}
      </div>

      {isED && hasCycles && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#374151', marginBottom: 10 }}>Manual Grading — Rubric</div>
          <EDGradingPanel batch={batch} onGraded={loadBatch} />
        </div>
      )}

      <div style={styles.actionRow}>
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
            {!isED && (
              <button style={styles.outlineBtn} title="Download per-coder scores, pass/fail, and feedback detail as Excel (.xlsx)"
                onClick={() => downloadBatchResultsExcel(batchId)}><Download size={15} /> Export Results (.xlsx)</button>
            )}
          </>
        )}
        {isOpen && closeBlockers.length === 0 && !confirmingClose && (
          <button style={{ ...styles.destructiveOutlineBtn, marginLeft: 'auto' }} onClick={() => setConfirmingClose(true)}>✕ {isDirectAssignment ? 'Close Assignment' : 'Close Batch'}</button>
        )}
        {isOpen && closeBlockers.length === 0 && confirmingClose && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>{isDirectAssignment ? 'Mark this assignment as complete?' : 'Lock all results?'}</span>
            <button style={{ ...styles.destructiveBtn, padding: '5px 12px', fontSize: 12 }} disabled={closing} onClick={handleClose}>
              {closing ? 'Closing…' : 'Yes, Close'}
            </button>
            <button style={{ ...styles.outlineBtn, padding: '5px 12px', fontSize: 12 }} onClick={() => setConfirmingClose(false)}>Cancel</button>
          </div>
        )}
      </div>

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
              {/* Selecting an existing coder brings their Emp ID with them, so a
                  variant spelling does not split their record. */}
              <div style={{ flex: 2 }}>
                <CoderPicker
                  value={row.name}
                  width="100%"
                  allowFreeText
                  placeholder="Coder name — search or type a new one"
                  onSelect={(name, empId) => setNewCoders(prev => prev.map((r, j) =>
                    j === i ? { ...r, name, emp_id: empId || r.emp_id } : r))}
                />
              </div>
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
                  if (res.skipped_duplicates.length) toast(`Skipped (name or emp ID already in this batch): ${res.skipped_duplicates.join(', ')}`, { icon: 'ℹ️' })
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

      <PracticeTokensSection batchId={batchId} />

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

// ── Practice Tokens Section ────────────────────────────────────────────────────

function PracticeTokensSection({ batchId }: { batchId: number }) {
  const [tokens, setTokens] = useState<{ coder_name: string; token: string; reused: boolean }[] | null>(null)
  const [existing, setExisting] = useState<{ session_id: number; coder_name: string; token: string; status: string; submitted_at: string | null }[]>([])
  const [loading, setLoading] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [reviewData, setReviewData] = useState<any>(null)
  const [reviewLoading, setReviewLoading] = useState(false)

  useEffect(() => {
    api.get(`/practicelab/practice-sessions/batch/${batchId}`).then(res => {
      setExisting(res.data.sessions || [])
      if ((res.data.sessions || []).length) setExpanded(true)
    }).catch(() => {})
  }, [batchId])

  async function generateTokens() {
    setLoading(true)
    try {
      const res = await api.post('/practicelab/practice-sessions/generate-tokens', {
        batch_id: batchId,
        show_results_to_coder: showResults,
      })
      setTokens(res.data.tokens)
      // Refresh existing list
      const listRes = await api.get(`/practicelab/practice-sessions/batch/${batchId}`)
      setExisting(listRes.data.sessions || [])
      setExpanded(true)
      toast.success(`${res.data.tokens.length} practice session${res.data.tokens.length !== 1 ? 's' : ''} generated`)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const status = e?.response?.status
      const msg = detail || (status ? `Server error ${status}` : e?.message || 'Failed to generate practice sessions')
      toast.error(msg, { duration: 8000 })
      console.error('Generate sessions error:', e?.response?.data, e?.message)
    }
    setLoading(false)
  }

  async function openReview(sessionId: number) {
    setReviewLoading(true)
    try {
      const res = await api.get(`/practicelab/practice-sessions/${sessionId}/review`)
      setReviewData({ ...res.data, session_id: sessionId })
    } catch {
      toast.error('Failed to load review')
    }
    setReviewLoading(false)
  }

  async function regrade(sessionId: number) {
    try {
      const res = await api.post(`/practicelab/practice-sessions/${sessionId}/regrade`)
      toast.success(`Re-graded ${res.data.regraded} chart${res.data.regraded !== 1 ? 's' : ''}`)
      if (reviewData?.session_id === sessionId) openReview(sessionId)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Re-grade failed')
    }
  }

  const statusColor = (s: string) => s === 'submitted' ? '#059669' : s === 'in_progress' ? '#d97706' : '#9ca3af'

  return (
    <div style={{ ...styles.cycleSection, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Key size={14} color="#7c3aed" />
          <span style={{ fontWeight: 700, fontSize: 13, color: '#374151' }}>Practice Sessions</span>
          {existing.length > 0 && (
            <span style={{ fontSize: 11, background: '#ede9fe', color: '#7c3aed', borderRadius: 20, padding: '2px 8px', fontWeight: 600 }}>
              {existing.length} session{existing.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6b7280', cursor: 'pointer' }}>
            <input type="checkbox" checked={showResults} onChange={e => setShowResults(e.target.checked)} />
            Show results to coder
          </label>
          <button
            onClick={generateTokens}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 700, opacity: loading ? 0.7 : 1 }}
          >
            <Key size={12} /> {loading ? 'Generating…' : existing.length ? 'Regenerate Sessions' : 'Generate Practice Sessions'}
          </button>
          {existing.length > 0 && (
            <button onClick={() => setExpanded(p => !p)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', fontSize: 12 }}>
              {expanded ? 'Hide' : 'Show'}
            </button>
          )}
        </div>
      </div>

      {expanded && existing.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {existing.map((s, i) => (
            <div key={s.session_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: i % 2 === 0 ? '#f9fafb' : '#fff', borderRadius: 8, border: '1px solid #f3f4f6' }}>
              <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{s.coder_name}</span>
              <code style={{ fontSize: 13, background: '#ede9fe', color: '#7c3aed', padding: '2px 8px', borderRadius: 6, letterSpacing: 1 }}>{s.token}</code>
              <button
                onClick={() => { navigator.clipboard.writeText(s.token); toast.success('Access code copied') }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 4 }}
                title="Copy access code"
              ><Copy size={13} /></button>
              <span style={{ fontSize: 11, fontWeight: 700, color: statusColor(s.status), width: 70, textAlign: 'center' as const }}>
                {s.status === 'submitted' ? '✓ Submitted' : s.status === 'in_progress' ? 'In Progress' : 'Pending'}
              </span>
              {s.status === 'submitted' && (
                <>
                  <button
                    onClick={() => openReview(s.session_id)}
                    style={{ background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', color: '#7c3aed', padding: '3px 8px', fontSize: 12 }}
                  >
                    <Eye size={12} /> Review
                  </button>
                  <button
                    onClick={() => regrade(s.session_id)}
                    title="Re-grade after uploading answer keys"
                    style={{ background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', color: '#059669', padding: '3px 8px', fontSize: 12 }}
                  >
                    ↻ Re-grade
                  </button>
                  <button
                    onClick={() => downloadSessionCoderReportPdf(s.session_id)}
                    title="Download this coder's report for this session only"
                    style={{ background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', color: '#4f46e5', padding: '3px 8px', fontSize: 12 }}
                  >
                    <Download size={12} /> Report
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {tokens && !expanded && (
        <div style={{ fontSize: 12, color: '#059669' }}>Practice sessions generated — click Show to see them.</div>
      )}

      {/* Review modal */}
      {reviewData && (
        <ReviewModal
          reviewData={reviewData}
          onClose={() => setReviewData(null)}
          onRefresh={() => openReview(reviewData.session_id)}
        />
      )}
    </div>
  )
}

// ── Review Modal (IP/OP codes + E&D rubric scoring) ───────────────────────────

const ED_RUBRIC_ITEMS = [
  { key: 'review_pass', label: 'Review', points: 30 },
  { key: 'research_coding_pass', label: 'Research — Coding', points: 10 },
  { key: 'research_payer_pass', label: 'Research — Payer', points: 10 },
  { key: 'research_nuances_pass', label: 'Research — Nuances', points: 10 },
  { key: 'resolution_pass', label: 'Resolution', points: 35 },
]
const RATIONALE_SCORES: Record<string, number> = { acceptable: 5, needs_improvement: 3, not_acceptable: 0 }

function isEDSpecialty(sp: string) {
  const s = sp.toUpperCase()
  return s.includes('EDIT') || s.includes('DENIAL')
}

function ReviewModal({ reviewData, onClose, onRefresh }: { reviewData: any; onClose: () => void; onRefresh: () => void }) {
  const ed = isEDSpecialty(reviewData.specialty || '')
  const [rubrics, setRubrics] = useState<Record<number, any>>({})
  const [scoring, setScoring] = useState<number | null>(null)
  const [drgSaving, setDrgSaving] = useState<number | null>(null)

  function initRubric(chartId: number, c: any) {
    setRubrics(prev => ({
      ...prev,
      [chartId]: prev[chartId] || {
        review_pass: c.ed_review_pass ?? false,
        research_coding_pass: c.ed_research_coding_pass ?? false,
        research_payer_pass: c.ed_research_payer_pass ?? false,
        research_nuances_pass: c.ed_research_nuances_pass ?? false,
        resolution_pass: c.ed_resolution_pass ?? false,
        rationale_tier: c.ed_rationale_tier || 'not_acceptable',
        trainer_note: c.ed_trainer_note || '',
      }
    }))
  }

  function calcScore(r: any) {
    const base = ED_RUBRIC_ITEMS.reduce((s, i) => s + (r[i.key] ? i.points : 0), 0)
    return base + (RATIONALE_SCORES[r.rationale_tier] ?? 0)
  }

  async function submitDrgReview(sessionId: number, chartId: number, drgError: boolean) {
    setDrgSaving(chartId)
    try {
      await api.post(`/practicelab/practice-sessions/${sessionId}/chart/${chartId}/drg-review`, {
        drg_error: drgError,
        reviewed_by: 'Trainer',
      })
      toast.success(drgError ? 'DRG marked as error — score set to 0' : 'DRG confirmed correct — full DRG score applied')
      onRefresh()
    } catch {
      toast.error('Failed to save DRG review')
    }
    setDrgSaving(null)
  }

  async function submitRubric(sessionId: number, chartId: number) {
    const r = rubrics[chartId]
    if (!r) return
    setScoring(chartId)
    try {
      await api.post(`/practicelab/practice-sessions/${sessionId}/chart/${chartId}/score-ed`, {
        ...r, graded_by: 'Trainer',
      })
      toast.success('Score saved')
      onRefresh()
    } catch {
      toast.error('Failed to save score')
    }
    setScoring(null)
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#fff', borderRadius: 16, padding: 28, maxWidth: 820, width: '94%', maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 8px 40px rgba(0,0,0,0.18)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>{reviewData.coder_name} — Practice Submission</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>{reviewData.specialty} · Submitted {reviewData.submitted_at ? new Date(reviewData.submitted_at).toLocaleString() : '—'}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: '#6b7280' }}>✕</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {(reviewData.charts || []).map((c: any, i: number) => {
            if (ed) {
              const r = rubrics[c.chart_id]
              if (!r) initRubric(c.chart_id, c)
              const liveScore = r ? calcScore(r) : (c.total_score ?? 0)
              const livePass = liveScore >= 80

              return (
                <div key={i} style={{ border: '1px solid #e5e7eb', borderRadius: 12, overflow: 'hidden' }}>
                  {/* chart header */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>{c.chart_number}</span>
                    {c.ed_scored && (
                      <>
                        <span style={{ fontWeight: 700, fontSize: 13, color: (c.total_score ?? 0) >= 80 ? '#059669' : '#dc2626' }}>{c.total_score}%</span>
                        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: c.pass_fail === 'PASS' ? '#d1fae5' : '#fee2e2', color: c.pass_fail === 'PASS' ? '#059669' : '#dc2626' }}>{c.pass_fail}</span>
                      </>
                    )}
                    {!c.ed_scored && <span style={{ fontSize: 11, background: '#fef3c7', color: '#b45309', borderRadius: 6, padding: '2px 8px' }}>Pending Score</span>}
                    {c.flagged && <span style={{ fontSize: 11, background: '#fef9c3', color: '#b45309', borderRadius: 6, padding: '1px 6px' }}>Flagged</span>}
                  </div>

                  {/* coder responses */}
                  <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {[
                      { label: 'Review', val: c.ed_review },
                      { label: 'Research', val: c.ed_research },
                      { label: 'Resolution', val: c.ed_resolution },
                      { label: 'Final Rationale', val: c.ed_rationale },
                    ].map(({ label, val }) => (
                      <div key={label}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, marginBottom: 3 }}>{label}</div>
                        <div style={{ fontSize: 13, color: '#111', background: '#f9fafb', borderRadius: 6, padding: '8px 10px', lineHeight: 1.5 }}>{val || <span style={{ color: '#d1d5db' }}>Not answered</span>}</div>
                      </div>
                    ))}
                    {c.coder_notes && (
                      <div style={{ fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>Coder notes: {c.coder_notes}</div>
                    )}

                    {/* Rubric scoring panel */}
                    {r && (
                      <div style={{ border: '1.5px solid #e5e7eb', borderRadius: 10, padding: '12px 14px', marginTop: 4, background: '#fafafa' }}>
                        <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>
                          Rubric Score — <span style={{ color: livePass ? '#059669' : '#dc2626' }}>{liveScore} pts ({livePass ? 'PASS' : 'FAIL'})</span>
                        </div>
                        {ED_RUBRIC_ITEMS.map(item => (
                          <label key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, cursor: 'pointer', fontSize: 13 }}>
                            <input
                              type="checkbox"
                              checked={r[item.key] || false}
                              onChange={e => setRubrics(prev => ({ ...prev, [c.chart_id]: { ...prev[c.chart_id], [item.key]: e.target.checked } }))}
                            />
                            <span style={{ flex: 1 }}>{item.label}</span>
                            <span style={{ fontSize: 11, color: '#9ca3af' }}>{item.points} pts</span>
                          </label>
                        ))}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
                          <span style={{ fontSize: 13, fontWeight: 600, minWidth: 80 }}>Rationale:</span>
                          <select
                            value={r.rationale_tier}
                            onChange={e => setRubrics(prev => ({ ...prev, [c.chart_id]: { ...prev[c.chart_id], rationale_tier: e.target.value } }))}
                            style={{ padding: '5px 8px', borderRadius: 6, border: '1px solid #e5e7eb', fontSize: 13, cursor: 'pointer' }}
                          >
                            <option value="acceptable">Acceptable (5 pts)</option>
                            <option value="needs_improvement">Needs Improvement (3 pts)</option>
                            <option value="not_acceptable">Not Acceptable (0 pts)</option>
                          </select>
                        </div>
                        <div style={{ marginTop: 8 }}>
                          <input
                            style={{ width: '100%', padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, boxSizing: 'border-box' as const }}
                            placeholder="Trainer note (optional)"
                            value={r.trainer_note}
                            onChange={e => setRubrics(prev => ({ ...prev, [c.chart_id]: { ...prev[c.chart_id], trainer_note: e.target.value } }))}
                          />
                        </div>
                        <button
                          onClick={() => submitRubric(reviewData.session_id, c.chart_id)}
                          disabled={scoring === c.chart_id}
                          style={{ marginTop: 10, padding: '7px 18px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13, opacity: scoring === c.chart_id ? 0.7 : 1 }}
                        >
                          {scoring === c.chart_id ? 'Saving…' : c.ed_scored ? 'Update Score' : 'Save Score'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )
            }

            // IP / OP view
            const noAK = c.total_score === null && c.pass_fail === null
            const hasDRG = c.drg_flag && !noAK
            const drgDone = c.drg_reviewed
            const borderColor = noAK ? '#fed7aa' : hasDRG && !drgDone ? '#fca5a5' : '#e5e7eb'
            const bg = noAK ? '#fffbeb' : hasDRG && !drgDone ? '#fff5f5' : '#fff'
            return (
              <div key={i} style={{ border: `1px solid ${borderColor}`, borderRadius: 10, padding: '12px 16px', background: bg }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, fontSize: 14 }}>{c.chart_number}</span>
                  {!noAK && c.total_score !== null && (
                    <span style={{ fontWeight: 700, fontSize: 13, color: c.total_score >= 80 ? '#059669' : '#dc2626' }}>{c.total_score}%</span>
                  )}
                  {!noAK && c.pass_fail && (
                    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: c.pass_fail === 'PASS' ? '#d1fae5' : '#fee2e2', color: c.pass_fail === 'PASS' ? '#059669' : '#dc2626' }}>{c.pass_fail}</span>
                  )}
                  {noAK && <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#fef3c7', color: '#b45309' }}>⚠ No Answer Key</span>}
                  {hasDRG && !drgDone && <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#fee2e2', color: '#dc2626' }}>⚑ DRG Review Needed</span>}
                  {hasDRG && drgDone && <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#d1fae5', color: '#059669' }}>✓ DRG Reviewed{c.drg_override ? ` — ${c.drg_override}` : ''}</span>}
                  {c.flagged && <span style={{ fontSize: 11, background: '#fef9c3', color: '#b45309', borderRadius: 6, padding: '1px 6px' }}>Flagged</span>}
                </div>
                {noAK ? (
                  <div style={{ fontSize: 12, color: '#92400e' }}>
                    <div>Coder submitted: PDx <code>{c.pdx_submitted || '—'}</code> — no answer key uploaded for this chart, grading was skipped.</div>
                    <div style={{ marginTop: 6, fontSize: 11, color: '#78350f' }}>Upload an answer key for this chart, then use the <strong>↻ Re-grade</strong> button on the session row to rescore.</div>
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 12, color: '#374151' }}>
                      <span style={{ color: '#6b7280' }}>PDx submitted:</span> <code>{c.pdx_submitted || '—'}</code>
                      {' '}<span style={{ color: '#6b7280' }}>· AK:</span> <code>{c.pdx_answer_key || '—'}</code>
                      {' '}{c.pdx_correct === true ? <span style={{ color: '#059669' }}>✓</span> : c.pdx_correct === false ? <span style={{ color: '#dc2626' }}>✗</span> : null}
                    </div>
                    {c.feedback?.length > 0 && (
                      <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {c.feedback.map((fb: any, j: number) => (
                          <div key={j} style={{ fontSize: 11, color: '#6b7280' }}>
                            • [{fb.section}] {fb.issue} — submitted: <code>{fb.coder_code || '—'}</code> | expected: <code>{fb.ak_code || '—'}</code>
                          </div>
                        ))}
                      </div>
                    )}
                    {hasDRG && (
                      <div style={{ marginTop: 10, padding: '10px 12px', background: drgDone ? '#f0fdf4' : '#fff1f2', borderRadius: 8, border: `1px solid ${drgDone ? '#bbf7d0' : '#fecaca'}` }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: drgDone ? '#059669' : '#dc2626', marginBottom: 6 }}>
                          {drgDone ? '✓ DRG Reviewed' : '⚑ DRG Review Required'}
                        </div>
                        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>
                          {drgDone
                            ? `Reviewed by Trainer${c.drg_override ? ` — confirmed DRG/PDx: ${c.drg_override}` : ' — no override needed'}`
                            : 'This chart has a DRG flag. Confirm the submitted code is acceptable or enter the correct DRG/PDx code below.'}
                        </div>
                        {!drgDone && (
                          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            <div style={{ fontSize: 11, color: '#6b7280', marginRight: 4 }}>DRG Change?</div>
                            <button
                              style={{ padding: '6px 18px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: drgSaving === c.chart_id ? 'wait' : 'pointer', opacity: drgSaving === c.chart_id ? 0.7 : 1 }}
                              disabled={drgSaving === c.chart_id}
                              onClick={() => submitDrgReview(reviewData.session_id, c.chart_id, true)}
                            >
                              Yes — DRG Error (0 pts)
                            </button>
                            <button
                              style={{ padding: '6px 18px', background: '#059669', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: drgSaving === c.chart_id ? 'wait' : 'pointer', opacity: drgSaving === c.chart_id ? 0.7 : 1 }}
                              disabled={drgSaving === c.chart_id}
                              onClick={() => submitDrgReview(reviewData.session_id, c.chart_id, false)}
                            >
                              No — DRG Correct (full pts)
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
                {c.coder_notes && (
                  <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>Notes: {c.coder_notes}</div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
