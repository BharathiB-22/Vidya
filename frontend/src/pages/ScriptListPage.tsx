// M09 Paper Administration — Admin/Board: list of scanned scripts
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listAllScripts } from '@/lib/api/scripts'
import type { ScannedScript, ScriptStatus } from '@/types/script'

const STATUS_OPTS: Array<{ value: ScriptStatus | ''; label: string }> = [
  { value: '',                 label: 'All' },
  { value: 'PENDING',          label: 'Pending' },
  { value: 'PROCESSING',       label: 'Processing' },
  { value: 'SCORED',           label: 'Scored' },
  { value: 'FAILED',           label: 'Failed' },
  { value: 'REVIEW_REQUIRED',  label: 'Review Required' },
  { value: 'MARKS_SUBMITTED',  label: 'Marks Submitted' },
  { value: 'BOARD_FINALISED',  label: 'Board Finalised' },
]

const STATUS_COLOR: Record<string, string> = {
  PENDING:         'bg-gray-100 text-gray-600',
  PROCESSING:      'bg-blue-100 text-blue-600',
  SCORED:          'bg-indigo-100 text-indigo-700',
  FAILED:          'bg-red-100 text-red-700',
  REVIEW_REQUIRED: 'bg-orange-100 text-orange-700',
  MARKS_SUBMITTED: 'bg-yellow-100 text-yellow-700',
  BOARD_FINALISED: 'bg-emerald-100 text-emerald-700',
}

export default function ScriptListPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<ScriptStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const limit = 20

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['scripts', statusFilter, offset],
    queryFn:  () => listAllScripts({ status: statusFilter || undefined, offset, limit }),
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
              <ScriptCard
                key={script.id}
                script={script}
                onEvaluate={() => navigate(`/scripts/${script.id}/evaluate`)}
                onBoardReview={() => navigate('/scripts/board')}
              />
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

function ScriptCard({
  script,
  onEvaluate,
  onBoardReview,
}: {
  script:        ScannedScript
  onEvaluate:    () => void
  onBoardReview: () => void
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
          <p className="text-xs text-gray-400">
            Evaluator: <span className="font-mono">{script.evaluator_id}</span>
          </p>
        )}
        {script.submitted_at && (
          <p className="text-xs text-gray-400">
            Submitted: {new Date(script.submitted_at).toLocaleString()}
          </p>
        )}
        {script.finalised_at && (
          <p className="text-xs text-gray-400">
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
        {!canEvaluate && !boardPending && (
          <Button size="sm" variant="outline" onClick={onEvaluate}>
            View
          </Button>
        )}
      </div>
    </div>
  )
}
