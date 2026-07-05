import { useQuery } from '@tanstack/react-query'
import { CalendarClock, FileText, Video, Clock } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { studentListVivas } from '@/lib/api/research'
import { WidgetCard } from './WidgetCard'

interface TodayScheduleProps {
  sessionId?: string
}

export function TodaySchedule({ sessionId }: TodayScheduleProps) {
  const timetableQ = useQuery({
    queryKey: ['my-timetable', sessionId],
    queryFn: () => sisApi.getMyTimetable(sessionId!),
    enabled: !!sessionId,
  })

  const vivasQ = useQuery({
    queryKey: ['student-vivas'],
    queryFn: () => studentListVivas(),
  })

  const today = new Date().toISOString().slice(0, 10)

  const todaysExams = (timetableQ.data?.courses ?? []).filter((c) => c.exam_date === today)
  const todaysVivas = (vivasQ.data?.items ?? []).filter(
    (v) => v.status === 'SCHEDULED' && v.scheduled_at.slice(0, 10) === today,
  )

  const isLoading = (!!sessionId && timetableQ.isLoading) || vivasQ.isLoading
  const isError = timetableQ.isError || vivasQ.isError
  const hasItems = todaysExams.length > 0 || todaysVivas.length > 0

  return (
    <WidgetCard title="Today's Schedule" icon={CalendarClock} isLoading={isLoading} isError={isError}>
      {!hasItems ? (
        <p className="text-sm text-gray-400 py-2">No sessions scheduled today.</p>
      ) : (
        <ul className="space-y-2">
          {todaysExams.map((c) => (
            <li key={c.course_id} className="flex items-center gap-2.5 text-sm">
              <FileText className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
              <span className="font-semibold text-gray-800">{c.course_code}</span>
              <span className="text-gray-500 truncate">{c.course_title} — Exam</span>
              {c.start_time && (
                <span className="ml-auto text-xs text-gray-400 flex items-center gap-1 flex-shrink-0">
                  <Clock className="h-3 w-3" /> {c.start_time}
                </span>
              )}
            </li>
          ))}
          {todaysVivas.map((v) => (
            <li key={v.id} className="flex items-center gap-2.5 text-sm">
              <Video className="h-3.5 w-3.5 text-purple-500 flex-shrink-0" />
              <span className="text-gray-700">Viva voce session</span>
              <span className="ml-auto text-xs text-gray-400 flex items-center gap-1 flex-shrink-0">
                <Clock className="h-3 w-3" /> {new Date(v.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
