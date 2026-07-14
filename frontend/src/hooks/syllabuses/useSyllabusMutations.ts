import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import { getErrorMessage } from '@/lib/api'
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

/**
 * How ONE subject's syllabus comes into being — and the Board decides, subject by
 * subject, which way.
 *
 *   AI      the shell is created, the Board's academic structure is written to it,
 *           and the generator is asked for a draft against that structure.
 *   MANUAL  the shell is created, and nothing else happens. No model runs. The Board
 *           writes the syllabus itself, in the same editor, using the same validation.
 *
 * BOTH END IN THE SAME PLACE — an empty syllabus at /syllabuses/{id}, which is the only
 * syllabus editor there is. The difference between them is not a different page or a
 * different workflow; it is only whether a first draft was written for the Board or by
 * the Board. Everything after that — the editing, the validation, the readiness, the
 * approval — cannot tell the two apart, and should not be able to.
 *
 * This replaces the bulk generator, which queued an AI job for every subject in the
 * curriculum on one click: forty syllabi and three hundred model calls, whether anybody
 * wanted them or not. A Board of Studies does not decide to draft forty syllabi. It
 * decides whether THIS subject wants an AI draft, or is better written by the professor
 * who has taught it for fifteen years.
 */
export interface PrepareSyllabusArgs {
  courseId: string
  mode: 'AI' | 'MANUAL'
  /** THEORY only, and required for AI: the Board's academic structure. */
  unitCount?: number
  unitHours?: number[]
  /**
   * THEORY only: what the subject is taught for, and at how many hours a week. The
   * Board's figures — the AI paces the whole syllabus against the total, and the unit
   * hours must add up to it or the server refuses to generate.
   */
  teachingHours?: number
  hoursPerWeek?: number
  instructions?: string
}

export function usePrepareSyllabus() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      courseId, mode, unitCount, unitHours, teachingHours, hoursPerWeek, instructions,
    }: PrepareSyllabusArgs) => {
      const syllabus = await syllabusesApi.createSyllabus({ course_id: courseId })

      // THE STRUCTURE IS SAVED THROUGH EITHER DOOR — and this used to be inside the AI
      // branch, which is the bug it exists to fix. A syllabus written by hand was
      // created with no teaching hours and the default unit count of five, neither of
      // which anybody had been asked about: the Board then wrote its four units and was
      // told the syllabus was missing one, against a figure it had never chosen.
      //
      // How a subject is divided and how long each part is taught is a curriculum
      // decision. It belongs to the Board whether or not a model is ever involved.
      if (unitCount && unitHours?.length) {
        await syllabusesApi.updateSyllabus(syllabus.id, {
          unit_count: unitCount,
          unit_hours: unitHours,
          teaching_hours: teachingHours,
          hours_per_week: hoursPerWeek,
        })
      }

      // And the manual door stops here. No model runs, nothing is generated, and the
      // Board opens the same editor the AI door opens — with its structure already in
      // it — to write the syllabus itself.
      if (mode === 'MANUAL') return syllabus

      const job = await syllabusesApi.generateSyllabus(syllabus.id, {
        custom_instructions: instructions,
        unit_count: unitCount,
        unit_hours: unitHours,
        teaching_hours: teachingHours,
        hours_per_week: hoursPerWeek,
      })

      // Remember which job is writing it, so the syllabus page can say what the AI is
      // doing — "Generating Unit III…" — rather than spin.
      qc.setQueryData(syllabusKeys.runningJob(syllabus.id), job.job_id)
      return syllabus
    },

    onSuccess: () => {
      qc.invalidateQueries({ queryKey: syllabusKeys.all })
      qc.invalidateQueries({ queryKey: ['governance'] })
    },
    onError: (err) => addToast(getErrorMessage(err), 'error', 9000),
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
