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

export interface StorageAsset {
  id: string
  uploaded_by_user_id: string
  entity_type: string
  entity_id: string
  object_key: string
  original_filename: string
  size_bytes: number
  content_type: string
  created_at: string
}

const BASE = '/storage'

export async function generateUploadUrl(
  payload: GenerateUploadUrlPayload,
): Promise<GenerateUploadUrlResponse> {
  const { data } = await api.post(`${BASE}/upload-url`, payload)
  return data
}

export async function createAsset(payload: CreateAssetPayload): Promise<StorageAsset> {
  const { data } = await api.post(`${BASE}/assets`, payload)
  return data
}

export async function getDownloadUrl(assetId: string): Promise<string> {
  const { data } = await api.get<{ presigned_url: string }>(`${BASE}/${assetId}/download-url`)
  return data.presigned_url
}
