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
  InternalMarks,
  InternalMarksListResponse,
  JobStatus,
  ManualQuestionPayload,
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
  workflow?: string
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

export async function deleteExamPaper(paperId: string): Promise<void> {
  await api.delete(`${BASE}/${paperId}`)
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

export async function listQuestionsWithAnswers(
  paperId:  string,
  setLabel?: string,
): Promise<ExamQuestion[]> {
  const { data } = await api.get(`${BASE}/${paperId}/questions/with-answers`, {
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

// ---- P1.16: Manual builder ----

export async function addQuestion(
  paperId: string,
  payload: ManualQuestionPayload,
): Promise<ExamQuestion> {
  const { data } = await api.post(`${BASE}/${paperId}/questions`, payload)
  return data
}

export async function reorderQuestions(
  paperId:   string,
  orderedIds: string[],
): Promise<ExamQuestion[]> {
  const { data } = await api.put(`${BASE}/${paperId}/questions/reorder`, { ordered_ids: orderedIds })
  return data
}

export async function duplicateQuestion(
  paperId:    string,
  questionId: string,
): Promise<ExamQuestion> {
  const { data } = await api.post(`${BASE}/${paperId}/questions/${questionId}/duplicate`)
  return data
}

// ---- P1.16: Dean review (INTERNAL papers) ----

export async function listDeanPending(params?: {
  offset?: number
  limit?: number
}): Promise<ExamPaperListResponse> {
  const { data } = await api.get(`${BASE}/dean/pending`, { params })
  return data
}

export async function deanDecision(
  paperId: string,
  payload: BoardDecisionPayload,
): Promise<ExamPaper> {
  const { data } = await api.post(`${BASE}/${paperId}/dean-decision`, payload)
  return data
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

export async function releasePaper(paperId: string): Promise<ExamPaper> {
  const { data } = await api.post(`${BASE}/${paperId}/release`)
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

export async function exportPdf(paperId: string, setLabel = 'A'): Promise<void> {
  const response = await api.get(`${BASE}/${paperId}/export/pdf`, {
    params: { set_label: setLabel },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `exam_${paperId}_set${setLabel}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ---- H-35: Regenerate single question ----

export async function regenerateQuestion(
  paperId:     string,
  questionId:  string,
  instruction?: string,
): Promise<{ paper_id: string; question_id: string; job_id: string; status: string }> {
  const { data } = await api.post(
    `${BASE}/${paperId}/questions/${questionId}/regenerate`,
    instruction ? { instruction } : {},
  )
  return data
}

// ---- Job polling ----

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get(`${BASE}/jobs/${jobId}`)
  return data
}

// ---- H-35: Internal marks management ----

export async function listInternalMarksByCourse(
  courseId: string,
  params?: {
    semester?:      number
    academic_year?: string
    offset?:        number
    limit?:         number
  },
): Promise<InternalMarksListResponse> {
  const { data } = await api.get(`${BASE}/internal-marks/course/${courseId}`, { params })
  return data
}

export async function submitInternalMarks(imsId: string): Promise<InternalMarks> {
  const { data } = await api.post(`${BASE}/internal-marks/${imsId}/submit`)
  return data
}

export async function lockInternalMarks(imsId: string): Promise<InternalMarks> {
  const { data } = await api.post(`${BASE}/internal-marks/${imsId}/lock`)
  return data
}
