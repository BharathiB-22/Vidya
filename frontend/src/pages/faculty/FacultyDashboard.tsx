import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import {
  FileText, FlaskConical, ClipboardList, BookMarked, Microscope,
} from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { listSyllabuses } from '@/lib/api/syllabuses'
import { assignmentsApi } from '@/lib/api/assignments'
import { useLabAssignments } from '@/hooks/labs'
import { useAssignments as useCourseworkAssignments } from '@/hooks/coursework'
import { listProblems } from '@/lib/api/research'
import { StatCard } from '@/components/dashboard/shared'
import { MyCoursesBanner } from '@/components/assignments/MyCoursesBanner'
import { NotificationsWidget } from '@/components/student/dashboard/NotificationsWidget'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { getGreeting, getDisplayFirstName } from '@/components/dashboard/shared'

/**
 * Faculty's homepage — one screen, composed entirely from existing
 * faculty-facing APIs (course allocation, syllabus, labs, coursework,
 * internal marks, research supervision, notifications). No new backend.
 */
export function FacultyDashboard() {
  const user = useCurrentUser()
  const isGuide = user?.responsibilities?.includes('GUIDE') ?? false

  const facultyQ = useQuery({
    queryKey: ['my-faculty-profile'],
    queryFn: sisApi.getMyFacultyProfile,
  })

  const myCoursesQ = useQuery({
    queryKey: ['my-assignments', 'dashboard'],
    queryFn: () => assignmentsApi.listMine(),
  })
  const myCourseIds = [...new Set((myCoursesQ.data?.items ?? []).map((a) => a.course_id))]

  const syllabusQueries = useQueries({
    queries: myCourseIds.map((courseId) => ({
      queryKey: ['syllabuses', 'dashboard', courseId],
      queryFn: () => listSyllabuses({ course_id: courseId }),
      enabled: myCourseIds.length > 0,
    })),
  })
  const syllabusLoading = myCoursesQ.isLoading || syllabusQueries.some((q) => q.isLoading)
  const pendingReviewCount = syllabusQueries
    .flatMap((q) => q.data?.items ?? [])
    .filter((s) => s.status === 'PENDING_REVIEW' || s.status === 'REJECTED').length

  const labsQ = useLabAssignments()
  const publishedLabs = (labsQ.data?.items ?? []).filter((a) => a.status === 'PUBLISHED').length

  const courseworkQ = useCourseworkAssignments()
  const publishedCoursework = (courseworkQ.data?.items ?? []).filter((a) => a.status === 'PUBLISHED').length

  const marksQ = useQuery({
    queryKey: ['marks-components-my'],
    queryFn: () => sisApi.listMarksComponents({}),
  })
  const draftMarksCount = (marksQ.data ?? []).filter((c) => c.status === 'DRAFT').length

  const researchQ = useQuery({
    queryKey: ['guide-problems', 'dashboard'],
    queryFn: () => listProblems({ status: 'PENDING_REVIEW' }),
    enabled: isGuide,
  })
  const pendingResearchCount = isGuide ? (researchQ.data?.items ?? []).length : 0

  const firstName = facultyQ.data?.full_name ? getDisplayFirstName(facultyQ.data.full_name) : null

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="text-lg font-bold text-gray-900 leading-tight">
          {getGreeting()}{firstName ? `, ${firstName}` : ''}
        </h2>
        {facultyQ.data && (
          <p className="text-sm text-gray-500 mt-0.5">
            {facultyQ.data.designation ?? 'Faculty'}
            {facultyQ.data.primary_department ? ` · ${facultyQ.data.primary_department.name}` : ''}
          </p>
        )}
      </section>

      <MyCoursesBanner />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <Link to="/syllabuses" className="block">
          <StatCard
            label="Syllabus Review"
            value={syllabusLoading ? '…' : String(pendingReviewCount)}
            icon={FileText}
            accent={pendingReviewCount > 0}
          />
        </Link>
        <Link to="/labs" className="block">
          <StatCard
            label="Active Labs"
            value={labsQ.isLoading ? '…' : String(publishedLabs)}
            icon={FlaskConical}
          />
        </Link>
        <Link to="/faculty/assignments" className="block">
          <StatCard
            label="Active Assignments"
            value={courseworkQ.isLoading ? '…' : String(publishedCoursework)}
            icon={ClipboardList}
          />
        </Link>
        <Link to="/sis/marks/setup" className="block">
          <StatCard
            label="Marks — Unpublished"
            value={marksQ.isLoading ? '…' : String(draftMarksCount)}
            icon={BookMarked}
            accent={draftMarksCount > 0}
          />
        </Link>
        {isGuide && (
          <Link to="/research/problems" className="block">
            <StatCard
              label="Research — Pending"
              value={researchQ.isLoading ? '…' : String(pendingResearchCount)}
              icon={Microscope}
              accent={pendingResearchCount > 0}
            />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <NotificationsWidget />
      </div>
    </div>
  )
}

export default FacultyDashboard
