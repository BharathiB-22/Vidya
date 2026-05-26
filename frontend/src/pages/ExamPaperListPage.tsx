// M08 Exam Setter — Exam paper list (role-aware: Faculty/Admin vs Board)
import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listExamPapers, listAllExamPapers, listBoardPending } from '@/lib/api/exam'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import type { ExamPaper, ExamPaperStatus } from '@/types/exam'

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

  const [statusFilter, setStatusFilter] = useState<ExamPaperStatus | ''>('')
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

  // Board clicks open the review page; faculty/admin open the editor
  function handlePaperClick(paperId: string) {
    if (isBoard) navigate(`/exams/${paperId}/review`)
    else navigate(`/exams/${paperId}`)
  }

  const pageTitle = isBoardPendingRoute ? 'Pending Board Review' : 'Exam Papers'

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">{pageTitle}</h1>
        </div>
        <Button
          onClick={() => navigate('/exams/create')}
          className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
        >
          <Plus className="w-4 h-4" />
          New Exam Paper
        </Button>
      </div>

      {/* Status filter — hidden on board/pending (already filtered to SUBMITTED) */}
      {!isBoardPendingRoute && <div className="flex flex-wrap gap-2">
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
      </div>}

      {isLoading && <PageLoading message="Loading exam papers…" />}

      {isError && (
        <PageError message="Failed to load exam papers." onRetry={() => refetch()} />
      )}

      {data && data.items.length === 0 && (
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

      {data && data.items.length > 0 && (
        <>
          <div className="space-y-3">
            {data.items.map(paper => (
              <PaperCard
                key={paper.id}
                paper={paper}
                onClick={() => handlePaperClick(paper.id)}
              />
            ))}
          </div>

          {/* Pagination */}
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
        </>
      )}
    </div>
  )
}

function PaperCard({ paper, onClick }: { paper: ExamPaper; onClick: () => void }) {
  const colorClass = STATUS_COLOR[paper.status] ?? 'bg-gray-100 text-gray-600'
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl border border-gray-200 bg-white p-4 hover:border-indigo-300 hover:shadow-sm transition-all"
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
        <span className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full ${colorClass}`}>
          {paper.status.replace('_', ' ')}
        </span>
      </div>
    </button>
  )
}
