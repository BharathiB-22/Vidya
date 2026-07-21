import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseworkApi from '@/lib/api/coursework'
import { courseworkKeys } from './useCoursework'
import type {
  AssignEvaluatorPayload,
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

export function useDeleteAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.deleteAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
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

export function useReleaseMarks() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.releaseAssignmentMarks(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

export function useArchiveAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.archiveAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

export function useRestoreAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.restoreAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

// ── Evaluation hand-off ─────────────────────────────────────────────────────

/** Faculty hands a CLOSED assignment to the department for evaluation. */
export function useSubmitForEvaluation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseworkApi.submitAssignmentForEvaluation(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
  })
}

/** Dept/Admin allocates one submission to one evaluator. */
export function useAssignEvaluator(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ submissionId, payload }: { submissionId: string; payload: AssignEvaluatorPayload }) =>
      courseworkApi.assignEvaluator(submissionId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseworkKeys.submissions(assignmentId) })
    },
  })
}

/** Ratify the evaluated marks — the human decision that closes the workflow. */
// useFinalizeMarks removed with the Dean ratification step — the owning faculty
// reviews the evaluator's recommendation and releases, in one decision.

// assignmentId is kept in the signature so every existing call site stays valid;
// the invalidation is namespace-wide and no longer needs it.
export function useGradeSubmission(_assignmentId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ submissionId, payload }: { submissionId: string; payload: CourseworkGradePayload }) =>
      courseworkApi.gradeSubmission(submissionId, payload),
    // Invalidate the whole namespace, not just this assignment's submissions: a
    // grade changes the progress counts the assignment lists render, and those
    // cards were previously left showing stale evaluation state until a reload.
    onSuccess: () => { qc.invalidateQueries({ queryKey: courseworkKeys.all }) },
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
