import api from '@/lib/api'
import type {
  CurationJobResponse,
  FacultyAddItemPayload,
  FacultyNoteUploadPayload,
  IndexJobResponse,
  JobStatus,
  LearningPackage,
  LearningPackageListFilters,
  LearningPackageListResponse,
  PackageItem,
  PackageStatus,
  QASession,
  QASessionWithMessages,
  RAGAnswerResponse,
} from '@/types/learningPackage'

const BASE = '/learning-packages'

export async function listPackages(
  filters: LearningPackageListFilters,
): Promise<LearningPackageListResponse> {
  const params: Record<string, unknown> = {}
  if (filters.syllabus_id) params.syllabus_id = filters.syllabus_id
  if (filters.status)      params.status      = filters.status
  if (filters.page)        params.page        = filters.page
  if (filters.page_size)   params.page_size   = filters.page_size
  const { data } = await api.get<LearningPackageListResponse>(BASE, { params })
  return data
}

export async function getPackage(id: string): Promise<LearningPackage> {
  const { data } = await api.get<LearningPackage>(`${BASE}/${id}`)
  return data
}

export async function getPackageStatus(id: string): Promise<LearningPackage> {
  const { data } = await api.get<LearningPackage>(`${BASE}/${id}/status`)
  return data
}

export async function listItems(
  packageId: string,
  facultyOnly = false,
): Promise<PackageItem[]> {
  const { data } = await api.get<PackageItem[]>(`${BASE}/${packageId}/items`, {
    params: { faculty_only: facultyOnly },
  })
  return data
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`${BASE}/jobs/${jobId}`)
  return data
}

// Convenience: list packages filtered to READY status for student browsing.
export async function listReadyPackages(
  syllabusId: string,
): Promise<LearningPackageListResponse> {
  return listPackages({ syllabus_id: syllabusId, status: 'READY' as PackageStatus })
}

// Student-scoped discovery (Phase 2): enrollment-checked, forces status=READY server-side.
export async function studentListPackages(
  syllabusId: string,
  unitNumber?: number,
): Promise<LearningPackageListResponse> {
  const { data } = await api.get<LearningPackageListResponse>(`${BASE}/student`, {
    params: { syllabus_id: syllabusId, unit_number: unitNumber },
  })
  return data
}

// ---------------------------------------------------------------------------
// Faculty curation mutations
// ---------------------------------------------------------------------------

export async function triggerCuration(
  syllabusId: string,
  unitNumber: number,
  topN?: number,
): Promise<CurationJobResponse> {
  const body: Record<string, unknown> = {
    syllabus_id: syllabusId,
    unit_number: unitNumber,
  }
  if (topN) body.top_n = topN
  const { data } = await api.post<CurationJobResponse>(`${BASE}/curate`, body)
  return data
}

export async function triggerIndexing(packageId: string): Promise<IndexJobResponse> {
  const { data } = await api.post<IndexJobResponse>(`${BASE}/${packageId}/index`)
  return data
}

export async function addFacultyItem(
  packageId: string,
  payload: FacultyAddItemPayload,
): Promise<PackageItem> {
  const { data } = await api.post<PackageItem>(`${BASE}/${packageId}/items`, payload)
  return data
}

export async function removeItem(packageId: string, itemId: string): Promise<void> {
  await api.delete(`${BASE}/${packageId}/items/${itemId}`)
}

export async function uploadFacultyNote(
  packageId: string,
  payload: FacultyNoteUploadPayload,
): Promise<PackageItem> {
  const form = new FormData()
  form.append('file', payload.file, payload.file.name)
  if (payload.title) form.append('title', payload.title)
  // Do NOT set Content-Type manually — axios/the browser must compute the
  // multipart boundary itself. A hardcoded 'multipart/form-data' header has
  // no boundary parameter, so the server can't parse the body and the
  // upload fails.
  const { data } = await api.post<PackageItem>(`${BASE}/${packageId}/notes`, form)
  return data
}

export async function toggleRecommendation(
  packageId: string,
  itemId: string,
  value: boolean,
): Promise<PackageItem> {
  const { data } = await api.patch<PackageItem>(
    `${BASE}/${packageId}/items/${itemId}/recommend`,
    { faculty_recommended: value },
  )
  return data
}

// ---------------------------------------------------------------------------
// Q&A
// ---------------------------------------------------------------------------

export async function askQuestion(
  packageId: string,
  question: string,
  sessionId?: string,
): Promise<RAGAnswerResponse> {
  const params: Record<string, string> = {}
  if (sessionId) params.session_id = sessionId
  const { data } = await api.post<RAGAnswerResponse>(
    `${BASE}/${packageId}/ask`,
    { question },
    { params },
  )
  return data
}

export async function listQASessions(packageId: string): Promise<QASession[]> {
  const { data } = await api.get<QASession[]>(`${BASE}/${packageId}/qa/sessions`)
  return data
}

export async function getQASession(
  packageId: string,
  sessionId: string,
): Promise<QASessionWithMessages> {
  const { data } = await api.get<QASessionWithMessages>(
    `${BASE}/${packageId}/qa/sessions/${sessionId}`,
  )
  return data
}
