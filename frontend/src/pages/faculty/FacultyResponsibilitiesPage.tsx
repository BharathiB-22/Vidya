import { BookUser, Building2, GraduationCap, BookOpen, CalendarDays, Users } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { useFacultyResponsibilities } from '@/hooks/useOwnership'
import type { FacultyCourseEntry, FacultyResponsibilityProgram } from '@/lib/api/ownership'

const ROLE_COLORS: Record<string, string> = {
  PRIMARY:    '#6366f1',
  CO_FACULTY: '#10b981',
  GUEST:      '#f59e0b',
}

function RoleChip({ role }: { role: string }) {
  const color = ROLE_COLORS[role] ?? '#6b7280'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}
    >
      {role.replace('_', ' ')}
    </span>
  )
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: React.FC<{ className?: string }>
  label: string
  value: number
  color: string
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 flex items-center gap-4">
      <div
        className="p-2.5 rounded-lg"
        style={{ background: `${color}15`, color }}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      </div>
    </div>
  )
}

function SectionHeading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap">
        {label}
      </h2>
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  )
}

function ProgramRow({ p }: { p: FacultyResponsibilityProgram }) {
  return (
    <div className="flex items-start justify-between gap-3 py-3 border-b border-gray-100 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-gray-900">{p.name}</span>
          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-mono">
            {p.code}
          </span>
          {p.is_primary && (
            <span className="text-xs bg-sv-primary/10 text-sv-primary px-1.5 py-0.5 rounded font-medium">
              Primary
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-xs text-gray-400">{p.degree_type}</span>
          {p.department && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {p.department.name}
              </span>
            </>
          )}
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        {p.assigned_by_name && (
          <p className="text-xs text-gray-400">
            Assigned by <span className="text-gray-600">{p.assigned_by_name}</span>
          </p>
        )}
        <p className="text-xs text-gray-400 mt-0.5">
          {new Date(p.assigned_at).toLocaleDateString('en-IN', {
            day: '2-digit', month: 'short', year: 'numeric',
          })}
        </p>
      </div>
    </div>
  )
}

function CourseRow({ c }: { c: FacultyCourseEntry }) {
  return (
    <div className={`flex items-start justify-between gap-3 py-3 border-b border-gray-100 last:border-0 ${!c.is_active ? 'opacity-50' : ''}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
            {c.code}
          </span>
          <span className="text-sm font-medium text-gray-900 truncate">{c.title}</span>
          {!c.is_active && (
            <span className="text-xs text-gray-400 bg-gray-100 px-1.5 rounded">Inactive</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-xs text-gray-400">
            Semester {c.semester_number}{c.semester_label ? ` — ${c.semester_label}` : ''}
          </span>
          {c.section_name && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-xs text-gray-400">Section {c.section_name}</span>
            </>
          )}
        </div>
      </div>
      <RoleChip role={c.role_in_course} />
    </div>
  )
}

export default function FacultyResponsibilitiesPage() {
  const { data, isLoading, error } = useFacultyResponsibilities()

  return (
    <PageShell>
      <PageHeader
        title="My Academic Responsibilities"
        subtitle="Departments, programs, and courses you are assigned to."
        icon={BookUser}
      />

      {isLoading && <PageLoading />}

      {error && (
        <div className="text-center py-16 text-red-400 text-sm">
          Failed to load responsibilities. Please refresh.
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <StatCard icon={Building2}    label="Departments" value={data.departments.length}       color="#6366f1" />
            <StatCard icon={GraduationCap} label="Programs"   value={data.programs.length}          color="#10b981" />
            <StatCard icon={BookOpen}      label="Courses"    value={data.course_assignments.length} color="#f59e0b" />
          </div>

          {/* Departments */}
          {data.departments.length > 0 && (
            <div>
              <SectionHeading label="Departments" />
              <div className="flex flex-wrap gap-2">
                {data.departments.map(d => (
                  <div
                    key={d.id}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 bg-white"
                  >
                    <Building2 className="h-4 w-4 text-sv-primary" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{d.name}</p>
                      <p className="text-xs text-gray-400 font-mono">{d.code}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Programs */}
          {data.programs.length > 0 ? (
            <div>
              <SectionHeading label="Programs" />
              <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 px-4">
                {data.programs.map(p => (
                  <ProgramRow key={`${p.id}-${p.assigned_at}`} p={p} />
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-200 py-10 text-center">
              <GraduationCap className="h-8 w-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400">No program assignments yet.</p>
              <p className="text-xs text-gray-400 mt-1">Your dean will assign you to programs.</p>
            </div>
          )}

          {/* Courses */}
          {data.course_assignments.length > 0 && (
            <div>
              <SectionHeading label="Course Assignments" />
              <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 px-4">
                {data.course_assignments.map(c => (
                  <CourseRow key={c.assignment_id} c={c} />
                ))}
              </div>
            </div>
          )}

          {data.departments.length === 0 && data.programs.length === 0 && data.course_assignments.length === 0 && (
            <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
              <Users className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm font-medium text-gray-500">No responsibilities assigned yet</p>
              <p className="text-xs text-gray-400 mt-1">
                Contact your dean or administrator to get assigned to programs and courses.
              </p>
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
