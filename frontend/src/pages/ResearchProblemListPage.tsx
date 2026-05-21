// M07 Research Supervision — Guide: Problem list + decide gate
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, BookOpen, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listProblems, decideProblem } from '@/lib/api/research'
import { addToast } from '@/hooks/useToast'
import type { ProblemStatus, ResearchProblem, GuideDecision } from '@/types/research'

const STATUS_OPTS: Array<{ value: ProblemStatus | ''; label: string }> = [
  { value: '',                 label: 'All' },
  { value: 'PENDING_REVIEW',   label: 'Pending Review' },
  { value: 'ACCEPTED',         label: 'Accepted' },
  { value: 'REVISION_REQUESTED', label: 'Revision Requested' },
  { value: 'REJECTED',         label: 'Rejected' },
  { value: 'DRAFT',            label: 'Draft' },
]

const STATUS_COLOR: Record<string, string> = {
  DRAFT:              'bg-gray-100 text-gray-600',
  PENDING_REVIEW:     'bg-yellow-100 text-yellow-700',
  ACCEPTED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  REJECTED:           'bg-red-100 text-red-600',
}

function DecideModal({
  problem,
  onClose,
}: {
  problem: ResearchProblem
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [decision, setDecision] = useState<GuideDecision>('ACCEPT')
  const [note, setNote]         = useState('')

  const { mutate, isPending, isError } = useMutation({
    mutationFn: () => decideProblem(problem.id, { decision, guide_note: note || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-problems'] })
      addToast('Decision submitted.', 'success')
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Decide on Proposal</h2>
        <p className="text-sm text-gray-600 font-medium">{problem.title}</p>

        {problem.ai_recommendation && (
          <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-sm">
            <span className="font-medium text-blue-700">AI recommendation:</span>{' '}
            <span className="text-blue-800">{problem.ai_recommendation}</span>
            {problem.ai_reasoning && (
              <p className="text-xs text-blue-600 mt-1">{problem.ai_reasoning}</p>
            )}
          </div>
        )}

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Decision</label>
          <div className="flex gap-2">
            {(['ACCEPT', 'REVISE', 'REJECT'] as GuideDecision[]).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDecision(d)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  decision === d
                    ? d === 'ACCEPT'
                      ? 'bg-green-600 text-white border-green-600'
                      : d === 'REJECT'
                      ? 'bg-red-600 text-white border-red-600'
                      : 'bg-orange-500 text-white border-orange-500'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Guide note (optional)</label>
          <textarea
            rows={3}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Feedback for the student…"
          />
        </div>

        {isError && (
          <p className="text-sm text-red-600">Failed to submit decision. Please try again.</p>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={() => mutate()} disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Confirm Decision
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ResearchProblemListPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<ProblemStatus | ''>('')
  const [deciding, setDeciding]         = useState<ResearchProblem | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['research-problems', statusFilter],
    queryFn: () => listProblems({ status: statusFilter || undefined }),
  })
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Research Proposals</h1>
          <p className="text-sm text-gray-500 mt-0.5">Student proposals assigned to you as guide</p>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_OPTS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value as ProblemStatus | '')}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              statusFilter === opt.value
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading && <PageLoading message="Loading proposals…" />}

      {isError && (
        <PageError message="Failed to load proposals." onRetry={() => refetch()} />
      )}

      {data && data.items.length === 0 && (
        <PageEmpty icon={BookOpen} message="No proposals found." />
      )}

      {data && data.items.length > 0 && (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {data.items.map((p) => (
            <div key={p.id} className="px-5 py-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <button
                  type="button"
                  className="flex-1 text-left"
                  onClick={() => navigate(`/research/problems/${p.id}`)}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800">{p.title}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[p.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {p.status.replace('_', ' ')}
                    </span>
                    {p.ai_recommendation && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 font-medium">
                        AI: {p.ai_recommendation}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {p.source === 'AI_GENERATED' ? 'AI-generated · ' : ''}
                    Submitted {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </button>

                <div className="flex items-center gap-2">
                  {p.status === 'PENDING_REVIEW' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-indigo-700 hover:bg-indigo-50"
                      onClick={(e) => { e.stopPropagation(); setDeciding(p) }}
                    >
                      Decide
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={() => navigate(`/research/problems/${p.id}`)}
                    className="p-1 rounded hover:bg-gray-100"
                  >
                    <ChevronRight className="h-4 w-4 text-gray-300" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {deciding && (
        <DecideModal problem={deciding} onClose={() => setDeciding(null)} />
      )}
    </div>
  )
}
