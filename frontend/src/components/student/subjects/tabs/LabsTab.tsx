import { useNavigate } from 'react-router-dom'
import { FlaskConical, Clock } from 'lucide-react'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import { groupByLabGroup, labProgramLabel } from '@/lib/labGrouping'
import type { LabAssignment, LabSubmission } from '@/types/labs'
import type { SubjectTabProps } from './types'

export function LabsTab({ subject }: SubjectTabProps) {
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

  if (isLoading) return <div className="text-sm text-gray-600 py-8 text-center">Loading labs…</div>

  if (assignments.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <FlaskConical className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-600">No lab assignments for this subject yet.</p>
      </div>
    )
  }

  const pending = assignments.filter((a) => !getSubmission(a.id))
  const submitted = assignments.filter((a) => getSubmission(a.id))

  const renderRow = (a: LabAssignment, displayTitle?: string) => {
    const sub = getSubmission(a.id)
    return (
      <button
        key={a.id}
        type="button"
        onClick={() => handleClick(a)}
        className="w-full text-left px-5 py-3 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800">{displayTitle ?? a.title}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              a.submission_type === 'CODE' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
            }`}>
              {a.submission_type}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {sub?.status === 'RATIFIED' && sub.final_score != null && (
              <span className="text-xs font-semibold text-green-700">
                {sub.final_score}/{sub.graded_max_marks}
              </span>
            )}
            {a.deadline && (
              <span className="text-xs text-gray-600 flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {new Date(a.deadline).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      </button>
    )
  }

  const renderGroup = (label: string, items: LabAssignment[]) => {
    if (items.length === 0) return null
    const { grouped, ungrouped } = groupByLabGroup(items)
    return (
      <div>
        <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
          {label} ({items.length})
        </h3>
        <div className="space-y-3">
          {grouped.map((g) => (
            <div key={g.label}>
              <p className="text-xs font-medium text-gray-500 mb-1">{g.label}</p>
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {g.items.map((a) => renderRow(a, labProgramLabel(a)))}
              </div>
            </div>
          ))}
          {ungrouped.length > 0 && (
            <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
              {ungrouped.map((a) => renderRow(a))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {renderGroup('Pending', pending)}
      {renderGroup('Submitted', submitted)}
    </div>
  )
}
