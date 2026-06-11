// M09.5 Admin — Digital Exam Session Management
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Monitor, Plus, Activity, ChevronRight, Loader2, RefreshCw,
  Search,
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

const STATUS_LABELS: Record<DigitalSessionStatus, string> = {
  DRAFT:  'Draft',
  ACTIVE: 'Active',
  CLOSED: 'Closed',
}

type FilterStatus = DigitalSessionStatus | ''

function SessionRow({ session }: { session: DigitalExamSession }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(`/exams/digital/${session.id}`)}
      className="w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border border-gray-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/30 text-left transition-colors group"
    >
      <Monitor className="h-4 w-4 text-gray-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{session.title}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {session.max_duration_mins} min
          {session.window_start && (
            <> · from {new Date(session.window_start).toLocaleString()}</>
          )}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <div className="hidden sm:flex items-center gap-2 text-xs text-gray-500">
          <span>{session.attempt_count} attempts</span>
          <span>·</span>
          <span>{session.scored_count} scored</span>
        </div>
        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[session.status]}`}>
          {session.status === 'ACTIVE' && (
            <span className="mr-1 h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
          )}
          {STATUS_LABELS[session.status]}
        </span>
        <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-indigo-500 transition-colors" />
      </div>
    </button>
  )
}

export default function DigitalSessionsPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<FilterStatus>('')
  const [search, setSearch] = useState('')

  const { data, isLoading, isError, refetch, isFetching } = useDigitalSessions({ limit: 200 })

  const all = data?.items ?? []
  const active  = all.filter(s => s.status === 'ACTIVE').length
  const draft   = all.filter(s => s.status === 'DRAFT').length
  const closed  = all.filter(s => s.status === 'CLOSED').length
  const totalAttempts = all.reduce((sum, s) => sum + s.attempt_count, 0)

  const visible = all
    .filter(s => !filter || s.status === filter)
    .filter(s => !search || s.title.toLowerCase().includes(search.toLowerCase()))

  if (isLoading) return <PageLoading />
  if (isError)   return <PageError onRetry={refetch} />

  return (
    <PageShell>
      <PageHeader
        icon={Monitor}
        title="Digital Exam Sessions"
        subtitle="Create and manage online exam delivery sessions"
        action={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate('/exams/digital/monitoring')}>
              <Activity className="h-4 w-4 mr-1.5" />
              Monitoring
            </Button>
            <Button size="sm" onClick={() => navigate('/exams/digital/create')}>
              <Plus className="h-4 w-4 mr-1.5" />
              New Session
            </Button>
          </div>
        }
      />

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Active',   value: active,        color: 'text-green-600' },
          { label: 'Draft',    value: draft,         color: 'text-gray-500' },
          { label: 'Closed',   value: closed,        color: 'text-slate-500' },
          { label: 'Attempts', value: totalAttempts, color: 'text-indigo-600' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-gray-100 bg-white px-4 py-3 space-y-0.5">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search sessions…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
        <div className="flex gap-1.5">
          {(['', 'ACTIVE', 'DRAFT', 'CLOSED'] as FilterStatus[]).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                filter === f
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
              }`}
            >
              {f === '' ? 'All' : STATUS_LABELS[f as DigitalSessionStatus]}
            </button>
          ))}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="px-2 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-500 hover:border-indigo-300 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* List */}
      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-16 text-center space-y-3">
          <Monitor className="h-8 w-8 mx-auto text-gray-300" />
          <p className="text-sm text-gray-500">
            {all.length === 0 ? 'No sessions yet.' : 'No sessions match the filter.'}
          </p>
          {all.length === 0 && (
            <Button size="sm" onClick={() => navigate('/exams/digital/create')}>
              <Plus className="h-4 w-4 mr-1" />
              Create First Session
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map(s => <SessionRow key={s.id} session={s} />)}
        </div>
      )}

      {isFetching && (
        <div className="flex justify-center pt-4">
          <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
        </div>
      )}
    </PageShell>
  )
}
