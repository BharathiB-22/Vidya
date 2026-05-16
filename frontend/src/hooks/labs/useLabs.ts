import { useQuery } from '@tanstack/react-query'
import * as labsApi from '@/lib/api/labs'

// ── Query key factory ────────────────────────────────────────────────────────

export const labKeys = {
  all:          ['labs'] as const,
  assignments:  (f?: Record<string, unknown>) => [...labKeys.all, 'assignments', f] as const,
  assignment:   (id: string) => [...labKeys.all, 'assignments', id] as const,
  submissions:  (assignmentId: string) => [...labKeys.all, 'submissions', assignmentId] as const,
  review:       (submissionId: string) => [...labKeys.all, 'review', submissionId] as const,
  job:          (jobId: string) => [...labKeys.all, 'jobs', jobId] as const,
  mySubmissions: () => [...labKeys.all, 'my-submissions'] as const,
  studentAssignments: (f?: Record<string, unknown>) => [...labKeys.all, 'student', 'assignments', f] as const,
  studentResult: (submissionId: string) => [...labKeys.all, 'student', 'result', submissionId] as const,
}

// ── Faculty queries ──────────────────────────────────────────────────────────

export function useLabAssignments(params?: { syllabus_id?: string; status?: string }) {
  return useQuery({
    queryKey: labKeys.assignments(params),
    queryFn:  () => labsApi.listAssignments(params),
  })
}

export function useLabAssignment(id: string) {
  return useQuery({
    queryKey: labKeys.assignment(id),
    queryFn:  () => labsApi.getAssignment(id),
    enabled:  Boolean(id),
  })
}

export function useSubmissions(assignmentId: string) {
  return useQuery({
    queryKey: labKeys.submissions(assignmentId),
    queryFn:  () => labsApi.listSubmissions(assignmentId),
    enabled:  Boolean(assignmentId),
  })
}

export function useReviewPanel(submissionId: string) {
  return useQuery({
    queryKey: labKeys.review(submissionId),
    queryFn:  () => labsApi.getReviewPanel(submissionId),
    enabled:  Boolean(submissionId),
  })
}

export function useEvalJob(jobId: string | null) {
  return useQuery({
    queryKey: labKeys.job(jobId ?? ''),
    queryFn:  () => labsApi.getJobStatus(jobId!),
    enabled:  Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false
    },
  })
}

// ── Student queries ──────────────────────────────────────────────────────────

export function useStudentAssignments(params?: { syllabus_id?: string }) {
  return useQuery({
    queryKey: labKeys.studentAssignments(params),
    queryFn:  () => labsApi.studentListAssignments(params),
  })
}

export function useStudentResult(submissionId: string) {
  return useQuery({
    queryKey: labKeys.studentResult(submissionId),
    queryFn:  () => labsApi.studentGetResult(submissionId),
    enabled:  Boolean(submissionId),
  })
}

export function useMySubmissions() {
  return useQuery({
    queryKey: labKeys.mySubmissions(),
    queryFn:  () => labsApi.studentMySubmissions(),
  })
}
