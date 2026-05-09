import { Routes, Route, Navigate } from 'react-router-dom'

export default function App() {
  return (
    <Routes>
      {/* M01 pages wired in STEP-15 */}
      <Route path="/programs/*" element={<div>Programs — coming in STEP-15</div>} />
      <Route path="/" element={<Navigate to="/programs" replace />} />
    </Routes>
  )
}
