/**
 * My Courses page — FACULTY.
 * Shows active course assignments with quick-links to Syllabus and Course Kit.
 */
import { BookOpen, FileText, Package, ChevronRight, LayoutGrid } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { assignmentsApi, Assignment, CourseRoleInCourse } from '@/lib/api/assignments'

const ROLE_LABELS: Record<CourseRoleInCourse, string> = {
  PRIMARY:    'Primary Faculty',
  CO_FACULTY: 'Co-Faculty',
  GUEST:      'Guest',
}

const ROLE_COLORS: Record<CourseRoleInCourse, string> = {
  PRIMARY:    'bg-blue-100 text-blue-800',
  CO_FACULTY: 'bg-teal-100 text-teal-800',
  GUEST:      'bg-gray-100 text-gray-600',
}

function QuickLink({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ElementType
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1.5 text-xs font-medium text-gray-600
                 bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5
                 hover:bg-sv-light hover:border-sv-primary/40 hover:text-sv-primary
                 transition-all duration-150"
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
      <ChevronRight className="h-3 w-3 ml-0.5 opacity-60" />
    </button>
  )
}

function CourseCard({ a }: { a: Assignment }) {
  const navigate = useNavigate()

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4
                    hover:border-sv-primary/30 hover:shadow-md transition-all duration-200">
      <div className="flex items-start gap-3">
        <div className="p-2.5 rounded-lg bg-blue-50 flex-shrink-0">
          <BookOpen className="h-4 w-4 text-blue-500" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-bold text-gray-900 leading-snug">
              {a.course?.title ?? 'Unnamed Course'}
            </p>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded flex-shrink-0
                              ${ROLE_COLORS[a.role_in_course]}`}>
              {ROLE_LABELS[a.role_in_course]}
            </span>
          </div>

          {a.course?.code && (
            <p className="text-xs text-gray-600 mt-0.5 font-mono">{a.course.code}</p>
          )}

          {a.semester && (
            <p className="text-xs text-gray-500 mt-1.5">
              <span className="font-medium">Semester {a.semester.number}</span>
              {a.semester.label ? ` — ${a.semester.label}` : ''}
              {a.section && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-semibold text-[10px]">
                  {a.section.name}
                </span>
              )}
            </p>
          )}

          <p className="text-[11px] text-gray-600 mt-1">
            Assigned {new Date(a.assigned_at).toLocaleDateString()}
          </p>

          {/* Primary action — opens the unified Faculty Subject Workspace */}
          <button
            type="button"
            onClick={() => navigate(`/faculty/subjects/${a.id}`)}
            className="w-full mt-3 flex items-center justify-center gap-1.5 text-xs font-semibold text-white
                       bg-sv-primary rounded-lg px-3 py-2 hover:opacity-90 transition-opacity"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Open Subject Workspace
          </button>

          {/* Quick actions */}
          <div className="flex gap-2 mt-2 flex-wrap">
            <QuickLink
              icon={FileText}
              label="Syllabus"
              onClick={() => navigate(`/syllabuses?course_id=${a.course_id}`)}
            />
            <QuickLink
              icon={Package}
              label="Course Kits"
              onClick={() => navigate(`/syllabuses?course_id=${a.course_id}`)}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function MyCoursesPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-assignments', 'page'],
    queryFn:  () => assignmentsApi.listMine(),
  })

  return (
    <PageShell>
      <PageHeader
        icon={BookOpen}
        title="My Courses"
        subtitle="Courses assigned to you — click Syllabus or Course Kits to open the content."
      />

      {isLoading ? (
        <PageLoading />
      ) : !data || data.total === 0 ? (
        <PageEmpty message="No courses assigned yet. Contact your Dean or Administrator." />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.items.map(a => (
            <CourseCard key={a.id} a={a} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
