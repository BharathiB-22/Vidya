import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type {
  ApproveRequest,
  ExportSyllabusRequest,
  GenerateSyllabusRequest,
  RegenerateSectionRequest,
} from '@/types/syllabus'
import { syllabusKeys } from './useSyllabuses'

/**
 * Actions on an official syllabus. Board-only, all of them.
 *
 * Gone with the old workflow: useSubmitSyllabusForReview, useResubmitSyllabus,
 * useRejectSyllabus, useRequestRevision, useLockSyllabus, useUnlockSyllabus.
 *
 * The first four existed because FACULTY authored a syllabus and a DEAN reviewed
 * it — two parties, so the work had to be handed between them. The Board writes
 * the syllabus and signs it off, so there is nobody to hand it to.
 *
 * Lock/unlock is gone because a syllabus is locked by CURRICULUM APPROVAL, not on
 * its own, and is never unlocked.
 */

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

/**
 * Rewrite ONE section — a unit, the objectives, the outcomes, the bibliography.
 *
 * This exists so the Board never has to regenerate a whole syllabus because a
 * single unit came out weak. By the time they notice, the rest will usually have
 * been hand-edited, and a full regeneration would throw every bit of that away.
 */
export function useRegenerateSection(syllabusId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: RegenerateSectionRequest) =>
      syllabusesApi.regenerateSection(syllabusId, payload),
    onSuccess: () => {
      // The worker rewrites in the background; poll the pieces it can touch.
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.units(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.outcomes(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.references(syllabusId) })
    },
  })
}

/** DRAFT → APPROVED. One board member signs off one official syllabus. */
export function useApproveSyllabus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ApproveRequest }) =>
      syllabusesApi.approveSyllabus(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: syllabusKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
      // The curriculum's readiness — "18 of 42 approved" — just moved.
      qc.invalidateQueries({ queryKey: ['governance'] })
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
