import { useState, useEffect, useRef } from 'react'
import { Download, Upload, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getPoolPreview, parseCoderList, createBatch, downloadCoderListTemplate } from '../../api'
import { trainerName, SPECIALTIES, DIFFICULTIES } from './shared'
import styles from './styles'

export function CreateBatchView({ onCreated, scoringCfg, directMode: directModeProp }: { onCreated: (id: number) => void; scoringCfg?: any; directMode?: boolean }) {
  const [directMode, setDirectMode] = useState(directModeProp ?? false)
  const [form, setForm] = useState({
    name: '', specialty: 'IP-DRG', categories: '', difficulties: [] as string[],
    charts_per_coder: directModeProp ? 1 : 5, use_weighted: true, use_dpo: false,
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
    if (!form.name.trim()) return toast.error(directMode ? 'Assignment name is required' : 'Batch name is required')
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
        is_direct_assignment: directMode,
      })
      if (res.warning) toast(res.warning, { icon: '⚠️', duration: 5000 })
      toast.success(directMode ? 'Assignment created — pick charts next' : 'Batch created — run an allocation cycle to assign charts')
      onCreated(res.batch_id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create batch')
    } finally { setCreating(false) }
  }

  const isIP = ['IP-DRG'].includes(form.specialty)
  const activeCfg = scoringCfg ? (isIP ? scoringCfg.IP : scoringCfg.OP) : null

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>{directMode ? 'New Direct Assignment' : 'Create New Batch'}</div>

      {directModeProp === undefined && (
        <div style={styles.modeToggle}>
          <button style={!directMode ? styles.modeTabActive : styles.modeTab} onClick={() => setDirectMode(false)}>Formal Batch</button>
          <button style={directMode ? styles.modeTabActive : styles.modeTab} onClick={() => { setDirectMode(true); setForm(f => ({ ...f, charts_per_coder: 1 })) }}>Direct Assignment</button>
        </div>
      )}

      <div style={styles.infoBox}>
        {directMode
          ? 'Assign specific chart(s) to one or more coders without the multi-day batch/cycle workflow — useful for one-off practice or targeted reinforcement. Results are graded and tracked in analytics exactly like a regular batch.'
          : <>Batch stays <strong>Open</strong> until you close it. Charts are assigned through allocation cycles — run one now, or more later as the practice phase progresses.</>}
      </div>

      <div style={styles.formGrid}>
        <div style={styles.formGroup}>
          <label style={styles.label}>{directMode ? 'Assignment Name *' : 'Batch Name *'}</label>
          <input style={styles.input} value={form.name} placeholder={directMode ? 'e.g. Sepsis Refresher — Harish' : 'e.g. June IP Assessment'}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <div style={styles.formGroup}>
          <label style={styles.label}>Specialty *</label>
          <select style={styles.select} value={form.specialty} onChange={e => setForm(f => ({ ...f, specialty: e.target.value }))}>
            {SPECIALTIES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div style={styles.formGroup}>
          <label style={styles.label}>{directMode ? 'Chart Pool — Category Filter' : 'Default Pool — Category Filter'} <span style={styles.hint}>(comma-separated)</span></label>
          <input style={styles.input} value={form.categories} placeholder="e.g. Sepsis, Cardiac, Trauma"
            onChange={e => setForm(f => ({ ...f, categories: e.target.value }))} />
        </div>
        <div style={styles.formGroup}>
          <label style={styles.label}>{directMode ? 'Chart Pool — Difficulty Filter' : 'Default Pool — Difficulty Filter'}</label>
          <div style={styles.chipRow}>
            {DIFFICULTIES.map(d => (
              <button key={d} style={form.difficulties.includes(d) ? styles.chipActive : styles.chip}
                onClick={() => toggleDifficulty(d)}>{d}</button>
            ))}
            <span style={styles.hint}>None = all</span>
          </div>
        </div>
        <div style={styles.formGroup}>
          <label style={styles.label}>{directMode ? 'Charts per Coder' : 'Default Charts per Coder'} <span style={styles.hint}>(overridable per cycle)</span></label>
          <input type="number" min={1} max={20} style={{ ...styles.input, width: 80 }}
            value={form.charts_per_coder}
            onChange={e => setForm(f => ({ ...f, charts_per_coder: parseInt(e.target.value) || 1 }))} />
        </div>
      </div>
      {directMode && (
        <div style={styles.infoBox}>
          After creating this assignment, use <strong>Allocation</strong> on the next screen to pick charts — choose <strong>Random</strong> to pull from the pool above, or <strong>Manual</strong> to search and select specific chart number(s) for each coder.
        </div>
      )}

      {pool && (
        <div style={styles.infoBox}>
          <strong>Pool preview:</strong> {pool.total_matching} matching charts · {pool.with_answer_key} have answer keys
          {pool.with_answer_key === 0 && <span style={{ color: '#dc2626', marginLeft: 8 }}>⚠ Upload answer keys before running allocation.</span>}
        </div>
      )}

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

      <div style={styles.formGroup}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <label style={styles.label}>Coders *</label>
          <div style={styles.modeToggle}>
            <button style={coderMode === 'quick' ? styles.modeTabActive : styles.modeTab} onClick={() => setCoderMode('quick')}>Quick Add</button>
            <button style={coderMode === 'upload' ? styles.modeTabActive : styles.modeTab} onClick={() => setCoderMode('upload')}>Upload List</button>
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
            <button style={styles.outlineBtn} onClick={downloadCoderListTemplate}><Download size={15} /> Download Template</button>
            <label style={parsing ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn}>
              {parsing ? <><Loader size={14} /> Parsing...</> : <><Upload size={15} /> Upload Filled List</>}
              <input ref={coderFileRef} type="file" accept=".xlsx" style={{ display: 'none' }} onChange={handleCoderUpload} disabled={parsing} />
            </label>
          </div>
        )}
        {coders.length > 0 && (
          <>
            <div style={styles.coderTable}>
              <div style={styles.coderTableHeader}><span>Coder Name</span><span>Emp ID</span><span></span></div>
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

      <button style={creating ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn} disabled={creating} onClick={handleCreate}>
        {creating ? <><Loader size={14} /> Creating...</> : directMode ? 'Create Assignment' : 'Open Batch'}
      </button>
    </div>
  )
}
