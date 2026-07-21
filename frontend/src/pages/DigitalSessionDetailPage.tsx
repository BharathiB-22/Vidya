// M09.5 Admin — Digital Exam Session Detail
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, Monitor, Clock, Calendar, CheckCircle2,
  PlayCircle, XCircle, Loader2, AlertTriangle, Users, Award,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useDigitalSession, useActivateSession, useCloseSession } from '@/hooks/digitalExams'
import { getErrorMessage } from '@/lib/api'
import type { DigitalSessionStatus } from '@/types/digitalExam'

const STATUS_COLORS: Record<DigitalSessionStatus, string> = {
  DRAFT:  'bg-gray-100 text-gray-700',
  ACTIVE: 'bg-green-100 text-green-700',
  CLOSED: 'bg-slate-100 text-slate-600',
}

function fmt(dt: string | null): string {
  if (!dt) return '—'
  return new Date(dt).toLocaleString()
}

export default function DigitalSessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate      = useNavigate()
  const sid           = sessionId ?? ''

  const { data: session, isLoading, isError, refetch } = useDigitalSession(sid)

  const { mutate: activate, isPending: activating } = useActivateSession()
  const { mutate: close,    isPending: closing    } = useCloseSession()

  const [confirmActivate, setConfirmActivate] = useState(false)
  const [confirmClose,    setConfirmClose]    = useState(false)
  const [actionError,     setActionError]     = useState('')

  if (isLoading) return <PageLoading />
  if (isError || !session) return <PageError onRetry={refetch} />

  const scoredPct = session.attempt_count > 0
    ? Math.round((session.scored_count / session.attempt_count) * 100)
    : 0

  return (
    <PageShell>
      <PageHeader
        icon={Monitor}
        title={session.title}
        subtitle="Digital exam session"
        action={
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_COLORS[session.status]}`}>
            {session.status === 'ACTIVE' && (
              <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            )}
            {session.status}
          </span>
        }
      />

      <div className="max-w-2xl space-y-5">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-1"
          onClick={() => navigate('/exams/digital')}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          All Sessions
        </Button>

        {/* Stats cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Attempts',      value: session.attempt_count, icon: Users,        color: 'text-indigo-600' },
            { label: 'Scored',        value: session.scored_count,  icon: Award,        color: 'text-green-600'  },
            { label: 'Duration',      value: `${session.max_duration_mins}m`, icon: Clock, color: 'text-amber-600' },
            { label: 'Scored %',      value: `${scoredPct}%`,       icon: CheckCircle2, color: 'text-teal-600'   },
          ].map(c => (
            <div key={c.label} className="rounded-xl border border-gray-100 bg-white px-4 py-3 flex flex-col gap-1">
              <c.icon className={`h-4 w-4 ${c.color}`} />
              <p className={`text-xl font-bold ${c.color}`}>{c.value}</p>
              <p className="text-xs text-gray-500">{c.label}</p>
            </div>
          ))}
        </div>

        {/* Info card */}
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
          {[
            { label: 'Status',     value: session.status },
            { label: 'Created',    value: fmt(session.created_at) },
            { label: 'Activated',  value: fmt(session.activated_at) },
            { label: 'Closed',     value: fmt(session.closed_at) },
            { label: 'Window opens',  value: fmt(session.window_start) },
            { label: 'Window closes', value: fmt(session.window_end) },
          ].map(row => (
            <div key={row.label} className="flex items-center gap-4 px-5 py-3">
              <span className="w-32 text-xs font-medium text-gray-500 shrink-0">{row.label}</span>
              <span className="text-sm text-gray-800">{row.value}</span>
            </div>
          ))}

          {session.instructions && (
            <div className="px-5 py-4 space-y-1.5">
              <p className="text-xs font-medium text-gray-500">Instructions</p>
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{session.instructions}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        {actionError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {actionError}
          </div>
        )}

        {session.status === 'DRAFT' && (
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 space-y-3">
            <div className="flex items-start gap-3">
              <Monitor className="h-5 w-5 text-indigo-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-indigo-800">Session is in Draft</p>
                <p className="text-xs text-indigo-700">
                  Activate to allow students to enter the exam. You can close it later.
                </p>
              </div>
            </div>
            <Button
              onClick={() => setConfirmActivate(true)}
              disabled={activating}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              {activating ? (
                <><Loader2 className="h-4 w-4 animate-spin mr-1.5" />Activating…</>
              ) : (
                <><PlayCircle className="h-4 w-4 mr-1.5" />Activate Session</>
              )}
            </Button>
          </div>
        )}

        {session.status === 'ACTIVE' && (
          <div className="rounded-xl border border-amber-100 bg-amber-50 px-5 py-4 space-y-3">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-amber-800">Session is Live</p>
                <p className="text-xs text-amber-700">
                  Closing will end the exam for all students. In-progress attempts will be
                  submitted automatically on their next action.
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={() => setConfirmClose(true)}
              disabled={closing}
              className="border-amber-300 text-amber-800 hover:bg-amber-100"
            >
              {closing ? (
                <><Loader2 className="h-4 w-4 animate-spin mr-1.5" />Closing…</>
              ) : (
                <><XCircle className="h-4 w-4 mr-1.5" />Close Session</>
              )}
            </Button>
          </div>
        )}

        {session.status === 'CLOSED' && (
          <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 text-gray-600 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-700">Session Closed</p>
              <p className="text-xs text-gray-500">
                Closed on {fmt(session.closed_at)}. All attempts are final.
              </p>
            </div>
          </div>
        )}

        {/* Upcoming result navigation hint */}
        {session.status === 'CLOSED' && session.scored_count > 0 && (
          <div className="flex items-center gap-2 px-1">
            <Calendar className="h-4 w-4 text-gray-600" />
            <p className="text-xs text-gray-500">
              {session.scored_count} of {session.attempt_count} attempts scored.
            </p>
          </div>
        )}
      </div>

      {/* Confirm: Activate */}
      <ConfirmDialog
        open={confirmActivate}
        title="Activate Session?"
        description="Students will immediately be able to enter this exam. Make sure the exam window and duration are correct before activating."
        confirmLabel="Activate"
        onConfirm={() => {
          setConfirmActivate(false)
          setActionError('')
          activate(sid, {
            onError: (err) => setActionError(getErrorMessage(err)),
          })
        }}
        onCancel={() => setConfirmActivate(false)}
      />

      {/* Confirm: Close */}
      <ConfirmDialog
        open={confirmClose}
        title="Close Session?"
        description="This will end the exam for all students. Any in-progress attempts will be auto-submitted on their next interaction. This action cannot be undone."
        confirmLabel="Close Session"
        danger
        onConfirm={() => {
          setConfirmClose(false)
          setActionError('')
          close(sid, {
            onError: (err) => setActionError(getErrorMessage(err)),
          })
        }}
        onCancel={() => setConfirmClose(false)}
      />
    </PageShell>
  )
}
