import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart2, AlertTriangle, CheckCircle2, ChevronLeft, Clock } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { CourseAttendanceSummary, MyCourseAttendanceDetail } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Attendance bar
// ---------------------------------------------------------------------------

function AttBar({ pct, isAtRisk }: { pct: number | null; isAtRisk: boolean }) {
  const barColor = isAtRisk ? 'bg-red-500' : 'bg-green-500'
  const trackColor = isAtRisk ? 'bg-red-100' : 'bg-green-100'
  const textColor = isAtRisk ? 'text-red-700' : 'text-green-700'
  const display = pct === null ? 0 : Math.min(100, pct)
  return (
    <div className="flex items-center gap-3">
      <div className={`flex-1 rounded-full h-2 overflow-hidden ${trackColor}`}>
        <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${display}%` }} />
      </div>
      <span className={`text-xs font-bold w-10 text-right ${textColor}`}>
        {pct === null ? '—' : `${pct.toFixed(1)}%`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sessions-needed calculator
// ---------------------------------------------------------------------------

function sessionsNeeded(attended: number, total: number, threshold = 75): number | null {
  // How many more consecutive attended sessions to cross above `threshold`%
  const denom = 1 - threshold / 100
  if (denom <= 0) return null
  const need = Math.ceil((threshold / 100 * total - attended) / denom)
  return need > 0 && isFinite(need) ? need : null
}

// ---------------------------------------------------------------------------
// Course card
// ---------------------------------------------------------------------------

function CourseCard({ c, onClick }: { c: CourseAttendanceSummary; onClick: () => void }) {
  const needed = c.is_at_risk
    ? sessionsNeeded(c.attended_sessions, c.total_sessions)
    : null

  return (
    <button onClick={onClick}
      className={`w-full text-left rounded-xl p-4 bg-white transition-all hover:shadow-sm border ${c.is_at_risk ? 'border-red-300' : 'border-gray-200'}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{c.course_code}</p>
          <p className="text-xs text-muted-foreground">{c.course_title}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {c.is_at_risk
            ? <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-semibold border border-red-300 bg-red-50 text-red-700">
                <AlertTriangle size={10} /> At Risk
              </span>
            : <CheckCircle2 size={14} className="text-green-600" />
          }
        </div>
      </div>
      <AttBar pct={c.attendance_pct} isAtRisk={c.is_at_risk} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2.5 text-xs font-medium">
        <span className="text-green-700">Present: {c.attended_sessions}</span>
        <span className="text-red-700">Absent: {c.total_sessions - c.attended_sessions}</span>
        <span className="text-foreground">Total Classes: {c.total_sessions}</span>
      </div>
      {needed !== null && (
        <p className="text-xs mt-2 font-semibold text-amber-800">
          Attend {needed} more consecutive session{needed !== 1 ? 's' : ''} to reach 75%
        </p>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<string, { className: string; label: string }> = {
  PRESENT: { className: 'text-green-700', label: 'Present' },
  ABSENT:  { className: 'text-red-700',   label: 'Absent' },
}

function CourseDetail({ detail, onBack }: { detail: MyCourseAttendanceDetail; onBack: () => void }) {
  return (
    <div className="space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft size={16} /> Back
      </button>

      {/* Summary card */}
      <div className="rounded-xl p-5 bg-blue-50 border border-blue-200">
        <h2 className="text-base font-semibold text-foreground">{detail.course_code} — {detail.course_title}</h2>
        <div className="mt-3">
          <AttBar pct={detail.summary.attendance_pct} isAtRisk={detail.summary.is_at_risk} />
        </div>
        <div className="flex flex-wrap gap-4 mt-3 text-xs font-medium">
          <span className="text-green-700 font-semibold">Present: {detail.summary.attended_sessions}</span>
          <span className="text-red-700 font-semibold">Absent: {detail.summary.total_sessions - detail.summary.attended_sessions}</span>
          <span className="text-foreground font-semibold">Total Classes: {detail.summary.total_sessions}</span>
        </div>
        {detail.summary.is_at_risk && (
          <div className="mt-3 rounded-lg p-2.5 flex gap-2 text-xs font-medium text-amber-900 bg-amber-50 border border-amber-300">
            <AlertTriangle size={13} className="shrink-0 mt-0.5" />
            Advisory: You may be below the required attendance threshold. Contact your faculty or Dean.
          </div>
        )}
      </div>

      {/* Session history */}
      <div className="rounded-xl overflow-hidden border border-gray-200">
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <h3 className="text-xs font-semibold text-foreground">Session History</h3>
        </div>
        {detail.sessions.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground text-sm">No sessions recorded yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                {['Date', 'Period', 'Topic', 'Status'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold text-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detail.sessions.map(s => {
                const ss = STATUS_STYLE[s.status] ?? { className: 'text-muted-foreground', label: s.status }
                return (
                  <tr key={s.session_id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                    <td className="px-4 py-2.5 text-xs font-medium text-foreground">{s.session_date}</td>
                    <td className="px-4 py-2.5 text-xs text-foreground">{s.period_number ?? '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-foreground max-w-[200px] truncate">{s.topic_covered ?? '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-semibold ${ss.className}`}>{ss.label}</span>
                      {s.remarks && <span className="text-xs text-muted-foreground ml-2">({s.remarks})</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AttendanceSummaryPage() {
  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['my-attendance'],
    queryFn: () => sisApi.getMyAttendance(),
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['my-course-attendance', selectedCourseId],
    queryFn: () => sisApi.getMyCourseAttendance(selectedCourseId!),
    enabled: !!selectedCourseId,
  })

  if (isLoading) return <PageLoading />

  const atRiskCount = summary?.courses.filter(c => c.is_at_risk).length ?? 0

  return (
    <PageShell>
      <PageHeader
        icon={BarChart2}
        title="My Attendance"
        subtitle="Track your attendance across all enrolled courses"
      />

      {selectedCourseId ? (
        detailLoading
          ? <PageLoading />
          : detail
            ? <CourseDetail detail={detail} onBack={() => setSelectedCourseId(null)} />
            : <p className="text-muted-foreground text-sm">Could not load course detail.</p>
      ) : (
        <div className="mt-6 space-y-5">
          {/* Overall */}
          {summary && (
            <div className="flex flex-wrap gap-4">
              <div className="rounded-xl px-5 py-4 flex-1 min-w-[160px] bg-blue-50 border border-blue-200">
                <p className="text-xs font-medium text-foreground">Overall Attendance</p>
                <p className="text-3xl font-bold text-blue-700 mt-1">
                  {summary.overall_pct === null ? '—' : `${summary.overall_pct.toFixed(1)}%`}
                </p>
              </div>
              {atRiskCount > 0 && (
                <div className="rounded-xl px-5 py-4 flex-1 min-w-[160px] bg-red-50 border border-red-200">
                  <p className="text-xs font-medium text-foreground">At Risk Courses</p>
                  <p className="text-3xl font-bold text-red-700 mt-1">{atRiskCount}</p>
                </div>
              )}
            </div>
          )}

          {/* At-risk advisory */}
          {atRiskCount > 0 && (
            <div className="rounded-lg p-3 flex gap-2 text-xs font-medium text-amber-900 bg-amber-50 border border-amber-300">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              You have {atRiskCount} course{atRiskCount > 1 ? 's' : ''} below the attendance threshold.
              Click a course to see details. This is advisory — contact your faculty or Dean.
            </div>
          )}

          {/* Course cards */}
          {!summary || summary.courses.length === 0 ? (
            <div className="rounded-xl py-12 text-center text-muted-foreground text-sm border border-gray-200">
              <Clock size={32} className="mx-auto mb-3 opacity-30" />
              No attendance records yet. Sessions will appear here once faculty marks attendance.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {summary.courses.map(c => (
                <CourseCard key={c.course_id} c={c} onClick={() => setSelectedCourseId(c.course_id)} />
              ))}
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
