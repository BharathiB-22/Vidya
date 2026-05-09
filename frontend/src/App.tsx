import { Routes, Route, Navigate } from 'react-router-dom'
import ProgramListPage from '@/pages/ProgramListPage'
import ProgramDetailPage from '@/pages/ProgramDetailPage'

export default function App() {
  return (
    <Routes>
      <Route path="/programs" element={<ProgramListPage />} />
      <Route path="/programs/:id" element={<ProgramDetailPage />} />
      <Route path="/" element={<Navigate to="/programs" replace />} />
    </Routes>
  )
}
