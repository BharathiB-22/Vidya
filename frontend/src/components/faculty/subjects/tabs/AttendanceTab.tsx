import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { CalendarCheck, AlertTriangle, ExternalLink, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { AttendanceSessionOut } from '@/lib/api/sis'
import { StatusBadge } from '@/components/attendance/AttendanceStatusBadge'
import { NewSessionModal } from '@/components/attendance/NewSessionModal'
import { MarkModal } from '@/components/attendance/MarkModal'
import type { FacultySubjectTabProps } from './types'

const today = () => new Date().toISOString().slice(0, 10)

export function AttendanceTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { course_id, section_id: sectionId } = ctx.assignment
  const [showNewSession, setShowNewSession] = useState(false)
  const [markSession, setMarkSession] = useState<AttendanceSessionOut | null>(null)

  const summaryQ = useQuery({
    queryKey: ['section-attendance', sectionId],
    queryFn: () => sisApi.getSectionAttendance(sectionId!),
    enabled: !!sectionId,
  })

  const sessionsQ = useQuery({
    queryKey: ['attendance-sessions', course_id, sectionId],
    queryFn: () => sisApi.listAttendanceSessions({ course_id, section_id: sectionId ?? undefined }),
    enabled: !!sectionId,
  })

  const atRiskCount = summaryQ.data?.students.filter((s) => s.is_at_risk).length ?? 0
  const sessions = sessionsQ.data ?? []
  const recentSessions = [...sessions].sort((a, b) => b.session_date.localeCompare(a.session_date)).slice(0, 5)
  const todaySession = sessions.find((s) => s.session_date === today())

  function refreshSessions() {
    qc.invalidateQueries({ queryKey: ['attendance-sessions'] })
  }

  function handleMarkAttendance() {
    if (todaySession) {
      setMarkSession(todaySession)
    } else {
      setShowNewSession(true)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Attendance Summary</p>
        <div className="flex gap-2">
          <Button size="sm" onClick={handleMarkAttendance} disabled={!sectionId}>
            {todaySession ? 'Mark Today’s Session' : 'Mark Attendance'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/sis/attendance/analytics')}>
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            View Full Attendance
          </Button>
        </div>
      </div>

      {!sectionId ? (
        <div className="text-sm text-gray-400 py-8 text-center">No section on record for this subject.</div>
      ) : summaryQ.isLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading attendance…</div>
      ) : summaryQ.isError || !summaryQ.data ? (
        <div className="text-sm text-gray-400 py-8 text-center">Failed to load attendance data.</div>
      ) : (
        <>
          {/* Today's session */}
          {todaySession && (
            <button
              type="button"
              onClick={() => setMarkSession(todaySession)}
              className="w-full flex items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50/50 px-4 py-3 hover:bg-blue-50 transition-colors text-left"
            >
              <div>
                <p className="text-sm font-semibold text-gray-800">Today's Session</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {todaySession.period_number != null ? `Period ${todaySession.period_number} · ` : ''}
                  {todaySession.first_marked_at
                    ? `${todaySession.present_count}/${todaySession.total_enrolled} present`
                    : 'Not marked yet'}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge session={todaySession} />
                <ChevronRight className="h-4 w-4 text-gray-300" />
              </div>
            </button>
          )}

          {/* Analytics preview */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <CalendarCheck className="h-4 w-4 text-gray-400 mb-2" />
              <p className="text-xl font-bold text-gray-900">{summaryQ.data.total_sessions}</p>
              <p className="text-xs text-gray-500 mt-0.5">Sessions Held</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <CalendarCheck className="h-4 w-4 text-gray-400 mb-2" />
              <p className="text-xl font-bold text-gray-900">
                {summaryQ.data.avg_attendance_pct != null ? `${summaryQ.data.avg_attendance_pct.toFixed(0)}%` : '—'}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Average Attendance</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <AlertTriangle className="h-4 w-4 text-amber-500 mb-2" />
              <p className="text-xl font-bold text-gray-900">{atRiskCount}</p>
              <p className="text-xs text-gray-500 mt-0.5">Students At Risk</p>
            </div>
          </div>

          {/* Recent attendance */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Recent Attendance</p>
            {sessionsQ.isLoading ? (
              <div className="text-sm text-gray-400 py-6 text-center">Loading sessions…</div>
            ) : recentSessions.length === 0 ? (
              <div className="text-center py-8 rounded-xl border border-dashed border-gray-200">
                <CalendarCheck className="h-6 w-6 mx-auto mb-2 text-gray-200" />
                <p className="text-sm text-gray-400">No attendance sessions recorded yet.</p>
              </div>
            ) : (
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {recentSessions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setMarkSession(s)}
                    className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800">
                        {new Date(s.session_date).toLocaleDateString()}
                        {s.period_number != null ? ` · Period ${s.period_number}` : ''}
                      </p>
                      <p className="text-xs text-gray-400">
                        {s.present_count}/{s.total_enrolled} present
                        {s.attendance_pct != null ? ` (${s.attendance_pct.toFixed(0)}%)` : ''}
                      </p>
                    </div>
                    <StatusBadge session={s} />
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {showNewSession && course_id && sectionId && (
        <NewSessionModal
          courseId={course_id}
          sectionId={sectionId}
          onClose={() => setShowNewSession(false)}
          onSaved={refreshSessions}
        />
      )}
      {markSession && (
        <MarkModal
          session={markSession}
          onClose={() => setMarkSession(null)}
          onSaved={refreshSessions}
        />
      )}
    </div>
  )
}
