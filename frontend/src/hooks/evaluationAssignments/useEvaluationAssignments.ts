import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api/evaluationAssignments'
import type { ListParams } from '@/lib/api/evaluationAssignments'
import type {
  AssignmentCreatePayload,
  AutoAssignPayload,
  BulkAssignmentPayload,
  CancelPayload,
  ReassignPayload,
} from '@/types/evaluationAssignment'

export const assignmentKeys = {
  all:        ['evaluationAssignments'] as const,
  list:       (f?: ListParams) => [...assignmentKeys.all, 'list', f] as const,
  mine:       (f?: Record<string, unknown>) => [...assignmentKeys.all, 'mine', f] as const,
  myWorkload: () => [...assignmentKeys.all, 'myWorkload'] as const,
  detail:     (id: string) => [...assignmentKeys.all, 'detail', id] as const,
  workload:   (ids: string[]) => [...assignmentKeys.all, 'workload', ids] as const,
}

// ---- Queries ----
export function useMyAssignments(params?: { status?: string; assignment_type?: string }) {
  return useQuery({
    queryKey: assignmentKeys.mine(params),
    queryFn:  () => api.myAssignments(params),
  })
}

export function useMyWorkload() {
  return useQuery({
    queryKey: assignmentKeys.myWorkload(),
    queryFn:  () => api.myWorkload(),
  })
}

export function useAssignments(params?: ListParams) {
  return useQuery({
    queryKey: assignmentKeys.list(params),
    queryFn:  () => api.listAssignments(params),
  })
}

export function useAssignment(id: string) {
  return useQuery({
    queryKey: assignmentKeys.detail(id),
    queryFn:  () => api.getAssignment(id),
    enabled:  Boolean(id),
  })
}

export function useWorkloadBoard(evaluatorIds: string[]) {
  return useQuery({
    queryKey: assignmentKeys.workload(evaluatorIds),
    queryFn:  () => api.workloadBoard(evaluatorIds),
    enabled:  evaluatorIds.length > 0,
  })
}

// ---- Mutations ----
function useInvalidate() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: assignmentKeys.all })
}

export function useCreateAssignment() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (p: AssignmentCreatePayload) => api.createAssignment(p),
    onSuccess: invalidate,
  })
}

export function useBulkAssign() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (p: BulkAssignmentPayload) => api.bulkAssign(p),
    onSuccess: invalidate,
  })
}

export function useAutoAssign() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (p: AutoAssignPayload) => api.autoAssign(p),
    onSuccess: (res) => { if (!res.dry_run) invalidate() },
  })
}

export function useStartAssignment() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.startAssignment(id), onSuccess: invalidate })
}

export function useSubmitAssignment() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.submitAssignment(id), onSuccess: invalidate })
}

export function useCompleteAssignment() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.completeAssignment(id), onSuccess: invalidate })
}

export function useReassignAssignment() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ReassignPayload }) =>
      api.reassignAssignment(id, payload),
    onSuccess: invalidate,
  })
}

export function useCancelAssignment() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CancelPayload }) =>
      api.cancelAssignment(id, payload),
    onSuccess: invalidate,
  })
}
