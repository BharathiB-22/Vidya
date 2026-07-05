import { FlaskConical } from 'lucide-react'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import { WidgetCard } from './WidgetCard'

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <p className="text-xl font-bold text-gray-900">{value}</p>
      <p className="text-[11px] text-gray-400 mt-0.5">{label}</p>
    </div>
  )
}

export function LabsWidget() {
  const assignmentsQ = useStudentAssignments()
  const submissionsQ = useMySubmissions()

  const assigned = assignmentsQ.data?.total ?? 0
  const submissions = submissionsQ.data?.items ?? []
  const submitted = submissions.length
  const pendingEvaluation = submissions.filter((s) => s.status === 'SUBMITTED' || s.status === 'EVALUATING').length

  return (
    <WidgetCard
      title="Labs"
      icon={FlaskConical}
      isLoading={assignmentsQ.isLoading || submissionsQ.isLoading}
      isError={assignmentsQ.isError || submissionsQ.isError}
      action={{ label: 'View', to: '/student/labs' }}
    >
      <div className="grid grid-cols-3 gap-2 py-1">
        <MiniStat label="Assigned" value={assigned} />
        <MiniStat label="Submitted" value={submitted} />
        <MiniStat label="Pending Eval." value={pendingEvaluation} />
      </div>
    </WidgetCard>
  )
}
