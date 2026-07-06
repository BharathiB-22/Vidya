import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseworkApi from '@/lib/api/coursework'
import { courseworkKeys } from './useCoursework'
import type {
  CourseworkAssignmentCreate,
  CourseworkAssignmentUpdate,
  CourseworkGradePayload,
  CourseworkSubmitPayload,
} from '@/types/coursework'

export function useCreateAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseworkAssignmentCreate) => courseworkApi.createAssignment(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

export function useUpdateAssignment(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseworkAssignmentUpdate) => courseworkApi.updateAssignment(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseworkKeys.detail(id) })
      qc.invalidateQueries({ queryKey: courseworkKeys.all })
    },
  })
}

export function usePublishAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.publishAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

export function useCloseAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.closeAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

export function useGradeSubmission(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ submissionId, payload }: { submissionId: string; payload: CourseworkGradePayload }) =>
      courseworkApi.gradeSubmission(submissionId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseworkKeys.submissions(assignmentId) })
      qc.invalidateQueries({ queryKey: courseworkKeys.statistics(assignmentId) })
    },
  })
}

export function useReturnSubmission(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (submissionId: string) => courseworkApi.returnSubmission(submissionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseworkKeys.submissions(assignmentId) })
    },
  })
}

export function useStudentSubmit(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseworkSubmitPayload) => courseworkApi.studentSubmit(assignmentId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseworkKeys.mySubmissions() })
      qc.invalidateQueries({ queryKey: courseworkKeys.studentAssignments() })
    },
  })
}
