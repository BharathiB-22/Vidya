import api from '@/lib/api'
import type {
  DocumentListResponse,
  DocumentSubmit,
  GuideDecisionRequest,
  GuideDocumentReviewRequest,
  JobStatus,
  ProblemCreate,
  ProblemListResponse,
  ResearchDocument,
  ResearchProblem,
  VivaListResponse,
  VivaRatifyRequest,
  VivaRespondRequest,
  VivaScheduleRequest,
  VivaSession,
} from '@/types/research'

const BASE = '/research'

// ── Guide — Problems ──────────────────────────────────────────────────────────

export async function listProblems(params?: {
  status?: string
  offset?: number
  limit?: number
}): Promise<ProblemListResponse> {
  const { data } = await api.get<ProblemListResponse>(`${BASE}/problems`, { params })
  return data
}

export async function getProblem(id: string): Promise<ResearchProblem> {
  const { data } = await api.get<ResearchProblem>(`${BASE}/problems/${id}`)
  return data
}

export async function decideProblem(
  id: string,
  payload: GuideDecisionRequest
): Promise<ResearchProblem> {
  const { data } = await api.post<ResearchProblem>(`${BASE}/problems/${id}/decide`, payload)
  return data
}

export async function generateProblems(params: {
  research_area: string
  num_problems?: number
}): Promise<{ problems: Array<{ title: string; abstract: string; research_questions: string[] }> }> {
  const { data } = await api.get(`${BASE}/problems/generate`, { params })
  return data
}

export async function storeAiProblem(payload: {
  title: string
  abstract: string
  research_questions: string[]
}): Promise<ResearchProblem> {
  const { data } = await api.post<ResearchProblem>(`${BASE}/problems/ai-store`, payload)
  return data
}

// ── Guide — Documents ─────────────────────────────────────────────────────────

export async function listDocumentsForGuide(params?: {
  status?: string
  offset?: number
  limit?: number
}): Promise<DocumentListResponse> {
  const { data } = await api.get<DocumentListResponse>(`${BASE}/documents`, { params })
  return data
}

export async function getDocument(id: string): Promise<ResearchDocument> {
  const { data } = await api.get<ResearchDocument>(`${BASE}/documents/${id}`)
  return data
}

export async function reviewDocument(
  id: string,
  payload: GuideDocumentReviewRequest
): Promise<ResearchDocument> {
  const { data } = await api.post<ResearchDocument>(`${BASE}/documents/${id}/review`, payload)
  return data
}

// ── Guide — Viva ──────────────────────────────────────────────────────────────

export async function scheduleViva(payload: VivaScheduleRequest): Promise<VivaSession> {
  const { data } = await api.post<VivaSession>(`${BASE}/vivas`, payload)
  return data
}

export async function listVivasForGuide(params?: {
  status?: string
  offset?: number
  limit?: number
}): Promise<VivaListResponse> {
  const { data } = await api.get<VivaListResponse>(`${BASE}/vivas`, { params })
  return data
}

export async function getViva(id: string): Promise<VivaSession> {
  const { data } = await api.get<VivaSession>(`${BASE}/vivas/${id}`)
  return data
}

export async function ratifyViva(id: string, payload: VivaRatifyRequest): Promise<VivaSession> {
  const { data } = await api.post<VivaSession>(`${BASE}/vivas/${id}/ratify`, payload)
  return data
}

// ── Student — Problems ────────────────────────────────────────────────────────

export async function studentListProblems(params?: {
  offset?: number
  limit?: number
}): Promise<ProblemListResponse> {
  const { data } = await api.get<ProblemListResponse>(`${BASE}/student/problems`, { params })
  return data
}

export async function studentPropose(payload: ProblemCreate): Promise<ResearchProblem> {
  const { data } = await api.post<ResearchProblem>(`${BASE}/student/problems`, payload)
  return data
}

export async function studentGetProblem(id: string): Promise<ResearchProblem> {
  const { data } = await api.get<ResearchProblem>(`${BASE}/student/problems/${id}`)
  return data
}

// ── Student — Documents ───────────────────────────────────────────────────────

export async function studentSubmitDocument(payload: DocumentSubmit): Promise<ResearchDocument> {
  const { data } = await api.post<ResearchDocument>(`${BASE}/student/documents`, payload)
  return data
}

export async function studentGetDocument(id: string): Promise<ResearchDocument> {
  const { data } = await api.get<ResearchDocument>(`${BASE}/student/documents/${id}`)
  return data
}

// ── Student — Viva ────────────────────────────────────────────────────────────

export async function studentListVivas(params?: {
  offset?: number
  limit?: number
}): Promise<VivaListResponse> {
  const { data } = await api.get<VivaListResponse>(`${BASE}/student/vivas`, { params })
  return data
}

export async function studentGetViva(id: string): Promise<VivaSession> {
  const { data } = await api.get<VivaSession>(`${BASE}/student/vivas/${id}`)
  return data
}

export async function recordConsent(token: string): Promise<VivaSession> {
  const { data } = await api.post<VivaSession>(`${BASE}/student/vivas/${token}/consent`)
  return data
}

export async function submitResponse(
  token: string,
  payload: VivaRespondRequest
): Promise<VivaSession> {
  const { data } = await api.post<VivaSession>(`${BASE}/student/vivas/${token}/respond`, payload)
  return data
}

export async function completeViva(token: string): Promise<VivaSession> {
  const { data } = await api.post<VivaSession>(`${BASE}/student/vivas/${token}/complete`)
  return data
}

// ── Job poll ─────────────────────────────────────────────────────────────────

export async function getResearchJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`${BASE}/jobs/${jobId}`)
  return data
}
