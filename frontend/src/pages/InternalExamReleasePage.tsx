// M08 Exam Setter — Internal Marks management
// /exams/internal-marks          → course picker (faculty only)
// /exams/internal-marks/course/:courseId → marks table
import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Lock, AlertTriangle, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import {
  listInternalMarksByCourse,
  submitInternalMarks,
  lockInternalMarks,
} from '@/lib/api/exam'
import { assignmentsApi } from '@/lib/api/assignments'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import type { InternalMarks } from '@/types/exam'

// ─── Status display ───────────────────────────────────────────────────────────

const IMS_STATUS_BADGE: Record<string, string> = {
  PENDING:           'bg-gray-100 text-gray-600',
  FACULTY_SUBMITTED: 'bg-yellow-100 text-yellow-700',
  DEAN_LOCKED:       'bg-green-100 text-green-700',
}

const IMS_STATUS_LABEL: Record<string, string> = {
  PENDING:           'Pending',
  FACULTY_SUBMITTED: 'Submitted',
  DEAN_LOCKED:       'Locked',
}

// Advisory: flag if std dev of totals > 30% of max (high variance)
function computeAdvisory(items: InternalMarks[]): string | null {
  const withTotals = items.filter(i => i.total_internal !== null)
  if (withTotals.length < 5) return null
  const totals = withTotals.map(i => i.total_internal!)
  const maxInternal = withTotals[0]?.max_internal ?? 40
  const mean = totals.reduce((a, b) => a + b, 0) / totals.length
  const variance = totals.reduce((a, b) => a + (b - mean) ** 2, 0) / totals.length
  const stdDev = Math.sqrt(variance)
  if (stdDev > 0.3 * maxInternal) {
    return `Distribution advisory: σ = ${stdDev.toFixed(1)}, mean = ${mean.toFixed(1)} / ${maxInternal}. High variance detected — please verify marks before submitting.`
  }
  return null
}

// ─── Entry point ─────────────────────────────────────────────────────────────

export default function InternalExamReleasePage() {
  const { courseId } = useParams<{ courseId?: string }>()
  if (!courseId) return <CoursePickerView />
  return <MarksTableView courseId={courseId} />
}

// ─── Course Picker ────────────────────────────────────────────────────────────

function CoursePickerView() {
  const user = useCurrentUser()
  const role = user?.role ?? ''
  const navigate = useNavigate()
  const isFacultyLike = ['FACULTY', 'ADMIN'].includes(role)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-assignments-ims'],
    queryFn: () => assignmentsApi.listMine(),
    enabled: isFacultyLike,
  })

  if (!isFacultyLike) {
    return (
      <PageShell>
        <PageHeader icon={BookOpen} title="Internal Marks" />
        <div className="text-center py-16 text-gray-500 space-y-3">
          <Lock className="mx-auto h-10 w-10 text-gray-300" />
          <p className="text-sm max-w-md mx-auto">
            Open the{' '}
            <Link to="/exams" className="text-indigo-600 underline">
              Exam Papers
            </Link>{' '}
            list and click <strong>Internal Marks →</strong> on any Internal-workflow paper to manage marks for that course.
          </p>
        </div>
      </PageShell>
    )
  }

  const courses = data?.items ?? []

  return (
    <PageShell>
      <PageHeader icon={BookOpen} title="Internal Marks" subtitle="Select a course to manage internal marks" />
      {isLoading && <PageLoading message="Loading your courses…" />}
      {isError && <PageError message="Failed to load course assignments." />}
      {!isLoading && !isError && courses.length === 0 && (
        <PageEmpty
          icon={BookOpen}
          message="No active course assignments found."
          action={
            <Link to="/exams">
              <Button variant="outline" size="sm">View Exam Papers</Button>
            </Link>
          }
        />
      )}
      {!isLoading && !isError && courses.length > 0 && (
        <div className="space-y-3">
          {courses.map(a => (
            <button
              key={a.id}
              onClick={() => navigate(`/exams/internal-marks/course/${a.course_id}`)}
              className="w-full text-left rounded-xl border border-gray-200 bg-white p-4 hover:border-amber-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900 truncate">
                    {a.course?.title ?? a.course_id}
                  </p>
                  <p className="text-sm text-gray-500 mt-0.5">
                    {a.course?.code && `${a.course.code} · `}
                    {a.semester ? `Semester ${a.semester.number}` : 'No semester info'}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-gray-400 shrink-0" />
              </div>
            </button>
          ))}
        </div>
      )}
    </PageShell>
  )
}

// ─── Marks Table ──────────────────────────────────────────────────────────────

function MarksTableView({ courseId }: { courseId: string }) {
  const user = useCurrentUser()
  const role = user?.role ?? ''
  const isFaculty = ['FACULTY', 'ADMIN'].includes(role)
  const isDean = ['DEAN', 'ADMIN'].includes(role)

  const [semester, setSemester] = useState('')
  const [academicYear, setAcademicYear] = useState('')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['internal-marks', courseId, semester, academicYear],
    queryFn: () =>
      listInternalMarksByCourse(courseId, {
        semester:      semester ? parseInt(semester, 10) : undefined,
        academic_year: academicYear || undefined,
        limit:         200,
      }),
  })

  const items = data?.items ?? []
  const advisory = computeAdvisory(items)

  const pendingCount    = items.filter(i => i.status === 'PENDING').length
  const submittedCount  = items.filter(i => i.status === 'FACULTY_SUBMITTED').length
  const lockedCount     = items.filter(i => i.status === 'DEAN_LOCKED').length

  async function handleSubmit(imsId: string) {
    setActionLoading(imsId)
    setActionError(null)
    try {
      await submitInternalMarks(imsId)
      await refetch()
    } catch (e: any) {
      setActionError(e?.response?.data?.detail?.message ?? 'Failed to submit marks.')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleLock(imsId: string) {
    setActionLoading(imsId)
    setActionError(null)
    try {
      await lockInternalMarks(imsId)
      await refetch()
    } catch (e: any) {
      setActionError(e?.response?.data?.detail?.message ?? 'Failed to lock marks.')
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <PageShell>
      <PageHeader
        icon={BookOpen}
        title="Internal Marks"
        subtitle={`Course ID: ${courseId.slice(0, 8)}…`}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="number"
          placeholder="Semester"
          value={semester}
          onChange={e => setSemester(e.target.value)}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm w-32 focus:outline-none focus:border-amber-400"
          min={1}
          max={12}
        />
        <input
          type="text"
          placeholder="Academic Year (e.g. 2025-26)"
          value={academicYear}
          onChange={e => setAcademicYear(e.target.value)}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm w-56 focus:outline-none focus:border-amber-400"
        />
      </div>

      {/* Summary chips */}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 font-medium">
            {pendingCount} Pending
          </span>
          <span className="px-2.5 py-1 rounded-full bg-yellow-100 text-yellow-700 font-medium">
            {submittedCount} Submitted
          </span>
          <span className="px-2.5 py-1 rounded-full bg-green-100 text-green-700 font-medium">
            {lockedCount} Locked
          </span>
        </div>
      )}

      {/* Advisory */}
      {advisory && (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <span>{advisory}</span>
        </div>
      )}

      {/* Action error */}
      {actionError && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {isLoading && <PageLoading message="Loading internal marks…" />}
      {isError && (
        <PageError message="Failed to load internal marks." onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && items.length === 0 && (
        <PageEmpty
          icon={BookOpen}
          message="No internal marks records found for this course."
          action={
            <Link to="/exams">
              <Button variant="outline" size="sm">Back to Exam Papers</Button>
            </Link>
          }
        />
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Student</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Int-1</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Int-2</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Assign</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Attend</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Total</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map(ims => (
                <MarksRow
                  key={ims.id}
                  ims={ims}
                  isFaculty={isFaculty}
                  isDean={isDean}
                  actionLoading={actionLoading}
                  onSubmit={handleSubmit}
                  onLock={handleLock}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  )
}

// ─── Table row ────────────────────────────────────────────────────────────────

function MarksRow({
  ims,
  isFaculty,
  isDean,
  actionLoading,
  onSubmit,
  onLock,
}: {
  ims:          InternalMarks
  isFaculty:    boolean
  isDean:       boolean
  actionLoading: string | null
  onSubmit:     (id: string) => Promise<void>
  onLock:       (id: string) => Promise<void>
}) {
  const isLocked  = ims.status === 'DEAN_LOCKED'
  const isActing  = actionLoading === ims.id
  const fmt = (v: number | null) => (v !== null ? v.toFixed(1) : '—')

  return (
    <tr className={isLocked ? 'bg-gray-50' : 'bg-white'}>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-gray-700">{ims.student_id.slice(0, 8)}…</span>
        <span className="ml-2 text-xs text-gray-400">Sem {ims.semester} / {ims.academic_year}</span>
      </td>
      <td className="px-3 py-3 text-center text-gray-700">{fmt(ims.internal1_marks)}</td>
      <td className="px-3 py-3 text-center text-gray-700">{fmt(ims.internal2_marks)}</td>
      <td className="px-3 py-3 text-center text-gray-700">{fmt(ims.assignment_marks)}</td>
      <td className="px-3 py-3 text-center text-gray-700">{fmt(ims.attendance_marks)}</td>
      <td className="px-3 py-3 text-center font-semibold text-gray-900">
        {ims.total_internal !== null
          ? `${ims.total_internal.toFixed(1)} / ${ims.max_internal}`
          : '—'}
      </td>
      <td className="px-3 py-3 text-center">
        <span
          className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${
            IMS_STATUS_BADGE[ims.status] ?? 'bg-gray-100 text-gray-600'
          }`}
        >
          {isLocked && <Lock className="h-3 w-3" />}
          {IMS_STATUS_LABEL[ims.status] ?? ims.status}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        {isLocked && (
          <Lock className="inline h-4 w-4 text-green-500" />
        )}
        {!isLocked && isFaculty && ims.status === 'PENDING' && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onSubmit(ims.id)}
            disabled={isActing}
            className="text-xs h-7 px-3"
          >
            {isActing ? '…' : 'Submit'}
          </Button>
        )}
        {!isLocked && isDean && ims.status === 'FACULTY_SUBMITTED' && (
          <Button
            size="sm"
            onClick={() => onLock(ims.id)}
            disabled={isActing}
            className="text-xs h-7 px-3 bg-green-600 hover:bg-green-700 text-white"
          >
            {isActing ? '…' : 'Lock'}
          </Button>
        )}
      </td>
    </tr>
  )
}
