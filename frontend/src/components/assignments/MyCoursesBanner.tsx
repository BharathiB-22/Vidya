/**
 * H-31: My Courses banner shown on the Dashboard for FACULTY users.
 *
 * Fetches active assignments from /course-assignments/mine and displays
 * a compact list of assigned courses. Non-invasive — renders nothing if
 * no assignments exist yet.
 */
import { BookOpen, ChevronRight } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { assignmentsApi, Assignment, CourseRoleInCourse } from '@/lib/api/assignments'

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

function CourseRow({ a }: { a: Assignment }) {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      onClick={() => navigate(`/faculty/subjects/${a.id}`)}
      className="w-full flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0 text-left hover:bg-gray-50 transition-colors"
    >
      <div className="p-2 rounded-lg bg-blue-50">
        <BookOpen className="h-3.5 w-3.5 text-blue-500" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900 truncate">
          {a.course?.title ?? a.course_id}
          {a.course?.code && (
            <span className="text-xs text-gray-500 font-normal ml-1.5">({a.course.code})</span>
          )}
        </p>
        {a.semester && (
          <p className="text-xs text-gray-600">
            Semester {a.semester.number}
            {a.semester.label ? ` — ${a.semester.label}` : ''}
            {a.section && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 font-semibold text-[10px]">
                {a.section.name}
              </span>
            )}
          </p>
        )}
      </div>
      <span className={`text-[10px] font-bold px-2 py-0.5 rounded shrink-0 ${ROLE_COLORS[a.role_in_course]}`}>
        {ROLE_LABELS[a.role_in_course]}
      </span>
      <ChevronRight className="h-4 w-4 text-gray-500 shrink-0" />
    </button>
  )
}

export function MyCoursesBanner() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-assignments'],
    queryFn:  () => assignmentsApi.listMine(),
    retry: false,
  })

  // Don't render if loading failed or no assignments
  if (isLoading || isError || !data || data.total === 0) return null

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-blue-50/50">
        <div>
          <p className="text-sm font-bold text-gray-900">My Courses</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {data.total} course{data.total !== 1 ? 's' : ''} assigned this semester
          </p>
        </div>
        <Link
          to="/my-courses"
          className="flex items-center gap-1 text-xs font-semibold text-sv-primary hover:underline"
        >
          View all <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* Course list — show up to 5 */}
      <div>
        {data.items.slice(0, 5).map(a => (
          <CourseRow key={a.id} a={a} />
        ))}
        {data.total > 5 && (
          <div className="px-4 py-2.5 text-xs text-gray-600 text-center">
            +{data.total - 5} more — <Link to="/my-courses" className="text-sv-primary font-semibold hover:underline">view all</Link>
          </div>
        )}
      </div>
    </div>
  )
}
