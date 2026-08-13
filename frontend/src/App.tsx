import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { lazy, Suspense } from 'react'

const CoderHome             = lazy(() => import('./pages/CoderHome').then(m => ({ default: m.CoderHome })))
const TrainerHome           = lazy(() => import('./pages/TrainerHome').then(m => ({ default: m.TrainerHome })))
const TrainerUpload         = lazy(() => import('./pages/TrainerUpload').then(m => ({ default: m.TrainerUpload })))
const TrainerCharts         = lazy(() => import('./pages/TrainerCharts').then(m => ({ default: m.TrainerCharts })))
const TrainerReports        = lazy(() => import('./pages/TrainerReports').then(m => ({ default: m.TrainerReports })))
const ChartLibraryAnalytics = lazy(() => import('./pages/ChartLibraryAnalytics').then(m => ({ default: m.ChartLibraryAnalytics })))
const TrainerFeedback       = lazy(() => import('./pages/TrainerFeedback').then(m => ({ default: m.TrainerFeedback })))
const TrainerPracticeLab    = lazy(() => import('./pages/TrainerPracticeLab').then(m => ({ default: m.TrainerPracticeLab })))
const AssessmentHome        = lazy(() => import('./pages/assessment/AssessmentHome').then(m => ({ default: m.AssessmentHome })))
const ChartManagementHome   = lazy(() => import('./pages/ChartManagementHome').then(m => ({ default: m.ChartManagementHome })))
const TakeAssessmentEntry   = lazy(() => import('./pages/TakeAssessmentEntry').then(m => ({ default: m.TakeAssessmentEntry })))
const TakeAssessmentSession = lazy(() => import('./pages/TakeAssessmentSession').then(m => ({ default: m.TakeAssessmentSession })))
const PracticeEntry         = lazy(() => import('./pages/PracticeEntry').then(m => ({ default: m.PracticeEntry })))
const PracticeSession       = lazy(() => import('./pages/PracticeSession').then(m => ({ default: m.PracticeSession })))
const AuditSession          = lazy(() => import('./pages/AuditSession').then(m => ({ default: m.AuditSession })))

function PageLoader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#94a3b8', fontSize: 14 }}>
      Loading…
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<CoderHome />} />
          <Route path="/trainer" element={<TrainerHome />} />
          <Route path="/trainer/upload" element={<TrainerUpload />} />
          <Route path="/trainer/charts" element={<TrainerCharts />} />
          <Route path="/trainer/reports" element={<TrainerReports />} />
          <Route path="/trainer/analytics" element={<ChartLibraryAnalytics />} />
          <Route path="/trainer/feedback" element={<TrainerFeedback />} />
          <Route path="/trainer/practicelab" element={<TrainerPracticeLab />} />
          <Route path="/trainer/assessment" element={<AssessmentHome />} />
          {/* Same component, tab read from the URL — see AssessmentHome. */}
          <Route path="/trainer/assessment/:tab" element={<AssessmentHome />} />
          <Route path="/trainer/chart-management" element={<ChartManagementHome />} />
          <Route path="/take-assessment" element={<TakeAssessmentEntry />} />
          <Route path="/take-assessment/:token" element={<TakeAssessmentSession />} />
          <Route path="/practice" element={<PracticeEntry />} />
          <Route path="/practice/:token" element={<PracticeSession />} />
          <Route path="/audit/:token" element={<AuditSession />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
