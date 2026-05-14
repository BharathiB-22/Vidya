import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthGuard } from '@/components/AuthGuard'
import LoginPage from '@/pages/LoginPage'
import ProgramListPage from '@/pages/ProgramListPage'
import ProgramDetailPage from '@/pages/ProgramDetailPage'
import SyllabusListPage from '@/pages/SyllabusListPage'
import SyllabusDetailPage from '@/pages/SyllabusDetailPage'
import CourseKitListPage from '@/pages/CourseKitListPage'
import CourseKitDetailPage from '@/pages/CourseKitDetailPage'

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
        <Route path="/" element={<Navigate to="/programs" replace />} />
      </Route>
    </Routes>
  )
}
