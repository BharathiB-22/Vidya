import { useQuery } from '@tanstack/react-query'
import { Microscope } from 'lucide-react'
import { studentListProblems, studentListVivas, listActiveGuides } from '@/lib/api/research'
import { WidgetCard } from './WidgetCard'

const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Draft',
  PENDING_REVIEW: 'Pending guide review',
  ACCEPTED: 'Accepted',
  REVISION_REQUESTED: 'Revision requested',
  REJECTED: 'Rejected',
}

export function ResearchWidget() {
  const problemsQ = useQuery({
    queryKey: ['student-problems'],
    queryFn: () => studentListProblems(),
  })
  const guidesQ = useQuery({
    queryKey: ['research-guides'],
    queryFn: () => listActiveGuides(),
  })
  const vivasQ = useQuery({
    queryKey: ['student-vivas'],
    queryFn: () => studentListVivas(),
  })

  const problem = problemsQ.data?.items?.[0]
  const guide = guidesQ.data?.find((g) => g.id === problem?.guide_user_id)
  const nextViva = vivasQ.data?.items
    ?.filter((v) => v.status === 'SCHEDULED')
    .sort((a, b) => (a.scheduled_at < b.scheduled_at ? -1 : 1))[0]

  const isLoading = problemsQ.isLoading || guidesQ.isLoading || vivasQ.isLoading
  const isError = problemsQ.isError

  return (
    <WidgetCard
      title="Research Supervision"
      icon={Microscope}
      isLoading={isLoading}
      isError={isError}
      action={{ label: 'View', to: '/student/research' }}
    >
      {!problem ? (
        <p className="text-sm text-gray-400 py-2">No research problem registered yet.</p>
      ) : (
        <div className="space-y-2 text-sm">
          <p className="font-semibold text-gray-800 leading-snug">{problem.title}</p>
          <p className="text-xs text-gray-500">
            Status: <span className="font-medium text-gray-700">{STATUS_LABEL[problem.status] ?? problem.status}</span>
          </p>
          {guide && (
            <p className="text-xs text-gray-500">
              Supervisor: <span className="font-medium text-gray-700">{guide.full_name}</span>
            </p>
          )}
          {nextViva && (
            <p className="text-xs text-gray-500">
              Next viva: <span className="font-medium text-gray-700">{new Date(nextViva.scheduled_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</span>
            </p>
          )}
        </div>
      )}
    </WidgetCard>
  )
}
