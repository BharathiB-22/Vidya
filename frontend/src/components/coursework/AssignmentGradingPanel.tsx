import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, CheckCircle2, Send, ShieldCheck, UserCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  useAssignment,
  useAssignmentSubmissions,
  useAssignmentStatistics,
  useAssignEvaluator,
  useReleaseMarks,
  useGradeSubmission,
  useReturnSubmission,
  useSubmitForEvaluation,
} from '@/hooks/coursework'
import { AssignmentQuestionsView } from '@/components/coursework/AssignmentQuestionsView'
import { CourseworkAiPanel } from '@/components/coursework/CourseworkAiPanel'
import { getQuestionPaperUrl, getSubmissionFileUrl, listEligibleEvaluators } from '@/lib/api/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'
import { useAuth } from '@/lib/auth'
import type { CourseworkSubmission, EligibleEvaluator } from '@/types/coursework'

export function GradeRow({
  submission,
  maxMarks,
  canGrade = true,
  evaluators,
  onGrade,
  onReturn,
  onAssignEvaluator,
}: {
  submission: CourseworkSubmission
  maxMarks: number
  /** False once marks are finalized — grading is closed. */
  canGrade?: boolean
  /** Non-empty only for Dept/Admin while the assignment is out for evaluation. */
  evaluators?: EligibleEvaluator[]
  onGrade: (submissionId: string, marks: number, feedback: string) => void
  onReturn: (submissionId: string) => void
  onAssignEvaluator?: (submissionId: string, evaluatorUserId: string) => void
}) {
  const [marks, setMarks] = useState(submission.marks_obtained != null ? String(submission.marks_obtained) : '')
  const [feedback, setFeedback] = useState(submission.feedback ?? '')

  async function handleDownload() {
    if (!submission.content_url) return
    try {
      const { url } = await getSubmissionFileUrl(submission.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    }
  }

  return (
    <div className="px-5 py-4 space-y-3">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <p className="text-sm font-semibold text-gray-800">
            {submission.student_name ?? submission.student_user_id}
            {submission.student_usn && <span className="text-gray-600 font-normal"> · {submission.student_usn}</span>}
          </p>
          <p className="text-xs text-gray-600 mt-0.5">
            Attempt {submission.attempt_number} · Submitted {new Date(submission.submitted_at).toLocaleString()}
            {submission.is_late && <span className="text-orange-600 font-medium"> · Late</span>}
            {submission.graded_at && <> · Graded {new Date(submission.graded_at).toLocaleString()}</>}
          </p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          submission.status === 'RETURNED' ? 'bg-indigo-50 text-indigo-700'
          : submission.status === 'GRADED' ? 'bg-green-50 text-green-700'
          : 'bg-blue-50 text-blue-700'
        }`}>
          {submission.status}
        </span>
      </div>

      {submission.content_text && (
        <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap max-h-40 overflow-y-auto">
          {submission.content_text}
        </div>
      )}
      {submission.content_url && (
        <Button variant="outline" size="sm" onClick={handleDownload}>
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Download submission
        </Button>
      )}

      {/* Evaluator allocation — Dept/Admin only, once the assignment is out for
          evaluation. The evaluator shown is read from the M09.6 ledger. */}
      {evaluators && evaluators.length > 0 && onAssignEvaluator && (
        <div className="flex items-end gap-2 flex-wrap rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs font-medium text-gray-500">
              <UserCheck className="h-3 w-3 inline mr-1" />
              Evaluator
            </label>
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={submission.evaluator_user_id ?? ''}
              onChange={(e) => e.target.value && onAssignEvaluator(submission.id, e.target.value)}
            >
              <option value="">— Not allocated —</option>
              {evaluators.map((ev) => (
                <option key={ev.id} value={ev.id}>{ev.full_name ?? ev.email ?? ev.id}</option>
              ))}
            </select>
          </div>
          {submission.evaluator_user_id && (
            <p className="text-xs text-gray-600 pb-2">
              Allocated to {submission.evaluator_name ?? 'an evaluator'}. Reallocating requires
              cancelling the current allocation.
            </p>
          )}
        </div>
      )}

      {/* Read-only allocation, for viewers who cannot allocate — above all the
          faculty who set this coursework. They hand it to the department and were
          previously shown nothing back; the allocation is already in the payload,
          it was simply gated behind the Dept/Admin editor above. Display only. */}
      {!(evaluators && evaluators.length > 0 && onAssignEvaluator) && submission.evaluator_user_id && (
        <p className="text-xs text-gray-600 flex items-center gap-1.5">
          <UserCheck className="h-3 w-3 text-gray-400" />
          Evaluator: <span className="font-medium text-gray-800">
            {submission.evaluator_name ?? submission.evaluator_user_id}
          </span>
        </p>
      )}

      {/* The evaluator's RECOMMENDATION. Read-only and permanent: the input below
          carries the faculty's own decision, and saving it never overwrites what
          the evaluator recommended. "Accept" only prefills the input. */}
      {submission.evaluator_marks_obtained != null && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-xs font-semibold text-gray-700">
              <UserCheck className="h-3 w-3 inline mr-1 text-gray-500" />
              Evaluator recommends: {submission.evaluator_marks_obtained}/{maxMarks}
              {submission.evaluator_name && (
                <span className="font-normal text-gray-600"> · {submission.evaluator_name}</span>
              )}
            </p>
            {canGrade && (
              <button
                type="button"
                onClick={() => setMarks(String(submission.evaluator_marks_obtained))}
                className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
              >
                Accept evaluator marks →
              </button>
            )}
          </div>
          {submission.evaluator_feedback && (
            <p className="text-xs text-gray-700 mt-1 whitespace-pre-wrap">
              {submission.evaluator_feedback}
            </p>
          )}
          <p className="text-[10px] text-gray-500 mt-1">
            A recommendation — your decision below is the final mark.
          </p>
        </div>
      )}

      {/* Advisory AI evaluation — prefills the input below via "Accept AI marks",
          never sets the mark itself. Human is final authority. */}
      <CourseworkAiPanel submissionId={submission.id} onAcceptMarks={(m) => setMarks(String(m))} />

      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="text-xs font-medium text-gray-500">Marks (/{maxMarks})</label>
          <input
            type="number"
            min={0}
            max={maxMarks}
            disabled={!canGrade}
            className="mt-1 w-28 rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:bg-gray-50 disabled:text-gray-600"
            value={marks}
            onChange={(e) => setMarks(e.target.value)}
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs font-medium text-gray-500">Feedback</label>
          <input
            disabled={!canGrade}
            className="mt-1 w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:bg-gray-50 disabled:text-gray-600"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Optional feedback for student"
          />
        </div>
        <Button
          size="sm"
          onClick={() => onGrade(submission.id, Number(marks), feedback)}
          disabled={marks === '' || !canGrade}
        >
          <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
          Save Grade
        </Button>
        {submission.status === 'GRADED' && (
          <Button size="sm" variant="outline" onClick={() => onReturn(submission.id)}>
            <Send className="h-3.5 w-3.5 mr-1" />
            Return to Student
          </Button>
        )}
      </div>
    </div>
  )
}

export interface AssignmentGradingPanelProps {
  assignmentId: string
  /** Hide the title/due-date block when the caller already renders its own header (e.g. inside a tab). */
  showHeader?: boolean
}

export function AssignmentGradingPanel({ assignmentId, showHeader = true }: AssignmentGradingPanelProps) {
  const { data: assignment } = useAssignment(assignmentId)
  const { data: submissionsData, isLoading } = useAssignmentSubmissions(assignmentId)
  const { data: stats } = useAssignmentStatistics(assignmentId)
  const gradeMutation = useGradeSubmission(assignmentId)
  const returnMutation = useReturnSubmission(assignmentId)
  const submitMutation = useSubmitForEvaluation()
  const assignEvaluatorMutation = useAssignEvaluator(assignmentId)
  const releaseMutation = useReleaseMarks()
  // Active workspace, not base role — a FACULTY account holding a DEAN grant must
  // be able to allocate while acting in the Dean workspace (matches viewing_role).
  const { activeWorkspace } = useWorkspace()
  const { user } = useAuth()
  const currentUserId = user?.id ?? null

  const submissions = submissionsData?.items ?? []

  // The evaluation hand-off: faculty submits, the department allocates and
  // ratifies. Faculty deliberately cannot allocate their own evaluator.
  const canAllocate    = activeWorkspace === 'ADMIN' || activeWorkspace === 'DEAN'
  const isClosed       = assignment?.status === 'CLOSED'
  const underEvaluation = assignment?.status === 'SUBMITTED'
  const isReleased     = assignment?.status === 'RELEASED'
  // Grading closes on release, not on a separate ratification step.
  const isFinalized    = isReleased || assignment?.status === 'FINALIZED'
  const allEvaluated   = submissions.length > 0 && submissions.every((s) => s.marks_obtained != null)
  // Releasing is the owning faculty's decision. `useAssignment` only returns an
  // assignment this user may view, and the API re-checks ownership — this just
  // keeps the button off a peer evaluator's screen.
  const isOwner = Boolean(
    assignment && currentUserId && assignment.created_by_user_id === currentUserId
  )

  // Only fetched when it can actually be used — the endpoint is Dept/Admin only.
  const { data: evaluators = [] } = useQuery({
    queryKey: ['coursework-evaluators'],
    queryFn: listEligibleEvaluators,
    enabled: canAllocate && underEvaluation,
    staleTime: 5 * 60 * 1000,
  })

  function handleSubmitForEvaluation() {
    submitMutation.mutate(assignmentId, {
      onSuccess: () => addToast('Submitted to the department for evaluation.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleAssignEvaluator(submissionId: string, evaluatorUserId: string) {
    assignEvaluatorMutation.mutate(
      { submissionId, payload: { evaluator_user_id: evaluatorUserId } },
      {
        onSuccess: () => addToast('Evaluator allocated.', 'success'),
        onError: (err) => addToast(getErrorMessage(err), 'error'),
      }
    )
  }

  function handleRelease() {
    releaseMutation.mutate(assignmentId, {
      onSuccess: () => addToast('Marks released — students have been notified.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleGrade(submissionId: string, marks: number, feedback: string) {
    gradeMutation.mutate(
      { submissionId, payload: { marks_obtained: marks, feedback: feedback || undefined } },
      {
        onSuccess: () => addToast('Grade saved.', 'success'),
        onError: (err) => addToast(getErrorMessage(err), 'error'),
      }
    )
  }

  function handleReturn(submissionId: string) {
    returnMutation.mutate(submissionId, {
      onSuccess: () => addToast('Returned to student.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  return (
    <div className="space-y-6">
      {showHeader && (
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{assignment?.title ?? 'Assignment'}</h1>
          {assignment && (
            <p className="text-sm text-gray-600 mt-0.5">
              Due {new Date(assignment.due_date).toLocaleString()} · {assignment.max_marks} marks
            </p>
          )}
        </div>
      )}

      {/* Assignment context — shown on the standalone page (evaluator/faculty
          open it from a notification or "My Evaluations"). Hidden inside a tab,
          which renders its own header. */}
      {showHeader && assignment && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 text-sm">
          {(assignment.course_title || assignment.course_code) && (
            <div>
              <p className="text-xs font-medium text-gray-500">Course</p>
              <p className="text-gray-800">
                {assignment.course_code ? `${assignment.course_code} · ` : ''}
                {assignment.course_title ?? '—'}
              </p>
            </div>
          )}
          <div>
            <p className="text-xs font-medium text-gray-500">Faculty</p>
            <p className="text-gray-800">{assignment.created_by_name ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500">Due</p>
            <p className="text-gray-800">{new Date(assignment.due_date).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500">Evaluators</p>
            <p className="text-gray-800">
              {assignment.evaluator_names && assignment.evaluator_names.length > 0
                ? assignment.evaluator_names.join(', ')
                : 'Not yet assigned'}
            </p>
          </div>
          {assignment.instructions && (
            <div className="sm:col-span-2">
              <p className="text-xs font-medium text-gray-500">Instructions</p>
              <p className="text-gray-700 whitespace-pre-wrap">{assignment.instructions}</p>
            </div>
          )}
        </div>
      )}

      {assignment && (
        <AssignmentQuestionsView
          questions={assignment.questions ?? []}
          hasQuestionPaper={Boolean(assignment.question_paper_url)}
          fetchQuestionPaperUrl={() => getQuestionPaperUrl(assignmentId)}
        />
      )}

      {/* Evaluation hand-off. Each step is a human act, and the button only
          appears for the person whose act it is. */}
      {(isClosed || underEvaluation || isFinalized) && (
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="text-sm">
            {isClosed && (
              <p className="text-gray-600">
                Submissions are closed. Hand this to the department so an evaluator can be allocated.
              </p>
            )}
            {underEvaluation && (
              <p className="text-gray-600">
                Out for evaluation
                {canAllocate
                  ? ' — allocate an evaluator to each submission below.'
                  : ' — the department is allocating evaluators.'}
              </p>
            )}
            {isReleased && (
              <p className="text-green-700 font-medium">
                Marks released to students. Grading is closed.
              </p>
            )}
          </div>
          {isClosed && (
            <Button size="sm" onClick={handleSubmitForEvaluation} disabled={submitMutation.isPending}>
              <Send className="h-3.5 w-3.5 mr-1" />
              Submit for Evaluation
            </Button>
          )}
          {/* Release is the owning faculty's single decision — there is no separate
              ratification step, and the department does not take it. */}
          {!isReleased && isOwner && (
            <Button
              size="sm"
              onClick={handleRelease}
              disabled={releaseMutation.isPending || !allEvaluated}
              title={allEvaluated ? undefined : 'Every submission must be evaluated first.'}
            >
              <ShieldCheck className="h-3.5 w-3.5 mr-1" />
              Release Marks
            </Button>
          )}
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Students', value: stats.total_students },
              { label: 'Submitted', value: stats.submitted_count },
              { label: 'Graded', value: stats.graded_count },
              { label: 'Late', value: stats.late_count },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-center">
                <p className="text-xl font-bold text-gray-900">{s.value}</p>
                <p className="text-xs text-gray-600 mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>
          {/* Evaluation pipeline state, so the assignment's owner can see where it
              has got to without expanding every row. Advisory AI counts only. */}
          <p className="text-xs text-gray-600 -mt-3 flex items-center gap-x-4 gap-y-1 flex-wrap">
            {(stats.evaluator_assigned_count ?? 0) > 0 && (
              <span>{stats.evaluator_assigned_count} allocated to evaluators</span>
            )}
            {(stats.ai_completed_count ?? 0) > 0 && (
              <span className="text-indigo-600">AI evaluation complete: {stats.ai_completed_count}</span>
            )}
            {(stats.ai_pending_count ?? 0) > 0 && (
              <span className="text-indigo-400">AI running: {stats.ai_pending_count}</span>
            )}
            {(stats.ai_failed_count ?? 0) > 0 && (
              <span className="text-orange-600">AI failed: {stats.ai_failed_count}</span>
            )}
          </p>
        </>
      )}

      {isLoading ? (
        <div className="text-sm text-gray-600 py-8 text-center">Loading submissions…</div>
      ) : submissions.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <p className="text-sm text-gray-600">No submissions yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {submissions.map((s) => (
            <GradeRow
              key={s.id}
              submission={s}
              maxMarks={assignment?.max_marks ?? 100}
              canGrade={!isFinalized}
              evaluators={canAllocate && underEvaluation ? evaluators : undefined}
              onGrade={handleGrade}
              onReturn={handleReturn}
              onAssignEvaluator={handleAssignEvaluator}
            />
          ))}
        </div>
      )}
    </div>
  )
}
