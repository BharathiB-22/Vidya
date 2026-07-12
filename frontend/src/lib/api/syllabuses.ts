import api from '@/lib/api'
import type {
  ApproveRequest,
  COPOMappingBulkUpdate,
  COPOMapping,
  COPOMatrixResponse,
  ComplianceCheckResponse,
  CourseOutcome,
  CourseOutcomeCreate,
  CourseOutcomeUpdate,
  DeanDocumentEditRequest,
  ExportSyllabusRequest,
  ForkRequest,
  GenerateSyllabusRequest,
  JobStatusResponse,
  ReferenceCandidate,
  ReferenceSearchRequest,
  Syllabus,
  RegenerateSectionRequest,
  SyllabusAIJobResponse,
  SyllabusCreate,
  SyllabusDetail,
  SyllabusExportJobResponse,
  SyllabusListFilters,
  SyllabusListResponse,
  SyllabusReference,
  SyllabusReferenceCreate,
  SyllabusReferenceUpdate,
  SyllabusStatusResponse,
  SyllabusUnit,
  SyllabusUnitCreate,
  SyllabusUnitReorder,
  SyllabusUnitUpdate,
  SyllabusUpdate,
  SyllabusVersionResponse,
} from '@/types/syllabus'

const BASE = '/syllabi'

// ---------------------------------------------------------------------------
// Syllabus CRUD
// ---------------------------------------------------------------------------

export async function createSyllabus(payload: SyllabusCreate): Promise<Syllabus> {
  const { data } = await api.post<Syllabus>(BASE, payload)
  return data
}

export async function listSyllabuses(filters: SyllabusListFilters): Promise<SyllabusListResponse> {
  const { data } = await api.get<SyllabusListResponse>(BASE, { params: filters })
  return data
}

export async function getSyllabus(id: string): Promise<SyllabusDetail> {
  const { data } = await api.get<SyllabusDetail>(`${BASE}/${id}`)
  return data
}

export async function getSyllabusStatus(id: string): Promise<SyllabusStatusResponse> {
  const { data } = await api.get<SyllabusStatusResponse>(`${BASE}/${id}/status`)
  return data
}

export async function updateSyllabus(id: string, payload: SyllabusUpdate): Promise<Syllabus> {
  const { data } = await api.patch<Syllabus>(`${BASE}/${id}`, payload)
  return data
}

export async function deleteSyllabus(id: string): Promise<void> {
  await api.delete(`${BASE}/${id}`)
}

export async function getSyllabusVersions(id: string): Promise<SyllabusVersionResponse[]> {
  const { data } = await api.get<SyllabusVersionResponse[]>(`${BASE}/${id}/versions`)
  return data
}

// ---------------------------------------------------------------------------
// AI generation
// ---------------------------------------------------------------------------

export async function generateSyllabus(
  id: string,
  payload: GenerateSyllabusRequest,
): Promise<SyllabusAIJobResponse> {
  const { data } = await api.post<SyllabusAIJobResponse>(`${BASE}/${id}/generate`, payload)
  return data
}

export async function getJobStatus(
  syllabusId: string,
  jobId: string,
): Promise<JobStatusResponse> {
  const { data } = await api.get<JobStatusResponse>(`${BASE}/${syllabusId}/jobs/${jobId}`)
  return data
}

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

// submitSyllabusForReview / rejectSyllabus / requestRevision / resubmitSyllabus /
// lockSyllabus / unlockSyllabus are gone. The Board writes the official syllabus
// and signs it off, so there is no handoff between two parties to model; and a
// syllabus is locked by CURRICULUM approval, never on its own, and never unlocked.

/**
 * Rewrite ONE section of the document — a unit, the objectives, the outcomes, the
 * text books, the practical components, or (for a lab manual, an internship, a
 * project or a seminar) the whole type-specific body. Runs in the background; the
 * rest of the document stays readable and editable while it does.
 *
 * Which sections are available depends on the course type: see
 * `regenerableSections()` in types/syllabus. Asking for a section the document does
 * not have is refused with 422.
 */
export async function regenerateSection(
  id: string,
  payload: RegenerateSectionRequest,
): Promise<SyllabusAIJobResponse> {
  const { data } = await api.post<SyllabusAIJobResponse>(`${BASE}/${id}/regenerate`, payload)
  return data
}

/**
 * The Dean adapting an APPROVED Internship / Mini Project / Major Project /
 * Seminar document.
 *
 * Permitted because those documents depend on the company, the supervisor and
 * institutional policy — things the Board cannot settle at approval time. A THEORY
 * syllabus is refused with 403: the Board owns the taught curriculum, and the Dean
 * publishes it without rewriting it.
 *
 * Unlike every other edit, this does NOT withdraw the Board's approval. The row is
 * stamped instead (`dean_edited_at`), so the governance trail can always say which
 * parts of the approved document the Board wrote and which the Dean did.
 */
export async function deanEditDocument(
  id: string,
  payload: DeanDocumentEditRequest,
): Promise<Syllabus> {
  const { data } = await api.patch<Syllabus>(`${BASE}/${id}/document/dean`, payload)
  return data
}

export async function approveSyllabus(
  id: string,
  payload: ApproveRequest,
): Promise<SyllabusStatusResponse> {
  const { data } = await api.post<SyllabusStatusResponse>(`${BASE}/${id}/approve`, payload)
  return data
}

export async function forkSyllabus(
  id: string,
  payload: ForkRequest,
): Promise<SyllabusStatusResponse> {
  const { data } = await api.post<SyllabusStatusResponse>(`${BASE}/${id}/fork`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export async function exportSyllabus(
  id: string,
  payload: ExportSyllabusRequest,
): Promise<SyllabusExportJobResponse> {
  const { data } = await api.post<SyllabusExportJobResponse>(`${BASE}/${id}/export`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

export async function getSyllabusCompliance(id: string): Promise<ComplianceCheckResponse> {
  const { data } = await api.get<ComplianceCheckResponse>(`${BASE}/${id}/compliance`)
  return data
}

// ---------------------------------------------------------------------------
// Course outcomes (COs)
// ---------------------------------------------------------------------------

export async function listOutcomes(syllabusId: string): Promise<CourseOutcome[]> {
  const { data } = await api.get<CourseOutcome[]>(`${BASE}/${syllabusId}/outcomes`)
  return data
}

export async function addOutcome(
  syllabusId: string,
  payload: CourseOutcomeCreate,
): Promise<CourseOutcome> {
  const { data } = await api.post<CourseOutcome>(`${BASE}/${syllabusId}/outcomes`, payload)
  return data
}

export async function updateOutcome(
  syllabusId: string,
  coId: string,
  payload: CourseOutcomeUpdate,
): Promise<CourseOutcome> {
  const { data } = await api.patch<CourseOutcome>(
    `${BASE}/${syllabusId}/outcomes/${coId}`,
    payload,
  )
  return data
}

export async function deleteOutcome(syllabusId: string, coId: string): Promise<void> {
  await api.delete(`${BASE}/${syllabusId}/outcomes/${coId}`)
}

// ---------------------------------------------------------------------------
// CO-PO mappings
// ---------------------------------------------------------------------------

export async function updateCOPOMappings(
  syllabusId: string,
  coId: string,
  payload: COPOMappingBulkUpdate,
): Promise<COPOMapping[]> {
  const { data } = await api.put<COPOMapping[]>(
    `${BASE}/${syllabusId}/outcomes/${coId}/mappings`,
    payload,
  )
  return data
}

export async function getCOPOMatrix(syllabusId: string): Promise<COPOMatrixResponse> {
  const { data } = await api.get<COPOMatrixResponse>(`${BASE}/${syllabusId}/copo-matrix`)
  return data
}

// ---------------------------------------------------------------------------
// Syllabus units
// ---------------------------------------------------------------------------

export async function listUnits(syllabusId: string): Promise<SyllabusUnit[]> {
  const { data } = await api.get<SyllabusUnit[]>(`${BASE}/${syllabusId}/units`)
  return data
}

export async function addUnit(
  syllabusId: string,
  payload: SyllabusUnitCreate,
): Promise<SyllabusUnit> {
  const { data } = await api.post<SyllabusUnit>(`${BASE}/${syllabusId}/units`, payload)
  return data
}

export async function updateUnit(
  syllabusId: string,
  unitId: string,
  payload: SyllabusUnitUpdate,
): Promise<SyllabusUnit> {
  const { data } = await api.patch<SyllabusUnit>(
    `${BASE}/${syllabusId}/units/${unitId}`,
    payload,
  )
  return data
}

export async function deleteUnit(syllabusId: string, unitId: string): Promise<void> {
  await api.delete(`${BASE}/${syllabusId}/units/${unitId}`)
}

export async function reorderUnits(
  syllabusId: string,
  payload: SyllabusUnitReorder,
): Promise<number> {
  const { data } = await api.put<number>(`${BASE}/${syllabusId}/units/reorder`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Syllabus references
// ---------------------------------------------------------------------------

export async function searchReferences(
  syllabusId: string,
  request: ReferenceSearchRequest,
): Promise<ReferenceCandidate[]> {
  const { data } = await api.get<ReferenceCandidate[]>(
    `${BASE}/${syllabusId}/references/search`,
    { params: { q: request.query, ref_type: request.ref_type, limit: request.limit } },
  )
  return data
}

export async function listReferences(syllabusId: string): Promise<SyllabusReference[]> {
  const { data } = await api.get<SyllabusReference[]>(`${BASE}/${syllabusId}/references`)
  return data
}

export async function addReference(
  syllabusId: string,
  payload: SyllabusReferenceCreate,
): Promise<SyllabusReference> {
  const { data } = await api.post<SyllabusReference>(
    `${BASE}/${syllabusId}/references`,
    payload,
  )
  return data
}

export async function updateReference(
  syllabusId: string,
  refId: string,
  payload: SyllabusReferenceUpdate,
): Promise<SyllabusReference> {
  const { data } = await api.patch<SyllabusReference>(
    `${BASE}/${syllabusId}/references/${refId}`,
    payload,
  )
  return data
}

export async function deleteReference(syllabusId: string, refId: string): Promise<void> {
  await api.delete(`${BASE}/${syllabusId}/references/${refId}`)
}

export async function confirmReference(
  syllabusId: string,
  refId: string,
): Promise<SyllabusReference> {
  const { data } = await api.post<SyllabusReference>(
    `${BASE}/${syllabusId}/references/${refId}/confirm`,
    {},
  )
  return data
}
