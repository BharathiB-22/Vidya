import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type { ForkRequest, SyllabusCreate, SyllabusUpdate } from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

export function useCreateSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SyllabusCreate) => syllabusesApi.createSyllabus(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useUpdateSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SyllabusUpdate }) =>
      syllabusesApi.updateSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useDeleteSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => syllabusesApi.deleteSyllabus(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useForkSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ForkRequest }) =>
      syllabusesApi.forkSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
      // Pre-populate the status cache for the new fork immediately
      qc.setQueryData(syllabusKeys.status(data.id), data)
    },
  })
}
