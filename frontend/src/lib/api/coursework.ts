import api from '@/lib/api'
import type {
  AssignEvaluatorPayload,
  CourseworkAssignment,
  CourseworkAssignmentCreate,
  CourseworkAssignmentListResponse,
  CourseworkAssignmentUpdate,
  CourseworkGradePayload,
  CourseworkStatistics,
  CourseworkSubmission,
  CourseworkSubmissionListResponse,
  AiEvaluation,
  CourseworkSubmitPayload,
  EligibleEvaluator,
  EvaluationCenterResponse,
  MyCourseworkEvaluation,
  MyTeachingCourse,
} from '@/types/coursework'

const BASE = '/assignments'

// ── Faculty — Assignments ────────────────────────────────────────────────────

export async function createAssignment(payload: CourseworkAssignmentCreate): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(BASE, payload)
  return data
}

export async function listAssignments(params?: {
  syllabus_id?: string
  status?: string
}): Promise<CourseworkAssignmentListResponse> {
  const { data } = await api.get<CourseworkAssignmentListResponse>(BASE, { params })
  return data
}

export async function getAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.get<CourseworkAssignment>(`${BASE}/${id}`)
  return data
}

export async function updateAssignment(
  id: string,
  payload: CourseworkAssignmentUpdate
): Promise<CourseworkAssignment> {
  const { data } = await api.put<CourseworkAssignment>(`${BASE}/${id}`, payload)
  return data
}

export async function deleteAssignment(id: string): Promise<void> {
  // DRAFT-only; the backend returns 409 for a published assignment.
  await api.delete(`${BASE}/${id}`)
}

export async function publishAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/publish`)
  return data
}

export async function closeAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/close`)
  return data
}

export async function releaseAssignmentMarks(id: string): Promise<CourseworkAssignment> {
  // Dean/Admin: FINALIZED -> RELEASED; makes marks visible to students.
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/release`)
  return data
}

export async function archiveAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/archive`)
  return data
}

export async function restoreAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/restore`)
  return data
}

// ── Evaluation hand-off ─────────────────────────────────────────────────────
// Faculty submits → Dept/Admin assigns an Evaluator per submission → Evaluator
// evaluates → a human finalizes the marks.

/** Faculty hands a CLOSED assignment to the department for evaluation. */
export async function submitAssignmentForEvaluation(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.post<CourseworkAssignment>(`${BASE}/${id}/submit`)
  return data
}

/** Users holding the EVALUATOR responsibility (standalone role or FACULTY with
 *  an active EVALUATOR grant). */
export async function listEligibleEvaluators(): Promise<EligibleEvaluator[]> {
  const { data } = await api.get<EligibleEvaluator[]>(`${BASE}/evaluators`)
  return data
}

/** The coursework currently allocated to me. Reads the M09.6 ledger and resolves
 *  its target ids back to the coursework they point at. */
export async function listMyTeachingCourses(): Promise<MyTeachingCourse[]> {
  // The faculty's OWN courses (not institution-wide), each with the latest
  // approved syllabus resolved — used to auto-bind syllabus_id on create.
  const { data } = await api.get<MyTeachingCourse[]>(`${BASE}/my-teaching-courses`)
  return data
}

export async function listMyCourseworkEvaluations(): Promise<MyCourseworkEvaluation[]> {
  const { data } = await api.get<MyCourseworkEvaluation[]>(`${BASE}/evaluator/my-work`)
  return data
}

/** One assignment's Evaluation Center: full class roster + live progress. The
 *  evaluator sees this from publish, before any student submits. */
export async function getEvaluationCenter(assignmentId: string): Promise<EvaluationCenterResponse> {
  const { data } = await api.get<EvaluationCenterResponse>(`${BASE}/${assignmentId}/evaluation-center`)
  return data
}

/** Dept/Admin allocates one submission to one evaluator. Recorded by the M09.6
 *  assignment engine, which is the single ledger for evaluation work. */
export async function assignEvaluator(
  submissionId: string,
  payload: AssignEvaluatorPayload,
): Promise<{ allocation_id: string; evaluator_user_id: string }> {
  const { data } = await api.post(`${BASE}/submissions/${submissionId}/evaluator`, payload)
  return data
}

// finalizeAssignmentMarks removed — POST /{id}/finalize no longer exists. The
// owning faculty's release IS the ratification; see releaseAssignmentMarks.

// ── AI evaluation (advisory, read-only) ─────────────────────────────────────

/** The advisory AI evaluation for a submission, or null if none exists yet. */
export async function getAiEvaluation(submissionId: string): Promise<AiEvaluation | null> {
  const { data } = await api.get<AiEvaluation | null>(`${BASE}/submissions/${submissionId}/ai-evaluation`)
  return data
}

/** Evaluator-triggered retry of the background AI evaluation (202, async). */
export async function reEvaluateSubmission(submissionId: string): Promise<void> {
  await api.post(`${BASE}/submissions/${submissionId}/re-evaluate`)
}

// ── Faculty — Submissions ────────────────────────────────────────────────────

export async function listSubmissions(assignmentId: string): Promise<CourseworkSubmissionListResponse> {
  const { data } = await api.get<CourseworkSubmissionListResponse>(`${BASE}/${assignmentId}/submissions`)
  return data
}

export async function gradeSubmission(
  submissionId: string,
  payload: CourseworkGradePayload
): Promise<CourseworkSubmission> {
  const { data } = await api.patch<CourseworkSubmission>(`${BASE}/submissions/${submissionId}/grade`, payload)
  return data
}

export async function returnSubmission(submissionId: string): Promise<CourseworkSubmission> {
  const { data } = await api.post<CourseworkSubmission>(`${BASE}/submissions/${submissionId}/return`)
  return data
}

export async function getAssignmentStatistics(assignmentId: string): Promise<CourseworkStatistics> {
  const { data } = await api.get<CourseworkStatistics>(`${BASE}/${assignmentId}/statistics`)
  return data
}

// ── Storage — submission file upload (generic, reused as-is from Labs) ──────

export interface UploadUrlRequest {
  entity_type: string
  entity_id: string
  original_filename: string
  content_type: string
  size_bytes: number
}

export interface UploadUrlResponse {
  object_key: string
  presigned_url: string
  expires_in_seconds: number
}

export async function requestSubmissionUploadUrl(
  params: UploadUrlRequest
): Promise<UploadUrlResponse> {
  const { data } = await api.post<UploadUrlResponse>('/storage/upload-url', params)
  return data
}

export function uploadFileToPresignedUrl(
  presignedUrl: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', presignedUrl)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`Upload failed: HTTP ${xhr.status}`))
    }
    xhr.onerror = () => reject(new Error('Network error during file upload'))
    xhr.send(file)
  })
}

export async function getSubmissionFileUrl(
  submissionId: string
): Promise<{ url: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ url: string; expires_in_seconds: number }>(
    `${BASE}/submissions/${submissionId}/file-url`
  )
  return data
}

/** Presigned download for the assignment's uploaded question paper (faculty /
 *  allocated evaluator). */
export async function getQuestionPaperUrl(
  assignmentId: string
): Promise<{ url: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ url: string; expires_in_seconds: number }>(
    `${BASE}/${assignmentId}/question-paper-url`
  )
  return data
}

/** Presigned download for the assignment's question paper (student). */
export async function studentGetQuestionPaperUrl(
  assignmentId: string
): Promise<{ url: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ url: string; expires_in_seconds: number }>(
    `${BASE}/student/${assignmentId}/question-paper-url`
  )
  return data
}

// ── Student ──────────────────────────────────────────────────────────────────

export async function studentListAssignments(params?: {
  syllabus_id?: string
}): Promise<CourseworkAssignmentListResponse> {
  const { data } = await api.get<CourseworkAssignmentListResponse>(`${BASE}/student`, { params })
  return data
}

export async function studentGetAssignment(id: string): Promise<CourseworkAssignment> {
  const { data } = await api.get<CourseworkAssignment>(`${BASE}/student/${id}`)
  return data
}

export async function studentSubmit(
  assignmentId: string,
  payload: CourseworkSubmitPayload
): Promise<CourseworkSubmission> {
  const { data } = await api.post<CourseworkSubmission>(`${BASE}/student/${assignmentId}/submit`, payload)
  return data
}

export async function studentMySubmissions(params?: {
  syllabus_id?: string
}): Promise<CourseworkSubmissionListResponse> {
  const { data } = await api.get<CourseworkSubmissionListResponse>(`${BASE}/student/submissions/my`, { params })
  return data
}

export async function studentGetResult(submissionId: string): Promise<CourseworkSubmission> {
  const { data } = await api.get<CourseworkSubmission>(`${BASE}/student/submissions/${submissionId}/result`)
  return data
}
