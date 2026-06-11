// M09.5 Dean — Digital Exam Analytics Overview
import { useNavigate } from 'react-router-dom'
import {
  BarChart2, Monitor, Users, Award, TrendingUp,
  ChevronRight, RefreshCw, Loader2, CheckCircle2, AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useDigitalSessions } from '@/hooks/digitalExams'
import type { DigitalExamSession, DigitalSessionStatus } from '@/types/digitalExam'

const STATUS_COLORS: Record<DigitalSessionStatus, string> = {
  DRAFT:  'bg-gray-100 text-gray-600',
  ACTIVE: 'bg-green-100 text-green-700',
  CLOSED: 'bg-slate-100 text-slate-600',
}

function completionPct(s: DigitalExamSession): number {
  if (s.attempt_count === 0) return 0
  return Math.round((s.scored_count / s.attempt_count) * 100)
}

function SessionAnalyticsRow({ session }: { session: DigitalExamSession }) {
  const navigate = useNavigate()
  const pct = completionPct(session)

  return (
    <tr
      className="hover:bg-indigo-50/40 cursor-pointer transition-colors group"
      onClick={() => navigate(`/exams/digital/analytics/${session.id}`)}
    >
      <td className="px-4 py-3.5 max-w-xs">
        <p className="text-sm font-medium text-gray-900 truncate">{session.title}</p>
      </td>
      <td className="px-4 py-3.5">
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[session.status]}`}>
          {session.status === 'ACTIVE' && (
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
          )}
          {session.status}
        </span>
      </td>
      <td className="px-4 py-3.5 text-sm text-gray-700 text-right font-medium">
        {session.attempt_count}
      </td>
      <td className="px-4 py-3.5 text-sm text-gray-700 text-right">
        {session.scored_count}
      </td>
      <td className="px-4 py-3.5 w-40">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                pct === 100 ? 'bg-green-500' : pct > 0 ? 'bg-indigo-500' : 'bg-gray-200'
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
        </div>
      </td>
      <td className="px-4 py-3.5 text-right">
        {session.status === 'CLOSED' && session.scored_count > 0 ? (
          <span className="text-xs font-medium text-indigo-600 group-hover:underline flex items-center justify-end gap-0.5">
            View stats <ChevronRight className="h-3 w-3" />
          </span>
        ) : (
          <span className="text-xs text-gray-300">—</span>
        )}
      </td>
    </tr>
  )
}

export default function DeanDigitalAnalyticsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useDigitalSessions({ limit: 200 })

  const all    = data?.items ?? []
  const active = all.filter(s => s.status === 'ACTIVE')
  const closed = all.filter(s => s.status === 'CLOSED')

  const totalAttempts  = all.reduce((n, s) => n + s.attempt_count, 0)
  const totalScored    = all.reduce((n, s) => n + s.scored_count, 0)
  const scoredSessions = closed.filter(s => s.scored_count > 0)
  const overallCompletionPct = totalAttempts > 0
    ? Math.round((totalScored / totalAttempts) * 100)
    : 0

  // Sort: ACTIVE → then closed by scored_count desc, then draft
  const sorted = [...all].sort((a, b) => {
    const order = { ACTIVE: 0, CLOSED: 1, DRAFT: 2 }
    if (order[a.status] !== order[b.status]) return order[a.status] - order[b.status]
    return b.scored_count - a.scored_count
  })

  if (isLoading) return <PageLoading />
  if (isError)   return <PageError onRetry={refetch} />

  return (
    <PageShell>
      <PageHeader
        icon={BarChart2}
        title="Digital Exam Analytics"
        subtitle="Session-level participation and scoring overview"
        action={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Total Sessions',  value: all.length,           icon: Monitor,      color: 'text-gray-700',   bg: 'bg-gray-50',    border: 'border-gray-200'   },
          { label: 'Active Now',      value: active.length,         icon: TrendingUp,   color: 'text-green-700',  bg: 'bg-green-50',   border: 'border-green-200'  },
          { label: 'Total Attempts',  value: totalAttempts,         icon: Users,        color: 'text-indigo-700', bg: 'bg-indigo-50',  border: 'border-indigo-200' },
          { label: 'Scored',          value: `${totalScored} (${overallCompletionPct}%)`, icon: Award, color: 'text-teal-700', bg: 'bg-teal-50', border: 'border-teal-200' },
        ].map(c => (
          <div key={c.label} className={`rounded-xl border ${c.border} ${c.bg} px-4 py-3.5 flex flex-col gap-1.5`}>
            <c.icon className={`h-4 w-4 ${c.color}`} />
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-xs text-gray-500">{c.label}</p>
          </div>
        ))}
      </div>

      {/* Sessions awaiting analytics */}
      {scoredSessions.length > 0 && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 mb-4 flex items-center gap-3">
          <CheckCircle2 className="h-4 w-4 text-indigo-500 shrink-0" />
          <p className="text-sm text-indigo-800">
            <span className="font-semibold">{scoredSessions.length}</span> session{scoredSessions.length > 1 ? 's' : ''} have scored results — click a row to view detailed statistics.
          </p>
        </div>
      )}

      {/* Sessions table */}
      {all.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-16 text-center space-y-2">
          <Monitor className="h-8 w-8 mx-auto text-gray-300" />
          <p className="text-sm text-gray-500">No digital exam sessions found.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">All Sessions</h2>
            {isFetching && <Loader2 className="h-4 w-4 animate-spin text-gray-300" />}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {['Session', 'Status', 'Attempts', 'Scored', 'Completion', ''].map(h => (
                    <th
                      key={h}
                      className={`px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide ${
                        h === 'Attempts' || h === 'Scored' ? 'text-right' : ''
                      }`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {sorted.map(s => <SessionAnalyticsRow key={s.id} session={s} />)}
              </tbody>
            </table>
          </div>

          {/* Footnote hint */}
          <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
            <p className="text-xs text-gray-400 flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3" />
              Detailed score analytics are available only for CLOSED sessions with scored results.
            </p>
          </div>
        </div>
      )}
    </PageShell>
  )
}
