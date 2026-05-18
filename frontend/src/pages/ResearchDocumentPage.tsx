// M07 Research Supervision — Guide: Document review panel
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, FileText, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getDocument, reviewDocument } from '@/lib/api/research'

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null
  const pct = Math.round(value * 100)
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-600">
        <span>{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full ${
            pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function ResearchDocumentPage() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const qc        = useQueryClient()

  const [decision, setDecision] = useState<'APPROVE' | 'REQUEST_REVISION'>('APPROVE')
  const [comment, setComment]   = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)

  const { data: doc, isLoading, isError } = useQuery({
    queryKey: ['research-doc', id],
    queryFn: () => getDocument(id!),
    enabled: !!id,
  })

  const { mutate: review, isPending } = useMutation({
    mutationFn: () => reviewDocument(id!, { decision, guide_comment: comment || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-doc', id] })
      qc.invalidateQueries({ queryKey: ['research-docs-guide'] })
      setReviewOpen(false)
    },
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
    </div>
  )
  if (isError || !doc) return (
    <div className="max-w-4xl mx-auto px-4 py-8 text-red-600 text-sm">
      Failed to load document.
    </div>
  )

  const canReview = doc.status === 'EVALUATED' || doc.status === 'GUIDE_REVIEWED'

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-gray-400" />
            <h1 className="text-xl font-bold text-gray-900">
              Research Document v{doc.version}
            </h1>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              doc.status === 'APPROVED' ? 'bg-green-100 text-green-700' :
              doc.status === 'EVALUATED' ? 'bg-blue-100 text-blue-700' :
              doc.status === 'REVISION_REQUESTED' ? 'bg-orange-100 text-orange-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {doc.status.replace('_', ' ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Submitted {new Date(doc.submitted_at).toLocaleDateString()}
            {doc.file_name && ` · ${doc.file_name}`}
          </p>
        </div>

        {canReview && (
          <Button onClick={() => setReviewOpen(true)}>Review Document</Button>
        )}
      </div>

      {/* AI Scores */}
      {(doc.plagiarism_score !== null || doc.ai_content_score !== null) && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">AI Evaluation Scores</h2>
          <div className="grid grid-cols-2 gap-4">
            <ScoreBar label="Format Compliance" value={doc.format_score} />
            <ScoreBar label="Clarity" value={doc.clarity_score} />
            <ScoreBar label="Plagiarism (lower is better)" value={doc.plagiarism_score !== null ? 1 - doc.plagiarism_score : null} />
            <ScoreBar label="AI Content (lower is better)" value={doc.ai_content_score !== null ? 1 - doc.ai_content_score : null} />
          </div>
          {doc.ai_model && (
            <p className="text-xs text-gray-400">Model: {doc.ai_model}</p>
          )}
        </div>
      )}

      {/* Evaluation report */}
      {doc.evaluation_report && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">Evaluation Report</h2>
          {doc.evaluation_report.sections?.map((s) => (
            <div key={s.section} className="flex items-start gap-3">
              <span className={`mt-0.5 h-4 w-4 rounded-full flex-shrink-0 ${
                s.present ? 'bg-green-400' : 'bg-red-300'
              }`} />
              <div>
                <p className="text-sm font-medium text-gray-800">{s.section}</p>
                {s.comment && <p className="text-xs text-gray-500">{s.comment}</p>}
              </div>
            </div>
          ))}
          {doc.evaluation_report.overall_comment && (
            <p className="text-sm text-gray-600 border-t border-gray-100 pt-3">
              {doc.evaluation_report.overall_comment}
            </p>
          )}
        </div>
      )}

      {/* Guide comment */}
      {doc.guide_comment && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4">
          <p className="text-sm font-medium text-indigo-700">Guide feedback</p>
          <p className="text-sm text-indigo-900 mt-1">{doc.guide_comment}</p>
        </div>
      )}

      {/* Review modal */}
      {reviewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Review Document</h2>

            <div className="flex gap-2">
              {(['APPROVE', 'REQUEST_REVISION'] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDecision(d)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    decision === d
                      ? d === 'APPROVE'
                        ? 'bg-green-600 text-white border-green-600'
                        : 'bg-orange-500 text-white border-orange-500'
                      : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {d === 'APPROVE' ? 'Approve' : 'Request Revision'}
                </button>
              ))}
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Comment (optional)</label>
              <textarea
                rows={3}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Feedback for the student…"
              />
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="ghost" onClick={() => setReviewOpen(false)} disabled={isPending}>
                Cancel
              </Button>
              <Button onClick={() => review()} disabled={isPending}>
                {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
