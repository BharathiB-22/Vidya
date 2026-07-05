import { useQuery } from '@tanstack/react-query'
import { CalendarClock, FlaskConical, Video, FileText } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import { studentListVivas } from '@/lib/api/research'
import { WidgetCard } from './WidgetCard'

interface UpcomingDeadlinesProps {
  sessionId?: string
}

interface DeadlineItem {
  key: string
  label: string
  detail: string
  date: string
  icon: React.FC<{ className?: string }>
  iconColor: string
}

export function UpcomingDeadlines({ sessionId }: UpcomingDeadlinesProps) {
  const assignmentsQ = useStudentAssignments()
  const submissionsQ = useMySubmissions()
  const vivasQ = useQuery({
    queryKey: ['student-vivas'],
    queryFn: () => studentListVivas(),
  })
  const timetableQ = useQuery({
    queryKey: ['my-timetable', sessionId],
    queryFn: () => sisApi.getMyTimetable(sessionId!),
    enabled: !!sessionId,
  })

  const now = new Date()
  const submittedIds = new Set((submissionsQ.data?.items ?? []).map((s) => s.assignment_id))

  const items: DeadlineItem[] = []

  for (const a of assignmentsQ.data?.items ?? []) {
    if (!a.deadline || submittedIds.has(a.id)) continue
    if (new Date(a.deadline) < now) continue
    items.push({
      key: `lab-${a.id}`,
      label: a.title,
      detail: a.course_code ? `${a.course_code} · Lab submission` : 'Lab submission',
      date: a.deadline,
      icon: FlaskConical,
      iconColor: 'text-emerald-500',
    })
  }

  for (const v of vivasQ.data?.items ?? []) {
    if (v.status !== 'SCHEDULED' || new Date(v.scheduled_at) < now) continue
    items.push({
      key: `viva-${v.id}`,
      label: 'Viva voce session',
      detail: 'Research supervision',
      date: v.scheduled_at,
      icon: Video,
      iconColor: 'text-purple-500',
    })
  }

  for (const c of timetableQ.data?.courses ?? []) {
    if (!c.exam_date || new Date(c.exam_date) < now) continue
    items.push({
      key: `exam-${c.course_id}`,
      label: `${c.course_code} exam`,
      detail: c.course_title,
      date: c.exam_date,
      icon: FileText,
      iconColor: 'text-amber-500',
    })
  }

  items.sort((a, b) => (a.date < b.date ? -1 : 1))
  const top = items.slice(0, 5)

  const isLoading = assignmentsQ.isLoading || submissionsQ.isLoading || vivasQ.isLoading || (!!sessionId && timetableQ.isLoading)
  const isError = assignmentsQ.isError || submissionsQ.isError || vivasQ.isError

  return (
    <WidgetCard title="Upcoming Deadlines" icon={CalendarClock} isLoading={isLoading} isError={isError}>
      {top.length === 0 ? (
        <p className="text-sm text-gray-400 py-2">No upcoming deadlines.</p>
      ) : (
        <ul className="space-y-2.5">
          {top.map((item) => (
            <li key={item.key} className="flex items-start gap-2.5 text-sm">
              <item.icon className={`h-3.5 w-3.5 flex-shrink-0 mt-0.5 ${item.iconColor}`} />
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-gray-800 truncate">{item.label}</p>
                <p className="text-xs text-gray-400 truncate">{item.detail}</p>
              </div>
              <span className="text-xs text-gray-400 flex-shrink-0 whitespace-nowrap">
                {new Date(item.date).toLocaleDateString([], { month: 'short', day: 'numeric' })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
