// M09.7 OCR Review Queue — detail page with image viewer + action panel
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ChevronLeft,
  ScanSearch,
  ZoomIn,
  ZoomOut,
  RotateCw,
  ChevronLeft as PagePrev,
  ChevronRight as PageNext,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  ArrowUpCircle,
  XCircle,
  Edit3,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PageLoading } from '@/components/shared/PageLoading'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import {
  useOcrDetail,
  useStartReview,
  useAcceptOcr,
  useCorrectOcr,
  useRerunOcr,
  useEscalateOcr,
  useMarkUnreadable,
} from '@/hooks/ocrReview/useOcrReview'

// ---- Helpers ----------------------------------------------------------------

const PRIORITY_META: Record<string, { label: string; color: string; bg: string }> = {
  OCR_FAILURE:       { label: 'OCR Failure',       color: 'text-red-700',    bg: 'bg-red-100 text-red-700'    },
  LOW_CONFIDENCE:    { label: 'Low Confidence',    color: 'text-orange-700', bg: 'bg-orange-100 text-orange-700' },
  QUALITY_ISSUE:     { label: 'Quality Issue',     color: 'text-yellow-700', bg: 'bg-yellow-100 text-yellow-700' },
  MEDIUM_CONFIDENCE: { label: 'Medium Confidence', color: 'text-blue-700',   bg: 'bg-blue-100 text-blue-700'  },
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'bg-red-100 text-red-700 border-red-200',
  HIGH:     'bg-orange-100 text-orange-700 border-orange-200',
  MEDIUM:   'bg-yellow-100 text-yellow-700 border-yellow-200',
  LOW:      'bg-gray-100 text-gray-600 border-gray-200',
}

// ---- Image Viewer -----------------------------------------------------------

function ImageViewer({ keys, currentPage, onChangePage }: {
  keys:         string[]
  currentPage:  number
  onChangePage: (p: number) => void
}) {
  const [zoom, setZoom]     = useState(1)
  const [rotate, setRotate] = useState(0)

  const key = keys[currentPage] ?? null

  if (!key) {
    return (
      <div className="flex items-center justify-center h-80 rounded-lg border-2 border-dashed border-gray-200 bg-gray-50">
        <p className="text-gray-600 text-sm">No scan image available</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Controls */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
            title="Zoom out"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-gray-500 w-12 text-center font-mono">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setZoom(z => Math.min(4, z + 0.25))}
            title="Zoom in"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRotate(r => (r + 90) % 360)}
            title="Rotate 90°"
            className="ml-1"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setZoom(1); setRotate(0) }}
            className="ml-1 text-xs"
          >
            Reset
          </Button>
        </div>

        {/* Page nav */}
        {keys.length > 1 && (
          <div className="flex items-center gap-1.5 text-sm text-gray-600">
            <Button
              variant="ghost"
              size="sm"
              disabled={currentPage === 0}
              onClick={() => onChangePage(currentPage - 1)}
            >
              <PagePrev className="h-4 w-4" />
            </Button>
            <span className="text-xs text-gray-500">
              Page {currentPage + 1} / {keys.length}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={currentPage === keys.length - 1}
              onClick={() => onChangePage(currentPage + 1)}
            >
              <PageNext className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      {/* Image area */}
      <div className="overflow-auto rounded-lg border border-gray-200 bg-gray-100 h-96 flex items-center justify-center">
        <img
          src={key}
          alt={`Scan page ${currentPage + 1}`}
          style={{
            transform: `scale(${zoom}) rotate(${rotate}deg)`,
            transformOrigin: 'center',
            transition: 'transform 0.15s ease',
            maxWidth: 'none',
          }}
          className="select-none"
          draggable={false}
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none'
          }}
        />
      </div>
    </div>
  )
}

// ---- Action Panel -----------------------------------------------------------

type ActionMode = 'idle' | 'edit' | 'escalate' | 'unreadable' | 'rerun' | 'accept'

function ActionPanel({
  queueId,
  currentOcrText,
  reviewStatus,
  onDone,
}: {
  queueId:      string
  currentOcrText: string | null
  reviewStatus: string
  onDone:       () => void
}) {
  const [mode, setMode]         = useState<ActionMode>('idle')
  const [editText, setEditText] = useState(currentOcrText ?? '')
  const [notes, setNotes]       = useState('')
  const [confirmAction, setConfirmAction] = useState<null | 'unreadable' | 'rerun'>(null)

  const accept    = useAcceptOcr()
  const correct   = useCorrectOcr()
  const rerun     = useRerunOcr()
  const escalate  = useEscalateOcr()
  const unreadable = useMarkUnreadable()

  const isDone = ['ACCEPTED', 'CORRECTED', 'RERUN', 'ESCALATED', 'UNREADABLE'].includes(reviewStatus)

  useEffect(() => {
    if (currentOcrText) setEditText(currentOcrText)
  }, [currentOcrText])

  async function handleAccept() {
    try {
      await accept.mutateAsync({ queueId, notes })
      addToast('OCR accepted', 'success', 3000)
      onDone()
    } catch {
      addToast('Failed to accept OCR', 'error', 4000)
    }
  }

  async function handleCorrect() {
    if (!editText.trim()) {
      addToast('Corrected text cannot be empty', 'error', 3000)
      return
    }
    try {
      await correct.mutateAsync({ queueId, correctedText: editText, notes })
      addToast('OCR text corrected', 'success', 3000)
      setMode('idle')
      onDone()
    } catch {
      addToast('Failed to save correction', 'error', 4000)
    }
  }

  async function handleRerun() {
    setConfirmAction(null)
    try {
      await rerun.mutateAsync({ queueId, notes })
      addToast('Re-run requested', 'success', 3000)
      onDone()
    } catch {
      addToast('Failed to request re-run', 'error', 4000)
    }
  }

  async function handleEscalate() {
    if (notes.trim().length < 10) {
      addToast('Escalation notes must be at least 10 characters', 'error', 3000)
      return
    }
    try {
      await escalate.mutateAsync({ queueId, notes })
      addToast('Escalated to Admin', 'success', 3000)
      onDone()
    } catch {
      addToast('Failed to escalate', 'error', 4000)
    }
  }

  async function handleUnreadable() {
    setConfirmAction(null)
    if (notes.trim().length < 10) {
      addToast('Please provide at least 10 characters of notes', 'error', 3000)
      setMode('unreadable')
      return
    }
    try {
      await unreadable.mutateAsync({ queueId, notes })
      addToast('Marked as unreadable', 'success', 3000)
      onDone()
    } catch {
      addToast('Failed to mark unreadable', 'error', 4000)
    }
  }

  if (isDone) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
        <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto mb-2" />
        <p className="text-green-800 font-medium">Review complete</p>
        <p className="text-sm text-green-700 mt-0.5">
          Status: <span className="font-semibold">{reviewStatus}</span>
        </p>
      </div>
    )
  }

  // ---- Edit mode ----
  if (mode === 'edit') {
    return (
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">Edit OCR Text</p>
        <textarea
          className="w-full h-48 rounded-md border border-gray-300 p-3 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-400"
          value={editText}
          onChange={e => setEditText(e.target.value)}
          placeholder="Enter the corrected OCR text…"
        />
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Reviewer Notes (optional)</label>
          <input
            className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="e.g. Corrected word that was garbled on line 3"
          />
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={handleCorrect}
            disabled={correct.isPending || !editText.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {correct.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
            Save Correction
          </Button>
          <Button size="sm" variant="outline" onClick={() => setMode('idle')}>
            Cancel
          </Button>
        </div>
      </div>
    )
  }

  // ---- Escalate mode ----
  if (mode === 'escalate') {
    return (
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">Escalate to Admin</p>
        <textarea
          className="w-full h-24 rounded-md border border-gray-300 p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-400"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Describe why this is being escalated (min 10 characters)…"
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={handleEscalate}
            disabled={escalate.isPending || notes.trim().length < 10}
            className="bg-red-600 hover:bg-red-700 text-white"
          >
            {escalate.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
            Escalate
          </Button>
          <Button size="sm" variant="outline" onClick={() => setMode('idle')}>
            Cancel
          </Button>
        </div>
        {notes.trim().length > 0 && notes.trim().length < 10 && (
          <p className="text-xs text-red-500">{10 - notes.trim().length} more characters needed</p>
        )}
      </div>
    )
  }

  // ---- Unreadable mode ----
  if (mode === 'unreadable') {
    return (
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">Mark as Unreadable</p>
        <p className="text-xs text-gray-500">
          Use this only when the physical scan is too damaged, blurred, or corrupted to be recovered.
        </p>
        <textarea
          className="w-full h-24 rounded-md border border-gray-300 p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-400"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Reason for marking unreadable (min 10 characters)…"
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => confirmAction === null && notes.trim().length >= 10
              ? setConfirmAction('unreadable')
              : handleUnreadable()
            }
            disabled={unreadable.isPending || notes.trim().length < 10}
            className="bg-zinc-700 hover:bg-zinc-800 text-white"
          >
            {unreadable.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
            Mark Unreadable
          </Button>
          <Button size="sm" variant="outline" onClick={() => setMode('idle')}>
            Cancel
          </Button>
        </div>
        {notes.trim().length > 0 && notes.trim().length < 10 && (
          <p className="text-xs text-red-500">{10 - notes.trim().length} more characters needed</p>
        )}
      </div>
    )
  }

  // ---- Default action buttons ----
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-gray-700">Review Action</p>
      <p className="text-xs text-gray-500">
        Select an action based on your review of the scanned image and OCR text.
      </p>

      <div className="grid grid-cols-1 gap-2">
        <Button
          variant="outline"
          className="justify-start text-green-700 border-green-200 hover:bg-green-50"
          onClick={handleAccept}
          disabled={accept.isPending}
        >
          {accept.isPending
            ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            : <CheckCircle2 className="h-4 w-4 mr-2" />
          }
          Accept OCR as-is
        </Button>

        <Button
          variant="outline"
          className="justify-start text-indigo-700 border-indigo-200 hover:bg-indigo-50"
          onClick={() => setMode('edit')}
        >
          <Edit3 className="h-4 w-4 mr-2" />
          Edit OCR Text
        </Button>

        <Button
          variant="outline"
          className="justify-start text-blue-700 border-blue-200 hover:bg-blue-50"
          onClick={() => setConfirmAction('rerun')}
          disabled={rerun.isPending}
        >
          {rerun.isPending
            ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            : <RotateCcw className="h-4 w-4 mr-2" />
          }
          Re-run OCR
        </Button>

        <Button
          variant="outline"
          className="justify-start text-red-700 border-red-200 hover:bg-red-50"
          onClick={() => setMode('escalate')}
        >
          <ArrowUpCircle className="h-4 w-4 mr-2" />
          Escalate to Admin
        </Button>

        <Button
          variant="outline"
          className="justify-start text-zinc-700 border-zinc-200 hover:bg-zinc-50"
          onClick={() => setMode('unreadable')}
        >
          <XCircle className="h-4 w-4 mr-2" />
          Mark Unreadable
        </Button>
      </div>

      {/* Confirm re-run */}
      <ConfirmDialog
        open={confirmAction === 'rerun'}
        title="Re-run OCR"
        description="This will queue the script for another OCR extraction pass. The current OCR text will be preserved until re-run completes."
        confirmLabel="Re-run OCR"
        onConfirm={handleRerun}
        onCancel={() => setConfirmAction(null)}
        loading={rerun.isPending}
      />

      {/* Confirm unreadable */}
      <ConfirmDialog
        open={confirmAction === 'unreadable'}
        title="Mark as Unreadable"
        description="This marks the script as physically unreadable and removes it from the review queue. This action is logged and cannot be self-reversed."
        confirmLabel="Mark Unreadable"
        onConfirm={handleUnreadable}
        onCancel={() => setConfirmAction(null)}
        loading={unreadable.isPending}
      />
    </div>
  )
}

// ---- Main page --------------------------------------------------------------

export default function OCRReviewDetailPage() {
  const { queueId = '' } = useParams<{ queueId: string }>()
  const navigate         = useNavigate()

  const { data, isLoading, isError, refetch } = useOcrDetail(queueId)
  const startReview = useStartReview()

  const [currentPage, setCurrentPage] = useState(0)

  async function handleStartReview() {
    try {
      await startReview.mutateAsync(queueId)
      refetch()
    } catch {
      addToast('Could not start review', 'error', 3000)
    }
  }

  if (isLoading) return <PageLoading />

  if (isError || !data) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <AlertCircle className="h-8 w-8 text-red-500 mx-auto mb-2" />
          <p className="text-red-700 font-medium">Unable to load review item</p>
          <p className="text-sm text-red-600 mt-1">Check your access or the queue ID.</p>
        </div>
      </div>
    )
  }

  const priorityMeta = PRIORITY_META[data.priority_category] ?? PRIORITY_META.OCR_FAILURE
  const imageKeys    = data.page_image_keys ?? []
  const flags        = data.scan_quality_flags ?? []

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">

      {/* Back nav */}
      <button
        onClick={() => navigate('/ocr-review')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-6 transition-colors"
      >
        <ChevronLeft className="h-4 w-4" />
        Back to Queue
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <ScanSearch className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              OCR Review — {data.masked_id ?? data.script_id.slice(0, 8).toUpperCase()}
            </h1>
            <p className="text-sm text-gray-500 font-mono">{data.id.slice(0, 12)}…</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Badge className={priorityMeta.bg}>{priorityMeta.label}</Badge>
          <Badge className="bg-gray-100 text-gray-700">{data.review_status}</Badge>

          {data.review_status === 'PENDING' && (
            <Button
              size="sm"
              onClick={handleStartReview}
              disabled={startReview.isPending}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              {startReview.isPending
                ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                : null}
              Start Review
            </Button>
          )}
        </div>
      </div>

      {/* Meta strip */}
      {data.ocr_confidence !== null && data.ocr_confidence !== undefined && (
        <div className="mb-6 flex flex-wrap gap-4 text-sm">
          <div className="rounded-md border border-gray-200 bg-white px-4 py-2">
            <p className="text-xs text-gray-500 mb-0.5">OCR Confidence</p>
            <p className="text-lg font-bold text-gray-900">
              {(data.ocr_confidence * 100).toFixed(1)}%
            </p>
          </div>
          <div className="rounded-md border border-gray-200 bg-white px-4 py-2">
            <p className="text-xs text-gray-500 mb-0.5">Priority Score</p>
            <p className="text-lg font-bold text-gray-900">{data.priority_score}</p>
          </div>
          {flags.length > 0 && (
            <div className="rounded-md border border-gray-200 bg-white px-4 py-2">
              <p className="text-xs text-gray-500 mb-0.5">Quality Flags</p>
              <p className="text-lg font-bold text-gray-900">{flags.length}</p>
            </div>
          )}
        </div>
      )}

      {/* Quality flags */}
      {flags.length > 0 && (
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Scan Quality Flags</p>
          <div className="flex flex-wrap gap-2">
            {flags.map((f, i) => (
              <div
                key={i}
                className={`rounded-md border px-3 py-1.5 text-xs ${SEVERITY_COLOR[f.severity] ?? SEVERITY_COLOR.LOW}`}
                title={f.description}
              >
                <span className="font-semibold">{f.type}</span>
                <span className="ml-1.5 text-opacity-70">p{f.page} · {f.severity}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Left — image viewer + OCR text */}
        <div className="space-y-6">
          {/* Image viewer */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
              Scanned Image{imageKeys.length > 1 ? ` (${imageKeys.length} pages)` : ''}
            </p>
            <ImageViewer
              keys={imageKeys}
              currentPage={currentPage}
              onChangePage={setCurrentPage}
            />
          </div>

          {/* Original OCR text */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
              Original OCR Text
            </p>
            {data.original_ocr_text ? (
              <div className="rounded-md border border-gray-200 bg-gray-50 p-4 text-sm font-mono text-gray-800 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                {data.original_ocr_text}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-600 italic text-center">
                No OCR text extracted
              </div>
            )}
          </div>

          {/* Corrected text (if present) */}
          {data.corrected_text && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-green-600 mb-2">
                Corrected Text
              </p>
              <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm font-mono text-gray-800 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                {data.corrected_text}
              </div>
            </div>
          )}
        </div>

        {/* Right — action panel */}
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Actions</p>

          {data.review_status === 'PENDING' && (
            <div className="rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              Click <strong>Start Review</strong> above to claim this item before taking action.
            </div>
          )}

          {['IN_REVIEW', 'ACCEPTED', 'CORRECTED', 'RERUN', 'ESCALATED', 'UNREADABLE'].includes(data.review_status) && (
            <ActionPanel
              queueId={queueId}
              currentOcrText={data.original_ocr_text ?? null}
              reviewStatus={data.review_status}
              onDone={() => refetch()}
            />
          )}

          {/* Reviewer notes (historical) */}
          {data.reviewer_notes && (
            <div className="mt-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Reviewer Notes</p>
              <div className="rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-700 whitespace-pre-wrap">
                {data.reviewer_notes}
              </div>
            </div>
          )}

          {/* Action taken */}
          {data.action_taken && (
            <div className="rounded-md border border-gray-100 bg-gray-50 p-3 text-sm text-gray-500">
              Action taken: <span className="font-medium text-gray-700">{data.action_taken}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
