// M08 Exam Setter — Exam paper list (role-aware: Faculty/Admin vs Board)
import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listExamPapers, listAllExamPapers, listBoardPending } from '@/lib/api/exam'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import type { ExamPaper, ExamPaperStatus, ExamWorkflow } from '@/types/exam'

const STATUS_OPTS: Array<{ value: ExamPaperStatus | ''; label: string }> = [
  { value: '',               label: 'All' },
  { value: 'DRAFT',          label: 'Draft' },
  { value: 'GENERATING',     label: 'Generating' },
  { value: 'GENERATED',      label: 'Generated' },
  { value: 'FAILED',         label: 'Failed' },
  { value: 'SUBMITTED',      label: 'Submitted' },
  { value: 'BOARD_APPROVED', label: 'Board Approved' },
  { value: 'BOARD_RETURNED', label: 'Board Returned' },
  { value: 'SEALED',         label: 'Sealed' },
  { value: 'RELEASED',       label: 'Released' },
]

const WORKFLOW_OPTS: Array<{ value: ExamWorkflow | ''; label: string }> = [
  { value: '',          label: 'All Workflows' },
  { value: 'INTERNAL',  label: 'Internal' },
  { value: 'BOARD_EXAM', label: 'Board Exam' },
]

const STATUS_COLOR: Record<string, string> = {
  DRAFT:          'bg-gray-100 text-gray-600',
  GENERATING:     'bg-blue-100 text-blue-600',
  GENERATED:      'bg-indigo-100 text-indigo-700',
  FAILED:         'bg-red-100 text-red-600',
  SUBMITTED:      'bg-yellow-100 text-yellow-700',
  BOARD_APPROVED: 'bg-green-100 text-green-700',
  BOARD_RETURNED: 'bg-orange-100 text-orange-700',
  SEALED:         'bg-purple-100 text-purple-700',
  RELEASED:       'bg-emerald-100 text-emerald-700',
}

export default function ExamPaperListPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useCurrentUser()
  const role = user?.role ?? ''

  const isBoardPendingRoute = location.pathname === '/exams/board/pending'
  const isBoard = role === 'BOARD'
  const canManageMarks = ['FACULTY', 'DEAN', 'ADMIN'].includes(role)

  const [statusFilter, setStatusFilter] = useState<ExamPaperStatus | ''>('')
  const [workflowFilter, setWorkflowFilter] = useState<ExamWorkflow | ''>('')
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Route-aware query: board/pending → listBoardPending, board on /exams → listAllExamPapers, faculty → own papers
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['exam-papers', role, isBoardPendingRoute, statusFilter, offset],
    queryFn: () => {
      if (isBoardPendingRoute) return listBoardPending({ offset, limit })
      if (isBoard) return listAllExamPapers({ status: statusFilter || undefined, offset, limit })
      return listExamPapers({ status: statusFilter || undefined, offset, limit })
    },
  })

  // Client-side workflow filter applied to current page
  const visibleItems = workflowFilter
    ? (data?.items ?? []).filter(p => p.exam_workflow === workflowFilter)
    : (data?.items ?? [])

  // Board clicks open the review page; faculty/admin open the editor
  function handlePaperClick(paperId: string) {
    if (isBoard) navigate(`/exams/${paperId}/review`)
    else navigate(`/exams/${paperId}`)
  }

  const pageTitle = isBoardPendingRoute ? 'Pending Board Review' : 'Exam Papers'

  return (
    <PageShell>
      <PageHeader
        icon={FileText}
        title={pageTitle}
        action={!isBoardPendingRoute ? (
          <Button onClick={() => navigate('/exams/create')} className="gap-2">
            <Plus className="w-4 h-4" />
            New Exam Paper
          </Button>
        ) : undefined}
      />

      {/* Status filter — hidden on board/pending (already filtered to SUBMITTED) */}
      {!isBoardPendingRoute && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTS.map(opt => (
              <button
                key={opt.value}
                onClick={() => { setStatusFilter(opt.value); setOffset(0) }}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  statusFilter === opt.value
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {/* Workflow filter */}
          <div className="flex flex-wrap gap-2">
            {WORKFLOW_OPTS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setWorkflowFilter(opt.value)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  workflowFilter === opt.value
                    ? 'bg-amber-600 text-white border-amber-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-amber-300'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {isLoading && <PageLoading message="Loading exam papers…" />}

      {isError && (
        <PageError message="Failed to load exam papers." onRetry={() => refetch()} />
      )}

      {data && visibleItems.length === 0 && (
        <PageEmpty
          icon={FileText}
          message="No exam papers found."
          action={
            <Button variant="outline" size="sm" onClick={() => navigate('/exams/create')}>
              Create your first exam paper
            </Button>
          }
        />
      )}

      {data && visibleItems.length > 0 && (
        <>
          <div className="space-y-3">
            {visibleItems.map(paper => (
              <PaperCard
                key={paper.id}
                paper={paper}
                onClick={() => handlePaperClick(paper.id)}
                onMarksClick={
                  canManageMarks && paper.exam_workflow === 'INTERNAL'
                    ? () => navigate(`/exams/internal-marks/course/${paper.course_id}`)
                    : undefined
                }
              />
            ))}
          </div>

          {/* Pagination — only shown when no workflow filter (otherwise count may be off) */}
          {!workflowFilter && (
            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-500">
                Showing {offset + 1}–{Math.min(offset + limit, data.total)} of {data.total}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + limit >= data.total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
          {workflowFilter && (
            <p className="text-xs text-gray-400 pt-1">
              {visibleItems.length} item{visibleItems.length !== 1 ? 's' : ''} on this page matching workflow filter.
            </p>
          )}
        </>
      )}
    </PageShell>
  )
}

function PaperCard({
  paper,
  onClick,
  onMarksClick,
}: {
  paper: ExamPaper
  onClick: () => void
  onMarksClick?: () => void
}) {
  const colorClass = STATUS_COLOR[paper.status] ?? 'bg-gray-100 text-gray-600'
  const workflowBadge =
    paper.exam_workflow === 'INTERNAL'
      ? 'bg-amber-100 text-amber-700'
      : 'bg-indigo-100 text-indigo-700'
  const workflowLabel = paper.exam_workflow === 'INTERNAL' ? 'Internal' : 'Board Exam'

  return (
    <div className="rounded-xl border border-gray-200 bg-white hover:border-indigo-300 hover:shadow-sm transition-all">
      <button
        onClick={onClick}
        className="w-full text-left p-4"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-gray-900 truncate">{paper.title}</p>
            <p className="text-sm text-gray-500 mt-0.5">
              {paper.exam_type.replace('_', ' ')} · {paper.total_marks} marks · {paper.duration_mins} min
            </p>
            {paper.release_at && (
              <p className="text-xs text-gray-400 mt-1">
                Release: {new Date(paper.release_at).toLocaleString()}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${colorClass}`}>
              {paper.status.replace(/_/g, ' ')}
            </span>
            <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${workflowBadge}`}>
              {workflowLabel}
            </span>
          </div>
        </div>
      </button>

      {onMarksClick && (
        <div className="px-4 pb-3 pt-0 border-t border-gray-100">
          <button
            onClick={e => { e.stopPropagation(); onMarksClick() }}
            className="flex items-center gap-1 text-xs font-medium text-amber-700 hover:text-amber-900 transition-colors"
          >
            Internal Marks
            <ChevronRight className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  )
}
