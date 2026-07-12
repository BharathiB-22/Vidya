import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as governanceApi from '@/lib/api/governance'
import { programKeys } from '@/hooks/programs'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type {
  ApproveCurriculumRequest,
  GenerateSyllabiRequest,
  SubmitForApprovalRequest,
} from '@/types/governance'

export const governanceKeys = {
  all: ['governance'] as const,
  info: () => [...governanceKeys.all, 'info'] as const,
  queue: () => [...governanceKeys.all, 'queue'] as const,
  readiness: (programId: string) => [...governanceKeys.all, 'readiness', programId] as const,
  changes: (programId: string) => [...governanceKeys.all, 'changes', programId] as const,
  trail: (programId: string) => [...governanceKeys.all, 'trail', programId] as const,
  submissionCheck: (programId: string) =>
    [...governanceKeys.all, 'submission-check', programId] as const,
  history: (programId: string) => [...governanceKeys.all, 'history', programId] as const,
}

/** The tenant's governance vocabulary. Cached for the session — it never changes
 *  while a user is signed in (only a Platform Admin can alter it).
 *
 *  `enabled` is passed false when nobody is signed in, so the login page does not
 *  fire an authenticated request and log a pointless 401. */
export function useGovernanceInfo(enabled = true) {
  return useQuery({
    queryKey: governanceKeys.info(),
    queryFn: governanceApi.getGovernanceInfo,
    staleTime: Infinity,
    retry: false,
    enabled,
  })
}

export function useReviewQueue() {
  return useQuery({
    queryKey: governanceKeys.queue(),
    queryFn: governanceApi.getReviewQueue,
  })
}

/**
 * Per-subject syllabus state for the Board's workbench.
 *
 * Polls while any syllabus is still generating, so the batch's progress appears
 * without the Board having to reload. Generation is one AI call per subject and
 * takes a while; a static page would look broken.
 */
export function useReadiness(programId: string, enabled = true) {
  return useQuery({
    queryKey: governanceKeys.readiness(programId),
    queryFn: () => governanceApi.getReadiness(programId),
    enabled: enabled && Boolean(programId),
    refetchInterval: (query) =>
      query.state.data?.items.some((i) => i.syllabus_status === 'AI_GENERATING') ? 4000 : false,
  })
}

/**
 * What the Dean still has to finish before the handover.
 *
 * `enabled` is false until the Dean actually clicks Submit — there is no reason to
 * run a compliance pass on every program page view.
 */
export function useSubmissionChecklist(programId: string, enabled = false) {
  return useQuery({
    queryKey: governanceKeys.submissionCheck(programId),
    queryFn: () => governanceApi.getSubmissionChecklist(programId),
    enabled: enabled && Boolean(programId),
    staleTime: 0,
  })
}

/** What the Board changed. The Dean reads this before publishing. */
export function useChangeSummary(programId: string, enabled = true) {
  return useQuery({
    queryKey: governanceKeys.changes(programId),
    queryFn: () => governanceApi.getChangeSummary(programId),
    enabled: enabled && Boolean(programId),
  })
}

/**
 * The governance trail. This is the Board's accountability record — with no
 * separation of duties inside the Board, it is the only thing that answers "who
 * did this?".
 */
export function useGovernanceTrail(programId: string, enabled = true) {
  return useQuery({
    queryKey: governanceKeys.trail(programId),
    queryFn: () => governanceApi.getGovernanceTrail(programId),
    enabled: enabled && Boolean(programId),
  })
}

export function useApprovalHistory(programId: string, enabled = true) {
  return useQuery({
    queryKey: governanceKeys.history(programId),
    queryFn: () => governanceApi.getApprovalHistory(programId),
    enabled: enabled && Boolean(programId),
  })
}

function useInvalidateCurriculum() {
  const qc = useQueryClient()
  return (programId: string) => {
    qc.invalidateQueries({ queryKey: programKeys.detail(programId) })
    qc.invalidateQueries({ queryKey: programKeys.status(programId) })
    qc.invalidateQueries({ queryKey: programKeys.all })
    qc.invalidateQueries({ queryKey: governanceKeys.queue() })
    qc.invalidateQueries({ queryKey: governanceKeys.readiness(programId) })
    qc.invalidateQueries({ queryKey: governanceKeys.changes(programId) })
    qc.invalidateQueries({ queryKey: governanceKeys.trail(programId) })
    qc.invalidateQueries({ queryKey: governanceKeys.submissionCheck(programId) })
    qc.invalidateQueries({ queryKey: governanceKeys.history(programId) })
  }
}

/**
 * Dean → Board. A one-way handover: the Dean is read-only on this curriculum
 * from here, permanently. There is no path back.
 */
export function useSubmitForApproval() {
  const invalidate = useInvalidateCurriculum()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SubmitForApprovalRequest }) =>
      governanceApi.submitForApproval(id, payload),
    onSuccess: (_data, { id }) => {
      invalidate(id)
      addToast(
        'Curriculum submitted. It is now owned by the governance authority and read-only for you.',
        'success',
        9000,
      )
    },
    onError: (err) => addToast(getErrorMessage(err), 'error', 9000),
  })
}

/** Board → generate the official syllabus for every subject that lacks one. */
export function useGenerateSyllabi() {
  const invalidate = useInvalidateCurriculum()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload?: GenerateSyllabiRequest }) =>
      governanceApi.generateSyllabi(id, payload),
    onSuccess: (data, { id }) => {
      invalidate(id)
      if (data.dispatched === 0) {
        addToast('Every subject already has a syllabus. Nothing to generate.', 'info')
        return
      }
      addToast(
        `Generating the official syllabus for ${data.dispatched} subject${
          data.dispatched === 1 ? '' : 's'
        }${data.skipped ? ` (${data.skipped} already had one)` : ''}. ` +
          'This runs in the background — you can leave this page.',
        'success',
        9000,
      )
    },
    onError: (err) => addToast(getErrorMessage(err), 'error', 9000),
  })
}

/**
 * Board → approve + lock, permanently.
 *
 * Refused unless every subject has an approved official syllabus. The UI keeps
 * the button disabled until then, but the server refuses regardless — the gate
 * is the API's, not the button's.
 */
export function useApproveCurriculum() {
  const invalidate = useInvalidateCurriculum()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ApproveCurriculumRequest }) =>
      governanceApi.approveCurriculum(id, payload),
    onSuccess: (data, { id }) => {
      invalidate(id)
      addToast(
        `Curriculum approved and locked. ${data.syllabi_locked} syllabus/syllabi frozen. ` +
          'The Dean has been notified and can now publish it.',
        'success',
        9000,
      )
    },
    onError: (err) => addToast(getErrorMessage(err), 'error', 9000),
  })
}
