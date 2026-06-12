import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, ChevronRight, Clock, CheckCircle2, Loader2, FileStack } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { useMyAssignments, useMyWorkload } from '@/hooks/evaluationAssignments'
import type { AssignmentStatus, EvaluationAssignment } from '@/types/evaluationAssignment'
import { StatusBadge, TypeBadge, formatDateTime, workItemCode } from './assignmentShared'

const TABS: { key: 'ACTIVE' | AssignmentStatus; label: string }[] = [
  { key: 'ACTIVE',      label: 'Active' },
  { key: 'ASSIGNED',    label: 'Pending' },
  { key: 'IN_PROGRESS', label: 'In Progress' },
  { key: 'COMPLETED',   label: 'Completed' },
]

function StatCard({ icon: Icon, label, value, tone }: {
  icon: typeof Clock; label: string; value: number | string; tone: string
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-center gap-3">
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <div className="text-2xl font-semibold text-gray-900 leading-none">{value}</div>
        <div className="text-xs text-gray-500 mt-1">{label}</div>
      </div>
    </div>
  )
}

function AssignmentRow({ a, onOpen }: { a: EvaluationAssignment; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm hover:border-blue-300 transition-colors"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-sm font-medium text-gray-800">{workItemCode(a)}</span>
          <StatusBadge status={a.status} />
          <TypeBadge type={a.assignment_type} />
          {a.evaluation_round !== 'NONE' && (
            <Badge className="bg-indigo-50 text-indigo-600 text-xs">{a.evaluation_round}</Badge>
          )}
        </div>
        <div className="text-xs text-gray-500">
          Assigned {formatDateTime(a.assigned_at)}
          {a.due_at && <span className="ml-2 text-amber-600">· Due {formatDateTime(a.due_at)}</span>}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-gray-300 shrink-0" />
    </button>
  )
}

export default function FacultyAssignmentsPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<'ACTIVE' | AssignmentStatus>('ACTIVE')

  const { data: workload } = useMyWorkload()
  const statusParam = tab === 'ACTIVE' ? undefined : tab
  const { data, isLoading, isError, refetch } = useMyAssignments({ status: statusParam })

  const items = useMemo(() => {
    const all = data?.items ?? []
    if (tab !== 'ACTIVE') return all
    const active: AssignmentStatus[] = ['ASSIGNED', 'IN_PROGRESS', 'SUBMITTED']
    return all.filter((a) => active.includes(a.status))
  }, [data, tab])

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <ClipboardList className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">My Evaluation Assignments</h1>
          <p className="text-sm text-gray-500">Anonymous scripts allocated to you for evaluation.</p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={Clock}        label="Pending"     value={workload?.pending_count ?? 0}     tone="bg-blue-50 text-blue-600" />
        <StatCard icon={Loader2}      label="In Progress" value={workload?.in_progress_count ?? 0} tone="bg-amber-50 text-amber-600" />
        <StatCard icon={FileStack}    label="Submitted"   value={workload?.submitted_count ?? 0}   tone="bg-violet-50 text-violet-600" />
        <StatCard icon={CheckCircle2} label="Completed"   value={workload?.completed_count ?? 0}   tone="bg-green-50 text-green-600" />
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === t.key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <PageLoading />
      ) : isError ? (
        <PageError onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <PageEmpty icon={ClipboardList} title="No assignments" message="You have no assignments in this view." />
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <AssignmentRow key={a.id} a={a} onOpen={() => navigate(`/faculty/evaluation-assignments/${a.id}`)} />
          ))}
        </div>
      )}
    </div>
  )
}
