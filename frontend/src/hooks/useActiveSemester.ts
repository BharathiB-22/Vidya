import { useQuery } from '@tanstack/react-query'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

/**
 * Resolves the current student's active semester from their profile's batch.
 * Centralised here so every student-facing screen (dashboard, My Subjects, ...)
 * derives "active semester" the same way instead of re-deriving it independently.
 */
export function useActiveSemester() {
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

  return {
    profile: profileQ.data,
    isProfileLoading: profileQ.isLoading,
    semesters,
    isSemestersLoading: semestersQ.isLoading,
    activeSemester,
    semesterId: activeSemester?.id,
  }
}
