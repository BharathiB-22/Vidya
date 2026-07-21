// Faculty — Performance Analytics: attendance shortage in my courses.
//
// The colours here were written for a dark surface (slate-200 text, white-alpha
// borders, translucent fills) but the app shell is bg-gray-50. Near-white text on
// a light background is what made this page hard to read: the numbers a faculty
// member comes here for — who is at risk, by how much — were the faintest things
// on the screen.
//
// Same layout, same structure, readable palette: body text at gray-700/900,
// muted text no lighter than gray-500, solid borders, and the figures that carry
// the meaning set bold in a colour that passes against white.
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

/** Severity of a shortage. Darkened from the previous 400-weights, which were
 *  mixed for a dark surface and washed out on white — amber-400 text on white is
 *  roughly 1.7:1, well under the 4.5:1 a number this important needs. */
function pctColor(p: number): string {
  if (p < 50) return 'text-red-700'
  if (p < 65) return 'text-orange-700'
  return 'text-amber-700'
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
    <tr className="border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-2.5 text-xs font-mono text-gray-600">{s.usn ?? '—'}</td>
      <td className="px-4 py-2.5">
        <p className="text-sm font-semibold text-gray-900">{s.student_name}</p>
        <p className="text-xs text-gray-500">{s.email}</p>
      </td>
      <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">
        <span className="font-semibold text-gray-900">{s.attended_sessions}</span>
        <span className="text-gray-600"> / {s.total_sessions}</span>
      </td>
      <td className="px-4 py-2.5">
        <span className={`text-base font-bold tabular-nums ${pctColor(s.attendance_pct)}`}>
          {s.attendance_pct.toFixed(1)}%
        </span>
      </td>
      <td className="px-4 py-2.5 text-sm text-gray-700">
        {needed !== null
          ? <><span className="font-bold text-gray-900 tabular-nums">{needed}</span> more</>
          : <span className="text-gray-600">—</span>}
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
    <div className="rounded-xl overflow-hidden border border-red-200 bg-white">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 bg-red-50/70 hover:bg-red-50 transition-colors"
      >
        <div className="flex items-start gap-3 text-left">
          <AlertTriangle size={16} className="text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-bold text-gray-900">
              {c.course_code} — {c.course_title}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">
              Section {c.section_name} · Semester {c.semester_number} ·{' '}
              <span className="font-semibold text-gray-800">{ratio}</span> below threshold
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="text-xs px-2.5 py-1 rounded font-bold bg-red-100 text-red-800 border border-red-300 tabular-nums">
            {c.at_risk_count} at risk
          </span>
          {expanded
            ? <ChevronDown size={16} className="text-gray-500" />
            : <ChevronRight size={16} className="text-gray-500" />
          }
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-200">
          {c.students.length === 0 ? (
            <p className="px-5 py-4 text-sm text-gray-500">No students below threshold.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {['USN', 'Student', 'Attended / Countable', '%', 'Sessions Needed'].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      {h}
                    </th>
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
// KPI card
// ---------------------------------------------------------------------------

function StatCard({
  label, value, tone,
}: { label: string; value: number; tone: 'red' | 'amber' }) {
  const styles = tone === 'red'
    ? { box: 'border-red-200 bg-red-50', num: 'text-red-700' }
    : { box: 'border-amber-200 bg-amber-50', num: 'text-amber-700' }
  return (
    <div className={`rounded-xl px-5 py-4 flex-1 min-w-[160px] border ${styles.box}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-600">{label}</p>
      <p className={`text-3xl font-bold mt-1 tabular-nums ${styles.num}`}>{value}</p>
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

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Shortage Report — My Courses"
        subtitle="Students below the attendance threshold in your assigned courses"
      />

      {/* Advisory disclaimer — always visible */}
      <div className="mt-5 rounded-lg p-3 flex gap-2 text-xs text-gray-700 bg-indigo-50 border border-indigo-200">
        <Info size={14} className="shrink-0 mt-0.5 text-indigo-600" />
        <span>
          This report is <strong className="font-bold text-gray-900">advisory only</strong>.
          Attendance action (counselling, follow-up) requires an academic authority
          decision. No automatic action is taken by the system.
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mt-5 mb-5 items-end">
        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1.5">
            Shortage Threshold (%)
          </label>
          <div className="flex gap-2">
            <input
              type="number" min={0} max={100} value={thresholdInput}
              onChange={e => setThresholdInput(e.target.value)}
              className="w-24 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white border border-gray-300
                         outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <Button onClick={applyThreshold} variant="outline" className="text-sm">
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
            className="accent-indigo-600 w-4 h-4"
          />
          <label htmlFor="finalized-only" className="text-xs text-gray-700 flex items-center gap-1.5 cursor-pointer">
            <Lock size={12} className="text-gray-500" />
            Finalized sessions only (LOCKED)
          </label>
        </div>
      </div>

      {isLoading ? <PageLoading /> : isError ? (
        <div className="rounded-xl py-10 text-center text-red-700 text-sm font-medium border border-red-200 bg-red-50">
          Could not load shortage report.
        </div>
      ) : data ? (
        <div className="space-y-4">
          {/* Summary bar — the two numbers this page exists to show. */}
          {data.total_at_risk > 0 && (
            <div className="flex flex-wrap gap-3 mb-2">
              <StatCard label="Total Students at Risk" value={data.total_at_risk} tone="red" />
              <StatCard label="Courses with Shortage" value={data.courses.length} tone="amber" />
            </div>
          )}

          {/* Finalized-only note */}
          {finalizedOnly && (
            <div className="rounded-lg p-2.5 flex gap-2 text-xs text-gray-700 bg-indigo-50 border border-indigo-200">
              <Lock size={12} className="shrink-0 mt-0.5 text-indigo-600" />
              Showing data from LOCKED sessions only. Open/pending sessions are excluded.
            </div>
          )}

          {/* Course cards */}
          {data.courses.length === 0 ? (
            <div className="rounded-xl py-12 text-center border border-gray-200 bg-white">
              <CheckCircle2 size={32} className="mx-auto mb-3 text-green-600" />
              <p className="text-sm font-semibold text-gray-800">No students below {threshold}%</p>
              <p className="text-xs text-gray-500 mt-1">
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
