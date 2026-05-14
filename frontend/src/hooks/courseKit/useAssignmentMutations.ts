import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type {
  KitAssignment,
  KitAssignmentCreate,
  KitAssignmentUpdate,
} from '@/types/courseKit'
import { courseKitKeys } from './useCourseKit'

export function useAddAssignment(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KitAssignmentCreate) => courseKitApi.addAssignment(kitId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.assignments(kitId) })
      const prev = qc.getQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId))
      qc.setQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId), (old) => [
        ...(old ?? []),
        {
          id:                    `optimistic-${Date.now()}`,
          kit_id:                kitId,
          assignment_number:     payload.assignment_number,
          title:                 payload.title,
          assignment_type:       payload.assignment_type ?? 'CLASSWORK',
          question_text:         payload.question_text,
          complexity_level:      payload.complexity_level ?? 'UG',
          current_events_toggle: payload.current_events_toggle ?? false,
          model_answer:          payload.model_answer ?? null,
          rubric:                (payload.rubric ?? []) as unknown as Record<string, unknown>[],
          bloom_level:           payload.bloom_level ?? null,
          co_reference:          payload.co_reference ?? null,
          created_at:            new Date().toISOString(),
          updated_at:            null,
        } as KitAssignment,
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.assignments(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.assignments(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useUpdateAssignment(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      assignmentId,
      payload,
    }: {
      assignmentId: string
      payload: KitAssignmentUpdate
    }) => courseKitApi.updateAssignment(kitId, assignmentId, payload),
    onMutate: async ({ assignmentId, payload }) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.assignments(kitId) })
      const prev = qc.getQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId))
      qc.setQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId), (old) =>
        old?.map((a) => (a.id === assignmentId ? ({ ...a, ...payload } as KitAssignment) : a)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.assignments(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.assignments(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useDeleteAssignment(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assignmentId: string) =>
      courseKitApi.deleteAssignment(kitId, assignmentId),
    onMutate: async (assignmentId) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.assignments(kitId) })
      const prev = qc.getQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId))
      qc.setQueryData<KitAssignment[]>(courseKitKeys.assignments(kitId), (old) =>
        old?.filter((a) => a.id !== assignmentId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.assignments(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.assignments(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}
