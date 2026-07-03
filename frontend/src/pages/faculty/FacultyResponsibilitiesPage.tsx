import { useMemo } from 'react'
import { BookUser, Building2, GraduationCap, BookOpen, Users, Layers } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { SectionDivider } from '@/components/shell/SectionDivider'
import { PageLoading } from '@/components/shared/PageLoading'
import { ResponsibilityChip } from '@/components/shared/ResponsibilityChip'
import { useFacultyResponsibilities } from '@/hooks/useOwnership'
import type { FacultyCourseEntry, FacultyResponsibilityProgram } from '@/lib/api/ownership'

const ROLE_COLORS: Record<string, string> = {
  PRIMARY:    '#6366f1',
  CO_FACULTY: '#10b981',
  GUEST:      '#f59e0b',
}

const UNASSIGNED_DEPT = 'unassigned-dept'
const UNASSIGNED_PROGRAM = 'unassigned-program'

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
        <p className="text-2xl font-bold text-foreground">{value}</p>
        <p className="text-xs font-medium text-foreground mt-0.5">{label}</p>
      </div>
    </div>
  )
}

function CourseRow({ c }: { c: FacultyCourseEntry }) {
  return (
    <div className={`flex items-start justify-between gap-3 py-3 border-b border-gray-100 last:border-0 ${!c.is_active ? 'opacity-50' : ''}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs bg-gray-100 text-muted-foreground px-1.5 py-0.5 rounded">
            {c.code}
          </span>
          <span className="text-sm font-semibold text-foreground truncate">{c.title}</span>
          {!c.is_active && (
            <span className="text-xs text-muted-foreground bg-gray-100 px-1.5 rounded">Inactive</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-xs font-medium text-foreground">
            Semester {c.semester_number}{c.semester_label ? ` — ${c.semester_label}` : ''}
          </span>
          {c.section_name && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-xs font-medium text-foreground">Section {c.section_name}</span>
            </>
          )}
        </div>
      </div>
      <RoleChip role={c.role_in_course} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hierarchy: Department -> Program -> Course
//
// Built strictly from the course's own resolved program/department (Course ->
// Semester -> Batch -> Program -> Department, per the backend join chain) so
// a course can never render disconnected from an unrelated program/department
// pairing shown elsewhere on the page.
// ---------------------------------------------------------------------------

interface ProgramNode {
  programKey:     string
  programId:      string | null
  programName:    string
  programCode:    string | null
  degreeType:     string | null
  isPrimary:      boolean
  source:         'APPOINTED' | 'TEACHING' | null
  assignedByName: string | null
  assignedAt:     string | null
  courses:        FacultyCourseEntry[]
}

interface DeptNode {
  deptKey:   string
  deptId:    string | null
  deptName:  string
  deptCode:  string | null
  programs:  Map<string, ProgramNode>
}

function buildHierarchy(
  courses: FacultyCourseEntry[],
  grants: FacultyResponsibilityProgram[],
): DeptNode[] {
  const depts = new Map<string, DeptNode>()

  function getDept(deptId: string | null, deptName: string, deptCode: string | null): DeptNode {
    const key = deptId ?? UNASSIGNED_DEPT
    let node = depts.get(key)
    if (!node) {
      node = { deptKey: key, deptId, deptName, deptCode, programs: new Map() }
      depts.set(key, node)
    }
    return node
  }

  function getProgram(
    dept: DeptNode,
    programId: string | null,
    programName: string,
    programCode: string | null,
  ): ProgramNode {
    const key = programId ?? UNASSIGNED_PROGRAM
    let node = dept.programs.get(key)
    if (!node) {
      node = {
        programKey: key,
        programId,
        programName,
        programCode,
        degreeType: null,
        isPrimary: false,
        source: null,
        assignedByName: null,
        assignedAt: null,
        courses: [],
      }
      dept.programs.set(key, node)
    }
    return node
  }

  for (const c of courses) {
    const dept = getDept(c.department_id, c.department_name ?? 'Unassigned Department', null)
    const prog = getProgram(dept, c.program_id, c.program_name ?? 'Unassigned Program', c.program_code)
    if (!prog.source) prog.source = 'TEACHING'
    prog.courses.push(c)
  }

  for (const g of grants) {
    const dept = getDept(g.department?.id ?? null, g.department?.name ?? 'Unassigned Department', g.department?.code ?? null)
    const prog = getProgram(dept, g.id, g.name, g.code)
    prog.degreeType = g.degree_type
    prog.isPrimary = g.is_primary
    prog.source = g.source
    prog.assignedByName = g.assigned_by_name
    prog.assignedAt = g.assigned_at
  }

  const deptList = Array.from(depts.values())
  for (const dept of deptList) {
    for (const prog of dept.programs.values()) {
      prog.courses.sort((a, b) => a.semester_number - b.semester_number || a.code.localeCompare(b.code))
    }
  }
  deptList.sort((a, b) => {
    if (a.deptKey === UNASSIGNED_DEPT) return 1
    if (b.deptKey === UNASSIGNED_DEPT) return -1
    return a.deptName.localeCompare(b.deptName)
  })
  return deptList
}

function ProgramGroup({ prog }: { prog: ProgramNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-gray-100">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <GraduationCap className="h-4 w-4 text-sv-primary flex-shrink-0" />
            <span className="text-sm font-semibold text-foreground">{prog.programName}</span>
            {prog.programCode && (
              <span className="text-xs bg-gray-100 text-muted-foreground px-1.5 py-0.5 rounded font-mono">
                {prog.programCode}
              </span>
            )}
            {prog.isPrimary && (
              <span
                className="text-xs px-1.5 py-0.5 rounded font-semibold"
                style={{ background: 'rgba(236,72,153,0.12)', color: '#db2777', border: '1px solid rgba(236,72,153,0.25)' }}
              >
                Coordinator
              </span>
            )}
            {prog.source === 'APPOINTED' ? (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                style={{ background: 'rgba(99,102,241,0.10)', color: '#4f46e5', border: '1px solid rgba(99,102,241,0.20)' }}
              >
                Appointed
              </span>
            ) : prog.source === 'TEACHING' ? (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                style={{ background: 'rgba(16,185,129,0.10)', color: '#059669', border: '1px solid rgba(16,185,129,0.20)' }}
              >
                Teaching
              </span>
            ) : null}
          </div>
          {prog.degreeType && (
            <p className="text-xs text-muted-foreground mt-0.5">{prog.degreeType}</p>
          )}
        </div>
        {prog.assignedByName && (
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-muted-foreground">
              Assigned by <span className="text-muted-foreground font-medium">{prog.assignedByName}</span>
            </p>
            {prog.assignedAt && (
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(prog.assignedAt).toLocaleDateString('en-IN', {
                  day: '2-digit', month: 'short', year: 'numeric',
                })}
              </p>
            )}
          </div>
        )}
      </div>
      <div className="px-4">
        {prog.courses.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {prog.courses.map(c => <CourseRow key={c.assignment_id} c={c} />)}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground py-3">No active teaching assignments yet.</p>
        )}
      </div>
    </div>
  )
}

function DepartmentGroup({ dept }: { dept: DeptNode }) {
  const programs = Array.from(dept.programs.values()).sort((a, b) => {
    if (a.programKey === UNASSIGNED_PROGRAM) return 1
    if (b.programKey === UNASSIGNED_PROGRAM) return -1
    return a.programName.localeCompare(b.programName)
  })
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="text-base font-bold text-foreground">{dept.deptName}</span>
        {dept.deptCode && (
          <span className="text-xs text-muted-foreground font-mono">{dept.deptCode}</span>
        )}
      </div>
      <div className="space-y-3 pl-6">
        {programs.map(prog => <ProgramGroup key={prog.programKey} prog={prog} />)}
      </div>
    </div>
  )
}

export default function FacultyResponsibilitiesPage() {
  const { data, isLoading, error } = useFacultyResponsibilities()

  const hierarchy = useMemo(
    () => (data ? buildHierarchy(data.course_assignments, data.programs) : []),
    [data],
  )

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
          {/* Identity — home department + responsibilities the login carries */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 flex-shrink-0" style={{ color: '#6b7280' }} />
                <span className="text-xs font-medium" style={{ color: '#6B7280' }}>Home Department</span>
                <span className="text-sm font-semibold" style={{ color: '#111827' }}>
                  {data.home_department
                    ? `${data.home_department.name}${data.home_department.code ? ` (${data.home_department.code})` : ''}`
                    : 'Not assigned'}
                </span>
              </div>
            </div>
            <div>
              <p className="text-xs font-medium mb-1.5" style={{ color: '#6B7280' }}>Responsibilities</p>
              {/* data.responsibilities is the complete, de-duplicated list from the
                  backend — it already includes the base login role (FACULTY/DEAN)
                  first, so nothing is hardcoded here. */}
              {data.responsibilities.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {data.responsibilities.map(r => <ResponsibilityChip key={r} role={r} />)}
                </div>
              ) : (
                <span className="text-xs" style={{ color: '#9CA3AF' }}>No responsibilities found.</span>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard icon={Building2}    label="Departments"      value={data.departments.length}                              color="#6366f1" />
            <StatCard icon={GraduationCap} label="Programs"        value={data.programs.length}                                 color="#10b981" />
            <StatCard icon={BookOpen}      label="Courses"         value={data.course_assignments.filter(c => c.is_active).length} color="#f59e0b" />
            <StatCard icon={Layers}        label="Sections"        value={new Set(data.course_assignments.filter(c => c.is_active && c.section_name).map(c => `${c.program_id}·${c.semester_number}·${c.section_name}`)).size} color="#0ea5e9" />
          </div>

          {hierarchy.length > 0 ? (
            <div>
              <SectionDivider label="My Teaching & Coordination" />
              <div className="space-y-6 mt-3">
                {hierarchy.map(dept => <DepartmentGroup key={dept.deptKey} dept={dept} />)}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
              <Users className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm font-medium text-foreground">No responsibilities assigned yet</p>
              <p className="text-xs text-muted-foreground mt-1">
                Contact your dean or administrator to get assigned to programs and courses.
              </p>
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
