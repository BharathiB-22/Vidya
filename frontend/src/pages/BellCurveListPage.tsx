// M10 Bell Curve Normaliser — Analysis list + trigger
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BarChart2, ChevronRight, Loader2, AlertTriangle, Info, PlusCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { listAnalyses, triggerAnalysis } from '@/lib/api/bellCurve'
import { getErrorMessage } from '@/lib/api'
import type { BellCurveAnalysis, AnalysisStatus } from '@/types/bellCurve'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: AnalysisStatus }) {
  const cfg: Record<AnalysisStatus, string> = {
    PENDING:        'bg-gray-100 text-gray-600',
    ANALYSING:      'bg-blue-100 text-blue-700',
    READY:          'bg-yellow-100 text-yellow-700',
    BOARD_REVIEWED: 'bg-indigo-100 text-indigo-700',
    APPLIED:        'bg-green-100 text-green-700',
    NO_ACTION:      'bg-orange-100 text-orange-700',
    FAILED:         'bg-red-100 text-red-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Trigger dialog (inline)
// ---------------------------------------------------------------------------

function TriggerPanel({ onDone }: { onDone: () => void }) {
  const [paperId, setPaperId] = useState('')
  const [error, setError]     = useState<string | null>(null)

  const mut = useMutation({
    mutationFn: () => triggerAnalysis({ exam_paper_id: paperId.trim() }),
    onSuccess: () => { setError(null); onDone() },
    onError:   (err) => setError(getErrorMessage(err)),
  })

  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 space-y-3">
      <p className="text-sm font-medium text-indigo-900">Trigger Bell Curve Analysis</p>
      <p className="text-xs text-indigo-700">
        All scanned scripts for the exam paper must be Board-finalised before analysis can start.
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={paperId}
          onChange={e => setPaperId(e.target.value)}
          placeholder="Exam paper UUID…"
          className="flex-1 border border-indigo-200 rounded-lg px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <Button
          size="sm"
          onClick={() => { setError(null); mut.mutate() }}
          disabled={!paperId.trim() || mut.isPending}
          className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
        >
          {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlusCircle className="w-3.5 h-3.5" />}
          Trigger
        </Button>
      </div>
      {error && (
        <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Analysis card
// ---------------------------------------------------------------------------

function AnalysisCard({ analysis }: { analysis: BellCurveAnalysis }) {
  const navigate = useNavigate()
  const canRatify = analysis.status === 'READY' || analysis.status === 'BOARD_REVIEWED'
  const role = localStorage.getItem('vidya_role') ?? ''
  const isBoard = role === 'BOARD'

  return (
    <div
      className="rounded-xl border border-gray-200 bg-white p-4 hover:border-indigo-200 cursor-pointer transition-colors"
      onClick={() => navigate(`/bell-curve/${analysis.id}`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={analysis.status} />
            {analysis.score_count != null && (
              <span className="text-xs text-gray-400">{analysis.score_count} scripts</span>
            )}
          </div>
          <p className="text-xs text-gray-500 font-mono truncate">
            Paper: {analysis.exam_paper_id}
          </p>
          {analysis.raw_stats && (
            <p className="text-xs text-gray-500">
              Mean {analysis.raw_stats.mean.toFixed(1)} · Std {analysis.raw_stats.std.toFixed(1)} ·
              Median {analysis.raw_stats.median.toFixed(1)}
            </p>
          )}
          {analysis.triggered_at && (
            <p className="text-xs text-gray-400">
              Triggered {new Date(analysis.triggered_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          {isBoard && canRatify && (
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs"
              onClick={e => { e.stopPropagation(); navigate(`/bell-curve/${analysis.id}/ratify`) }}
            >
              Ratify
            </Button>
          )}
          <ChevronRight className="w-4 h-4 text-gray-400" />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BellCurveListPage() {
  const navigate  = useNavigate()
  const qc        = useQueryClient()
  const role      = localStorage.getItem('vidya_role') ?? ''
  const canTrigger = role === 'BOARD' || role === 'ADMIN'

  const [offset, setOffset]       = useState(0)
  const [showTrigger, setShowTrigger] = useState(false)
  const limit = 15

  const { data, isLoading, isError } = useQuery({
    queryKey: ['bell-curve-analyses', offset],
    queryFn:  () => listAnalyses({ offset, limit }),
  })

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">Bell Curve Analyses</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/bell-curve/reports')}
          >
            Fairness Report
          </Button>
          {canTrigger && (
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
              onClick={() => setShowTrigger(v => !v)}
            >
              <PlusCircle className="w-3.5 h-3.5" />
              New Analysis
            </Button>
          )}
        </div>
      </div>

      {/* Advisory banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          <strong>Advisory only.</strong> Bell curve normalisation is a Board-level advisory tool.
          Raw M09 marks are immutable. Normalised scores are stored separately and never replace the original
          score ledger.
        </span>
      </div>

      {/* Trigger panel */}
      {showTrigger && canTrigger && (
        <TriggerPanel onDone={() => {
          setShowTrigger(false)
          qc.invalidateQueries({ queryKey: ['bell-curve-analyses'] })
        }} />
      )}

      {/* List */}
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-12 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading analyses…
        </div>
      )}

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-600 text-sm">
          Failed to load analyses. Please try again.
        </div>
      )}

      {data && (
        <>
          {data.items.length === 0 ? (
            <div className="text-center text-gray-400 py-16">
              No bell curve analyses yet.
              {canTrigger && (
                <p className="mt-2 text-sm">
                  Use <strong>New Analysis</strong> to trigger analysis for a Board-finalised exam paper.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {data.items.map(a => <AnalysisCard key={a.id} analysis={a} />)}
            </div>
          )}

          {data.total > limit && (
            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline" size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-500">
                {Math.min(offset + 1, data.total)}–{Math.min(offset + limit, data.total)} of {data.total}
              </span>
              <Button
                variant="outline" size="sm"
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
