import { useNavigate, useSearchParams } from 'react-router-dom'
import { ClipboardList, ChevronRight, Clock } from 'lucide-react'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import type { LabAssignment, LabSubmission } from '@/types/labs'

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

function AssignmentRow({
  assignment,
  submission,
  onClick,
}: {
  assignment: LabAssignment
  submission: LabSubmission | undefined
  onClick: () => void
}) {
  const isDeadlineSoon =
    assignment.deadline != null &&
    new Date(assignment.deadline).getTime() - Date.now() < 48 * 60 * 60 * 1000 &&
    new Date(assignment.deadline).getTime() > Date.now()

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
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              assignment.submission_type === 'CODE'
                ? 'bg-blue-50 text-blue-700'
                : 'bg-purple-50 text-purple-700'
            }`}>
              {assignment.submission_type}
            </span>
            {assignment.max_marks != null && (
              <span className="text-xs text-gray-400">{assignment.max_marks} marks</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {assignment.deadline && (
              <span className={`text-xs flex items-center gap-0.5 ${
                isDeadlineSoon ? 'text-orange-600 font-medium' : 'text-gray-400'
              }`}>
                <Clock className="h-3 w-3" />
                Due {new Date(assignment.deadline).toLocaleString()}
              </span>
            )}
            {submission && (
              <SubmissionPill submission={submission} />
            )}
            {!submission && assignment.ai_not_permitted && (
              <span className="text-xs text-gray-400">AI not permitted</span>
            )}
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-gray-300 shrink-0" />
      </div>
    </button>
  )
}

function SubmissionPill({ submission }: { submission: LabSubmission }) {
  const CFG: Record<string, { label: string; cls: string }> = {
    SUBMITTED:  { label: 'Submitted',  cls: 'text-blue-700 bg-blue-50' },
    EVALUATING: { label: 'Evaluating', cls: 'text-yellow-700 bg-yellow-50' },
    EVALUATED:  { label: 'Evaluated',  cls: 'text-purple-700 bg-purple-50' },
    REVIEWED:   { label: 'Under review', cls: 'text-indigo-700 bg-indigo-50' },
    RATIFIED:   { label: 'Graded',     cls: 'text-green-700 bg-green-50' },
  }
  const cfg = CFG[submission.status] ?? { label: submission.status, cls: 'text-gray-500 bg-gray-50' }
  return (
    <div className="flex items-center gap-1.5">
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>{cfg.label}</span>
      {submission.ai_scan_status !== 'PENDING' && (
        <AIScanBadge status={submission.ai_scan_status} />
      )}
    </div>
  )
}

export default function StudentLabListPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const syllabusId = params.get('syllabus_id') ?? undefined

  const { data: assignData, isLoading, isError } = useStudentAssignments({ syllabus_id: syllabusId })
  const { data: mySubData } = useMySubmissions()

  const assignments = assignData?.items ?? []
  const mySubmissions = mySubData?.items ?? []

  function getSubmission(assignmentId: string): LabSubmission | undefined {
    return mySubmissions.find((s) => s.assignment_id === assignmentId)
  }

  function handleClick(assignment: LabAssignment) {
    const sub = getSubmission(assignment.id)
    if (sub?.status === 'RATIFIED') {
      navigate(`/student/submissions/${sub.id}/result`)
    } else {
      navigate(`/student/labs/${assignment.id}`)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Lab Assignments</h1>
        <p className="text-sm text-gray-400 mt-0.5">Submit your work and track evaluation status.</p>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
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
          <p className="text-sm text-gray-400">No assignments available.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {assignments.map((a) => (
            <AssignmentRow
              key={a.id}
              assignment={a}
              submission={getSubmission(a.id)}
              onClick={() => handleClick(a)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
