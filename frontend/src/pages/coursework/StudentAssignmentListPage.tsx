import { useNavigate, useSearchParams } from 'react-router-dom'
import { ClipboardList, ChevronRight, Clock, AlertTriangle } from 'lucide-react'
import { useStudentAssignments, useMySubmissions } from '@/hooks/coursework'
import type { CourseworkAssignment, CourseworkSubmission } from '@/types/coursework'

const TYPE_LABELS: Record<string, string> = {
  ESSAY: 'Essay',
  CASE_STUDY: 'Case Study',
  REPORT: 'Report',
  HOMEWORK: 'Homework',
  OTHER: 'Assignment',
}

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

function latestSubmission(
  subs: CourseworkSubmission[],
  assignmentId: string
): CourseworkSubmission | undefined {
  const matches = subs.filter((s) => s.assignment_id === assignmentId)
  if (matches.length === 0) return undefined
  return matches.reduce((a, b) => (b.attempt_number > a.attempt_number ? b : a))
}

function isOverdue(a: CourseworkAssignment): boolean {
  return new Date(a.due_date).getTime() < Date.now()
}

function StatusPill({
  assignment,
  submission,
}: {
  assignment: CourseworkAssignment
  submission: CourseworkSubmission | undefined
}) {
  if (!submission) {
    if (isOverdue(assignment)) {
      return (
        <span className="text-xs px-2 py-0.5 rounded-full font-medium text-red-700 bg-red-50">
          Overdue
        </span>
      )
    }
    return (
      <span className="text-xs px-2 py-0.5 rounded-full font-medium text-gray-500 bg-gray-100">
        Pending
      </span>
    )
  }

  // Until the faculty releases results the API sends no marks, so a GRADED
  // submission reads as "Under Evaluation" here — a mark exists internally but
  // is not the student's to see yet. Once released, marks_obtained arrives and
  // the score shows. RETURNED work carries its feedback as it always did.
  const hasScore = submission.marks_obtained != null
  const CFG: Record<string, { label: string; cls: string }> = {
    SUBMITTED: { label: submission.is_late ? 'Submitted (Late)' : 'Submitted', cls: 'text-blue-700 bg-blue-50' },
    GRADED:    hasScore
      ? { label: 'Graded',           cls: 'text-green-700 bg-green-50' }
      : { label: 'Under Evaluation', cls: 'text-amber-700 bg-amber-50' },
    RETURNED:  { label: 'Returned', cls: 'text-indigo-700 bg-indigo-50' },
  }
  const cfg = CFG[submission.status] ?? { label: submission.status, cls: 'text-gray-500 bg-gray-50' }

  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>
      {cfg.label}
      {hasScore && (
        <span className="ml-1 font-bold">
          · {submission.marks_obtained}/{assignment.max_marks}
        </span>
      )}
    </span>
  )
}

function AssignmentRow({
  assignment,
  submission,
  onClick,
}: {
  assignment: CourseworkAssignment
  submission: CourseworkSubmission | undefined
  onClick: () => void
}) {
  const isDeadlineSoon =
    !submission &&
    new Date(assignment.due_date).getTime() - Date.now() < 48 * 60 * 60 * 1000 &&
    new Date(assignment.due_date).getTime() > Date.now()

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-800">{assignment.title}</span>
            <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700">
              {TYPE_LABELS[assignment.assignment_type] ?? assignment.assignment_type}
            </span>
            <span className="text-xs text-gray-600">{assignment.max_marks} marks</span>
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            <span className={`text-xs flex items-center gap-0.5 ${
              isDeadlineSoon ? 'text-orange-600 font-medium' : 'text-gray-600'
            }`}>
              <Clock className="h-3 w-3" />
              Due {new Date(assignment.due_date).toLocaleString()}
            </span>
            <StatusPill assignment={assignment} submission={submission} />
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-gray-500 shrink-0" />
      </div>
    </button>
  )
}

export default function StudentAssignmentListPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const syllabusId = params.get('syllabus_id') ?? undefined

  const { data: assignData, isLoading, isError } = useStudentAssignments({ syllabus_id: syllabusId })
  const { data: subData } = useMySubmissions({ syllabus_id: syllabusId })

  const assignments = assignData?.items ?? []
  const submissions = subData?.items ?? []

  function handleClick(assignment: CourseworkAssignment) {
    const sub = latestSubmission(submissions, assignment.id)
    if (sub && (sub.status === 'GRADED' || sub.status === 'RETURNED')) {
      navigate(`/student/assignment-submissions/${sub.id}/result`)
    } else {
      navigate(`/student/assignments/${assignment.id}`)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Assignments</h1>
        <p className="text-sm text-gray-600 mt-0.5">Theory coursework — essays, reports, and case studies.</p>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          Failed to load assignments. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : assignments.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <ClipboardList className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-600">No assignments available.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {assignments.map((a) => (
            <AssignmentRow
              key={a.id}
              assignment={a}
              submission={latestSubmission(submissions, a.id)}
              onClick={() => handleClick(a)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
