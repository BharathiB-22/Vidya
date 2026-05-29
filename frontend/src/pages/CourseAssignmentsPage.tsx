/**
 * Course Assignments — DEAN only.
 * Groups courses by Program, shows assigned faculty per course.
 * Dean can assign/revoke without drilling through menus.
 */
import { useState, useEffect } from 'react'
import { UserCheck, Plus, X, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { listPrograms, listCourses } from '@/lib/api/programs'
import { academicsApi } from '@/lib/api/academics'
import { assignmentsApi, Assignment, CourseRoleInCourse } from '@/lib/api/assignments'
import api from '@/lib/api'

// ── Types ────────────────────────────────────────────────────────────────────

interface FacultyUser { id: string; full_name: string; email: string }

const ROLE_LABELS: Record<CourseRoleInCourse, string> = {
  PRIMARY:    'Primary',
  CO_FACULTY: 'Co-Faculty',
  GUEST:      'Guest',
}
const ROLE_COLORS: Record<CourseRoleInCourse, string> = {
  PRIMARY:    'bg-blue-100 text-blue-700',
  CO_FACULTY: 'bg-teal-100 text-teal-700',
  GUEST:      'bg-gray-100 text-gray-500',
}

function RoleBadge({ role }: { role: CourseRoleInCourse }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-semibold ${ROLE_COLORS[role]}`}>
      {ROLE_LABELS[role]}
    </span>
  )
}

// ── Assign dialog ─────────────────────────────────────────────────────────────

function AssignDialog({
  open, onClose, courseId, semesterId, courseName, onAssigned,
}: {
  open: boolean
  onClose: () => void
  courseId: string
  semesterId: string
  courseName: string
  onAssigned: () => void
}) {
  const [facultyId, setFacultyId] = useState('')
  const [role,      setRole]      = useState<CourseRoleInCourse>('PRIMARY')
  const [saving,    setSaving]    = useState(false)

  const { data: facultyList = [] } = useQuery<FacultyUser[]>({
    queryKey: ['faculty-list'],
    queryFn:  () => api.get<FacultyUser[]>('/course-assignments/faculty-list').then(r => r.data),
    enabled:  open,
  })

  useEffect(() => { if (!open) { setFacultyId(''); setRole('PRIMARY') } }, [open])

  async function handleSave() {
    if (!facultyId) { addToast('Select a faculty member.', 'error'); return }
    setSaving(true)
    try {
      await assignmentsApi.create({ course_id: courseId, faculty_user_id: facultyId, semester_id: semesterId, role_in_course: role })
      addToast(`Assigned to ${courseName}.`, 'success')
      onAssigned()
      onClose()
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Assign Faculty</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-gray-500 -mt-2">{courseName}</p>
        <div className="space-y-4 py-2">
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1 block">Faculty</label>
            <Select value={facultyId} onValueChange={setFacultyId}>
              <SelectTrigger>
                <SelectValue placeholder={facultyList.length === 0 ? 'No faculty found' : 'Select faculty…'} />
              </SelectTrigger>
              <SelectContent>
                {facultyList.map(u => (
                  <SelectItem key={u.id} value={u.id}>{u.full_name} — {u.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1 block">Role</label>
            <Select value={role} onValueChange={v => setRole(v as CourseRoleInCourse)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="PRIMARY">Primary Faculty</SelectItem>
                <SelectItem value="CO_FACULTY">Co-Faculty</SelectItem>
                <SelectItem value="GUEST">Guest</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? 'Assigning…' : 'Assign'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Program section ───────────────────────────────────────────────────────────

function ProgramSection({
  program,
  assignmentMap,
  onAssign,
  onRevoke,
}: {
  program: { id: string; title: string; code?: string }
  assignmentMap: Map<string, Assignment[]>
  onAssign: (courseId: string, courseName: string) => void
  onRevoke: (assignmentId: string) => void
}) {
  const [expanded, setExpanded] = useState(true)

  const { data: courses = [], isLoading } = useQuery({
    queryKey: ['courses', program.id],
    queryFn:  () => listCourses(program.id),
    enabled:  expanded,
  })

  const unassignedCount = courses.filter(c => {
    const asgns = assignmentMap.get(c.id) ?? []
    return !asgns.some(a => a.is_active && a.role_in_course === 'PRIMARY')
  }).length

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Program header */}
      <button
        type="button"
        className="w-full flex items-center gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200
                   hover:bg-gray-100 transition-colors text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded
          ? <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />
          : <ChevronRight className="h-4 w-4 text-gray-400 shrink-0" />
        }
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-gray-900">{program.title}</p>
          {program.code && (
            <p className="text-[11px] font-mono text-gray-400">{program.code}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {expanded && courses.length > 0 && (
            <span className="text-[11px] text-gray-500">{courses.length} courses</span>
          )}
          {unassignedCount > 0 && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full">
              <AlertCircle className="h-3 w-3" />
              {unassignedCount} unassigned
            </span>
          )}
        </div>
      </button>

      {/* Course rows */}
      {expanded && (
        isLoading ? (
          <div className="px-4 py-3 text-sm text-gray-400">Loading courses…</div>
        ) : courses.length === 0 ? (
          <div className="px-4 py-3 text-sm text-gray-400">No courses in this program.</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {courses.map(course => {
              const asgns    = assignmentMap.get(course.id) ?? []
              const primary  = asgns.find(a => a.is_active && a.role_in_course === 'PRIMARY')
              const coFaculty = asgns.filter(a => a.is_active && a.role_in_course !== 'PRIMARY')
              const isUnassigned = !primary

              return (
                <div key={course.id}
                     className={`flex items-center gap-3 px-4 py-3 group ${isUnassigned ? 'bg-orange-50/30' : ''}`}>
                  {/* Course info */}
                  <div className="w-20 shrink-0">
                    <span className="text-[11px] font-mono text-gray-400">{course.code}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 font-medium truncate">{course.title}</p>
                    <p className="text-[11px] text-gray-400 mt-0.5">Semester {course.semester}</p>
                  </div>

                  {/* Faculty assignment */}
                  <div className="flex items-center gap-2 flex-wrap justify-end min-w-[200px]">
                    {isUnassigned ? (
                      <span className="text-xs text-orange-600 font-medium italic">Unassigned</span>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <RoleBadge role="PRIMARY" />
                        <span className="text-xs font-medium text-gray-800">
                          {primary!.faculty?.full_name ?? '—'}
                        </span>
                        <button
                          type="button"
                          title="Revoke"
                          onClick={() => onRevoke(primary!.id)}
                          className="text-gray-300 hover:text-red-500 transition-colors"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}

                    {coFaculty.map(a => (
                      <div key={a.id} className="flex items-center gap-1">
                        <RoleBadge role={a.role_in_course} />
                        <span className="text-[11px] text-gray-600">{a.faculty?.full_name ?? '—'}</span>
                        <button
                          type="button"
                          title="Revoke"
                          onClick={() => onRevoke(a.id)}
                          className="text-gray-300 hover:text-red-500 transition-colors"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))}

                    <button
                      type="button"
                      onClick={() => onAssign(course.id, `${course.code} — ${course.title}`)}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-sv-primary
                                 border border-dashed border-gray-300 hover:border-sv-primary/60
                                 px-2 py-0.5 rounded transition-colors"
                    >
                      <Plus className="h-3 w-3" />
                      Assign
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CourseAssignmentsPage() {
  const qc = useQueryClient()
  const [semId,     setSemId]     = useState('')
  const [assignTarget, setAssignTarget] = useState<{ courseId: string; courseName: string } | null>(null)

  const { data: programsData, isLoading: loadingPrograms } = useQuery({
    queryKey: ['programs', 'list'],
    queryFn:  () => listPrograms(),
  })
  const programs = programsData?.items ?? []

  const { data: semesters = [] } = useQuery({
    queryKey: ['semesters', 'all'],
    queryFn:  () => academicsApi.listSemesters(),
  })
  const activeSemesters = semesters.filter((s: any) => s.is_active)

  const { data: allAssignments, refetch: refetchAssignments } = useQuery({
    queryKey: ['assignments', 'all', semId],
    queryFn:  () => assignmentsApi.listAll(semId || undefined, false),
  })

  const assignmentMap = new Map<string, Assignment[]>()
  for (const a of allAssignments?.items ?? []) {
    const list = assignmentMap.get(a.course_id) ?? []
    list.push(a)
    assignmentMap.set(a.course_id, list)
  }

  const revokeMutation = useMutation({
    mutationFn: (id: string) => assignmentsApi.revoke(id),
    onSuccess: () => {
      addToast('Assignment revoked.', 'success')
      refetchAssignments()
      qc.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (err) => addToast(getErrorMessage(err), 'error'),
  })

  return (
    <PageShell>
      <PageHeader
        icon={UserCheck}
        title="Course Assignments"
        subtitle="Faculty assignments grouped by program. Unassigned courses are highlighted."
      />

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-56">
          <Select
            value={semId || '_all_'}
            onValueChange={v => setSemId(v === '_all_' ? '' : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="All semesters" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all_">All semesters</SelectItem>
              {activeSemesters.map((s: any) => (
                <SelectItem key={s.id} value={s.id}>
                  Sem {s.number}{s.label ? ` — ${s.label}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="text-sm text-gray-500">
          {allAssignments?.total ?? 0} active assignment{allAssignments?.total !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Program groups */}
      {loadingPrograms ? (
        <PageLoading />
      ) : programs.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-400 rounded-xl border border-dashed border-gray-200">
          No programs found. Create programs in Program Advisor first.
        </div>
      ) : (
        <div className="space-y-3">
          {programs.map(p => (
            <ProgramSection
              key={p.id}
              program={p}
              assignmentMap={assignmentMap}
              onAssign={(courseId, courseName) => setAssignTarget({ courseId, courseName })}
              onRevoke={id => revokeMutation.mutate(id)}
            />
          ))}
        </div>
      )}

      {/* Assign dialog */}
      {assignTarget && (
        <AssignDialog
          open
          onClose={() => setAssignTarget(null)}
          courseId={assignTarget.courseId}
          semesterId={semId}
          courseName={assignTarget.courseName}
          onAssigned={() => {
            refetchAssignments()
            qc.invalidateQueries({ queryKey: ['assignments'] })
          }}
        />
      )}
    </PageShell>
  )
}
