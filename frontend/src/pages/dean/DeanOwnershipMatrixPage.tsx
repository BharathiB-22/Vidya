import { useState } from 'react'
import { ChevronDown, ChevronRight, LayoutGrid, BookOpen, Users, Building2 } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDeanPrograms, useOwnershipMatrix } from '@/hooks/useOwnership'
import type { MatrixProgram, MatrixSemester, MatrixCourse } from '@/lib/api/ownership'

const ROLE_COLORS: Record<string, string> = {
  PRIMARY:    '#6366f1',
  CO_FACULTY: '#10b981',
  GUEST:      '#f59e0b',
}

function RoleChip({ role }: { role: string }) {
  const color = ROLE_COLORS[role] ?? '#6b7280'
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
      style={{ background: `${color}15`, color, border: `1px solid ${color}30` }}
    >
      {role.replace('_', ' ')}
    </span>
  )
}

function CourseRow({ course }: { course: MatrixCourse }) {
  return (
    <div className="ml-4 py-2 border-b border-gray-50 last:border-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
              {course.code}
            </span>
            <span className="text-sm font-medium text-gray-800">{course.title}</span>
            {course.course_type && (
              <span className="text-[10px] text-gray-400 uppercase tracking-wide">
                {course.course_type}
              </span>
            )}
          </div>
          {course.faculty.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {course.faculty.map(f => (
                <div key={f.user_id} className="flex items-center gap-1 text-xs text-gray-600">
                  <span>{f.full_name}</span>
                  <RoleChip role={f.role_in_course} />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-amber-500 mt-1">No faculty assigned</p>
          )}
        </div>
      </div>
    </div>
  )
}

function SemesterPanel({ sem }: { sem: MatrixSemester }) {
  const [open, setOpen] = useState(true)
  const unassigned = sem.courses.filter(c => c.faculty.length === 0).length

  return (
    <div className="ml-4 mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-xs font-semibold text-gray-600 hover:text-gray-900 transition-colors w-full py-1"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span>Semester {sem.number}{sem.label ? ` — ${sem.label}` : ''}</span>
        <span className="text-gray-400 font-normal">{sem.courses.length} course{sem.courses.length !== 1 ? 's' : ''}</span>
        {unassigned > 0 && (
          <span className="ml-auto text-amber-500 font-medium">{unassigned} unassigned</span>
        )}
      </button>
      {open && sem.courses.length > 0 && (
        <div className="border-l-2 border-gray-100 ml-1.5 pl-2 mt-1">
          {sem.courses.map(c => (
            <CourseRow key={c.course_id} course={c} />
          ))}
        </div>
      )}
      {open && sem.courses.length === 0 && (
        <p className="ml-5 text-xs text-gray-400 py-2">No courses in this semester.</p>
      )}
    </div>
  )
}

function ProgramBlock({ prog }: { prog: MatrixProgram }) {
  const [open, setOpen] = useState(true)
  const totalCourses   = prog.semesters.reduce((n, s) => n + s.courses.length, 0)
  const totalUnassigned = prog.semesters.reduce(
    (n, s) => n + s.courses.filter(c => c.faculty.length === 0).length, 0
  )

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-3 w-full px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-gray-900">{prog.name}</span>
            <span className="text-xs font-mono bg-sv-primary/10 text-sv-primary px-1.5 py-0.5 rounded">
              {prog.code}
            </span>
            {prog.department && (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {prog.department.name}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-400 flex-shrink-0">
          <span>{prog.semesters.length} sem</span>
          <span>{totalCourses} courses</span>
          {totalUnassigned > 0 && (
            <span className="text-amber-500 font-medium">{totalUnassigned} unassigned</span>
          )}
        </div>
      </button>
      {open && (
        <div className="px-4 py-3">
          {prog.semesters.length === 0 && (
            <p className="text-xs text-gray-400 py-3 text-center">
              No active semesters. Create batches and semesters in the Academic Structure settings.
            </p>
          )}
          {prog.semesters.map(sem => (
            <SemesterPanel key={sem.semester_id} sem={sem} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function DeanOwnershipMatrixPage() {
  const [selectedProgram, setSelectedProgram] = useState<string>('all')

  const { data: programs, isLoading: progsLoading } = useDeanPrograms()

  const programIds = selectedProgram === 'all'
    ? programs?.map(p => p.id)
    : programs?.filter(p => p.id === selectedProgram).map(p => p.id)

  const { data: matrix, isLoading: matrixLoading } = useOwnershipMatrix(programIds)

  const isLoading = progsLoading || matrixLoading

  return (
    <PageShell>
      <PageHeader
        title="Academic Ownership Matrix"
        subtitle="Program → Semester → Course → Faculty assignment view."
        icon={LayoutGrid}
      />

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Select value={selectedProgram} onValueChange={setSelectedProgram}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="All Programs" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Programs</SelectItem>
            {programs?.map(p => (
              <SelectItem key={p.id} value={p.id}>
                {p.name} ({p.code})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {programs && (
          <p className="text-xs text-gray-400">
            {programs.length} program{programs.length !== 1 ? 's' : ''} governed
          </p>
        )}
      </div>

      {isLoading && <PageLoading />}

      {!isLoading && matrix && (
        <div className="space-y-4">
          {matrix.programs.length === 0 && (
            <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
              <LayoutGrid className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm font-medium text-gray-500">No programs in scope</p>
              <p className="text-xs text-gray-400 mt-1">
                Contact your administrator to assign programs to your governance scope.
              </p>
            </div>
          )}
          {matrix.programs.map(prog => (
            <ProgramBlock key={prog.program_id} prog={prog} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
