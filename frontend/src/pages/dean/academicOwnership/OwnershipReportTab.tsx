import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Building2, Download } from 'lucide-react'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDeanPrograms, useOwnershipMatrix } from '@/hooks/useOwnership'
import type { MatrixDepartment, MatrixProgram, MatrixSection, MatrixCourse } from '@/lib/api/ownership'

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
  const vacant = course.faculty.length === 0
  return (
    <div className={`ml-4 py-2 border-b border-gray-50 last:border-0 ${vacant ? 'bg-amber-50/60 -mx-2 px-2 rounded' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
              {course.code}
            </span>
            <span className="text-sm font-medium text-foreground">{course.title}</span>
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
            <p className="text-xs text-amber-600 font-medium mt-1">Vacant — no faculty assigned</p>
          )}
        </div>
      </div>
    </div>
  )
}

function SectionPanel({ section, vacantOnly }: { section: MatrixSection; vacantOnly: boolean }) {
  const [open, setOpen] = useState(true)
  const courses = vacantOnly ? section.courses.filter(c => c.faculty.length === 0) : section.courses
  const vacantCount = section.courses.filter(c => c.faculty.length === 0).length
  if (vacantOnly && courses.length === 0) return null

  return (
    <div className="ml-4 mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-xs font-semibold text-gray-600 hover:text-gray-900 transition-colors w-full py-1"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span>{section.name}</span>
        <span className="text-gray-400 font-normal">{courses.length} course{courses.length !== 1 ? 's' : ''}</span>
        {vacantCount > 0 && (
          <span className="ml-auto text-amber-500 font-medium">{vacantCount} vacant</span>
        )}
      </button>
      {open && courses.length > 0 && (
        <div className="border-l-2 border-gray-100 ml-1.5 pl-2 mt-1">
          {courses.map(c => (
            <CourseRow key={c.course_id} course={c} />
          ))}
        </div>
      )}
      {open && courses.length === 0 && (
        <p className="ml-5 text-xs text-gray-400 py-2">No courses.</p>
      )}
    </div>
  )
}

function ProgramBlock({ prog, vacantOnly }: { prog: MatrixProgram; vacantOnly: boolean }) {
  const [open, setOpen] = useState(true)
  const totalCourses   = prog.semesters.reduce((n, s) => n + s.sections.reduce((m, sec) => m + sec.courses.length, 0), 0)
  const totalVacant = prog.semesters.reduce(
    (n, s) => n + s.sections.reduce((m, sec) => m + sec.courses.filter(c => c.faculty.length === 0).length, 0), 0
  )

  if (vacantOnly && totalVacant === 0) return null

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-3 w-full px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-foreground">{prog.name}</span>
            <span className="text-xs font-mono bg-sv-primary/10 text-sv-primary px-1.5 py-0.5 rounded">
              {prog.code}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-400 flex-shrink-0">
          <span>{prog.semesters.length} sem</span>
          <span>{totalCourses} courses</span>
          {totalVacant > 0 && (
            <span className="text-amber-500 font-medium">{totalVacant} vacant</span>
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
            <div key={sem.semester_id} className="mb-3 last:mb-0">
              <p className="text-xs font-semibold text-gray-500 mb-1">
                Semester {sem.number}{sem.label ? ` — ${sem.label}` : ''}
              </p>
              {sem.sections.map(sec => (
                <SectionPanel key={sec.section_id ?? 'general'} section={sec} vacantOnly={vacantOnly} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DepartmentBlock({ dept, vacantOnly }: { dept: MatrixDepartment; vacantOnly: boolean }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="space-y-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
        <Building2 className="h-4 w-4 text-gray-400" />
        <span className="text-base font-bold text-foreground">{dept.name}</span>
        {dept.code && <span className="text-xs text-gray-400 font-mono">{dept.code}</span>}
      </button>
      {open && (
        <div className="pl-6 space-y-3">
          {dept.programs.map(prog => (
            <ProgramBlock key={prog.program_id} prog={prog} vacantOnly={vacantOnly} />
          ))}
        </div>
      )}
    </div>
  )
}

function toCsv(departments: MatrixDepartment[]): string {
  const rows = [['Department', 'Program', 'Semester', 'Section', 'Course Code', 'Course Title', 'Faculty', 'Status']]
  for (const dept of departments) {
    for (const prog of dept.programs) {
      for (const sem of prog.semesters) {
        for (const sec of sem.sections) {
          for (const course of sec.courses) {
            const facultyNames = course.faculty.map(f => `${f.full_name} (${f.role_in_course})`).join('; ')
            rows.push([
              dept.name, prog.name,
              `Semester ${sem.number}${sem.label ? ` - ${sem.label}` : ''}`,
              sec.name, course.code, course.title,
              facultyNames || '—',
              course.faculty.length === 0 ? 'Vacant' : 'Assigned',
            ])
          }
        }
      }
    }
  }
  return rows.map(r => r.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n')
}

/** Ownership Report — read-only Department → Program → Semester → Section → Course → Faculty hierarchy. Replaces the old "Ownership Matrix" page. */
export default function OwnershipReportTab() {
  const [selectedProgram, setSelectedProgram] = useState<string>('all')
  const [vacantOnly, setVacantOnly] = useState(false)

  const { data: programs, isLoading: progsLoading } = useDeanPrograms()

  const programIds = selectedProgram === 'all'
    ? programs?.map(p => p.id)
    : programs?.filter(p => p.id === selectedProgram).map(p => p.id)

  const { data: matrix, isLoading: matrixLoading } = useOwnershipMatrix(programIds)

  const isLoading = progsLoading || matrixLoading

  const handleExport = () => {
    if (!matrix) return
    const csv = toCsv(matrix.departments)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ownership-report-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const visibleDepartments = useMemo(() => matrix?.departments ?? [], [matrix])

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
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

        <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-gray-600">
          <input
            type="checkbox"
            checked={vacantOnly}
            onChange={e => setVacantOnly(e.target.checked)}
            className="rounded border-gray-300 text-sv-primary focus:ring-sv-primary"
          />
          Vacant only
        </label>

        {programs && (
          <p className="text-xs text-gray-400">
            {programs.length} program{programs.length !== 1 ? 's' : ''} governed
          </p>
        )}

        <Button variant="outline" size="sm" className="ml-auto" onClick={handleExport} disabled={!matrix}>
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Export CSV
        </Button>
      </div>

      {isLoading && <PageLoading />}

      {!isLoading && matrix && (
        <div className="space-y-4">
          {visibleDepartments.length === 0 && (
            <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
              <p className="text-sm font-medium text-gray-500">No programs in scope</p>
              <p className="text-xs text-gray-400 mt-1">
                Contact your administrator to assign programs to your governance scope.
              </p>
            </div>
          )}
          {visibleDepartments.map(dept => (
            <DepartmentBlock key={dept.department_id ?? 'unassigned'} dept={dept} vacantOnly={vacantOnly} />
          ))}
        </div>
      )}
    </div>
  )
}
