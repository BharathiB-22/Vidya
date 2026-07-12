import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ChevronLeft, ChevronRight, XCircle } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import type { CourseAttendanceSummary, SessionRecordForStudent } from '@/lib/api/sis'

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function prettyDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${DOW[date.getDay()]} ${String(d).padStart(2, '0')} ${MONTHS[m - 1]}`
}

function pctColor(pct: number | null): string {
  if (pct === null) return 'text-gray-400'
  if (pct < 75) return 'text-red-600'
  if (pct < 85) return 'text-amber-600'
  return 'text-emerald-600'
}

function barColor(pct: number | null): string {
  if (pct === null) return 'bg-gray-200'
  if (pct < 75) return 'bg-red-500'
  if (pct < 85) return 'bg-amber-500'
  return 'bg-emerald-500'
}

/**
 * A student's read-only attendance: an overall figure, one card per subject, and
 * a dated history behind each. No editing, no session controls — students only
 * ever view. Everything comes from the existing self-view endpoints.
 */
export default function StudentAttendancePage() {
  const [openCourse, setOpenCourse] = useState<CourseAttendanceSummary | null>(null)

  if (openCourse) {
    return <CourseHistory course={openCourse} onBack={() => setOpenCourse(null)} />
  }
  return <Dashboard onOpen={setOpenCourse} />
}

function Dashboard({ onOpen }: { onOpen: (c: CourseAttendanceSummary) => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-attendance'],
    queryFn: () => sisApi.getMyAttendance(),
  })

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Attendance</h1>
        <p className="text-sm text-gray-500 mt-0.5">Your attendance across all subjects.</p>
      </div>

      {isError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your attendance. Please refresh.
        </div>
      ) : isLoading ? (
        <div className="h-40 rounded-xl bg-gray-50 animate-pulse" />
      ) : (
        <>
          {/* Overall */}
          <div className="flex items-center gap-5 rounded-2xl border border-gray-200 bg-white p-6">
            <div className={`text-4xl font-bold ${pctColor(data?.overall_pct ?? null)}`}>
              {data?.overall_pct != null ? `${Math.round(data.overall_pct)}%` : '—'}
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900">Overall attendance</p>
              <p className="text-xs text-gray-500">
                Across {data?.courses.length ?? 0} subject{data?.courses.length === 1 ? '' : 's'}.
                Minimum required is usually 75%.
              </p>
            </div>
          </div>

          {(data?.courses.length ?? 0) === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center text-sm text-gray-500">
              No attendance recorded yet.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {data!.courses.map((c) => (
                <button
                  key={c.course_id}
                  type="button"
                  onClick={() => onOpen(c)}
                  className="rounded-xl border border-gray-200 bg-white p-4 text-left space-y-3 hover:border-gray-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className="font-mono text-xs text-gray-500">{c.course_code}</span>
                      <p className="text-sm font-semibold text-gray-900 leading-tight">{c.course_title}</p>
                    </div>
                    <span className={`text-lg font-bold shrink-0 ${pctColor(c.attendance_pct)}`}>
                      {c.attendance_pct != null ? `${Math.round(c.attendance_pct)}%` : '—'}
                    </span>
                  </div>

                  <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${barColor(c.attendance_pct)}`}
                      style={{ width: `${c.attendance_pct ?? 0}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>
                      {c.attended_sessions} present · {c.total_sessions - c.attended_sessions} absent
                    </span>
                    <span className="inline-flex items-center gap-0.5 text-gray-400">
                      History <ChevronRight className="h-3.5 w-3.5" />
                    </span>
                  </div>
                  {c.is_at_risk && (
                    <p className="text-[11px] font-medium text-red-600">Below the required minimum</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function CourseHistory({
  course, onBack,
}: {
  course: CourseAttendanceSummary
  onBack: () => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-course-attendance', course.course_id],
    queryFn: () => sisApi.getMyCourseAttendance(course.course_id),
  })

  const sessions = data?.sessions ?? []

  return (
    <div className="w-full max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
        <ChevronLeft className="h-4 w-4" /> Back to my attendance
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="font-mono text-xs text-gray-500">{course.course_code}</span>
          <h1 className="text-xl font-semibold text-gray-900">{course.course_title}</h1>
        </div>
        <div className={`text-right ${pctColor(course.attendance_pct)}`}>
          <div className="text-2xl font-bold">
            {course.attendance_pct != null ? `${Math.round(course.attendance_pct)}%` : '—'}
          </div>
          <div className="text-xs text-gray-500">
            {course.attended_sessions}/{course.total_sessions}
          </div>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load history. Please refresh.
        </div>
      ) : isLoading ? (
        <div className="h-64 rounded-xl bg-gray-50 animate-pulse" />
      ) : sessions.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center text-sm text-gray-500">
          No sessions recorded yet.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
          {sessions.map((s: SessionRecordForStudent) => (
            <div key={s.session_id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900">{prettyDate(s.session_date)}</p>
                <p className="text-xs text-gray-500">
                  {s.period_number != null ? `Period ${s.period_number}` : ''}
                  {s.topic_covered ? ` · ${s.topic_covered}` : ''}
                </p>
              </div>
              {s.status === 'PRESENT' ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700 shrink-0">
                  <CheckCircle2 className="h-4 w-4" /> Present
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-red-600 shrink-0">
                  <XCircle className="h-4 w-4" /> Absent
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
