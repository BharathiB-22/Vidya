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

// ── Export file lifecycle: upload an edited deck, replace, delete ──────────────

/**
 * Upload an externally-edited .pptx/.pdf back as a kit export.
 * Presigned PUT to storage, then confirm. Pass replaceAssetId to REPLACE an
 * existing export (old one is removed server-side after the new one is stored).
 */
export function useUploadExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (
      { kitId, file, replaceAssetId }:
      { kitId: string; file: File; replaceAssetId?: string },
    ) => {
      const { object_key, presigned_url } = await courseKitApi.generateExportUploadUrl(kitId, {
        original_filename: file.name,
        content_type:      file.type,
        size_bytes:        file.size,
      })
      const putResp = await fetch(presigned_url, {
        method:  'PUT',
        headers: { 'Content-Type': file.type },
        body:    file,
      })
      if (!putResp.ok) {
        throw new Error(`Deck upload to storage failed (HTTP ${putResp.status}).`)
      }
      return courseKitApi.confirmExportUpload(kitId, {
        object_key,
        original_filename: file.name,
        content_type:      file.type,
        size_bytes:        file.size,
        replace_asset_id:  replaceAssetId ?? null,
      })
    },
    onSuccess: (_data, { kitId }) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.exports(kitId) })
    },
  })
}

export function useDeleteExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kitId, assetId }: { kitId: string; assetId: string }) =>
      courseKitApi.deleteExport(kitId, assetId),
    onSuccess: (_data, { kitId }) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.exports(kitId) })
    },
  })
}
