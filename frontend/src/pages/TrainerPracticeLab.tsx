import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus, Upload, Download, FileCheck, BarChart2, Key, Loader, Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  listBatches, createBatch, getPoolPreview, downloadAnswerKeyTemplate,
  uploadAnswerKeys, getBatch, downloadBatchExcel, gradeSubmissions,
  getDRGReview, submitDRGDecision, getBatchResults, downloadBatchResultsExcel,
  getAnswerKeyStatus, getPLAnalyticsOverview,
  downloadCoderListTemplate, parseCoderList,
  getScoringConfigs, updateScoringConfig,
} from '../api'
import { SPECIALTY_COLORS } from '../theme'

type View = 'home' | 'answer-keys' | 'create-batch' | 'batch-detail' | 'drg-review' | 'results' | 'analytics' | 'scoring-config'

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
    getScoringConfigs().then(setScoringCfg).catch(() => {})
  }, [])

  async function loadHome() {
    setLoading(true)
    try {
      const [b, ov] = await Promise.all([listBatches(), getPLAnalyticsOverview()])
      setBatches(b)
      setOverview(ov)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  function openBatch(id: number) {
    setSelectedBatchId(id)
    setView('batch-detail')
  }

  const statusColor = (s: string) => ({
    Draft: '#6b7280', Active: '#2563eb', Grading: '#d97706', Complete: '#16a34a',
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
                  <button style={styles.navBtn} onClick={() => setView('scoring-config')}>
                <Settings size={15} /> Scoring Config
              </button>
              <button style={styles.navBtn} onClick={() => setView('answer-keys')}>
                <Key size={15} /> Answer Keys
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
        {view === 'scoring-config' && <ScoringConfigView />}
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
            { label: 'Complete', value: overview.complete_batches },
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
                    <span style={styles.metaText}>{b.coder_count} coders · {b.charts_per_coder} charts each</span>
                    <span style={styles.metaText}>by {b.created_by}</span>
                    <span style={styles.metaText}>{new Date(b.created_at).toLocaleDateString()}</span>
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
    try { setStatus(await getAnswerKeyStatus(specialty)) } catch { /* ignore */ }
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
    } catch { /* ignore */ }
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

  async function handleCreate() {
    if (!form.name.trim()) return toast.error('Batch name is required')
    if (coders.length === 0) return toast.error('Upload a coder list first')
    if (!pool || pool.with_answer_key === 0) return toast.error('No charts with answer keys match filters')

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
      toast.success(`Batch created — ${res.pool_size} charts in pool`)
      onCreated(res.batch_id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create batch')
    } finally { setCreating(false) }
  }

  const needed = coders.length * form.charts_per_coder
  const available = pool?.with_answer_key || 0

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Create New Batch</div>

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
          <label style={styles.label}>Category Filter <span style={styles.hint}>(comma-separated, OR logic)</span></label>
          <input style={styles.input} value={form.categories}
            placeholder="e.g. Sepsis, Cardiac, Trauma"
            onChange={e => setForm(f => ({ ...f, categories: e.target.value }))} />
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Difficulty Filter</label>
          <div style={styles.chipRow}>
            {DIFFICULTIES.map(d => (
              <button key={d}
                style={form.difficulties.includes(d) ? styles.chipActive : styles.chip}
                onClick={() => toggleDifficulty(d)}>{d}</button>
            ))}
            <span style={styles.hint}>None selected = all difficulties</span>
          </div>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.label}>Charts per Coder</label>
          <input type="number" min={1} max={20} style={{ ...styles.input, width: 80 }}
            value={form.charts_per_coder}
            onChange={e => setForm(f => ({ ...f, charts_per_coder: parseInt(e.target.value) || 1 }))} />
        </div>
      </div>

      {/* Live pool count */}
      {pool && (
        <div style={needed > available && available > 0 ? styles.warnBox : styles.infoBox}>
          <strong>Matching pool:</strong> {pool.total_matching} charts · {pool.with_answer_key} have answer keys
          {needed > available && available > 0 && (
            <span style={{ color: '#b45309', marginLeft: 8 }}>
              ⚠ {coders.length} coders × {form.charts_per_coder} charts = {needed} needed. Some charts will repeat.
            </span>
          )}
          {available === 0 && <span style={{ color: '#dc2626', marginLeft: 8 }}>⚠ No keyed charts — upload answer keys first.</span>}
        </div>
      )}

      {/* Scoring method */}
      <div style={styles.formGroup}>
        <label style={styles.label}>Scoring Method</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={styles.methodOption}>
            <input type="checkbox" checked={form.use_weighted}
              disabled={scoringCfg && !scoringCfg.weighted_enabled}
              onChange={e => setForm(f => ({ ...f, use_weighted: e.target.checked }))} />
            <div>
              <div style={styles.methodLabel}>Weighted Scoring <span style={styles.methodBadge}>Primary · Pass/Fail</span></div>
              <div style={styles.methodDesc}>Category importance (PDx / SDx / PCS / DRG weights) — drives the official pass/fail verdict</div>
            </div>
          </label>
          <label style={styles.methodOption}>
            <input type="checkbox" checked={form.use_dpo}
              disabled={scoringCfg && !scoringCfg.dpo_enabled}
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
        <label style={styles.label}>Coder List *</label>
        <div style={styles.actionRow}>
          <button style={styles.outlineBtn} onClick={downloadCoderListTemplate}>
            <Download size={15} /> Download Template
          </button>
          <label style={parsing ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
            {parsing ? <><Loader size={14} /> Parsing...</> : <><Upload size={15} /> Upload Filled List</>}
            <input ref={coderFileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
              onChange={handleCoderUpload} disabled={parsing} />
          </label>
          {coders.length > 0 && (
            <button style={{ ...styles.outlineBtn, color: '#dc2626', borderColor: '#fca5a5' }}
              onClick={() => setCoders([])}>Clear</button>
          )}
        </div>

        {coders.length > 0 && (
          <div style={styles.coderTable}>
            <div style={styles.coderTableHeader}>
              <span>Coder Name</span><span>Emp ID</span>
            </div>
            {coders.map((c, i) => (
              <div key={i} style={styles.coderTableRow}>
                <span>{c.name}</span>
                <span style={{ fontWeight: 700, color: '#0f766e' }}>{c.emp_id}</span>
              </div>
            ))}
          </div>
        )}
        {coders.length > 0 && <span style={styles.hint}>{coders.length} coder(s) ready</span>}
      </div>

      <button style={creating ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}
        disabled={creating} onClick={handleCreate}>
        {creating ? <><Loader size={14} /> Creating...</> : 'Create Batch & Assign Charts'}
      </button>
    </div>
  )
}

// ── Batch Detail ──────────────────────────────────────────────────────────────

function BatchDetailView({ batchId, onDRGReview, onResults }: any) {
  const [batch, setBatch] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [grading, setGrading] = useState(false)
  const [gradingResult, setGradingResult] = useState<any>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadBatch() }, [batchId])

  async function loadBatch() {
    setLoading(true)
    try { setBatch(await getBatch(batchId)) } catch { /* ignore */ } finally { setLoading(false) }
  }

  async function handleGradeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setGrading(true)
    setGradingResult(null)
    try {
      const res = await gradeSubmissions(batchId, files)
      setGradingResult(res)
      if (res.graded.length) toast.success(`Graded: ${res.graded.length} submission(s)`)
      if (res.errors.length) toast.error(`Errors: ${res.errors.length} file(s) had issues`)
      loadBatch()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Grading failed')
    } finally {
      setGrading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  if (loading) return <div style={styles.center}><Loader size={24} /></div>
  if (!batch) return <div style={styles.center}>Batch not found</div>

  const sc = SPECIALTY_COLORS[batch.specialty as keyof typeof SPECIALTY_COLORS]
  const pendingDRG = batch.coders?.some((c: any) =>
    c.charts?.some((ch: any) => ch.submission_status === 'Submitted')
  ) && batch.status === 'Grading'

  return (
    <div style={styles.section}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <span style={{ ...styles.badge, background: sc?.light || '#f3f4f6', color: sc?.bg || '#374151', fontSize: 13 }}>
          {batch.specialty}
        </span>
        <span style={styles.sectionTitle}>{batch.name}</span>
        <span style={{ fontSize: 12, color: '#6b7280' }}>by {batch.created_by} · {new Date(batch.created_at).toLocaleDateString()}</span>
      </div>

      {/* Action buttons */}
      <div style={styles.actionRow}>
        <button style={styles.outlineBtn} onClick={() => downloadBatchExcel(batchId)}>
          <Download size={15} /> Download Answer Sheets (ZIP)
        </button>
        <label style={grading ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
          {grading ? <><Loader size={14} /> Grading...</> : <><Upload size={15} /> Upload Returned Sheets</>}
          <input ref={fileRef} type="file" accept=".xlsx" multiple style={{ display: 'none' }}
            onChange={handleGradeUpload} disabled={grading} />
        </label>
        {(batch.status === 'Grading' || batch.status === 'Complete') && (
          <>
            {pendingDRG && (
              <button style={{ ...styles.primaryBtn, background: '#d97706' }} onClick={onDRGReview}>
                DRG Review Required
              </button>
            )}
            <button style={styles.outlineBtn} onClick={onResults}>
              <BarChart2 size={15} /> View Results
            </button>
            <button style={styles.outlineBtn} onClick={() => downloadBatchResultsExcel(batchId)}>
              <Download size={15} /> Export Excel
            </button>
          </>
        )}
      </div>

      {/* Grading result summary */}
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

      {/* Coders table */}
      <div style={styles.sectionHeader}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>
          Coders ({batch.coders?.length || 0}) · {batch.charts_per_coder} charts each
        </span>
      </div>

      <div style={styles.table}>
        <div style={styles.tableHeader}>
          <span>Coder</span>
          <span>Excel Generated</span>
          <span>Charts Assigned</span>
          <span>Submitted</span>
        </div>
        {(batch.coders || []).map((c: any) => {
          const submitted = c.charts.filter((ch: any) => ch.submission_status === 'Submitted').length
          return (
            <div key={c.name} style={styles.tableRow}>
              <span style={{ fontWeight: 600 }}>{c.name}</span>
              <span style={{ color: c.excel_generated ? '#16a34a' : '#9ca3af' }}>
                {c.excel_generated ? '✓ Generated' : '—'}
              </span>
              <span>{c.charts.length}</span>
              <span style={{ color: submitted > 0 ? '#16a34a' : '#9ca3af' }}>
                {submitted} / {c.charts.length}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── DRG Review ────────────────────────────────────────────────────────────────

function DRGReviewView({ batchId, onDone }: any) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [decisions, setDecisions] = useState<Record<number, boolean>>({})
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <span style={styles.sectionTitle}>{data.batch_name} — Results</span>
        <button style={styles.outlineBtn} onClick={() => downloadBatchResultsExcel(batchId)}>
          <Download size={15} /> Export Excel
        </button>
      </div>

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
          <div style={styles.statLabel}>Pass Rate</div>
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
  coderTableHeader: { display: 'grid', gridTemplateColumns: '1fr 140px', padding: '8px 14px', background: '#f0fdf4', fontSize: 11, fontWeight: 700, color: '#065f46', textTransform: 'uppercase' as const, letterSpacing: 0.5, borderBottom: '1px solid #d1fae5' },
  coderTableRow: { display: 'grid', gridTemplateColumns: '1fr 140px', padding: '8px 14px', borderBottom: '1px solid #f0fdf4', fontSize: 13 },
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
}
