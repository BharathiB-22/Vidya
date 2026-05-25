import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Eye, Loader2, AlertTriangle, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { useEvaluatorAssignment, useEvaluatorSubmissions } from '@/hooks/labs'
import type { LabSubmission, SubmissionStatus } from '@/types/labs'

const SUB_STATUS_CFG: Record<SubmissionStatus, { label: string; cls: string }> = {
  SUBMITTED:  { label: 'Submitted',  cls: 'text-blue-700 bg-blue-50' },
  EVALUATING: { label: 'Evaluating', cls: 'text-yellow-700 bg-yellow-50' },
  EVALUATED:  { label: 'AI Evaluated', cls: 'text-purple-700 bg-purple-50' },
  REVIEWED:   { label: 'Recommended', cls: 'text-indigo-700 bg-indigo-50' },
  RATIFIED:   { label: 'Ratified',   cls: 'text-green-700 bg-green-50' },
}

function SubmissionRow({
  sub,
  onReview,
}: {
  sub: LabSubmission
  onReview: () => void
}) {
  const cfg = SUB_STATUS_CFG[sub.status] ?? { label: sub.status, cls: 'text-gray-500 bg-gray-50' }
  const canReview = ['EVALUATED', 'REVIEWED', 'RATIFIED'].includes(sub.status)
  const isRatified = sub.status === 'RATIFIED'

  return (
    <div className="px-5 py-3.5 flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-mono text-gray-700 truncate">
          {sub.student_user_id}
        </p>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>
            {cfg.label}
          </span>
          <AIScanBadge status={sub.ai_scan_status} />
          {sub.is_late && (
            <span className="text-xs text-orange-600 bg-orange-50 px-1.5 py-0.5 rounded">
              Late
            </span>
          )}
          <span className="text-xs text-gray-400">
            {new Date(sub.submitted_at).toLocaleDateString()}
          </span>
        </div>
      </div>

      <div className="shrink-0 flex items-center gap-2">
        {isRatified ? (
          <span className="text-xs text-green-700 font-medium">Finalised</span>
        ) : canReview ? (
          <Button size="sm" variant="ghost" onClick={onReview} className="text-indigo-600 hover:text-indigo-800">
            <Eye className="h-3.5 w-3.5 mr-1" />
            {sub.status === 'REVIEWED' ? 'Edit Recommendation' : 'Start Review'}
          </Button>
        ) : (
          <span className="text-xs text-gray-400">Awaiting AI eval</span>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EvaluatorSubmissionsPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>()
  const navigate = useNavigate()
  const id = assignmentId ?? ''

  const { data: assignment, isLoading: assignmentLoading } = useEvaluatorAssignment(id)
  const { data: subsData, isLoading: subsLoading, isError } = useEvaluatorSubmissions(id)

  const submissions = subsData?.items ?? []

  const pending   = submissions.filter((s) => !['REVIEWED', 'RATIFIED'].includes(s.status)).length
  const reviewed  = submissions.filter((s) => s.status === 'REVIEWED').length
  const ratified  = submissions.filter((s) => s.status === 'RATIFIED').length

  if (assignmentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      {/* Nav */}
      <Button
        variant="ghost"
        size="sm"
        className="-ml-1"
        onClick={() => navigate('/evaluator')}
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        My Evaluations
      </Button>

      {/* Header */}
      {assignment && (
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-gray-900">{assignment.title}</h1>
            <LabStatusBadge status={assignment.status} />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {assignment.rubric.reduce((s, c) => s + c.max_marks, 0)} marks ·{' '}
            {assignment.rubric.length} rubric criteria
          </p>
        </div>
      )}

      {/* Summary chips */}
      <div className="flex gap-3 flex-wrap">
        <span className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-full font-medium">
          {submissions.length} total
        </span>
        {pending > 0 && (
          <span className="text-xs bg-amber-100 text-amber-700 px-3 py-1.5 rounded-full font-medium">
            {pending} pending
          </span>
        )}
        {reviewed > 0 && (
          <span className="text-xs bg-indigo-100 text-indigo-700 px-3 py-1.5 rounded-full font-medium">
            {reviewed} recommended
          </span>
        )}
        {ratified > 0 && (
          <span className="text-xs bg-green-100 text-green-700 px-3 py-1.5 rounded-full font-medium">
            {ratified} finalised
          </span>
        )}
      </div>

      {/* Rubric preview */}
      {assignment && assignment.rubric.length > 0 && (
        <details className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <summary className="px-4 py-3 text-sm font-medium text-gray-700 cursor-pointer select-none">
            Rubric ({assignment.rubric.length} criteria)
          </summary>
          <div className="divide-y divide-gray-100">
            {assignment.rubric.map((c) => (
              <div key={c.criterion_id} className="px-4 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-800">{c.name}</span>
                  <span className="text-xs text-gray-500">{c.max_marks} marks</span>
                </div>
                {c.description && (
                  <p className="text-xs text-gray-400 mt-0.5">{c.description}</p>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Submission list */}
      {subsLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : isError ? (
        <div className="text-center py-12">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-red-400" />
          <p className="text-sm text-gray-500">Failed to load submissions.</p>
        </div>
      ) : submissions.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Users className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No submissions yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
          {submissions.map((sub) => (
            <SubmissionRow
              key={sub.id}
              sub={sub}
              onReview={() => navigate(`/evaluator/submissions/${sub.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
