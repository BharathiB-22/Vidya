import { useQuery } from '@tanstack/react-query'
import { CalendarCheck } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import type { SubjectTabProps } from './types'

export function AttendanceTab({ subject }: SubjectTabProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-course-attendance', subject.course_id],
    queryFn: () => sisApi.getMyCourseAttendance(subject.course_id),
  })

  if (isLoading) return <div className="text-sm text-gray-400 py-8 text-center">Loading attendance…</div>
  if (isError || !data) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <CalendarCheck className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No attendance records for this subject yet.</p>
      </div>
    )
  }

  const { summary, sessions } = data

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-center justify-between">
        <div>
          <div className="text-2xl font-bold text-gray-900">
            {summary.attendance_pct != null ? `${summary.attendance_pct.toFixed(1)}%` : '—'}
          </div>
          <div className="text-xs text-gray-400">
            {summary.attended_sessions} / {summary.total_sessions} sessions attended
          </div>
        </div>
        {summary.is_at_risk && (
          <span className="text-xs px-2 py-1 rounded-full bg-red-50 text-red-700 font-medium">At risk</span>
        )}
      </div>
      <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden max-h-96 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">No sessions recorded yet.</div>
        ) : (
          sessions.map((s) => (
            <div key={s.session_id} className="px-5 py-2.5 flex items-center justify-between text-sm">
              <div>
                <span className="text-gray-700">{new Date(s.session_date).toLocaleDateString()}</span>
                {s.topic_covered && <span className="text-gray-400 ml-2 text-xs">{s.topic_covered}</span>}
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                s.status === 'PRESENT' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              }`}>
                {s.status}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
