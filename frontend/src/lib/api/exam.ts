// M08 Exam Setter — API client
import api from '@/lib/api'
import type {
  BloomsComplianceReport,
  BoardDecisionPayload,
  ExamPaper,
  ExamPaperCreatePayload,
  ExamPaperListResponse,
  ExamQuestion,
  ExamQuestionUpdatePayload,
  JobStatus,
  SealPayload,
} from '@/types/exam'

const BASE = '/exams'

// ---- Paper CRUD ----

export async function createExamPaper(
  payload: ExamPaperCreatePayload,
): Promise<{ paper_id: string; job_id: string; status: string }> {
  const { data } = await api.post(BASE, payload)
  return data
}

export async function listExamPapers(params?: {
  status?: string
  offset?: number
  limit?: number
}): Promise<ExamPaperListResponse> {
  const { data } = await api.get(BASE, { params })
  return data
}

export async function listAllExamPapers(params?: {
  status?: string
  offset?: number
  limit?: number
}): Promise<ExamPaperListResponse> {
  const { data } = await api.get(`${BASE}/all`, { params })
  return data
}

export async function getExamPaper(paperId: string): Promise<ExamPaper> {
  const { data } = await api.get(`${BASE}/${paperId}`)
  return data
}

// ---- Questions ----

export async function listQuestions(
  paperId: string,
  setLabel?: string,
): Promise<ExamQuestion[]> {
  const { data } = await api.get(`${BASE}/${paperId}/questions`, {
    params: setLabel ? { set_label: setLabel } : undefined,
  })
  return data
}

export async function editQuestion(
  paperId:    string,
  questionId: string,
  payload:    ExamQuestionUpdatePayload,
): Promise<ExamQuestion> {
  const { data } = await api.patch(`${BASE}/${paperId}/questions/${questionId}`, payload)
  return data
}

export async function deleteQuestion(paperId: string, questionId: string): Promise<void> {
  await api.delete(`${BASE}/${paperId}/questions/${questionId}`)
}

// ---- Bloom's report ----

export async function getBloomsReport(paperId: string): Promise<BloomsComplianceReport> {
  const { data } = await api.get(`${BASE}/${paperId}/blooms`)
  return data
}

// ---- Board ----

export async function listBoardPending(params?: {
  offset?: number
  limit?: number
}): Promise<ExamPaperListResponse> {
  const { data } = await api.get(`${BASE}/board/pending`, { params })
  return data
}

export async function boardDecision(
  paperId: string,
  payload: BoardDecisionPayload,
): Promise<ExamPaper> {
  const { data } = await api.post(`${BASE}/${paperId}/board-decision`, payload)
  return data
}

// ---- Workflow actions ----

export async function submitForReview(paperId: string): Promise<ExamPaper> {
  const { data } = await api.post(`${BASE}/${paperId}/submit`)
  return data
}

export async function sealPaper(paperId: string, payload: SealPayload): Promise<ExamPaper> {
  const { data } = await api.post(`${BASE}/${paperId}/seal`, payload)
  return data
}

// ---- Export ----

export async function exportQuestions(paperId: string, setLabel = 'A') {
  const { data } = await api.get(`${BASE}/${paperId}/export/questions`, {
    params: { set_label: setLabel },
  })
  return data
}

export async function exportAnswers(paperId: string, setLabel = 'A') {
  const { data } = await api.get(`${BASE}/${paperId}/export/answers`, {
    params: { set_label: setLabel },
  })
  return data
}

// ---- Job polling ----

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get(`${BASE}/jobs/${jobId}`)
  return data
}
