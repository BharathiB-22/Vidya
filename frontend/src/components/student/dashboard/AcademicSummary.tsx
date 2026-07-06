import { useQuery } from '@tanstack/react-query'
import {
  CalendarCheck, FlaskConical, CalendarDays, Ticket,
  Award, BookMarked, Microscope, Bell, GraduationCap, ClipboardList,
} from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import {
  useStudentAssignments as useStudentCoursework,
  useMySubmissions as useMyCourseworkSubmissions,
} from '@/hooks/coursework'
import { studentListProblems } from '@/lib/api/research'
import { listNotifications } from '@/lib/api/notifications'
import { StatCard } from '@/components/dashboard/shared'

interface AcademicSummaryProps {
  semesterId?: string
  sessionId?: string
}

function TileShell({ isLoading, children }: { isLoading: boolean; children: React.ReactNode }) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white px-4 py-3.5 h-[62px] animate-pulse" aria-hidden="true">
        <div className="h-3 w-16 rounded bg-gray-100 mb-2" />
        <div className="h-4 w-12 rounded bg-gray-100" />
      </div>
    )
  }
  return <>{children}</>
}

export function AcademicSummary({ semesterId, sessionId }: AcademicSummaryProps) {
  const attendanceQ = useQuery({
    queryKey: ['my-attendance-summary'],
    queryFn: () => sisApi.getMyAttendance(),
  })

  const assignmentsQ = useStudentAssignments()
  const submissionsQ = useMySubmissions()
  const submittedAssignmentIds = new Set((submissionsQ.data?.items ?? []).map((s) => s.assignment_id))
  const pendingLabs = (assignmentsQ.data?.items ?? []).filter((a) => !submittedAssignmentIds.has(a.id)).length

  const courseworkQ = useStudentCoursework()
  const courseworkSubmissionsQ = useMyCourseworkSubmissions()
  const submittedCourseworkIds = new Set((courseworkSubmissionsQ.data?.items ?? []).map((s) => s.assignment_id))
  const pendingCoursework = (courseworkQ.data?.items ?? []).filter((a) => !submittedCourseworkIds.has(a.id)).length
  const submittedCourseworkCount = courseworkSubmissionsQ.data?.items?.length ?? 0

  const subjectsQ = useQuery({
    queryKey: ['my-subjects-summary'],
    queryFn: () => sisApi.getMySubjects(),
  })
  const creditsRegistered = (subjectsQ.data?.subjects ?? []).reduce((sum, s) => sum + (s.credits ?? 0), 0)

  const timetableQ = useQuery({
    queryKey: ['my-timetable', sessionId],
    queryFn: () => sisApi.getMyTimetable(sessionId!),
    enabled: !!sessionId,
  })
  const today = new Date().toISOString().slice(0, 10)
  const nextExam = (timetableQ.data?.courses ?? [])
    .filter((c) => c.exam_date && c.exam_date >= today)
    .sort((a, b) => (a.exam_date! < b.exam_date! ? -1 : 1))[0]

  const eligibilityQ = useQuery({
    queryKey: ['my-eligibility', semesterId],
    queryFn: () => sisApi.getMyEligibility(semesterId!),
    enabled: !!semesterId,
  })

  const transcriptQ = useQuery({
    queryKey: ['my-transcript'],
    queryFn: sisApi.getMyTranscript,
  })

  const marksQ = useQuery({
    queryKey: ['my-marks'],
    queryFn: sisApi.getMyMarks,
  })
  const marksTotals = (marksQ.data?.courses ?? []).reduce(
    (acc, c) => ({
      obtained: acc.obtained + Number(c.total_marks_obtained ?? 0),
      max: acc.max + Number(c.total_max_marks ?? 0),
    }),
    { obtained: 0, max: 0 },
  )
  const marksPct = marksTotals.max > 0 ? Math.round((marksTotals.obtained / marksTotals.max) * 100) : null

  const researchQ = useQuery({
    queryKey: ['student-problems'],
    queryFn: () => studentListProblems(),
  })
  const latestProblem = researchQ.data?.items?.[0]

  const notificationsQ = useQuery({
    queryKey: ['notifications', 'summary'],
    queryFn: () => listNotifications({ page_size: 1 }),
  })

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <TileShell isLoading={attendanceQ.isLoading}>
        <StatCard
          label="Attendance"
          value={attendanceQ.data?.overall_pct != null ? `${attendanceQ.data.overall_pct.toFixed(1)}%` : '—'}
          icon={CalendarCheck}
          accent={!!attendanceQ.data?.overall_pct && attendanceQ.data.overall_pct < 75}
        />
      </TileShell>

      <TileShell isLoading={assignmentsQ.isLoading || submissionsQ.isLoading}>
        <StatCard label="Pending Labs" value={String(pendingLabs)} icon={FlaskConical} accent={pendingLabs > 0} />
      </TileShell>

      <TileShell isLoading={courseworkQ.isLoading || courseworkSubmissionsQ.isLoading}>
        <StatCard label="Assignments Pending" value={String(pendingCoursework)} icon={ClipboardList} accent={pendingCoursework > 0} />
      </TileShell>

      <TileShell isLoading={courseworkSubmissionsQ.isLoading}>
        <StatCard label="Assignments Submitted" value={String(submittedCourseworkCount)} icon={ClipboardList} />
      </TileShell>

      <TileShell isLoading={subjectsQ.isLoading}>
        <StatCard label="Credits Registered" value={String(creditsRegistered)} icon={GraduationCap} />
      </TileShell>

      <TileShell isLoading={!!sessionId && timetableQ.isLoading}>
        <StatCard
          label="Upcoming Exam"
          value={nextExam ? `${nextExam.course_code} · ${nextExam.exam_date}` : 'None scheduled'}
          icon={CalendarDays}
        />
      </TileShell>

      <TileShell isLoading={!!semesterId && eligibilityQ.isLoading}>
        <StatCard
          label="Hall Ticket"
          value={eligibilityQ.data?.status ?? 'Not computed'}
          icon={Ticket}
          accent={eligibilityQ.data?.status === 'NOT_ELIGIBLE'}
        />
      </TileShell>

      <TileShell isLoading={transcriptQ.isLoading}>
        <StatCard label="CGPA" value={transcriptQ.data?.cgpa != null ? transcriptQ.data.cgpa.toFixed(2) : '—'} icon={Award} />
      </TileShell>

      <TileShell isLoading={marksQ.isLoading}>
        <StatCard label="Internal Marks" value={marksPct != null ? `${marksPct}%` : '—'} icon={BookMarked} />
      </TileShell>

      <TileShell isLoading={researchQ.isLoading}>
        <StatCard label="Research" value={latestProblem ? latestProblem.status.replace('_', ' ') : 'Not registered'} icon={Microscope} />
      </TileShell>

      <TileShell isLoading={notificationsQ.isLoading}>
        <StatCard
          label="Notifications"
          value={String(notificationsQ.data?.unread_count ?? 0)}
          icon={Bell}
          accent={(notificationsQ.data?.unread_count ?? 0) > 0}
        />
      </TileShell>
    </div>
  )
}
