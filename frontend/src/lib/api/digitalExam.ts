// M09.5 Digital Exams — API client
import api from '@/lib/api'
import type {
  DigitalAttemptDetailResponse,
  DigitalExamAttempt,
  DigitalExamSession,
  DigitalResultResponse,
  DigitalResponseIn,
  DigitalResponseOut,
  DigitalSessionAnalytics,
  DigitalSessionCreate,
  DigitalSessionListResponse,
} from '@/types/digitalExam'

const BASE = '/scripts/digital'

// ---------------------------------------------------------------------------
// Session management (Admin / Board)
// ---------------------------------------------------------------------------

export async function createSession(
  payload: DigitalSessionCreate,
): Promise<DigitalExamSession> {
  const { data } = await api.post(`${BASE}/sessions`, payload)
  return data
}

export async function activateSession(sessionId: string): Promise<DigitalExamSession> {
  const { data } = await api.patch(`${BASE}/sessions/${sessionId}/activate`)
  return data
}

export async function closeSession(sessionId: string): Promise<DigitalExamSession> {
  const { data } = await api.patch(`${BASE}/sessions/${sessionId}/close`)
  return data
}

export async function listSessions(params?: {
  exam_paper_id?: string
  offset?: number
  limit?: number
}): Promise<DigitalSessionListResponse> {
  const { data } = await api.get(`${BASE}/sessions`, { params })
  return data
}

export async function getSession(sessionId: string): Promise<DigitalExamSession> {
  const { data } = await api.get(`${BASE}/sessions/${sessionId}`)
  return data
}

// ---------------------------------------------------------------------------
// Student exam-taking
// ---------------------------------------------------------------------------

export async function startOrResumeAttempt(
  sessionId: string,
): Promise<DigitalExamAttempt> {
  const { data } = await api.post(`${BASE}/sessions/${sessionId}/attempt`)
  return data
}

export async function getAttemptQuestions(
  attemptId: string,
): Promise<DigitalAttemptDetailResponse> {
  const { data } = await api.get(`${BASE}/attempts/${attemptId}/questions`)
  return data
}

export async function saveResponse(
  attemptId:  string,
  questionId: string,
  payload:    DigitalResponseIn,
): Promise<DigitalResponseOut> {
  const { data } = await api.put(
    `${BASE}/attempts/${attemptId}/responses/${questionId}`,
    payload,
  )
  return data
}

export async function submitAttempt(
  attemptId: string,
): Promise<DigitalResultResponse> {
  const { data } = await api.post(`${BASE}/attempts/${attemptId}/submit`)
  return data
}

export async function getAttemptResult(
  attemptId: string,
): Promise<DigitalResultResponse> {
  const { data } = await api.get(`${BASE}/attempts/${attemptId}/result`)
  return data
}

export async function getSessionAnalytics(
  sessionId: string,
  passThresholdPct = 40,
): Promise<DigitalSessionAnalytics> {
  const { data } = await api.get(`${BASE}/sessions/${sessionId}/analytics`, {
    params: { pass_threshold_pct: passThresholdPct },
  })
  return data
}
