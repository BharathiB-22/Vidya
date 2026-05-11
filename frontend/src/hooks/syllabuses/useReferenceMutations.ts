import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type {
  SyllabusReference,
  SyllabusReferenceCreate,
  SyllabusReferenceUpdate,
} from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

export function useAddReference(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SyllabusReferenceCreate) =>
      syllabusesApi.addReference(syllabusId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.references(syllabusId) })
      const prev = qc.getQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId))
      qc.setQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId), (old) => [
        ...(old ?? []),
        {
          id:           `optimistic-${Date.now()}`,
          syllabus_id:  syllabusId,
          title:        payload.title,
          authors:      payload.authors ?? [],
          year:         payload.year ?? null,
          ref_type:     payload.ref_type ?? 'TEXTBOOK',
          source:       payload.source ?? 'MANUAL',
          doi:          payload.doi ?? null,
          isbn:         payload.isbn ?? null,
          url:          payload.url ?? null,
          publisher:    payload.publisher ?? null,
          is_confirmed: payload.is_confirmed ?? true,
          created_at:   new Date().toISOString(),
          updated_at:   null,
        },
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.references(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.references(syllabusId) })
    },
  })
}

export function useUpdateReference(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ refId, payload }: { refId: string; payload: SyllabusReferenceUpdate }) =>
      syllabusesApi.updateReference(syllabusId, refId, payload),
    onMutate: async ({ refId, payload }) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.references(syllabusId) })
      const prev = qc.getQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId))
      qc.setQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId), (old) =>
        old?.map((r) => (r.id === refId ? { ...r, ...payload } : r)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.references(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.references(syllabusId) })
    },
  })
}

export function useDeleteReference(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (refId: string) => syllabusesApi.deleteReference(syllabusId, refId),
    onMutate: async (refId) => {
      await qc.cancelQueries({ queryKey: syllabusKeys.references(syllabusId) })
      const prev = qc.getQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId))
      qc.setQueryData<SyllabusReference[]>(syllabusKeys.references(syllabusId), (old) =>
        old?.filter((r) => r.id !== refId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(syllabusKeys.references(syllabusId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.references(syllabusId) })
    },
  })
}

export function useConfirmReference(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (refId: string) => syllabusesApi.confirmReference(syllabusId, refId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.references(syllabusId) })
    },
  })
}
