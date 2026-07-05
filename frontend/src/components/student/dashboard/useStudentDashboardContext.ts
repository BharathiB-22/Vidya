import { useQuery } from '@tanstack/react-query'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

/**
 * Resolves the values several dashboard widgets need but none of them "own":
 * the student's profile (for batch_id) and the currently-active semester and
 * exam session. Centralised here so each widget doesn't re-derive "active"
 * with slightly different logic.
 */
export function useStudentDashboardContext() {
  const profileQ = useQuery({
    queryKey: ['my-student-profile'],
    queryFn: sisApi.getMyStudentProfile,
  })

  const batchId = profileQ.data?.batch?.id

  const semestersQ = useQuery({
    queryKey: ['semesters', batchId],
    queryFn: () => academicsApi.listSemesters(batchId),
    enabled: !!batchId,
  })
  const semesters = semestersQ.data ?? []
  const activeSemester = semesters.find((s) => s.is_active) ?? semesters[semesters.length - 1]

  const sessionsQ = useQuery({
    queryKey: ['exam-sessions-published'],
    queryFn: () => sisApi.listExamSessions({ status: 'PUBLISHED' }),
  })
  // Heuristic: prefer a session whose window hasn't fully passed yet, else the latest one.
  const today = new Date().toISOString().slice(0, 10)
  const sessions = sessionsQ.data ?? []
  const activeSession = sessions.find((s) => s.end_date >= today) ?? sessions[sessions.length - 1]

  return {
    profile: profileQ.data,
    isProfileLoading: profileQ.isLoading,
    semesterId: activeSemester?.id,
    sessionId: activeSession?.id,
  }
}
