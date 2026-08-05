import { useState } from 'react'
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

const TABS: { id: AnalyticsTab; label: string; title: string }[] = [
  { id: 'overview', label: 'Overview', title: 'Overview' },
  { id: 'batch', label: 'Batches', title: 'Batch Analysis' },
  { id: 'drill', label: 'Drill-down', title: 'Assessment Drill-down' },
  { id: 'specialty', label: 'Specialty', title: 'By Specialty' },
  { id: 'topic', label: 'Topic', title: 'By Topic' },
  { id: 'questions', label: 'Questions', title: 'Question Signals — which questions teach, which mislead' },
  { id: 'matrix', label: 'Matrix', title: 'Coder × Specialty Matrix' },
  { id: 'coder', label: 'Coder', title: 'Coder History' },
]

export function AnalyticsView() {
  const [tab, setTab] = useState<AnalyticsTab>('overview')
  const [filters, setFilters] = useState<AFilters>({})

  return (
    <div>
      {/*
        One segmented control, matching PracticeLab analytics — same shape, same
        slate, so moving between the two modules does not feel like moving
        between two apps.

        No icons. Eight glyphs of eight different metaphors read as decoration
        rather than meaning: nothing distinguishes a tag from a layer at 14px,
        so they add colour and width without adding information. The label is
        the label.

        A dark selected segment reads as chrome — the thing you move around in,
        rather than a setting you have switched on. Labels are short so all
        eight fit one row at ordinary widths, with the full name on hover.
      */}
      <div style={{
        display: 'flex',
        border: '1px solid #cbd5e1',
        borderRadius: 10,
        overflow: 'hidden',
        alignSelf: 'flex-start',
        maxWidth: '100%',
        flexWrap: 'wrap' as const,
        background: '#f8fafc',
        marginBottom: 20,
        width: 'fit-content',
      }}>
        {TABS.map(t => (
          <button
            key={t.id}
            title={t.title}
            onClick={() => setTab(t.id)}
            style={{
              padding: '8px 15px',
              border: 'none',
              cursor: 'pointer',
              whiteSpace: 'nowrap' as const,
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: 0.2,
              background: tab === t.id ? '#334155' : 'transparent',
              color: tab === t.id ? '#fff' : '#64748b',
            }}
          >
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
