import { useState } from 'react'
import { Download, CheckCircle2, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  useAssignment,
  useAssignmentSubmissions,
  useAssignmentStatistics,
  useGradeSubmission,
  useReturnSubmission,
} from '@/hooks/coursework'
import { getSubmissionFileUrl } from '@/lib/api/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { CourseworkSubmission } from '@/types/coursework'

export function GradeRow({
  submission,
  maxMarks,
  onGrade,
  onReturn,
}: {
  submission: CourseworkSubmission
  maxMarks: number
  onGrade: (submissionId: string, marks: number, feedback: string) => void
  onReturn: (submissionId: string) => void
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
            {submission.student_usn && <span className="text-gray-400 font-normal"> · {submission.student_usn}</span>}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
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

      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="text-xs font-medium text-gray-500">Marks (/{maxMarks})</label>
          <input
            type="number"
            min={0}
            max={maxMarks}
            className="mt-1 w-28 rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={marks}
            onChange={(e) => setMarks(e.target.value)}
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs font-medium text-gray-500">Feedback</label>
          <input
            className="mt-1 w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Optional feedback for student"
          />
        </div>
        <Button
          size="sm"
          onClick={() => onGrade(submission.id, Number(marks), feedback)}
          disabled={marks === ''}
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

  const submissions = submissionsData?.items ?? []

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
            <p className="text-sm text-gray-400 mt-0.5">
              Due {new Date(assignment.due_date).toLocaleString()} · {assignment.max_marks} marks
            </p>
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
              <p className="text-xs text-gray-400 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading submissions…</div>
      ) : submissions.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <p className="text-sm text-gray-400">No submissions yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {submissions.map((s) => (
            <GradeRow
              key={s.id}
              submission={s}
              maxMarks={assignment?.max_marks ?? 100}
              onGrade={handleGrade}
              onReturn={handleReturn}
            />
          ))}
        </div>
      )}
    </div>
  )
}
