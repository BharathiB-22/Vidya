import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { CheckCircle2, Clock, BookOpen, ChevronRight, Loader2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAttemptResult } from '@/hooks/digitalExams'
import type { DigitalResultResponse } from '@/types/digitalExam'

function ScoreSummary({ result }: { result: DigitalResultResponse }) {
  const { attempt, mcq_questions, subjective_questions, correct_mcq } = result
  const mcqScore   = attempt.auto_score   ?? 0
  const mcqMax     = attempt.mcq_max_score ?? 0
  const pct        = mcqMax > 0 ? Math.round((mcqScore / mcqMax) * 100) : 0

  return (
    <div className="rounded-xl border border-gray-200 bg-white px-6 py-5 space-y-4">
      <h2 className="font-semibold text-gray-700">Score Summary</h2>

      {mcq_questions > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">MCQ Score</span>
            <span className="font-bold text-gray-900">
              {mcqScore} / {mcqMax}
              <span className="text-gray-600 font-normal ml-2">({pct}%)</span>
            </span>
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                pct >= 60 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-xs text-gray-600">
            {correct_mcq} of {mcq_questions} MCQ correct
          </p>
        </div>
      )}

      {subjective_questions > 0 && (
        <div className="flex items-start gap-2 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2.5">
          <BookOpen className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
          <p className="text-xs text-blue-700">
            <strong>{subjective_questions} subjective question{subjective_questions > 1 ? 's' : ''}</strong> pending
            faculty evaluation. Final marks will be published after board declaration.
          </p>
        </div>
      )}
    </div>
  )
}

export default function SubmissionConfirmPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const sid = sessionId ?? ''

  const attemptId: string =
    (location.state as { attemptId?: string } | null)?.attemptId
    ?? sessionStorage.getItem(`exam_attempt_${sid}`)
    ?? ''

  // Result may have been passed directly from submit mutation
  const passedResult: DigitalResultResponse | null =
    (location.state as { result?: DigitalResultResponse } | null)?.result ?? null

  const { data: fetchedResult, isLoading, isError } = useAttemptResult(
    passedResult ? '' : attemptId
  )

  const result = passedResult ?? fetchedResult

  if (!passedResult && isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  const submittedAt = result?.attempt?.submitted_at
    ? new Date(result.attempt.submitted_at).toLocaleString()
    : 'just now'

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Success hero */}
      <div className="rounded-2xl border border-green-200 bg-green-50 px-6 py-8 text-center space-y-3">
        <CheckCircle2 className="h-12 w-12 mx-auto text-green-600" />
        <h1 className="text-xl font-bold text-gray-900">Exam Submitted Successfully</h1>
        <div className="flex items-center justify-center gap-1.5 text-sm text-gray-500">
          <Clock className="h-3.5 w-3.5" />
          <span>Submitted at {submittedAt}</span>
        </div>
      </div>

      {/* Score summary */}
      {result ? (
        <ScoreSummary result={result} />
      ) : isError ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-4 flex items-center gap-2 text-sm text-gray-500">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          Score details unavailable right now.
        </div>
      ) : null}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        {attemptId && (
          <Button
            className="flex-1 gap-1"
            onClick={() => navigate(`/student/exams/digital/attempts/${attemptId}/result`)}
          >
            View Detailed Result
            <ChevronRight className="h-4 w-4" />
          </Button>
        )}
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => navigate('/student/exams/digital')}
        >
          Back to Exams
        </Button>
      </div>
    </div>
  )
}
