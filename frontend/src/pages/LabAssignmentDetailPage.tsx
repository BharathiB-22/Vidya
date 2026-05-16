import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Users, Clock, Download, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { useLabAssignment, useSubmissions, usePublishAssignment, useCloseAssignment } from '@/hooks/labs'
import { getModerationReportUrl } from '@/lib/api/labs'
import type { LabSubmission, SubmissionStatus } from '@/types/labs'

type Tab = 'overview' | 'submissions'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const SUB_STATUS_CFG: Record<SubmissionStatus, { label: string; cls: string }> = {
  SUBMITTED:  { label: 'Submitted',  cls: 'text-blue-700 bg-blue-50' },
  EVALUATING: { label: 'Evaluating', cls: 'text-yellow-700 bg-yellow-50' },
  EVALUATED:  { label: 'Evaluated',  cls: 'text-purple-700 bg-purple-50' },
  REVIEWED:   { label: 'Reviewed',   cls: 'text-indigo-700 bg-indigo-50' },
  RATIFIED:   { label: 'Ratified',   cls: 'text-green-700 bg-green-50' },
}

function InfoCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 bg-white">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-semibold text-gray-800 mt-0.5">{String(value)}</p>
    </div>
  )
}

function SubmissionRow({ sub, onReview }: { sub: LabSubmission; onReview: () => void }) {
  const cfg = SUB_STATUS_CFG[sub.status] ?? { label: sub.status, cls: 'text-gray-500 bg-gray-50' }
  const canReview = sub.status === 'EVALUATED' || sub.status === 'REVIEWED' || sub.status === 'RATIFIED'
  return (
    <div className="px-5 py-3 flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-mono text-gray-700 truncate">{sub.student_user_id}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>{cfg.label}</span>
          <AIScanBadge status={sub.ai_scan_status} />
          {sub.is_late && (
            <span className="text-xs text-orange-600 bg-orange-50 px-1.5 py-0.5 rounded">Late</span>
          )}
          <span className="text-xs text-gray-400">{new Date(sub.submitted_at).toLocaleDateString()}</span>
        </div>
      </div>
      {canReview && (
        <Button size="sm" variant="ghost" onClick={onReview} className="shrink-0 text-gray-600">
          <Eye className="h-3.5 w-3.5 mr-1" />
          Review
        </Button>
      )}
    </div>
  )
}

export default function LabAssignmentDetailPage() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const role      = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canWrite  = WRITE_ROLES.includes(role)
  const [tab, setTab] = useState<Tab>('overview')

  const assignmentId = id ?? ''
  const { data: assignment, isLoading } = useLabAssignment(assignmentId)
  const { data: subsData } = useSubmissions(assignmentId)
  const submissions = subsData?.items ?? []

  const { mutate: publish, isPending: publishing } = usePublishAssignment()
  const { mutate: close,   isPending: closing }    = useCloseAssignment()

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-4 animate-pulse">
        <div className="h-4 w-24 bg-gray-200 rounded" />
        <div className="h-8 w-64 bg-gray-200 rounded" />
        <div className="h-4 w-32 bg-gray-100 rounded" />
      </div>
    )
  }

  if (!assignment) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-gray-400 text-sm">
        Assignment not found.
      </div>
    )
  }

  const totalMarks = assignment.rubric.reduce((s, c) => s + c.max_marks, 0)

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate('/labs')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">{assignment.title}</h1>
            <LabStatusBadge status={assignment.status} />
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              assignment.submission_type === 'CODE' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
            }`}>
              {assignment.submission_type}
            </span>
          </div>
          {assignment.deadline && (
            <p className="text-sm text-gray-400 mt-1 flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              Due {new Date(assignment.deadline).toLocaleString()}
            </p>
          )}
        </div>

        {canWrite && (
          <div className="flex items-center gap-2 flex-wrap">
            {assignment.status === 'DRAFT' && (
              <Button
                size="sm"
                className="bg-green-700 hover:bg-green-800 text-white"
                onClick={() => publish(assignmentId)}
                disabled={publishing}
              >
                Publish
              </Button>
            )}
            {assignment.status === 'PUBLISHED' && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-orange-700 border-orange-200 hover:bg-orange-50"
                  onClick={() => close(assignmentId)}
                  disabled={closing}
                >
                  Close
                </Button>
                <a
                  href={getModerationReportUrl(assignmentId)}
                  download
                  className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 font-medium"
                >
                  <Download className="h-3.5 w-3.5" />
                  Report
                </a>
              </>
            )}
            {assignment.status === 'CLOSED' && (
              <a
                href={getModerationReportUrl(assignmentId)}
                download
                className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 font-medium"
              >
                <Download className="h-3.5 w-3.5" />
                Report
              </a>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['overview', 'submissions'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
              tab === t
                ? 'text-gray-900 border-b-2 border-gray-900 -mb-px'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t}
            {t === 'submissions' && submissions.length > 0 && (
              <span className="ml-1.5 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">
                {submissions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-6">
          {assignment.description && (
            <p className="text-sm text-gray-700 leading-relaxed">{assignment.description}</p>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <InfoCard label="Max Marks" value={assignment.max_marks ?? totalMarks} />
            <InfoCard label="Rubric Criteria" value={assignment.rubric.length} />
            {assignment.submission_type === 'CODE' && (
              <InfoCard label="Test Cases" value={assignment.test_cases?.length ?? 0} />
            )}
            <InfoCard label="AI Permitted" value={assignment.ai_not_permitted ? 'No' : 'Yes'} />
            <InfoCard label="Late Submissions" value={assignment.allow_late ? 'Allowed' : 'Not allowed'} />
            {assignment.language && (
              <InfoCard label="Language" value={assignment.language} />
            )}
          </div>

          {/* Rubric */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Rubric</h2>
            <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
              {assignment.rubric.map((c) => (
                <div key={c.criterion_id} className="px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-800">{c.name}</span>
                    <span className="text-xs text-gray-500 shrink-0">
                      {c.max_marks} marks · weight {c.weight.toFixed(2)}
                    </span>
                  </div>
                  {c.description && (
                    <p className="text-xs text-gray-400 mt-0.5">{c.description}</p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Test cases — CODE only */}
          {assignment.submission_type === 'CODE' && (assignment.test_cases?.length ?? 0) > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-3">Test Cases</h2>
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {assignment.test_cases.map((tc) => (
                  <div key={tc.id} className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{tc.name}</span>
                      {tc.is_hidden && (
                        <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">Hidden</span>
                      )}
                      <span className="text-xs text-gray-400 ml-auto">{tc.points} pts</span>
                    </div>
                    {tc.stdin && (
                      <pre className="text-xs text-gray-500 mt-1.5 font-mono bg-gray-50 rounded p-2 overflow-x-auto">
                        stdin: {tc.stdin}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'submissions' && (
        <div>
          {submissions.length === 0 ? (
            <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
              <Users className="h-8 w-8 mx-auto mb-2 text-gray-200" />
              <p className="text-sm text-gray-400">No submissions yet.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
              {submissions.map((sub) => (
                <SubmissionRow
                  key={sub.id}
                  sub={sub}
                  onReview={() => navigate(`/labs/review/${sub.id}`)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
