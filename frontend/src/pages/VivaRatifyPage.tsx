// M07 Research Supervision — Guide: Viva session detail + conduct + ratify
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Loader2, Video, CheckCircle2, Clock,
  AlertCircle, PlayCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { conductViva, getViva, ratifyViva } from '@/lib/api/research'
import { addToast } from '@/hooks/useToast'
import type { VivaQuestion } from '@/types/research'

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

const STATUS_COLOR: Record<string, string> = {
  SCHEDULED:      'bg-yellow-100 text-yellow-700',
  IN_PROGRESS:    'bg-indigo-100 text-indigo-700',
  COMPLETED:      'bg-blue-100 text-blue-700',
  ASR_PROCESSING: 'bg-purple-100 text-purple-700',
  EVALUATED:      'bg-teal-100 text-teal-700',
  GUIDE_RATIFIED: 'bg-green-100 text-green-700',
}

// ── Conduct panel — appears when status is SCHEDULED ─────────────────────────

function ConductPanel({
  questions,
  vivaId,
  onSuccess,
}: {
  questions: VivaQuestion[]
  vivaId: string
  onSuccess: () => void
}) {
  const [responses, setResponses] = useState<Record<string, string>>(
    () => Object.fromEntries(questions.map((q) => [q.id, '']))
  )

  const { mutate: submit, isPending } = useMutation({
    mutationFn: () =>
      conductViva(vivaId, {
        responses: questions.map((q) => ({
          question_id:   q.id,
          response_text: responses[q.id] || '',
        })),
      }),
    onSuccess: () => {
      addToast('Viva submitted — AI evaluation queued.', 'success')
      onSuccess()
    },
    onError: () => addToast('Failed to submit viva responses.', 'error'),
  })

  const allFilled = questions.every((q) => (responses[q.id] || '').trim().length > 0)

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 flex items-start gap-2">
        <PlayCircle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-800">
          Conduct the viva in person or via call, then enter the student&apos;s responses below.
          Submitting will trigger AI evaluation automatically.
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden divide-y divide-gray-100">
        <div className="px-5 py-3 bg-gray-50">
          <span className="text-sm font-semibold text-gray-700">
            Questions &amp; Responses ({questions.length})
          </span>
        </div>

        {questions.map((q, i) => (
          <div key={q.id} className="px-5 py-4 space-y-2">
            <div className="flex items-start gap-2">
              <span className="flex-shrink-0 h-5 w-5 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600 mt-0.5">
                {i + 1}
              </span>
              <div className="flex-1 space-y-1">
                <p className="text-sm font-medium text-gray-800">{q.text}</p>
                {q.source === 'followup' && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
                    Follow-up
                  </span>
                )}
                <textarea
                  rows={3}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none mt-1"
                  placeholder="Student's response…"
                  value={responses[q.id] || ''}
                  onChange={(e) =>
                    setResponses((prev) => ({ ...prev, [q.id]: e.target.value }))
                  }
                  disabled={isPending}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button
          onClick={() => submit()}
          disabled={isPending || !allFilled}
        >
          {isPending
            ? <><Loader2 className="h-4 w-4 animate-spin mr-1" />Submitting…</>
            : 'Submit Responses & Trigger AI Evaluation'}
        </Button>
        {!allFilled && (
          <p className="text-xs text-gray-600">All responses required before submitting.</p>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function VivaRatifyPage() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const qc        = useQueryClient()

  const [guideScore, setGuideScore] = useState<number>(7)
  const [ratifyNote, setRatifyNote] = useState('')

  const { data: viva, isLoading, isError } = useQuery({
    queryKey: ['viva', id],
    queryFn: () => getViva(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      // Poll while AI is running
      return s === 'COMPLETED' || s === 'ASR_PROCESSING' ? 5000 : false
    },
  })

  const { mutate: ratify, isPending: ratifying } = useMutation({
    mutationFn: () =>
      ratifyViva(id!, {
        overall_guide_score: guideScore,
        ratification_note: ratifyNote || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['viva', id] })
      qc.invalidateQueries({ queryKey: ['research-vivas-guide'] })
      addToast('Viva ratified.', 'success')
    },
    onError: () => addToast('Failed to ratify viva.', 'error'),
  })

  // ── loading ────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }
  if (isError || !viva) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 flex gap-3 text-red-700">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <p className="text-sm">Failed to load viva session.</p>
        </div>
      </div>
    )
  }

  // ── derived state ──────────────────────────────────────────────────────────

  const questions: VivaQuestion[] = viva.ai_questions ?? []
  const responses = viva.ai_responses ?? []
  const answered  = new Set(responses.map((r) => r.question_id))
  const eval_     = viva.ai_evaluation as {
    per_question: Array<{ question_id: string; coherence: number; accuracy: number; depth: number; comment: string }> | null
    overall_score?: number
    summary?: string
    /** Set by the worker when no AI advisory could be produced (e.g. ASR not
     *  configured). The viva is still EVALUATED and fully ratifiable — the
     *  guide simply evaluates without an AI second opinion. */
    unavailable?: boolean
    reason?: string
  } | null

  // An advisory exists only when the AI actually produced per-question scores.
  const aiUnavailable = Boolean(eval_?.unavailable) || !eval_?.per_question
  const hasAiEval     = Boolean(eval_) && !aiUnavailable

  const isScheduled    = viva.status === 'SCHEDULED'
  const isProcessing   = viva.status === 'COMPLETED' || viva.status === 'ASR_PROCESSING'
  const canRatify      = viva.status === 'EVALUATED'
  const isRatified     = viva.status === 'GUIDE_RATIFIED'

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Back */}
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      {/* Title */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <Video className="h-5 w-5 text-gray-600 shrink-0" />
          <h1 className="text-xl font-bold text-gray-900">Viva Session</h1>
          <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${STATUS_COLOR[viva.status] ?? 'bg-gray-100 text-gray-600'}`}>
            {viva.status.replace(/_/g, ' ')}
          </span>
        </div>
        <div className="text-xs text-gray-600 text-right">
          <p>Scheduled {fmt(viva.scheduled_at)}</p>
          {viva.completed_at && <p>Completed {fmt(viva.completed_at)}</p>}
          {viva.ratified_at  && <p>Ratified {fmt(viva.ratified_at)}</p>}
        </div>
      </div>

      {/* Meta cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Questions</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">{questions.length}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Answered</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">{answered.size} / {questions.length}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">AI Score</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">
            {hasAiEval && eval_?.overall_score != null
              ? `${eval_.overall_score.toFixed(1)} / 10`
              : aiUnavailable ? 'Unavailable' : '—'}
          </p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Guide Score</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">
            {viva.overall_guide_score != null ? `${viva.overall_guide_score} / 10` : '—'}
          </p>
        </div>
      </div>

      {/* ── SCHEDULED: conduct form ─────────────────────────────────────────── */}
      {isScheduled && questions.length > 0 && (
        <ConductPanel
          questions={questions}
          vivaId={id!}
          onSuccess={() => qc.invalidateQueries({ queryKey: ['viva', id] })}
        />
      )}

      {isScheduled && questions.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-600">
          Viva questions are still being generated. Refresh in a moment.
        </div>
      )}

      {/* ── COMPLETED / ASR_PROCESSING: waiting for AI ──────────────────────── */}
      {isProcessing && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-5 py-5 flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-800">AI evaluation in progress</p>
            <p className="text-xs text-blue-600 mt-0.5">
              This page refreshes automatically. It usually takes under a minute.
            </p>
          </div>
        </div>
      )}

      {/* ── Q&A transcript (visible once responses exist) ────────────────────── */}
      {responses.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
            <span className="text-sm font-semibold text-gray-700">Q&amp;A Transcript</span>
          </div>
          <div className="divide-y divide-gray-100">
            {questions.map((q, i) => {
              const resp = responses.find((r) => r.question_id === q.id)
              return (
                <div key={q.id} className="px-5 py-4 space-y-1">
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0 h-5 w-5 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-500 mt-0.5">
                      {i + 1}
                    </span>
                    <div className="space-y-1 flex-1">
                      <p className="text-sm font-medium text-gray-800">{q.text}</p>
                      {resp ? (
                        <p className="text-sm text-gray-600 whitespace-pre-wrap">{resp.response_text}</p>
                      ) : (
                        <p className="text-xs text-gray-600 italic">No response recorded.</p>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── AI advisory unavailable ──────────────────────────────────────────
          No AI second opinion was produced. The viva is unaffected: the guide's
          evaluation below is, and always was, the authoritative one. */}
      {eval_ && aiUnavailable && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          <p className="text-sm font-medium text-amber-800">
            AI viva evaluation unavailable. Please complete the guide evaluation manually.
          </p>
          <p className="text-xs text-amber-700 mt-1">
            The student&apos;s responses are recorded above and ready for your review.
            Your evaluation is the authoritative one.
          </p>
          {eval_.reason && (
            <p className="text-[11px] text-amber-600 mt-1.5">Reason: {eval_.reason}</p>
          )}
        </div>
      )}

      {/* ── AI Evaluation (visible once EVALUATED or GUIDE_RATIFIED) ────────── */}
      {hasAiEval && eval_ && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-700">AI Evaluation</span>
            <span className="text-sm font-bold text-gray-900">
              {(eval_.overall_score ?? 0).toFixed(1)} / 10
            </span>
          </div>
          <div className="divide-y divide-gray-100">
            {(eval_.per_question ?? []).map((q, i) => (
              <div key={q.question_id} className="px-5 py-3 space-y-0.5">
                <p className="text-xs font-medium text-gray-500">Q{i + 1}</p>
                <div className="flex gap-4 text-sm">
                  <span className="text-gray-500">Coherence: <strong>{q.coherence}</strong></span>
                  <span className="text-gray-500">Accuracy: <strong>{q.accuracy}</strong></span>
                  <span className="text-gray-500">Depth: <strong>{q.depth}</strong></span>
                </div>
                {q.comment && <p className="text-xs text-gray-500 italic">{q.comment}</p>}
              </div>
            ))}
          </div>
          {eval_.summary && (
            <div className="px-5 py-4 border-t border-gray-100 bg-blue-50">
              <p className="text-xs font-medium text-blue-600">AI Summary</p>
              <p className="text-sm text-blue-900 mt-0.5">{eval_.summary}</p>
            </div>
          )}
        </div>
      )}

      {/* ── EVALUATED: ratification form — HUMAN GATE 3 ─────────────────────── */}
      {canRatify && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-teal-500 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-700">Ratify — Human Gate 3</h2>
          </div>
          <p className="text-xs text-gray-500">
            AI scores are advisory only. Enter your final score to ratify the viva.
          </p>

          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Your overall score (0–10)</label>
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
            <label className="text-sm font-medium text-gray-700">
              Ratification note <span className="text-gray-600 font-normal">(optional)</span>
            </label>
            <textarea
              rows={3}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
              value={ratifyNote}
              onChange={(e) => setRatifyNote(e.target.value)}
              placeholder="Overall assessment of the viva performance…"
            />
          </div>

          <Button onClick={() => ratify()} disabled={ratifying}>
            {ratifying ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Ratify Viva
          </Button>
        </div>
      )}

      {/* ── GUIDE_RATIFIED: final result ─────────────────────────────────────── */}
      {isRatified && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-5 space-y-1">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
            <p className="text-sm font-semibold text-green-800">Viva ratified</p>
          </div>
          <p className="text-2xl font-bold text-gray-900 pl-7">
            {viva.overall_guide_score} / 10
          </p>
          {viva.ratified_at && (
            <p className="text-xs text-gray-600 pl-7">Ratified {fmt(viva.ratified_at)}</p>
          )}
        </div>
      )}

      {/* ── Catch-all for unexpected status (guard, shouldn't appear) ───────── */}
      {!isScheduled && !isProcessing && !canRatify && !isRatified && (
        <div className="rounded-xl border border-dashed border-gray-200 p-5 text-center text-sm text-gray-600">
          <Clock className="h-4 w-4 mx-auto mb-1" />
          Status: {viva.status.replace(/_/g, ' ')} — waiting for next step.
        </div>
      )}

    </div>
  )
}
