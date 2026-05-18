import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthGuard } from '@/components/AuthGuard'
import LoginPage from '@/pages/LoginPage'
import ProgramListPage from '@/pages/ProgramListPage'
import ProgramDetailPage from '@/pages/ProgramDetailPage'
import SyllabusListPage from '@/pages/SyllabusListPage'
import SyllabusDetailPage from '@/pages/SyllabusDetailPage'
import CourseKitListPage from '@/pages/CourseKitListPage'
import CourseKitDetailPage from '@/pages/CourseKitDetailPage'
import LearningPackageListPage from '@/pages/LearningPackageListPage'
import LearningPackagePage from '@/pages/LearningPackage'
import FacultyCuratePage from '@/pages/FacultyCurate'
import LabAssignmentListPage from '@/pages/LabAssignmentListPage'
import LabAssignmentDetailPage from '@/pages/LabAssignmentDetailPage'
import LabReviewPanel from '@/pages/LabReviewPanel'
import StudentLabListPage from '@/pages/StudentLabListPage'
import StudentSubmitPage from '@/pages/StudentSubmitPage'
import StudentResultPage from '@/pages/StudentResultPage'
import ResearchProblemListPage from '@/pages/ResearchProblemListPage'
import ResearchDocumentPage from '@/pages/ResearchDocumentPage'
import VivaRatifyPage from '@/pages/VivaRatifyPage'
import StudentResearchPage from '@/pages/StudentResearchPage'
import StudentVivaPage from '@/pages/StudentVivaPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/programs" element={<ProgramListPage />} />
        <Route path="/programs/:id" element={<ProgramDetailPage />} />
        <Route path="/syllabuses" element={<SyllabusListPage />} />
        <Route path="/syllabuses/:id" element={<SyllabusDetailPage />} />
        <Route path="/course-kits" element={<CourseKitListPage />} />
        <Route path="/course-kits/:id" element={<CourseKitDetailPage />} />
        <Route path="/learning-packages" element={<LearningPackageListPage />} />
        <Route path="/learning-packages/:id" element={<LearningPackagePage />} />
        <Route path="/learning-packages/:id/curate" element={<FacultyCuratePage />} />

        {/* M06 — Labs (faculty) */}
        <Route path="/labs" element={<LabAssignmentListPage />} />
        <Route path="/labs/review/:submissionId" element={<LabReviewPanel />} />
        <Route path="/labs/:id" element={<LabAssignmentDetailPage />} />

        {/* M06 — Labs (student) */}
        <Route path="/student/labs" element={<StudentLabListPage />} />
        <Route path="/student/labs/:id" element={<StudentSubmitPage />} />
        <Route path="/student/submissions/:submissionId/result" element={<StudentResultPage />} />

        {/* M07 — Research Supervision (guide) */}
        <Route path="/research/problems" element={<ResearchProblemListPage />} />
        <Route path="/research/documents/:id" element={<ResearchDocumentPage />} />
        <Route path="/research/vivas/:id" element={<VivaRatifyPage />} />

        {/* M07 — Research Supervision (student) */}
        <Route path="/student/research" element={<StudentResearchPage />} />
        <Route path="/student/viva/:token" element={<StudentVivaPage />} />

        <Route path="/" element={<Navigate to="/programs" replace />} />
      </Route>
    </Routes>
  )
}
