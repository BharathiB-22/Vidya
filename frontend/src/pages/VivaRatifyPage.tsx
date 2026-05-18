// M07 Research Supervision — Guide: Viva ratification (Human Gate 3)
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Loader2, Video } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getViva, ratifyViva } from '@/lib/api/research'

export default function VivaRatifyPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()

  const [guideScore, setGuideScore]   = useState<number>(7)
  const [ratifyNote, setRatifyNote]   = useState('')

  const { data: viva, isLoading, isError } = useQuery({
    queryKey: ['viva', id],
    queryFn: () => getViva(id!),
    enabled: !!id,
  })

  const { mutate: ratify, isPending } = useMutation({
    mutationFn: () =>
      ratifyViva(id!, {
        overall_guide_score: guideScore,
        ratification_note: ratifyNote || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['viva', id] })
      qc.invalidateQueries({ queryKey: ['vivas-guide'] })
    },
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
    </div>
  )
  if (isError || !viva) return (
    <div className="max-w-4xl mx-auto px-4 py-8 text-red-600 text-sm">
      Failed to load viva session.
    </div>
  )

  const canRatify  = viva.status === 'EVALUATED'
  const isRatified = viva.status === 'GUIDE_RATIFIED'
  const eval_     = viva.ai_evaluation

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Video className="h-5 w-5 text-gray-400" />
            <h1 className="text-xl font-bold text-gray-900">Viva Session Review</h1>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              isRatified ? 'bg-green-100 text-green-700' :
              viva.status === 'EVALUATED' ? 'bg-blue-100 text-blue-700' :
              viva.status === 'SCHEDULED' ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {viva.status.replace('_', ' ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Scheduled {new Date(viva.scheduled_at).toLocaleDateString()}
            {viva.completed_at && ` · Completed ${new Date(viva.completed_at).toLocaleDateString()}`}
          </p>
        </div>
      </div>

      {/* AI Q&A + Evaluation */}
      {eval_ && (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
          <div className="px-5 py-4 flex items-center justify-between bg-gray-50">
            <span className="text-sm font-semibold text-gray-700">AI Evaluation</span>
            <span className="text-sm font-bold text-gray-900">
              Overall: {eval_.overall_score.toFixed(1)} / 10
            </span>
          </div>

          {eval_.per_question.map((q, i) => (
            <div key={q.question_id} className="px-5 py-4 space-y-1">
              <p className="text-xs font-medium text-gray-500">Q{i + 1}</p>
              <div className="flex gap-4 text-sm">
                <span className="text-gray-500">Coherence: <strong>{q.coherence}</strong></span>
                <span className="text-gray-500">Accuracy: <strong>{q.accuracy}</strong></span>
                <span className="text-gray-500">Depth: <strong>{q.depth}</strong></span>
              </div>
              {q.comment && <p className="text-xs text-gray-500 italic">{q.comment}</p>}
            </div>
          ))}

          {eval_.summary && (
            <div className="px-5 py-4 bg-blue-50">
              <p className="text-xs font-medium text-blue-600">AI Summary</p>
              <p className="text-sm text-blue-900 mt-0.5">{eval_.summary}</p>
            </div>
          )}
        </div>
      )}

      {/* Session info */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-400">Questions answered</p>
          <p className="text-lg font-bold text-gray-900 mt-1">
            {viva.ai_responses?.length ?? 0} / {viva.ai_questions?.length ?? 0}
          </p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-400">AI overall score</p>
          <p className="text-lg font-bold text-gray-900 mt-1">
            {eval_ ? `${eval_.overall_score.toFixed(1)} / 10` : '—'}
          </p>
        </div>
      </div>

      {/* Ratification panel */}
      {isRatified ? (
        <div className="rounded-xl border border-green-200 bg-green-50 p-5 space-y-1">
          <p className="text-sm font-semibold text-green-700">Viva ratified</p>
          <p className="text-lg font-bold text-gray-900">
            Guide score: {viva.overall_guide_score} / 10
          </p>
          {viva.ratified_at && (
            <p className="text-xs text-gray-400">
              Ratified {new Date(viva.ratified_at).toLocaleDateString()}
            </p>
          )}
        </div>
      ) : canRatify ? (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">
            Ratify — Human Gate 3
          </h2>
          <p className="text-xs text-gray-500">
            AI scores are advisory only. Enter your final score to ratify.
          </p>

          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">
              Your overall score (0–10)
            </label>
            <input
              type="number"
              min={0}
              max={10}
              step={0.5}
              className="w-32 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={guideScore}
              onChange={(e) => setGuideScore(Number(e.target.value))}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Ratification note (optional)</label>
            <textarea
              rows={3}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
              value={ratifyNote}
              onChange={(e) => setRatifyNote(e.target.value)}
              placeholder="Overall assessment of the viva performance…"
            />
          </div>

          <Button onClick={() => ratify()} disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Ratify Viva
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-200 p-5 text-center text-sm text-gray-400">
          Viva not yet ready for ratification (status: {viva.status}).
        </div>
      )}
    </div>
  )
}
