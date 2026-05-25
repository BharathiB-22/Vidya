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

// ── Evaluator — scoped routes ─────────────────────────────────────────────────

export async function evaluatorListAssignments(params?: {
  offset?: number
  limit?: number
}): Promise<LabAssignmentListResponse> {
  const { data } = await api.get<LabAssignmentListResponse>(
    `${BASE}/evaluator/assignments`, { params }
  )
  return data
}

export async function evaluatorGetAssignment(id: string): Promise<LabAssignment> {
  const { data } = await api.get<LabAssignment>(`${BASE}/evaluator/assignments/${id}`)
  return data
}

export async function evaluatorListSubmissions(
  assignmentId: string,
  params?: { offset?: number; limit?: number }
): Promise<SubmissionListResponse> {
  const { data } = await api.get<SubmissionListResponse>(
    `${BASE}/evaluator/assignments/${assignmentId}/submissions`,
    { params }
  )
  return data
}

export async function evaluatorGetReviewPanel(submissionId: string): Promise<ReviewPanel> {
  const { data } = await api.get<ReviewPanel>(
    `${BASE}/evaluator/submissions/${submissionId}/review`
  )
  return data
}

export async function evaluatorSubmitRecommendation(
  submissionId: string,
  payload: ScoresUpdateRequest & { recommendation_note?: string }
): Promise<LabEvaluation> {
  const { data } = await api.patch<LabEvaluation>(
    `${BASE}/evaluator/submissions/${submissionId}/recommend`,
    payload
  )
  return data
}

export interface EvaluatorAnalytics {
  total_assigned: number
  total_submissions: number
  pending_review: number
  recommended: number
  ratified: number
}

export async function evaluatorGetAnalytics(): Promise<EvaluatorAnalytics> {
  const { data } = await api.get<EvaluatorAnalytics>(`${BASE}/evaluator/analytics`)
  return data
}

// ── Faculty — tenant evaluator lookup (role-filtered, safe) ─────────────────

export interface TenantEvaluatorUser {
  id: string
  email: string
  full_name: string
}

export async function listTenantEvaluators(): Promise<TenantEvaluatorUser[]> {
  const { data } = await api.get<TenantEvaluatorUser[]>(`${BASE}/evaluators`)
  return data
}

// ── Faculty — evaluator management ──────────────────────────────────────────

export interface EvaluatorAssignmentRecord {
  id: string
  assignment_id: string
  evaluator_user_id: string
  assigned_by_user_id: string
  assigned_at: string
  is_active: boolean
}

export async function assignEvaluator(
  assignmentId: string,
  evaluatorUserId: string
): Promise<EvaluatorAssignmentRecord> {
  const { data } = await api.post<EvaluatorAssignmentRecord>(
    `${BASE}/assignments/${assignmentId}/evaluators`,
    { evaluator_user_id: evaluatorUserId }
  )
  return data
}

export async function listAssignmentEvaluators(
  assignmentId: string
): Promise<{ items: EvaluatorAssignmentRecord[]; total: number }> {
  const { data } = await api.get<{ items: EvaluatorAssignmentRecord[]; total: number }>(
    `${BASE}/assignments/${assignmentId}/evaluators`
  )
  return data
}

export async function removeEvaluator(
  assignmentId: string,
  evaluatorUserId: string
): Promise<void> {
  await api.delete(`${BASE}/assignments/${assignmentId}/evaluators/${evaluatorUserId}`)
}
