// Evaluation Center — one assignment's workspace.
//
// Level 2: the full class roster (every enrolled student, submitted or not) with
// live progress, plus the proven grading surface (AssignmentGradingPanel, reused
// with its own header hidden). The roster is the "who has / hasn't submitted"
// overview the evaluator asked for; the panel below is where submitted work is
// actually graded. Nothing here is submission-gated, so the page loads from
// publish with "0 submitted" and fills in automatically as students submit.
import { useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentGradingPanel } from '@/components/coursework/AssignmentGradingPanel'
import { getEvaluationCenter } from '@/lib/api/coursework'
import type { EvaluationCenterStatus } from '@/types/coursework'

const STATUS_PILL: Record<EvaluationCenterStatus, string> = {
  NOT_SUBMITTED: 'bg-gray-100 text-gray-600',
  SUBMITTED:     'bg-blue-50 text-blue-700',
  UNDER_REVIEW:  'bg-amber-50 text-amber-700',
  REVIEWED:      'bg-green-50 text-green-700',
}

const STATUS_LABEL: Record<EvaluationCenterStatus, string> = {
  NOT_SUBMITTED: 'Not submitted',
  SUBMITTED:     'Submitted',
  UNDER_REVIEW:  'Under review',
  REVIEWED:      'Reviewed',
}

function ProgressStat({ value, label, tone = '' }: { value: number; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-center">
      <p className={`text-xl font-bold ${tone || 'text-gray-900'}`}>{value}</p>
      <p className="text-xs text-gray-600 mt-0.5">{label}</p>
    </div>
  )
}

export default function EvaluationCenterAssignmentPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const assignmentId = id ?? ''

  const { data, isLoading } = useQuery({
    queryKey: ['evaluation-center', assignmentId],
    queryFn: () => getEvaluationCenter(assignmentId),
    enabled: Boolean(assignmentId),
  })

  const assignment = data?.assignment
  const progress = data?.progress
  const students = data?.students ?? []
  const semester = data?.semester ?? null
  const gradeRef = useRef<HTMLDivElement>(null)

  // "Review" reuses the existing grading panel below — no separate grading UI.
  const openGrading = () => gradeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/faculty/evaluation-center')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Evaluation Center
      </Button>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{assignment?.title ?? 'Assignment'}</h1>
        {assignment && (
          <p className="text-sm text-gray-600 mt-0.5">
            {[
              assignment.course_code && `${assignment.course_code}${assignment.course_title ? ` — ${assignment.course_title}` : ''}`,
              semester != null && `Semester ${semester}`,
              assignment.created_by_name && `Faculty: ${assignment.created_by_name}`,
            ].filter(Boolean).join(' · ')}
            {assignment.due_date && <> · Due {new Date(assignment.due_date).toLocaleString()}</>}
            {' · '}{assignment.max_marks} marks
          </p>
        )}
        {assignment?.evaluator_names && assignment.evaluator_names.length > 0 && (
          <p className="text-xs text-gray-600 mt-1">
            Evaluators: {assignment.evaluator_names.join(', ')}
          </p>
        )}
      </div>

      {/* Live progress */}
      {progress && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <ProgressStat value={progress.total_students} label="Students" />
          <ProgressStat value={progress.submitted} label="Submitted" />
          <ProgressStat value={progress.pending_submission} label="Pending submission" />
          <ProgressStat value={progress.reviewed} label="Reviewed" tone="text-green-700" />
          <ProgressStat
            value={progress.pending_review}
            label="Pending review"
            tone={progress.pending_review > 0 ? 'text-orange-600' : 'text-gray-900'}
          />
        </div>
      )}

      {/* Student queue — the whole class, submitters and non-submitters alike. */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-600" />
          <h2 className="text-sm font-semibold text-gray-700">Student Queue</h2>
          <span className="text-xs text-gray-600">({students.length})</span>
        </div>
        {isLoading ? (
          <div className="text-sm text-gray-600 py-8 text-center">Loading roster…</div>
        ) : students.length === 0 ? (
          <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
            <p className="text-sm text-gray-600">No students are enrolled in this course yet.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {students.map((s) => (
              <div key={s.student_user_id} className="px-5 py-3 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {s.student_name ?? s.student_user_id}
                    {s.student_usn && <span className="text-gray-600 font-normal"> · {s.student_usn}</span>}
                  </p>
                  <p className="text-xs text-gray-600 mt-0.5">
                    {s.submitted_at ? `Submitted ${new Date(s.submitted_at).toLocaleString()}` : 'Awaiting submission'}
                    {s.is_late && <span className="text-orange-600 font-medium"> · Late</span>}
                    {s.marks_obtained != null && <> · {s.marks_obtained} marks</>}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_PILL[s.submission_status]}`}>
                    {STATUS_LABEL[s.submission_status]}
                  </span>
                  {s.submission_id && (
                    <button
                      type="button"
                      onClick={openGrading}
                      className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
                    >
                      Review →
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Grade submissions — the proven grading surface, reused as-is. */}
      {assignmentId && (
        <section ref={gradeRef} className="space-y-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-gray-600" />
            <h2 className="text-sm font-semibold text-gray-700">Grade Submissions</h2>
          </div>
          <AssignmentGradingPanel assignmentId={assignmentId} showHeader={false} />
        </section>
      )}
    </div>
  )
}
