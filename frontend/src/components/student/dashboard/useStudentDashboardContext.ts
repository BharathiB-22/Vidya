import { useQuery } from '@tanstack/react-query'
import { sisApi } from '@/lib/api/sis'
import { useActiveSemester } from '@/hooks/useActiveSemester'

/**
 * Resolves the values several dashboard widgets need but none of them "own":
 * the student's profile, the currently-active semester (via useActiveSemester)
 * and exam session. Centralised here so each widget doesn't re-derive "active"
 * with slightly different logic.
 */
export function useStudentDashboardContext() {
  const { profile, isProfileLoading, semesterId } = useActiveSemester()

  const sessionsQ = useQuery({
    queryKey: ['exam-sessions-published'],
    queryFn: () => sisApi.listExamSessions({ status: 'PUBLISHED' }),
  })
  // Heuristic: prefer a session whose window hasn't fully passed yet, else the latest one.
  const today = new Date().toISOString().slice(0, 10)
  const sessions = sessionsQ.data ?? []
  const activeSession = sessions.find((s) => s.end_date >= today) ?? sessions[sessions.length - 1]

  return {
    profile,
    isProfileLoading,
    semesterId,
    sessionId: activeSession?.id,
  }
}
