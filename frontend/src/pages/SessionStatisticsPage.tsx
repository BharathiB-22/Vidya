// M09.5 Dean — Per-session score statistics
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  BarChart2, ChevronLeft, Users, Award, TrendingUp, TrendingDown,
  Target, CheckCircle2, XCircle, RefreshCw, Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useSessionAnalytics } from '@/hooks/digitalExams'
import type { DigitalScoreBucket } from '@/types/digitalExam'

const PASS_OPTIONS = [30, 35, 40, 45, 50] as const

function StatCard({
  label, value, sub, icon: Icon, colorClass,
}: {
  label: string
  value: string | number
  sub?: string
  icon: typeof Users
  colorClass: string
}) {
  return (
    <div className={`rounded-xl border px-4 py-4 space-y-1.5 ${colorClass}`}>
      <Icon className="h-4 w-4 opacity-70" />
      <p className="text-2xl font-bold">{value ?? '—'}</p>
      <p className="text-xs font-medium opacity-80">{label}</p>
      {sub && <p className="text-xs opacity-60">{sub}</p>}
    </div>
  )
}

function ScoreHistogram({ buckets, passThreshold }: { buckets: DigitalScoreBucket[]; passThreshold: number }) {
  const maxCount = Math.max(...buckets.map(b => b.count), 1)

  return (
    <div className="space-y-2">
      {buckets.map(b => {
        const barPct = (b.count / maxCount) * 100
        const isPass = b.pct_lo >= passThreshold
        return (
          <div key={b.label} className="flex items-center gap-3 group">
            <span className="w-16 text-right text-xs text-gray-500 shrink-0">{b.label}</span>
            <div className="flex-1 h-7 bg-gray-100 rounded-md overflow-hidden relative">
              <div
                className={`h-full rounded-md transition-all ${isPass ? 'bg-green-400' : 'bg-red-300'}`}
                style={{ width: `${barPct}%` }}
              />
              {b.count > 0 && (
                <span className="absolute inset-0 flex items-center px-2 text-xs font-medium text-gray-700">
                  {b.count}
                </span>
              )}
            </div>
            <span className="w-4 text-xs text-gray-400 shrink-0">{b.count}</span>
          </div>
        )
      })}
      <div className="flex items-center gap-3 pt-1">
        <span className="w-16" />
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-300" />
            Below threshold
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-green-400" />
            Pass zone
          </span>
        </div>
      </div>
    </div>
  )
}

function PassFailDonut({ passCount, failCount }: { passCount: number; failCount: number }) {
  const total = passCount + failCount
  if (total === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-gray-400 text-sm">
        No scored attempts
      </div>
    )
  }
  const passPct = Math.round((passCount / total) * 100)
  const failPct = 100 - passPct

  // Simple horizontal stacked bar
  return (
    <div className="space-y-4">
      <div className="flex h-8 rounded-full overflow-hidden gap-0.5">
        {passCount > 0 && (
          <div
            className="h-full bg-green-500 flex items-center justify-center text-white text-xs font-semibold"
            style={{ width: `${passPct}%` }}
          >
            {passPct >= 12 ? `${passPct}%` : ''}
          </div>
        )}
        {failCount > 0 && (
          <div
            className="h-full bg-red-400 flex items-center justify-center text-white text-xs font-semibold"
            style={{ width: `${failPct}%` }}
          >
            {failPct >= 12 ? `${failPct}%` : ''}
          </div>
        )}
      </div>
      <div className="flex justify-around text-sm">
        <div className="text-center space-y-0.5">
          <div className="flex items-center gap-1.5 justify-center">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span className="font-bold text-gray-800 text-lg">{passCount}</span>
          </div>
          <p className="text-xs text-gray-500">Passed ({passPct}%)</p>
        </div>
        <div className="text-center space-y-0.5">
          <div className="flex items-center gap-1.5 justify-center">
            <XCircle className="h-4 w-4 text-red-400" />
            <span className="font-bold text-gray-800 text-lg">{failCount}</span>
          </div>
          <p className="text-xs text-gray-500">Failed ({failPct}%)</p>
        </div>
      </div>
    </div>
  )
}

export default function SessionStatisticsPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate       = useNavigate()
  const sid            = sessionId ?? ''

  const [passThreshold, setPassThreshold] = useState(40)

  const { data, isLoading, isError, refetch, isFetching } = useSessionAnalytics(sid, passThreshold)

  if (isLoading) return <PageLoading />
  if (isError || !data) return <PageError onRetry={refetch} />

  const hasScores = data.scored_count > 0

  return (
    <PageShell>
      <PageHeader
        icon={BarChart2}
        title={data.title}
        subtitle="Session score statistics"
        action={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />

      <div className="max-w-3xl space-y-6">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-1"
          onClick={() => navigate('/exams/digital/analytics')}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Analytics Overview
        </Button>

        {/* Participation stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Attempts"
            value={data.attempt_count}
            sub="total enrolled"
            icon={Users}
            colorClass="border-indigo-100 bg-indigo-50 text-indigo-700"
          />
          <StatCard
            label="Scored"
            value={data.scored_count}
            sub={data.attempt_count > 0 ? `${Math.round(data.scored_count / data.attempt_count * 100)}% complete` : undefined}
            icon={Award}
            colorClass="border-teal-100 bg-teal-50 text-teal-700"
          />
          <StatCard
            label="In Progress"
            value={data.in_progress_count}
            icon={Loader2}
            colorClass="border-amber-100 bg-amber-50 text-amber-700"
          />
          <StatCard
            label="Pass Rate"
            value={data.pass_rate_pct != null ? `${data.pass_rate_pct}%` : '—'}
            sub={`at ${data.pass_threshold_pct}% threshold`}
            icon={Target}
            colorClass={
              data.pass_rate_pct == null
                ? 'border-gray-100 bg-gray-50 text-gray-500'
                : data.pass_rate_pct >= 70
                ? 'border-green-100 bg-green-50 text-green-700'
                : data.pass_rate_pct >= 50
                ? 'border-amber-100 bg-amber-50 text-amber-700'
                : 'border-red-100 bg-red-50 text-red-700'
            }
          />
        </div>

        {/* Score summary */}
        {hasScores && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="Average"
              value={data.avg_score_pct != null ? `${data.avg_score_pct}%` : '—'}
              icon={TrendingUp}
              colorClass="border-purple-100 bg-purple-50 text-purple-700"
            />
            <StatCard
              label="Median"
              value={data.median_score_pct != null ? `${data.median_score_pct}%` : '—'}
              icon={BarChart2}
              colorClass="border-blue-100 bg-blue-50 text-blue-700"
            />
            <StatCard
              label="Highest"
              value={data.max_score_pct != null ? `${data.max_score_pct}%` : '—'}
              icon={TrendingUp}
              colorClass="border-green-100 bg-green-50 text-green-700"
            />
            <StatCard
              label="Lowest"
              value={data.min_score_pct != null ? `${data.min_score_pct}%` : '—'}
              icon={TrendingDown}
              colorClass="border-red-100 bg-red-50 text-red-700"
            />
          </div>
        )}

        {!hasScores && (
          <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-12 text-center space-y-2">
            <Award className="h-8 w-8 mx-auto text-gray-300" />
            <p className="text-sm text-gray-500">No scored attempts yet.</p>
            <p className="text-xs text-gray-400">
              Score analytics will appear once students submit and MCQ auto-scoring runs.
            </p>
          </div>
        )}

        {hasScores && (
          <>
            {/* Pass / fail distribution */}
            <div className="rounded-xl border border-gray-200 bg-white px-5 py-5 space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h2 className="text-sm font-semibold text-gray-800">Pass / Fail Distribution</h2>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500">Pass threshold:</span>
                  <div className="flex gap-1">
                    {PASS_OPTIONS.map(t => (
                      <button
                        key={t}
                        onClick={() => setPassThreshold(t)}
                        className={`px-2 py-0.5 rounded-md border text-xs font-medium transition-colors ${
                          passThreshold === t
                            ? 'bg-indigo-600 text-white border-indigo-600'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                        }`}
                      >
                        {t}%
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <PassFailDonut passCount={data.pass_count} failCount={data.fail_count} />
            </div>

            {/* Score histogram */}
            <div className="rounded-xl border border-gray-200 bg-white px-5 py-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-800">Score Distribution</h2>
                <span className="text-xs text-gray-400">
                  Pass zone ≥ {passThreshold}% (green)
                </span>
              </div>
              <ScoreHistogram
                buckets={data.score_buckets}
                passThreshold={passThreshold}
              />
            </div>

            {/* Info footnote */}
            <p className="text-xs text-gray-400 px-1">
              Scores are MCQ auto-scores only. Subjective answers are not included in these analytics.
            </p>
          </>
        )}
      </div>
    </PageShell>
  )
}
