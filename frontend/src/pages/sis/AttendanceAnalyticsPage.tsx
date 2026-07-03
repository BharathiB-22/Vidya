import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart2, AlertTriangle, Clock, CheckCircle2, Users, Info, Lock, ChevronDown, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type { ShortageStudentOut, ShortageCourseGroup } from '@/lib/api/sis'
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
// Flat shortage table
// ---------------------------------------------------------------------------

function pctColor(p: number) {
  if (p < 50) return '#f87171'
  if (p < 65) return '#fb923c'
  return '#fbbf24'
}

function FlatShortageTable({ students }: { students: ShortageStudentOut[] }) {
  if (students.length === 0) {
    return (
      <div className="rounded-xl py-10 text-center text-slate-500 text-sm"
        style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <CheckCircle2 size={28} className="mx-auto mb-2 text-green-400 opacity-60" />
        No students below threshold.
      </div>
    )
  }

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
      <table className="w-full text-sm">
        <thead>
          <tr style={{ background: 'rgba(255,255,255,0.04)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
            {['USN', 'Student', 'Course', 'Section', 'Sem', 'Attended', '%'].map(h => (
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
              <td className="px-4 py-3 text-xs text-slate-400">{s.semester_number ?? '—'}</td>
              <td className="px-4 py-3 text-xs text-slate-400">
                {s.attended_sessions}/{s.total_sessions}
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
// Grouped shortage view
// ---------------------------------------------------------------------------

function GroupedCourseRow({ c }: { c: ShortageCourseGroup }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.1)' }}>
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors"
        style={{ background: 'rgba(255,255,255,0.03)' }}
      >
        <div className="flex items-center gap-3 text-left">
          <div>
            <p className="text-sm font-semibold text-slate-200">{c.course_code} — {c.course_title}</p>
            <p className="text-xs text-slate-400 mt-0.5">{c.sections.length} section(s)</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs px-2.5 py-1 rounded font-semibold"
            style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}>
            {c.total_at_risk} at risk
          </span>
          {expanded
            ? <ChevronDown size={16} className="text-slate-400" />
            : <ChevronRight size={16} className="text-slate-400" />
          }
        </div>
      </button>

      {expanded && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          {c.sections.map(sec => (
            <div key={sec.section_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div className="px-5 py-2.5 flex items-center justify-between"
                style={{ background: 'rgba(255,255,255,0.02)' }}>
                <p className="text-xs font-semibold text-slate-300">
                  Section {sec.section_name} · Sem {sec.semester_number}
                </p>
                <div className="flex items-center gap-3 text-xs text-slate-400">
                  {sec.avg_pct !== null && (
                    <span>Avg: <span style={{ color: pctColor(sec.avg_pct) }}>{sec.avg_pct.toFixed(1)}%</span></span>
                  )}
                  <span>{sec.at_risk_count} students</span>
                </div>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    {['USN', 'Student', 'Attended / Total', '%'].map(h => (
                      <th key={h} className="px-4 py-2 text-left text-xs font-medium text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sec.students.map((s, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                      className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2 text-xs font-mono text-slate-400">{s.usn ?? '—'}</td>
                      <td className="px-4 py-2">
                        <p className="text-xs text-slate-200">{s.student_name}</p>
                        <p className="text-xs text-slate-500">{s.email}</p>
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-400">
                        {s.attended_sessions}/{s.total_sessions}
                      </td>
                      <td className="px-4 py-2">
                        <span className="text-sm font-bold" style={{ color: pctColor(s.attendance_pct) }}>
                          {s.attendance_pct.toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function GroupedShortageView({ courses }: { courses: ShortageCourseGroup[] }) {
  if (courses.length === 0) {
    return (
      <div className="rounded-xl py-10 text-center text-slate-500 text-sm"
        style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <CheckCircle2 size={28} className="mx-auto mb-2 text-green-400 opacity-60" />
        No students below threshold.
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {courses.map(c => <GroupedCourseRow key={c.course_id} c={c} />)}
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
  const [programId, setProgramId] = useState('')
  const [batchId, setBatchId] = useState('')
  const [finalizedOnly, setFinalizedOnly] = useState(false)
  const [viewMode, setViewMode] = useState<'flat' | 'grouped'>('flat')

  const { data: semesters = [] } = useQuery({
    queryKey: ['semesters-for-analytics'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const { data: programs = [] } = useQuery({
    queryKey: ['programs-for-analytics'],
    queryFn: () => academicsApi.listPrograms(),
  })

  const { data: batches = [] } = useQuery({
    queryKey: ['batches-for-analytics', programId],
    queryFn: () => academicsApi.listBatches(programId || undefined),
  })

  const { data: dashboard, isLoading: dashLoading } = useQuery({
    queryKey: ['attendance-dashboard', semesterId, threshold],
    queryFn: () => sisApi.getAttendanceDashboard({
      semester_id: semesterId || undefined,
      threshold,
    }),
  })

  const { data: shortage, isLoading: shortageLoading } = useQuery({
    queryKey: ['shortage-report', semesterId, threshold, programId, batchId, finalizedOnly],
    queryFn: () => sisApi.getShortageReport({
      threshold,
      semester_id: semesterId || undefined,
      program_id: programId || undefined,
      batch_id: batchId || undefined,
      finalized_only: finalizedOnly,
    }),
    enabled: viewMode === 'flat',
  })

  const { data: grouped, isLoading: groupedLoading } = useQuery({
    queryKey: ['shortage-grouped', semesterId, threshold, programId, batchId, finalizedOnly],
    queryFn: () => sisApi.getShortageGrouped({
      threshold,
      semester_id: semesterId || undefined,
      program_id: programId || undefined,
      batch_id: batchId || undefined,
      finalized_only: finalizedOnly,
    }),
    enabled: viewMode === 'grouped',
  })

  function applyThreshold() {
    const v = parseFloat(thresholdInput)
    if (!isNaN(v) && v >= 0 && v <= 100) setThreshold(v)
  }

  const atRisk = viewMode === 'flat'
    ? (shortage?.total_at_risk ?? 0)
    : (grouped?.total_students_at_risk ?? 0)

  return (
    <PageShell>
      <PageHeader icon={BarChart2} title="Attendance Analytics"
        subtitle="Monitor attendance trends and identify students at risk" />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mt-6 mb-5 items-end">
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Semester</label>
          <Select value={semesterId || 'ALL'} onValueChange={v => setSemesterId(v === 'ALL' ? '' : v)}>
            <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Semesters" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Semesters</SelectItem>
              {semesters.map(s => (
                <SelectItem key={s.id} value={s.id}>Sem {s.number}{s.label ? ` — ${s.label}` : ''}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Program</label>
          <Select value={programId || 'ALL'} onValueChange={v => { setProgramId(v === 'ALL' ? '' : v); setBatchId('') }}>
            <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Programs" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Programs</SelectItem>
              {programs.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Batch</label>
          <Select value={batchId || 'ALL'} onValueChange={v => setBatchId(v === 'ALL' ? '' : v)} disabled={!programId}>
            <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Batches" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Batches</SelectItem>
              {batches.map(b => (
                <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Shortage Threshold (%)</label>
          <div className="flex gap-2">
            <input type="number" min={0} max={100} value={thresholdInput}
              onChange={e => setThresholdInput(e.target.value)}
              className="w-24 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:ring-2 focus:ring-indigo-500" />
            <Button onClick={applyThreshold} variant="outline"
              className="border-slate-600 text-slate-300 text-sm">
              Apply
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-2 pb-1">
          <input
            type="checkbox"
            id="finalized-only-analytics"
            checked={finalizedOnly}
            onChange={e => setFinalizedOnly(e.target.checked)}
            className="accent-indigo-500"
          />
          <label htmlFor="finalized-only-analytics" className="text-xs text-slate-400 flex items-center gap-1.5 cursor-pointer">
            <Lock size={11} className="text-slate-500" />
            Finalized only
          </label>
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

      {/* Pending sessions warning */}
      {dashboard && dashboard.pending_sessions > 0 && (
        <div className="mb-5 rounded-lg p-3 flex gap-2 text-xs text-orange-300"
          style={{ background: 'rgba(251,146,60,0.07)', border: '1px solid rgba(251,146,60,0.25)' }}>
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          {dashboard.pending_sessions} session{dashboard.pending_sessions > 1 ? 's' : ''} have not been marked yet.
          Enable "Finalized only" to see shortage based on locked sessions only.
        </div>
      )}

      {/* Shortage report section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h2 className="text-sm font-semibold text-slate-200">
            Shortage Report
            <span className="text-slate-400 font-normal ml-2">— students below {threshold}%</span>
          </h2>
          <div className="flex items-center gap-3">
            {atRisk > 0 && (
              <span className="text-xs text-slate-400">{atRisk} students</span>
            )}
            {/* View mode toggle */}
            <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.12)' }}>
              {(['flat', 'grouped'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className="px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    background: viewMode === mode ? 'rgba(99,102,241,0.25)' : 'rgba(255,255,255,0.03)',
                    color: viewMode === mode ? '#a5b4fc' : '#94a3b8',
                    borderRight: mode === 'flat' ? '1px solid rgba(255,255,255,0.08)' : undefined,
                  }}
                >
                  {mode === 'flat' ? 'Flat List' : 'By Course'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Finalized-only indicator */}
        {finalizedOnly && (
          <div className="rounded-lg p-2.5 flex gap-2 text-xs text-slate-400"
            style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}>
            <Lock size={11} className="shrink-0 mt-0.5 text-indigo-400" />
            Showing data from LOCKED sessions only. Open/pending sessions are excluded.
          </div>
        )}

        {/* Advisory disclaimer */}
        <div className="rounded-lg p-3 flex gap-2 text-xs text-slate-400"
          style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)' }}>
          <Info size={13} className="shrink-0 mt-0.5 text-indigo-400" />
          This report is <strong className="text-slate-300 mx-1">advisory only</strong>.
          Attendance action (e.g., detainment, counselling) requires explicit DEAN or ADMIN decision.
          No automatic action is taken by the system.
        </div>

        {/* Flat view */}
        {viewMode === 'flat' && (
          shortageLoading ? <PageLoading /> : shortage ? (
            <FlatShortageTable students={shortage.students} />
          ) : null
        )}

        {/* Grouped view */}
        {viewMode === 'grouped' && (
          groupedLoading ? <PageLoading /> : grouped ? (
            <>
              {grouped.total_courses_with_shortage > 0 && (
                <div className="flex gap-3 text-xs text-slate-400 mb-1">
                  <span>{grouped.total_courses_with_shortage} course(s) with shortage</span>
                  <span>·</span>
                  <span>{grouped.total_students_at_risk} unique student(s)</span>
                </div>
              )}
              <GroupedShortageView courses={grouped.courses} />
            </>
          ) : null
        )}
      </div>
    </PageShell>
  )
}
