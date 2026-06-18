import { useState } from 'react'
import { BarChart2, TrendingUp, User, Layers, Tag, Grid, BookOpen } from 'lucide-react'
import { OverviewTab } from './analytics/OverviewTab'
import { AssessmentDrillTab } from './analytics/AssessmentDrillTab'
import { CoderHistoryTab } from './analytics/CoderHistoryTab'
import { BySpecialtyTab } from './analytics/BySpecialtyTab'
import { ByTopicTab } from './analytics/ByTopicTab'
import { BatchAnalysisTab } from './analytics/BatchAnalysisTab'
import { CoderMatrixTab } from './analytics/CoderMatrixTab'

type AnalyticsTab = 'overview' | 'drill' | 'coder' | 'specialty' | 'topic' | 'batch' | 'matrix'

export function AnalyticsView() {
  const [tab, setTab] = useState<AnalyticsTab>('overview')

  const tabs: { id: AnalyticsTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'batch', label: 'Batch Analysis', icon: <BookOpen size={14} /> },
    { id: 'drill', label: 'Assessment Drill-down', icon: <TrendingUp size={14} /> },
    { id: 'specialty', label: 'By Specialty', icon: <Layers size={14} /> },
    { id: 'topic', label: 'By Topic', icon: <Tag size={14} /> },
    { id: 'matrix', label: 'Coder Matrix', icon: <Grid size={14} /> },
    { id: 'coder', label: 'Coder History', icon: <User size={14} /> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 22 }}>
        {tabs.map(t => (
          <button
            key={t.id}
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

      {tab === 'overview' && <OverviewTab />}
      {tab === 'batch' && <BatchAnalysisTab />}
      {tab === 'drill' && <AssessmentDrillTab />}
      {tab === 'specialty' && <BySpecialtyTab />}
      {tab === 'topic' && <ByTopicTab />}
      {tab === 'matrix' && <CoderMatrixTab />}
      {tab === 'coder' && <CoderHistoryTab />}
    </div>
  )
}
