import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { Course, CourseCreate, CourseUpdate } from '@/types/program'
import { programKeys } from './usePrograms'

// ---------------------------------------------------------------------------
// All three mutations use the same optimistic update pattern:
//   onMutate  → cancel in-flight queries → snapshot → apply optimistic change
//   onError   → rollback to snapshot
//   onSettled → invalidate to sync with server truth
// ---------------------------------------------------------------------------

export function useAddCourse(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseCreate) => programsApi.addCourse(programId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: programKeys.courses(programId) })
      const prev = qc.getQueryData<Course[]>(programKeys.courses(programId))
      qc.setQueryData<Course[]>(programKeys.courses(programId), (old) => [
        ...(old ?? []),
        {
          id: `optimistic-${Date.now()}`,
          program_id: programId,
          // The server assigns the code, so there is nothing to show optimistically.
          // onSettled invalidates and the real code arrives with the refetch.
          code: payload.code ?? '…',
          title: payload.title,
          credits: payload.credits,
          semester: payload.semester,
          course_type: payload.course_type ?? null,
          is_elective: payload.is_elective ?? false,
          elective_basket_id: payload.elective_basket_id ?? null,
          is_ai_generated: false,
          hours_lecture: payload.hours_lecture ?? null,
          hours_tutorial: payload.hours_tutorial ?? null,
          hours_practical: payload.hours_practical ?? null,
          description: payload.description ?? null,
          created_at: new Date().toISOString(),
          updated_at: null,
        },
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.courses(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
    },
  })
}

export function useUpdateCourse(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ courseId, payload }: { courseId: string; payload: CourseUpdate }) =>
      programsApi.updateCourse(programId, courseId, payload),
    onMutate: async ({ courseId, payload }) => {
      await qc.cancelQueries({ queryKey: programKeys.courses(programId) })
      const prev = qc.getQueryData<Course[]>(programKeys.courses(programId))
      qc.setQueryData<Course[]>(programKeys.courses(programId), (old) =>
        old?.map((c) =>
          c.id === courseId
            ? { ...c, ...payload, updated_at: new Date().toISOString() }
            : c,
        ) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.courses(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
    },
  })
}

export function useDeleteCourse(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (courseId: string) => programsApi.deleteCourse(programId, courseId),
    onMutate: async (courseId) => {
      await qc.cancelQueries({ queryKey: programKeys.courses(programId) })
      const prev = qc.getQueryData<Course[]>(programKeys.courses(programId))
      qc.setQueryData<Course[]>(programKeys.courses(programId), (old) =>
        old?.filter((c) => c.id !== courseId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.courses(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
    },
  })
}
