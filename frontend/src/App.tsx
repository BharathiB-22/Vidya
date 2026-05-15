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
        <Route path="/" element={<Navigate to="/programs" replace />} />
      </Route>
    </Routes>
  )
}
