// M10 Bell Curve Normaliser — Analysis detail: stats, histogram, anomalies, suggestion
import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart2, ChevronLeft, Loader2, AlertTriangle, Info,
  CheckCircle2, XCircle, TrendingUp,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getAnalysis, getAnalysisJobStatus, getGradeSummary, listNormalisedLedger } from '@/lib/api/bellCurve'
import type { AnalysisStatus, AnomalyItem, BellCurveAnalysis, GradeSummaryResponse, HistogramBin, NormalisedScore } from '@/types/bellCurve'
import { useWorkspace } from '@/lib/workspace'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: AnalysisStatus }) {
  const cfg: Record<AnalysisStatus, string> = {
    PENDING:        'bg-gray-100 text-gray-600',
    ANALYSING:      'bg-blue-100 text-blue-700 animate-pulse',
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
// Histogram (SVG)
// ---------------------------------------------------------------------------

function Histogram({ bins }: { bins: HistogramBin[] }) {
  if (!bins.length) return <p className="text-xs text-gray-400">No histogram data.</p>

  const maxCount = Math.max(...bins.map(b => b.count), 1)
  const svgH = 100
  const svgW = 400
  const barW = svgW / bins.length
  const pad  = 2

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full h-28" preserveAspectRatio="none">
        {bins.map((bin, i) => {
          const barH = (bin.count / maxCount) * (svgH - 4)
          return (
            <g key={i}>
              <rect
                x={i * barW + pad / 2}
                y={svgH - barH - 2}
                width={barW - pad}
                height={barH}
                fill="#6366f1"
                fillOpacity={0.75}
                rx={1}
              />
            </g>
          )
        })}
      </svg>
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>{bins[0].bin_start.toFixed(1)}</span>
        <span>Score distribution</span>
        <span>{bins[bins.length - 1].bin_end.toFixed(1)}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stats grid
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-white p-3 text-center">
      <div className="text-base font-bold text-gray-800">{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Anomaly row
// ---------------------------------------------------------------------------

function AnomalyRow({ anomaly }: { anomaly: AnomalyItem }) {
  const isCritical = anomaly.severity === 'CRITICAL'
  return (
    <div className={`rounded-lg border p-3 flex gap-3 text-xs ${
      isCritical
        ? 'border-red-200 bg-red-50 text-red-800'
        : 'border-yellow-200 bg-yellow-50 text-yellow-800'
    }`}>
      <AlertTriangle className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${isCritical ? 'text-red-600' : 'text-yellow-600'}`} />
      <div className="space-y-0.5">
        <span className="font-semibold">{anomaly.type.replace(/_/g, ' ')}</span>
        {' — '}
        {anomaly.description}
        <div className="text-xs opacity-70">
          Threshold: {anomaly.threshold.toFixed(3)} · Observed: {anomaly.observed_value.toFixed(3)}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Grade distribution summary panel (APPLIED status only)
// ---------------------------------------------------------------------------

const GRADE_ORDER   = ['S', 'A', 'B', 'C', 'D', 'P', 'F'] as const
const GRADE_PALETTE: Record<string, { bg: string; text: string; border: string }> = {
  S: { bg: 'bg-indigo-50', text: 'text-indigo-800', border: 'border-indigo-200' },
  A: { bg: 'bg-green-50',  text: 'text-green-800',  border: 'border-green-200'  },
  B: { bg: 'bg-teal-50',   text: 'text-teal-800',   border: 'border-teal-200'   },
  C: { bg: 'bg-blue-50',   text: 'text-blue-800',   border: 'border-blue-200'   },
  D: { bg: 'bg-yellow-50', text: 'text-yellow-800', border: 'border-yellow-200' },
  P: { bg: 'bg-orange-50', text: 'text-orange-800', border: 'border-orange-200' },
  F: { bg: 'bg-red-50',    text: 'text-red-800',    border: 'border-red-200'    },
}

function GradeSummaryPanel({ summary }: { summary: GradeSummaryResponse }) {
  const { total, pass_count, fail_count, pass_rate, grade_counts } = summary
  const passBarWidth = total > 0 ? `${pass_rate}%` : '0%'

  return (
    <div className="space-y-4">
      {/* Grade distribution cards */}
      <div className="grid grid-cols-7 gap-1.5">
        {GRADE_ORDER.map(g => {
          const count = grade_counts[g] ?? 0
          const pal   = GRADE_PALETTE[g]
          const pct   = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0'
          return (
            <div
              key={g}
              className={`rounded-lg border ${pal.border} ${pal.bg} p-2 text-center`}
            >
              <div className={`text-xs font-bold ${pal.text}`}>{g}</div>
              <div className="text-lg font-bold text-gray-800 leading-tight">{count}</div>
              <div className="text-xs text-gray-400">{pct}%</div>
            </div>
          )
        })}
      </div>

      {/* Pass rate bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Pass rate</span>
          <span className="font-semibold text-gray-700">{pass_rate.toFixed(1)}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-green-500 transition-all"
            style={{ width: passBarWidth }}
          />
        </div>
      </div>

      {/* Pass / fail counts */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-lg border border-gray-100 bg-white p-2">
          <div className="text-base font-bold text-gray-800">{total}</div>
          <div className="text-gray-400">Total</div>
        </div>
        <div className="rounded-lg border border-green-100 bg-green-50 p-2">
          <div className="text-base font-bold text-green-700">{pass_count}</div>
          <div className="text-green-600">Pass</div>
        </div>
        <div className="rounded-lg border border-red-100 bg-red-50 p-2">
          <div className="text-base font-bold text-red-700">{fail_count}</div>
          <div className="text-red-500">Fail</div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Grade badge
// ---------------------------------------------------------------------------

const GRADE_COLORS: Record<string, string> = {
  S: 'bg-indigo-100 text-indigo-800',
  A: 'bg-green-100  text-green-800',
  B: 'bg-teal-100   text-teal-800',
  C: 'bg-blue-100   text-blue-800',
  D: 'bg-yellow-100 text-yellow-800',
  P: 'bg-orange-100 text-orange-800',
  F: 'bg-red-100    text-red-800',
}

function GradeBadge({ letter }: { letter: string | null }) {
  if (!letter) return <span className="text-gray-400">—</span>
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${GRADE_COLORS[letter] ?? 'bg-gray-100 text-gray-700'}`}>
      {letter}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Normalised score ledger table (shown when analysis is APPLIED)
// ---------------------------------------------------------------------------

function NormalisedLedger({ paperId }: { paperId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['bell-curve-ledger', paperId],
    queryFn:  () => listNormalisedLedger(paperId, { limit: 200 }),
  })

  if (isLoading) return (
    <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading normalised scores…
    </div>
  )

  const items: NormalisedScore[] = data?.items ?? []
  if (!items.length) return (
    <p className="text-xs text-gray-400">No normalised scores recorded for this paper.</p>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500 uppercase tracking-wide">
            <th className="py-2 pr-4 font-medium">Roll ref</th>
            <th className="py-2 pr-4 font-medium text-right">Raw</th>
            <th className="py-2 pr-4 font-medium text-right">Normalised</th>
            <th className="py-2 pr-4 font-medium text-right">Pct %</th>
            <th className="py-2 pr-4 font-medium text-center">Grade</th>
            <th className="py-2 pr-4 font-medium text-center">Points</th>
            <th className="py-2     font-medium text-center">Pass</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map(s => (
            <tr key={s.id} className="hover:bg-gray-50 transition-colors">
              <td className="py-1.5 pr-4 font-mono text-gray-600">{s.student_roll_ref ?? '—'}</td>
              <td className="py-1.5 pr-4 text-right text-gray-500">{s.raw_score.toFixed(1)}</td>
              <td className="py-1.5 pr-4 text-right font-medium text-gray-800">{s.normalised_score.toFixed(1)}</td>
              <td className="py-1.5 pr-4 text-right text-gray-600">
                {s.pct != null ? `${s.pct.toFixed(1)}%` : '—'}
              </td>
              <td className="py-1.5 pr-4 text-center">
                <GradeBadge letter={s.grade_letter} />
              </td>
              <td className="py-1.5 pr-4 text-center text-gray-600">
                {s.grade_point != null ? s.grade_point.toFixed(1) : '—'}
              </td>
              <td className="py-1.5 text-center">
                {s.is_pass === null ? <span className="text-gray-400">—</span>
                  : s.is_pass
                    ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500 mx-auto" />
                    : <XCircle     className="w-3.5 h-3.5 text-red-500   mx-auto" />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(data?.total ?? 0) > items.length && (
        <p className="text-xs text-gray-400 mt-2">
          Showing {items.length} of {data?.total} scores.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Applied section — grade summary panel + normalised ledger
// ---------------------------------------------------------------------------

function AppliedSection({ paperId }: { paperId: string }) {
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['bell-curve-grade-summary', paperId],
    queryFn:  () => getGradeSummary(paperId),
  })

  return (
    <div className="rounded-xl border border-green-200 bg-green-50 p-5 space-y-5">
      {/* Banner */}
      <div className="flex gap-3 text-sm text-green-800">
        <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-green-600" />
        <span>
          <strong>Board ratified.</strong> Normalised scores are recorded in the bell curve ledger.
          Grades are advisory — raw M09 marks are unchanged.
        </span>
      </div>

      {/* Grade distribution summary */}
      <div className="rounded-lg border border-green-100 bg-white p-4 space-y-1">
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-3">
          Grade Distribution (Advisory)
        </p>
        {summaryLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading summary…
          </div>
        ) : summary ? (
          <GradeSummaryPanel summary={summary} />
        ) : null}
      </div>

      {/* Full ledger table */}
      <div className="rounded-lg border border-green-100 bg-white p-3">
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-3">
          Normalised Score Ledger
        </p>
        <NormalisedLedger paperId={paperId} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job poller (PENDING / ANALYSING)
// ---------------------------------------------------------------------------

function JobPoller({ analysis }: { analysis: BellCurveAnalysis }) {
  const qc = useQueryClient()

  const { data: job } = useQuery({
    queryKey: ['bell-curve-job', analysis.id],
    queryFn:  () => getAnalysisJobStatus(analysis.id),
    refetchInterval: 4000,
    enabled: analysis.status === 'PENDING' || analysis.status === 'ANALYSING',
  })

  useEffect(() => {
    if (job && job.status !== 'PENDING' && job.status !== 'RUNNING') {
      qc.invalidateQueries({ queryKey: ['bell-curve-analysis', analysis.id] })
    }
  }, [job, analysis.id, qc])

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex items-center gap-3 text-sm text-blue-800">
      <Loader2 className="w-4 h-4 animate-spin text-blue-600 shrink-0" />
      <span>
        Analysis running… Job status: <strong>{job?.status ?? '…'}</strong>
        {job?.started_at && (
          <span className="text-xs text-blue-600 ml-2">
            Started {new Date(job.started_at).toLocaleTimeString()}
          </span>
        )}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BellCurveAnalysisPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const isBoard  = role === 'BOARD'
  const canRatify = isBoard

  const { data: analysis, isLoading, isError } = useQuery({
    queryKey: ['bell-curve-analysis', id],
    queryFn:  () => getAnalysis(id!),
    enabled:  !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return (status === 'PENDING' || status === 'ANALYSING') ? 6000 : false
    },
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
    </div>
  )

  if (isError || !analysis) return (
    <div className="max-w-4xl mx-auto p-6 text-red-600 text-sm">
      Failed to load analysis.
    </div>
  )

  const stats     = analysis.raw_stats
  const anomalies = analysis.anomalies ?? []
  const suggestion = analysis.normalisation_suggestion
  const canRatifyNow = canRatify &&
    (analysis.status === 'READY' || analysis.status === 'BOARD_REVIEWED')
  const isTerminal = analysis.status === 'APPLIED' || analysis.status === 'NO_ACTION'

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">

      {/* Back + Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/bell-curve')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <BarChart2 className="w-5 h-5 text-indigo-600 shrink-0" />
            <h1 className="text-xl font-bold text-gray-900">Analysis Detail</h1>
            <StatusBadge status={analysis.status} />
          </div>
          <p className="text-xs text-gray-400 font-mono mt-1 truncate">
            Paper: {analysis.exam_paper_id}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button
            variant="outline" size="sm"
            onClick={() => navigate(`/bell-curve/reports?paper=${analysis.exam_paper_id}`)}
          >
            PDF Report
          </Button>
          {canRatifyNow && (
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={() => navigate(`/bell-curve/${analysis.id}/ratify`)}
            >
              Ratify (Gate 1)
            </Button>
          )}
        </div>
      </div>

      {/* Advisory banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          <strong>Advisory only.</strong> Statistics below are computed from M09 Board-finalised marks.
          Normalised scores are a Board recommendation and do not overwrite the original score ledger.
        </span>
      </div>

      {/* Job poller */}
      {(analysis.status === 'PENDING' || analysis.status === 'ANALYSING') && (
        <JobPoller analysis={analysis} />
      )}

      {/* Ratified / No-action result */}
      {analysis.status === 'APPLIED' && (
        <AppliedSection paperId={analysis.exam_paper_id} />
      )}

      {analysis.status === 'NO_ACTION' && (
        <div className="rounded-xl border border-orange-200 bg-orange-50 p-4 flex gap-3 text-sm text-orange-800">
          <XCircle className="w-4 h-4 shrink-0 mt-0.5 text-orange-600" />
          <span><strong>No action.</strong> Board rejected normalisation. Raw M09 marks stand.</span>
        </div>
      )}

      {analysis.status === 'FAILED' && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 flex gap-3 text-sm text-red-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-600" />
          <span><strong>Analysis failed.</strong> The Celery task encountered an error. Trigger a new analysis.</span>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-500" />
            Score Distribution
            {analysis.score_count != null && (
              <span className="text-xs text-gray-400 font-normal ml-1">({analysis.score_count} scripts)</span>
            )}
          </h2>

          <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
            <StatCard label="Mean"     value={stats.mean.toFixed(2)} />
            <StatCard label="Std Dev"  value={stats.std.toFixed(2)} />
            <StatCard label="Median"   value={stats.median.toFixed(2)} />
            <StatCard label="Min"      value={stats.min.toFixed(1)} />
            <StatCard label="Max"      value={stats.max.toFixed(1)} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            <StatCard label="Q1"       value={stats.q1.toFixed(2)} />
            <StatCard label="Q3"       value={stats.q3.toFixed(2)} />
            <StatCard label="Skewness" value={stats.skewness.toFixed(3)} />
            <StatCard label="Kurtosis" value={stats.kurtosis.toFixed(3)} />
          </div>

          {stats.histogram.length > 0 && (
            <div className="mt-2">
              <Histogram bins={stats.histogram} />
            </div>
          )}
        </div>
      )}

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-700">
            Anomalies ({anomalies.length})
          </h2>
          {anomalies.map((a, i) => <AnomalyRow key={i} anomaly={a} />)}
        </div>
      )}

      {/* AI Normalisation Suggestion */}
      {suggestion && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-indigo-900 flex items-center gap-2">
            <Info className="w-4 h-4 text-indigo-600" />
            AI Normalisation Suggestion (Advisory)
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full">
              {suggestion.method.replace(/_/g, ' ')}
            </span>
            {Object.keys(suggestion.params).length > 0 && (
              <span className="text-xs text-indigo-600">
                {JSON.stringify(suggestion.params)}
              </span>
            )}
          </div>
          <p className="text-sm text-indigo-800">{suggestion.reasoning}</p>

          {suggestion.projected_stats && (
            <div>
              <p className="text-xs font-medium text-indigo-700 mb-2">Projected outcome:</p>
              <div className="grid grid-cols-3 gap-2">
                <StatCard label="Proj. Mean"   value={suggestion.projected_stats.mean.toFixed(2)} />
                <StatCard label="Proj. Median" value={suggestion.projected_stats.median.toFixed(2)} />
                <StatCard label="Proj. Std"    value={suggestion.projected_stats.std.toFixed(2)} />
              </div>
            </div>
          )}

          {!isTerminal && canRatifyNow && (
            <Button
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full mt-2"
              onClick={() => navigate(`/bell-curve/${analysis.id}/ratify`)}
            >
              Review and Ratify →
            </Button>
          )}
        </div>
      )}

      {/* Cross-evaluator stats */}
      {(analysis.cross_evaluator_stats ?? []).length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">Cross-Evaluator Consistency</h2>
          <div className="space-y-2">
            {analysis.cross_evaluator_stats!.map(ev => (
              <div
                key={ev.evaluator_id}
                className={`flex items-center gap-3 rounded-lg border p-2 text-xs ${
                  ev.is_outlier
                    ? 'border-red-200 bg-red-50 text-red-800'
                    : 'border-gray-100 bg-white text-gray-700'
                }`}
              >
                <span className="font-mono text-gray-400 shrink-0 truncate max-w-[120px]">
                  {ev.evaluator_id.slice(0, 8)}…
                </span>
                <span>Mean {ev.mean.toFixed(1)}</span>
                <span>Std {ev.std.toFixed(1)}</span>
                <span>n={ev.count}</span>
                <span>z={ev.z_score.toFixed(2)}</span>
                {ev.is_outlier && (
                  <span className="ml-auto text-red-600 font-semibold">Outlier</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
