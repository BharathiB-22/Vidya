import api from '@/lib/api'
import type {
  ApprovalRequest,
  ApproveCurriculumRequest,
  ChangeSummary,
  GenerateSyllabiRequest,
  GenerateSyllabiResponse,
  GovernanceInfo,
  GovernanceQueue,
  ReadinessSummary,
  SubmissionChecklist,
  SubmitForApprovalRequest,
  TrailEntry,
} from '@/types/governance'

const BASE = '/governance'

/** What this tenant calls its governance authority. Drives every label. */
export async function getGovernanceInfo(): Promise<GovernanceInfo> {
  const { data } = await api.get<GovernanceInfo>(`${BASE}/info`)
  return data
}

/** Curricula with the Board, plus those already approved/published. */
export async function getReviewQueue(): Promise<GovernanceQueue> {
  const { data } = await api.get<GovernanceQueue>(`${BASE}/queue`)
  return data
}

/**
 * Per-subject syllabus state, and whether the curriculum can be approved yet.
 * Drives the Board's workbench and the enabled state of Approve Curriculum.
 */
export async function getReadiness(programId: string): Promise<ReadinessSummary> {
  const { data } = await api.get<ReadinessSummary>(`${BASE}/programs/${programId}/readiness`)
  return data
}

/**
 * Generate the official syllabus for every subject that lacks one — core courses
 * and every elective option alike. One AI call per subject, dispatched as
 * independent background jobs.
 */
export async function generateSyllabi(
  programId: string,
  payload: GenerateSyllabiRequest = {},
): Promise<GenerateSyllabiResponse> {
  const { data } = await api.post(`${BASE}/programs/${programId}/syllabus/generate`, payload)
  return data
}

/**
 * Approve AND lock, permanently. Refused (422 SYLLABUS_INCOMPLETE) unless every
 * subject has an approved official syllabus.
 */
export async function approveCurriculum(
  programId: string,
  payload: ApproveCurriculumRequest,
): Promise<{ program_id: string; status: string; syllabi_locked: number }> {
  const { data } = await api.post(`${BASE}/programs/${programId}/approve`, payload)
  return data
}

/** What the Board changed while it held this curriculum. Shown to the Dean. */
export async function getChangeSummary(programId: string): Promise<ChangeSummary> {
  const { data } = await api.get<ChangeSummary>(`${BASE}/programs/${programId}/changes`)
  return data
}

/**
 * The full governance trail: who reviewed, who modified, who approved, and when.
 *
 * The Board has no separation of duties — one member may enhance, write the
 * syllabus, approve and lock a curriculum alone — so this record is the whole of
 * its accountability. Built from the append-only audit log.
 */
export async function getGovernanceTrail(programId: string): Promise<TrailEntry[]> {
  const { data } = await api.get<TrailEntry[]>(`${BASE}/programs/${programId}/trail`)
  return data
}

/** Every submit → approve this curriculum has been through. */
export async function getApprovalHistory(programId: string): Promise<ApprovalRequest[]> {
  const { data } = await api.get<ApprovalRequest[]>(`${BASE}/programs/${programId}/history`)
  return data
}

/**
 * What the Dean still has to finish before the curriculum can be submitted.
 *
 * Read-only, and it does NOT replace the server's guard: the submit endpoint
 * refuses a bad handover whether or not anyone called this first.
 *
 * Lives on the program router (it is a Dean action on a Dean-owned resource).
 */
export async function getSubmissionChecklist(programId: string): Promise<SubmissionChecklist> {
  const { data } = await api.get<SubmissionChecklist>(`/programs/${programId}/submission-check`)
  return data
}

/** Dean action — lives on the program router, not /governance. */
export async function submitForApproval(
  programId: string,
  payload: SubmitForApprovalRequest,
): Promise<{ id: string; status: string; version: number }> {
  const { data } = await api.post(`/programs/${programId}/submit`, payload)
  return data
}
