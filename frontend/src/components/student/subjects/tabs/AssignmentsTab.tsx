import { useNavigate } from 'react-router-dom'
import { ClipboardList, Clock } from 'lucide-react'
import { useStudentAssignments, useMySubmissions } from '@/hooks/coursework'
import type { CourseworkAssignment, CourseworkSubmission } from '@/types/coursework'
import type { SubjectTabProps } from './types'

function latestSubmission(
  subs: CourseworkSubmission[],
  assignmentId: string
): CourseworkSubmission | undefined {
  const matches = subs.filter((s) => s.assignment_id === assignmentId)
  if (matches.length === 0) return undefined
  return matches.reduce((a, b) => (b.attempt_number > a.attempt_number ? b : a))
}

export function AssignmentsTab({ subject }: SubjectTabProps) {
  const navigate = useNavigate()
  const { data: assignData, isLoading } = useStudentAssignments({
    syllabus_id: subject.syllabus_id ?? undefined,
  })
  const { data: subData } = useMySubmissions({ syllabus_id: subject.syllabus_id ?? undefined })

  const assignments = assignData?.items ?? []
  const submissions = subData?.items ?? []

  function handleClick(a: CourseworkAssignment) {
    const sub = latestSubmission(submissions, a.id)
    if (sub && (sub.status === 'GRADED' || sub.status === 'RETURNED')) {
      navigate(`/student/assignment-submissions/${sub.id}/result`)
    } else {
      navigate(`/student/assignments/${a.id}`)
    }
  }

  if (isLoading) return <div className="text-sm text-gray-400 py-8 text-center">Loading assignments…</div>

  if (assignments.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <ClipboardList className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No assignments for this subject yet.</p>
      </div>
    )
  }

  const overdue = assignments.filter((a) => !latestSubmission(submissions, a.id) && new Date(a.due_date) < new Date())
  const pending = assignments.filter((a) => !latestSubmission(submissions, a.id) && new Date(a.due_date) >= new Date())
  const submitted = assignments.filter((a) => {
    const s = latestSubmission(submissions, a.id)
    return s && s.status === 'SUBMITTED'
  })
  const graded = assignments.filter((a) => {
    const s = latestSubmission(submissions, a.id)
    return s && (s.status === 'GRADED' || s.status === 'RETURNED')
  })

  const renderGroup = (label: string, items: CourseworkAssignment[]) =>
    items.length > 0 && (
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
          {label} ({items.length})
        </h3>
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((a) => {
            const sub = latestSubmission(submissions, a.id)
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => handleClick(a)}
                className="w-full text-left px-5 py-3 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm font-medium text-gray-800">{a.title}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {sub?.marks_obtained != null && (
                      <span className="text-xs font-semibold text-green-700">
                        {sub.marks_obtained}/{a.max_marks}
                      </span>
                    )}
                    <span className="text-xs text-gray-400 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(a.due_date).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    )

  return (
    <div className="space-y-4">
      {renderGroup('Overdue', overdue)}
      {renderGroup('Pending', pending)}
      {renderGroup('Submitted', submitted)}
      {renderGroup('Graded', graded)}
    </div>
  )
}
