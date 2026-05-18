// M09 Paper Administration — Board Gate 2: review and finalise submitted scripts
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardCheck, ChevronLeft, Loader2, AlertTriangle, CheckCircle2, Info,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  listBoardPending,
  getEvaluations,
  boardFinalise,
} from '@/lib/api/scripts'
import type {
  ScannedScript,
  ScriptEvaluation,
  BoardFinaliseResponse,
} from '@/types/script'

// ---------------------------------------------------------------------------
// Sub-panel: evaluation summary for one script
// ---------------------------------------------------------------------------

function ScriptEvalSummary({
  scriptId,
}: {
  scriptId: string
}) {
  const { data: evals, isLoading } = useQuery({
    queryKey: ['script-evals', scriptId],
    queryFn:  () => getEvaluations(scriptId),
  })

  if (isLoading) return (
    <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
      <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading evaluations…
    </div>
  )

  if (!evals || evals.length === 0) return (
    <p className="text-xs text-gray-400 py-2">No evaluation rows found.</p>
  )

  const totalEvaluator = evals.reduce((s, e) => s + (e.evaluator_marks ?? 0), 0)
  const totalAI        = evals.reduce((s, e) => s + (e.ai_suggested_marks ?? 0), 0)
  const maxTotal       = evals.reduce((s, e) => s + e.max_marks, 0)

  return (
    <div className="space-y-3 mt-3">
      {/* Totals row */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg bg-indigo-50 border border-indigo-100 p-2 text-center">
          <div className="font-semibold text-indigo-700 text-base">{totalEvaluator.toFixed(1)}</div>
          <div className="text-indigo-500">Evaluator total</div>
        </div>
        <div className="rounded-lg bg-blue-50 border border-blue-100 p-2 text-center">
          <div className="font-semibold text-blue-700 text-base">{totalAI.toFixed(1)}</div>
          <div className="text-blue-500">AI suggested</div>
        </div>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-2 text-center">
          <div className="font-semibold text-gray-700 text-base">{maxTotal}</div>
          <div className="text-gray-500">Max marks</div>
        </div>
      </div>

      {/* Question breakdown */}
      <div className="space-y-1">
        {evals.map(ev => (
          <EvalSummaryRow key={ev.id} ev={ev} />
        ))}
      </div>
    </div>
  )
}

function EvalSummaryRow({ ev }: { ev: ScriptEvaluation }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-100 bg-white px-3 py-2 text-xs">
      <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded-full font-medium shrink-0">
        {ev.question_type.replace('_', ' ')}
      </span>
      <span className="font-mono text-gray-400 truncate flex-1">{ev.question_id}</span>
      <span className="text-blue-500 shrink-0">AI: {ev.ai_suggested_marks ?? '—'}</span>
      <span className={`shrink-0 font-semibold ${ev.evaluator_marks != null ? 'text-indigo-700' : 'text-red-500'}`}>
        Eval: {ev.evaluator_marks ?? 'missing'}
      </span>
      <span className="text-gray-400 shrink-0">/ {ev.max_marks}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Script review card (expandable)
// ---------------------------------------------------------------------------

function BoardScriptCard({
  script,
  onFinalised,
}: {
  script:      ScannedScript
  onFinalised: (result: BoardFinaliseResponse) => void
}) {
  const [expanded,         setExpanded]         = useState(false)
  const [note,             setNote]             = useState('')
  const [confirmVisible,   setConfirmVisible]   = useState(false)
  const [finaliseError,    setFinaliseError]    = useState<string | null>(null)
  const qc = useQueryClient()

  const finaliseMut = useMutation({
    mutationFn: () => boardFinalise(script.id, { finalisation_note: note.trim() || undefined }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['board-pending'] })
      onFinalised(data)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setFinaliseError(msg ?? 'Finalisation failed.')
    },
  })

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header row */}
      <div
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-sm text-gray-800">{script.masked_id}</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700">
              MARKS SUBMITTED
            </span>
          </div>
          <p className="text-xs text-gray-500 truncate">
            Paper: <span className="font-mono">{script.exam_paper_id}</span>
          </p>
          {script.submitted_at && (
            <p className="text-xs text-gray-400">
              Submitted: {new Date(script.submitted_at).toLocaleString()}
            </p>
          )}
        </div>
        <span className="text-xs text-indigo-500 shrink-0">{expanded ? 'Collapse ▲' : 'Review ▼'}</span>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 p-4 space-y-4">
          <ScriptEvalSummary scriptId={script.id} />

          {/* Identity reveal warning */}
          <div className="rounded-lg border border-orange-200 bg-orange-50 p-3 flex gap-2 text-xs text-orange-800">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-orange-600" />
            <span>
              <strong>Board Gate 2 is irreversible.</strong> Finalising writes an append-only score ledger
              entry and reveals student identity. Marks cannot be changed after this step.
            </span>
          </div>

          {/* Evaluator marks are read-only here — board only finalises */}
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-3 flex gap-2 text-xs text-blue-800">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-blue-500" />
            <span>Evaluator marks shown above are final. The Board cannot edit them here.</span>
          </div>

          {/* Finalisation note */}
          {!confirmVisible && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">
                Finalisation note (optional)
              </label>
              <input
                type="text"
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="Board remarks or justification…"
                className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
              />
            </div>
          )}

          {/* Confirm step */}
          {confirmVisible ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 space-y-3">
              <p className="text-sm font-semibold text-emerald-800">
                Confirm: finalise script <span className="font-mono">{script.masked_id}</span>?
              </p>
              <p className="text-xs text-emerald-700">
                This will record the score ledger entry and reveal student identity. Cannot be undone.
              </p>

              {finaliseError && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  {finaliseError}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  size="sm"
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
                  size="sm"
                  variant="outline"
                  onClick={() => { setConfirmVisible(false); setFinaliseError(null) }}
                  disabled={finaliseMut.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              onClick={() => setConfirmVisible(true)}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              Finalise Script (Gate 2)
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Finalised result banner
// ---------------------------------------------------------------------------

function FinalisedBanner({ result }: { result: BoardFinaliseResponse }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 space-y-3">
      <div className="flex items-center gap-2 text-emerald-700 font-semibold">
        <CheckCircle2 className="w-5 h-5" />
        Script finalised — score ledger recorded
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-emerald-800">
        <p><span className="font-medium">Masked ID:</span> <span className="font-mono">{result.script.masked_id}</span></p>
        <p><span className="font-medium">Status:</span> {result.script.status}</p>
        <p><span className="font-medium">Total marks:</span> {result.ledger.total_marks} / {result.ledger.max_marks}</p>
        <p><span className="font-medium">Ledger ID:</span> <span className="font-mono text-xs">{result.ledger.id}</span></p>
        {result.script.student_roll_ref && (
          <p className="col-span-2"><span className="font-medium">Roll:</span> {result.script.student_roll_ref}</p>
        )}
        {result.script.student_user_id && (
          <p className="col-span-2"><span className="font-medium">Student ID:</span> <span className="font-mono">{result.script.student_user_id}</span></p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BoardScriptReviewPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const limit = 10
  const [lastFinalised, setLastFinalised] = useState<BoardFinaliseResponse | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['board-pending', offset],
    queryFn:  () => listBoardPending({ offset, limit }),
  })

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <ClipboardCheck className="w-6 h-6 text-emerald-600" />
          <h1 className="text-2xl font-bold text-gray-900">Board Script Review</h1>
        </div>
      </div>

      {/* Board advisory */}
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex gap-3 text-sm text-emerald-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-emerald-600" />
        <span>
          <strong>Gate 2 — Board Finalisation.</strong> Review evaluator marks for each submitted script.
          Finalising an entry writes an immutable score ledger record and reveals student identity.
          This action cannot be undone.
        </span>
      </div>

      {/* Last finalised banner */}
      {lastFinalised && (
        <FinalisedBanner result={lastFinalised} />
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading pending scripts…
        </div>
      )}

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-600">
          Failed to load pending scripts. Please try again.
        </div>
      )}

      {data && (
        <>
          {data.items.length === 0 && !lastFinalised && (
            <div className="text-gray-500 text-center py-12">
              No scripts pending Board finalisation.
            </div>
          )}

          <div className="space-y-3">
            {data.items.map(script => (
              <BoardScriptCard
                key={script.id}
                script={script}
                onFinalised={setLastFinalised}
              />
            ))}
          </div>

          {data.total > limit && (
            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-500">
                Showing {Math.min(offset + 1, data.total)}–{Math.min(offset + limit, data.total)} of {data.total}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + limit >= data.total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
