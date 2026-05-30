// M09 Paper Administration & Scanning — API client
import api from '@/lib/api'
import type {
  AcceptSuggestionsPayload,
  BoardFinaliseResponse,
  BulkMarkUpdatePayload,
  EvaluatorReviewResponse,
  ExamScoreLedger,
  ExamScoreLedgerListResponse,
  JobStatus,
  PaperPipelineStats,
  ScannedScript,
  ScannedScriptListResponse,
  ScriptAssignEvaluatorPayload,
  ScriptEvaluation,
  ScriptFileUrlResponse,
  ScriptFinalisePayload,
  ScriptIngestPayload,
  ScriptIngestResponse,
  ScriptSubmitMarksPayload,
} from '@/types/script'

const BASE = '/scripts'

// ---------------------------------------------------------------------------
// Ingest
// ---------------------------------------------------------------------------

/** Register a scanned script and queue the AI scoring task (202 Accepted). */
export async function uploadScript(
  payload:    ScriptIngestPayload,
  uploadUrl?: string,
  pageCount?: number,
): Promise<ScriptIngestResponse> {
  const params: Record<string, string | number> = {}
  if (uploadUrl !== undefined) params.upload_url = uploadUrl
  if (pageCount !== undefined) params.page_count = pageCount
  const { data } = await api.post(`${BASE}/upload`, payload, {
    params: Object.keys(params).length ? params : undefined,
  })
  return data
}

// ---------------------------------------------------------------------------
// Assign evaluator
// ---------------------------------------------------------------------------

export async function assignEvaluator(
  scriptId: string,
  payload:  ScriptAssignEvaluatorPayload,
): Promise<ScannedScript> {
  const { data } = await api.post(`${BASE}/${scriptId}/assign`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Marks — intermediate save (no gate)
// ---------------------------------------------------------------------------

export async function updateMarks(
  scriptId: string,
  payload:  BulkMarkUpdatePayload,
): Promise<ScriptEvaluation[]> {
  const { data } = await api.patch(`${BASE}/${scriptId}/marks`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Gate 1 — submit all marks
// ---------------------------------------------------------------------------

export async function submitMarks(
  scriptId: string,
  payload:  ScriptSubmitMarksPayload,
): Promise<ScannedScript> {
  const { data } = await api.post(`${BASE}/${scriptId}/submit`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Gate 2 — Board finalise
// ---------------------------------------------------------------------------

export async function boardFinalise(
  scriptId: string,
  payload:  ScriptFinalisePayload,
): Promise<BoardFinaliseResponse> {
  const { data } = await api.post(`${BASE}/${scriptId}/finalise`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Read — scripts
// ---------------------------------------------------------------------------

export async function getScript(
  scriptId:        string,
  includeIdentity = false,
): Promise<ScannedScript> {
  const { data } = await api.get(`${BASE}/${scriptId}`, {
    params: includeIdentity ? { include_identity: true } : undefined,
  })
  return data
}

export async function listAllScripts(params?: {
  exam_paper_id?: string
  status?:        string
  offset?:        number
  limit?:         number
}): Promise<ScannedScriptListResponse> {
  const { data } = await api.get(BASE, { params })
  return data
}

export async function listBoardPending(params?: {
  offset?: number
  limit?:  number
}): Promise<ScannedScriptListResponse> {
  const { data } = await api.get(`${BASE}/board/pending`, { params })
  return data
}

/** Evaluator: list scripts assigned to the authenticated user. */
export async function listMyScripts(params?: {
  status?:  string
  offset?:  number
  limit?:   number
}): Promise<ScannedScriptListResponse> {
  const { data } = await api.get(`${BASE}/evaluator/me`, { params })
  return data
}

export async function listScriptsForPaper(
  paperId: string,
  params?: {
    status?: string
    offset?: number
    limit?:  number
  },
): Promise<ScannedScriptListResponse> {
  const { data } = await api.get(`${BASE}/paper/${paperId}`, { params })
  return data
}

// ---------------------------------------------------------------------------
// Read — evaluations
// ---------------------------------------------------------------------------

export async function getEvaluations(scriptId: string): Promise<ScriptEvaluation[]> {
  const { data } = await api.get(`${BASE}/${scriptId}/evaluations`)
  return data
}

/** H-36 STEP-06: combined review panel — OCR text + enriched AI evaluations. */
export async function getEvaluatorReview(scriptId: string): Promise<EvaluatorReviewResponse> {
  const { data } = await api.get(`${BASE}/${scriptId}/review`)
  return data
}

/** H-36 STEP-06: evaluator accepts AI suggestions for all or specific questions. */
export async function acceptSuggestions(
  scriptId: string,
  payload:  AcceptSuggestionsPayload,
): Promise<ScriptEvaluation[]> {
  const { data } = await api.post(`${BASE}/${scriptId}/accept`, payload)
  return data
}

// ---------------------------------------------------------------------------
// Read — score ledger
// ---------------------------------------------------------------------------

export async function getLedgerEntry(scriptId: string): Promise<ExamScoreLedger> {
  const { data } = await api.get(`${BASE}/${scriptId}/ledger`)
  return data
}

export async function listLedgerForPaper(
  paperId: string,
  params?: {
    offset?: number
    limit?:  number
  },
): Promise<ExamScoreLedgerListResponse> {
  const { data } = await api.get(`${BASE}/ledger/paper/${paperId}`, { params })
  return data
}

// ---------------------------------------------------------------------------
// Job polling
// ---------------------------------------------------------------------------

export async function getScoringJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get(`/exams/jobs/${jobId}`)
  return data
}

// ---------------------------------------------------------------------------
// Paper pipeline stats (H-36 STEP-10)
// ---------------------------------------------------------------------------

/** Board/Admin: aggregate pipeline-status counts for all scripts in an exam paper. */
export async function getPaperStats(paperId: string): Promise<PaperPipelineStats> {
  const { data } = await api.get(`${BASE}/stats`, { params: { paper_id: paperId } })
  return data
}

// ---------------------------------------------------------------------------
// Score ledger CSV export (H-36 STEP-11)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Quality-failed admin override (H-36 STEP-12)
// ---------------------------------------------------------------------------

/** Admin: override a QUALITY_FAILED script to proceed to OCR. */
export async function overrideQualityFailed(
  scriptId: string,
  reason:   string,
): Promise<ScannedScript> {
  const { data } = await api.post(`${BASE}/${scriptId}/override-quality`, { reason })
  return data
}

// ---------------------------------------------------------------------------
// Script file URL — presigned GET URL for uploaded scan (H-36 STEP-13)
// ---------------------------------------------------------------------------

/** Evaluator/Admin/Board: get a 5-minute presigned URL to view the uploaded script PDF. */
export async function getScriptFileUrl(scriptId: string): Promise<ScriptFileUrlResponse> {
  const { data } = await api.get(`${BASE}/${scriptId}/file-url`)
  return data
}

/** Board/Admin: fetch score ledger as CSV blob and trigger browser download. */
export async function downloadLedgerCSV(paperId: string): Promise<void> {
  const response = await api.get(`${BASE}/ledger/paper/${paperId}/export`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(new Blob([response.data as BlobPart], { type: 'text/csv' }))
  const a   = document.createElement('a')
  a.href     = url
  a.download = `score_ledger_${paperId.slice(0, 8)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
