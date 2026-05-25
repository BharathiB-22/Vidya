// M07 Research Supervision — Student proposal detail view
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { studentGetProblem, listActiveGuides } from '@/lib/api/research'

const STATUS_LABEL: Record<string, string> = {
  DRAFT:              'Draft',
  PENDING_REVIEW:     'Pending Review',
  ACCEPTED:           'Accepted',
  REVISION_REQUESTED: 'Revision Requested',
  REJECTED:           'Rejected',
}

const STATUS_COLOR: Record<string, string> = {
  DRAFT:              'bg-gray-100 text-gray-600',
  PENDING_REVIEW:     'bg-yellow-100 text-yellow-700',
  ACCEPTED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  REJECTED:           'bg-red-100 text-red-600',
}

const DECISION_LABEL: Record<string, string> = {
  ACCEPT: 'Accepted',
  REVISE: 'Revision requested',
  REJECT: 'Rejected',
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

export default function StudentResearchDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const {
    data: problem,
    isLoading: problemLoading,
    isError: problemError,
    error: problemErr,
  } = useQuery({
    queryKey: ['student-problem', id],
    queryFn: () => studentGetProblem(id!),
    enabled: !!id,
    retry: 1,
  })

  const { data: guides = [] } = useQuery({
    queryKey: ['research-guides'],
    queryFn: listActiveGuides,
    staleTime: 60_000,
  })

  const guide = guides.find((g) => g.id === problem?.guide_user_id)

  function guideDisplay(): string {
    if (guide) {
      return guide.identifier
        ? `${guide.identifier} — ${guide.full_name}`
        : guide.full_name
    }
    if (problem?.guide_user_id) {
      return `ID: ${problem.guide_user_id.slice(0, 8)}…`
    }
    return '—'
  }

  if (problemLoading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 flex items-center gap-3 text-gray-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading proposal…</span>
      </div>
    )
  }

  if (problemError || !problem) {
    const msg = (() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const d = (problemErr as any)?.response?.data
        return d?.message ?? d?.detail?.message ?? 'Failed to load proposal.'
      } catch {
        return 'Failed to load proposal.'
      }
    })()
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/research')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-6 flex gap-3 text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm">Proposal not found</p>
            <p className="text-sm mt-0.5 text-red-600">{msg}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/research')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> My Research
        </Button>
        <div className="flex items-start gap-3 flex-wrap">
          <h1 className="text-xl font-bold text-gray-900 flex-1">{problem.title}</h1>
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium flex-shrink-0 ${STATUS_COLOR[problem.status] ?? 'bg-gray-100 text-gray-600'}`}>
            {STATUS_LABEL[problem.status] ?? problem.status}
          </span>
        </div>
      </div>

      {/* Meta row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Submitted</p>
          <p className="text-gray-800 mt-0.5">{fmt(problem.created_at)}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Last Updated</p>
          <p className="text-gray-800 mt-0.5">{fmt(problem.updated_at)}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Guide</p>
          <p className="text-gray-800 mt-0.5 truncate">{guideDisplay()}</p>
        </div>
        {problem.decided_at && (
          <div className="rounded-lg bg-gray-50 px-3 py-2">
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Decided</p>
            <p className="text-gray-800 mt-0.5">{fmt(problem.decided_at)}</p>
          </div>
        )}
      </div>

      {/* Abstract */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-1">
        <h2 className="text-sm font-semibold text-gray-700">Abstract</h2>
        <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">{problem.abstract}</p>
      </div>

      {/* Research questions */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-3">
        <h2 className="text-sm font-semibold text-gray-700">
          Research Questions ({problem.research_questions.length})
        </h2>
        <ol className="space-y-2 list-decimal list-inside">
          {problem.research_questions.map((rq, i) => (
            <li key={i} className="text-sm text-gray-600">{rq.question}</li>
          ))}
        </ol>
      </div>

      {/* Guide decision & note */}
      {(problem.guide_decision || problem.guide_note) && (
        <div className={`rounded-xl border px-5 py-4 space-y-1 ${
          problem.guide_decision === 'ACCEPT'
            ? 'border-green-200 bg-green-50'
            : problem.guide_decision === 'REJECT'
            ? 'border-red-200 bg-red-50'
            : 'border-orange-200 bg-orange-50'
        }`}>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-gray-700">Guide Review</h2>
            {problem.guide_decision && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                problem.guide_decision === 'ACCEPT'
                  ? 'bg-green-100 text-green-800'
                  : problem.guide_decision === 'REJECT'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-orange-100 text-orange-800'
              }`}>
                {DECISION_LABEL[problem.guide_decision] ?? problem.guide_decision}
              </span>
            )}
          </div>
          {problem.guide_note && (
            <p className="text-sm text-gray-600 whitespace-pre-line">{problem.guide_note}</p>
          )}
        </div>
      )}

      {/* AI evaluation summary (shown when available) */}
      {(problem.novelty_score !== null || problem.ai_recommendation) && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 space-y-3">
          <h2 className="text-sm font-semibold text-indigo-800">AI Evaluation</h2>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { label: 'Novelty', value: problem.novelty_score },
              { label: 'Feasibility', value: problem.feasibility_score },
              { label: 'Clarity', value: problem.clarity_score },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-white/60 px-2 py-2">
                <p className="text-xs text-indigo-500">{label}</p>
                <p className="text-lg font-bold text-indigo-900">
                  {value !== null && value !== undefined ? value.toFixed(1) : '—'}
                </p>
              </div>
            ))}
          </div>
          {problem.ai_reasoning && (
            <p className="text-xs text-indigo-700 leading-relaxed">{problem.ai_reasoning}</p>
          )}
        </div>
      )}
    </div>
  )
}
