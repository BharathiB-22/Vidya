import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as labsApi from '@/lib/api/labs'
import { labKeys } from './useLabs'
import type {
  AssignmentCreate,
  AssignmentUpdate,
  RatifyRequest,
  ScoresUpdateRequest,
  SubmitPayload,
} from '@/types/labs'

export function useCreateAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AssignmentCreate) => labsApi.createAssignment(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: labKeys.all }) },
  })
}

export function useUpdateAssignment(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AssignmentUpdate) => labsApi.updateAssignment(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labKeys.assignment(id) })
      qc.invalidateQueries({ queryKey: labKeys.all })
    },
  })
}

export function usePublishAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => labsApi.publishAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: labKeys.all }) },
  })
}

export function useCloseAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => labsApi.closeAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: labKeys.all }) },
  })
}

export function useUpdateScores(submissionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ScoresUpdateRequest) => labsApi.updateScores(submissionId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labKeys.review(submissionId) })
    },
  })
}

export function useRatify(submissionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: RatifyRequest) => labsApi.ratifySubmission(submissionId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labKeys.review(submissionId) })
      qc.invalidateQueries({ queryKey: labKeys.all })
    },
  })
}

export function useStudentSubmit(assignmentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SubmitPayload) => labsApi.studentSubmit(assignmentId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labKeys.mySubmissions() })
      qc.invalidateQueries({ queryKey: labKeys.studentAssignments() })
    },
  })
}
