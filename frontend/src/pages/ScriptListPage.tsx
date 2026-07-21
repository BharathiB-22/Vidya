// M09 Paper Administration — Admin/Board: list of scanned scripts (H-36 STEP-10/12)
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listAllScripts, getPaperStats, overrideQualityFailed } from '@/lib/api/scripts'
import { listAllExamPapers } from '@/lib/api/exam'
import type { PaperPipelineStats, ScannedScript, ScriptStatus } from '@/types/script'

const STATUS_OPTS: Array<{ value: ScriptStatus | ''; label: string }> = [
  { value: '',                 label: 'All' },
  { value: 'PENDING',          label: 'Pending' },
  { value: 'QUALITY_CHECKING', label: 'Quality Check' },
  { value: 'QUALITY_FAILED',   label: 'Quality Failed' },
  { value: 'OCR_PROCESSING',   label: 'OCR Processing' },
  { value: 'PROCESSING',       label: 'Scoring' },
  { value: 'SCORED',           label: 'Scored' },
  { value: 'FAILED',           label: 'Failed' },
  { value: 'REVIEW_REQUIRED',  label: 'Review Required' },
  { value: 'MARKS_SUBMITTED',  label: 'Marks Submitted' },
  { value: 'BOARD_FINALISED',  label: 'Board Finalised' },
]

const STATUS_COLOR: Record<string, string> = {
  PENDING:          'bg-gray-100 text-gray-600',
  QUALITY_CHECKING: 'bg-amber-100 text-amber-700',
  QUALITY_FAILED:   'bg-red-100 text-red-700',
  OCR_PROCESSING:   'bg-sky-100 text-sky-700',
  PROCESSING:       'bg-blue-100 text-blue-600',
  SCORED:           'bg-indigo-100 text-indigo-700',
  FAILED:           'bg-red-100 text-red-700',
  REVIEW_REQUIRED:  'bg-orange-100 text-orange-700',
  MARKS_SUBMITTED:  'bg-yellow-100 text-yellow-700',
  BOARD_FINALISED:  'bg-emerald-100 text-emerald-700',
}

export default function ScriptListPage() {
  const navigate     = useNavigate()
  const queryClient  = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ScriptStatus | ''>('')
  const [paperFilter, setPaperFilter]   = useState('')
  const [offset, setOffset]             = useState(0)
  const [overrideId, setOverrideId]     = useState<string | null>(null)
  const [overrideReason, setOverrideReason] = useState('')
  const [overriding, setOverriding]     = useState(false)
  const limit = 20

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['scripts', statusFilter, paperFilter, offset],
    queryFn:  () => listAllScripts({
      status:        statusFilter  || undefined,
      exam_paper_id: paperFilter   || undefined,
      offset,
      limit,
    }),
  })

  const { data: papersData } = useQuery({
    queryKey: ['exam-papers-for-stats'],
    queryFn:  () => listAllExamPapers({ limit: 200 }),
  })

  const { data: statsData } = useQuery({
    queryKey: ['paper-stats', paperFilter],
    queryFn:  () => getPaperStats(paperFilter),
    enabled:  !!paperFilter,
  })

  return (
    <PageShell>
      <PageHeader
        icon={FileText}
        title="Scanned Scripts"
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => navigate('/scripts/board')}>
              Board Review
            </Button>
            <Button onClick={() => navigate('/scripts/upload')} className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2">
              <Plus className="w-4 h-4" />
              Upload Script
            </Button>
          </div>
        }
      />

      {/* Paper selector */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
        <div className="w-full sm:max-w-sm">
          <label className="block text-xs font-medium text-gray-500 mb-1">Filter by exam paper</label>
          <select
            value={paperFilter}
            onChange={e => { setPaperFilter(e.target.value); setOffset(0) }}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
          >
            <option value="">— All papers —</option>
            {(papersData?.items ?? []).map(p => (
              <option key={p.id} value={p.id}>
                {p.title} · {p.exam_type.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>
        {paperFilter && statsData && (
          <button
            className="text-xs text-gray-600 hover:text-gray-600 transition-colors self-end pb-2"
            onClick={() => { setPaperFilter(''); setOffset(0) }}
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Pipeline stats panel — shown when a paper is selected */}
      {paperFilter && statsData && <PipelineStatsPanel stats={statsData} />}

      {/* Status filter chips */}
      <div className="flex flex-wrap gap-2">
        {STATUS_OPTS.map(opt => (
          <button
            key={opt.value}
            onClick={() => { setStatusFilter(opt.value); setOffset(0) }}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              statusFilter === opt.value
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading && <PageLoading message="Loading scripts…" />}

      {isError && (
        <PageError message="Failed to load scripts." onRetry={() => refetch()} />
      )}

      {data && data.items.length === 0 && (
        <PageEmpty
          icon={FileText}
          message="No scripts found."
          action={
            <Button variant="outline" size="sm" onClick={() => navigate('/scripts/upload')}>
              Upload your first script
            </Button>
          }
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="space-y-3">
            {data.items.map(script => (
              <div key={script.id}>
                <ScriptCard
                  script={script}
                  onEvaluate={() => navigate(`/scripts/${script.id}/evaluate`)}
                  onBoardReview={() => navigate('/scripts/board')}
                  onOverride={script.status === 'QUALITY_FAILED'
                    ? () => { setOverrideId(script.id); setOverrideReason('') }
                    : undefined}
                />
                {/* Inline override panel — shown for the selected QUALITY_FAILED script */}
                {overrideId === script.id && (
                  <div className="mt-1 ml-4 rounded-b-xl border border-orange-200 bg-orange-50 p-4 space-y-3">
                    <div className="flex items-center gap-2 text-orange-700">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      <p className="text-sm font-medium">Override quality check</p>
                    </div>
                    <p className="text-xs text-orange-600">
                      This script failed quality checks. Provide a reason to force-advance it to OCR.
                      Your name and reason will be permanently audit-logged.
                    </p>
                    <textarea
                      rows={2}
                      value={overrideReason}
                      onChange={e => setOverrideReason(e.target.value)}
                      placeholder="Mandatory reason (min 10 chars)…"
                      className="w-full border border-orange-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white resize-none"
                    />
                    <div className="flex gap-2 justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOverrideId(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        disabled={overrideReason.trim().length < 10 || overriding}
                        onClick={async () => {
                          setOverriding(true)
                          try {
                            await overrideQualityFailed(script.id, overrideReason.trim())
                            setOverrideId(null)
                            queryClient.invalidateQueries({ queryKey: ['scripts'] })
                            queryClient.invalidateQueries({ queryKey: ['paper-stats'] })
                          } finally {
                            setOverriding(false)
                          }
                        }}
                        className="bg-orange-600 hover:bg-orange-700 text-white"
                      >
                        {overriding ? 'Overriding…' : 'Confirm override'}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

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
        </>
      )}
    </PageShell>
  )
}

// ---------------------------------------------------------------------------
// Pipeline stats panel (H-36 STEP-10)
// ---------------------------------------------------------------------------

const STAT_ROWS: Array<{ key: keyof PaperPipelineStats; label: string; color: string }> = [
  { key: 'pending',          label: 'Pending',          color: 'text-gray-500' },
  { key: 'quality_checking', label: 'Quality check',    color: 'text-amber-600' },
  { key: 'quality_failed',   label: 'Quality failed',   color: 'text-red-600' },
  { key: 'ocr_processing',   label: 'OCR',              color: 'text-sky-600' },
  { key: 'processing',       label: 'Scoring',          color: 'text-blue-600' },
  { key: 'scored',           label: 'Scored',           color: 'text-indigo-600' },
  { key: 'review_required',  label: 'Review required',  color: 'text-orange-600' },
  { key: 'marks_submitted',  label: 'Marks submitted',  color: 'text-yellow-600' },
  { key: 'board_finalised',  label: 'Board finalised',  color: 'text-emerald-600' },
  { key: 'failed',           label: 'Failed',           color: 'text-red-500' },
]

function PipelineStatsPanel({ stats }: { stats: PaperPipelineStats }) {
  const pctColor = stats.completion_pct >= 75
    ? 'text-emerald-600'
    : stats.completion_pct >= 25
      ? 'text-amber-600'
      : 'text-gray-500'

  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-700">Pipeline status</p>
        <div className="text-right">
          <span className={`text-2xl font-bold ${pctColor}`}>{stats.completion_pct}%</span>
          <span className="text-xs text-gray-600 ml-1">complete</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-1.5">
        <div
          className="bg-emerald-500 h-1.5 rounded-full transition-all"
          style={{ width: `${Math.min(stats.completion_pct, 100)}%` }}
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {STAT_ROWS.filter(r => (stats[r.key] as number) > 0).map(r => (
          <div key={r.key} className="text-center bg-white rounded-lg border border-gray-100 px-2 py-1.5">
            <p className={`text-lg font-bold ${r.color}`}>{stats[r.key] as number}</p>
            <p className="text-[10px] text-gray-600 leading-tight mt-0.5">{r.label}</p>
          </div>
        ))}
        {stats.total === 0 && (
          <p className="col-span-5 text-xs text-gray-600 text-center py-2">No scripts uploaded for this paper yet.</p>
        )}
      </div>

      <p className="text-xs text-gray-600 text-right">
        {stats.board_finalised} of {stats.total} scripts finalised
      </p>
    </div>
  )
}

function ScriptCard({
  script,
  onEvaluate,
  onBoardReview,
  onOverride,
}: {
  script:        ScannedScript
  onEvaluate:    () => void
  onBoardReview: () => void
  onOverride?:   () => void
}) {
  const colorClass = STATUS_COLOR[script.status] ?? 'bg-gray-100 text-gray-600'
  const canEvaluate = ['SCORED', 'REVIEW_REQUIRED'].includes(script.status)
  const boardPending = script.status === 'MARKS_SUBMITTED'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-start gap-4">
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-gray-700">{script.masked_id}</span>
          <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${colorClass}`}>
            {script.status.replace(/_/g, ' ')}
          </span>
        </div>
        <p className="text-xs text-gray-500 truncate">
          Paper: <span className="font-mono">{script.exam_paper_id}</span>
        </p>
        {script.evaluator_id && (
          <p className="text-xs text-gray-600">
            Evaluator: <span className="font-mono">{script.evaluator_id}</span>
          </p>
        )}
        {script.submitted_at && (
          <p className="text-xs text-gray-600">
            Submitted: {new Date(script.submitted_at).toLocaleString()}
          </p>
        )}
        {script.finalised_at && (
          <p className="text-xs text-gray-600">
            Finalised: {new Date(script.finalised_at).toLocaleString()}
          </p>
        )}
        {/* Identity only shown after BOARD_FINALISED if backend returns it */}
        {script.status === 'BOARD_FINALISED' && script.student_roll_ref && (
          <p className="text-xs text-emerald-600 font-medium">
            Roll: {script.student_roll_ref}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 shrink-0">
        {canEvaluate && (
          <Button size="sm" onClick={onEvaluate} className="bg-indigo-600 hover:bg-indigo-700 text-white">
            Evaluate
          </Button>
        )}
        {boardPending && (
          <Button size="sm" onClick={onBoardReview} className="bg-yellow-600 hover:bg-yellow-700 text-white">
            Board Review
          </Button>
        )}
        {script.status === 'QUALITY_FAILED' && onOverride && (
          <Button
            size="sm"
            variant="outline"
            onClick={onOverride}
            className="border-orange-300 text-orange-700 hover:bg-orange-50"
          >
            Override
          </Button>
        )}
        {!canEvaluate && !boardPending && script.status !== 'QUALITY_FAILED' && (
          <Button size="sm" variant="outline" onClick={onEvaluate}>
            View
          </Button>
        )}
      </div>
    </div>
  )
}
