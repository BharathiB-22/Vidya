// M07 Research Supervision — Guide: Document review panel
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, FileText, Loader2, Download, Clock,
  CheckCircle2, AlertCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getDocument, getDocumentDownloadUrl, reviewDocument } from '@/lib/api/research'
import { useAuth } from '@/lib/auth'
import { addToast } from '@/hooks/useToast'

// ── Score bar ─────────────────────────────────────────────────────────────────

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

// ── Status banner (SUBMITTED / EVALUATING) ────────────────────────────────────

function StatusBanner({ status }: { status: string }) {
  if (status === 'SUBMITTED') {
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-start gap-3">
        <Clock className="h-4 w-4 text-gray-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-gray-700">Awaiting AI Evaluation</p>
          <p className="text-xs text-gray-500 mt-0.5">
            The document has been submitted and is queued for automated evaluation.
            AI scores and the review panel will appear here once evaluation completes.
          </p>
        </div>
      </div>
    )
  }
  if (status === 'EVALUATING') {
    return (
      <div className="rounded-xl border border-blue-100 bg-blue-50 px-5 py-4 flex items-start gap-3">
        <Loader2 className="h-4 w-4 text-blue-500 shrink-0 mt-0.5 animate-spin" />
        <div>
          <p className="text-sm font-medium text-blue-700">AI Evaluation In Progress</p>
          <p className="text-xs text-blue-600 mt-0.5">
            The document is being evaluated. This typically takes 1–3 minutes.
            Refresh the page to check for updated scores.
          </p>
        </div>
      </div>
    )
  }
  return null
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ResearchDocumentPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()
  const { user } = useAuth()

  const isReviewer =
    user?.role === 'GUIDE' || user?.role === 'FACULTY' || user?.role === 'ADMIN'

  const [decision, setDecision]       = useState<'APPROVE' | 'REQUEST_REVISION'>('APPROVE')
  const [comment, setComment]         = useState('')
  const [reviewOpen, setReviewOpen]   = useState(false)
  const [downloading, setDownloading] = useState(false)

  const { data: doc, isLoading, isError } = useQuery({
    queryKey: ['research-doc', id],
    queryFn:  () => getDocument(id!),
    enabled:  !!id,
  })

  const { mutate: review, isPending } = useMutation({
    mutationFn: () => reviewDocument(id!, { decision, guide_comment: comment || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-doc', id] })
      qc.invalidateQueries({ queryKey: ['research-docs-guide'] })
      setReviewOpen(false)
      setComment('')
      addToast('Review submitted.', 'success')
    },
    onError: () => addToast('Failed to submit review. Please try again.', 'error'),
  })

  async function handleDownload() {
    if (!id) return
    setDownloading(true)
    try {
      const { presigned_url } = await getDocumentDownloadUrl(id)
      window.open(presigned_url, '_blank', 'noopener,noreferrer')
    } catch {
      addToast('Could not generate download link. Please try again.', 'error')
    } finally {
      setDownloading(false)
    }
  }

  // Back target: problem detail if doc is loaded, else problems list
  const backPath = doc?.research_problem_id
    ? `/research/problems/${doc.research_problem_id}`
    : '/research/problems'

  // ── Loading ──────────────────────────────────────────────────────────────────

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
    </div>
  )

  if (isError || !doc) return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate('/research/problems')}>
        <ChevronLeft className="h-4 w-4 mr-1" /> Research Proposals
      </Button>
      <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-6 flex gap-3 text-red-700">
        <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-medium text-sm">Document not found</p>
          <p className="text-sm mt-0.5 text-red-600">
            This document may have been removed or you do not have access to it.
          </p>
        </div>
      </div>
    </div>
  )

  const canReview = isReviewer && (doc.status === 'EVALUATED' || doc.status === 'GUIDE_REVIEWED')

  const statusColor: Record<string, string> = {
    SUBMITTED:          'bg-gray-100 text-gray-600',
    EVALUATING:         'bg-blue-100 text-blue-700',
    EVALUATED:          'bg-indigo-100 text-indigo-700',
    GUIDE_REVIEWED:     'bg-yellow-100 text-yellow-700',
    APPROVED:           'bg-green-100 text-green-700',
    REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Header */}
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(backPath)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back to Proposal
      </Button>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <FileText className="h-5 w-5 text-gray-400 shrink-0" />
            <h1 className="text-xl font-bold text-gray-900">
              Research Document v{doc.version}
            </h1>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              statusColor[doc.status] ?? 'bg-gray-100 text-gray-600'
            }`}>
              {doc.status.replace(/_/g, ' ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Submitted {new Date(doc.submitted_at).toLocaleDateString()}
            {doc.file_name && ` · ${doc.file_name}`}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Download button — always visible when file exists */}
          {doc.file_url && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading
                ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                : <Download className="h-4 w-4 mr-1.5" />}
              {downloading ? 'Opening…' : 'Download PDF'}
            </Button>
          )}

          {/* Review button — only for reviewers when doc is evaluated */}
          {canReview && (
            <Button onClick={() => setReviewOpen(true)}>
              Review Document
            </Button>
          )}
        </div>
      </div>

      {/* Status placeholder for not-yet-evaluated docs */}
      <StatusBanner status={doc.status} />

      {/* AI Scores — only when evaluation is complete */}
      {(doc.plagiarism_score !== null || doc.ai_content_score !== null) && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">AI Evaluation Scores</h2>
          <div className="grid grid-cols-2 gap-4">
            <ScoreBar label="Format Compliance"          value={doc.format_score} />
            <ScoreBar label="Clarity"                    value={doc.clarity_score} />
            <ScoreBar
              label="Plagiarism (lower = better)"
              value={doc.plagiarism_score !== null ? 1 - doc.plagiarism_score : null}
            />
            <ScoreBar
              label="AI Content (lower = better)"
              value={doc.ai_content_score !== null ? 1 - doc.ai_content_score : null}
            />
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

      {/* Guide comment from a previous review */}
      {doc.guide_comment && (
        <div className={`rounded-xl border px-5 py-4 space-y-1 ${
          doc.status === 'APPROVED'
            ? 'border-green-200 bg-green-50'
            : 'border-orange-200 bg-orange-50'
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-gray-500 shrink-0" />
            <p className="text-sm font-medium text-gray-700">Guide Feedback</p>
            <span className={`text-xs px-2 py-0.5 rounded font-medium ml-auto ${
              doc.status === 'APPROVED'
                ? 'bg-green-100 text-green-800'
                : 'bg-orange-100 text-orange-800'
            }`}>
              {doc.status.replace(/_/g, ' ')}
            </span>
          </div>
          <p className="text-sm text-gray-600 whitespace-pre-line">{doc.guide_comment}</p>
          {doc.guide_reviewed_at && (
            <p className="text-xs text-gray-400">
              Reviewed {new Date(doc.guide_reviewed_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}

      {/* Review modal — HUMAN GATE 2 */}
      {reviewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Review Document</h2>

            <div className="flex gap-2">
              {([
                { value: 'APPROVE',          label: 'Approve',          cls: 'bg-green-600 border-green-600' },
                { value: 'REQUEST_REVISION', label: 'Request Revision',  cls: 'bg-orange-500 border-orange-500' },
              ] as const).map(({ value, label, cls }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setDecision(value)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    decision === value
                      ? `${cls} text-white`
                      : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">
                Comment{decision === 'REQUEST_REVISION' ? '' : ' (optional)'}
              </label>
              <textarea
                rows={3}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                           focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={
                  decision === 'APPROVE'
                    ? 'Optional feedback for the student…'
                    : 'Explain what needs to be revised…'
                }
              />
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button
                variant="ghost"
                onClick={() => { setReviewOpen(false); setComment('') }}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button
                onClick={() => review()}
                disabled={isPending || (decision === 'REQUEST_REVISION' && !comment.trim())}
              >
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
