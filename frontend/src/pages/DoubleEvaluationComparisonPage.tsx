// M09 Paper Administration — Board: double evaluation comparison + adjust page (M09.1)
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  GitCompareArrows, ChevronLeft, Loader2, AlertTriangle,
  CheckCircle2, Info, Save,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getBoardComparison, boardAdjustMarks, boardFinalise } from '@/lib/api/scripts'
import type { BoardAdjustRequest, ScriptEvaluation } from '@/types/script'

// ---------------------------------------------------------------------------
// Per-question comparison row
// ---------------------------------------------------------------------------

function ComparisonRow({
  primary,
  secondary,
  adjustedMarks,
  onAdjust,
}: {
  primary:       ScriptEvaluation
  secondary?:    ScriptEvaluation
  adjustedMarks: number | ''
  onAdjust:      (val: number | '') => void
}) {
  return (
    <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr] gap-2 items-center rounded-lg border border-gray-100 bg-white px-3 py-2 text-xs">
      {/* Question info */}
      <div className="min-w-0">
        <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded-full font-medium">
          {primary.question_type.replace('_', ' ')}
        </span>
        <span className="ml-2 font-mono text-gray-600 text-[10px] truncate">
          {primary.question_id.slice(0, 8)}…
        </span>
      </div>

      {/* Primary evaluator marks */}
      <div className="text-center">
        <span className={`font-semibold ${primary.evaluator_marks != null ? 'text-indigo-700' : 'text-red-400'}`}>
          {primary.evaluator_marks ?? '—'}
        </span>
        <span className="text-gray-600"> / {primary.max_marks}</span>
      </div>

      {/* Secondary evaluator marks */}
      <div className="text-center">
        {secondary ? (
          <>
            <span className={`font-semibold ${secondary.evaluator_marks != null ? 'text-purple-700' : 'text-gray-600'}`}>
              {secondary.evaluator_marks ?? '—'}
            </span>
            <span className="text-gray-600"> / {secondary.max_marks}</span>
          </>
        ) : (
          <span className="text-gray-500">—</span>
        )}
      </div>

      {/* Discrepancy */}
      <div className="text-center">
        {primary.evaluator_marks != null && secondary?.evaluator_marks != null ? (
          <span className={`font-medium ${
            Math.abs(primary.evaluator_marks - secondary.evaluator_marks) > 0
              ? 'text-orange-600'
              : 'text-emerald-600'
          }`}>
            {(primary.evaluator_marks - secondary.evaluator_marks).toFixed(1)}
          </span>
        ) : (
          <span className="text-gray-500">—</span>
        )}
      </div>

      {/* Board adjusted marks input */}
      <div className="flex items-center gap-1">
        <input
          type="number"
          min={0}
          max={primary.max_marks}
          step={0.5}
          value={adjustedMarks}
          onChange={e => onAdjust(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder="Board mark"
          className="w-full border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
        />
        <span className="text-gray-600 shrink-0">/{primary.max_marks}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DoubleEvaluationComparisonPage() {
  const { scriptId } = useParams<{ scriptId: string }>()
  const navigate     = useNavigate()
  const qc           = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['board-comparison', scriptId],
    queryFn:  () => getBoardComparison(scriptId!),
    enabled:  !!scriptId,
  })

  // adjustments[questionId] = board mark entered by user
  const [adjustments, setAdjustments] = useState<Record<string, number | ''>>({})
  const [adjustError,  setAdjustError]  = useState<string | null>(null)
  const [finaliseNote, setFinaliseNote] = useState('')
  const [confirmOpen,  setConfirmOpen]  = useState(false)
  const [finaliseError, setFinaliseError] = useState<string | null>(null)

  const adjustMut = useMutation({
    mutationFn: () => {
      const payload: BoardAdjustRequest = {
        adjustments: Object.fromEntries(
          Object.entries(adjustments)
            .filter(([, v]) => v !== '')
            .map(([qid, v]) => [qid, { board_adjusted_marks: v as number }])
        ),
      }
      return boardAdjustMarks(scriptId!, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['board-comparison', scriptId] })
      setAdjustError(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setAdjustError(msg ?? 'Failed to save board adjustments.')
    },
  })

  const finaliseMut = useMutation({
    mutationFn: () => boardFinalise(scriptId!, { finalisation_note: finaliseNote.trim() || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['board-pending'] })
      navigate('/scripts/board')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setFinaliseError(msg ?? 'Finalisation failed.')
    },
  })

  const allAdjustmentsEntered = data
    ? data.primary_evaluations.every(e => adjustments[e.question_id] !== undefined && adjustments[e.question_id] !== '')
    : false

  const savedAdjustmentsComplete = data?.board_adjustments_set ?? false

  if (isLoading) return (
    <div className="flex items-center justify-center h-64 gap-2 text-gray-600">
      <Loader2 className="w-5 h-5 animate-spin" />
      Loading comparison view…
    </div>
  )

  if (isError || !data) return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-600">
        Failed to load comparison view. The script may not be in MARKS_SUBMITTED status.
      </div>
    </div>
  )

  // Build secondary map keyed by question_id for O(1) lookup
  const secondaryByQuestion = Object.fromEntries(
    data.secondary_evaluations.map(e => [e.question_id, e])
  )

  const discrepancyCount = data.primary_evaluations.filter(e => {
    const sec = secondaryByQuestion[e.question_id]
    return (
      e.evaluator_marks != null &&
      sec?.evaluator_marks != null &&
      Math.abs(e.evaluator_marks - sec.evaluator_marks) > 0
    )
  }).length

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/scripts/board')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <GitCompareArrows className="w-6 h-6 text-purple-600" />
          <h1 className="text-2xl font-bold text-gray-900">Double Evaluation Comparison</h1>
        </div>
        <span className="font-mono text-sm text-gray-600 ml-2">{data.masked_id}</span>
      </div>

      {/* Advisory */}
      <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 flex gap-3 text-sm text-purple-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-purple-600" />
        <div className="space-y-1">
          <p><strong>Board Gate 2 — Double Evaluation Review.</strong></p>
          <p>
            Two evaluators have independently scored this script.
            Review both sets of marks and enter your Board-approved mark for each question.
            <strong> No automatic averaging is applied — every mark must be set explicitly.</strong>
          </p>
        </div>
      </div>

      {/* Totals summary */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-center">
          <div className="text-xl font-bold text-indigo-700">{data.primary_total.toFixed(1)}</div>
          <div className="text-xs text-indigo-500">Primary total</div>
        </div>
        <div className="rounded-xl border border-purple-100 bg-purple-50 p-3 text-center">
          <div className="text-xl font-bold text-purple-700">{data.secondary_total.toFixed(1)}</div>
          <div className="text-xs text-purple-500">Secondary total</div>
        </div>
        <div className="rounded-xl border border-orange-100 bg-orange-50 p-3 text-center">
          <div className="text-xl font-bold text-orange-700">{discrepancyCount}</div>
          <div className="text-xs text-orange-500">Questions with discrepancy</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 text-center">
          <div className="text-xl font-bold text-gray-700">{data.max_marks_total}</div>
          <div className="text-xs text-gray-500">Max marks</div>
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr] gap-2 px-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
        <div>Question</div>
        <div className="text-center text-indigo-600">Primary</div>
        <div className="text-center text-purple-600">Secondary</div>
        <div className="text-center text-orange-600">Diff</div>
        <div className="text-center text-emerald-600">Board Mark</div>
      </div>

      {/* Question rows */}
      <div className="space-y-1">
        {data.primary_evaluations.map(ev => (
          <ComparisonRow
            key={ev.question_id}
            primary={ev}
            secondary={secondaryByQuestion[ev.question_id]}
            adjustedMarks={adjustments[ev.question_id] ?? (ev.board_adjusted_marks ?? '')}
            onAdjust={val => setAdjustments(prev => ({ ...prev, [ev.question_id]: val }))}
          />
        ))}
      </div>

      {/* Save adjustments */}
      {adjustError && (
        <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {adjustError}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button
          onClick={() => adjustMut.mutate()}
          disabled={adjustMut.isPending || !allAdjustmentsEntered}
          className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          {adjustMut.isPending
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <Save className="w-4 h-4" />}
          Save Board Adjustments
        </Button>
        {savedAdjustmentsComplete && (
          <span className="text-xs text-emerald-600 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            All adjustments saved
          </span>
        )}
        {!allAdjustmentsEntered && (
          <span className="text-xs text-gray-600">
            Enter a Board mark for every question to enable save.
          </span>
        )}
      </div>

      {/* Finalise */}
      {savedAdjustmentsComplete && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 space-y-4">
          <div className="flex items-center gap-2 text-emerald-800 font-semibold">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            Board adjustments complete — ready to finalise
          </div>

          <div className="rounded-lg border border-orange-200 bg-orange-50 p-3 flex gap-2 text-xs text-orange-800">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-orange-600" />
            <span>
              <strong>Gate 2 is irreversible.</strong> Finalising writes an append-only score ledger
              entry and reveals student identity. The official score uses your Board-adjusted marks
              (COALESCE with evaluator marks where not adjusted).
            </span>
          </div>

          {!confirmOpen ? (
            <div className="space-y-2">
              <input
                type="text"
                value={finaliseNote}
                onChange={e => setFinaliseNote(e.target.value)}
                placeholder="Board finalisation note (optional)…"
                className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
              />
              <Button
                onClick={() => setConfirmOpen(true)}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
              >
                <CheckCircle2 className="w-4 h-4" />
                Finalise Script (Gate 2)
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-emerald-800">
                Confirm: finalise script <span className="font-mono">{data.masked_id}</span>?
              </p>
              {finaliseError && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  {finaliseError}
                </div>
              )}
              <div className="flex gap-2">
                <Button
                  onClick={() => { setFinaliseError(null); finaliseMut.mutate() }}
                  disabled={finaliseMut.isPending}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
                >
                  {finaliseMut.isPending
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <CheckCircle2 className="w-3.5 h-3.5" />}
                  Yes, finalise
                </Button>
                <Button
                  variant="outline"
                  onClick={() => { setConfirmOpen(false); setFinaliseError(null) }}
                  disabled={finaliseMut.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
