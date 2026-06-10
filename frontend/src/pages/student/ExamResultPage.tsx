import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, CheckCircle2, XCircle, Clock,
  BookOpen, Loader2, AlertTriangle, Lock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAttemptResult } from '@/hooks/digitalExams'
import type { DigitalResponseOut } from '@/types/digitalExam'

function ResponseRow({ response, index }: { response: DigitalResponseOut; index: number }) {
  const isMcq = response.question_type === 'MCQ'
  if (!isMcq) return null   // subjective: not shown in breakdown

  return (
    <tr className="border-t border-gray-100">
      <td className="px-4 py-2.5 text-sm text-gray-600 font-medium">Q{index + 1}</td>
      <td className="px-4 py-2.5 text-sm text-gray-700">
        {response.selected_option
          ? <span className="font-mono font-bold">{response.selected_option}</span>
          : <span className="text-gray-400 italic">Not answered</span>
        }
      </td>
      <td className="px-4 py-2.5">
        {response.is_auto_scored ? (
          response.is_correct
            ? <span className="flex items-center gap-1 text-green-600 text-sm"><CheckCircle2 className="h-3.5 w-3.5" />Correct</span>
            : <span className="flex items-center gap-1 text-red-500 text-sm"><XCircle className="h-3.5 w-3.5" />Incorrect</span>
        ) : (
          <span className="text-gray-400 text-sm">Pending</span>
        )}
      </td>
      <td className="px-4 py-2.5 text-sm text-right font-medium">
        {response.auto_score !== null ? response.auto_score : '—'}
      </td>
    </tr>
  )
}

export default function ExamResultPage() {
  const { attemptId } = useParams<{ attemptId: string }>()
  const navigate = useNavigate()
  const aid = attemptId ?? ''

  const { data, isLoading, isError } = useAttemptResult(aid)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-400" />
        <p className="text-sm text-gray-500">Result not available.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/exams/digital')}>
          Back to Exams
        </Button>
      </div>
    )
  }

  if (!data) return null

  const { attempt, responses, total_questions, mcq_questions, subjective_questions, attempted_count, correct_mcq } = data
  const mcqScore  = attempt.auto_score   ?? 0
  const mcqMax    = attempt.mcq_max_score ?? 0
  const pct       = mcqMax > 0 ? Math.round((mcqScore / mcqMax) * 100) : 0
  const mcqResps  = responses.filter(r => r.question_type === 'MCQ')

  if (attempt.status === 'IN_PROGRESS') {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center space-y-3">
        <Lock className="h-8 w-8 mx-auto text-gray-300" />
        <p className="text-sm text-gray-500">Your exam has not been submitted yet.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>Go Back</Button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/exams/digital')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Exams
      </Button>

      {/* Score overview */}
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-6 space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-gray-900">Exam Result</h1>
          <span className="rounded-full bg-green-100 text-green-700 text-xs font-medium px-2.5 py-0.5">
            {attempt.status}
          </span>
        </div>

        {/* MCQ score gauge */}
        {mcq_questions > 0 && (
          <div className="space-y-2">
            <div className="flex items-end justify-between">
              <span className="text-sm text-gray-500">MCQ Score</span>
              <span className="text-2xl font-extrabold text-gray-900">
                {mcqScore}
                <span className="text-sm font-normal text-gray-400"> / {mcqMax}</span>
              </span>
            </div>
            <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  pct >= 60 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'
                }`}
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span>{correct_mcq} of {mcq_questions} correct</span>
              <span>{pct}%</span>
            </div>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total Questions', value: total_questions },
            { label: 'Attempted',       value: attempted_count },
            { label: 'MCQ Questions',   value: mcq_questions },
            { label: 'Subjective',      value: subjective_questions },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg bg-gray-50 px-3 py-2 text-center">
              <p className="text-lg font-bold text-gray-900">{value}</p>
              <p className="text-xs text-gray-500">{label}</p>
            </div>
          ))}
        </div>

        {/* Timestamps */}
        {attempt.submitted_at && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <Clock className="h-3.5 w-3.5" />
            Submitted {new Date(attempt.submitted_at).toLocaleString()}
          </div>
        )}
      </div>

      {/* MCQ breakdown table */}
      {mcqResps.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="font-semibold text-gray-700 text-sm">MCQ Answer Breakdown</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 text-left">#</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 text-left">Your Answer</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 text-left">Result</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 text-right">Marks</th>
                </tr>
              </thead>
              <tbody>
                {mcqResps.map((r, i) => (
                  <ResponseRow key={r.id} response={r} index={i} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Subjective pending */}
      {subjective_questions > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50 px-5 py-4">
          <BookOpen className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <p className="text-sm font-semibold text-blue-800">Subjective Answers Pending Evaluation</p>
            <p className="text-sm text-blue-600">
              Your {subjective_questions} subjective answer{subjective_questions > 1 ? 's are' : ' is'} being
              reviewed by faculty. Final marks will appear after the board declares results.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
