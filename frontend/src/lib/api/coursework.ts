import api from '@/lib/api'
import type {
  CourseworkAssignment,
  CourseworkAssignmentCreate,
  CourseworkAssignmentListResponse,
  CourseworkAssignmentUpdate,
  CourseworkGradePayload,
  CourseworkStatistics,
  CourseworkSubmission,
  CourseworkSubmissionListResponse,
  CourseworkSubmitPayload,
} from '@/types/coursework'

const BASE = '/assignments'

// ── Faculty — Assignments ────────────────────────────────────────────────────

export async function createAssignment(payload: CourseworkAssignmentCreate): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(BASE, payload)
  return data
}

export async function listAssignments(params?: {
  syllabus_id?: string
  status?: string
}): Promise<CourseworkAssignmentListResponse> {
  const { data } = await api.get<CourseworkAssignmentListResponse>(BASE, { params })
  return data
}

export async function getAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.get<CourseworkAssignment>(`${BASE}/${id}`)
  return data
}

export async function updateAssignment(
  id: string,
  payload: CourseworkAssignmentUpdate
): Promise<CourseworkAssignment> {
  const { data } = await api.put<CourseworkAssignment>(`${BASE}/${id}`, payload)
  return data
}

export async function publishAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/publish`)
  return data
}

export async function closeAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/close`)
  return data
}

// ── Faculty — Submissions ────────────────────────────────────────────────────

export async function listSubmissions(assignmentId: string): Promise<CourseworkSubmissionListResponse> {
  const { data } = await api.get<CourseworkSubmissionListResponse>(`${BASE}/${assignmentId}/submissions`)
  return data
}

export async function gradeSubmission(
  submissionId: string,
  payload: CourseworkGradePayload
): Promise<CourseworkSubmission> {
  const { data } = await api.patch<CourseworkSubmission>(`${BASE}/submissions/${submissionId}/grade`, payload)
  return data
}

export async function returnSubmission(submissionId: string): Promise<CourseworkSubmission> {
  const { data } = await api.post<CourseworkSubmission>(`${BASE}/submissions/${submissionId}/return`)
  return data
}

export async function getAssignmentStatistics(assignmentId: string): Promise<CourseworkStatistics> {
  const { data } = await api.get<CourseworkStatistics>(`${BASE}/${assignmentId}/statistics`)
  return data
}

// ── Storage — submission file upload (generic, reused as-is from Labs) ──────

export interface UploadUrlRequest {
  entity_type: string
  entity_id: string
  original_filename: string
  content_type: string
  size_bytes: number
}

export interface UploadUrlResponse {
  object_key: string
  presigned_url: string
  expires_in_seconds: number
}

export async function requestSubmissionUploadUrl(
  params: UploadUrlRequest
): Promise<UploadUrlResponse> {
  const { data } = await api.post<UploadUrlResponse>('/storage/upload-url', params)
  return data
}

export function uploadFileToPresignedUrl(
  presignedUrl: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', presignedUrl)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`Upload failed: HTTP ${xhr.status}`))
    }
    xhr.onerror = () => reject(new Error('Network error during file upload'))
    xhr.send(file)
  })
}

export async function getSubmissionFileUrl(
  submissionId: string
): Promise<{ url: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ url: string; expires_in_seconds: number }>(
    `${BASE}/submissions/${submissionId}/file-url`
  )
  return data
}

// ── Student ──────────────────────────────────────────────────────────────────

export async function studentListAssignments(params?: {
  syllabus_id?: string
}): Promise<CourseworkAssignmentListResponse> {
  const { data } = await api.get<CourseworkAssignmentListResponse>(`${BASE}/student`, { params })
  return data
}

export async function studentGetAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.get<CourseworkAssignment>(`${BASE}/student/${id}`)
  return data
}

export async function studentSubmit(
  assignmentId: string,
  payload: CourseworkSubmitPayload
): Promise<CourseworkSubmission> {
  const { data } = await api.post<CourseworkSubmission>(`${BASE}/student/${assignmentId}/submit`, payload)
  return data
}

export async function studentMySubmissions(params?: {
  syllabus_id?: string
}): Promise<CourseworkSubmissionListResponse> {
  const { data } = await api.get<CourseworkSubmissionListResponse>(`${BASE}/student/submissions/my`, { params })
  return data
}

export async function studentGetResult(submissionId: string): Promise<CourseworkSubmission> {
  const { data } = await api.get<CourseworkSubmission>(`${BASE}/student/submissions/${submissionId}/result`)
  return data
}
