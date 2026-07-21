// M09 Paper Administration — Evaluator: my assigned scripts (H-36 STEP-07)
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ClipboardList } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listMyScripts } from '@/lib/api/scripts'
import type { ScannedScript, ScriptStatus } from '@/types/script'

const STATUS_OPTS: Array<{ value: ScriptStatus | ''; label: string }> = [
  { value: '',                         label: 'All' },
  { value: 'SCORED',                   label: 'Ready to Evaluate' },
  { value: 'REVIEW_REQUIRED',          label: 'Review Required' },
  { value: 'WAITING_SECOND_EVALUATOR', label: 'Awaiting Secondary' },
  { value: 'MARKS_SUBMITTED',          label: 'Submitted' },
  { value: 'BOARD_FINALISED',          label: 'Finalised' },
]

const STATUS_COLOR: Record<string, string> = {
  PENDING:                   'bg-gray-100 text-gray-600',
  QUALITY_CHECKING:          'bg-amber-100 text-amber-700',
  QUALITY_FAILED:            'bg-red-100 text-red-700',
  OCR_PROCESSING:            'bg-sky-100 text-sky-700',
  PROCESSING:                'bg-blue-100 text-blue-600',
  SCORED:                    'bg-indigo-100 text-indigo-700',
  FAILED:                    'bg-red-100 text-red-700',
  REVIEW_REQUIRED:           'bg-orange-100 text-orange-700',
  WAITING_SECOND_EVALUATOR:  'bg-purple-100 text-purple-700',
  SECONDARY_EVALUATED:       'bg-violet-100 text-violet-700',
  MARKS_SUBMITTED:           'bg-yellow-100 text-yellow-700',
  BOARD_FINALISED:           'bg-emerald-100 text-emerald-700',
}

export default function MyScriptsPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<ScriptStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const limit = 20

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['my-scripts', statusFilter, offset],
    queryFn:  () => listMyScripts({ status: statusFilter || undefined, offset, limit }),
  })

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardList}
        title="My Assigned Scripts"
      />

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

      {isLoading && <PageLoading message="Loading your scripts…" />}
      {isError   && <PageError message="Failed to load scripts." onRetry={() => refetch()} />}

      {data && data.items.length === 0 && (
        <PageEmpty
          icon={ClipboardList}
          message="No scripts assigned to you yet."
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="space-y-3">
            {data.items.map(script => (
              <EvaluatorScriptCard
                key={script.id}
                script={script}
                onEvaluate={() => navigate(`/scripts/${script.id}/evaluate`)}
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
    </PageShell>
  )
}

function EvaluatorScriptCard({
  script,
  onEvaluate,
}: {
  script:     ScannedScript
  onEvaluate: () => void
}) {
  const colorClass  = STATUS_COLOR[script.status] ?? 'bg-gray-100 text-gray-600'
  const canEvaluate = ['SCORED', 'REVIEW_REQUIRED'].includes(script.status)

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
      </div>

      <div className="shrink-0">
        <Button
          size="sm"
          onClick={onEvaluate}
          className={
            canEvaluate
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
              : undefined
          }
          variant={canEvaluate ? 'default' : 'outline'}
        >
          {canEvaluate ? 'Evaluate' : 'View'}
        </Button>
      </div>
    </div>
  )
}
