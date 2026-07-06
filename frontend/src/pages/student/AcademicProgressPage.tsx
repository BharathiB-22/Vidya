import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp, GraduationCap, Award, CalendarCheck, BookMarked,
  FlaskConical, ClipboardList,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { StatCard } from '@/components/dashboard/shared'
import { sisApi } from '@/lib/api/sis'
import { useStudentAssignments as useLabAssignments, useMySubmissions as useMyLabSubmissions } from '@/hooks/labs'
import {
  useStudentAssignments as useCourseworkAssignments,
  useMySubmissions as useMyCourseworkSubmissions,
} from '@/hooks/coursework'

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

/**
 * One-screen aggregation of already-existing student APIs — no new backend.
 * Deliberately compact (same spirit as the trimmed StudentDashboard), not a
 * long scrolling report.
 */
export default function AcademicProgressPage() {
  const transcriptQ = useQuery({ queryKey: ['my-transcript'], queryFn: sisApi.getMyTranscript })
  const subjectsQ = useQuery({ queryKey: ['my-subjects-summary'], queryFn: () => sisApi.getMySubjects() })
  const attendanceQ = useQuery({ queryKey: ['my-attendance-summary'], queryFn: () => sisApi.getMyAttendance() })
  const marksQ = useQuery({ queryKey: ['my-marks'], queryFn: sisApi.getMyMarks })

  const labAssignmentsQ = useLabAssignments()
  const labSubmissionsQ = useMyLabSubmissions()
  const courseworkAssignmentsQ = useCourseworkAssignments()
  const courseworkSubmissionsQ = useMyCourseworkSubmissions()

  const creditsRegistered = (subjectsQ.data?.subjects ?? []).reduce((sum, s) => sum + (s.credits ?? 0), 0)
  const creditsEarned = transcriptQ.data?.total_credits ?? null
  const cgpa = transcriptQ.data?.cgpa ?? null
  const semesters = transcriptQ.data?.semesters ?? []

  const attendancePct = attendanceQ.data?.overall_pct ?? null
  const attendanceLow = attendancePct != null && attendancePct < 75

  const allComponents = (marksQ.data?.courses ?? []).flatMap((c) => c.components)
  const publishedComponents = allComponents.filter((c) => c.status === 'PUBLISHED' || c.status === 'LOCKED').length

  const labTotal = labAssignmentsQ.data?.total ?? labAssignmentsQ.data?.items?.length ?? 0
  const labSubmitted = labSubmissionsQ.data?.items?.length ?? 0
  const labGraded = (labSubmissionsQ.data?.items ?? []).filter((s) => s.status === 'RATIFIED').length

  const courseworkTotal = courseworkAssignmentsQ.data?.total ?? courseworkAssignmentsQ.data?.items?.length ?? 0
  const courseworkSubmitted = courseworkSubmissionsQ.data?.items?.length ?? 0
  const courseworkGraded = (courseworkSubmissionsQ.data?.items ?? [])
    .filter((s) => s.status === 'GRADED' || s.status === 'RETURNED').length

  return (
    <PageShell>
      <PageHeader
        icon={TrendingUp}
        title="Academic Progress"
        subtitle="Credits, CGPA, attendance, and completion across every module — all read-only"
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <TileShell isLoading={transcriptQ.isLoading}>
          <StatCard label="Current CGPA" value={cgpa != null ? cgpa.toFixed(2) : '—'} icon={Award} />
        </TileShell>

        <TileShell isLoading={transcriptQ.isLoading}>
          <StatCard
            label="Credits Earned"
            value={creditsEarned != null ? String(creditsEarned) : '—'}
            icon={GraduationCap}
          />
        </TileShell>

        <TileShell isLoading={subjectsQ.isLoading}>
          <StatCard label="Credits Registered" value={String(creditsRegistered)} icon={BookMarked} />
        </TileShell>

        <TileShell isLoading={attendanceQ.isLoading}>
          <StatCard
            label="Attendance"
            value={attendancePct != null ? `${attendancePct.toFixed(1)}%` : '—'}
            icon={CalendarCheck}
            accent={attendanceLow}
          />
        </TileShell>

        <TileShell isLoading={marksQ.isLoading}>
          <StatCard
            label="Internal Marks Status"
            value={`${publishedComponents} of ${allComponents.length} published`}
            icon={BookMarked}
          />
        </TileShell>

        <TileShell isLoading={labAssignmentsQ.isLoading || labSubmissionsQ.isLoading}>
          <StatCard
            label="Lab Completion"
            value={`${labSubmitted}/${labTotal} submitted · ${labGraded} graded`}
            icon={FlaskConical}
          />
        </TileShell>

        <TileShell isLoading={courseworkAssignmentsQ.isLoading || courseworkSubmissionsQ.isLoading}>
          <StatCard
            label="Assignment Completion"
            value={`${courseworkSubmitted}/${courseworkTotal} submitted · ${courseworkGraded} graded`}
            icon={ClipboardList}
          />
        </TileShell>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Semester Trend</h2>
        {transcriptQ.isLoading ? (
          <div className="space-y-2 animate-pulse">
            <div className="h-4 w-full rounded bg-gray-100" />
            <div className="h-4 w-3/4 rounded bg-gray-100" />
          </div>
        ) : semesters.length === 0 ? (
          <p className="text-sm text-gray-400">No published semester results yet.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {semesters.map((s) => (
              <div key={s.declaration_id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-gray-700">{s.snapshot_semester_name}</span>
                <span className="text-gray-500">
                  SGPA {s.sgpa != null ? s.sgpa.toFixed(2) : '—'} · CGPA {s.cgpa != null ? s.cgpa.toFixed(2) : '—'}
                  {' · '}{s.total_credits_earned ?? 0}/{s.total_credits_attempted ?? 0} credits
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}
