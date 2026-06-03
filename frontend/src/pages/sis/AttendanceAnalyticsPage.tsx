import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart2, AlertTriangle, Clock, CheckCircle2, Users, Info } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { ShortageStudentOut } from '@/lib/api/sis'
import { useQuery as useAcadQuery } from '@tanstack/react-query'
import { academicsApi } from '@/lib/api/academics'

// ---------------------------------------------------------------------------
// Dashboard cards
// ---------------------------------------------------------------------------

function DashCard({ label, value, color, icon: Icon }: {
  label: string; value: number; color: string; icon: typeof BarChart2
}) {
  return (
    <div className="rounded-xl px-5 py-4 flex-1 min-w-[130px]"
      style={{ background: `${color}10`, border: `1px solid ${color}33` }}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} style={{ color }} />
        <p className="text-xs text-slate-400">{label}</p>
      </div>
      <p className="text-3xl font-bold" style={{ color }}>{value}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shortage table
// ---------------------------------------------------------------------------

function ShortageTable({ students }: { students: ShortageStudentOut[] }) {
  if (students.length === 0) {
    return (
      <div className="rounded-xl py-10 text-center text-slate-500 text-sm"
        style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <CheckCircle2 size={28} className="mx-auto mb-2 text-green-400 opacity-60" />
        No students below threshold.
      </div>
    )
  }

  function pctColor(p: number) {
    if (p < 50) return '#f87171'
    if (p < 65) return '#fb923c'
    return '#fbbf24'
  }

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
      <table className="w-full text-sm">
        <thead>
          <tr style={{ background: 'rgba(255,255,255,0.04)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
            {['USN', 'Student', 'Course', 'Section', 'Attended', '%'].map(h => (
              <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-400">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {students.map((s, i) => (
            <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
              className="hover:bg-white/[0.02]">
              <td className="px-4 py-3 text-xs font-mono text-slate-400">{s.usn ?? '—'}</td>
              <td className="px-4 py-3">
                <p className="text-xs text-slate-200 font-medium">{s.student_name}</p>
                <p className="text-xs text-slate-500">{s.email}</p>
              </td>
              <td className="px-4 py-3 text-xs text-slate-300">{s.course_code} – {s.course_title}</td>
              <td className="px-4 py-3 text-xs text-slate-400">{s.section_name}</td>
              <td className="px-4 py-3 text-xs text-slate-400">
                {s.attended_sessions}/{s.total_countable}
              </td>
              <td className="px-4 py-3">
                <span className="text-sm font-bold" style={{ color: pctColor(s.attendance_pct) }}>
                  {s.attendance_pct.toFixed(1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AttendanceAnalyticsPage() {
  const [threshold, setThreshold] = useState(75)
  const [thresholdInput, setThresholdInput] = useState('75')
  const [semesterId, setSemesterId] = useState('')

  const { data: semesters = [] } = useAcadQuery({
    queryKey: ['semesters-for-analytics'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const { data: dashboard, isLoading: dashLoading } = useQuery({
    queryKey: ['attendance-dashboard', semesterId, threshold],
    queryFn: () => sisApi.getAttendanceDashboard({
      semester_id: semesterId || undefined,
      threshold,
    }),
  })

  const { data: shortage, isLoading: shortageLoading } = useQuery({
    queryKey: ['shortage-report', semesterId, threshold],
    queryFn: () => sisApi.getShortageReport({
      threshold,
      semester_id: semesterId || undefined,
    }),
  })

  function applyThreshold() {
    const v = parseFloat(thresholdInput)
    if (!isNaN(v) && v >= 0 && v <= 100) setThreshold(v)
  }

  const selectClass = "rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-2 focus:ring-indigo-500"
  const selectStyle = { background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }

  return (
    <PageShell>
      <PageHeader icon={BarChart2} title="Attendance Analytics"
        subtitle="Monitor attendance trends and identify students at risk" />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mt-6 mb-5 items-end">
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Semester</label>
          <select value={semesterId} onChange={e => setSemesterId(e.target.value)}
            className={selectClass} style={selectStyle}>
            <option value="">All Semesters</option>
            {semesters.map(s => (
              <option key={s.id} value={s.id}>Sem {s.number}{s.label ? ` — ${s.label}` : ''}</option>
            ))}
          </select>
        </div>
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
      </div>

      {/* Dashboard cards */}
      {dashLoading ? <PageLoading /> : dashboard ? (
        <div className="flex flex-wrap gap-3 mb-6">
          <DashCard label="Today's Sessions"   value={dashboard.today_sessions}           color="#a5b4fc" icon={Clock} />
          <DashCard label="Marked Today"       value={dashboard.marked_today}             color="#4ade80" icon={CheckCircle2} />
          <DashCard label="Pending Sessions"   value={dashboard.pending_sessions}         color="#fb923c" icon={AlertTriangle} />
          <DashCard label={`Below ${threshold}%`} value={dashboard.students_below_threshold} color="#f87171" icon={Users} />
        </div>
      ) : null}

      {/* Pending warning */}
      {dashboard && dashboard.pending_sessions > 0 && (
        <div className="mb-5 rounded-lg p-3 flex gap-2 text-xs text-orange-300"
          style={{ background: 'rgba(251,146,60,0.07)', border: '1px solid rgba(251,146,60,0.25)' }}>
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          {dashboard.pending_sessions} session{dashboard.pending_sessions > 1 ? 's' : ''} have not been marked yet.
          Faculty should be reminded to submit attendance.
        </div>
      )}

      {/* Shortage report */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">
            Shortage Report
            <span className="text-slate-400 font-normal ml-2">— students below {threshold}%</span>
          </h2>
          {shortage && (
            <span className="text-xs text-slate-400">{shortage.total_at_risk} students</span>
          )}
        </div>

        {/* Advisory disclaimer — always visible */}
        <div className="rounded-lg p-3 flex gap-2 text-xs text-slate-400"
          style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)' }}>
          <Info size={13} className="shrink-0 mt-0.5 text-indigo-400" />
          This report is <strong>advisory only</strong>. Attendance action (e.g., detainment, counselling)
          requires explicit DEAN or ADMIN decision. No automatic action is taken by the system.
        </div>

        {shortageLoading ? <PageLoading /> : shortage ? (
          <ShortageTable students={shortage.students} />
        ) : null}
      </div>
    </PageShell>
  )
}
