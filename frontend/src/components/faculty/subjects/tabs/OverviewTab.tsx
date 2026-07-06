import { useQuery } from '@tanstack/react-query'
import { ClipboardList, FlaskConical, Users, CalendarCheck, BookMarked } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { useAssignments } from '@/hooks/coursework'
import { useLabAssignments } from '@/hooks/labs'
import type { FacultySubjectTabProps } from './types'

const ROLE_LABELS: Record<string, string> = {
  PRIMARY: 'Primary Faculty',
  CO_FACULTY: 'Co-Faculty',
  GUEST: 'Guest',
}

function StatTile({ icon: Icon, label, value, onClick }: {
  icon: typeof Users; label: string; value: string; onClick?: () => void
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`rounded-xl border border-gray-200 bg-white p-4 text-left w-full ${onClick ? 'hover:border-sv-primary/30 hover:shadow-sm transition-all' : ''}`}
    >
      <Icon className="h-4 w-4 text-gray-400 mb-2" />
      <p className="text-xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </Tag>
  )
}

export function OverviewTab({ ctx, onNavigateTab }: FacultySubjectTabProps) {
  const { assignment, syllabusId, departmentName, facultyName, sectionsHandled } = ctx
  const sectionId = assignment.section_id

  const attendanceQ = useQuery({
    queryKey: ['section-attendance', sectionId],
    queryFn: () => sisApi.getSectionAttendance(sectionId!),
    enabled: !!sectionId,
  })

  const assignmentsQ = useAssignments({ syllabus_id: syllabusId ?? undefined })
  const labsQ = useLabAssignments({ syllabus_id: syllabusId ?? undefined })

  const studentCount = attendanceQ.data?.students.length
  const avgAttendance = attendanceQ.data?.avg_attendance_pct

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Subject</p>
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <dt className="text-xs text-gray-400">Code</dt>
            <dd className="font-medium text-gray-800">{assignment.course?.code ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Title</dt>
            <dd className="font-medium text-gray-800">{assignment.course?.title ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Credits</dt>
            <dd className="font-medium text-gray-800">Not configured</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Semester</dt>
            <dd className="font-medium text-gray-800">
              {assignment.semester ? `${assignment.semester.number}${assignment.semester.label ? ` — ${assignment.semester.label}` : ''}` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Section{sectionsHandled.length > 1 ? 's' : ''}</dt>
            <dd className="font-medium text-gray-800">{sectionsHandled.join(', ') || assignment.section?.name || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Department</dt>
            <dd className="font-medium text-gray-800">{departmentName ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Faculty</dt>
            <dd className="font-medium text-gray-800">
              {facultyName ?? '—'}
              <span className="text-xs text-gray-400 font-normal ml-1.5">
                ({ROLE_LABELS[assignment.role_in_course] ?? assignment.role_in_course})
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Assigned</dt>
            <dd className="font-medium text-gray-800">{new Date(assignment.assigned_at).toLocaleDateString()}</dd>
          </div>
        </dl>
      </div>

      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Quick Statistics</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile
            icon={Users}
            label="Students"
            value={studentCount != null ? String(studentCount) : '—'}
            onClick={() => onNavigateTab('students')}
          />
          <StatTile
            icon={CalendarCheck}
            label="Avg. Attendance"
            value={avgAttendance != null ? `${avgAttendance.toFixed(0)}%` : '—'}
            onClick={() => onNavigateTab('attendance')}
          />
          <StatTile
            icon={ClipboardList}
            label="Assignments"
            value={assignmentsQ.data ? String(assignmentsQ.data.total) : '—'}
            onClick={() => onNavigateTab('assignments')}
          />
          <StatTile
            icon={FlaskConical}
            label="Labs"
            value={labsQ.data ? String(labsQ.data.total) : '—'}
            onClick={() => onNavigateTab('labs')}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-gray-400">
        <BookMarked className="h-3.5 w-3.5" />
        Use the tabs above to manage this subject's assignments, labs, attendance, marks, and content.
      </div>
    </div>
  )
}
