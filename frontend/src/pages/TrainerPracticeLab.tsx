import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus, Zap, Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { listBatches, getPLAnalyticsOverview, getScoringConfigs } from '../api'
import { HomeView } from './practicelab/HomeView'
import { AnswerKeysView } from './practicelab/AnswerKeysView'
import { CreateBatchView } from './practicelab/CreateBatchView'
import { BatchDetailView } from './practicelab/BatchDetailView'
import { DRGReviewView } from './practicelab/DRGReviewView'
import { ResultsView } from './practicelab/ResultsView'
import { ScoringConfigView } from './practicelab/ScoringConfigView'
import { PLAnalyticsView } from './practicelab/PLAnalyticsView'
import styles from './practicelab/styles'

type Tab = 'home' | 'answer-keys' | 'analytics'
type View = Tab | 'scoring-config' | 'create-batch' | 'create-direct' | 'batch-detail' | 'drg-review' | 'results'

const TABS: { key: Tab; label: string }[] = [
  { key: 'home',          label: 'Batches' },
  { key: 'answer-keys',   label: 'Answer Keys' },
  { key: 'analytics',     label: 'Analytics' },
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

  /**
   * Where "Back" goes.
   *
   * The back button used to be hardcoded to the Batches list, so opening a
   * batch from Analytics and coming back dropped you somewhere you had never
   * been — and the tab, scope and filters you had set up were gone. Same for
   * Results and DRG Review, which returned to the list rather than to the
   * batch you were working inside.
   *
   * A stack of where you actually came from, rather than one assumed origin.
   */
  const [navStack, setNavStack] = useState<View[]>([])

  const VIEW_LABELS: Record<string, string> = {
    'home': 'All Batches',
    'analytics': 'Analytics',
    'answer-keys': 'Answer Keys',
    'batch-detail': 'Batch',
    'results': 'Results',
    'drg-review': 'DRG Review',
    'scoring-config': 'Scoring Config',
  }

  function go(next: View) {
    setNavStack(s => [...s, view])
    setView(next)
  }

  function goBack() {
    const prev = (navStack[navStack.length - 1] || 'home') as View
    setNavStack(s => s.slice(0, -1))
    setView(prev)
    if (prev === 'home') loadHome()
  }

  const backTarget = (navStack[navStack.length - 1] || 'home') as View

  function openBatch(id: number) {
    const b = batches.find((x: any) => x.id === id) || directAssignments.find((x: any) => x.id === id)
    setSelectedBatchId(id)
    if (b) setLastBatch({ id, name: b.name })
    go('batch-detail')
  }

  const statusColor = (s: string) => ({ Open: '#2563eb', Closed: '#16a34a' }[s] || '#6b7280')

  // Which tab is "active" — drilldown views belong to 'home'
  const activeTab: Tab = (['home', 'answer-keys', 'analytics'] as Tab[]).includes(view as Tab)
    ? (view as Tab)
    : 'home'

  const isDrilldown = !(['home', 'answer-keys', 'analytics'] as string[]).includes(view)

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
              <button style={styles.navBtn} onClick={goBack}>
                ← Back to {VIEW_LABELS[backTarget] || 'All Batches'}
              </button>
              {/* The list stays reachable in one click even when Back leads
                  somewhere else, so the shortcut is not lost to the fix. */}
              {backTarget !== 'home' && (
                <button style={styles.navBtn} onClick={() => { setNavStack([]); setView('home'); loadHome() }}>
                  All Batches
                </button>
              )}
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
                onClick={() => go('create-direct')}
              >
                <Zap size={15} /> Direct Assignment
              </button>
              <button
                style={{ ...styles.navBtn, background: '#0f766e', color: '#fff', border: 'none' }}
                onClick={() => go('create-batch')}
              >
                <Plus size={15} /> New Batch
              </button>
            </>
          )}
          {/* Scoring config gear — always accessible */}
          <button
            title="Scoring Config"
            style={{
              ...styles.navBtn,
              padding: '6px 10px',
              color: view === 'scoring-config' ? '#0f766e' : '#9ca3af',
              borderColor: view === 'scoring-config' ? '#0f766e' : '#e5e7eb',
              background: view === 'scoring-config' ? '#f0fdf4' : 'transparent',
            }}
            onClick={() => { setNavStack([]); setView(view === 'scoring-config' ? 'home' : 'scoring-config') }}
          >
            <Settings size={15} />
          </button>
        </div>
      </div>

      {/* ── Tab bar (hidden during drilldown views) ── */}
      {!isDrilldown && (
        <div style={s.tabBar}>
          {TABS.map(t => (
            <button
              key={t.key}
              style={{ ...s.tab, ...(activeTab === t.key ? s.tabActive : {}) }}
              onClick={() => { setNavStack([]); setView(t.key); if (t.key === 'home') loadHome() }}
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
            onCreateBatch={() => go('create-batch')}
          />
        )}
        {view === 'answer-keys'    && <AnswerKeysView />}
        {view === 'analytics'      && <PLAnalyticsView onOpenBatch={(id: number) => { setSelectedBatchId(id); go('batch-detail') }} />}
        {view === 'scoring-config' && <ScoringConfigView />}
        {view === 'create-batch' && (
          <CreateBatchView
            onCancel={goBack}
            onCreated={(id: number) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }}
            scoringCfg={scoringCfg}
          />
        )}
        {view === 'create-direct' && (
          <CreateBatchView
            onCancel={goBack}
            directMode
            onCreated={(id: number) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }}
            scoringCfg={scoringCfg}
          />
        )}
        {view === 'batch-detail' && selectedBatchId && (
          <BatchDetailView
            batchId={selectedBatchId}
            onDRGReview={() => go('drg-review')}
            onResults={() => go('results')}
          />
        )}
        {view === 'drg-review' && selectedBatchId && (
          <DRGReviewView batchId={selectedBatchId} onDone={goBack} />
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
