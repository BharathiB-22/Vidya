// M09 Paper Administration — Evaluator: per-question marks entry panel
import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Save, Send, Loader2, AlertTriangle, Info, CheckCircle2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getScript,
  getEvaluations,
  updateMarks,
  submitMarks,
} from '@/lib/api/scripts'
import type {
  ScriptEvaluation,
  EvaluatorMarkUpdate,
  MarksMap,
  ScriptSubmitMarksPayload,
} from '@/types/script'

// ---------------------------------------------------------------------------
// Evaluation row
// ---------------------------------------------------------------------------

function EvalRow({
  ev,
  mark,
  note,
  onChange,
  readOnly,
}: {
  ev:       ScriptEvaluation
  mark:     number | ''
  note:     string
  onChange: (m: number | '', n: string) => void
  readOnly: boolean
}) {
  return (
    <div className="border border-gray-100 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 flex-1 min-w-0">
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs font-semibold px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
              {ev.question_type.replace('_', ' ')}
            </span>
            <span className="text-xs text-gray-400 font-mono truncate">{ev.question_id}</span>
          </div>
        </div>
        <span className="text-xs text-gray-500 shrink-0">/ {ev.max_marks} marks</span>
      </div>

      {/* AI suggestion */}
      {ev.ai_suggested_marks != null ? (
        <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 space-y-1">
          <div className="flex items-center gap-2">
            <Info className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-xs font-semibold text-blue-700">AI Suggestion</span>
            <span className="text-sm font-bold text-blue-900 ml-auto">{ev.ai_suggested_marks}</span>
          </div>
          {ev.ai_justification && (
            <p className="text-xs text-blue-700 leading-relaxed">{ev.ai_justification}</p>
          )}
          {ev.ai_model && (
            <p className="text-xs text-blue-400">Model: {ev.ai_model}</p>
          )}
        </div>
      ) : (
        <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
          <p className="text-xs text-gray-500">No AI suggestion — evaluator must enter marks manually.</p>
        </div>
      )}

      {/* Human marks input */}
      <div className="flex gap-3 items-start">
        <div className="w-28 shrink-0 space-y-1">
          <label className="text-xs font-medium text-gray-600">
            Your marks {readOnly ? '' : <span className="text-red-400">*</span>}
          </label>
          <input
            type="number"
            min={0}
            max={ev.max_marks}
            step={0.5}
            value={mark}
            onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value), note)}
            disabled={readOnly}
            className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50"
          />
        </div>
        <div className="flex-1 space-y-1">
          <label className="text-xs font-medium text-gray-600">Note (optional)</label>
          <input
            type="text"
            value={note}
            onChange={e => onChange(mark, e.target.value)}
            placeholder="Add evaluator note…"
            disabled={readOnly}
            className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50"
          />
        </div>
      </div>

      {ev.final_marks != null && (
        <div className="flex items-center gap-1.5 text-xs text-emerald-600">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Final marks: <strong>{ev.final_marks}</strong> (Board finalised)
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ScriptEvaluationPanel() {
  const { scriptId } = useParams<{ scriptId: string }>()
  const navigate     = useNavigate()
  const qc           = useQueryClient()

  // Local marks state: question_id → {mark, note}
  const [localMarks, setLocalMarks] = useState<Record<string, { mark: number | ''; note: string }>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  const { data: script, isLoading: scriptLoading } = useQuery({
    queryKey: ['script', scriptId],
    queryFn:  () => getScript(scriptId!),
  })

  const { data: evals, isLoading: evalsLoading } = useQuery({
    queryKey: ['script-evals', scriptId],
    queryFn:  () => getEvaluations(scriptId!),
    enabled:  !!script,
  })

  // Seed local marks from loaded evaluations
  useEffect(() => {
    if (!evals) return
    setLocalMarks(prev => {
      const next = { ...prev }
      for (const ev of evals) {
        if (!(ev.question_id in next)) {
          next[ev.question_id] = {
            mark: ev.evaluator_marks ?? '',
            note: ev.evaluator_note ?? '',
          }
        }
      }
      return next
    })
  }, [evals])

  const saveMut = useMutation({
    mutationFn: () => {
      const marks: MarksMap = {}
      for (const [qid, { mark, note }] of Object.entries(localMarks)) {
        if (mark !== '') {
          const entry: EvaluatorMarkUpdate = { evaluator_marks: Number(mark) }
          if (note) entry.evaluator_note = note
          marks[qid] = entry
        }
      }
      return updateMarks(scriptId!, { marks })
    },
    onSuccess: () => {
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
      qc.invalidateQueries({ queryKey: ['script-evals', scriptId] })
    },
  })

  const submitMut = useMutation({
    mutationFn: () => {
      const marks: MarksMap = {}
      for (const [qid, { mark, note }] of Object.entries(localMarks)) {
        if (mark !== '') {
          const entry: EvaluatorMarkUpdate = { evaluator_marks: Number(mark) }
          if (note) entry.evaluator_note = note
          marks[qid] = entry
        }
      }
      const payload: ScriptSubmitMarksPayload = { marks }
      return submitMarks(scriptId!, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['script', scriptId] })
      navigate('/scripts')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setSubmitError(msg ?? 'Submission failed.')
    },
  })

  function handleSubmit() {
    setSubmitError(null)
    if (!evals) return
    // Validate all questions have a mark
    const missing = evals.filter(ev => {
      const local = localMarks[ev.question_id]
      return !local || local.mark === ''
    })
    if (missing.length > 0) {
      setSubmitError(`Please enter marks for all ${missing.length} remaining question(s) before submitting.`)
      return
    }
    submitMut.mutate()
  }

  const isReadOnly = script
    ? !['SCORED', 'REVIEW_REQUIRED'].includes(script.status)
    : true

  if (scriptLoading || evalsLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading evaluation panel…
      </div>
    )
  }

  if (!script) return <div className="p-8 text-red-600">Script not found.</div>

  const totalAI = evals?.reduce((s, e) => s + (e.ai_suggested_marks ?? 0), 0) ?? 0
  const totalHuman = evals?.reduce((s, e) => {
    const m = localMarks[e.question_id]?.mark
    return s + (m !== '' && m != null ? Number(m) : 0)
  }, 0) ?? 0
  const maxTotal = evals?.reduce((s, e) => s + e.max_marks, 0) ?? 0

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900">
            Evaluation — <span className="font-mono text-indigo-600">{script.masked_id}</span>
          </h1>
          <p className="text-sm text-gray-500">
            Status: <strong>{script.status.replace(/_/g, ' ')}</strong>
          </p>
        </div>
      </div>

      {/* AI advisory notice */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          <strong>AI advises, human decides.</strong> AI-suggested marks are for reference only.
          You must enter your own marks for every question. Your marks are final for Gate 1 submission.
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: script metadata + OCR placeholder */}
        <div className="space-y-4">
          <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-700">Script Info</h3>
            <div className="space-y-1 text-xs text-gray-600">
              <p><span className="font-medium">Masked ID:</span> <span className="font-mono">{script.masked_id}</span></p>
              <p><span className="font-medium">Status:</span> {script.status.replace(/_/g, ' ')}</p>
              {script.objective_auto_score != null && (
                <p><span className="font-medium">MCQ Auto-score:</span> {script.objective_auto_score}</p>
              )}
              {script.ocr_status && (
                <p><span className="font-medium">OCR Status:</span> {script.ocr_status}</p>
              )}
            </div>

            {script.upload_url ? (
              <a
                href={script.upload_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-xs text-indigo-600 underline break-all"
              >
                View uploaded scan
              </a>
            ) : (
              <div className="rounded-lg bg-gray-50 border border-dashed border-gray-200 p-4 text-center text-xs text-gray-400">
                No scan uploaded
              </div>
            )}
          </div>

          {/* Score summary */}
          <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-2">
            <h3 className="text-sm font-semibold text-gray-700">Score Summary</h3>
            <div className="space-y-1 text-xs text-gray-600">
              <div className="flex justify-between">
                <span>AI total (suggested)</span>
                <span className="font-mono text-blue-600">{totalAI.toFixed(1)} / {maxTotal}</span>
              </div>
              <div className="flex justify-between font-medium text-gray-800">
                <span>Your marks (current)</span>
                <span className="font-mono text-indigo-700">{totalHuman.toFixed(1)} / {maxTotal}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          {!isReadOnly && (
            <div className="space-y-2">
              <Button
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending}
                variant="outline"
                className="w-full gap-2"
              >
                {saveMut.isPending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : saveSuccess
                  ? <CheckCircle2 className="w-4 h-4 text-green-600" />
                  : <Save className="w-4 h-4" />}
                {saveSuccess ? 'Saved!' : 'Save Marks'}
              </Button>

              {submitError && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {submitError}
                </div>
              )}

              <Button
                onClick={handleSubmit}
                disabled={submitMut.isPending}
                className="w-full bg-yellow-600 hover:bg-yellow-700 text-white gap-2"
              >
                {submitMut.isPending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />}
                Submit All Marks (Gate 1)
              </Button>
              <p className="text-xs text-gray-400 text-center">
                Gate 1 submits marks to the Board for finalisation. You cannot edit after this.
              </p>
            </div>
          )}

          {isReadOnly && (
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-xs text-gray-500 text-center">
              {script.status === 'MARKS_SUBMITTED' && 'Marks submitted — awaiting Board finalisation.'}
              {script.status === 'BOARD_FINALISED' && 'Board finalised — view only.'}
              {['PENDING', 'PROCESSING', 'FAILED'].includes(script.status) && 'Scoring in progress or failed — cannot evaluate yet.'}
            </div>
          )}
        </div>

        {/* Right: question evaluation rows */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Questions ({evals?.length ?? 0})
          </h2>

          {evals && evals.length === 0 && (
            <div className="text-gray-500 text-center py-12">
              No evaluation rows found. The scoring task may still be running.
            </div>
          )}

          {evals && evals.map(ev => (
            <EvalRow
              key={ev.id}
              ev={ev}
              mark={localMarks[ev.question_id]?.mark ?? ''}
              note={localMarks[ev.question_id]?.note ?? ''}
              onChange={(m, n) =>
                setLocalMarks(prev => ({
                  ...prev,
                  [ev.question_id]: { mark: m, note: n },
                }))
              }
              readOnly={isReadOnly}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
