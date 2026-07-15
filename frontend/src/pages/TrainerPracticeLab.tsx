import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { listBatches, getPLAnalyticsOverview, getScoringConfigs } from '../api'
import { HomeView } from './practicelab/HomeView'
import { AnswerKeysView } from './practicelab/AnswerKeysView'
import { CreateBatchView } from './practicelab/CreateBatchView'
import { BatchDetailView } from './practicelab/BatchDetailView'
import { DRGReviewView } from './practicelab/DRGReviewView'
import { ResultsView } from './practicelab/ResultsView'
import { ScoringConfigView } from './practicelab/ScoringConfigView'
import { SelfPracticeView } from './practicelab/SelfPracticeView'
import { PLAnalyticsView } from './practicelab/PLAnalyticsView'
import styles from './practicelab/styles'

type Tab = 'home' | 'answer-keys' | 'self-practice' | 'analytics' | 'scoring-config'
type View = Tab | 'create-batch' | 'create-direct' | 'batch-detail' | 'drg-review' | 'results'

const TABS: { key: Tab; label: string }[] = [
  { key: 'home',           label: 'Batches' },
  { key: 'answer-keys',    label: 'Answer Keys' },
  { key: 'self-practice',  label: 'Self Practice' },
  { key: 'analytics',      label: 'Analytics' },
  { key: 'scoring-config', label: 'Config' },
]

export function TrainerPracticeLab() {
  const navigate = useNavigate()
  const [view, setView]                     = useState<View>('home')
  const [batches, setBatches]               = useState<any[]>([])
  const [directAssignments, setDirectAssignments] = useState<any[]>([])
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [lastBatch, setLastBatch]           = useState<{ id: number; name: string } | null>(null)
  const [overview, setOverview]             = useState<any>(null)
  const [scoringCfg, setScoringCfg]         = useState<any>(null)
  const [loading, setLoading]               = useState(false)

  useEffect(() => {
    loadHome()
    getScoringConfigs().then(setScoringCfg).catch(() => {})
  }, [])

  async function loadHome() {
    setLoading(true)
    try {
      const [b, da, ov] = await Promise.all([
        listBatches(),
        listBatches(undefined, undefined, true),
        getPLAnalyticsOverview(),
      ])
      setBatches(b)
      setDirectAssignments(da)
      setOverview(ov)
    } catch { toast.error('Failed to load batches') }
    finally { setLoading(false) }
  }

  function openBatch(id: number) {
    const b = batches.find((x: any) => x.id === id) || directAssignments.find((x: any) => x.id === id)
    setSelectedBatchId(id)
    if (b) setLastBatch({ id, name: b.name })
    setView('batch-detail')
  }

  const statusColor = (s: string) => ({ Open: '#2563eb', Closed: '#16a34a' }[s] || '#6b7280')

  // Which tab is "active" — drilldown views belong to 'home'
  const activeTab: Tab = (['home', 'answer-keys', 'self-practice', 'analytics', 'scoring-config'] as Tab[]).includes(view as Tab)
    ? (view as Tab)
    : 'home'

  const isDrilldown = !(['home', 'answer-keys', 'self-practice', 'analytics', 'scoring-config'] as string[]).includes(view)

  return (
    <div style={styles.container}>
      {/* ── Top bar ── */}
      <div style={styles.topBar}>
        <div style={styles.topLeft}>
          <button style={styles.backBtn} onClick={() => navigate('/trainer')}>
            <ChevronLeft size={18} /> Trainer Home
          </button>
          <span style={styles.title}>PracticeLab</span>
        </div>

        <div style={styles.topRight}>
          {isDrilldown ? (
            // Inside batch detail / create / results — show back + last batch shortcut
            <>
              <button style={styles.navBtn} onClick={() => { setView('home'); loadHome() }}>
                ← All Batches
              </button>
              {lastBatch && (
                <button style={{ ...styles.navBtn, color: '#4f46e5', borderColor: '#c7d2fe' }}
                  onClick={() => openBatch(lastBatch.id)}>
                  ↩ {lastBatch.name}
                </button>
              )}
            </>
          ) : (
            // Primary create actions — always visible on tab views
            <>
              <button
                style={{ ...styles.navBtn, color: '#4f46e5', borderColor: '#c7d2fe' }}
                onClick={() => setView('create-direct')}
              >
                <Zap size={15} /> Direct Assignment
              </button>
              <button
                style={{ ...styles.navBtn, background: '#0f766e', color: '#fff', border: 'none' }}
                onClick={() => setView('create-batch')}
              >
                <Plus size={15} /> New Batch
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Tab bar (hidden during drilldown views) ── */}
      {!isDrilldown && (
        <div style={s.tabBar}>
          {TABS.map(t => (
            <button
              key={t.key}
              style={{ ...s.tab, ...(activeTab === t.key ? s.tabActive : {}) }}
              onClick={() => { setView(t.key); if (t.key === 'home') loadHome() }}
            >
              {t.label}
              {activeTab === t.key && <span style={s.tabUnderline} />}
            </button>
          ))}
        </div>
      )}

      {/* ── Content ── */}
      <div style={styles.content}>
        {view === 'home' && (
          <HomeView
            batches={batches} directAssignments={directAssignments}
            overview={overview} loading={loading}
            onOpen={openBatch} statusColor={statusColor}
            onCreateBatch={() => setView('create-batch')}
            onCreateDirect={() => setView('create-direct')}
          />
        )}
        {view === 'answer-keys'    && <AnswerKeysView />}
        {view === 'self-practice'  && <SelfPracticeView />}
        {view === 'analytics'      && <PLAnalyticsView onOpenBatch={(id: number) => { setSelectedBatchId(id); setView('batch-detail') }} />}
        {view === 'scoring-config' && <ScoringConfigView />}
        {view === 'create-batch' && (
          <CreateBatchView
            onCreated={(id: number) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }}
            scoringCfg={scoringCfg}
          />
        )}
        {view === 'create-direct' && (
          <CreateBatchView
            directMode
            onCreated={(id: number) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }}
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
        {view === 'results' && selectedBatchId && <ResultsView batchId={selectedBatchId} />}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  tabBar: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 0,
    padding: '0 24px',
    background: 'rgba(255,255,255,0.6)',
    borderBottom: '1px solid #e5e7eb',
    backdropFilter: 'blur(8px)',
  },
  tab: {
    position: 'relative',
    padding: '11px 18px 10px',
    fontSize: 13,
    fontWeight: 600,
    color: '#6b7280',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
    transition: 'color 0.15s',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 0,
  },
  tabActive: {
    color: '#0f766e',
    borderBottom: '2px solid #0f766e',
  },
  tabUnderline: {
    display: 'none', // handled by borderBottom on tabActive
  },
}
