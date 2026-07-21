// M08 Exam Setter — Dean: review queue for INTERNAL papers (approve / return)
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardCheck, Loader2, CheckCircle2, CornerUpLeft, ExternalLink } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { listDeanPending, deanDecision } from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import type { ExamPaper } from '@/types/exam'

export default function DeanReviewPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [returnFor, setReturnFor] = useState<ExamPaper | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['dean-pending'],
    queryFn: () => listDeanPending(),
  })
  const papers = data?.items ?? []

  const approveMut = useMutation({
    mutationFn: (paperId: string) => deanDecision(paperId, { approved: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dean-pending'] }),
  })

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardCheck}
        title="Internal Paper Review"
        subtitle="Internal assessment papers submitted by faculty for your approval."
      />

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load the review queue. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="text-muted-foreground py-8">Loading…</div>
      ) : papers.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200 text-gray-600">
          No internal papers awaiting review.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {papers.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{p.title}</p>
                <p className="text-xs text-gray-600">
                  {p.exam_type.replace('_', ' ')} · {p.total_marks} marks · {p.duration_mins} min
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button size="sm" variant="outline" onClick={() => navigate(`/exams/${p.id}`)}>
                  <ExternalLink className="h-3.5 w-3.5 mr-1" /> View
                </Button>
                <Button size="sm" variant="outline" className="text-orange-600" onClick={() => setReturnFor(p)}>
                  <CornerUpLeft className="h-3.5 w-3.5 mr-1" /> Return
                </Button>
                <Button
                  size="sm"
                  className="bg-green-600 hover:bg-green-700 text-white"
                  disabled={approveMut.isPending}
                  onClick={() => approveMut.mutate(p.id)}
                >
                  {approveMut.isPending
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <><CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve</>}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {returnFor && (
        <ReturnDialog
          paper={returnFor}
          onClose={() => setReturnFor(null)}
          onDone={() => { setReturnFor(null); qc.invalidateQueries({ queryKey: ['dean-pending'] }) }}
        />
      )}
    </PageShell>
  )
}

function ReturnDialog({ paper, onClose, onDone }: { paper: ExamPaper; onClose: () => void; onDone: () => void }) {
  const [comment, setComment] = useState('')
  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: () => deanDecision(paper.id, { approved: false, board_comment: comment.trim() }),
    onSuccess: onDone,
  })
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Return “{paper.title}”</h2>
        <p className="text-sm text-gray-600">The faculty will edit this same paper and resubmit.</p>
        <textarea
          rows={4}
          value={comment}
          onChange={e => setComment(e.target.value)}
          placeholder="Comments for the faculty (required)…"
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 resize-none"
        />
        {isError && <p className="text-sm text-red-600">{getErrorMessage(error)}</p>}
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1 bg-orange-600 hover:bg-orange-700 text-white"
            disabled={isPending || !comment.trim()}
            onClick={() => mutate()}
          >
            {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Return with Comments'}
          </Button>
        </div>
      </div>
    </div>
  )
}
