// M07 Research Supervision — Student: proposal list + proposal submission form
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, BookOpen, ChevronRight, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { studentListProblems, studentPropose } from '@/lib/api/research'
import type { ResearchProblem, ResearchQuestion } from '@/types/research'

const STATUS_COLOR: Record<string, string> = {
  DRAFT:              'bg-gray-100 text-gray-600',
  PENDING_REVIEW:     'bg-yellow-100 text-yellow-700',
  ACCEPTED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  REJECTED:           'bg-red-100 text-red-600',
}

function ProposeDialog({ onClose }: { onClose: () => void }) {
  const qc       = useQueryClient()
  const navigate = useNavigate()

  const [guideId, setGuideId]   = useState('')
  const [title, setTitle]       = useState('')
  const [abstract, setAbstract] = useState('')
  const [questions, setQuestions] = useState<string[]>([''])

  const { mutate, isPending, isError } = useMutation({
    mutationFn: () =>
      studentPropose({
        guide_user_id: guideId,
        title,
        abstract,
        research_questions: questions
          .filter((q) => q.trim())
          .map((q): ResearchQuestion => ({ question: q })),
      }),
    onSuccess: (p: ResearchProblem) => {
      qc.invalidateQueries({ queryKey: ['student-problems'] })
      onClose()
      navigate(`/student/research/${p.id}`)
    },
  })

  function addQuestion() {
    if (questions.length < 5) setQuestions([...questions, ''])
  }

  function removeQuestion(i: number) {
    setQuestions(questions.filter((_, idx) => idx !== i))
  }

  function updateQuestion(i: number, v: string) {
    setQuestions(questions.map((q, idx) => (idx === i ? v : q)))
  }

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const guideIdValid = UUID_RE.test(guideId.trim())

  const valid =
    guideIdValid &&
    title.trim() &&
    abstract.trim().length >= 50 &&
    questions.some((q) => q.trim())

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900">Submit Research Proposal</h2>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Guide User UUID</label>
          <input
            className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 font-mono ${
              guideId && !guideIdValid ? 'border-red-300 bg-red-50' : 'border-gray-200'
            }`}
            value={guideId}
            onChange={(e) => setGuideId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          />
          {guideId && !guideIdValid ? (
            <p className="text-xs text-red-600">Must be a valid UUID (e.g. from Admin → Users → Guide details).</p>
          ) : (
            <p className="text-xs text-gray-400">
              Copy this UUID from <strong>Admin → Users</strong>, click the Guide user's <strong>Edit</strong> button to reveal their UUID.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Title</label>
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Research proposal title"
          />
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Abstract</label>
          <textarea
            rows={4}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
            value={abstract}
            onChange={(e) => setAbstract(e.target.value)}
            placeholder="Describe your research in at least 50 characters…"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Research Questions (1–5)</label>
            {questions.length < 5 && (
              <button
                type="button"
                onClick={addQuestion}
                className="text-xs text-indigo-600 hover:underline"
              >
                + Add question
              </button>
            )}
          </div>
          {questions.map((q, i) => (
            <div key={i} className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                value={q}
                onChange={(e) => updateQuestion(i, e.target.value)}
                placeholder={`Research question ${i + 1}`}
              />
              {questions.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeQuestion(i)}
                  className="p-2 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>

        {isError && (
          <p className="text-sm text-red-600">Submission failed. Please try again.</p>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={() => mutate()} disabled={isPending || !valid}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Submit Proposal
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function StudentResearchPage() {
  const navigate     = useNavigate()
  const [open, setOpen] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['student-problems'],
    queryFn: () => studentListProblems(),
  })
  const problems = data?.items ?? []

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Research Proposals</h1>
          <p className="text-sm text-gray-500 mt-0.5">Submit and track your research proposals</p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          New Proposal
        </Button>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load proposals. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
          {[1, 2].map((n) => (
            <div key={n} className="px-5 py-4 animate-pulse">
              <div className="h-4 w-60 rounded bg-gray-200" />
              <div className="mt-1.5 h-3 w-36 rounded bg-gray-100" />
            </div>
          ))}
        </div>
      ) : problems.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No proposals yet. Submit your first research proposal.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {problems.map((p) => (
            <div
              key={p.id}
              className="px-5 py-4 hover:bg-gray-50 transition-colors cursor-pointer"
              onClick={() => navigate(`/student/research/${p.id}`)}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800 truncate">{p.title}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${STATUS_COLOR[p.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {p.status.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Submitted {new Date(p.created_at).toLocaleDateString()}
                    {p.guide_note && ' · Guide note available'}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-gray-300 flex-shrink-0" />
              </div>
            </div>
          ))}
        </div>
      )}

      {open && <ProposeDialog onClose={() => setOpen(false)} />}
    </div>
  )
}
