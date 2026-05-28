import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type {
  ApproveRequest,
  ExportSyllabusRequest,
  GenerateSyllabusRequest,
  LockRequest,
  RejectRequest,
} from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

export function useSubmitSyllabusForReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => syllabusesApi.submitSyllabusForReview(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useGenerateSyllabus(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GenerateSyllabusRequest) =>
      syllabusesApi.generateSyllabus(syllabusId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(syllabusId) })
    },
  })
}

export function useApproveSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ApproveRequest }) =>
      syllabusesApi.approveSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useRejectSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RejectRequest }) =>
      syllabusesApi.rejectSyllabus(id, payload),
    onSuccess: (_data, { id }) => {
      // Original syllabus and new draft both need refresh
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useLockSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: LockRequest }) =>
      syllabusesApi.lockSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useUnlockSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => syllabusesApi.unlockSyllabus(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
    },
  })
}

export function useExportSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ExportSyllabusRequest }) =>
      syllabusesApi.exportSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.job(data.syllabus_id, data.job_id) })
    },
  })
}
