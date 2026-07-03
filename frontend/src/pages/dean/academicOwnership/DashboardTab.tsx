import { GraduationCap, BookOpen, Users, AlertTriangle, TrendingUp, LayoutGrid } from 'lucide-react'
import { PageLoading } from '@/components/shared/PageLoading'
import { useOwnershipDashboardSummary } from '@/hooks/useOwnership'

function StatCard({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  color: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4">
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
    </div>
  )
}

export default function DashboardTab() {
  const { data, isLoading } = useOwnershipDashboardSummary()

  if (isLoading) return <PageLoading />
  if (!data) return null

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon={LayoutGrid}      label="Total Programs"    value={data.total_programs}    color="#6366f1" />
        <StatCard icon={BookOpen}        label="Total Courses"     value={data.total_courses}      color="#10b981" />
        <StatCard icon={Users}           label="Total Faculty"     value={data.total_faculty}      color="#0ea5e9" />
        <StatCard icon={AlertTriangle}   label="Vacant Courses"    value={data.vacant_courses}     color="#f59e0b" />
        <StatCard icon={TrendingUp}      label="Program Coverage"  value={`${data.program_coverage_pct}%`} color="#ec4899" />
        <StatCard icon={GraduationCap}   label="Faculty w/ Load"   value={data.faculty_workload.length} color="#8b5cf6" />
      </div>

      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-foreground">Faculty Workload</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Active course and program count per faculty member, across programs you govern.
          </p>
        </div>
        {data.faculty_workload.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            No active teaching assignments yet.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {data.faculty_workload.map(w => (
              <div key={w.faculty_user_id} className="flex items-center justify-between gap-3 px-5 py-3">
                <span className="text-sm font-medium text-foreground">{w.faculty_name}</span>
                <div className="flex items-center gap-4 text-xs text-muted-foreground flex-shrink-0">
                  <span>{w.course_count} course{w.course_count !== 1 ? 's' : ''}</span>
                  <span>{w.program_count} program{w.program_count !== 1 ? 's' : ''}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
