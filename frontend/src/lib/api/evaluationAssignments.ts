// M09.6 Assignment Engine — API client.
import api from '@/lib/api'
import type {
  AssignmentCreatePayload,
  AssignmentListResponse,
  AutoAssignPayload,
  AutoAssignPreview,
  AutoAssignResult,
  BulkAssignmentPayload,
  CancelPayload,
  EvaluationAssignment,
  ReassignPayload,
  WorkloadBoard,
  WorkloadSummary,
} from '@/types/evaluationAssignment'

const BASE = '/evaluation-assignments'

export interface ListParams {
  evaluator_id?: string
  assignment_type?: string
  status?: string
  exam_paper_id?: string
  offset?: number
  limit?: number
}

// ---- Faculty / evaluator (own work) ----
export async function myAssignments(params?: {
  status?: string; assignment_type?: string; offset?: number; limit?: number
}): Promise<AssignmentListResponse> {
  const { data } = await api.get(`${BASE}/me`, { params })
  return data
}

export async function myWorkload(): Promise<WorkloadSummary> {
  const { data } = await api.get(`${BASE}/me/workload`)
  return data
}

// ---- Monitoring (admin / dean / board) ----
export async function listAssignments(params?: ListParams): Promise<AssignmentListResponse> {
  const { data } = await api.get(BASE, { params })
  return data
}

export async function workloadBoard(evaluatorIds: string[]): Promise<WorkloadBoard> {
  const { data } = await api.get(`${BASE}/workload`, {
    params: { evaluator_ids: evaluatorIds },
    paramsSerializer: { indexes: null }, // evaluator_ids=a&evaluator_ids=b
  })
  return data
}

export async function getAssignment(id: string): Promise<EvaluationAssignment> {
  const { data } = await api.get(`${BASE}/${id}`)
  return data
}

// ---- Admin allocation ----
export async function createAssignment(p: AssignmentCreatePayload): Promise<EvaluationAssignment> {
  const { data } = await api.post(BASE, p)
  return data
}

export async function bulkAssign(p: BulkAssignmentPayload): Promise<AssignmentListResponse> {
  const { data } = await api.post(`${BASE}/bulk`, p)
  return data
}

export async function autoAssign(p: AutoAssignPayload): Promise<AutoAssignPreview | AutoAssignResult> {
  const { data } = await api.post(`${BASE}/auto`, p)
  return data
}

// ---- Lifecycle ----
export async function startAssignment(id: string): Promise<EvaluationAssignment> {
  const { data } = await api.post(`${BASE}/${id}/start`)
  return data
}

export async function submitAssignment(id: string): Promise<EvaluationAssignment> {
  const { data } = await api.post(`${BASE}/${id}/submit`)
  return data
}

export async function completeAssignment(id: string): Promise<EvaluationAssignment> {
  const { data } = await api.post(`${BASE}/${id}/complete`)
  return data
}

export async function reassignAssignment(id: string, p: ReassignPayload): Promise<EvaluationAssignment> {
  const { data } = await api.post(`${BASE}/${id}/reassign`, p)
  return data
}

export async function cancelAssignment(id: string, p: CancelPayload): Promise<EvaluationAssignment> {
  const { data } = await api.post(`${BASE}/${id}/cancel`, p)
  return data
}
