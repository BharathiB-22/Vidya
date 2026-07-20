import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, CheckCircle2, Send, ShieldCheck, UserCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  useAssignment,
  useAssignmentSubmissions,
  useAssignmentStatistics,
  useAssignEvaluator,
  useFinalizeMarks,
  useGradeSubmission,
  useReturnSubmission,
  useSubmitForEvaluation,
} from '@/hooks/coursework'
import { AssignmentQuestionsView } from '@/components/coursework/AssignmentQuestionsView'
import { getQuestionPaperUrl, getSubmissionFileUrl, listEligibleEvaluators } from '@/lib/api/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'
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
  const finalizeMutation = useFinalizeMarks()
  // Active workspace, not base role — a FACULTY account holding a DEAN grant must
  // be able to allocate while acting in the Dean workspace (matches viewing_role).
  const { activeWorkspace } = useWorkspace()

  const submissions = submissionsData?.items ?? []

  // The evaluation hand-off: faculty submits, the department allocates and
  // ratifies. Faculty deliberately cannot allocate their own evaluator.
  const canAllocate    = activeWorkspace === 'ADMIN' || activeWorkspace === 'DEAN'
  const isClosed       = assignment?.status === 'CLOSED'
  const underEvaluation = assignment?.status === 'SUBMITTED'
  const isFinalized    = assignment?.status === 'FINALIZED'
  const allEvaluated   = submissions.length > 0 && submissions.every((s) => s.marks_obtained != null)

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

  function handleFinalize() {
    finalizeMutation.mutate(assignmentId, {
      onSuccess: () => addToast('Marks finalized.', 'success'),
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
            {isFinalized && assignment?.finalized_at && (
              <p className="text-green-700 font-medium">
                Marks finalized on {new Date(assignment.finalized_at).toLocaleString()}. Grading is closed.
              </p>
            )}
          </div>
          {isClosed && (
            <Button size="sm" onClick={handleSubmitForEvaluation} disabled={submitMutation.isPending}>
              <Send className="h-3.5 w-3.5 mr-1" />
              Submit for Evaluation
            </Button>
          )}
          {underEvaluation && canAllocate && (
            <Button
              size="sm"
              onClick={handleFinalize}
              disabled={finalizeMutation.isPending || !allEvaluated}
              title={allEvaluated ? undefined : 'Every submission must be evaluated first.'}
            >
              <ShieldCheck className="h-3.5 w-3.5 mr-1" />
              Finalize Marks
            </Button>
          )}
        </div>
      )}

      {stats && (
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
