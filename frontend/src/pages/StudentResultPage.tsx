import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, CheckCircle2, Loader2, AlertTriangle, Lock, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { ConfidenceBadge } from '@/components/labs/ConfidenceBadge'
import { useStudentResult } from '@/hooks/labs'
import type { ReviewPanel } from '@/types/labs'

export default function StudentResultPage() {
  const { submissionId } = useParams<{ submissionId: string }>()
  const navigate = useNavigate()
  const sid = submissionId ?? ''

  const { data, isLoading, isError } = useStudentResult(sid)
  const panel = data as ReviewPanel | undefined

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-400" />
        <p className="text-sm text-gray-500">
          Result not available yet. Grades are released only after faculty ratification.
        </p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/labs')}>
          Back to Assignments
        </Button>
      </div>
    )
  }

  if (!panel) return null

  const { submission, assignment, grade_entry } = panel
  const evaluation = submission.evaluation

  if (!grade_entry) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center space-y-3">
        <Lock className="h-8 w-8 mx-auto text-gray-500" />
        <p className="text-sm text-gray-500">Your grade has not been finalised yet.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/labs')}>
          Back to Assignments
        </Button>
      </div>
    )
  }

  const percentage = grade_entry.max_marks > 0
    ? Math.round((grade_entry.final_score / grade_entry.max_marks) * 100)
    : 0

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/labs')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      {/* Grade card */}
      <div className="rounded-2xl border border-green-200 bg-green-50 px-6 py-6 text-center">
        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-600" />
        <h1 className="text-xl font-bold text-gray-900">{assignment.title}</h1>
        <p className="text-sm text-gray-500 mt-0.5">Final Grade</p>
        <div className="mt-4">
          <span className="text-5xl font-extrabold text-green-800">{grade_entry.final_score}</span>
          <span className="text-xl text-green-600"> / {grade_entry.max_marks}</span>
        </div>
        <p className="text-lg font-semibold text-green-700 mt-1">{percentage}%</p>
        <div className="mt-2 flex items-center justify-center gap-3 text-xs text-green-600 flex-wrap">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Submitted {new Date(submission.submitted_at).toLocaleDateString()}
          </span>
          {submission.is_late && (
            <span className="text-orange-600 font-medium">· Late</span>
          )}
          <span>· Graded {new Date(grade_entry.ratified_at).toLocaleDateString()}</span>
        </div>
        {grade_entry.ratification_note && (
          <div className="mt-4 text-left bg-white rounded-lg px-4 py-3 border border-green-100">
            <p className="text-xs font-semibold text-gray-500 mb-1">Faculty note</p>
            <p className="text-sm text-gray-700 italic">"{grade_entry.ratification_note}"</p>
          </div>
        )}
      </div>

      {/* Badges */}
      {evaluation && (
        <div className="flex items-center gap-2 flex-wrap">
          <AIScanBadge status={submission.ai_scan_status} />
          {evaluation.confidence_level && <ConfidenceBadge level={evaluation.confidence_level} />}
          {submission.is_late && (
            <span className="text-xs text-orange-600 bg-orange-50 border border-orange-200 px-2 py-0.5 rounded-full font-medium">
              Late submission
            </span>
          )}
        </div>
      )}

      {/* Per-criterion breakdown */}
      {evaluation && evaluation.rubric_scores.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-700">Score Breakdown</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {assignment.rubric.map((rubric) => {
              const score = evaluation.rubric_scores.find((s) => s.criterion_id === rubric.criterion_id)
              const finalScore = score?.human_score ?? score?.ai_score ?? null
              return (
                <div key={rubric.criterion_id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{rubric.name}</p>
                      {score?.human_note && (
                        <p className="text-xs text-gray-500 mt-0.5 italic">
                          <span className="not-italic font-medium text-gray-600">Feedback: </span>
                          "{score.human_note}"
                        </p>
                      )}
                      {score?.ai_justification && !score?.human_note && (
                        <p className="text-xs text-gray-600 mt-0.5">
                          <span className="font-medium">AI: </span>{score.ai_justification}
                        </p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-sm font-bold text-gray-900">
                        {finalScore != null ? finalScore : '—'}
                      </span>
                      <span className="text-xs text-gray-600"> / {rubric.max_marks}</span>
                    </div>
                  </div>

                  {/* Progress bar */}
                  {finalScore != null && rubric.max_marks > 0 && (
                    <div className="mt-2 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-green-500 transition-all"
                        style={{ width: `${Math.min(100, (finalScore / rubric.max_marks) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Test results (CODE) */}
      {assignment.submission_type === 'CODE' && evaluation?.test_results && evaluation.test_results.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-700">Test Results</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {evaluation.test_results.map((tr) => (
              <div key={tr.id} className="px-4 py-2.5 flex items-center gap-3">
                <span className={`h-2 w-2 rounded-full shrink-0 ${tr.passed ? 'bg-green-500' : 'bg-red-400'}`} />
                <span className="text-sm text-gray-700 flex-1">{tr.name}</span>
                <span className="text-xs text-gray-600">{tr.points_awarded} pts</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
