import api from '@/lib/api'
import type {
  AssignmentCreate,
  AssignmentUpdate,
  GradeLedgerEntry,
  JobStatus,
  LabAssignment,
  LabAssignmentListResponse,
  LabEvaluation,
  RatifyRequest,
  ReviewPanel,
  ScoresUpdateRequest,
  SubmissionListResponse,
  SubmitPayload,
} from '@/types/labs'

const BASE = '/labs'

// ── Faculty — Assignments ────────────────────────────────────────────────────

export async function createAssignment(payload: AssignmentCreate): Promise<LabAssignment> {
  const { data } = await api.post<LabAssignment>(`${BASE}/assignments`, payload)
  return data
}

export async function listAssignments(params?: {
  syllabus_id?: string
  status?: string
  offset?: number
  limit?: number
}): Promise<LabAssignmentListResponse> {
  const { data } = await api.get<LabAssignmentListResponse>(`${BASE}/assignments`, { params })
  return data
}

export async function getAssignment(id: string): Promise<LabAssignment> {
  const { data } = await api.get<LabAssignment>(`${BASE}/assignments/${id}`)
  return data
}

export async function updateAssignment(id: string, payload: AssignmentUpdate): Promise<LabAssignment> {
  const { data } = await api.put<LabAssignment>(`${BASE}/assignments/${id}`, payload)
  return data
}

export async function publishAssignment(id: string): Promise<LabAssignment> {
  const { data } = await api.post<LabAssignment>(`${BASE}/assignments/${id}/publish`)
  return data
}

export async function closeAssignment(id: string): Promise<LabAssignment> {
  const { data } = await api.post<LabAssignment>(`${BASE}/assignments/${id}/close`)
  return data
}

// ── Faculty — Submissions ────────────────────────────────────────────────────

export async function listSubmissions(
  assignmentId: string,
  params?: { offset?: number; limit?: number }
): Promise<SubmissionListResponse> {
  const { data } = await api.get<SubmissionListResponse>(
    `${BASE}/assignments/${assignmentId}/submissions`,
    { params }
  )
  return data
}

export async function getReviewPanel(submissionId: string): Promise<ReviewPanel> {
  const { data } = await api.get<ReviewPanel>(`${BASE}/submissions/${submissionId}/review`)
  return data
}

export async function updateScores(
  submissionId: string,
  payload: ScoresUpdateRequest
): Promise<LabEvaluation> {
  const { data } = await api.patch<LabEvaluation>(`${BASE}/submissions/${submissionId}/scores`, payload)
  return data
}

export async function ratifySubmission(
  submissionId: string,
  payload: RatifyRequest
): Promise<GradeLedgerEntry> {
  const { data } = await api.post<GradeLedgerEntry>(
    `${BASE}/submissions/${submissionId}/ratify`,
    payload
  )
  return data
}

export function getModerationReportUrl(assignmentId: string): string {
  return `${api.defaults.baseURL ?? ''}${BASE}/assignments/${assignmentId}/report`
}

// ── Job poll ─────────────────────────────────────────────────────────────────

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`${BASE}/jobs/${jobId}`)
  return data
}

// ── Student ──────────────────────────────────────────────────────────────────

export async function studentListAssignments(params?: {
  syllabus_id?: string
  offset?: number
  limit?: number
}): Promise<LabAssignmentListResponse> {
  const { data } = await api.get<LabAssignmentListResponse>(`${BASE}/student/assignments`, { params })
  return data
}

export async function studentGetAssignment(id: string): Promise<LabAssignment> {
  const { data } = await api.get<LabAssignment>(`${BASE}/student/assignments/${id}`)
  return data
}

export async function studentSubmit(assignmentId: string, payload: SubmitPayload) {
  const { data } = await api.post(`${BASE}/student/assignments/${assignmentId}/submit`, payload)
  return data
}

export async function studentMySubmissions(params?: {
  offset?: number
  limit?: number
}): Promise<SubmissionListResponse> {
  const { data } = await api.get<SubmissionListResponse>(`${BASE}/student/submissions/my`, { params })
  return data
}

export async function studentGetResult(submissionId: string) {
  const { data } = await api.get(`${BASE}/student/submissions/${submissionId}/result`)
  return data
}
