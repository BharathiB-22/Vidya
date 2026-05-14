import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type { CourseKitCreate, CourseKitUpdate } from '@/types/courseKit'
import { courseKitKeys } from './useCourseKit'

export function useCreateKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseKitCreate) => courseKitApi.createKit(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
    },
  })
}

export function useUpdateKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CourseKitUpdate }) =>
      courseKitApi.updateKit(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
    },
  })
}

export function useDeleteKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => courseKitApi.deleteKit(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
    },
  })
}
