// M09 Paper Administration — Evaluator: enriched review + marks entry panel (H-36 STEP-06)
import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Save, Send, Loader2, AlertTriangle, Info,
  CheckCircle2, CheckCheck, ChevronDown, ChevronUp, Zap,
  FileText, AlertCircle, ExternalLink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getEvaluatorReview,
  getScriptFileUrl,
  updateMarks,
  submitMarks,
  acceptSuggestions,
} from '@/lib/api/scripts'
import type {
  ScriptEvaluation,
  EvaluatorMarkUpdate,
  MarksMap,
  ScriptSubmitMarksPayload,
  KeywordHit,
  RubricItem,
  ScriptStatus,
} from '@/types/script'

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

const STATUS_PIPELINE: ScriptStatus[] = [
  'QUALITY_CHECKING', 'QUALITY_FAILED', 'OCR_PROCESSING',
]

function PipelineStatusBanner({ status }: { status: ScriptStatus }) {
  if (!STATUS_PIPELINE.includes(status)) return null

  const map: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
    QUALITY_CHECKING: {
      label: 'Checking scan quality…',
      icon:  <Loader2 className="w-4 h-4 animate-spin" />,
      cls:   'bg-yellow-50 border-yellow-200 text-yellow-800',
    },
    QUALITY_FAILED: {
      label: 'Scan quality check failed — upload may need replacement.',
      icon:  <AlertCircle className="w-4 h-4" />,
      cls:   'bg-red-50 border-red-200 text-red-800',
    },
    OCR_PROCESSING: {
      label: 'Extracting text from scan (OCR)…',
      icon:  <Loader2 className="w-4 h-4 animate-spin" />,
      cls:   'bg-blue-50 border-blue-200 text-blue-800',
    },
  }

  const item = map[status]
  if (!item) return null

  return (
    <div className={`flex items-center gap-2.5 rounded-xl border px-4 py-3 text-sm ${item.cls}`}>
      {item.icon}
      <span>{item.label}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Keyword hits panel
// ---------------------------------------------------------------------------

function KeywordHitsPanel({ hits }: { hits: KeywordHit[] }) {
  const [expanded, setExpanded] = useState(false)
  const found   = hits.filter(h => h.found)
  const missing = hits.filter(h => !h.found)

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 text-xs">
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-2 w-full px-3 py-2 text-gray-600 font-medium hover:bg-gray-100 rounded-lg"
      >
        <span>Keywords ({found.length}/{hits.length} matched)</span>
        {expanded ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1">
          {hits.map((h, i) => (
            <div key={i} className="flex items-start gap-1.5">
              {h.found
                ? <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0 mt-0.5" />
                : <AlertTriangle className="w-3 h-3 text-gray-600 shrink-0 mt-0.5" />}
              <span className={h.found ? 'text-emerald-700' : 'text-gray-600'}>
                {h.keyword}
                {h.context && h.found && (
                  <span className="text-gray-500"> — "{h.context}"</span>
                )}
              </span>
            </div>
          ))}
          {missing.length > 0 && (
            <p className="text-gray-600 mt-1">
              {missing.length} keyword{missing.length > 1 ? 's' : ''} not found in OCR text.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Rubric mapping panel
// ---------------------------------------------------------------------------

function RubricPanel({ items }: { items: RubricItem[] }) {
  const [expanded, setExpanded] = useState(false)
  const matched = items.filter(r => r.matched)

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 text-xs">
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-2 w-full px-3 py-2 text-gray-600 font-medium hover:bg-gray-100 rounded-lg"
      >
        <span>Rubric ({matched.length}/{items.length} criteria met)</span>
        {expanded ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1">
          {items.map((r, i) => (
            <div key={i} className="flex items-start gap-1.5">
              {r.matched
                ? <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0 mt-0.5" />
                : <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />}
              <span className={r.matched ? 'text-gray-700' : 'text-gray-600'}>
                {r.criterion}
                {r.note && <span className="text-gray-500"> — {r.note}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

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
  const hasEnrichment = (
    (ev.keyword_hits && ev.keyword_hits.length > 0) ||
    (ev.rubric_mapping && ev.rubric_mapping.length > 0)
  )

  return (
    <div className="border border-gray-100 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 flex-1 min-w-0">
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-xs font-semibold px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
              {ev.question_type.replace('_', ' ')}
            </span>
            <span className="text-xs text-gray-600 font-mono truncate">{ev.question_id}</span>
            {ev.page_range && (
              <span className="text-xs text-gray-600">
                pp. {ev.page_range.start}–{ev.page_range.end}
              </span>
            )}
          </div>
        </div>
        <span className="text-xs text-gray-500 shrink-0">/ {ev.max_marks} marks</span>
      </div>

      {/* AI suggestion */}
      {ev.ai_suggested_marks != null ? (
        <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 space-y-2">
          <div className="flex items-center gap-2">
            <Info className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-xs font-semibold text-blue-700">AI Suggestion</span>
            {ev.ai_confidence != null && (
              <span className="ml-auto text-xs text-blue-500">
                {Math.round(ev.ai_confidence * 100)}% confidence
              </span>
            )}
            <span className="text-sm font-bold text-blue-900 ml-1">{ev.ai_suggested_marks}</span>
          </div>
          {ev.ai_justification && (
            <p className="text-xs text-blue-700 leading-relaxed">{ev.ai_justification}</p>
          )}
          {ev.ai_model && (
            <p className="text-xs text-blue-400">Model: {ev.ai_model}</p>
          )}

          {/* Enrichment panels */}
          {hasEnrichment && (
            <div className="space-y-1.5 pt-1">
              {ev.keyword_hits && ev.keyword_hits.length > 0 && (
                <KeywordHitsPanel hits={ev.keyword_hits} />
              )}
              {ev.rubric_mapping && ev.rubric_mapping.length > 0 && (
                <RubricPanel items={ev.rubric_mapping} />
              )}
            </div>
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
// OCR empty banner
// ---------------------------------------------------------------------------

function OcrEmptyBanner({
  onViewPdf,
  loading,
}: {
  onViewPdf: () => void
  loading:   boolean
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-amber-800">
            OCR could not extract readable text
          </p>
          <p className="text-xs text-amber-700 leading-relaxed">
            This PDF does not contain an embedded text layer — typical for scanned image
            files. Open the script PDF, read the answers, and enter question marks manually
            using the rows below.
          </p>
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={onViewPdf}
        disabled={loading}
        className="self-start gap-1.5 border-amber-300 text-amber-800 hover:bg-amber-100"
      >
        {loading
          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
          : <ExternalLink className="w-3.5 h-3.5" />}
        Open Script PDF
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// OCR text viewer
// ---------------------------------------------------------------------------

function OcrTextPanel({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const preview = text.slice(0, 300)

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-700">Extracted OCR Text</h3>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          className="text-xs text-indigo-600 hover:underline"
        >
          {expanded ? 'Collapse' : 'Show all'}
        </button>
      </div>
      <pre className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap break-words max-h-48 overflow-y-auto bg-gray-50 rounded-lg p-3">
        {expanded ? text : (text.length > 300 ? preview + '…' : text)}
      </pre>
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

  const [localMarks, setLocalMarks]       = useState<Record<string, { mark: number | ''; note: string }>>({})
  const [submitError, setSubmitError]     = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess]     = useState(false)
  const [fileUrlLoading, setFileUrlLoading] = useState(false)
  const [fileUrlError, setFileUrlError]   = useState<string | null>(null)

  async function handleViewScript() {
    if (!scriptId) return
    setFileUrlLoading(true)
    setFileUrlError(null)
    try {
      const { url } = await getScriptFileUrl(scriptId)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch {
      setFileUrlError('Could not fetch script file. The file may not be available.')
    } finally {
      setFileUrlLoading(false)
    }
  }

  const { data: review, isLoading } = useQuery({
    queryKey: ['script-review', scriptId],
    queryFn:  () => getEvaluatorReview(scriptId!),
  })

  const script = review
    ? {
        id:                  review.script_id,
        masked_id:           review.masked_id,
        status:              review.status,
        ocr_status:          review.ocr_status,
        page_count:          review.page_count,
        objective_auto_score: review.objective_auto_score,
        upload_url:          null as string | null,
      }
    : null

  const evals = review?.evaluations ?? null

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
      qc.invalidateQueries({ queryKey: ['script-review', scriptId] })
    },
  })

  const acceptMut = useMutation({
    mutationFn: () => acceptSuggestions(scriptId!, {}),
    onSuccess: (updatedEvals) => {
      // Merge accepted marks into local state
      setLocalMarks(prev => {
        const next = { ...prev }
        for (const ev of updatedEvals) {
          next[ev.question_id] = {
            mark: ev.evaluator_marks ?? '',
            note: prev[ev.question_id]?.note ?? '',
          }
        }
        return next
      })
      qc.invalidateQueries({ queryKey: ['script-review', scriptId] })
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
      qc.invalidateQueries({ queryKey: ['script-review', scriptId] })
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading evaluation panel…
      </div>
    )
  }

  if (!review) return <div className="p-8 text-red-600">Script not found.</div>

  const totalAI = evals?.reduce((s, e) => s + (e.ai_suggested_marks ?? 0), 0) ?? 0
  const totalHuman = evals?.reduce((s, e) => {
    const m = localMarks[e.question_id]?.mark
    return s + (m !== '' && m != null ? Number(m) : 0)
  }, 0) ?? 0
  const maxTotal = evals?.reduce((s, e) => s + e.max_marks, 0) ?? 0

  const allHaveAI = evals != null && evals.length > 0 && evals.every(e => e.ai_suggested_marks != null)

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900">
            Evaluation — <span className="font-mono text-indigo-600">{review.masked_id}</span>
          </h1>
          <p className="text-sm text-gray-500">
            Status: <strong>{review.status.replace(/_/g, ' ')}</strong>
          </p>
        </div>
      </div>

      {/* Pipeline status banner */}
      <PipelineStatusBanner status={review.status} />

      {/* OCR empty — manual review required */}
      {review.ocr_status === 'EMPTY' && review.status === 'REVIEW_REQUIRED' && (
        <OcrEmptyBanner onViewPdf={handleViewScript} loading={fileUrlLoading} />
      )}

      {/* AI advisory */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          <strong>AI advises, human decides.</strong> AI-suggested marks are for reference only.
          Review keyword evidence and rubric matches before accepting. Your marks are final for Gate 1.
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left column */}
        <div className="space-y-4">

          {/* Script info card */}
          <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-700">Script Info</h3>
            <div className="space-y-1 text-xs text-gray-600">
              <p><span className="font-medium">Masked ID:</span> <span className="font-mono">{review.masked_id}</span></p>
              <p><span className="font-medium">Status:</span> {review.status.replace(/_/g, ' ')}</p>
              {review.page_count != null && (
                <p><span className="font-medium">Pages:</span> {review.page_count}</p>
              )}
              {review.objective_auto_score != null && (
                <p><span className="font-medium">MCQ Auto-score:</span> {review.objective_auto_score}</p>
              )}
              {review.ocr_status && (
                <p>
                  <span className="font-medium">OCR:</span>{' '}
                  <span className={
                    review.ocr_status === 'COMPLETE' ? 'text-emerald-600'
                    : review.ocr_status === 'EMPTY'  ? 'text-amber-600'
                    : 'text-red-600'
                  }>
                    {review.ocr_status === 'COMPLETE' ? 'Complete'
                     : review.ocr_status === 'EMPTY'  ? 'Empty — manual review'
                     : review.ocr_status}
                  </span>
                </p>
              )}
            </div>

            {/* View original scan */}
            <Button
              size="sm"
              variant="outline"
              onClick={handleViewScript}
              disabled={fileUrlLoading}
              className="w-full gap-1.5 text-indigo-700 border-indigo-200 hover:bg-indigo-50"
            >
              {fileUrlLoading
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <ExternalLink className="w-3.5 h-3.5" />}
              View Script PDF
            </Button>
            {fileUrlError && (
              <p className="text-xs text-red-500">{fileUrlError}</p>
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

              {/* Accept AI suggestions */}
              {allHaveAI && (
                <Button
                  onClick={() => acceptMut.mutate()}
                  disabled={acceptMut.isPending}
                  variant="outline"
                  className="w-full gap-2 border-blue-200 text-blue-700 hover:bg-blue-50"
                >
                  {acceptMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Zap className="w-4 h-4" />}
                  Accept All AI Suggestions
                </Button>
              )}

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
              <p className="text-xs text-gray-600 text-center">
                Gate 1 submits marks to the Board for finalisation. You cannot edit after this.
              </p>
            </div>
          )}

          {isReadOnly && (
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-xs text-gray-500 text-center">
              {review.status === 'MARKS_SUBMITTED' && 'Marks submitted — awaiting Board finalisation.'}
              {review.status === 'BOARD_FINALISED' && 'Board finalised — view only.'}
              {(['PENDING', 'PROCESSING', 'FAILED'] as ScriptStatus[]).includes(review.status) &&
                'Scoring in progress or failed — cannot evaluate yet.'}
              {review.status === 'QUALITY_CHECKING' && 'Scan quality check in progress.'}
              {review.status === 'QUALITY_FAILED' && 'Scan quality check failed — upload may need replacement.'}
              {review.status === 'OCR_PROCESSING' && 'OCR text extraction in progress.'}
            </div>
          )}

          {!isReadOnly && evals != null && evals.length === 0 && review.ocr_status === 'EMPTY' && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-700 text-center">
              Manual review required — enter marks once question rows appear below.
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="lg:col-span-2 space-y-4">

          {/* OCR text panel */}
          {review.ocr_text && <OcrTextPanel text={review.ocr_text} />}

          {/* Question evaluation rows */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700">
                Questions ({evals?.length ?? 0})
              </h2>
              {!isReadOnly && evals && evals.length > 0 && (
                <button
                  onClick={() => acceptMut.mutate()}
                  disabled={acceptMut.isPending || !allHaveAI}
                  className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 disabled:opacity-40"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Accept all AI
                </button>
              )}
            </div>

            {evals && evals.length === 0 && (
              <div className="text-center py-12 space-y-2">
                {review.ocr_status === 'EMPTY' ? (
                  <>
                    <p className="text-sm font-medium text-gray-700">
                      No AI suggestions — OCR returned no readable text
                    </p>
                    <p className="text-xs text-gray-500 max-w-sm mx-auto leading-relaxed">
                      Open the PDF above, read each answer, and enter marks manually
                      once question rows have been created by an administrator.
                    </p>
                  </>
                ) : (
                  <p className="text-gray-500 text-sm">
                    No evaluation rows found. The scoring task may still be running.
                  </p>
                )}
              </div>
            )}

            <div className="space-y-3">
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
      </div>
    </div>
  )
}
