import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type {
  ArchiveRequest,
  ForkRequest,
  GenerateKitRequest,
  KitExportRequest,
  PublishRequest,
} from '@/types/courseKit'
import { courseKitKeys } from './useCourseKit'

export function useGenerateKit(kitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GenerateKitRequest) => courseKitApi.generateKit(kitId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: courseKitKeys.status(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    },
  })
}

export function usePublishKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PublishRequest }) =>
      courseKitApi.publishKit(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
    },
  })
}

export function useArchiveKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ArchiveRequest }) =>
      courseKitApi.archiveKit(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
    },
  })
}

export function useForkKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ForkRequest }) =>
      courseKitApi.forkKit(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.all })
      // Pre-populate the status cache for the new fork immediately
      qc.setQueryData(courseKitKeys.status(data.id), data)
    },
  })
}

export function useExportKit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: KitExportRequest }) =>
      courseKitApi.requestExport(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.exports(data.kit_id) })
    },
  })
}
