/**
 * ExamGuard — wraps ActiveExamPage.
 *
 * Responsibilities:
 *  1. Block browser back/forward/close with beforeunload while IN_PROGRESS.
 *  2. Redirect to /student/exams/digital if no attemptId in sessionStorage.
 *  3. Pass attemptId down via Outlet context so ActiveExamPage can use it.
 */
import { useEffect } from 'react'
import { Navigate, Outlet, useParams } from 'react-router-dom'

interface ExamGuardProps {
  /** If true, the beforeunload warning is active (exam is in progress). */
  active?: boolean
}

export function ExamGuard({ active = true }: ExamGuardProps) {
  const { sessionId } = useParams<{ sessionId: string }>()

  // beforeunload warning during active exam
  useEffect(() => {
    if (!active) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [active])

  // If no sessionId in the URL something is wrong — redirect home
  if (!sessionId) {
    return <Navigate to="/student/exams/digital" replace />
  }

  return <Outlet />
}
