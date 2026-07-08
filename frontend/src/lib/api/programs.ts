import api from '@/lib/api'
import type {
  ApproveRequest,
  Course,
  CourseCreate,
  CoursePrerequisite,
  CourseUpdate,
  ComplianceResult,
  ElectiveBasket,
  ElectiveBasketCreate,
  ElectiveBasketUpdate,
  ExportProgramRequest,
  GenerateProgramRequest,
  JobStatusResponse,
  Program,
  ProgramAIJobResponse,
  ProgramCreate,
  ProgramDetail,
  ProgramExportJobResponse,
  ProgramListFilters,
  ProgramListResponse,
  ProgramOutcome,
  ProgramOutcomeCreate,
  ProgramOutcomeUpdate,
  ProgramStatusResponse,
  ProgramUpdate,
  ProgramVersionResponse,
  PublishRequest,
  RejectRequest,
} from '@/types/program'

const BASE = '/programs'

// ---------------------------------------------------------------------------
// Program CRUD
// ---------------------------------------------------------------------------

export async function createProgram(payload: ProgramCreate): Promise<Program> {
  const { data } = await api.post<Program>(BASE, payload)
  return data
}

export async function listPrograms(filters?: ProgramListFilters): Promise<ProgramListResponse> {
  const { data } = await api.get<ProgramListResponse>(BASE, { params: filters })
  return data
}

export async function getProgram(id: string): Promise<ProgramDetail> {
  const { data } = await api.get<ProgramDetail>(`${BASE}/${id}`)
  return data
}

export async function getProgramStatus(id: string): Promise<ProgramStatusResponse> {
  const { data } = await api.get<ProgramStatusResponse>(`${BASE}/${id}/status`)
  return data
}

export async function updateProgram(id: string, payload: ProgramUpdate): Promise<Program> {
  const { data } = await api.patch<Program>(`${BASE}/${id}`, payload)
  return data
}

export async function deleteProgram(id: string): Promise<void> {
  await api.delete(`${BASE}/${id}`)
}

export async function getProgramVersions(id: string): Promise<ProgramVersionResponse[]> {
  const { data } = await api.get<ProgramVersionResponse[]>(`${BASE}/${id}/versions`)
  return data
}

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

export async function generateProgram(
  id: string,
  payload: GenerateProgramRequest,
): Promise<ProgramAIJobResponse> {
  const { data } = await api.post<ProgramAIJobResponse>(`${BASE}/${id}/generate`, payload)
  return data
}

export async function getJobStatus(
  programId: string,
  jobId: string,
): Promise<JobStatusResponse> {
  const { data } = await api.get<JobStatusResponse>(`${BASE}/${programId}/jobs/${jobId}`)
  return data
}

export async function approveProgram(id: string, payload: ApproveRequest): Promise<Program> {
  const { data } = await api.post<Program>(`${BASE}/${id}/approve`, payload)
  return data
}

export async function rejectProgram(
  id: string,
  payload: RejectRequest,
): Promise<ProgramStatusResponse> {
  const { data } = await api.post<ProgramStatusResponse>(`${BASE}/${id}/reject`, payload)
  return data
}

export async function publishProgram(id: string, payload: PublishRequest): Promise<Program> {
  const { data } = await api.post<Program>(`${BASE}/${id}/publish`, payload)
  return data
}

export async function forkProgram(id: string): Promise<Program> {
  const { data } = await api.post<Program>(`${BASE}/${id}/fork`)
  return data
}

export async function exportProgram(
  id: string,
  payload: ExportProgramRequest,
): Promise<ProgramExportJobResponse> {
  const { data } = await api.post<ProgramExportJobResponse>(`${BASE}/${id}/export`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

export async function getCompliance(id: string): Promise<ComplianceResult> {
  const { data } = await api.get<ComplianceResult>(`${BASE}/${id}/compliance`)
  return data
}

// ---------------------------------------------------------------------------
// Outcomes
// ---------------------------------------------------------------------------

export async function addOutcome(
  programId: string,
  payload: ProgramOutcomeCreate,
): Promise<ProgramOutcome> {
  const { data } = await api.post<ProgramOutcome>(`${BASE}/${programId}/outcomes`, payload)
  return data
}

export async function listOutcomes(programId: string): Promise<ProgramOutcome[]> {
  const { data } = await api.get<ProgramOutcome[]>(`${BASE}/${programId}/outcomes`)
  return data
}

export async function updateOutcome(
  programId: string,
  outcomeId: string,
  payload: ProgramOutcomeUpdate,
): Promise<ProgramOutcome> {
  const { data } = await api.patch<ProgramOutcome>(
    `${BASE}/${programId}/outcomes/${outcomeId}`,
    payload,
  )
  return data
}

export async function deleteOutcome(programId: string, outcomeId: string): Promise<void> {
  await api.delete(`${BASE}/${programId}/outcomes/${outcomeId}`)
}

// ---------------------------------------------------------------------------
// Courses
// ---------------------------------------------------------------------------

export async function addCourse(programId: string, payload: CourseCreate): Promise<Course> {
  const { data } = await api.post<Course>(`${BASE}/${programId}/courses`, payload)
  return data
}

export async function listCourses(programId: string): Promise<Course[]> {
  const { data } = await api.get<Course[]>(`${BASE}/${programId}/courses`)
  return data
}

export async function updateCourse(
  programId: string,
  courseId: string,
  payload: CourseUpdate,
): Promise<Course> {
  const { data } = await api.patch<Course>(
    `${BASE}/${programId}/courses/${courseId}`,
    payload,
  )
  return data
}

export async function deleteCourse(programId: string, courseId: string): Promise<void> {
  await api.delete(`${BASE}/${programId}/courses/${courseId}`)
}

export async function getCoursePrerequisites(
  programId: string,
  courseId: string,
): Promise<CoursePrerequisite[]> {
  const { data } = await api.get<CoursePrerequisite[]>(
    `${BASE}/${programId}/courses/${courseId}/prerequisites`,
  )
  return data
}

export async function removeCourseFromBasket(programId: string, courseId: string): Promise<Course> {
  const { data } = await api.delete<Course>(`${BASE}/${programId}/courses/${courseId}/basket`)
  return data
}

// ---------------------------------------------------------------------------
// Elective Baskets — a named group of elective courses within one program+
// semester. Electives are never a single standalone course.
// ---------------------------------------------------------------------------

export async function listBaskets(programId: string): Promise<ElectiveBasket[]> {
  const { data } = await api.get<ElectiveBasket[]>(`${BASE}/${programId}/electives/baskets`)
  return data
}

export async function createBasket(programId: string, payload: ElectiveBasketCreate): Promise<ElectiveBasket> {
  const { data } = await api.post<ElectiveBasket>(`${BASE}/${programId}/electives/baskets`, payload)
  return data
}

export async function updateBasket(
  programId: string, basketId: string, payload: ElectiveBasketUpdate,
): Promise<ElectiveBasket> {
  const { data } = await api.patch<ElectiveBasket>(`${BASE}/${programId}/electives/baskets/${basketId}`, payload)
  return data
}

export async function deleteBasket(programId: string, basketId: string): Promise<void> {
  await api.delete(`${BASE}/${programId}/electives/baskets/${basketId}`)
}
