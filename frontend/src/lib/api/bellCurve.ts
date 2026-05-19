// M10 Bell Curve Normaliser — API client
import api from '@/lib/api'
import type {
  BellCurveAnalysis,
  BellCurveAnalysisListResponse,
  BellCurveDecision,
  BellCurveDecisionListResponse,
  JobStatusResponse,
  NormalisedScoreListResponse,
  PreviewNormalisationRequest,
  PreviewNormalisationResponse,
  RatifyRequest,
  RatifyResponse,
  TriggerAnalysisRequest,
  TriggerAnalysisResponse,
} from '@/types/bellCurve'

const BASE = '/bell-curve'

// ---------------------------------------------------------------------------
// Analyses
// ---------------------------------------------------------------------------

export async function triggerAnalysis(
  payload: TriggerAnalysisRequest,
): Promise<TriggerAnalysisResponse> {
  const { data } = await api.post(`${BASE}/analyses`, payload)
  return data
}

export async function listAnalyses(params?: {
  offset?: number
  limit?:  number
}): Promise<BellCurveAnalysisListResponse> {
  const { data } = await api.get(`${BASE}/analyses`, { params })
  return data
}

export async function listAnalysesForPaper(
  paperId: string,
  params?: { offset?: number; limit?: number },
): Promise<BellCurveAnalysisListResponse> {
  const { data } = await api.get(`${BASE}/analyses/paper/${paperId}`, { params })
  return data
}

export async function getAnalysis(analysisId: string): Promise<BellCurveAnalysis> {
  const { data } = await api.get(`${BASE}/analyses/${analysisId}`)
  return data
}

export async function getAnalysisJobStatus(
  analysisId: string,
): Promise<JobStatusResponse> {
  const { data } = await api.get(`${BASE}/analyses/${analysisId}/job`)
  return data
}

export async function previewNormalisation(
  analysisId: string,
  payload:    PreviewNormalisationRequest,
): Promise<PreviewNormalisationResponse> {
  const { data } = await api.post(`${BASE}/analyses/${analysisId}/preview`, payload)
  return data
}

export async function ratifyAnalysis(
  analysisId: string,
  payload:    RatifyRequest,
): Promise<RatifyResponse> {
  const { data } = await api.post(`${BASE}/analyses/${analysisId}/ratify`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Decisions
// ---------------------------------------------------------------------------

export async function listDecisions(params?: {
  offset?: number
  limit?:  number
}): Promise<BellCurveDecisionListResponse> {
  const { data } = await api.get(`${BASE}/decisions`, { params })
  return data
}

export async function getDecision(decisionId: string): Promise<BellCurveDecision> {
  const { data } = await api.get(`${BASE}/decisions/${decisionId}`)
  return data
}

// ---------------------------------------------------------------------------
// Normalised score ledger
// ---------------------------------------------------------------------------

export async function listNormalisedLedger(
  paperId: string,
  params?: { offset?: number; limit?: number },
): Promise<NormalisedScoreListResponse> {
  const { data } = await api.get(`${BASE}/ledger/paper/${paperId}`, { params })
  return data
}

// ---------------------------------------------------------------------------
// Reports — returns a Blob for PDF download
// ---------------------------------------------------------------------------

export async function downloadFairnessReport(examPaperId?: string): Promise<Blob> {
  const params: Record<string, string> = {}
  if (examPaperId) params.exam_paper_id = examPaperId
  const { data } = await api.get(`${BASE}/reports/semester`, {
    params,
    responseType: 'blob',
  })
  return data
}
