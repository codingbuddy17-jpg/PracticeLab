import { useState } from 'react'
import { BarChart2, TrendingUp, User, Layers, Tag, Grid, BookOpen, HelpCircle } from 'lucide-react'
import { OverviewTab } from './analytics/OverviewTab'
import { AssessmentDrillTab } from './analytics/AssessmentDrillTab'
import { CoderHistoryTab } from './analytics/CoderHistoryTab'
import { BySpecialtyTab } from './analytics/BySpecialtyTab'
import { ByTopicTab } from './analytics/ByTopicTab'
import { BatchAnalysisTab } from './analytics/BatchAnalysisTab'
import { CoderMatrixTab } from './analytics/CoderMatrixTab'
import { QuestionSignalsTab } from './analytics/QuestionSignalsTab'
import { FilterBar } from './analytics/FilterBar'
import type { AFilters } from '../../api'

type AnalyticsTab = 'overview' | 'drill' | 'coder' | 'specialty' | 'topic' | 'batch' | 'matrix' | 'questions'

/**
 * Tabs that read the shared window. The others answer a question the window
 * does not apply to — Batch Analysis IS the batch view, and the drill and coder
 * tabs are already scoped to one paper or one person — so showing the bar there
 * would imply a filter that does nothing.
 */
const FILTERED: AnalyticsTab[] = ['overview', 'specialty', 'topic', 'matrix', 'questions']

export function AnalyticsView() {
  const [tab, setTab] = useState<AnalyticsTab>('overview')
  const [filters, setFilters] = useState<AFilters>({})

  const tabs: { id: AnalyticsTab; label: string; title: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', title: 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'batch', label: 'Batches', title: 'Batch Analysis', icon: <BookOpen size={14} /> },
    { id: 'drill', label: 'Drill-down', title: 'Assessment Drill-down', icon: <TrendingUp size={14} /> },
    { id: 'specialty', label: 'Specialty', title: 'By Specialty', icon: <Layers size={14} /> },
    { id: 'topic', label: 'Topic', title: 'By Topic', icon: <Tag size={14} /> },
    { id: 'questions', label: 'Questions', title: 'Question Signals — which questions teach, which mislead', icon: <HelpCircle size={14} /> },
    { id: 'matrix', label: 'Matrix', title: 'Coder × Specialty Matrix', icon: <Grid size={14} /> },
    { id: 'coder', label: 'Coder', title: 'Coder History', icon: <User size={14} /> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 22, flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <button
            key={t.id}
            title={t.title}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', borderRadius: 10,
              border: tab === t.id ? '1px solid rgba(124,58,237,0.3)' : '1px solid transparent',
              background: tab === t.id ? 'rgba(124,58,237,0.1)' : 'rgba(255,255,255,0.5)',
              cursor: 'pointer', fontSize: 13, fontWeight: 700,
              color: tab === t.id ? '#7c3aed' : '#6b7280',
              backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
              transition: 'all 0.15s',
            }}
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Above the tab content, never inside it: a filter that empties the view
          must not take its own control down with it. */}
      {FILTERED.includes(tab) && <FilterBar value={filters} onChange={setFilters} />}

      {tab === 'overview' && <OverviewTab filters={filters} />}
      {tab === 'batch' && <BatchAnalysisTab />}
      {tab === 'drill' && <AssessmentDrillTab />}
      {tab === 'specialty' && <BySpecialtyTab filters={filters} />}
      {tab === 'topic' && <ByTopicTab filters={filters} />}
      {tab === 'matrix' && <CoderMatrixTab filters={filters} />}
      {tab === 'questions' && <QuestionSignalsTab filters={filters} />}
      {tab === 'coder' && <CoderHistoryTab />}
    </div>
  )
}
