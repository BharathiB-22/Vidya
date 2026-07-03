import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import { courseKitKeys } from './useCourseKit'

interface UploadResourceArgs {
  kitId: string
  file:  File
}

export function useUploadResource() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ kitId, file }: UploadResourceArgs) => {
      const { object_key, presigned_url } = await courseKitApi.generateResourceUploadUrl(kitId, {
        original_filename: file.name,
        content_type:      file.type,
        size_bytes:         file.size,
      })

      const putResp = await fetch(presigned_url, {
        method:  'PUT',
        headers: { 'Content-Type': file.type },
        body:    file,
      })
      if (!putResp.ok) {
        throw new Error(`File upload to storage failed (HTTP ${putResp.status}).`)
      }

      return courseKitApi.confirmResourceUpload(kitId, {
        object_key,
        original_filename: file.name,
        content_type:      file.type,
        size_bytes:         file.size,
      })
    },
    onSuccess: (_data, { kitId }) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.resources(kitId) })
    },
  })
}

export function useDeleteResource() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kitId, assetId }: { kitId: string; assetId: string }) =>
      courseKitApi.deleteResource(kitId, assetId),
    onSuccess: (_data, { kitId }) => {
      qc.invalidateQueries({ queryKey: courseKitKeys.resources(kitId) })
    },
  })
}

export async function downloadResource(kitId: string, assetId: string, filename: string) {
  const { presigned_url } = await courseKitApi.getResourceDownloadUrl(kitId, assetId)
  const a = document.createElement('a')
  a.href = presigned_url
  a.download = filename
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
