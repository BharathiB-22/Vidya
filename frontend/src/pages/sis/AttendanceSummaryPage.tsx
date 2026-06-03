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
  const color = isAtRisk ? '#f87171' : '#4ade80'
  const track = isAtRisk ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.12)'
  const display = pct === null ? 0 : Math.min(100, pct)
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 rounded-full h-2 overflow-hidden" style={{ background: track }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${display}%`, background: color }} />
      </div>
      <span className="text-xs font-semibold w-10 text-right" style={{ color }}>
        {pct === null ? '—' : `${pct.toFixed(1)}%`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Course card
// ---------------------------------------------------------------------------

function CourseCard({ c, onClick }: { c: CourseAttendanceSummary; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full text-left rounded-xl p-4 transition-all hover:scale-[1.01]"
      style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${c.is_at_risk ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.08)'}` }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-sm font-semibold text-slate-200">{c.course_code}</p>
          <p className="text-xs text-slate-400">{c.course_title}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {c.is_at_risk
            ? <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-semibold"
                style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}>
                <AlertTriangle size={10} /> At Risk
              </span>
            : <CheckCircle2 size={14} className="text-green-400" />
          }
        </div>
      </div>
      <AttBar pct={c.attendance_pct} isAtRisk={c.is_at_risk} />
      <div className="flex justify-between mt-2 text-xs text-slate-500">
        <span>{c.attended_sessions} attended</span>
        <span>{c.total_countable} countable sessions</span>
      </div>
      {c.excused_sessions > 0 && (
        <p className="text-xs text-slate-600 mt-1">{c.excused_sessions} excused (excluded from %)</p>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<string, { color: string; label: string }> = {
  PRESENT: { color: '#4ade80', label: 'Present' },
  LATE:    { color: '#fbbf24', label: 'Late' },
  ABSENT:  { color: '#f87171', label: 'Absent' },
  EXCUSED: { color: '#a5b4fc', label: 'Excused' },
}

function CourseDetail({ detail, onBack }: { detail: MyCourseAttendanceDetail; onBack: () => void }) {
  return (
    <div className="space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200 transition-colors">
        <ChevronLeft size={16} /> Back
      </button>

      {/* Summary card */}
      <div className="rounded-xl p-5" style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}>
        <h2 className="text-base font-semibold text-slate-200">{detail.course_code} — {detail.course_title}</h2>
        <div className="mt-3">
          <AttBar pct={detail.summary.attendance_pct} isAtRisk={detail.summary.is_at_risk} />
        </div>
        <div className="flex flex-wrap gap-4 mt-3 text-xs text-slate-400">
          <span><span className="text-green-400 font-semibold">{detail.summary.attended_sessions}</span> attended</span>
          <span><span className="text-slate-300 font-semibold">{detail.summary.total_countable}</span> countable</span>
          {detail.summary.excused_sessions > 0 && (
            <span><span className="text-indigo-400 font-semibold">{detail.summary.excused_sessions}</span> excused</span>
          )}
        </div>
        {detail.summary.is_at_risk && (
          <div className="mt-3 rounded-lg p-2.5 flex gap-2 text-xs text-yellow-300"
            style={{ background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)' }}>
            <AlertTriangle size={13} className="shrink-0 mt-0.5" />
            Advisory: You may be below the required attendance threshold. Contact your faculty or Dean.
          </div>
        )}
      </div>

      {/* Session history */}
      <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <div className="px-4 py-3" style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <h3 className="text-xs font-semibold text-slate-400">Session History</h3>
        </div>
        {detail.sessions.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-sm">No sessions recorded yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                {['Date', 'Period', 'Topic', 'Status'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-slate-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detail.sessions.map(s => {
                const ss = STATUS_STYLE[s.status] ?? { color: '#94a3b8', label: s.status }
                return (
                  <tr key={s.session_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                    className="hover:bg-white/[0.02]">
                    <td className="px-4 py-2.5 text-xs text-slate-200">{s.session_date}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">{s.period_number ?? '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400 max-w-[200px] truncate">{s.topic_covered ?? '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs font-semibold" style={{ color: ss.color }}>{ss.label}</span>
                      {s.remarks && <span className="text-xs text-slate-500 ml-2">({s.remarks})</span>}
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
            : <p className="text-slate-400 text-sm">Could not load course detail.</p>
      ) : (
        <div className="mt-6 space-y-5">
          {/* Overall */}
          {summary && (
            <div className="flex flex-wrap gap-4">
              <div className="rounded-xl px-5 py-4 flex-1 min-w-[160px]"
                style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)' }}>
                <p className="text-xs text-slate-400">Overall Attendance</p>
                <p className="text-3xl font-bold text-indigo-300 mt-1">
                  {summary.overall_pct === null ? '—' : `${summary.overall_pct.toFixed(1)}%`}
                </p>
              </div>
              {atRiskCount > 0 && (
                <div className="rounded-xl px-5 py-4 flex-1 min-w-[160px]"
                  style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <p className="text-xs text-slate-400">At Risk Courses</p>
                  <p className="text-3xl font-bold text-red-400 mt-1">{atRiskCount}</p>
                </div>
              )}
            </div>
          )}

          {/* At-risk advisory */}
          {atRiskCount > 0 && (
            <div className="rounded-lg p-3 flex gap-2 text-xs text-yellow-300"
              style={{ background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)' }}>
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              You have {atRiskCount} course{atRiskCount > 1 ? 's' : ''} below the attendance threshold.
              Click a course to see details. This is advisory — contact your faculty or Dean.
            </div>
          )}

          {/* Course cards */}
          {!summary || summary.courses.length === 0 ? (
            <div className="rounded-xl py-12 text-center text-slate-500 text-sm"
              style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
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
