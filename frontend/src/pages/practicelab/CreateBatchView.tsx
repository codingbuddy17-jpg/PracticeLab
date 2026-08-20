import { useState, useEffect, useRef } from 'react'
import { Download, Upload, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { getPoolPreview, parseCoderList, createBatch, downloadCoderListTemplate } from '../../api'
import { CoderPicker } from '../../components/CoderPicker'
import { trainerName, SPECIALTIES, DIFFICULTIES } from './shared'
import styles from './styles'

export function CreateBatchView({ onCreated, onCancel, scoringCfg, directMode: directModeProp }: { onCreated: (id: number) => void; onCancel?: () => void; scoringCfg?: any; directMode?: boolean }) {
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

  /**
   * Is the pool big enough for what is being asked of it?
   *
   * The preview used to report a raw count and leave the arithmetic to the
   * trainer, so an assignment for 8 coders x 5 charts against a pool of 12
   * looked fine on this screen and only revealed the shortfall as a toast
   * after allocation had already run. Everything needed to answer it is on
   * this form; it just was not being asked.
   *
   * Only charts WITH an answer key can be graded, so that is the number that
   * has to cover the requirement — not total_matching.
   */
  const gradable = pool?.with_answer_key ?? 0
  const needed = directMode ? 0 : coders.length * form.charts_per_coder
  // Direct assignment picks charts by hand, so charts-per-coder is a cap
  // rather than a requirement and there is no total to fall short of.
  const shortfall = directMode ? 0 : Math.max(0, needed - gradable)

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
      if (parsed.length === 0) {
        toast.error('No usable coder rows found — check that Name and Emp ID are both filled in below the header row')
      } else {
        toast.success(`${parsed.length} coder(s) loaded`)
      }
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
        use_dpo: dpoAllowed ? form.use_dpo : false,
        is_direct_assignment: directMode,
      })
      if (res.warning) toast(res.warning, { icon: '⚠️', duration: 5000 })
      if (res.skipped_duplicates?.length) toast(`Skipped duplicate coder name(s) or employee ID(s): ${res.skipped_duplicates.join(', ')}`, { icon: '⚠️', duration: 6000 })
      toast.success(directMode ? 'Assignment created — pick charts next' : 'Batch created — run an allocation cycle to assign charts')
      onCreated(res.batch_id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create batch')
    } finally { setCreating(false) }
  }

  const isIP = ['IP-DRG'].includes(form.specialty)
  const isED = ['Edits', 'Denials'].includes(form.specialty)
  const isEM = ['E/M', 'ED Profee'].includes(form.specialty)
  const isEDSP = form.specialty === 'ED Single Path'
  const dpoAllowed = ['IP-DRG', 'ED Facility', 'SDS', 'Surgery', 'Ancillary', 'ED Single Path'].includes(form.specialty)
  const activeCfg = scoringCfg
    ? (isIP ? scoringCfg.IP : isEDSP ? scoringCfg.EDSP : scoringCfg.OP)
    : null

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>{directMode ? 'New Direct Assignment' : 'Create New Batch'}</div>

      {/* "Formal Batch / Direct Assignment" read like two products, and a
          trainer had to already know the difference to choose. They are one
          thing with a scope switch: same creation, same allocation, same access
          codes, same coder form, same grading. What actually differs is whether
          the work counts toward cohort analytics — so that is what the choice
          now says, with the label kept underneath for anyone who knows it. */}
      {directModeProp === undefined && (
        <div style={{ marginBottom: 14 }}>
          <div style={styles.modeToggle}>
            <button style={!directMode ? styles.modeTabActive : styles.modeTab}
              onClick={() => setDirectMode(false)}>
              Counts toward cohort analytics
            </button>
            <button style={directMode ? styles.modeTabActive : styles.modeTab}
              onClick={() => { setDirectMode(true); setForm(f => ({ ...f, charts_per_coder: 1 })) }}>
              Tracked separately
            </button>
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
            {directMode
              ? <><strong>Direct assignment.</strong> Graded and reported exactly like batch work, but kept out of cohort averages and trends so a one-off refresher does not move the team's numbers. Analytics shows it under "Direct Assignments" or "Both".</>
              : <><strong>Batch.</strong> Counts toward team averages, pass rates and trends — the right choice for a cohort assessment everyone sits.</>}
          </div>
        </div>
      )}

      {/* The old copy promised "without the multi-day batch/cycle workflow" and
          the very next screen asked for an allocation cycle. Describe the four
          steps that actually follow, so nothing on the next screen is a
          surprise. */}
      <div style={styles.infoBox}>
        {directMode
          ? <>Graded and tracked in analytics exactly like a regular batch.</>
          : <>Batch stays <strong>Open</strong> until you close it. Charts are assigned through allocation cycles — run one now, or more later as the practice phase progresses.</>}
      </div>

      <div style={styles.formGrid}>
        <div style={styles.formGroup}>
          <label style={styles.label}>{directMode ? 'Assignment Name *' : 'Batch Name *'}</label>
          <input style={styles.input} value={form.name} placeholder={directMode ? 'e.g. Sepsis Refresher — Coder' : 'e.g. June IP Assessment'}
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
          Every coder gets the same charts — minus any already assigned to them.
        </div>
      )}

      {pool && (
        <div style={{
          ...styles.infoBox,
          ...(shortfall > 0
            ? { background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e' }
            : {}),
        }}>
          <div>
            <strong>Pool preview:</strong> {pool.total_matching} matching charts
            {pool.with_answer_key != null && <> · {pool.with_answer_key} with answer keys</>}
          </div>

          {gradable === 0 ? (
            <div style={{ color: '#dc2626', marginTop: 6, fontWeight: 600 }}>
              ⚠ No chart here has an answer key, so nothing can be graded. Upload keys before
              running allocation.
            </div>
          ) : directMode ? null : coders.length === 0 ? (
            <div style={{ marginTop: 6, color: '#6b7280' }}>
              Add coders below to see whether the pool covers them.
            </div>
          ) : shortfall > 0 ? (
            <div style={{ marginTop: 6, fontWeight: 600 }}>
              ⚠ Short by {shortfall}. {coders.length} coder{coders.length === 1 ? '' : 's'} ×{' '}
              {form.charts_per_coder} chart{form.charts_per_coder === 1 ? '' : 's'} ={' '}
              <strong>{needed} needed</strong>, {gradable} gradable available. Reduce charts per
              coder, widen the filters, or upload more answer keys — allocation will otherwise
              assign everyone whatever it can and stop short.
            </div>
          ) : (
            <div style={{ marginTop: 6, color: '#15803d', fontWeight: 600 }}>
              ✓ {coders.length} coder{coders.length === 1 ? '' : 's'} × {form.charts_per_coder}{' '}
              chart{form.charts_per_coder === 1 ? '' : 's'} = {needed} needed. Pool is sufficient.
            </div>
          )}
        </div>
      )}

      <div style={styles.formGroup}>
        <label style={styles.label}>Scoring Method</label>
        {isED ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#fef9c3', border: '1px solid #fde68a', borderRadius: 8 }}>
            <span style={{ fontSize: 16 }}>📋</span>
            <div style={{ fontSize: 13, color: '#92400e' }}>
              <strong>Manual rubric scoring applies for Edits &amp; Denials specialties.</strong>
              <div style={{ fontWeight: 400, marginTop: 2 }}>You score each case on the rubric after submission — there is no auto-grading.</div>
            </div>
          </div>
        ) : isEM ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#ede9fe', border: '1px solid #c4b5fd', borderRadius: 8 }}>
            <span style={{ fontSize: 16 }}>🩺</span>
            <div style={{ fontSize: 13, color: '#5b21b6' }}>
              <strong>E/M MDM scoring applies for this specialty.</strong>
              <div style={{ fontWeight: 400, marginTop: 2 }}>E/M level · COPA / Data Review / Risk · diagnoses · procedure CPTs.</div>
            </div>
          </div>
        ) : isEDSP ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#f3e8ff', border: '1px solid #d8b4fe', borderRadius: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: '#6b21a8' }}>SP</span>
              <div style={{ fontSize: 13, color: '#6b21a8' }}>
                <strong>ED Single Path scoring applies for this specialty.</strong>
                <div style={{ fontWeight: 400, marginTop: 2 }}>Shared Dx, facility and profee levels, additional CPTs. No diagnosis pointers.</div>
              </div>
            </div>
            <label style={styles.methodOption}>
              <input type="checkbox" checked={form.use_weighted}
                disabled={activeCfg ? activeCfg.weighted_enabled === false : false}
                onChange={e => setForm(f => ({ ...f, use_weighted: e.target.checked }))} />
              <div>
                <div style={styles.methodLabel}>Grading Score <span style={styles.methodBadge}>Primary · Pass/Fail</span></div>
                <div style={styles.methodDesc}>Shared Dx, facility level, profee level, and additional CPT weights</div>
              </div>
            </label>
            <label style={styles.methodOption}>
              <input type="checkbox" checked={form.use_dpo}
                disabled={activeCfg ? activeCfg.dpo_enabled === false : false}
                onChange={e => setForm(f => ({ ...f, use_dpo: e.target.checked }))} />
              <div>
                <div style={styles.methodLabel}>Accuracy (DPO) <span style={{ ...styles.methodBadge, background: '#dbeafe', color: '#1d4ed8' }}>Supplementary</span></div>
                <div style={styles.methodDesc}>Defect rate across Dx, facility/profee levels, and CPT opportunities</div>
              </div>
            </label>
            {!form.use_weighted && !form.use_dpo && (
              <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must be selected</div>
            )}
          </div>
        ) : !dpoAllowed ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 800, color: '#475569' }}>OP</span>
            <div style={{ fontSize: 13, color: '#334155' }}>
              <strong>Grading Score applies for this specialty.</strong>
              <div style={{ fontWeight: 400, marginTop: 2 }}>Supplementary accuracy is not used for this specialty.</div>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <label style={styles.methodOption}>
              <input type="checkbox" checked={form.use_weighted}
                disabled={activeCfg ? activeCfg.weighted_enabled === false : false}
                onChange={e => setForm(f => ({ ...f, use_weighted: e.target.checked }))} />
              <div>
                <div style={styles.methodLabel}>Grading Score <span style={styles.methodBadge}>Primary · Pass/Fail</span></div>
                <div style={styles.methodDesc}>{isIP ? 'Category importance (PDx / SDx / PCS / DRG weights)' : 'Category importance (PDx / SDx / CPT weights)'} — drives the official pass/fail verdict</div>
              </div>
            </label>
            <label style={styles.methodOption}>
              <input type="checkbox" checked={form.use_dpo}
                disabled={activeCfg ? activeCfg.dpo_enabled === false : false}
                onChange={e => setForm(f => ({ ...f, use_dpo: e.target.checked }))} />
              <div>
                <div style={styles.methodLabel}>Accuracy (DPO) <span style={{ ...styles.methodBadge, background: '#dbeafe', color: '#1d4ed8' }}>Supplementary</span></div>
                <div style={styles.methodDesc}>Defect rate per code opportunity — shows Dx{isIP ? ', POA' : ''} and procedure accuracy % per coder</div>
              </div>
            </label>
            {!form.use_weighted && !form.use_dpo && (
              <div style={{ color: '#dc2626', fontSize: 12 }}>At least one method must be selected</div>
            )}
          </div>
        )}
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
            {/* Picking an existing coder carries their Emp ID across, so a new
                spelling does not fork the history they already have. */}
            <div style={{ flex: 1 }}>
              <CoderPicker
                value={quickRow.name}
                width="100%"
                allowFreeText
                placeholder="Coder name — search or type a new one"
                onSelect={(name, empId) =>
                  setQuickRow(r => ({ ...r, name, emp_id: empId || r.emp_id }))}
              />
            </div>
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

      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
      <button style={creating ? { ...styles.primaryBtn, opacity: 0.6 } : styles.primaryBtn} disabled={creating} onClick={handleCreate}>
        {creating ? <><Loader size={14} /> Creating...</> : directMode ? 'Create Assignment' : 'Open Batch'}
      </button>
      {onCancel && (
        <button
          style={{ padding: '11px 18px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 8, cursor: creating ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: 13, color: '#6b7280', opacity: creating ? 0.5 : 1 }}
          disabled={creating}
          onClick={onCancel}
        >
          Cancel
        </button>
      )}
      </div>
    </div>
  )
}
