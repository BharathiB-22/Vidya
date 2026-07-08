import { useNavigate } from 'react-router-dom'
import {
  GraduationCap, BookOpen, Users, AlertTriangle, TrendingUp, LayoutGrid,
  UserRoundCog, ClipboardList, Building2,
} from 'lucide-react'
import { PageLoading } from '@/components/shared/PageLoading'
import { useOwnershipDashboardSummary } from '@/hooks/useOwnership'

function StatCard({ icon: Icon, label, value, color, onClick }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  color: string
  onClick?: () => void
}) {
  const clickable = !!onClick
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!clickable}
      className={`flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 text-left w-full transition-all ${
        clickable ? 'hover:border-sv-primary/40 hover:shadow-md cursor-pointer' : 'cursor-default'
      }`}
    >
      <div
        className="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0"
        style={{ background: `${color}15`, color }}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-foreground">{value}</p>
        <p className="text-xs font-medium text-muted-foreground mt-0.5">{label}</p>
      </div>
    </button>
  )
}

/** Simple workload health: no courses → No Assignment; heavy (>6 courses or
 *  >20 published hrs/wk) → Overloaded; otherwise Balanced. */
function workloadStatus(courseCount: number, hoursPerWeek: number): { label: string; color: string } {
  if (courseCount === 0) return { label: 'No Assignment', color: '#6b7280' }
  if (hoursPerWeek > 20 || courseCount > 6) return { label: 'Overloaded', color: '#ef4444' }
  return { label: 'Balanced', color: '#10b981' }
}

export default function DashboardTab({ onNavigateTab }: { onNavigateTab?: (tab: string) => void }) {
  const { data, isLoading } = useOwnershipDashboardSummary()
  const navigate = useNavigate()

  if (isLoading) return <PageLoading />
  if (!data) return null

  const goTab = (t: string) => () => onNavigateTab?.(t)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <StatCard icon={LayoutGrid}    label="Programs Governed"        value={data.total_programs} color="#6366f1" onClick={goTab('program-ownership')} />
        <StatCard icon={BookOpen}      label="Courses"                  value={data.total_courses} color="#10b981" onClick={goTab('course-ownership')} />
        <StatCard icon={Users}         label="Faculty"                  value={data.total_faculty} color="#0ea5e9" onClick={() => navigate('/dean/my-faculty')} />
        <StatCard icon={GraduationCap} label="Students"                 value={data.total_students} color="#8b5cf6" onClick={() => navigate('/dean/my-students')} />
        <StatCard icon={AlertTriangle} label="Vacant Courses"           value={data.vacant_courses} color="#f59e0b" onClick={goTab('course-ownership')} />
        <StatCard icon={TrendingUp}    label="Teaching Coverage"        value={`${data.teaching_coverage_pct}%`} color="#ec4899" onClick={goTab('ownership-report')} />
        <StatCard icon={UserRoundCog}  label="Pending Faculty Alloc."   value={data.pending_faculty_allocation} color="#f97316" onClick={goTab('course-ownership')} />
        <StatCard icon={ClipboardList} label="Pending Course Alloc."    value={data.pending_course_allocation} color="#ef4444" onClick={goTab('ownership-report')} />
      </div>

      {/* Department Summary */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-foreground">Department Summary</h3>
        </div>
        {data.department_summary.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">No departments in scope.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-gray-100">
                  <th className="text-left font-medium px-5 py-2.5">Department</th>
                  <th className="text-right font-medium px-3 py-2.5">Programs</th>
                  <th className="text-right font-medium px-3 py-2.5">Courses</th>
                  <th className="text-right font-medium px-3 py-2.5">Faculty</th>
                  <th className="text-right font-medium px-5 py-2.5">Vacant</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.department_summary.map((d) => (
                  <tr key={d.department_id ?? 'unassigned'}>
                    <td className="px-5 py-2.5 font-medium text-foreground">{d.department_name}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">{d.program_count}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">{d.course_count}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">{d.faculty_count}</td>
                    <td className="px-5 py-2.5 text-right">
                      {d.vacant_courses > 0
                        ? <span className="text-amber-600 font-medium">{d.vacant_courses}</span>
                        : <span className="text-muted-foreground">0</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Faculty Workload */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-foreground">Faculty Workload</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Assigned courses, credits, sections, and published hours/week per faculty, across programs you govern.
          </p>
        </div>
        {data.faculty_workload.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            No active teaching assignments yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[620px]">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-gray-100">
                  <th className="text-left font-medium px-5 py-2.5">Faculty</th>
                  <th className="text-right font-medium px-3 py-2.5">Courses</th>
                  <th className="text-right font-medium px-3 py-2.5">Credits</th>
                  <th className="text-right font-medium px-3 py-2.5">Sections</th>
                  <th className="text-right font-medium px-3 py-2.5">Programs</th>
                  <th className="text-right font-medium px-3 py-2.5">Hours/Week</th>
                  <th className="text-left font-medium px-5 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.faculty_workload.map((w) => {
                  const status = workloadStatus(w.course_count, w.hours_per_week)
                  return (
                    <tr key={w.faculty_user_id}>
                      <td className="px-5 py-2.5 font-medium text-foreground">{w.faculty_name}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{w.course_count}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{w.credits}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{w.section_count}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{w.program_count}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{w.hours_per_week}</td>
                      <td className="px-5 py-2.5">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                          style={{ background: `${status.color}18`, color: status.color, border: `1px solid ${status.color}33` }}
                        >
                          {status.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
