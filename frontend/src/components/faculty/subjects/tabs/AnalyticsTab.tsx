import { useQuery, useQueries } from '@tanstack/react-query'
import { ClipboardList, FlaskConical, CalendarCheck, ClipboardCheck, AlertTriangle, Hourglass } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { useAssignments } from '@/hooks/coursework'
import { getAssignmentStatistics } from '@/lib/api/coursework'
import { useLabAssignments } from '@/hooks/labs'
import { listSubmissions } from '@/lib/api/labs'
import type { FacultySubjectTabProps } from './types'

function Stat({ icon: Icon, label, value, tone = 'default' }: {
  icon: typeof ClipboardList; label: string; value: string; tone?: 'default' | 'warning'
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <Icon className={`h-4 w-4 mb-2 ${tone === 'warning' ? 'text-amber-500' : 'text-gray-600'}`} />
      <p className="text-xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}

function pct(numerator: number, denominator: number): string {
  if (denominator <= 0) return '—'
  return `${Math.round((numerator / denominator) * 100)}%`
}

export function AnalyticsTab({ ctx }: FacultySubjectTabProps) {
  const { assignment, syllabusId } = ctx
  const sectionId = assignment.section_id
  const { course_id, section_id } = assignment

  const attendanceQ = useQuery({
    queryKey: ['section-attendance', sectionId],
    queryFn: () => sisApi.getSectionAttendance(sectionId!),
    enabled: !!sectionId,
  })
  const totalStudents = attendanceQ.data?.students.length ?? 0
  const atRiskCount = attendanceQ.data?.students.filter((s) => s.is_at_risk).length ?? 0

  const assignmentsQ = useAssignments({ syllabus_id: syllabusId ?? undefined })
  const publishedAssignments = (assignmentsQ.data?.items ?? []).filter((a) => a.status === 'PUBLISHED')
  const assignmentStatsQ = useQueries({
    queries: publishedAssignments.map((a) => ({
      queryKey: ['assignment-stats', a.id],
      queryFn: () => getAssignmentStatistics(a.id),
    })),
  })
  const assignmentStatsLoaded = assignmentStatsQ.length > 0 && assignmentStatsQ.every((q) => q.data)
  const assignmentSubmitted = assignmentStatsQ.reduce((s, q) => s + (q.data?.submitted_count ?? 0), 0)
  const assignmentGraded = assignmentStatsQ.reduce((s, q) => s + (q.data?.graded_count ?? 0), 0)
  const assignmentPossible = assignmentStatsQ.reduce((s, q) => s + (q.data?.total_students ?? 0), 0)
  const assignmentPendingGrading = Math.max(assignmentSubmitted - assignmentGraded, 0)

  const labsQ = useLabAssignments({ syllabus_id: syllabusId ?? undefined })
  const publishedLabs = (labsQ.data?.items ?? []).filter((l) => l.status === 'PUBLISHED')
  const labSubmissionsQ = useQueries({
    queries: publishedLabs.map((l) => ({
      queryKey: ['lab-submissions-full', l.id],
      queryFn: () => listSubmissions(l.id),
    })),
  })
  const labSubmittedTotal = labSubmissionsQ.reduce((s, q) => s + (q.data?.total ?? 0), 0)
  const labPendingGrading = labSubmissionsQ.reduce(
    (s, q) => s + (q.data?.items.filter((sub) => sub.status === 'SUBMITTED' || sub.status === 'EVALUATING').length ?? 0),
    0
  )

  const marksQ = useQuery({
    queryKey: ['marks-components', course_id, section_id],
    queryFn: () => sisApi.listMarksComponents({ course_id, section_id: section_id ?? undefined }),
  })
  const marksPublished = (marksQ.data ?? []).filter((c) => c.status === 'PUBLISHED').length
  const marksTotal = (marksQ.data ?? []).length

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Subject Analytics</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat
          icon={ClipboardList}
          label="Assignment Completion"
          value={assignmentStatsLoaded ? pct(assignmentSubmitted, assignmentPossible) : '—'}
        />
        <Stat
          icon={FlaskConical}
          label="Lab Completion"
          value={publishedLabs.length > 0 ? pct(labSubmittedTotal, totalStudents * publishedLabs.length) : '—'}
        />
        <Stat
          icon={CalendarCheck}
          label="Average Attendance"
          value={attendanceQ.data?.avg_attendance_pct != null ? `${attendanceQ.data.avg_attendance_pct.toFixed(0)}%` : '—'}
        />
        <Stat
          icon={Hourglass}
          label="Pending Grading (Assignments + Labs)"
          value={String(assignmentPendingGrading + labPendingGrading)}
          tone={assignmentPendingGrading + labPendingGrading > 0 ? 'warning' : 'default'}
        />
        <Stat
          icon={AlertTriangle}
          label="Students Below Attendance Threshold"
          value={String(atRiskCount)}
          tone={atRiskCount > 0 ? 'warning' : 'default'}
        />
        <Stat
          icon={ClipboardCheck}
          label="Internal Marks Published"
          value={`${marksPublished}/${marksTotal}`}
        />
      </div>
    </div>
  )
}
