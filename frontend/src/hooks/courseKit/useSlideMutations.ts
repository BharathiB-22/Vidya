import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type { KitSlide, KitSlideCreate, KitSlideReorder, KitSlideUpdate } from '@/types/courseKit'
import { courseKitKeys } from './useCourseKit'

export function useAddSlide(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KitSlideCreate) => courseKitApi.addSlide(kitId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.slides(kitId) })
      const prev = qc.getQueryData<KitSlide[]>(courseKitKeys.slides(kitId))
      qc.setQueryData<KitSlide[]>(courseKitKeys.slides(kitId), (old) => [
        ...(old ?? []),
        {
          id:            `optimistic-${Date.now()}`,
          kit_id:        kitId,
          slide_number:  payload.slide_number,
          title:         payload.title,
          content:       (payload.content ?? { bullets: [], key_concepts: [], image_hint: null, code_snippet: null }) as unknown as Record<string, unknown>,
          speaker_notes: payload.speaker_notes ?? null,
          bloom_level:   payload.bloom_level ?? null,
          co_reference:  payload.co_reference ?? null,
          created_at:    new Date().toISOString(),
          updated_at:    null,
        } as KitSlide,
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.slides(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.slides(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useUpdateSlide(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ slideId, payload }: { slideId: string; payload: KitSlideUpdate }) =>
      courseKitApi.updateSlide(kitId, slideId, payload),
    onMutate: async ({ slideId, payload }) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.slides(kitId) })
      const prev = qc.getQueryData<KitSlide[]>(courseKitKeys.slides(kitId))
      qc.setQueryData<KitSlide[]>(courseKitKeys.slides(kitId), (old) =>
        old?.map((s) => (s.id === slideId ? ({ ...s, ...payload } as KitSlide) : s)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.slides(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.slides(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useDeleteSlide(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (slideId: string) => courseKitApi.deleteSlide(kitId, slideId),
    onMutate: async (slideId) => {
      await qc.cancelQueries({ queryKey: courseKitKeys.slides(kitId) })
      const prev = qc.getQueryData<KitSlide[]>(courseKitKeys.slides(kitId))
      qc.setQueryData<KitSlide[]>(courseKitKeys.slides(kitId), (old) =>
        old?.filter((s) => s.id !== slideId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(courseKitKeys.slides(kitId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.slides(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.compliance(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function useReorderSlides(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KitSlideReorder) => courseKitApi.reorderSlides(kitId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.slides(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}
