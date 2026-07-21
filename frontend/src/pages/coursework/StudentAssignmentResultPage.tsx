import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, CheckCircle2, Loader2, AlertTriangle, Lock, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useStudentResult, useAssignment } from '@/hooks/coursework'

export default function StudentAssignmentResultPage() {
  const { submissionId } = useParams<{ submissionId: string }>()
  const navigate = useNavigate()
  const sid = submissionId ?? ''

  const { data: submission, isLoading, isError } = useStudentResult(sid)
  const { data: assignment } = useAssignment(submission?.assignment_id ?? '')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  if (isError || !submission) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-400" />
        <p className="text-sm text-gray-500">
          Result not available yet. Grades are released only after faculty grades this submission.
        </p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/assignments')}>
          Back to Assignments
        </Button>
      </div>
    )
  }

  if (submission.marks_obtained == null || !assignment) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-3">
        <Lock className="h-8 w-8 mx-auto text-gray-500" />
        <p className="text-sm text-gray-500">Your grade has not been finalised yet.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/assignments')}>
          Back to Assignments
        </Button>
      </div>
    )
  }

  const percentage = assignment.max_marks > 0
    ? Math.round((submission.marks_obtained / assignment.max_marks) * 100)
    : 0

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/assignments')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      <div className="rounded-2xl border border-green-200 bg-green-50 px-6 py-6 text-center">
        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-600" />
        <h1 className="text-xl font-bold text-gray-900">{assignment.title}</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {submission.status === 'RETURNED' ? 'Returned by Faculty' : 'Final Grade'}
        </p>
        <div className="mt-4">
          <span className="text-5xl font-extrabold text-green-800">{submission.marks_obtained}</span>
          <span className="text-xl text-green-600"> / {assignment.max_marks}</span>
        </div>
        <p className="text-lg font-semibold text-green-700 mt-1">{percentage}%</p>
        <div className="mt-2 flex items-center justify-center gap-3 text-xs text-green-600 flex-wrap">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Submitted {new Date(submission.submitted_at).toLocaleDateString()}
          </span>
          {submission.is_late && <span className="text-orange-600 font-medium">· Late</span>}
          {submission.graded_at && <span>· Graded {new Date(submission.graded_at).toLocaleDateString()}</span>}
        </div>
        {submission.feedback && (
          <div className="mt-4 text-left bg-white rounded-lg px-4 py-3 border border-green-100">
            <p className="text-xs font-semibold text-gray-500 mb-1">Faculty feedback</p>
            <p className="text-sm text-gray-700 italic">"{submission.feedback}"</p>
          </div>
        )}
      </div>
    </div>
  )
}
