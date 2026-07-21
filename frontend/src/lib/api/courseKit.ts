import api from '@/lib/api'
import type {
  ArchiveRequest,
  ComplianceCheckResponse,
  CourseKit,
  CourseKitCreate,
  CourseKitDetail,
  CourseKitListFilters,
  CourseKitListResponse,
  CourseKitStatusResponse,
  CourseKitUpdate,
  CourseKitVersionResponse,
  ForkRequest,
  GenerateKitRequest,
  KitAIJobResponse,
  KitAssignment,
  KitAssignmentCreate,
  KitAssignmentUpdate,
  KitExportAsset,
  KitExportDownloadResponse,
  KitExportJobResponse,
  KitExportRequest,
  KitJobStatusResponse,
  KitResourceConfirmRequest,
  KitResourceDownloadUrlResponse,
  KitResourceFile,
  KitResourceListResponse,
  KitResourceUploadUrlRequest,
  KitResourceUploadUrlResponse,
  KitSlide,
  KitSlideCreate,
  KitSlideReorder,
  KitSlideUpdate,
  PublishRequest,
} from '@/types/courseKit'

const BASE = '/course-kits'

// ---------------------------------------------------------------------------
// Kit CRUD
// ---------------------------------------------------------------------------

export async function createKit(payload: CourseKitCreate): Promise<CourseKit> {
  const { data } = await api.post<CourseKit>(BASE, payload)
  return data
}

export async function listKits(filters: CourseKitListFilters): Promise<CourseKitListResponse> {
  const { data } = await api.get<CourseKitListResponse>(BASE, { params: filters })
  return data
}

export async function getKit(id: string): Promise<CourseKitDetail> {
  const { data } = await api.get<CourseKitDetail>(`${BASE}/${id}`)
  return data
}

export async function getKitStatus(id: string): Promise<CourseKitStatusResponse> {
  const { data } = await api.get<CourseKitStatusResponse>(`${BASE}/${id}/status`)
  return data
}

export async function updateKit(id: string, payload: CourseKitUpdate): Promise<CourseKit> {
  const { data } = await api.patch<CourseKit>(`${BASE}/${id}`, payload)
  return data
}

export async function deleteKit(id: string): Promise<void> {
  await api.delete(`${BASE}/${id}`)
}

export async function listVersions(id: string): Promise<CourseKitVersionResponse[]> {
  const { data } = await api.get<CourseKitVersionResponse[]>(`${BASE}/${id}/versions`)
  return data
}

// ---------------------------------------------------------------------------
// AI generation
// ---------------------------------------------------------------------------

export async function generateKit(
  id: string,
  payload: GenerateKitRequest,
): Promise<KitAIJobResponse> {
  const { data } = await api.post<KitAIJobResponse>(`${BASE}/${id}/generate`, payload)
  return data
}

export async function getJobStatus(
  kitId: string,
  jobId: string,
): Promise<KitJobStatusResponse> {
  const { data } = await api.get<KitJobStatusResponse>(`${BASE}/${kitId}/jobs/${jobId}`)
  return data
}

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

export async function publishKit(
  id: string,
  payload: PublishRequest,
): Promise<CourseKitStatusResponse> {
  const { data } = await api.post<CourseKitStatusResponse>(`${BASE}/${id}/publish`, payload)
  return data
}

export async function archiveKit(
  id: string,
  payload: ArchiveRequest,
): Promise<CourseKitStatusResponse> {
  const { data } = await api.post<CourseKitStatusResponse>(`${BASE}/${id}/archive`, payload)
  return data
}

export async function forkKit(
  id: string,
  payload: ForkRequest,
): Promise<CourseKitStatusResponse> {
  const { data } = await api.post<CourseKitStatusResponse>(`${BASE}/${id}/fork`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

export async function getKitCompliance(id: string): Promise<ComplianceCheckResponse> {
  const { data } = await api.get<ComplianceCheckResponse>(`${BASE}/${id}/compliance`)
  return data
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export async function requestExport(
  id: string,
  payload: KitExportRequest,
): Promise<KitExportJobResponse> {
  const { data } = await api.post<KitExportJobResponse>(`${BASE}/${id}/export`, payload)
  return data
}

export async function listExports(id: string): Promise<KitExportAsset[]> {
  const { data } = await api.get<KitExportAsset[]>(`${BASE}/${id}/exports`)
  return data
}

export async function getExportDownload(
  kitId: string,
  assetId: string,
): Promise<KitExportDownloadResponse> {
  const { data } = await api.get<KitExportDownloadResponse>(
    `${BASE}/${kitId}/exports/${assetId}/download`,
  )
  return data
}

// ---- Export file lifecycle: upload an edited deck / replace / delete ----

export async function generateExportUploadUrl(
  kitId: string,
  payload: KitResourceUploadUrlRequest,
): Promise<KitResourceUploadUrlResponse> {
  const { data } = await api.post<KitResourceUploadUrlResponse>(
    `${BASE}/${kitId}/exports/upload-url`,
    payload,
  )
  return data
}

export async function confirmExportUpload(
  kitId: string,
  payload: KitResourceConfirmRequest & { replace_asset_id?: string | null },
): Promise<KitExportAsset> {
  const { data } = await api.post<KitExportAsset>(`${BASE}/${kitId}/exports`, payload)
  return data
}

export async function deleteExport(kitId: string, assetId: string): Promise<void> {
  await api.delete(`${BASE}/${kitId}/exports/${assetId}`)
}

// ---------------------------------------------------------------------------
// Slides
// ---------------------------------------------------------------------------

export async function listSlides(kitId: string): Promise<KitSlide[]> {
  const { data } = await api.get<KitSlide[]>(`${BASE}/${kitId}/slides`)
  return data
}

export async function addSlide(kitId: string, payload: KitSlideCreate): Promise<KitSlide> {
  const { data } = await api.post<KitSlide>(`${BASE}/${kitId}/slides`, payload)
  return data
}

export async function updateSlide(
  kitId: string,
  slideId: string,
  payload: KitSlideUpdate,
): Promise<KitSlide> {
  const { data } = await api.patch<KitSlide>(`${BASE}/${kitId}/slides/${slideId}`, payload)
  return data
}

export async function deleteSlide(kitId: string, slideId: string): Promise<void> {
  await api.delete(`${BASE}/${kitId}/slides/${slideId}`)
}

export async function reorderSlides(
  kitId: string,
  payload: KitSlideReorder,
): Promise<{ updated: number }> {
  const { data } = await api.put<{ updated: number }>(
    `${BASE}/${kitId}/slides/reorder`,
    payload,
  )
  return data
}

// ---------------------------------------------------------------------------
// Assignments
// ---------------------------------------------------------------------------

export async function listAssignments(kitId: string): Promise<KitAssignment[]> {
  const { data } = await api.get<KitAssignment[]>(`${BASE}/${kitId}/assignments`)
  return data
}

export async function addAssignment(
  kitId: string,
  payload: KitAssignmentCreate,
): Promise<KitAssignment> {
  const { data } = await api.post<KitAssignment>(`${BASE}/${kitId}/assignments`, payload)
  return data
}

export async function updateAssignment(
  kitId: string,
  assignmentId: string,
  payload: KitAssignmentUpdate,
): Promise<KitAssignment> {
  const { data } = await api.patch<KitAssignment>(
    `${BASE}/${kitId}/assignments/${assignmentId}`,
    payload,
  )
  return data
}

export async function deleteAssignment(kitId: string, assignmentId: string): Promise<void> {
  await api.delete(`${BASE}/${kitId}/assignments/${assignmentId}`)
}

// ---------------------------------------------------------------------------
// Faculty-uploaded resources (PDF/PPT/DOCX/notes)
// ---------------------------------------------------------------------------

export async function listResources(kitId: string): Promise<KitResourceListResponse> {
  const { data } = await api.get<KitResourceListResponse>(`${BASE}/${kitId}/resources`)
  return data
}

export async function generateResourceUploadUrl(
  kitId: string,
  payload: KitResourceUploadUrlRequest,
): Promise<KitResourceUploadUrlResponse> {
  const { data } = await api.post<KitResourceUploadUrlResponse>(
    `${BASE}/${kitId}/resources/upload-url`,
    payload,
  )
  return data
}

export async function confirmResourceUpload(
  kitId: string,
  payload: KitResourceConfirmRequest,
): Promise<KitResourceFile> {
  const { data } = await api.post<KitResourceFile>(`${BASE}/${kitId}/resources`, payload)
  return data
}

export async function getResourceDownloadUrl(
  kitId: string,
  assetId: string,
): Promise<KitResourceDownloadUrlResponse> {
  const { data } = await api.get<KitResourceDownloadUrlResponse>(
    `${BASE}/${kitId}/resources/${assetId}/download-url`,
  )
  return data
}

export async function deleteResource(kitId: string, assetId: string): Promise<void> {
  await api.delete(`${BASE}/${kitId}/resources/${assetId}`)
}

// ---------------------------------------------------------------------------
// Student access (Phase 2 — read-only, scoped to enrolled courses, PUBLISHED only)
// ---------------------------------------------------------------------------

export async function studentListKits(
  syllabusId: string,
  unitNumber?: number,
): Promise<CourseKitListResponse> {
  const { data } = await api.get<CourseKitListResponse>(`${BASE}/student`, {
    params: { syllabus_id: syllabusId, unit_number: unitNumber },
  })
  return data
}

export async function studentGetKit(kitId: string): Promise<CourseKitDetail> {
  const { data } = await api.get<CourseKitDetail>(`${BASE}/student/${kitId}`)
  return data
}

export async function studentListResources(kitId: string): Promise<KitResourceListResponse> {
  const { data } = await api.get<KitResourceListResponse>(`${BASE}/student/${kitId}/resources`)
  return data
}

export async function studentGetResourceDownloadUrl(
  kitId: string,
  assetId: string,
): Promise<KitResourceDownloadUrlResponse> {
  const { data } = await api.get<KitResourceDownloadUrlResponse>(
    `${BASE}/student/${kitId}/resources/${assetId}/download-url`,
  )
  return data
}
