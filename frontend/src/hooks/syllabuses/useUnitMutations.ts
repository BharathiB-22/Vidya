import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type {
  SyllabusUnit,
  SyllabusUnitCreate,
  SyllabusUnitReorder,
  SyllabusUnitUpdate,
} from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

export function useAddUnit(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SyllabusUnitCreate) =>
      syllabusesApi.addUnit(syllabusId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.units(syllabusId) })
      const prev = qc.getQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId))
      qc.setQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId), (old) => [
        ...(old ?? []),
        {
          id:            `optimistic-${Date.now()}`,
          syllabus_id:   syllabusId,
          unit_number:   payload.unit_number,
          title:         payload.title,
          topics:        payload.topics ?? [],
          total_hours:   payload.total_hours,
          pedagogy:      payload.pedagogy ?? null,
          bloom_summary: null,
          created_at:    new Date().toISOString(),
          updated_at:    null,
        },
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.units(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.units(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}

export function useUpdateUnit(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ unitId, payload }: { unitId: string; payload: SyllabusUnitUpdate }) =>
      syllabusesApi.updateUnit(syllabusId, unitId, payload),
    onMutate: async ({ unitId, payload }) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.units(syllabusId) })
      const prev = qc.getQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId))
      qc.setQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId), (old) =>
        old?.map((u) => (u.id === unitId ? { ...u, ...payload } : u)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.units(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.units(syllabusId) })
    },
  })
}

export function useDeleteUnit(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (unitId: string) => syllabusesApi.deleteUnit(syllabusId, unitId),
    onMutate: async (unitId) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.units(syllabusId) })
      const prev = qc.getQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId))
      qc.setQueryData<SyllabusUnit[]>(syllabusKeys.units(syllabusId), (old) =>
        old?.filter((u) => u.id !== unitId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.units(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.units(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.compliance(syllabusId) })
    },
  })
}

export function useReorderUnits(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SyllabusUnitReorder) =>
      syllabusesApi.reorderUnits(syllabusId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.units(syllabusId) })
    },
  })
}
