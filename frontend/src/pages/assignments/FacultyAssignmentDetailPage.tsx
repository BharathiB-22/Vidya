import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Play, Send, CheckCircle2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import {
  useAssignment,
  useStartAssignment,
  useSubmitAssignment,
  useCompleteAssignment,
} from '@/hooks/evaluationAssignments'
import type { AssignmentStatus } from '@/types/evaluationAssignment'
import { StatusBadge, TypeBadge, TYPE_LABELS, formatDateTime, workItemCode } from './assignmentShared'

const STEPS: { status: AssignmentStatus; label: string }[] = [
  { status: 'ASSIGNED',    label: 'Assigned' },
  { status: 'IN_PROGRESS', label: 'In Progress' },
  { status: 'SUBMITTED',   label: 'Submitted' },
  { status: 'COMPLETED',   label: 'Completed' },
]

function Stepper({ status }: { status: AssignmentStatus }) {
  const order = STEPS.findIndex((s) => s.status === status)
  return (
    <div className="flex items-center">
      {STEPS.map((s, i) => {
        const done = i <= order && order >= 0
        return (
          <div key={s.status} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                done ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'
              }`}>{i + 1}</div>
              <span className={`mt-1 text-[11px] ${done ? 'text-blue-700' : 'text-gray-600'}`}>{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 flex-1 mx-1 ${i < order ? 'bg-blue-600' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-600">{label}</dt>
      <dd className="text-sm text-gray-800 mt-0.5">{value}</dd>
    </div>
  )
}

export default function FacultyAssignmentDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data: a, isLoading, isError, refetch } = useAssignment(id)

  const start = useStartAssignment()
  const submit = useSubmitAssignment()
  const complete = useCompleteAssignment()
  const busy = start.isPending || submit.isPending || complete.isPending

  if (isLoading) return <PageLoading />
  if (isError || !a) return <div className="max-w-2xl mx-auto p-6"><PageError onRetry={() => refetch()} /></div>

  const run = async (
    fn: { mutateAsync: (id: string) => Promise<unknown> },
    okMsg: string,
  ) => {
    try {
      await fn.mutateAsync(id)
      addToast(okMsg, 'success')
    } catch (e) {
      addToast(getErrorMessage(e), 'error')
    }
  }

  const terminal = ['COMPLETED', 'CANCELLED', 'REASSIGNED'].includes(a.status)

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <button onClick={() => navigate('/faculty/evaluation-assignments')}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700">
        <ArrowLeft className="w-4 h-4" /> Back to my assignments
      </button>

      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-gray-900 font-mono">{workItemCode(a)}</h1>
              <StatusBadge status={a.status} />
            </div>
            <div className="mt-1"><TypeBadge type={a.assignment_type} /></div>
          </div>
        </div>

        <div className="rounded-lg bg-blue-50/60 border border-blue-100 p-3 flex items-start gap-2">
          <ShieldCheck className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-700">
            Anonymous evaluation: you see only the script code. Student name and roll
            number are hidden until the Board finalises results.
          </p>
        </div>

        <Stepper status={a.status} />

        <dl className="grid grid-cols-2 gap-4 pt-1">
          <Field label="Type" value={TYPE_LABELS[a.assignment_type]} />
          <Field label="Round" value={a.evaluation_round === 'NONE' ? '—' : a.evaluation_round} />
          <Field label="Assigned" value={formatDateTime(a.assigned_at)} />
          <Field label="Due" value={formatDateTime(a.due_at)} />
          <Field label="Started" value={formatDateTime(a.started_at)} />
          <Field label="Submitted" value={formatDateTime(a.submitted_at)} />
          {a.notes && <div className="col-span-2"><Field label="Notes" value={a.notes} /></div>}
        </dl>

        {!terminal && (
          <div className="flex gap-2 pt-2 border-t border-gray-100">
            {a.status === 'ASSIGNED' && (
              <Button disabled={busy} onClick={() => run(start, 'Assignment started')} className="gap-1.5">
                <Play className="w-4 h-4" /> Start
              </Button>
            )}
            {a.status === 'IN_PROGRESS' && (
              <Button disabled={busy} onClick={() => run(submit, 'Marks submitted')} className="gap-1.5">
                <Send className="w-4 h-4" /> Submit
              </Button>
            )}
            {a.status === 'SUBMITTED' && (
              <Button disabled={busy} onClick={() => run(complete, 'Assignment completed')} className="gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> Mark Complete
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
