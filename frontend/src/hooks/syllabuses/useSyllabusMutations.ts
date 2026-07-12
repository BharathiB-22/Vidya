import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import { addToast } from '@/hooks/useToast'
import type {
  DeanDocumentEditRequest,
  ForkRequest,
  SyllabusCreate,
  SyllabusUpdate,
} from '@/types/syllabus'
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

/**
 * The Dean adapting an APPROVED Internship / Project / Seminar document.
 *
 * A separate mutation from `useUpdateSyllabus` because it is a separate act: it
 * lands on an approved, otherwise-immutable row, it does NOT withdraw the Board's
 * approval, and it stamps the row with the Dean's name so the governance trail can
 * tell the two hands apart. The API refuses it outright on a theory syllabus.
 */
export function useDeanEditDocument(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: DeanDocumentEditRequest) =>
      syllabusesApi.deanEditDocument(syllabusId, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
      addToast('Guidelines updated. The Board’s approval stands.', 'success')
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
