import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type {
  COPOMappingBulkUpdate,
  CourseOutcome,
  CourseOutcomeCreate,
  CourseOutcomeUpdate,
} from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

// ---------------------------------------------------------------------------
// Course outcome mutations (optimistic)
// ---------------------------------------------------------------------------

export function useAddCourseOutcome(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseOutcomeCreate) =>
      syllabusesApi.addOutcome(syllabusId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      const prev = qc.getQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId))
      qc.setQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId), (old) => [
        ...(old ?? []),
        {
          id:            `optimistic-${Date.now()}`,
          syllabus_id:   syllabusId,
          code:          payload.code,
          description:   payload.description,
          bloom_level:   payload.bloom_level,
          display_order: payload.display_order ?? (old?.length ?? 0) + 1,
          created_at:    new Date().toISOString(),
          updated_at:    null,
        },
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.outcomes(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}

export function useUpdateCourseOutcome(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ coId, payload }: { coId: string; payload: CourseOutcomeUpdate }) =>
      syllabusesApi.updateOutcome(syllabusId, coId, payload),
    onMutate: async ({ coId, payload }) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      const prev = qc.getQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId))
      qc.setQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId), (old) =>
        old?.map((co) => (co.id === coId ? { ...co, ...payload } : co)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.outcomes(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}

export function useDeleteCourseOutcome(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (coId: string) => syllabusesApi.deleteOutcome(syllabusId, coId),
    onMutate: async (coId) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      const prev = qc.getQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId))
      qc.setQueryData<CourseOutcome[]>(syllabusKeys.outcomes(syllabusId), (old) =>
        old?.filter((co) => co.id !== coId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.outcomes(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.copoMatrix(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}

// ---------------------------------------------------------------------------
// CO-PO mapping mutations
// ---------------------------------------------------------------------------

export function useUpdateCOPOMappings(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ coId, payload }: { coId: string; payload: COPOMappingBulkUpdate }) =>
      syllabusesApi.updateCOPOMappings(syllabusId, coId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.copoMatrix(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}
