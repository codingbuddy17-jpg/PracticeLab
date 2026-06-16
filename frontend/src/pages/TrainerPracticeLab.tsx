import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus, BarChart2, Key, Settings, FileCheck } from 'lucide-react'
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

type View = 'home' | 'answer-keys' | 'create-batch' | 'batch-detail' | 'drg-review' | 'results' | 'analytics' | 'scoring-config' | 'self-practice'

export function TrainerPracticeLab() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('home')
  const [batches, setBatches] = useState<any[]>([])
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [lastBatch, setLastBatch] = useState<{ id: number; name: string } | null>(null)
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
    } catch { toast.error('Failed to load batches') } finally {
      setLoading(false)
    }
  }

  function openBatch(id: number) {
    const b = batches.find((x: any) => x.id === id)
    setSelectedBatchId(id)
    if (b) setLastBatch({ id, name: b.name })
    setView('batch-detail')
  }

  const statusColor = (s: string) => ({ Open: '#2563eb', Closed: '#16a34a' }[s] || '#6b7280')

  return (
    <div style={styles.container}>
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
              {lastBatch && (
                <button style={{ ...styles.navBtn, color: '#4f46e5', borderColor: '#c7d2fe' }}
                  onClick={() => openBatch(lastBatch.id)}>
                  ↩ {lastBatch.name}
                </button>
              )}
              <button style={styles.navBtn} onClick={() => setView('analytics')}><BarChart2 size={15} /> Analytics</button>
              <button style={styles.navBtn} onClick={() => setView('scoring-config')}><Settings size={15} /> Scoring Config</button>
              <button style={styles.navBtn} onClick={() => setView('answer-keys')}><Key size={15} /> Answer Keys</button>
              <button style={styles.navBtn} onClick={() => setView('self-practice')}><FileCheck size={15} /> Self Practice</button>
              <button style={{ ...styles.navBtn, background: '#0f766e', color: '#fff', border: 'none' }}
                onClick={() => setView('create-batch')}><Plus size={15} /> New Batch</button>
            </>
          )}
        </div>
      </div>

      <div style={styles.content}>
        {view === 'home' && (
          <HomeView batches={batches} overview={overview} loading={loading}
            onOpen={openBatch} statusColor={statusColor} onCreateBatch={() => setView('create-batch')} />
        )}
        {view === 'answer-keys' && <AnswerKeysView />}
        {view === 'create-batch' && (
          <CreateBatchView onCreated={(id: number) => { setSelectedBatchId(id); setView('batch-detail'); loadHome() }} scoringCfg={scoringCfg} />
        )}
        {view === 'batch-detail' && selectedBatchId && (
          <BatchDetailView batchId={selectedBatchId} onDRGReview={() => setView('drg-review')} onResults={() => setView('results')} />
        )}
        {view === 'drg-review' && selectedBatchId && (
          <DRGReviewView batchId={selectedBatchId} onDone={() => setView('batch-detail')} />
        )}
        {view === 'results' && selectedBatchId && <ResultsView batchId={selectedBatchId} />}
        {view === 'analytics' && <PLAnalyticsView onOpenBatch={(id: number) => { setSelectedBatchId(id); setView('batch-detail') }} />}
        {view === 'scoring-config' && <ScoringConfigView />}
        {view === 'self-practice' && <SelfPracticeView />}
      </div>
    </div>
  )
}
