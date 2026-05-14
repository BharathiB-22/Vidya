import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type { KitQuizlet, KitQuizletCreate, KitQuizletUpdate } from '@/types/courseKit'
import { courseKitKeys } from './useCourseKit'

export function useAddQuizlet(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KitQuizletCreate) => courseKitApi.addQuizlet(kitId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      const prev = qc.getQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId))
      qc.setQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId), (old) => [
        ...(old ?? []),
        {
          id:                 `optimistic-${Date.now()}`,
          kit_id:             kitId,
          question_number:    payload.question_number,
          question_text:      payload.question_text,
          question_type:      payload.question_type ?? 'MCQ',
          options:            (payload.options ?? []) as unknown as Record<string, unknown>[],
          answer_key:         payload.answer_key ?? null,
          answer_explanation: payload.answer_explanation ?? null,
          bloom_level:        payload.bloom_level ?? null,
          co_reference:       payload.co_reference ?? null,
          created_at:         new Date().toISOString(),
          updated_at:         null,
        } as KitQuizlet,
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.quizlets(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useUpdateQuizlet(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ quizletId, payload }: { quizletId: string; payload: KitQuizletUpdate }) =>
      courseKitApi.updateQuizlet(kitId, quizletId, payload),
    onMutate: async ({ quizletId, payload }) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      const prev = qc.getQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId))
      qc.setQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId), (old) =>
        old?.map((q) => (q.id === quizletId ? ({ ...q, ...payload } as KitQuizlet) : q)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.quizlets(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useDeleteQuizlet(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (quizletId: string) => courseKitApi.deleteQuizlet(kitId, quizletId),
    onMutate: async (quizletId) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      const prev = qc.getQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId))
      qc.setQueryData<KitQuizlet[]>(courseKitKeys.quizlets(kitId), (old) =>
        old?.filter((q) => q.id !== quizletId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.quizlets(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}
