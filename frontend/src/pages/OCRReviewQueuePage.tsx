// M09.7 OCR Review Queue — list page with priority dashboard counters and filters
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ScanSearch,
  AlertCircle,
  Eye,
  TrendingDown,
  AlertTriangle,
  ChevronRight,
  RefreshCw,
  CheckCircle2,
  Clock,
  Settings,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PageLoading } from '@/components/shared/PageLoading'
import { useOcrDashboard, useOcrQueue } from '@/hooks/ocrReview/useOcrReview'
import type { OcrQueueItem } from '@/lib/api/ocrReview'

// ---- Priority helpers -------------------------------------------------------

const PRIORITY_META: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  OCR_FAILURE:       { label: 'OCR Failure',       color: 'text-red-700',    bg: 'bg-red-50 border-red-200',    icon: AlertCircle  },
  LOW_CONFIDENCE:    { label: 'Low Confidence',    color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200', icon: TrendingDown },
  QUALITY_ISSUE:     { label: 'Quality Issue',     color: 'text-yellow-700', bg: 'bg-yellow-50 border-yellow-200', icon: AlertTriangle },
  MEDIUM_CONFIDENCE: { label: 'Medium Confidence', color: 'text-blue-700',   bg: 'bg-blue-50 border-blue-200',  icon: Eye          },
}

const STATUS_META: Record<string, { label: string; badge: string }> = {
  PENDING:   { label: 'Pending',    badge: 'bg-gray-100 text-gray-700'   },
  IN_REVIEW: { label: 'In Review',  badge: 'bg-blue-100 text-blue-700'   },
  ACCEPTED:  { label: 'Accepted',   badge: 'bg-green-100 text-green-700' },
  CORRECTED: { label: 'Corrected',  badge: 'bg-purple-100 text-purple-700' },
  RERUN:     { label: 'Rerun',      badge: 'bg-indigo-100 text-indigo-700' },
  ESCALATED: { label: 'Escalated',  badge: 'bg-red-100 text-red-700'     },
  UNREADABLE:{ label: 'Unreadable', badge: 'bg-zinc-100 text-zinc-700'   },
}

// ---- Stat card --------------------------------------------------------------

function StatCard({
  label,
  count,
  icon: Icon,
  color,
  bg,
  active,
  onClick,
}: {
  label:   string
  count:   number
  icon:    React.ElementType
  color:   string
  bg:      string
  active:  boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 min-w-0 rounded-lg border p-4 text-left transition-all hover:shadow-md
        ${active ? `${bg} ring-2 ring-offset-1 ring-current shadow-sm` : 'bg-white border-gray-200 hover:border-gray-300'}
      `}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`h-4 w-4 shrink-0 ${color}`} />
        <span className={`text-xs font-medium truncate ${color}`}>{label}</span>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{count}</p>
    </button>
  )
}

// ---- Queue item card --------------------------------------------------------

function QueueCard({ item, onClick }: { item: OcrQueueItem; onClick: () => void }) {
  const meta   = PRIORITY_META[item.priority_category] ?? PRIORITY_META.OCR_FAILURE
  const status = STATUS_META[item.review_status] ?? { label: item.review_status, badge: 'bg-gray-100 text-gray-700' }
  const Icon   = meta.icon

  return (
    <div className={`rounded-lg border ${meta.bg} p-4 transition-shadow hover:shadow-md`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <Icon className={`h-4 w-4 shrink-0 ${meta.color}`} />
            <span className={`text-xs font-semibold uppercase tracking-wide ${meta.color}`}>
              {meta.label}
            </span>
            <Badge className={`text-xs ${status.badge}`}>{status.label}</Badge>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-700 flex-wrap">
            <span className="font-mono font-medium">
              {item.masked_id ?? item.script_id.slice(0, 8).toUpperCase()}
            </span>
            {item.ocr_confidence !== null && item.ocr_confidence !== undefined && (
              <span className="text-gray-500">
                Confidence: <span className="font-medium">{(item.ocr_confidence * 100).toFixed(0)}%</span>
              </span>
            )}
            {item.exam_paper_id && (
              <span className="text-gray-400 text-xs truncate max-w-[160px]">
                Exam: {item.exam_paper_id.slice(0, 8)}…
              </span>
            )}
          </div>

          <div className="flex items-center gap-1 mt-2 text-xs text-gray-500">
            <Clock className="h-3 w-3" />
            Queued {new Date(item.enqueued_at).toLocaleString('en-IN', {
              day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
            })}
          </div>
        </div>

        <Button
          size="sm"
          variant="ghost"
          onClick={onClick}
          className={`shrink-0 ${meta.color} hover:bg-white/60`}
        >
          Review
          <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  )
}

// ---- Main page --------------------------------------------------------------

export default function OCRReviewQueuePage() {
  const navigate                  = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const activePriority = searchParams.get('priority') ?? ''
  const showCompleted  = searchParams.get('completed') === '1'
  const page           = parseInt(searchParams.get('page') ?? '1', 10)

  const [thresholdOpen, setThresholdOpen] = useState(false)

  const { data: dash, isLoading: dashLoading, refetch: refetchDash } = useOcrDashboard()
  const { data: queue, isLoading: queueLoading, isError: queueError } = useOcrQueue({
    priority_category: activePriority || undefined,
    show_completed:    showCompleted || undefined,
    page,
    page_size:         20,
  })

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value); else next.delete(key)
    next.delete('page')
    setSearchParams(next)
  }

  function togglePriority(cat: string) {
    setFilter('priority', activePriority === cat ? '' : cat)
  }

  function setPage(p: number) {
    const next = new URLSearchParams(searchParams)
    next.set('page', String(p))
    setSearchParams(next)
  }

  const categories: Array<{ key: string; label: string; count: number; icon: React.ElementType; color: string; bg: string }> = [
    { key: 'OCR_FAILURE',       ...PRIORITY_META.OCR_FAILURE,       count: dash?.ocr_failure_count ?? 0 },
    { key: 'LOW_CONFIDENCE',    ...PRIORITY_META.LOW_CONFIDENCE,    count: dash?.low_confidence_count ?? 0 },
    { key: 'QUALITY_ISSUE',     ...PRIORITY_META.QUALITY_ISSUE,     count: dash?.quality_issue_count ?? 0 },
    { key: 'MEDIUM_CONFIDENCE', ...PRIORITY_META.MEDIUM_CONFIDENCE, count: dash?.medium_confidence_count ?? 0 },
  ]

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <ScanSearch className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">OCR Review Queue</h1>
            <p className="text-sm text-gray-500">Prioritised script review — OCR failures first</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => { refetchDash() }}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setThresholdOpen(v => !v)}
          >
            <Settings className="h-3.5 w-3.5 mr-1.5" />
            Thresholds
          </Button>
        </div>
      </div>

      {/* Threshold info (collapsible) */}
      {thresholdOpen && (
        <div className="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
          <p className="text-sm font-medium text-indigo-800 mb-1">Confidence Thresholds</p>
          <p className="text-xs text-indigo-700">
            Scripts with OCR confidence below the <strong>Low</strong> threshold are queued as
            LOW_CONFIDENCE. Scripts with a CRITICAL/HIGH scan quality flag become QUALITY_ISSUE.
            Scripts with confidence between Low and <strong>Medium</strong> thresholds are MEDIUM_CONFIDENCE.
            Scripts above the Medium threshold are not queued (unless OCR failed entirely).
          </p>
          <p className="text-xs text-indigo-600 mt-2">
            To change thresholds, contact Admin to update via the API or the threshold configuration panel.
          </p>
        </div>
      )}

      {/* Priority counter cards */}
      <div className="flex gap-3 mb-6 overflow-x-auto pb-1">
        {dashLoading ? (
          <div className="h-20 flex-1 rounded-lg bg-gray-100 animate-pulse" />
        ) : (
          categories.map(cat => (
            <StatCard
              key={cat.key}
              label={cat.label}
              count={cat.count}
              icon={cat.icon}
              color={cat.color}
              bg={cat.bg}
              active={activePriority === cat.key}
              onClick={() => togglePriority(cat.key)}
            />
          ))
        )}
      </div>

      {/* Summary strip */}
      {dash && !dashLoading && (
        <div className="flex items-center gap-6 mb-4 text-sm text-gray-600 flex-wrap">
          <span>
            <span className="font-medium text-gray-900">{dash.pending_total}</span> pending
          </span>
          <span>
            <span className="font-medium text-gray-900">{dash.in_review_total}</span> in review
          </span>
          <span>
            <CheckCircle2 className="inline h-3.5 w-3.5 text-green-500 mr-0.5" />
            <span className="font-medium text-gray-900">{dash.completed_today}</span> completed today
          </span>
          <button
            onClick={() => setFilter('completed', showCompleted ? '' : '1')}
            className={`ml-auto text-xs px-2 py-1 rounded-md border transition-colors
              ${showCompleted
                ? 'border-green-300 bg-green-50 text-green-700'
                : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300'}`}
          >
            {showCompleted ? 'Hide completed' : 'Show completed'}
          </button>
        </div>
      )}

      {/* Active filter badge */}
      {activePriority && (
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xs text-gray-500">Filtered by:</span>
          <Badge
            className={`${PRIORITY_META[activePriority]?.bg ?? ''} ${PRIORITY_META[activePriority]?.color ?? ''} border text-xs`}
          >
            {PRIORITY_META[activePriority]?.label ?? activePriority}
          </Badge>
          <button
            className="text-xs text-gray-400 hover:text-gray-600"
            onClick={() => setFilter('priority', '')}
          >
            Clear
          </button>
        </div>
      )}

      {/* Queue list */}
      {queueLoading ? (
        <PageLoading />
      ) : queueError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <AlertCircle className="h-8 w-8 text-red-500 mx-auto mb-2" />
          <p className="text-red-700 font-medium">Failed to load queue</p>
          <p className="text-sm text-red-600 mt-1">Check your access and try refreshing.</p>
        </div>
      ) : !queue || queue.items.length === 0 ? (
        <div className="rounded-lg border border-green-200 bg-green-50 p-10 text-center">
          <CheckCircle2 className="h-10 w-10 text-green-500 mx-auto mb-3" />
          <p className="text-green-800 font-medium text-lg">Queue is clear!</p>
          <p className="text-sm text-green-700 mt-1">
            {activePriority
              ? `No ${PRIORITY_META[activePriority]?.label ?? activePriority} items to review.`
              : 'No scripts are awaiting OCR review.'}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3 mb-6">
            {queue.items.map(item => (
              <QueueCard
                key={item.id}
                item={item}
                onClick={() => navigate(`/ocr-review/${item.id}`)}
              />
            ))}
          </div>

          {/* Pagination */}
          {queue.pages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">
                Page {queue.page} of {queue.pages} ({queue.total} total)
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={queue.page <= 1}
                  onClick={() => setPage(queue.page - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={queue.page >= queue.pages}
                  onClick={() => setPage(queue.page + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
