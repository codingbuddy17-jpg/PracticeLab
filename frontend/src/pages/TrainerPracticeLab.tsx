import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus, Upload, Download, FileCheck, BarChart2, Key, Loader, Settings, Search, CheckSquare, Square } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import { getSelfPracticeQueue, releaseSelfPractice, standaloneGrade } from '../api'
import {
  listBatches, createBatch, runAllocation, closeBatch, forceCloseBatch, addBatchNote,
  getPoolPreview, searchChartsForBatch, downloadAnswerKeyTemplate,
  uploadAnswerKeys, getBatch, downloadBatchExcel, downloadCycleExcel, gradeSubmissions,
  getDRGReview, submitDRGDecision, getBatchResults, downloadBatchResultsExcel,
  getAnswerKeyStatus, getPLAnalyticsOverview,
  getPLAnalyticsBySpecialty, getPLAnalyticsByChart, getPLAnalyticsByBatch, getCoderTrend,
  getPLAnalyticsByCategory, getPLChartTeachingValue, getPLCoderMatrix,
  downloadCoderListTemplate, parseCoderList,
  getScoringConfigs, updateScoringConfig,
  getBatchInsights,
} from '../api'
import { SPECIALTY_COLORS } from '../theme'

type View = 'home' | 'answer-keys' | 'create-batch' | 'batch-detail' | 'drg-review' | 'results' | 'analytics' | 'scoring-config' | 'self-practice'

const SPECIALTIES = ['IP-DRG', 'ED Facility', 'ED Profee', 'SDS', 'Edits', 'Denials', 'Ancillary', 'E/M']
const DIFFICULTIES = ['Beginner', 'Intermediate', 'Advanced']

function trainerName() {
  return localStorage.getItem('trainer_name') || 'Trainer'
}

export function TrainerPracticeLab() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('home')
  const [batches, setBatches] = useState<any[]>([])
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [overview, setOverview] = useState<any>(null)
  const [scoringCfg, setScoringCfg] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadHome()
    getScoringConfigs().then(setScoringCfg).catch(() => { /* non-critical, batch creation falls back to defaults */ })
  }, [])

  async function loadHome() {
    setLoading(true)
    try {
      const [b, ov] = await Promise.all([listBatches(), getPLAnalyticsOverview()])
      setBatches(b)
      setOverview(ov)
    } catch { toast.error('Failed to load batches') } finally {
      setLoading(false)
    }
  }

  function openBatch(id: number) {
    setSelectedBatchId(id)
    setView('batch-detail')
  }

  const statusColor = (s: string) => ({
    Open: '#2563eb', Closed: '#16a34a',
  }[s] || '#6b7280')

  return (
    <div style={styles.container}>
      {/* Top bar */}
      <div style={styles.topBar}>
        <div style={styles.topLeft}>
          <button style={styles.backBtn} onClick={() => navigate('/trainer')}>
            <ChevronLeft size={18} /> Trainer Home
          </button>
          <span style={styles.title}>PracticeLab</span>
        </div>
        <div style={styles.topRight}>
          {view !== 'home' && (
            <button style={styles.navBtn} onClick={() => { setView('home'); loadHome() }}>
              ← All Batches
            </button>
          )}
          {view === 'home' && (
            <>
              <button style={styles.navBtn} onClick={() => setView('analytics')}>
                <BarChart2 size={15} /> Analytics
              </button>
              <button style={styles.navBtn} onClick={() => setView('scoring-config')}>
                <Settings size={15} /> Scoring Config
              </button>
              <button style={styles.navBtn} onClick={() => setView('answer-keys')}>
                <Key size={15} /> Answer Keys
              </button>
              <button style={styles.navBtn} onClick={() => setView('self-practice')}>
                <FileCheck size={15} /> Self Practice
              </button>
              <button style={{ ...styles.navBtn, background: '#0f766e', color: '#fff', border: 'none' }}
                onClick={() => setView('create-batch')}>
                <Plus size={15} /> New Batch
              </button>
            </>
          )}
        </div>
      </div>

      <div style={styles.content}>
        {view === 'home' && (
          <HomeView
            batches={batches} overview={overview} loading={loading}
            onOpen={openBatch} statusColor={statusColor}
            onCreateBatch={() => setView('create-batch')}
          />
        )}
        {view === 'answer-keys' && <AnswerKeysView />}
        {view === 'create-batch' && (
          <CreateBatchView
            onCreated={(id) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }}
            scoringCfg={scoringCfg}
          />
        )}
        {view === 'batch-detail' && selectedBatchId && (
          <BatchDetailView
            batchId={selectedBatchId}
            onDRGReview={() => setView('drg-review')}
            onResults={() => setView('results')}
          />
        )}
        {view === 'drg-review' && selectedBatchId && (
          <DRGReviewView batchId={selectedBatchId} onDone={() => setView('batch-detail')} />
        )}
        {view === 'results' && selectedBatchId && (
          <ResultsView batchId={selectedBatchId} />
        )}
        {view === 'analytics' && <PLAnalyticsView />}
        {view === 'scoring-config' && <ScoringConfigView />}
        {view === 'self-practice' && <SelfPracticeInlineView />}
      </div>
    </div>
  )
}

// ── Home ──────────────────────────────────────────────────────────────────────

function HomeView({ batches, overview, loading, onOpen, statusColor, onCreateBatch }: any) {
  if (loading) return <div style={styles.center}><Loader size={24} style={{ animation: 'spin 1s linear infinite' }} /></div>
  return (
    <div>
      {/* Overview stats */}
      {overview && (
        <div style={styles.statsRow}>
          {[
            { label: 'Total Batches', value: overview.total_batches },
            { label: 'Open', value: overview.open_batches ?? overview.total_batches - overview.complete_batches },
            { label: 'Closed', value: overview.complete_batches },
            { label: 'Total Graded', value: overview.total_graded },
            { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%` },
          ].map(s => (
            <div key={s.label} style={styles.statCard}>
              <div style={styles.statValue}>{s.value}</div>
              <div style={styles.statLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Batches</span>
      </div>

      {batches.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={40} color="#d1d5db" />
          <p>No batches yet.</p>
          <button style={styles.primaryBtn} onClick={onCreateBatch}>Create your first batch</button>
        </div>
      ) : (
        <div style={styles.batchList}>
          {batches.map((b: any) => {
            const sc = SPECIALTY_COLORS[b.specialty as keyof typeof SPECIALTY_COLORS]
            return (
              <div key={b.id} style={styles.batchRow} onClick={() => onOpen(b.id)}>
                <div style={{ ...styles.batchAccent, background: sc?.bg || '#6b7280' }} />
                <div style={styles.batchInfo}>
                  <div style={styles.batchName}>{b.name}</div>
                  <div style={styles.batchMeta}>
                    <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151' }}>
                      {b.specialty}
                    </span>
                    <span style={styles.metaText}>{b.coder_count} coders</span>
                    <span style={styles.metaText}>{b.allocation_cycles ?? 0} cycle{b.allocation_cycles !== 1 ? 's' : ''}</span>
                    {b.days_open != null && <span style={{ ...styles.metaText, color: b.days_open > 14 ? '#d97706' : '#6b7280' }}>open {b.days_open}d</span>}
                    <span style={styles.metaText}>by {b.created_by}</span>
                    {b.force_closed && <span style={{ ...styles.metaText, color: '#dc2626', fontWeight: 700 }}>force-closed</span>}
                  </div>
                </div>
                <span style={{ ...styles.statusPill, color: statusColor(b.status), borderColor: statusColor(b.status) }}>
                  {b.status}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Answer Keys ───────────────────────────────────────────────────────────────

function AnswerKeysView() {
  const [status, setStatus] = useState<any>(null)
  const [specialty, setSpecialty] = useState('IP-DRG')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadStatus() }, [specialty])

  async function loadStatus() {
    try { setStatus(await getAnswerKeyStatus(specialty)) } catch { toast.error('Could not load answer key status') }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const isIP = specialty === 'IP-DRG'
      const res = await uploadAnswerKeys(file, isIP ? 'IP' : 'OP', trainerName())
      if (res.stored.length) toast.success(`Stored: ${res.stored.join(', ')}`)
      if (res.skipped_duplicates.length) toast(`Skipped (already exist): ${res.skipped_duplicates.join(', ')}`, { icon: '⚠️' })
      if (res.not_found.length) toast.error(`Chart numbers not found: ${res.not_found.join(', ')}`)
      loadStatus()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const isIP = specialty === 'IP-DRG'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Answer Keys</span>
      </div>
      <p style={styles.helpText}>
        Answer keys are stored permanently per chart. Once stored, only a master admin can delete them.
        Keys are reused across all batches automatically.
      </p>

      <div style={styles.row}>
        <div>
          <label style={styles.label}>Specialty type</label>
          <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value)}>
            {SPECIALTIES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {status && (
        <div style={styles.statsRow}>
          <div style={styles.statCard}>
            <div style={styles.statValue}>{status.total_charts}</div>
            <div style={styles.statLabel}>Total Charts</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: '#16a34a' }}>{status.with_answer_key}</div>
            <div style={styles.statLabel}>Have Answer Key</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: '#dc2626' }}>{status.without_answer_key}</div>
            <div style={styles.statLabel}>Missing Key</div>
          </div>
        </div>
      )}

      <div style={styles.actionRow}>
        <button style={styles.outlineBtn} onClick={() => downloadAnswerKeyTemplate(isIP ? 'IP' : 'OP')}>
          <Download size={15} /> Download Blank Template ({isIP ? 'IP' : 'OP'})
        </button>
        <label style={uploading ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
          {uploading ? <><Loader size={14} /> Uploading...</> : <><Upload size={15} /> Upload Filled Key</>}
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleUpload} disabled={uploading} />
        </label>
      </div>

      <div style={styles.infoBox}>
        <strong>How it works:</strong>
        <ol style={{ margin: '8px 0 0 0', paddingLeft: 20, lineHeight: 1.8, fontSize: 13 }}>
          <li>Download the blank template for your specialty type</li>
          <li>Fill one row per chart — Chart_Number must match exactly what's in PracticeLab</li>
          <li>Upload the filled template — keys are stored permanently</li>
          <li>Duplicate chart numbers are skipped with a warning</li>
        </ol>
      </div>
    </div>
  )
}

// ── Create Batch ──────────────────────────────────────────────────────────────

function CreateBatchView({ onCreated, scoringCfg }: { onCreated: (id: number) => void; scoringCfg?: any }) {
  const [form, setForm] = useState({
    name: '', specialty: 'IP-DRG', categories: '', difficulties: [] as string[],
    charts_per_coder: 5,
    use_weighted: true,
    use_dpo: false,
  })
  const [coders, setCoders] = useState<{ name: string; emp_id: string }[]>([])
  const [coderMode, setCoderMode] = useState<'quick' | 'upload'>('quick')
  const [quickRow, setQuickRow] = useState({ name: '', emp_id: '' })
  const [pool, setPool] = useState<{ total_matching: number; with_answer_key: number } | null>(null)
  const [creating, setCreating] = useState(false)
  const [parsing, setParsing] = useState(false)
  const coderFileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const t = setTimeout(loadPool, 400)
    return () => clearTimeout(t)
  }, [form.specialty, form.categories, form.difficulties])

  async function loadPool() {
    try {
      const cats = form.categories.split(',').map(s => s.trim()).filter(Boolean).join(',')
      const diffs = form.difficulties.join(',')
      setPool(await getPoolPreview(form.specialty, cats || undefined, diffs || undefined))
    } catch { setPool(null) }
  }

  function toggleDifficulty(d: string) {
    setForm(f => ({
      ...f,
      difficulties: f.difficulties.includes(d) ? f.difficulties.filter(x => x !== d) : [...f.difficulties, d],
    }))
  }

  async function handleCoderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setParsing(true)
    try {
      const parsed = await parseCoderList(file)
      setCoders(parsed)
      toast.success(`${parsed.length} coder(s) loaded`)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to parse coder list')
    } finally {
      setParsing(false)
      if (coderFileRef.current) coderFileRef.current.value = ''
    }
  }

  function addQuickCoder() {
    const name = quickRow.name.trim()
    const emp_id = quickRow.emp_id.trim()
    if (!name || !emp_id) return toast.error('Enter both name and Emp ID')
    if (coders.some(c => c.emp_id === emp_id)) return toast.error('Emp ID already added')
    setCoders(prev => [...prev, { name, emp_id }])
    setQuickRow({ name: '', emp_id: '' })
  }

  async function handleCreate() {
    if (!form.name.trim()) return toast.error('Batch name is required')
    if (coders.length === 0) return toast.error('Add at least one coder')

    setCreating(true)
    try {
      const res = await createBatch({
        name: form.name.trim(),
        specialty: form.specialty,
        categories: form.categories.split(',').map(s => s.trim()).filter(Boolean),
        difficulties: form.difficulties,
        charts_per_coder: form.charts_per_coder,
        coders,
        created_by: trainerName(),
        use_weighted: form.use_weighted,
        use_dpo: form.use_dpo,
      })
      if (res.warning) toast(res.warning, { icon: '⚠️', duration: 5000 })
      toast.success('Batch created — run an allocation cycle to assign charts')
      onCreated(res.batch_id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create batch')
    } finally { setCreating(false) }
  }

  const isIP = ['IP-DRG'].includes(form.specialty)
  const activeCfg = scoringCfg ? (isIP ? scoringCfg.IP : scoringCfg.OP) : null

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Create New Batch</div>
      <div style={styles.infoBox}>
        Batch stays <strong>Open</strong> until you close it. Charts are assigned through allocation cycles — run one now, or more later as the practice phase progresses.
      </div>

      <div style={styles.formGrid}>
        <div style={styles.formGroup}>
          <label style={styles.label}>Batch Name *</label>
          <input style={styles.input} value={form.name}
            placeholder="e.g. June IP Assessment"
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Specialty *</label>
          <select style={styles.select} value={form.specialty}
            onChange={e => setForm(f => ({ ...f, specialty: e.target.value }))}>
            {SPECIALTIES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Default Pool — Category Filter <span style={styles.hint}>(comma-separated)</span></label>
          <input style={styles.input} value={form.categories}
            placeholder="e.g. Sepsis, Cardiac, Trauma"
            onChange={e => setForm(f => ({ ...f, categories: e.target.value }))} />
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Default Pool — Difficulty Filter</label>
          <div style={styles.chipRow}>
            {DIFFICULTIES.map(d => (
              <button key={d}
                style={form.difficulties.includes(d) ? styles.chipActive : styles.chip}
                onClick={() => toggleDifficulty(d)}>{d}</button>
            ))}
            <span style={styles.hint}>None = all</span>
          </div>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Default Charts per Coder <span style={styles.hint}>(overridable per cycle)</span></label>
          <input type="number" min={1} max={20} style={{ ...styles.input, width: 80 }}
            value={form.charts_per_coder}
            onChange={e => setForm(f => ({ ...f, charts_per_coder: parseInt(e.target.value) || 1 }))} />
        </div>
      </div>

      {pool && (
        <div style={styles.infoBox}>
          <strong>Pool preview:</strong> {pool.total_matching} matching charts · {pool.with_answer_key} have answer keys
          {pool.with_answer_key === 0 && <span style={{ color: '#dc2626', marginLeft: 8 }}>⚠ Upload answer keys before running allocation.</span>}
        </div>
      )}

      {/* Scoring method */}
      <div style={styles.formGroup}>
        <label style={styles.label}>Scoring Method</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={styles.methodOption}>
            <input type="checkbox" checked={form.use_weighted}
              disabled={activeCfg ? activeCfg.weighted_enabled === false : false}
              onChange={e => setForm(f => ({ ...f, use_weighted: e.target.checked }))} />
            <div>
              <div style={styles.methodLabel}>Weighted Scoring <span style={styles.methodBadge}>Primary · Pass/Fail</span></div>
              <div style={styles.methodDesc}>Category importance (PDx / SDx / PCS / DRG weights) — drives the official pass/fail verdict</div>
            </div>
          </label>
          <label style={styles.methodOption}>
            <input type="checkbox" checked={form.use_dpo}
              disabled={activeCfg ? activeCfg.dpo_enabled === false : false}
              onChange={e => setForm(f => ({ ...f, use_dpo: e.target.checked }))} />
            <div>
              <div style={styles.methodLabel}>DPO Accuracy <span style={{ ...styles.methodBadge, background: '#dbeafe', color: '#1d4ed8' }}>Supplementary</span></div>
              <div style={styles.methodDesc}>Defect rate per code opportunity — shows Dx, POA and procedure accuracy % per coder</div>
            </div>
          </label>
          {!form.use_weighted && !form.use_dpo && (
            <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must be selected</div>
          )}
        </div>
      </div>

      {/* Coder list */}
      <div style={styles.formGroup}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <label style={styles.label}>Coders *</label>
          <div style={styles.modeToggle}>
            <button style={coderMode === 'quick' ? styles.modeTabActive : styles.modeTab}
              onClick={() => setCoderMode('quick')}>Quick Add</button>
            <button style={coderMode === 'upload' ? styles.modeTabActive : styles.modeTab}
              onClick={() => setCoderMode('upload')}>Upload List</button>
          </div>
        </div>

        {coderMode === 'quick' && (
          <div style={styles.quickAddRow}>
            <input style={{ ...styles.input, flex: 1 }} placeholder="Coder name"
              value={quickRow.name} onChange={e => setQuickRow(r => ({ ...r, name: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && addQuickCoder()} />
            <input style={{ ...styles.input, width: 130 }} placeholder="Emp ID"
              value={quickRow.emp_id} onChange={e => setQuickRow(r => ({ ...r, emp_id: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && addQuickCoder()} />
            <button style={styles.outlineBtn} onClick={addQuickCoder}>+ Add</button>
          </div>
        )}

        {coderMode === 'upload' && (
          <div style={styles.actionRow}>
            <button style={styles.outlineBtn} onClick={downloadCoderListTemplate}>
              <Download size={15} /> Download Template
            </button>
            <label style={parsing ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
              {parsing ? <><Loader size={14} /> Parsing...</> : <><Upload size={15} /> Upload Filled List</>}
              <input ref={coderFileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                onChange={handleCoderUpload} disabled={parsing} />
            </label>
          </div>
        )}

        {coders.length > 0 && (
          <>
            <div style={styles.coderTable}>
              <div style={styles.coderTableHeader}>
                <span>Coder Name</span><span>Emp ID</span><span></span>
              </div>
              {coders.map((c, i) => (
                <div key={i} style={styles.coderTableRow}>
                  <span>{c.name}</span>
                  <span style={{ fontWeight: 700, color: '#0f766e' }}>{c.emp_id}</span>
                  <button style={styles.removeCoder} onClick={() => setCoders(prev => prev.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={styles.hint}>{coders.length} coder{coders.length !== 1 ? 's' : ''} ready</span>
              <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '4px 10px', color: '#dc2626', borderColor: '#fca5a5' }}
                onClick={() => setCoders([])}>Clear all</button>
            </div>
          </>
        )}
      </div>

      <button style={creating ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
        disabled={creating} onClick={handleCreate}>
        {creating ? <><Loader size={14} /> Creating...</> : 'Open Batch'}
      </button>
    </div>
  )
}

// ── Batch Detail ──────────────────────────────────────────────────────────────

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
              <div style={styles.chartPickerListHeader}>
                <span>Chart</span><span>Category</span><span>Difficulty</span><span></span>
              </div>
              {chartSearchResults.map(c => {
                const selected = selectedChartIds.has(c.id)
                return (
                  <div key={c.id} style={{ ...styles.chartPickerRow, background: selected ? '#eef2ff' : '#fff' }}
                    onClick={() => toggleChart(c.id)}>
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
        <button style={running ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
          disabled={running} onClick={handleRun}>
          {running ? <><Loader size={14} /> Running…</> : `▶ Run Cycle ${nextCycle}`}
        </button>
      </div>
    </div>
  )
}

function BatchDetailView({ batchId, onDRGReview, onResults }: any) {
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
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' as const }}>
        <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151', fontSize: 13 }}>
          {batch.specialty}
        </span>
        <span style={styles.sectionTitle}>{batch.name}</span>
        <span style={{ fontSize: 12, fontWeight: 700, padding: '3px 12px', borderRadius: 20, border: '1.5px solid',
          color: isOpen ? '#2563eb' : '#16a34a', borderColor: isOpen ? '#2563eb' : '#16a34a' }}>
          {batch.status}
        </span>
        {isOpen && batch.days_open != null && (
          <span style={{ fontSize: 12, color: batch.days_open > 14 ? '#d97706' : '#6b7280' }}>
            {batch.days_open} day{batch.days_open !== 1 ? 's' : ''} open
          </span>
        )}
        {batch.force_closed && (
          <span style={{ fontSize: 11, background: '#fee2e2', color: '#dc2626', padding: '2px 10px', borderRadius: 20, fontWeight: 700 }}>
            Force-closed
          </span>
        )}
        <span style={{ fontSize: 12, color: '#9ca3af' }}>by {batch.created_by} · {new Date(batch.created_at).toLocaleDateString()}</span>
      </div>

      {batch.force_close_reason && (
        <div style={styles.warnBox}>Force-close reason: {batch.force_close_reason}</div>
      )}

      {/* Allocation cycles section */}
      <div style={styles.cycleSection}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>
            Allocation Cycles ({batch.allocation_cycles?.length || 0})
          </span>
          {isOpen && (
            <button style={{ ...styles.primaryBtn, background: '#4f46e5' }}
              onClick={() => setShowAllocationPanel(p => !p)}>
              {showAllocationPanel ? '✕ Cancel' : '▶ Run New Cycle'}
            </button>
          )}
        </div>

        {showAllocationPanel && isOpen && (
          <AllocationPanel batch={batch} onDone={() => { setShowAllocationPanel(false); loadBatch() }} />
        )}

        {(batch.allocation_cycles || []).length === 0 && !showAllocationPanel && (
          <div style={{ fontSize: 13, color: '#9ca3af', padding: '12px 0' }}>No cycles yet — run the first allocation to assign charts.</div>
        )}

        {(batch.allocation_cycles || []).map((c: any) => (
          <div key={c.id} style={styles.cycleRow}>
            <div style={styles.cycleBadge}>Cycle {c.cycle_number}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {c.charts_per_coder} charts/coder · {c.assigned_count} assignments
              </div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>
                by {c.run_by} on {new Date(c.run_at).toLocaleDateString()}
                {c.notes && <span style={{ marginLeft: 8, color: '#6b7280' }}>— {c.notes}</span>}
              </div>
            </div>
            <button style={styles.outlineBtn} onClick={() => downloadCycleExcel(batchId, c.id)}>
              <Download size={13} /> Cycle {c.cycle_number} Sheets
            </button>
          </div>
        ))}

        {(batch.allocation_cycles || []).length > 0 && (
          <div style={{ marginTop: 6 }}>
            <button style={{ ...styles.outlineBtn, fontSize: 12 }} onClick={() => downloadBatchExcel(batchId)}>
              <Download size={13} /> All Cycles (ZIP)
            </button>
          </div>
        )}
      </div>

      {/* Grade uploads + results */}
      <div style={styles.actionRow}>
        {isOpen && (
          <label style={grading ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
            {grading ? <><Loader size={14} /> Grading...</> : <><Upload size={15} /> Upload Returned Sheets</>}
            <input ref={fileRef} type="file" accept=".xlsx" multiple style={{ display: 'none' }}
              onChange={handleGradeUpload} disabled={grading} />
          </label>
        )}
        {hasResults && (
          <>
            {pendingDRG && (
              <button style={{ ...styles.primaryBtn, background: '#d97706' }} onClick={onDRGReview}>
                DRG Review Required
              </button>
            )}
            <button style={styles.outlineBtn} onClick={onResults}>
              <BarChart2 size={15} /> View Results
            </button>
            <button style={{ ...styles.outlineBtn, color: '#4f46e5', borderColor: '#a5b4fc' }}
              onClick={() => {
                if (insights) { setShowInsights(s => !s) }
                else { getBatchInsights(batchId).then(ins => { setInsights(ins); setShowInsights(true) }).catch(() => toast.error('Failed to load insights')) }
              }}>
              ✦ {showInsights ? 'Hide Insights' : 'View Insights'}
            </button>
            <button style={styles.outlineBtn} onClick={() => downloadBatchResultsExcel(batchId)}>
              <Download size={15} /> Export Results
            </button>
          </>
        )}
        {isOpen && closeBlockers.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#991b1b', fontWeight: 600 }}>
              Cannot close: {closeBlockers.join(' · ')}
            </span>
          </div>
        )}
        {isOpen && closeBlockers.length === 0 && !confirmingClose && (
          <button style={{ ...styles.outlineBtn, color: '#dc2626', borderColor: '#fca5a5', marginLeft: 'auto' }}
            onClick={() => setConfirmingClose(true)}>
            ✕ Close Batch
          </button>
        )}
        {isOpen && closeBlockers.length === 0 && confirmingClose && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ fontSize: 12, color: '#92400e', fontWeight: 600 }}>Lock all results?</span>
            <button style={{ ...styles.primaryBtn, background: '#dc2626', padding: '5px 12px', fontSize: 12 }}
              disabled={closing} onClick={handleClose}>
              {closing ? 'Closing…' : 'Yes, Close'}
            </button>
            <button style={{ ...styles.outlineBtn, padding: '5px 12px', fontSize: 12 }}
              onClick={() => setConfirmingClose(false)}>
              Cancel
            </button>
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

      {showInsights && insights?.has_data && (
        <InsightsPanel insights={insights} onClose={() => setShowInsights(false)} />
      )}

      {/* Coders table */}
      <div style={styles.sectionHeader}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>
          Coders ({batch.coders?.length || 0})
        </span>
      </div>

      <div style={styles.table}>
        <div style={styles.tableHeader}>
          <span>Coder</span>
          <span>Emp ID</span>
          <span>Charts Assigned</span>
          <span>Submitted</span>
        </div>
        {(batch.coders || []).map((c: any) => {
          const submitted = c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length
          return (
            <div key={c.name} style={styles.tableRow}>
              <span style={{ fontWeight: 600 }}>{c.name}</span>
              <span style={{ color: '#0f766e', fontWeight: 600 }}>{c.emp_id || '—'}</span>
              <span>{c.charts.length}</span>
              <span style={{ color: submitted > 0 ? '#16a34a' : '#9ca3af' }}>
                {submitted} / {c.charts.length}
              </span>
            </div>
          )
        })}
      </div>

      {/* Batch notes */}
      <div style={styles.cycleSection}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 13, color: '#374151' }}>Batch Log</span>
          <button style={{ ...styles.outlineBtn, fontSize: 12, padding: '4px 10px' }}
            onClick={() => setShowNoteBox(p => !p)}>
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
        {(batch.notes || []).length === 0 && !showNoteBox && (
          <div style={{ fontSize: 12, color: '#9ca3af' }}>No notes yet.</div>
        )}
        {(batch.notes || []).map((n: any, i: number) => (
          <div key={i} style={styles.noteRow}>
            <span style={{ fontSize: 13, flex: 1 }}>{n.text}</span>
            <span style={{ fontSize: 11, color: '#9ca3af', whiteSpace: 'nowrap' as const }}>
              {n.author} · {new Date(n.ts).toLocaleDateString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── DRG Review ────────────────────────────────────────────────────────────────

function DRGReviewView({ batchId, onDone }: any) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState<Record<number, boolean>>({})

  useEffect(() => { loadRows() }, [])

  async function loadRows() {
    setLoading(true)
    try { setRows(await getDRGReview(batchId)) } catch { /* ignore */ } finally { setLoading(false) }
  }

  async function decide(resultId: number, drgError: boolean) {
    setSubmitting(s => ({ ...s, [resultId]: true }))
    try {
      await submitDRGDecision(resultId, drgError, trainerName())
      setRows(r => r.filter(x => x.result_id !== resultId))
      toast.success(drgError ? 'Marked as DRG error (0 pts)' : 'Confirmed correct DRG (40 pts)')
    } catch { toast.error('Failed to save decision') }
    finally { setSubmitting(s => ({ ...s, [resultId]: false })) }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>DRG Review</div>
      <p style={styles.helpText}>
        Review flagged cases. Confirm if the DRG is correct (40 pts) or mark as DRG error (0 pts).
        Results are finalized after all rows are reviewed.
      </p>

      {rows.length === 0 ? (
        <div style={styles.empty}>
          <FileCheck size={36} color="#16a34a" />
          <p style={{ color: '#16a34a', fontWeight: 600 }}>All DRG reviews complete!</p>
          <button style={styles.primaryBtn} onClick={onDone}>← Back to Batch</button>
        </div>
      ) : (
        rows.map((r: any) => (
          <div key={r.result_id} style={styles.drgCard}>
            <div style={styles.drgHeader}>
              <span style={{ fontWeight: 700 }}>{r.coder_name}</span>
              <span style={styles.badge}>{r.chart_number}</span>
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                PDx {r.pdx_score} + SDx {r.sdx_score} + PCS {r.pcs_score || 0} = {(r.pdx_score || 0) + (r.sdx_score || 0) + (r.pcs_score || 0)} pts (before DRG)
              </span>
            </div>
            {r.feedback?.length > 0 && (
              <div style={styles.fbList}>
                {r.feedback.map((f: any, i: number) => (
                  <div key={i} style={styles.fbRow}>
                    <span style={styles.fbSection}>{f.section}</span>
                    <span style={styles.fbIssue}>{f.issue_type}</span>
                    {f.ak_code && <span style={{ fontSize: 12, color: '#374151' }}>AK: {f.ak_code}</span>}
                    {f.coder_code && <span style={{ fontSize: 12, color: '#6b7280' }}>Coder: {f.coder_code}</span>}
                    {f.detail && <span style={{ fontSize: 12, color: '#6b7280' }}>{f.detail}</span>}
                  </div>
                ))}
              </div>
            )}
            <div style={styles.drgActions}>
              <button
                style={{ ...styles.outlineBtn, borderColor: '#16a34a', color: '#16a34a' }}
                disabled={submitting[r.result_id]}
                onClick={() => decide(r.result_id, false)}>
                ✓ DRG Correct (+40 pts)
              </button>
              <button
                style={{ ...styles.outlineBtn, borderColor: '#dc2626', color: '#dc2626' }}
                disabled={submitting[r.result_id]}
                onClick={() => decide(r.result_id, true)}>
                ✗ DRG Error (0 pts)
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

// ── Results ───────────────────────────────────────────────────────────────────

function ResultsView({ batchId }: any) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [insights, setInsights] = useState<any>(null)
  const [showInsights, setShowInsights] = useState(false)

  useEffect(() => {
    getBatchResults(batchId).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [batchId])

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!data) return <div style={styles.center}>No results yet</div>

  const { batch_summary: bs, coder_summaries, is_ip, use_dpo } = data

  function AccBadge({ val, label }: { val: number | null | undefined; label: string }) {
    if (val == null) return null
    const color = val >= 90 ? '#16a34a' : val >= 80 ? '#d97706' : '#dc2626'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 70 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color }}>{val}%</div>
        <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</div>
      </div>
    )
  }

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <span style={styles.sectionTitle}>{data.batch_name} — Results</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...styles.outlineBtn, color: '#4f46e5', borderColor: '#a5b4fc' }}
            onClick={() => {
              if (insights) { setShowInsights(s => !s) }
              else { getBatchInsights(batchId).then(ins => { setInsights(ins); setShowInsights(true) }).catch(() => toast.error('Failed to load insights')) }
            }}>
            ✦ {showInsights ? 'Hide Insights' : 'View Insights'}
          </button>
          <button style={styles.outlineBtn} onClick={() => downloadBatchResultsExcel(batchId)}>
            <Download size={15} /> Export Excel
          </button>
        </div>
      </div>

      {showInsights && insights?.has_data && (
        <InsightsPanel insights={insights} onClose={() => setShowInsights(false)} />
      )}

      {/* Batch summary */}
      <div style={styles.statsRow}>
        <div style={styles.statCard}>
          <div style={styles.statValue}>{bs.total_coders}</div>
          <div style={styles.statLabel}>Coders</div>
        </div>
        <div style={styles.statCard}>
          <div style={{ ...styles.statValue, color: '#16a34a' }}>{bs.passed}</div>
          <div style={styles.statLabel}>Passed</div>
        </div>
        <div style={styles.statCard}>
          <div style={{ ...styles.statValue, color: '#dc2626' }}>{bs.failed}</div>
          <div style={styles.statLabel}>Failed</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statValue}>{bs.pass_rate}%</div>
          <div style={styles.statLabel}>Coder Pass Rate</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statValue}>{bs.avg_score}%</div>
          <div style={styles.statLabel}>Avg Score</div>
        </div>
      </div>

      {/* Top missed codes */}
      {bs.top_missed_codes?.length > 0 && (
        <div style={{ ...styles.infoBox, marginBottom: 20 }}>
          <strong>Top missed codes:</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {bs.top_missed_codes.map((m: any) => (
              <span key={m.code} style={{ ...styles.badge, background: '#fee2e2', color: '#dc2626' }}>
                {m.code} <span style={{ opacity: 0.7 }}>({m.count}×)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Per-coder table */}
      <div style={styles.table}>
        <div style={{ ...styles.tableHeader, gridTemplateColumns: is_ip ? '2fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr' : '2fr 1fr 1fr 1fr 1fr 1fr' }}>
          <span>Coder</span>
          <span>PDx</span>
          <span>SDx</span>
          {is_ip && <><span>PCS</span><span>DRG</span></>}
          {!is_ip && <span>CPT</span>}
          <span>Total</span>
          <span>Result</span>
        </div>
        {coder_summaries.map((c: any) => (
          <div key={c.coder_name}>
            <div
              style={{ ...styles.tableRow, cursor: 'pointer', gridTemplateColumns: is_ip ? '2fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr' : '2fr 1fr 1fr 1fr 1fr 1fr' }}
              onClick={() => setExpanded(expanded === c.coder_name ? null : c.coder_name)}>
              <span style={{ fontWeight: 600 }}>{c.coder_name} {expanded === c.coder_name ? '▲' : '▼'}</span>
              <span>{c.avg_pdx}</span>
              <span>{c.avg_sdx}</span>
              {is_ip && <><span>{c.avg_pcs}</span><span>{c.avg_drg}</span></>}
              {!is_ip && <span>{c.avg_cpt}</span>}
              <span style={{ fontWeight: 700 }}>{c.avg_total}%</span>
              <span style={{ fontWeight: 700, color: c.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>
                {c.pass_fail}
              </span>
            </div>
            {expanded === c.coder_name && (
              <div style={styles.chartDetail}>
                {/* DPO supplementary accuracy panel */}
                {use_dpo && (c.dpo_dx_accuracy != null || c.dpo_overall_accuracy != null) && (
                  <div style={styles.dpoPanel}>
                    <div style={styles.dpoPanelTitle}>
                      <span style={styles.dpoSupBadge}>DPO Supplementary</span>
                      Coding Accuracy Breakdown
                    </div>
                    <div style={styles.dpoPanelRow}>
                      <AccBadge val={c.dpo_dx_accuracy} label="Dx Accuracy" />
                      {is_ip && <AccBadge val={c.dpo_poa_accuracy} label="POA Accuracy" />}
                      <AccBadge val={c.dpo_proc_accuracy} label={is_ip ? 'PCS Accuracy' : 'CPT Accuracy'} />
                      <div style={styles.dpoDivider} />
                      <AccBadge val={c.dpo_overall_accuracy} label="Overall Accuracy" />
                    </div>
                  </div>
                )}
                {c.charts.map((ch: any) => (
                  <div key={ch.chart_number} style={styles.chartDetailRow}>
                    <span style={{ fontWeight: 600, minWidth: 70 }}>{ch.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>PDx:{ch.pdx_score} SDx:{ch.sdx_score}
                      {is_ip ? ` PCS:${ch.pcs_score} DRG:${ch.drg_score ?? '—'}` : ` CPT:${ch.cpt_score}`}
                    </span>
                    <span style={{ fontWeight: 700 }}>{ch.total_score ?? '—'}%</span>
                    <span style={{ color: ch.pass_fail === 'PASS' ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                      {ch.pass_fail || '—'}
                    </span>
                    {ch.feedback?.length > 0 && (
                      <div style={styles.fbList}>
                        {ch.feedback.map((f: any, i: number) => (
                          <div key={i} style={styles.fbRow}>
                            <span style={styles.fbSection}>{f.section}</span>
                            <span style={styles.fbIssue}>{f.issue_type}</span>
                            {f.ak_code && <span style={{ fontSize: 11 }}>AK:{f.ak_code}</span>}
                            {f.coder_code && <span style={{ fontSize: 11 }}>Cdr:{f.coder_code}</span>}
                            {f.detail && <span style={{ fontSize: 11, color: '#6b7280' }}>{f.detail}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Scoring Config ────────────────────────────────────────────────────────────

const ALL_DRG_TRIGGERS = [
  { key: 'pdx_mismatch', label: 'PDx code or POA mismatch' },
  { key: 'ccmcc_missing', label: 'CC/MCC SDx from AK missing from coder' },
  { key: 'pcs_undercoded', label: 'PCS under-coded (missed AK procedures)' },
  { key: 'pcs_overcoded', label: 'PCS over-coded (extra procedures)' },
  { key: 'spurious_sdx', label: 'AK has no SDx but coder added SDx' },
  { key: 'spurious_pcs', label: 'AK has no PCS but coder added PCS' },
]

function ScoringConfigView() {
  const [configs, setConfigs] = useState<any>(null)
  const [tab, setTab] = useState<'IP' | 'OP'>('IP')
  const [form, setForm] = useState<any>({})
  const [passphrase, setPassphrase] = useState('')
  const [saving, setSaving] = useState(false)
  const [showPassphrase, setShowPassphrase] = useState(false)

  useEffect(() => { loadConfigs() }, [])

  async function loadConfigs() {
    try {
      const data = await getScoringConfigs()
      setConfigs(data)
      setForm({ IP: { ...data.IP }, OP: { ...data.OP } })
    } catch { toast.error('Failed to load scoring config') }
  }

  function updateField(stype: string, field: string, value: any) {
    setForm((f: any) => ({ ...f, [stype]: { ...f[stype], [field]: value } }))
  }

  function toggleTrigger(key: string) {
    const current: string[] = form.IP?.drg_triggers || []
    const updated = current.includes(key) ? current.filter(k => k !== key) : [...current, key]
    updateField('IP', 'drg_triggers', updated)
  }

  function weightSum(stype: string) {
    const f = form[stype] || {}
    if (stype === 'IP') return (f.pdx_weight || 0) + (f.sdx_weight || 0) + (f.pcs_weight || 0) + (f.drg_weight || 0)
    return (f.pdx_weight || 0) + (f.sdx_weight || 0) + (f.cpt_weight || 0)
  }

  async function handleSave() {
    if (!passphrase) return toast.error('Enter master admin passphrase')
    const f = form[tab]
    const sum = weightSum(tab)
    if (sum !== 100) return toast.error(`Weights must sum to 100 (currently ${sum})`)

    setSaving(true)
    try {
      if (!f.weighted_enabled && !f.dpo_enabled) return toast.error('At least one scoring method must be enabled')
      await updateScoringConfig({
        specialty_type: tab,
        pdx_weight: f.pdx_weight,
        sdx_weight: f.sdx_weight,
        pcs_weight: tab === 'IP' ? f.pcs_weight : undefined,
        drg_weight: tab === 'IP' ? f.drg_weight : undefined,
        cpt_weight: tab === 'OP' ? f.cpt_weight : undefined,
        pass_threshold: f.pass_threshold,
        drg_triggers: tab === 'IP' ? (f.drg_triggers || []) : [],
        overcoding_penalty: f.overcoding_penalty,
        weighted_enabled: f.weighted_enabled ?? true,
        dpo_enabled: f.dpo_enabled ?? true,
        dpo_pass_threshold: f.dpo_pass_threshold ?? 80,
        passphrase,
        updated_by: trainerName(),
      })
      toast.success(`${tab} scoring config saved`)
      loadConfigs()
      setPassphrase('')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save')
    } finally { setSaving(false) }
  }

  if (!form.IP || !form.OP) return <div style={styles.center}><Loader size={24} /></div>

  const f = form[tab]
  const sum = weightSum(tab)

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Scoring Configuration</div>
      <div style={styles.warnBox}>
        ⚠ Changes apply to <strong>future batches only</strong>. In-progress and completed batches are not affected.
        Requires master admin passphrase.
      </div>

      {/* Tab */}
      <div style={styles.chipRow}>
        {(['IP', 'OP'] as const).map(t => (
          <button key={t} style={tab === t ? styles.chipActive : styles.chip} onClick={() => setTab(t)}>
            {t === 'IP' ? 'IP-DRG' : 'Outpatient (OP)'}
          </button>
        ))}
      </div>

      {/* Weights */}
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Scoring Weights <span style={styles.hint}>(must sum to 100)</span></div>
        <div style={styles.weightGrid}>
          <WeightField label="PDx" value={f.pdx_weight} onChange={v => updateField(tab, 'pdx_weight', v)} />
          <WeightField label="SDx" value={f.sdx_weight} onChange={v => updateField(tab, 'sdx_weight', v)} />
          {tab === 'IP' && <>
            <WeightField label="PCS" value={f.pcs_weight} onChange={v => updateField(tab, 'pcs_weight', v)} />
            <WeightField label="DRG" value={f.drg_weight} onChange={v => updateField(tab, 'drg_weight', v)} />
          </>}
          {tab === 'OP' && <WeightField label="CPT" value={f.cpt_weight} onChange={v => updateField(tab, 'cpt_weight', v)} />}
        </div>
        <div style={{ fontSize: 13, fontWeight: 700, color: sum === 100 ? '#16a34a' : '#dc2626', marginTop: 6 }}>
          Total: {sum} / 100 {sum === 100 ? '✓' : '⚠ Must equal 100'}
        </div>
      </div>

      {/* Pass threshold */}
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Pass Threshold</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
            value={f.pass_threshold}
            onChange={e => updateField(tab, 'pass_threshold', parseInt(e.target.value) || 80)} />
          <span style={styles.hint}>% minimum to pass</span>
        </div>
      </div>

      {/* Overcoding penalty */}
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Overcoding Penalty</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
          <input type="checkbox" checked={f.overcoding_penalty}
            onChange={e => updateField(tab, 'overcoding_penalty', e.target.checked)} />
          Penalize extra codes submitted beyond the answer key count
        </label>
      </div>

      {/* DRG triggers (IP only) */}
      {tab === 'IP' && (
        <div style={styles.configSection}>
          <div style={styles.configSectionTitle}>DRG Auto-Flag Triggers
            <span style={styles.hint}> — any one active trigger flags the row for review</span>
          </div>
          {ALL_DRG_TRIGGERS.map(t => (
            <label key={t.key} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13, padding: '4px 0' }}>
              <input type="checkbox"
                checked={(f.drg_triggers || []).includes(t.key)}
                onChange={() => toggleTrigger(t.key)} />
              {t.label}
            </label>
          ))}
        </div>
      )}

      {/* Method availability */}
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Scoring Method Availability
          <span style={styles.hint}> — disabled methods cannot be selected when creating a batch</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={f.weighted_enabled ?? true}
              onChange={e => updateField(tab, 'weighted_enabled', e.target.checked)} />
            <span><strong>Weighted Scoring</strong> enabled (primary method, drives pass/fail)</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={f.dpo_enabled ?? true}
              onChange={e => updateField(tab, 'dpo_enabled', e.target.checked)} />
            <span><strong>DPO Accuracy</strong> enabled (supplementary, shows per-area accuracy %)</span>
          </label>
          {!(f.weighted_enabled ?? true) && !(f.dpo_enabled ?? true) && (
            <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must remain enabled</div>
          )}
        </div>
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            DPO Pass Threshold <span style={styles.hint}>(for supplementary reference only)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input type="number" min={50} max={100} style={{ ...styles.input, width: 80 }}
              value={f.dpo_pass_threshold ?? 80}
              onChange={e => updateField(tab, 'dpo_pass_threshold', parseFloat(e.target.value) || 80)} />
            <span style={styles.hint}>% accuracy — shown alongside results but does not override weighted pass/fail</span>
          </div>
        </div>
      </div>

      {/* Passphrase + Save */}
      <div style={styles.configSection}>
        <div style={styles.configSectionTitle}>Master Admin Passphrase *</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <input
            type={showPassphrase ? 'text' : 'password'}
            style={{ ...styles.input, width: 220 }}
            placeholder="Enter passphrase to save"
            value={passphrase}
            onChange={e => setPassphrase(e.target.value)} />
          <button style={styles.outlineBtn} onClick={() => setShowPassphrase(s => !s)}>
            {showPassphrase ? 'Hide' : 'Show'}
          </button>
          <button style={saving ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
            disabled={saving} onClick={handleSave}>
            {saving ? <><Loader size={14} /> Saving...</> : 'Save Config'}
          </button>
        </div>
        {configs?.[tab]?.updated_by && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
            Last updated by {configs[tab].updated_by}
            {configs[tab].updated_at && ` on ${new Date(configs[tab].updated_at).toLocaleDateString()}`}
          </div>
        )}
      </div>
    </div>
  )
}

function WeightField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <label style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>{label}</label>
      <input type="number" min={0} max={100} style={{ ...styles.input, width: 70, textAlign: 'center' }}
        value={value || 0} onChange={e => onChange(parseInt(e.target.value) || 0)} />
    </div>
  )
}

// ── Self Practice (inline inside PracticeLab) ─────────────────────────────────

function SelfPracticeInlineView() {
  const [tab, setTab] = useState<'queue' | 'standalone'>('queue')
  const trainerName = () => localStorage.getItem('trainer_name') || ''

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={styles.sectionTitle}>Self Practice</div>
        <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden' }}>
          <button style={tab === 'queue' ? { ...styles.navBtn, background: '#4f46e5', color: '#fff', border: 'none' } : styles.navBtn}
            onClick={() => setTab('queue')}>Review Queue</button>
          <button style={tab === 'standalone' ? { ...styles.navBtn, background: '#4f46e5', color: '#fff', border: 'none' } : styles.navBtn}
            onClick={() => setTab('standalone')}>Standalone Grade</button>
        </div>
      </div>
      {tab === 'queue' ? <SPQueuePanel trainerName={trainerName()} /> : <SPStandalonePanel trainerName={trainerName()} />}
    </div>
  )
}

function SPQueuePanel({ trainerName }: { trainerName: string }) {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('pending_review')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({})
  const [releasing, setReleasing] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try { setItems(await getSelfPracticeQueue(filter)) }
    catch { toast.error('Failed to load queue') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [filter])

  const handleRelease = async (sub: any) => {
    if (!trainerName) return toast.error('Set your trainer name in Upload Charts first')
    setReleasing(sub.id)
    const tid = toast.loading('Releasing…')
    try {
      await releaseSelfPractice(sub.id, feedbacks[sub.id] || '', trainerName)
      toast.dismiss(tid); toast.success('Results released')
      load(); setExpanded(null)
    } catch { toast.dismiss(tid); toast.error('Failed to release') }
    finally { setReleasing(null) }
  }

  if (loading) return <div style={styles.emptyState}>Loading…</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <select style={styles.select} value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="pending_review">Pending Review</option>
          <option value="released">Released</option>
          <option value="all">All</option>
        </select>
        <span style={styles.hint}>{items.length} submission{items.length !== 1 ? 's' : ''}</span>
      </div>

      {items.length === 0 ? (
        <div style={styles.emptyState}>No submissions in this view.</div>
      ) : items.map(sub => (
        <div key={sub.id} style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden', background: '#fff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', cursor: 'pointer' }}
            onClick={() => setExpanded(expanded === sub.id ? null : sub.id)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontWeight: 800, fontSize: 15 }}>{sub.coder_name}</span>
              <span style={{ fontSize: 12, color: '#6b7280', background: '#f3f4f6', padding: '2px 8px', borderRadius: 12 }}>{sub.emp_id}</span>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: sub.status === 'pending_review' ? '#fef3c7' : '#dcfce7', color: sub.status === 'pending_review' ? '#b45309' : '#15803d' }}>
                {sub.status === 'pending_review' ? 'Pending' : 'Released'}
              </span>
              <span style={styles.hint}>{sub.chart_count} chart{sub.chart_count !== 1 ? 's' : ''}</span>
            </div>
            <span style={styles.hint}>{new Date(sub.submitted_at).toLocaleDateString()}</span>
          </div>

          {expanded === sub.id && (
            <div style={{ borderTop: '1px solid #f3f4f6', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr 70px 70px 80px 80px', padding: '7px 12px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' }}>
                  <span>Chart</span><span>Specialty</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
                </div>
                {sub.results.map((r: any, i: number) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '100px 1fr 70px 70px 80px 80px', padding: '8px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' }}>
                    <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty || '—'}</span>
                    <span>{r.weighted_score != null ? `${r.weighted_score}%` : '—'}</span>
                    <span style={{ fontWeight: 700, color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{r.pass_fail || '—'}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
                  </div>
                ))}
              </div>

              {sub.status === 'pending_review' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={styles.label}>Feedback for coder (optional)</label>
                  <textarea style={{ ...styles.input, resize: 'vertical' as const, fontFamily: 'system-ui', minHeight: 70 }} rows={3}
                    placeholder="Overall comments, areas to improve…"
                    value={feedbacks[sub.id] || ''}
                    onChange={e => setFeedbacks(f => ({ ...f, [sub.id]: e.target.value }))} />
                  <button style={{ ...styles.primaryBtn, opacity: releasing === sub.id ? 0.7 : 1, alignSelf: 'flex-start' }}
                    disabled={releasing === sub.id} onClick={() => handleRelease(sub)}>
                    {releasing === sub.id ? 'Releasing…' : '✓ Release Results'}
                  </button>
                </div>
              )}
              {sub.status === 'released' && sub.trainer_feedback && (
                <div style={{ fontSize: 13, color: '#15803d', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '10px 14px' }}>
                  <strong>Feedback:</strong> {sub.trainer_feedback}
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>Released by {sub.reviewed_by}</div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function SPStandalonePanel({ trainerName }: { trainerName: string }) {
  const [files, setFiles] = useState<File[]>([])
  const [grading, setGrading] = useState(false)
  const [results, setResults] = useState<any | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFiles = (fl: FileList | null) => {
    if (!fl) return
    const valid = Array.from(fl).filter(f => f.name.endsWith('.xlsx'))
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...valid.filter(f => !names.has(f.name))]
    })
  }

  const handleGrade = async () => {
    if (!trainerName) return toast.error('Set your trainer name in Upload Charts first')
    if (!files.length) return toast.error('Add at least one answer sheet')
    setGrading(true)
    const tid = toast.loading(`Grading ${files.length} file${files.length !== 1 ? 's' : ''}…`)
    try {
      const res = await standaloneGrade(trainerName, files)
      toast.dismiss(tid)
      if (res.results.length) toast.success(`${res.results.length} chart${res.results.length !== 1 ? 's' : ''} graded`)
      res.errors.forEach((e: string) => toast.error(e, { duration: 6000 }))
      setResults(res)
    } catch (err: any) {
      toast.dismiss(tid); toast.error(err?.response?.data?.detail || 'Grading failed')
    } finally { setGrading(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={styles.infoBox}>
        Grade any completed answer sheet immediately — no batch needed. Charts must have answer keys. Filename is used as coder name.
      </div>
      <div style={styles.dropzone} onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileRef.current?.click()}>
        <Upload size={22} color="#4f46e5" />
        <div style={{ fontWeight: 600, fontSize: 14, color: '#374151' }}>Drop completed answer sheets or click to browse</div>
        <div style={{ fontSize: 12, color: '#9ca3af' }}>Accepts .xlsx</div>
        <input ref={fileRef} type="file" multiple accept=".xlsx" style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {files.map((f, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 7 }}>
              <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
              <button style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af' }} onClick={() => setFiles(p => p.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button style={{ ...styles.primaryBtn, opacity: grading ? 0.7 : 1 }} disabled={grading} onClick={handleGrade}>
            {grading ? <><Loader size={13} /> Grading…</> : `Grade ${files.length} File${files.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}

      {results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <StandaloneInsights results={results.results} />
          <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '140px 100px 70px 70px 80px 80px', padding: '7px 12px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' }}>
              <span>Coder</span><span>Chart</span><span>Score</span><span>Result</span><span>Dx Acc</span><span>Proc Acc</span>
            </div>
            {results.results.map((r: any, i: number) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '140px 100px 70px 70px 80px 80px', padding: '8px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' }}>
                <span style={{ fontWeight: 600 }}>{r.coder_name}</span>
                <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                <span>{r.weighted_score != null ? `${r.weighted_score}%` : '—'}</span>
                <span style={{ fontWeight: 700, color: r.pass_fail === 'PASS' ? '#16a34a' : '#dc2626' }}>{r.pass_fail || '—'}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_dx_accuracy != null ? `${r.dpo_dx_accuracy.toFixed(1)}%` : '—'}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{r.dpo_proc_accuracy != null ? `${r.dpo_proc_accuracy.toFixed(1)}%` : '—'}</span>
              </div>
            ))}
          </div>
          <button style={styles.outlineBtn} onClick={() => { setFiles([]); setResults(null) }}>Grade More</button>
        </div>
      )}
    </div>
  )
}

// ── Standalone Grading Insights ───────────────────────────────────────────────

function StandaloneInsights({ results }: { results: any[] }) {
  if (!results.length) return null
  const scored = results.filter(r => r.weighted_score != null)
  if (!scored.length) return null

  const passed = scored.filter(r => r.pass_fail === 'PASS').length
  const avgScore = Math.round(scored.reduce((s, r) => s + r.weighted_score, 0) / scored.length)
  const passRate = Math.round(passed / scored.length * 100)

  // Aggregate feedback_items
  const issueCounts: Record<string, number> = {}
  const sectionCounts: Record<string, number> = {}
  const missedCodes: Record<string, number> = {}
  for (const r of results) {
    for (const f of r.feedback_items || []) {
      const issue = f.issue || f.issue_type || ''
      const section = f.section || ''
      if (issue) issueCounts[issue] = (issueCounts[issue] || 0) + 1
      if (section) sectionCounts[section] = (sectionCounts[section] || 0) + 1
      if ((issue === 'Missed' || issue === 'missed') && f.ak_code) {
        missedCodes[f.ak_code] = (missedCodes[f.ak_code] || 0) + 1
      }
    }
  }
  const totalFb = Object.values(issueCounts).reduce((a, b) => a + b, 0)
  const topIssues = Object.entries(issueCounts).sort((a, b) => b[1] - a[1])
  const topMissed = Object.entries(missedCodes).sort((a, b) => b[1] - a[1]).slice(0, 6)

  const ISSUE_COLORS: Record<string, string> = {
    Missed: '#dc2626', Over_coded: '#d97706', Wrong_Code: '#7c3aed', Wrong_POA: '#0891b2', Wrong_Modifier: '#6b7280',
  }

  return (
    <div style={{ background: '#f8faff', border: '1.5px solid #a5b4fc', borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: '#312e81' }}>✦ Grading Summary</div>

      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {[
          { label: 'Charts Graded', value: scored.length, color: '#111' },
          { label: 'Passed', value: passed, color: '#16a34a' },
          { label: 'Failed', value: scored.length - passed, color: '#dc2626' },
          { label: 'Pass Rate', value: `${passRate}%`, color: passRate >= 80 ? '#16a34a' : passRate >= 60 ? '#d97706' : '#dc2626' },
          { label: 'Avg Score', value: `${avgScore}%`, color: '#111' },
        ].map(s => (
          <div key={s.label} style={{ background: '#fff', border: '1px solid #e0e7ff', borderRadius: 8, padding: '10px 14px', textAlign: 'center', minWidth: 90 }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {totalFb > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          {/* Error breakdown */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 14px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 10 }}>Error Breakdown</div>
            <ResponsiveContainer width="100%" height={Math.max(100, topIssues.length * 36)}>
              <BarChart data={topIssues.map(([type, count]) => ({ label: type.replace(/_/g, ' '), count, pct: Math.round(count / totalFb * 100), type }))}
                layout="vertical" margin={{ left: 8, right: 36, top: 2, bottom: 2 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="label" width={90} tick={{ fontSize: 11, fontWeight: 600 }} />
                <Tooltip formatter={(v: any, _: any, p: any) => [`${p.payload.count} (${v}%)`, 'Share']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="pct" radius={[0, 5, 5, 0]}>
                  {topIssues.map(([type]) => <Cell key={type} fill={ISSUE_COLORS[type] || '#6b7280'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 8 }}>
              {Object.entries(sectionCounts).map(([sec, cnt]) => (
                <span key={sec} style={{ fontSize: 10, fontWeight: 700, background: '#dbeafe', color: '#1d4ed8', padding: '1px 8px', borderRadius: 10 }}>{sec} {cnt}×</span>
              ))}
            </div>
          </div>

          {/* Top missed codes */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 14px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 10 }}>Top Missed Codes</div>
            {topMissed.length === 0 ? (
              <div style={{ fontSize: 12, color: '#9ca3af' }}>None</div>
            ) : topMissed.map(([code, cnt]) => (
              <div key={code} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                <span style={{ fontWeight: 700, color: '#dc2626' }}>{code}</span>
                <span style={{ color: '#6b7280' }}>{cnt}×</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


// ── PracticeLab Analytics (standalone tab) ────────────────────────────────────

const TEACHING_LABEL_META: Record<string, { color: string; bg: string; desc: string }> = {
  'High Yield':    { color: '#166534', bg: '#dcfce7', desc: 'Commonly attempted, produces meaningful repeatable mistakes' },
  'High Confusion':{ color: '#92400e', bg: '#fef3c7', desc: '>60% fail rate with diverse error types — review answer key' },
  'High Fail':     { color: '#991b1b', bg: '#fee2e2', desc: 'High failure rate, low error variety' },
  'Too Easy':      { color: '#1d4ed8', bg: '#dbeafe', desc: 'Avg score ≥90% — suitable for beginner packs' },
  'Underused':     { color: '#6b7280', bg: '#f3f4f6', desc: 'Fewer than 2 grading attempts' },
  'Standard':      { color: '#374151', bg: '#f9fafb', desc: 'Typical performance range' },
}

function PLAnalyticsView() {
  const [tab, setTab] = useState<'overview' | 'specialty' | 'chart' | 'batch' | 'coder' | 'category' | 'teaching' | 'matrix'>('overview')
  const [overview, setOverview] = useState<any>(null)
  const [bySpecialty, setBySpecialty] = useState<any[]>([])
  const [byChart, setByChart] = useState<any[]>([])
  const [byBatch, setByBatch] = useState<any[]>([])
  const [coderName, setCoderName] = useState('')
  const [coderTrend, setCoderTrend] = useState<any[]>([])
  const [categoryData, setCategoryData] = useState<{ team: any[]; coder_category: any[] } | null>(null)
  const [teachingData, setTeachingData] = useState<any[]>([])
  const [matrixData, setMatrixData] = useState<{ batches: any[]; coders: string[]; cells: any[] } | null>(null)
  const [teachingFilter, setTeachingFilter] = useState<string>('All')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getPLAnalyticsOverview(),
      getPLAnalyticsBySpecialty(),
      getPLAnalyticsByBatch(),
    ]).then(([ov, sp, bt]) => {
      setOverview(ov); setBySpecialty(sp); setByBatch(bt)
    }).catch(() => toast.error('Failed to load analytics')).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (tab === 'chart' && byChart.length === 0) getPLAnalyticsByChart().then(setByChart).catch(() => {})
    if (tab === 'category' && !categoryData) getPLAnalyticsByCategory().then(setCategoryData).catch(() => {})
    if (tab === 'teaching' && teachingData.length === 0) getPLChartTeachingValue().then(setTeachingData).catch(() => {})
    if (tab === 'matrix' && !matrixData) getPLCoderMatrix().then(setMatrixData).catch(() => {})
  }, [tab])

  async function loadCoderTrend() {
    if (!coderName.trim()) return
    const data = await getCoderTrend(coderName.trim()).catch(() => null)
    if (data) setCoderTrend(data)
    else toast.error('No data for this coder')
  }

  const TABS = [
    { key: 'overview', label: 'Overview' },
    { key: 'specialty', label: 'By Specialty' },
    { key: 'batch', label: 'By Batch' },
    { key: 'coder', label: 'Coder Trend' },
    { key: 'category', label: 'Category Mastery' },
    { key: 'teaching', label: 'Chart Value' },
    { key: 'matrix', label: 'Coder Matrix' },
    { key: 'chart', label: 'By Chart' },
  ]

  if (loading) return <div style={styles.center}><Loader size={24} /></div>

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={styles.sectionTitle}>Analytics</span>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', alignSelf: 'flex-start' }}>
        {TABS.map(t => (
          <button key={t.key}
            style={tab === t.key ? { ...styles.modeTab, background: '#4f46e5', color: '#fff', padding: '7px 16px' } : { ...styles.modeTab, padding: '7px 16px' }}
            onClick={() => setTab(t.key as any)}>{t.label}</button>
        ))}
      </div>

      {/* Overview */}
      {tab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {!overview ? (
            <div style={styles.emptyState}>No grading data yet</div>
          ) : (
            <>
              <div style={styles.statsRow}>
                {[
                  { label: 'Total Batches', value: overview.total_batches },
                  { label: 'Open Batches', value: overview.open_batches ?? 0, color: '#2563eb' },
                  { label: 'Closed Batches', value: overview.complete_batches ?? 0, color: '#16a34a' },
                  { label: 'Total Graded', value: overview.total_graded },
                  { label: 'Overall Pass Rate', value: `${overview.overall_pass_rate}%`, color: overview.overall_pass_rate >= 80 ? '#16a34a' : overview.overall_pass_rate >= 60 ? '#d97706' : '#dc2626' },
                ].map(s => (
                  <div key={s.label} style={styles.statCard}>
                    <div style={{ ...styles.statValue, color: s.color || '#111' }}>{s.value}</div>
                    <div style={styles.statLabel}>{s.label}</div>
                  </div>
                ))}
              </div>
              {overview.total_graded === 0 ? (
                <div style={styles.warnBox}>No grading results yet. Complete at least one batch grading cycle to see analytics.</div>
              ) : (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px', display: 'flex', alignItems: 'center', gap: 32 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 4 }}>Overall Pass / Fail Split</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{overview.total_graded} graded submissions</div>
                  </div>
                  <PieChart width={180} height={180}>
                    <Pie data={[{ name: 'Passed', value: overview.total_passed }, { name: 'Failed', value: overview.total_graded - overview.total_passed }]}
                      cx={90} cy={90} innerRadius={52} outerRadius={80} paddingAngle={3} dataKey="value">
                      <Cell fill="#16a34a" />
                      <Cell fill="#dc2626" />
                    </Pie>
                    <Tooltip formatter={(v: any, name: string) => [v, name]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* By Specialty */}
      {tab === 'specialty' && (
        <div>
          {bySpecialty.length === 0 ? (
            <div style={styles.emptyState}>No data yet — complete a grading cycle first</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Avg Score & Pass Rate by Specialty</div>
                <ResponsiveContainer width="100%" height={Math.max(200, bySpecialty.length * 56)}>
                  <BarChart data={bySpecialty} layout="vertical" margin={{ left: 20, right: 50, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="specialty" width={110} tick={{ fontSize: 12, fontWeight: 600 }} />
                    <Tooltip formatter={(v: any, name: string) => [`${v}%`, name === 'avg_score' ? 'Avg Score' : 'Pass Rate']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'avg_score' ? 'Avg Score' : 'Pass Rate'} />
                    <Bar dataKey="avg_score" name="avg_score" radius={[0, 4, 4, 0]} fill="#4f46e5" fillOpacity={0.85} />
                    <Bar dataKey="pass_rate" name="pass_rate" radius={[0, 4, 4, 0]} fill="#16a34a" fillOpacity={0.85} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
                  <span>Specialty</span><span>Graded</span><span>Avg Score</span><span>Pass Rate</span>
                </div>
                {bySpecialty.map((r: any) => (
                  <div key={r.specialty} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
                    <span style={{ fontWeight: 600 }}>{r.specialty}</span>
                    <span>{r.total}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                    <span style={{ fontWeight: 700, color: r.pass_rate >= 80 ? '#16a34a' : r.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{r.pass_rate}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* By Chart */}
      {tab === 'chart' && (
        <div>
          {byChart.length === 0 ? (
            <div style={styles.emptyState}>No chart data yet</div>
          ) : (
            <div style={styles.table}>
              <div style={{ ...styles.tableHeader, gridTemplateColumns: '120px 1fr 1fr 80px 80px' }}>
                <span>Chart</span><span>Category</span><span>Specialty</span><span>Attempts</span><span>Avg Score</span>
              </div>
              {byChart.map((r: any) => (
                <div key={r.chart_number} style={{ ...styles.tableRow, gridTemplateColumns: '120px 1fr 1fr 80px 80px', flexDirection: 'column' as const, height: 'auto', alignItems: 'stretch', padding: 0 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 80px 80px', padding: '10px 16px', alignItems: 'center' }}>
                    <span style={{ fontWeight: 700, color: '#1e40af' }}>{r.chart_number}</span>
                    <span style={{ fontSize: 12 }}>{r.category}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span>{r.attempt_count}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                  </div>
                  {r.top_missed?.length > 0 && (
                    <div style={{ padding: '4px 16px 8px 132px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {r.top_missed.map(([code, cnt]: any) => (
                        <span key={code} style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '1px 8px', borderRadius: 10 }}>{code} {cnt}×</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* By Batch */}
      {tab === 'batch' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {byBatch.length === 0 ? (
            <div style={styles.emptyState}>No batch results yet</div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Pass Rate & Avg Score Over Batches</div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={byBatch.map(b => ({ ...b, label: b.batch_name.length > 16 ? b.batch_name.slice(0, 16) + '…' : b.batch_name }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any, name: string) => [`${v}%`, name === 'pass_rate' ? 'Pass Rate' : 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend formatter={n => n === 'pass_rate' ? 'Pass Rate' : 'Avg Score'} />
                    <Line type="monotone" dataKey="pass_rate" stroke="#16a34a" strokeWidth={2.5} dot={{ r: 5, fill: '#16a34a' }} activeDot={{ r: 7 }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 5, fill: '#4f46e5' }} activeDot={{ r: 7 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 100px 80px 80px 80px' }}>
                  <span>Batch</span><span>Specialty</span><span>Coders</span><span>Avg Score</span><span>Pass Rate</span>
                </div>
                {byBatch.map((r: any) => (
                  <div key={r.batch_id} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 100px 80px 80px 80px' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{r.batch_name}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>{r.specialty}</span>
                    <span>{r.coder_count}</span>
                    <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                    <span style={{ fontWeight: 700, color: r.pass_rate >= 80 ? '#16a34a' : r.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{r.pass_rate}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Coder Trend */}
      {tab === 'coder' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input style={{ ...styles.input, width: 260 }} placeholder="Enter coder name exactly"
              value={coderName} onChange={e => setCoderName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadCoderTrend()} />
            <button style={styles.primaryBtn} onClick={loadCoderTrend}>Look Up</button>
          </div>
          {coderTrend.length === 0 ? (
            <div style={styles.emptyState}>Enter a coder name to see their score trend across batches</div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Score Trend — {coderName}</div>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={coderTrend.map(r => ({ ...r, label: r.batch_name.length > 14 ? r.batch_name.slice(0, 14) + '…' : r.batch_name }))} margin={{ left: 10, right: 20, top: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => [`${v}%`, 'Avg Score']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 6, fill: '#4f46e5' }} activeDot={{ r: 8 }} name="Avg Score" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={styles.table}>
                <div style={{ ...styles.tableHeader, gridTemplateColumns: '2fr 120px 80px 80px' }}>
                  <span>Batch</span><span>Date</span><span>Charts</span><span>Avg Score</span>
                </div>
                {coderTrend.map((r: any, i: number) => {
                  const prev = coderTrend[i - 1]
                  const delta = prev ? round1(r.avg_score - prev.avg_score) : null
                  return (
                    <div key={r.batch_id} style={{ ...styles.tableRow, gridTemplateColumns: '2fr 120px 80px 80px' }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{r.batch_name}</span>
                      <span style={{ fontSize: 12, color: '#6b7280' }}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</span>
                      <span>{r.chart_count}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontWeight: 700, color: r.avg_score >= 80 ? '#16a34a' : r.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{r.avg_score}%</span>
                        {delta != null && <span style={{ fontSize: 11, fontWeight: 700, color: delta > 0 ? '#16a34a' : delta < 0 ? '#dc2626' : '#9ca3af' }}>{delta > 0 ? '↑' : delta < 0 ? '↓' : '→'}{Math.abs(delta)}%</span>}
                      </span>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── C: Category Mastery ───────────────────────────────────────────── */}
      {tab === 'category' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!categoryData ? (
            <div style={styles.emptyState}>Loading…</div>
          ) : categoryData.team.length === 0 ? (
            <div style={styles.emptyState}>No category data yet — grade some batches first.</div>
          ) : (
            <>
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Team Avg Score by Category</div>
                <ResponsiveContainer width="100%" height={Math.max(180, categoryData.team.length * 48)}>
                  <BarChart data={categoryData.team} layout="vertical" margin={{ left: 10, right: 40, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={140} />
                    <Tooltip formatter={(v: any) => [`${v}%`]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Bar dataKey="avg_score" name="Avg Score" radius={[0, 4, 4, 0]}>
                      {categoryData.team.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.avg_score >= 80 ? '#22c55e' : entry.avg_score >= 60 ? '#f59e0b' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {categoryData.coder_category.length > 0 && (() => {
                const coders = Array.from(new Set(categoryData.coder_category.map((r: any) => r.coder_name)))
                const cats = categoryData.team.map((r: any) => r.category)
                const cellMap: Record<string, Record<string, any>> = {}
                categoryData.coder_category.forEach((r: any) => {
                  if (!cellMap[r.coder_name]) cellMap[r.coder_name] = {}
                  cellMap[r.coder_name][r.category] = r
                })
                return (
                  <div style={{ overflowX: 'auto' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 10 }}>Coder × Category Heatmap</div>
                    <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: 'left', padding: '6px 10px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' }}>Coder</th>
                          {cats.map((c: string) => (
                            <th key={c} style={{ padding: '6px 8px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap', textAlign: 'center', fontWeight: 600 }}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {coders.map((coder: string) => (
                          <tr key={coder}>
                            <td style={{ padding: '6px 10px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' }}>{coder}</td>
                            {cats.map((cat: string) => {
                              const cell = cellMap[coder]?.[cat]
                              const score = cell?.avg_score
                              const bg = score == null ? '#f9fafb' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                              const color = score == null ? '#9ca3af' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
                              return (
                                <td key={cat} style={{ padding: '6px 8px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                  {score != null ? `${score}%` : '—'}
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>Green ≥80% · Yellow 60–79% · Red &lt;60% · — no data</div>
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}

      {/* ── D: Chart Teaching Value ──────────────────────────────────────────── */}
      {tab === 'teaching' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {teachingData.length === 0 ? (
            <div style={styles.emptyState}>No chart grading data yet.</div>
          ) : (() => {
            const labels = Object.keys(TEACHING_LABEL_META)
            const filterOptions = ['All', ...labels]
            const filtered = teachingFilter === 'All' ? teachingData : teachingData.filter((c: any) => c.teaching_label === teachingFilter)
            const grouped: Record<string, any[]> = {}
            teachingData.forEach((c: any) => {
              if (!grouped[c.teaching_label]) grouped[c.teaching_label] = []
              grouped[c.teaching_label].push(c)
            })
            const summaryData = labels.map(l => ({ label: l, count: grouped[l]?.length || 0 })).filter(d => d.count > 0)
            return (
              <>
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 16 }}>Chart Teaching Value Distribution</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={summaryData} margin={{ left: 10, right: 20, top: 4, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                      <Bar dataKey="count" name="Charts" radius={[4, 4, 0, 0]}>
                        {summaryData.map((entry: any, i: number) => {
                          const meta = TEACHING_LABEL_META[entry.label]
                          return <Cell key={i} fill={meta?.color || '#6b7280'} />
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {filterOptions.map(opt => (
                    <button key={opt} onClick={() => setTeachingFilter(opt)}
                      style={{ padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        background: teachingFilter === opt ? '#4f46e5' : '#f3f4f6',
                        color: teachingFilter === opt ? '#fff' : '#374151',
                        border: teachingFilter === opt ? '1px solid #4f46e5' : '1px solid #e5e7eb' }}>
                      {opt}{opt !== 'All' && grouped[opt] ? ` (${grouped[opt].length})` : ''}
                    </button>
                  ))}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
                  {filtered.map((c: any, i: number) => {
                    const meta = TEACHING_LABEL_META[c.teaching_label] || { color: '#374151', bg: '#f9fafb', desc: '' }
                    return (
                      <div key={i} style={{ background: meta.bg, border: `1px solid ${meta.color}30`, borderRadius: 8, padding: '12px 14px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <span style={{ fontWeight: 700, fontSize: 13, color: '#111' }}>{c.chart_number}</span>
                          <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: '#fff', border: `1px solid ${meta.color}40`, borderRadius: 10, padding: '2px 8px' }}>{c.teaching_label}</span>
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{c.specialty} · {c.category}</div>
                        <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
                          <span><b style={{ color: '#111' }}>{c.attempt_count}</b> attempts</span>
                          <span><b style={{ color: c.avg_score >= 80 ? '#16a34a' : c.avg_score >= 60 ? '#d97706' : '#dc2626' }}>{c.avg_score}%</b> avg</span>
                          <span><b style={{ color: c.pass_rate >= 80 ? '#16a34a' : c.pass_rate >= 60 ? '#d97706' : '#dc2626' }}>{c.pass_rate}%</b> pass</span>
                        </div>
                        {c.error_variety > 0 && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{c.error_variety} distinct error type{c.error_variety > 1 ? 's' : ''}</div>}
                      </div>
                    )
                  })}
                </div>
                {filtered.length === 0 && <div style={styles.emptyState}>No charts in this category.</div>}
              </>
            )
          })()}
        </div>
      )}

      {/* ── E: Coder Matrix ──────────────────────────────────────────────────── */}
      {tab === 'matrix' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!matrixData ? (
            <div style={styles.emptyState}>Loading…</div>
          ) : matrixData.coders.length === 0 ? (
            <div style={styles.emptyState}>No closed batch results yet — close a batch to see the coder matrix.</div>
          ) : (
            <>
              <div style={{ fontSize: 13, color: '#6b7280' }}>
                Cross-batch performance grid — each cell shows the coder's avg score for that batch. Only closed batches are shown.
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '7px 12px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', fontWeight: 700, color: '#374151' }}>Coder</th>
                      {matrixData.batches.map((b: any) => (
                        <th key={b.id} style={{ padding: '7px 10px', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', textAlign: 'center', fontWeight: 600, color: '#374151', minWidth: 80 }}>
                          <div>{b.name.length > 14 ? b.name.slice(0, 14) + '…' : b.name}</div>
                          <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af' }}>{b.closed_at ? new Date(b.closed_at).toLocaleDateString() : ''}</div>
                        </th>
                      ))}
                      <th style={{ padding: '7px 10px', background: '#f1f5f9', borderBottom: '2px solid #e5e7eb', textAlign: 'center', fontWeight: 700, color: '#374151', minWidth: 70 }}>Overall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matrixData.coders.map((coder: string) => {
                      const coderCells = matrixData.cells.filter((c: any) => c.coder_name === coder)
                      const allScores = coderCells.filter((c: any) => c.avg_score != null).map((c: any) => c.avg_score)
                      const overall = allScores.length ? Math.round(allScores.reduce((a: number, b: number) => a + b, 0) / allScores.length) : null
                      const cellMap: Record<number, any> = {}
                      coderCells.forEach((c: any) => { cellMap[c.batch_id] = c })
                      return (
                        <tr key={coder}>
                          <td style={{ padding: '7px 12px', fontWeight: 600, borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap', color: '#111' }}>{coder}</td>
                          {matrixData.batches.map((b: any) => {
                            const cell = cellMap[b.id]
                            const score = cell?.avg_score
                            const bg = score == null ? '#f9fafb' : score >= 80 ? '#dcfce7' : score >= 60 ? '#fef3c7' : '#fee2e2'
                            const color = score == null ? '#9ca3af' : score >= 80 ? '#166534' : score >= 60 ? '#92400e' : '#991b1b'
                            return (
                              <td key={b.id} style={{ padding: '7px 10px', textAlign: 'center', background: bg, color, fontWeight: 700, borderBottom: '1px solid #f3f4f6', borderLeft: '1px solid #f3f4f6' }}>
                                {score != null ? (
                                  <div>
                                    <div>{score}%</div>
                                    {cell?.chart_count != null && <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>{cell.chart_count} charts</div>}
                                  </div>
                                ) : '—'}
                              </td>
                            )
                          })}
                          <td style={{ padding: '7px 10px', textAlign: 'center', background: overall == null ? '#f9fafb' : overall >= 80 ? '#bbf7d0' : overall >= 60 ? '#fde68a' : '#fecaca', color: overall == null ? '#9ca3af' : overall >= 80 ? '#14532d' : overall >= 60 ? '#78350f' : '#7f1d1d', fontWeight: 800, borderBottom: '1px solid #f3f4f6', borderLeft: '2px solid #e5e7eb' }}>
                            {overall != null ? `${overall}%` : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: 11, color: '#6b7280' }}>Green ≥80% · Yellow 60–79% · Red &lt;60%</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function round1(n: number) { return Math.round(n * 10) / 10 }


// ── Insights Panel (A + B) ────────────────────────────────────────────────────

function InsightsPanel({ insights, onClose }: { insights: any; onClose: () => void }) {
  const { batch_summary: bs, team_errors: te, category_performance: cp, chart_signals: cs, coder_insights: ci, is_ip } = insights
  const [expandedCoder, setExpandedCoder] = useState<string | null>(null)

  function buildCopyText() {
    const lines: string[] = [
      `BATCH INSIGHTS — ${insights.batch_name}`,
      `Specialty: ${insights.specialty}`,
      '',
      `SUMMARY`,
      `Pass Rate: ${bs.pass_rate}% (${bs.passed}/${bs.total_graded} passed)${bs.pass_rate_delta != null ? `  vs prior batch: ${bs.pass_rate_delta > 0 ? '+' : ''}${bs.pass_rate_delta}%` : ''}`,
      `Avg Score: ${bs.avg_score}%`,
      '',
    ]
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

  const ISSUE_COLORS: Record<string, string> = {
    Missed: '#dc2626', Over_coded: '#d97706', Wrong_Code: '#7c3aed',
    Wrong_POA: '#0891b2', Wrong_Modifier: '#6b7280',
  }

  return (
    <div style={{ background: '#f8faff', border: '1.5px solid #a5b4fc', borderRadius: 12, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
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

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
        {[
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

      {/* Two-column: error patterns + category performance */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Error patterns */}
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
                    {te.by_issue_type.map((e: any) => (
                      <Cell key={e.type} fill={ISSUE_COLORS[e.type] || '#6b7280'} />
                    ))}
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

        {/* Category performance */}
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 12 }}>Category Performance</div>
          {cp.length === 0 ? (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>No data</div>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(140, cp.length * 40)}>
              <BarChart data={cp} layout="vertical" margin={{ left: 8, right: 40, top: 2, bottom: 2 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="category" width={100} tick={{ fontSize: 11, fontWeight: 600 }} />
                <Tooltip formatter={(v: any, name: string, p: any) => [
                  `${v}% avg · ${p.payload.pass_rate}% pass rate · ${p.payload.attempt_count} attempts`,
                  'Avg Score'
                ]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="avg_score" radius={[0, 6, 6, 0]}>
                  {cp.map((c: any) => (
                    <Cell key={c.category} fill={c.avg_score < 60 ? '#dc2626' : c.avg_score < 80 ? '#d97706' : '#16a34a'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Chart signals */}
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

      {/* Per-coder insights */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#111', marginBottom: 10 }}>Per-Coder Insights</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ci.map((c: any) => (
            <div key={c.coder_name} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', cursor: 'pointer' }}
                onClick={() => setExpandedCoder(expandedCoder === c.coder_name ? null : c.coder_name)}>
                <span style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>{c.coder_name}</span>
                <span style={{ fontSize: 18, fontWeight: 800, color: c.avg_score >= 80 ? '#16a34a' : '#dc2626' }}>{c.avg_score}%</span>
                {c.score_delta != null && (
                  <span style={{ fontSize: 12, fontWeight: 700, color: deltaColor(c.score_delta) }}>{deltaLabel(c.score_delta)}</span>
                )}
                <span style={{ fontSize: 11, color: '#6b7280' }}>
                  {c.vs_team_avg > 0 ? '+' : ''}{c.vs_team_avg}% vs team
                </span>
                {c.dominant_weakness && (
                  <span style={{ fontSize: 11, fontWeight: 700, background: '#fef3c7', color: '#92400e', padding: '2px 9px', borderRadius: 10 }}>
                    {c.dominant_weakness} weakness
                  </span>
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


// ── Styles ────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', position: 'sticky', top: 0, zIndex: 10 },
  topLeft: { display: 'flex', alignItems: 'center', gap: 14 },
  topRight: { display: 'flex', gap: 10, alignItems: 'center' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 13, padding: '4px 8px', borderRadius: 6 },
  title: { fontWeight: 800, fontSize: 18, color: '#0f766e', letterSpacing: -0.5 },
  navBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  content: { maxWidth: 1000, margin: '0 auto', padding: '28px 24px' },
  center: { display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 },
  section: { display: 'flex', flexDirection: 'column', gap: 18 },
  sectionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  sectionTitle: { fontSize: 18, fontWeight: 800, color: '#111', letterSpacing: -0.3 },
  statsRow: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 14, marginBottom: 8 },
  statCard: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 18px', textAlign: 'center' },
  statValue: { fontSize: 28, fontWeight: 800, color: '#111', letterSpacing: -1 },
  statLabel: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  batchList: { display: 'flex', flexDirection: 'column', gap: 8 },
  batchRow: { display: 'flex', alignItems: 'center', gap: 0, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden', cursor: 'pointer', transition: 'box-shadow 0.15s' },
  batchAccent: { width: 5, alignSelf: 'stretch', flexShrink: 0 },
  batchInfo: { flex: 1, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 5 },
  batchName: { fontWeight: 700, fontSize: 15, color: '#111' },
  batchMeta: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  metaText: { fontSize: 12, color: '#6b7280' },
  badge: { display: 'inline-flex', alignItems: 'center', fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: '#f3f4f6', color: '#374151' },
  statusPill: { fontSize: 12, fontWeight: 700, padding: '4px 14px', borderRadius: 20, border: '1.5px solid', marginRight: 14, whiteSpace: 'nowrap' as const },
  empty: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '48px 0', color: '#9ca3af' },
  formGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 },
  formGroup: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: 13, fontWeight: 600, color: '#374151' },
  hint: { fontSize: 11, fontWeight: 400, color: '#9ca3af' },
  input: { padding: '9px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none' },
  select: { padding: '9px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, background: '#fff' },
  textarea: { padding: '9px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, resize: 'vertical' as const, fontFamily: 'inherit' },
  chipRow: { display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  chip: { padding: '5px 14px', borderRadius: 20, border: '1.5px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  chipActive: { padding: '5px 14px', borderRadius: 20, border: '1.5px solid #0f766e', background: '#ccfbf1', color: '#0f766e', cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  actionRow: { display: 'flex', flexWrap: 'wrap', gap: 10 },
  primaryBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 18px', background: '#0f766e', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  outlineBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', background: '#fff', color: '#374151', border: '1.5px solid #d1d5db', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  infoBox: { background: '#f0fdfa', border: '1px solid #99f6e4', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#134e4a' },
  warnBox: { background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#78350f' },
  helpText: { fontSize: 13, color: '#6b7280', lineHeight: 1.6, margin: 0 },
  table: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' },
  tableHeader: { display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', padding: '10px 16px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb' },
  tableRow: { display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', padding: '12px 16px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center' },
  chartDetail: { background: '#f9fafb', borderTop: '1px solid #e5e7eb', padding: '8px 16px 8px 32px', display: 'flex', flexDirection: 'column', gap: 6 },
  chartDetailRow: { display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 12, padding: '6px 0', borderBottom: '1px solid #e5e7eb' },
  fbList: { width: '100%', display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4 },
  fbRow: { display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', padding: '3px 0' },
  fbSection: { fontSize: 11, fontWeight: 700, background: '#dbeafe', color: '#1d4ed8', padding: '2px 8px', borderRadius: 10 },
  fbIssue: { fontSize: 11, fontWeight: 700, background: '#fee2e2', color: '#dc2626', padding: '2px 8px', borderRadius: 10 },
  drgCard: { background: '#fff', border: '1.5px solid #e5e7eb', borderRadius: 10, padding: 18, display: 'flex', flexDirection: 'column', gap: 12 },
  drgHeader: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 },
  drgActions: { display: 'flex', gap: 12 },
  coderTable: { border: '1px solid #d1fae5', borderRadius: 8, overflow: 'hidden', marginTop: 8 },
  coderTableHeader: { display: 'grid', gridTemplateColumns: '1fr 140px 32px', padding: '8px 14px', background: '#f0fdf4', fontSize: 11, fontWeight: 700, color: '#065f46', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #d1fae5' },
  coderTableRow: { display: 'grid', gridTemplateColumns: '1fr 140px 32px', padding: '8px 14px', borderBottom: '1px solid #f0fdf4', fontSize: 13, alignItems: 'center' },
  removeCoder: { border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14, padding: 0, lineHeight: 1 },
  modeToggle: { display: 'flex', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden' },
  modeTab: { padding: '5px 14px', border: 'none', background: '#fff', fontSize: 12, fontWeight: 600, color: '#6b7280', cursor: 'pointer' },
  modeTabActive: { padding: '5px 14px', border: 'none', background: '#4f46e5', fontSize: 12, fontWeight: 600, color: '#fff', cursor: 'pointer' },
  chartPickerHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  chartSearchRow: { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' as const },
  chartPickerList: { border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', maxHeight: 320, overflowY: 'auto' as const },
  chartPickerListHeader: { display: 'grid', gridTemplateColumns: '110px 1fr 120px 32px', padding: '7px 14px', background: '#f9fafb', fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #e5e7eb', position: 'sticky' as const, top: 0 },
  chartPickerRow: { display: 'grid', gridTemplateColumns: '110px 1fr 120px 32px', padding: '9px 14px', borderBottom: '1px solid #f3f4f6', fontSize: 13, alignItems: 'center', cursor: 'pointer' },
  chartPickerNum: { fontWeight: 700, color: '#1e40af' },
  chartPickerCat: { color: '#374151' },
  chartPickerDiff: { color: '#6b7280', fontSize: 12 },
  clearSmallBtn: { border: 'none', background: 'none', color: '#dc2626', fontSize: 12, cursor: 'pointer', padding: 0 },
  quickAddRow: { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 },
  configSection: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 },
  configSectionTitle: { fontSize: 14, fontWeight: 700, color: '#111' },
  weightGrid: { display: 'flex', gap: 16, flexWrap: 'wrap' as const },
  // Scoring method selector (batch creation)
  methodOption: { display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: '10px 12px', background: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' },
  methodLabel: { fontSize: 13, fontWeight: 700, color: '#111', display: 'flex', alignItems: 'center', gap: 8 },
  methodBadge: { fontSize: 10, fontWeight: 700, background: '#d1fae5', color: '#065f46', padding: '2px 8px', borderRadius: 10, letterSpacing: 0.3 },
  methodDesc: { fontSize: 12, color: '#6b7280', marginTop: 2, lineHeight: 1.5 },
  // DPO accuracy panel in results
  dpoPanel: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '12px 16px', marginBottom: 10 },
  dpoPanelTitle: { fontSize: 12, fontWeight: 700, color: '#1d4ed8', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 },
  dpoSupBadge: { fontSize: 10, fontWeight: 700, background: '#dbeafe', color: '#1d4ed8', padding: '2px 8px', borderRadius: 10, letterSpacing: 0.3 },
  dpoPanelRow: { display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' as const },
  dpoDivider: { width: 1, height: 36, background: '#bfdbfe', margin: '0 4px' },
  // Batch management — cycles
  cycleSection: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 },
  cycleRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' },
  cycleBadge: { fontSize: 11, fontWeight: 800, background: '#dbeafe', color: '#1d4ed8', padding: '3px 10px', borderRadius: 20, whiteSpace: 'nowrap' as const },
  allocationPanel: { background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: 10, padding: '16px 18px', marginBottom: 10 },
  noteRow: { display: 'flex', alignItems: 'flex-start', gap: 12, padding: '8px 0', borderBottom: '1px solid #f3f4f6', fontSize: 13 },
  emptyState: { fontSize: 13, color: '#9ca3af', padding: '20px 0', textAlign: 'center' as const },
  dropzone: { border: '2px dashed #d1d5db', borderRadius: 10, padding: '28px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, cursor: 'pointer', background: '#fafafa' },
}
