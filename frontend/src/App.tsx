import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { CoderHome } from './pages/CoderHome'
import { TrainerHome } from './pages/TrainerHome'
import { TrainerUpload } from './pages/TrainerUpload'
import { TrainerCharts } from './pages/TrainerCharts'
import { TrainerReports } from './pages/TrainerReports'
import { ChartLibraryAnalytics } from './pages/ChartLibraryAnalytics'
import { TrainerFeedback } from './pages/TrainerFeedback'
import { TrainerPracticeLab } from './pages/TrainerPracticeLab'
import { CoderSelfPractice } from './pages/CoderSelfPractice'
import { AssessmentHome } from './pages/assessment/AssessmentHome'
import { ChartManagementHome } from './pages/ChartManagementHome'
import { TakeAssessmentEntry } from './pages/TakeAssessmentEntry'
import { TakeAssessmentSession } from './pages/TakeAssessmentSession'

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <Routes>
        <Route path="/" element={<CoderHome />} />
        <Route path="/self-practice" element={<CoderSelfPractice />} />
        <Route path="/trainer" element={<TrainerHome />} />
        <Route path="/trainer/upload" element={<TrainerUpload />} />
        <Route path="/trainer/charts" element={<TrainerCharts />} />
        <Route path="/trainer/reports" element={<TrainerReports />} />
        <Route path="/trainer/analytics" element={<ChartLibraryAnalytics />} />
        <Route path="/trainer/feedback" element={<TrainerFeedback />} />
        <Route path="/trainer/practicelab" element={<TrainerPracticeLab />} />
        <Route path="/trainer/assessment" element={<AssessmentHome />} />
        <Route path="/trainer/chart-management" element={<ChartManagementHome />} />
        <Route path="/take-assessment" element={<TakeAssessmentEntry />} />
        <Route path="/take-assessment/:token" element={<TakeAssessmentSession />} />
      </Routes>
    </BrowserRouter>
  )
}
