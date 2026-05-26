// Storage — presigned URL upload flow
import api from '@/lib/api'

export interface GenerateUploadUrlPayload {
  entity_type: string
  entity_id:   string  // UUID string
  original_filename: string
  content_type: string
  size_bytes:   number
}

export interface GenerateUploadUrlResponse {
  object_key:        string
  presigned_url:     string
  expires_in_seconds: number
}

export interface CreateAssetPayload {
  object_key:        string
  entity_type:       string
  entity_id:         string
  original_filename: string
  content_type:      string
  size_bytes:        number
}

const BASE = '/storage'

export async function generateUploadUrl(
  payload: GenerateUploadUrlPayload,
): Promise<GenerateUploadUrlResponse> {
  const { data } = await api.post(`${BASE}/upload-url`, payload)
  return data
}

export async function createAsset(payload: CreateAssetPayload): Promise<void> {
  await api.post(`${BASE}/assets`, payload)
}
