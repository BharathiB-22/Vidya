// Evaluation Center — the coursework-specific evaluator workspace (Level 1).
//
// Every assignment the caller is a nominated/allocated evaluator for, shown from
// the moment the faculty publishes (before any student submits). Each card
// carries the full context — subject, semester, faculty, evaluators — plus the
// live whole-class progress, so the evaluator understands the assignment at a
// glance and drills in for the student queue.
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ListChecks, ArrowRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listMyCourseworkEvaluations } from '@/lib/api/coursework'

function Metric({ value, label, tone = '' }: { value: number; label: string; tone?: string }) {
  return (
    <div className="text-center">
      <p className={`text-lg font-bold ${tone || 'text-gray-900'}`}>{value}</p>
      <p className="text-[11px] text-gray-600 mt-0.5 leading-tight">{label}</p>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium text-gray-500">{label}</p>
      <p className="text-sm text-gray-800 truncate">{value}</p>
    </div>
  )
}

export default function EvaluationCenterPage() {
  const navigate = useNavigate()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['evaluation-center', 'list'],
    queryFn: listMyCourseworkEvaluations,
  })

  return (
    <PageShell>
      <PageHeader
        icon={ListChecks}
        title="Evaluation Center"
        subtitle="Coursework assigned to you — open an assignment to review its student queue"
      />

      {!isLoading && items.length === 0 && (
        <PageEmpty
          icon={ListChecks}
          message="No coursework is assigned to you for evaluation yet."
        />
      )}

      <div className="space-y-4">
        {items.map((cw) => {
          const subject = [cw.course_code, cw.course_title].filter(Boolean).join(' — ') || 'Course'
          const courseLine = [
            cw.course_title ?? cw.course_code,
            cw.semester != null ? `Semester ${cw.semester}` : null,
          ].filter(Boolean).join(' · ')
          return (
            <button
              key={cw.assignment_id}
              type="button"
              onClick={() => navigate(`/faculty/evaluation-center/${cw.assignment_id}`)}
              className="w-full text-left rounded-xl border border-gray-200 bg-white px-5 py-4 hover:border-indigo-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{cw.assignment_title}</p>
                  <p className="text-xs text-gray-600 mt-0.5 truncate">{subject}</p>
                </div>
                <ArrowRight className="h-4 w-4 text-indigo-500 shrink-0 mt-0.5" />
              </div>

              <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2">
                <Field label="Faculty" value={cw.faculty_name ?? '—'} />
                <Field label="Course" value={courseLine || '—'} />
                <Field label="Evaluator" value={cw.evaluator_names ?? '—'} />
                <Field
                  label="Due"
                  value={cw.due_date ? new Date(cw.due_date).toLocaleDateString() : '—'}
                />
              </div>

              <div className="mt-3 pt-3 border-t border-gray-100 grid grid-cols-5 gap-2">
                <Metric value={cw.total_students} label="Students" />
                <Metric value={cw.submitted_students} label="Submitted" />
                <Metric value={cw.pending_submission} label="Pending submission" />
                <Metric
                  value={cw.pending_review}
                  label="Pending review"
                  tone={cw.pending_review > 0 ? 'text-orange-600' : 'text-gray-900'}
                />
                <Metric value={cw.reviewed_students} label="Reviewed" tone="text-green-700" />
              </div>
            </button>
          )
        })}
      </div>
    </PageShell>
  )
}
