import { useQuery } from '@tanstack/react-query'
import * as courseworkApi from '@/lib/api/coursework'

// ── Query key factory ────────────────────────────────────────────────────────

export const courseworkKeys = {
  all:          ['coursework'] as const,
  list:         (f?: Record<string, unknown>) => [...courseworkKeys.all, 'list', f] as const,
  detail:       (id: string) => [...courseworkKeys.all, 'detail', id] as const,
  submissions:  (assignmentId: string) => [...courseworkKeys.all, 'submissions', assignmentId] as const,
  statistics:   (id: string) => [...courseworkKeys.all, 'statistics', id] as const,
  mySubmissions: (f?: Record<string, unknown>) => [...courseworkKeys.all, 'my-submissions', f] as const,
  studentAssignments: (f?: Record<string, unknown>) => [...courseworkKeys.all, 'student', 'list', f] as const,
  studentResult: (submissionId: string) => [...courseworkKeys.all, 'student', 'result', submissionId] as const,
  fileUrl:      (submissionId: string) => [...courseworkKeys.all, 'file-url', submissionId] as const,
}

// ── Faculty queries ──────────────────────────────────────────────────────────

export function useAssignments(params?: { syllabus_id?: string; status?: string }) {
  return useQuery({
    queryKey: courseworkKeys.list(params),
    queryFn:  () => courseworkApi.listAssignments(params),
  })
}

export function useAssignment(id: string) {
  return useQuery({
    queryKey: courseworkKeys.detail(id),
    queryFn:  () => courseworkApi.getAssignment(id),
    enabled:  Boolean(id),
  })
}

export function useAssignmentSubmissions(assignmentId: string) {
  return useQuery({
    queryKey: courseworkKeys.submissions(assignmentId),
    queryFn:  () => courseworkApi.listSubmissions(assignmentId),
    enabled:  Boolean(assignmentId),
  })
}

export function useAssignmentStatistics(id: string) {
  return useQuery({
    queryKey: courseworkKeys.statistics(id),
    queryFn:  () => courseworkApi.getAssignmentStatistics(id),
    enabled:  Boolean(id),
  })
}

// ── Student queries ──────────────────────────────────────────────────────────

export function useStudentAssignments(params?: { syllabus_id?: string }) {
  return useQuery({
    queryKey: courseworkKeys.studentAssignments(params),
    queryFn:  () => courseworkApi.studentListAssignments(params),
  })
}

export function useMySubmissions(params?: { syllabus_id?: string }) {
  return useQuery({
    queryKey: courseworkKeys.mySubmissions(params),
    queryFn:  () => courseworkApi.studentMySubmissions(params),
  })
}

export function useStudentResult(submissionId: string) {
  return useQuery({
    queryKey: courseworkKeys.studentResult(submissionId),
    queryFn:  () => courseworkApi.studentGetResult(submissionId),
    enabled:  Boolean(submissionId),
  })
}

export function useSubmissionFileUrl(submissionId: string, enabled: boolean) {
  return useQuery({
    queryKey: courseworkKeys.fileUrl(submissionId),
    queryFn:  () => courseworkApi.getSubmissionFileUrl(submissionId),
    enabled:  enabled && Boolean(submissionId),
    staleTime: 4 * 60 * 1000,
    gcTime:   5 * 60 * 1000,
  })
}
