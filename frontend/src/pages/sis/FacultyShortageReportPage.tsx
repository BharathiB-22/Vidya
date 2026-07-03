import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Info, Lock, Users } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { FacultyCourseShortage, ShortageStudentOut } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pctColor(p: number): string {
  if (p < 50) return '#f87171'
  if (p < 65) return '#fb923c'
  return '#fbbf24'
}

function sessionsNeeded(attended: number, total: number, threshold: number): number | null {
  const need = Math.ceil((threshold / 100 * total - attended) / (1 - threshold / 100))
  return need > 0 && isFinite(need) ? need : null
}

// ---------------------------------------------------------------------------
// Student row
// ---------------------------------------------------------------------------

function StudentRow({ s, threshold }: { s: ShortageStudentOut; threshold: number }) {
  const needed = sessionsNeeded(s.attended_sessions, s.total_sessions, threshold)
  return (
    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }} className="hover:bg-white/[0.02]">
      <td className="px-4 py-2.5 text-xs font-mono text-slate-400">{s.usn ?? '—'}</td>
      <td className="px-4 py-2.5">
        <p className="text-xs text-slate-200 font-medium">{s.student_name}</p>
        <p className="text-xs text-slate-500">{s.email}</p>
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-400">
        {s.attended_sessions}/{s.total_sessions}
      </td>
      <td className="px-4 py-2.5">
        <span className="text-sm font-bold" style={{ color: pctColor(s.attendance_pct) }}>
          {s.attendance_pct.toFixed(1)}%
        </span>
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-500">
        {needed !== null ? `Need ${needed} more` : '—'}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Course+section card (collapsible)
// ---------------------------------------------------------------------------

function CourseCard({ c, threshold }: { c: FacultyCourseShortage; threshold: number }) {
  const [expanded, setExpanded] = useState(false)
  const ratio = c.total_enrolled > 0
    ? `${c.at_risk_count} of ${c.total_enrolled} students`
    : `${c.at_risk_count} students`

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(239,68,68,0.2)' }}>
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors"
        style={{ background: 'rgba(239,68,68,0.05)' }}
      >
        <div className="flex items-start gap-3 text-left">
          <AlertTriangle size={15} className="text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-slate-200">
              {c.course_code} — {c.course_title}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              Section {c.section_name} · Semester {c.semester_number} · {ratio} below threshold
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="text-xs px-2.5 py-1 rounded font-semibold"
            style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}>
            {c.at_risk_count} at risk
          </span>
          {expanded
            ? <ChevronDown size={16} className="text-slate-400" />
            : <ChevronRight size={16} className="text-slate-400" />
          }
        </div>
      </button>

      {expanded && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          {c.students.length === 0 ? (
            <p className="px-5 py-4 text-sm text-slate-500">No students below threshold.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                  {['USN', 'Student', 'Attended / Countable', '%', 'Sessions Needed'].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {c.students.map(s => (
                  <StudentRow key={s.student_id} s={s} threshold={threshold} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function FacultyShortageReportPage() {
  const [threshold, setThreshold] = useState(75)
  const [thresholdInput, setThresholdInput] = useState('75')
  const [finalizedOnly, setFinalizedOnly] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['faculty-shortage', threshold, finalizedOnly],
    queryFn: () => sisApi.getFacultyShortage({ threshold, finalized_only: finalizedOnly }),
  })

  function applyThreshold() {
    const v = parseFloat(thresholdInput)
    if (!isNaN(v) && v >= 0 && v <= 100) setThreshold(v)
  }

  const selectClass = "rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-2 focus:ring-indigo-500"
  const selectStyle = { background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Shortage Report — My Courses"
        subtitle="Students below the attendance threshold in your assigned courses"
      />

      {/* Advisory disclaimer — always visible */}
      <div className="mt-5 rounded-lg p-3 flex gap-2 text-xs text-slate-400"
        style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)' }}>
        <Info size={13} className="shrink-0 mt-0.5 text-indigo-400" />
        This report is <strong className="text-slate-300 mx-1">advisory only</strong>.
        Attendance action (counselling, follow-up) requires academic authority decision.
        No automatic action is taken by the system.
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mt-5 mb-5 items-end">
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Shortage Threshold (%)</label>
          <div className="flex gap-2">
            <input type="number" min={0} max={100} value={thresholdInput}
              onChange={e => setThresholdInput(e.target.value)}
              className={`${selectClass} w-24`} style={selectStyle} />
            <Button onClick={applyThreshold} variant="outline"
              className="border-slate-600 text-slate-300 text-sm">
              Apply
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-2 pb-1">
          <input
            type="checkbox"
            id="finalized-only"
            checked={finalizedOnly}
            onChange={e => setFinalizedOnly(e.target.checked)}
            className="accent-indigo-500"
          />
          <label htmlFor="finalized-only" className="text-xs text-slate-400 flex items-center gap-1.5 cursor-pointer">
            <Lock size={11} className="text-slate-500" />
            Finalized sessions only (LOCKED)
          </label>
        </div>
      </div>

      {isLoading ? <PageLoading /> : isError ? (
        <div className="rounded-xl py-10 text-center text-red-400 text-sm"
          style={{ border: '1px solid rgba(239,68,68,0.2)' }}>
          Could not load shortage report.
        </div>
      ) : data ? (
        <div className="space-y-4">
          {/* Summary bar */}
          {data.total_at_risk > 0 && (
            <div className="flex flex-wrap gap-3 mb-2">
              <div className="rounded-xl px-5 py-4 flex-1 min-w-[140px]"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                <p className="text-xs text-slate-400">Total Students at Risk</p>
                <p className="text-3xl font-bold text-red-400 mt-1">{data.total_at_risk}</p>
              </div>
              <div className="rounded-xl px-5 py-4 flex-1 min-w-[140px]"
                style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)' }}>
                <p className="text-xs text-slate-400">Courses with Shortage</p>
                <p className="text-3xl font-bold text-yellow-400 mt-1">{data.courses.length}</p>
              </div>
            </div>
          )}

          {/* Finalized-only note */}
          {finalizedOnly && (
            <div className="rounded-lg p-2.5 flex gap-2 text-xs text-slate-400"
              style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}>
              <Lock size={11} className="shrink-0 mt-0.5 text-indigo-400" />
              Showing data from LOCKED sessions only. Open/pending sessions are excluded.
            </div>
          )}

          {/* Course cards */}
          {data.courses.length === 0 ? (
            <div className="rounded-xl py-12 text-center"
              style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
              <CheckCircle2 size={32} className="mx-auto mb-3 text-green-400 opacity-60" />
              <p className="text-sm font-medium text-slate-300">No students below {threshold}%</p>
              <p className="text-xs text-slate-500 mt-1">
                All students in your assigned courses meet the attendance threshold.
              </p>
            </div>
          ) : (
            data.courses.map(c => (
              <CourseCard
                key={`${c.course_id}-${c.section_id}`}
                c={c}
                threshold={threshold}
              />
            ))
          )}
        </div>
      ) : null}
    </PageShell>
  )
}
