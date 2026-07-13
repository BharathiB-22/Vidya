import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
    onSuccess: (job) => {
      // Remember WHICH job is writing this syllabus, so the page can say what it is
      // doing — "Generating Unit III…" — instead of spinning. Cached rather than held
      // in component state: the Board presses Generate in the action bar and reads the
      // progress on the page, and the two must not have to pass it between them.
      qc.setQueryData(syllabusKeys.runningJob(syllabusId), job.job_id)
      qc.invalidateQueries({ queryKey: syllabusKeys.status(syllabusId) })
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(syllabusId) })
    },
  })
}

/**
 * What the AI is doing to this syllabus, right now.
 *
 * A generation is ten AI calls and several minutes. A spinner for the whole of it is
 * what makes this feel like a machine being asked for a document; a Board watching
 * "Generating Unit III…" is watching a syllabus being written.
 *
 * The message comes from the job itself — the worker writes it as it works — so the
 * words are the backend's and this only prints them. Polled while a generation is in
 * flight, and not at all otherwise.
 */
export function useGenerationProgress(syllabusId: string, isGenerating: boolean) {
  const qc = useQueryClient()
  const jobId = qc.getQueryData<string>(syllabusKeys.runningJob(syllabusId))

  const { data } = useQuery({
    queryKey: syllabusKeys.job(syllabusId, jobId ?? ''),
    queryFn: () => syllabusesApi.getJobStatus(syllabusId, jobId as string),
    enabled: Boolean(jobId) && isGenerating,
    refetchInterval: 2000,
  })

  const result = data?.result as { message?: string; phase?: string } | null | undefined
  return result?.message ?? null
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
