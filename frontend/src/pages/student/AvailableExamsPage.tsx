import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Monitor, Clock, ChevronRight, Loader2, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDigitalSessions } from '@/hooks/digitalExams'
import { startOrResumeAttempt } from '@/lib/api/digitalExam'
import type { DigitalExamSession } from '@/types/digitalExam'

function formatWindow(session: DigitalExamSession): string {
  if (!session.window_end) return `${session.max_duration_mins} min`
  const end = new Date(session.window_end)
  const now = new Date()
  const mins = Math.max(0, Math.floor((end.getTime() - now.getTime()) / 60000))
  if (mins < 60) return `Closes in ${mins}m`
  const hrs = Math.floor(mins / 60)
  return `Closes in ${hrs}h ${mins % 60}m`
}

function SessionCard({ session }: { session: DigitalExamSession }) {
  const navigate = useNavigate()

  const { mutate: enter, isPending } = useMutation({
    mutationFn: () => startOrResumeAttempt(session.id),
    onSuccess: (attempt) => {
      // Store attempt mapping for the guard
      sessionStorage.setItem(`exam_attempt_${session.id}`, attempt.id)
      if (attempt.status === 'SCORED' || attempt.status === 'SUBMITTED') {
        navigate(`/student/exams/digital/attempts/${attempt.id}/result`)
      } else {
        navigate(`/student/exams/digital/${session.id}/instructions`, {
          state: { attemptId: attempt.id },
        })
      }
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const msg = err?.response?.data?.detail ?? ''
      if (msg.includes('already submitted') || msg.includes('already been scored')) {
        const stored = sessionStorage.getItem(`exam_attempt_${session.id}`)
        if (stored) navigate(`/student/exams/digital/attempts/${stored}/result`)
      }
    },
  })

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-5 flex flex-col gap-3 hover:border-indigo-300 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">{session.title}</h3>
          <p className="text-xs text-gray-500 mt-0.5">{session.max_duration_mins} minutes</p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 text-xs font-medium px-2 py-0.5 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
          Open
        </span>
      </div>

      {session.instructions && (
        <p className="text-sm text-gray-600 line-clamp-2">{session.instructions}</p>
      )}

      <div className="flex items-center justify-between pt-1">
        <span className="flex items-center gap-1 text-xs text-gray-600">
          <Clock className="h-3.5 w-3.5" />
          {formatWindow(session)}
        </span>
        <Button
          size="sm"
          onClick={() => enter()}
          disabled={isPending}
          className="gap-1"
        >
          {isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          {isPending ? 'Starting…' : 'Enter Exam'}
        </Button>
      </div>
    </div>
  )
}

function CompletedRow({ session }: { session: DigitalExamSession }) {
  const navigate = useNavigate()
  const stored = sessionStorage.getItem(`exam_attempt_${session.id}`)

  if (!stored) return null

  return (
    <button
      onClick={() => navigate(`/student/exams/digital/attempts/${stored}/result`)}
      className="w-full flex items-center justify-between px-4 py-3 rounded-lg border border-gray-100 bg-white hover:bg-gray-50 text-left transition-colors"
    >
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
        <span className="text-sm font-medium text-gray-700 truncate">{session.title}</span>
      </div>
      <ChevronRight className="h-4 w-4 text-gray-600 shrink-0" />
    </button>
  )
}

export default function AvailableExamsPage() {
  const { data, isLoading, isError, refetch } = useDigitalSessions({ limit: 100 })

  const allSessions = data?.items ?? []
  const active  = allSessions.filter(s => s.status === 'ACTIVE')
  const closed  = allSessions.filter(s => s.status === 'CLOSED')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-400" />
        <p className="text-sm text-gray-500">Failed to load exams.</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Monitor className="h-6 w-6 text-indigo-600" />
        <div>
          <h1 className="text-xl font-bold text-gray-900">Digital Exams</h1>
          <p className="text-sm text-gray-500">Online exams open for submission</p>
        </div>
      </div>

      {/* Active exams */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Open Now
        </h2>
        {active.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-12 text-center">
            <Monitor className="h-8 w-8 mx-auto text-gray-500 mb-2" />
            <p className="text-sm text-gray-500">No exams are currently open.</p>
            <p className="text-xs text-gray-600 mt-1">Check back when your exam window opens.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-1">
            {active.map(s => <SessionCard key={s.id} session={s} />)}
          </div>
        )}
      </section>

      {/* Completed exams */}
      {closed.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Completed Exams
          </h2>
          <div className="space-y-1.5">
            {closed.map(s => <CompletedRow key={s.id} session={s} />)}
          </div>
        </section>
      )}
    </div>
  )
}
