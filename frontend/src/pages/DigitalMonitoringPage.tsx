// M09.5 Admin — Digital Exam Monitoring Dashboard
import { useNavigate } from 'react-router-dom'
import {
  Activity, Monitor, Users, Award, ChevronLeft,
  RefreshCw, Loader2, CheckCircle2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useDigitalSessions } from '@/hooks/digitalExams'
import type { DigitalSessionStatus, DigitalExamSession } from '@/types/digitalExam'

const STATUS_COLORS: Record<DigitalSessionStatus, string> = {
  DRAFT:  'bg-gray-100 text-gray-600',
  ACTIVE: 'bg-green-100 text-green-700',
  CLOSED: 'bg-slate-100 text-slate-600',
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.min(100, Math.round((value / max) * 100))
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

function SessionMonitorRow({ session }: { session: DigitalExamSession }) {
  const navigate = useNavigate()
  return (
    <tr
      className="hover:bg-gray-50 cursor-pointer transition-colors"
      onClick={() => navigate(`/exams/digital/${session.id}`)}
    >
      <td className="px-4 py-3 max-w-xs">
        <p className="text-sm font-medium text-gray-900 truncate">{session.title}</p>
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[session.status]}`}>
          {session.status === 'ACTIVE' && (
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
          )}
          {session.status}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-700 text-right">{session.attempt_count}</td>
      <td className="px-4 py-3 text-sm text-gray-700 text-right">{session.scored_count}</td>
      <td className="px-4 py-3 w-40">
        <ProgressBar value={session.scored_count} max={session.attempt_count} />
      </td>
    </tr>
  )
}

export default function DigitalMonitoringPage() {
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch, isFetching } = useDigitalSessions({ limit: 200 })

  const all      = data?.items ?? []
  const active   = all.filter(s => s.status === 'ACTIVE')
  const draft    = all.filter(s => s.status === 'DRAFT')
  const closed   = all.filter(s => s.status === 'CLOSED')

  const totalAttempts     = all.reduce((n, s) => n + s.attempt_count, 0)
  const totalScored       = all.reduce((n, s) => n + s.scored_count, 0)
  const inProgressEst     = active.reduce((n, s) => n + Math.max(0, s.attempt_count - s.scored_count), 0)
  const scoringCompletePct = totalAttempts > 0
    ? Math.round((totalScored / totalAttempts) * 100)
    : 0

  // Sort: ACTIVE first, then DRAFT, then CLOSED
  const ORDER: Record<DigitalSessionStatus, number> = { ACTIVE: 0, DRAFT: 1, CLOSED: 2 }
  const sorted = [...all].sort((a, b) => ORDER[a.status] - ORDER[b.status])

  if (isLoading) return <PageLoading />
  if (isError)   return <PageError onRetry={refetch} />

  return (
    <PageShell>
      <PageHeader
        icon={Activity}
        title="Exam Monitoring Dashboard"
        subtitle="Aggregate view across all digital exam sessions"
        action={
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={`h-4 w-4 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button size="sm" onClick={() => navigate('/exams/digital')}>
              <Monitor className="h-4 w-4 mr-1.5" />
              Sessions
            </Button>
          </div>
        }
      />

      <Button
        variant="ghost"
        size="sm"
        className="-ml-1 mb-4"
        onClick={() => navigate('/exams/digital')}
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back to Sessions
      </Button>

      {/* Aggregate stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="rounded-xl border border-green-100 bg-green-50 px-4 py-4 space-y-1">
          <div className="flex items-center gap-1.5">
            <Activity className="h-4 w-4 text-green-600" />
            <span className="text-xs text-green-700 font-medium">Active Now</span>
          </div>
          <p className="text-3xl font-bold text-green-700">{active.length}</p>
          <p className="text-xs text-green-600">
            {inProgressEst} student{inProgressEst !== 1 ? 's' : ''} in progress
          </p>
        </div>

        <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-4 space-y-1">
          <div className="flex items-center gap-1.5">
            <Users className="h-4 w-4 text-indigo-600" />
            <span className="text-xs text-indigo-700 font-medium">Total Attempts</span>
          </div>
          <p className="text-3xl font-bold text-indigo-700">{totalAttempts}</p>
          <p className="text-xs text-indigo-600">across all sessions</p>
        </div>

        <div className="rounded-xl border border-teal-100 bg-teal-50 px-4 py-4 space-y-1">
          <div className="flex items-center gap-1.5">
            <Award className="h-4 w-4 text-teal-600" />
            <span className="text-xs text-teal-700 font-medium">Scored</span>
          </div>
          <p className="text-3xl font-bold text-teal-700">{totalScored}</p>
          <p className="text-xs text-teal-600">{scoringCompletePct}% complete</p>
        </div>

        <div className="rounded-xl border border-gray-100 bg-white px-4 py-4 space-y-1">
          <div className="flex items-center gap-1.5">
            <Monitor className="h-4 w-4 text-gray-500" />
            <span className="text-xs text-gray-600 font-medium">Sessions</span>
          </div>
          <p className="text-3xl font-bold text-gray-700">{all.length}</p>
          <p className="text-xs text-gray-500">
            {draft.length} draft · {closed.length} closed
          </p>
        </div>
      </div>

      {/* Sessions table */}
      {sorted.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-16 text-center space-y-2">
          <Monitor className="h-8 w-8 mx-auto text-gray-500" />
          <p className="text-sm text-gray-500">No sessions to monitor.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">All Sessions</h2>
            {isFetching && <Loader2 className="h-4 w-4 animate-spin text-gray-600" />}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Session</th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide text-right">Attempts</th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide text-right">Scored</th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Progress</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {sorted.map(s => <SessionMonitorRow key={s.id} session={s} />)}
              </tbody>
            </table>
          </div>
          {totalAttempts > 0 && (
            <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between bg-gray-50">
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <CheckCircle2 className="h-3.5 w-3.5 text-teal-500" />
                {totalScored} of {totalAttempts} attempts scored ({scoringCompletePct}%)
              </div>
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
