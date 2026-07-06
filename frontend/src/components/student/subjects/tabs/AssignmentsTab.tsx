import { useNavigate } from 'react-router-dom'
import { ClipboardList, Clock } from 'lucide-react'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import type { LabAssignment, LabSubmission } from '@/types/labs'
import type { SubjectTabProps } from './types'

export function AssignmentsTab({ subject }: SubjectTabProps) {
  const navigate = useNavigate()
  const { data: assignData, isLoading } = useStudentAssignments({
    syllabus_id: subject.syllabus_id ?? undefined,
  })
  const { data: subData } = useMySubmissions()

  const assignments = assignData?.items ?? []
  const submissions = subData?.items ?? []

  function getSubmission(assignmentId: string): LabSubmission | undefined {
    return submissions.find((s) => s.assignment_id === assignmentId)
  }

  function handleClick(a: LabAssignment) {
    const sub = getSubmission(a.id)
    if (sub?.status === 'RATIFIED') navigate(`/student/submissions/${sub.id}/result`)
    else navigate(`/student/labs/${a.id}`)
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

  const pending = assignments.filter((a) => !getSubmission(a.id))
  const submitted = assignments.filter((a) => getSubmission(a.id))

  const renderGroup = (label: string, items: LabAssignment[]) =>
    items.length > 0 && (
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
          {label} ({items.length})
        </h3>
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => handleClick(a)}
              className="w-full text-left px-5 py-3 hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center justify-between gap-4">
                <span className="text-sm font-medium text-gray-800">{a.title}</span>
                {a.deadline && (
                  <span className="text-xs text-gray-400 flex items-center gap-1 shrink-0">
                    <Clock className="h-3 w-3" />
                    {new Date(a.deadline).toLocaleDateString()}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>
    )

  return (
    <div className="space-y-4">
      {renderGroup('Pending', pending)}
      {renderGroup('Submitted', submitted)}
    </div>
  )
}
