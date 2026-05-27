import { useNavigate } from 'react-router-dom'
import { ClipboardCheck, Clock, CheckCircle2 } from 'lucide-react'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useEvaluatorAssignments, useEvaluatorAnalytics } from '@/hooks/labs'
import type { LabAssignment } from '@/types/labs'

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  colorClass,
}: {
  label: string
  value: number
  icon: typeof ClipboardCheck
  colorClass: string
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 flex items-center gap-4">
      <div className={`rounded-lg p-2.5 ${colorClass}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      </div>
    </div>
  )
}

// ── Assignment row ────────────────────────────────────────────────────────────

function AssignmentRow({ assignment }: { assignment: LabAssignment }) {
  const navigate = useNavigate()
  const totalMarks = assignment.rubric.reduce((s, c) => s + c.max_marks, 0)

  return (
    <button
      type="button"
      onClick={() => navigate(`/evaluator/${assignment.id}/submissions`)}
      className="w-full px-5 py-4 flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium text-gray-900 truncate">{assignment.title}</p>
          <LabStatusBadge status={assignment.status} />
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
            assignment.submission_type === 'CODE'
              ? 'bg-blue-50 text-blue-700'
              : 'bg-purple-50 text-purple-700'
          }`}>
            {assignment.submission_type}
          </span>
        </div>
        <p className="text-xs text-gray-400 mt-0.5">
          {totalMarks} marks
          {assignment.deadline && (
            <> · Due {new Date(assignment.deadline).toLocaleDateString()}</>
          )}
        </p>
      </div>
      <span className="text-xs text-indigo-600 font-medium shrink-0">
        View submissions →
      </span>
    </button>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EvaluatorDashboardPage() {
  const { data: assignmentsData, isLoading: assignmentsLoading, isError } = useEvaluatorAssignments()
  const { data: analytics } = useEvaluatorAnalytics()

  const assignments = assignmentsData?.items ?? []

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardCheck}
        title="My Evaluations"
        subtitle="Lab assignments assigned to you for evaluation"
      />

      {/* Analytics strip */}
      {analytics && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="Assigned Labs"
            value={analytics.total_assigned}
            icon={ClipboardCheck}
            colorClass="bg-indigo-50 text-indigo-600"
          />
          <StatCard
            label="Pending Review"
            value={analytics.pending_review}
            icon={Clock}
            colorClass="bg-amber-50 text-amber-600"
          />
          <StatCard
            label="Recommended"
            value={analytics.recommended}
            icon={CheckCircle2}
            colorClass="bg-blue-50 text-blue-600"
          />
          <StatCard
            label="Ratified"
            value={analytics.ratified}
            icon={CheckCircle2}
            colorClass="bg-green-50 text-green-600"
          />
        </div>
      )}

      {/* Assignment list */}
      {assignmentsLoading ? (
        <PageLoading message="Loading assignments…" />
      ) : isError ? (
        <PageError message="Failed to load assignments." />
      ) : assignments.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <ClipboardCheck className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm font-medium text-gray-500">No evaluations assigned yet.</p>
          <p className="text-xs text-gray-400 mt-1">
            A faculty member will assign you to lab assignments.
          </p>
        </div>
      ) : (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Assigned Assignments ({assignments.length})
          </h2>
          <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
            {assignments.map((a) => (
              <AssignmentRow key={a.id} assignment={a} />
            ))}
          </div>
        </div>
      )}
    </PageShell>
  )
}
