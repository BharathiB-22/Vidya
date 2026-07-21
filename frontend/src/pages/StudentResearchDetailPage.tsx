// M07 Research Supervision — Student proposal detail view + document upload
import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Loader2, AlertCircle, Upload, FileText,
  CheckCircle2, X, ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { studentGetProblem, listActiveGuides, studentListProblemDocuments, studentSubmitDocument } from '@/lib/api/research'
import { generateUploadUrl } from '@/lib/api/storage'
import { uploadFileToPresignedUrl } from '@/lib/api/labs'
import { addToast } from '@/hooks/useToast'
import type { ResearchDocument } from '@/types/research'

// ── constants ─────────────────────────────────────────────────────────────────

const ACCEPTED_EXT = '.pdf,.docx'
const MAX_SIZE_MB   = 50

const STATUS_LABEL: Record<string, string> = {
  DRAFT:              'Draft',
  PENDING_REVIEW:     'Pending Review',
  ACCEPTED:           'Accepted',
  REVISION_REQUESTED: 'Revision Requested',
  REJECTED:           'Rejected',
}

const STATUS_COLOR: Record<string, string> = {
  DRAFT:              'bg-gray-100 text-gray-600',
  PENDING_REVIEW:     'bg-yellow-100 text-yellow-700',
  ACCEPTED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  REJECTED:           'bg-red-100 text-red-600',
}

const DOC_STATUS_COLOR: Record<string, string> = {
  SUBMITTED:          'bg-gray-100 text-gray-600',
  EVALUATING:         'bg-blue-100 text-blue-700',
  EVALUATED:          'bg-indigo-100 text-indigo-700',
  GUIDE_REVIEWED:     'bg-yellow-100 text-yellow-700',
  APPROVED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
}

const DECISION_LABEL: Record<string, string> = {
  ACCEPT: 'Accepted',
  REVISE: 'Revision requested',
  REJECT: 'Rejected',
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function resolveContentType(file: File): string {
  if (file.name.toLowerCase().endsWith('.docx'))
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  if (file.name.toLowerCase().endsWith('.pdf')) return 'application/pdf'
  return file.type || 'application/octet-stream'
}

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase()
  return name.endsWith('.pdf') || name.endsWith('.docx')
}

// ── Document row (read-only list) ─────────────────────────────────────────────

function DocumentRow({ doc }: { doc: ResearchDocument }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <FileText className="h-4 w-4 text-gray-600 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {doc.file_name ?? `Document v${doc.version}`}
          </p>
          <p className="text-xs text-gray-600 mt-0.5">
            Version {doc.version} · Submitted {fmt(doc.submitted_at)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-4">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${DOC_STATUS_COLOR[doc.status] ?? 'bg-gray-100 text-gray-600'}`}>
          {doc.status.replace(/_/g, ' ')}
        </span>
        {doc.guide_comment && (
          <ChevronRight className="h-3.5 w-3.5 text-gray-500" />
        )}
      </div>
    </div>
  )
}

// ── Document upload section ───────────────────────────────────────────────────

function DocumentUploadSection({
  problemId,
  onUploaded,
}: {
  problemId: string
  onUploaded: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileError, setFileError]       = useState<string | null>(null)
  const [uploading, setUploading]       = useState(false)
  const [progress, setProgress]         = useState(0)
  const [submitError, setSubmitError]   = useState<string | null>(null)

  function pickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    setFileError(null)
    setSubmitError(null)
    if (!file) { setSelectedFile(null); return }
    if (!isAccepted(file)) {
      setFileError('Only PDF and DOCX files are accepted.')
      setSelectedFile(null)
      return
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setFileError(`File exceeds the ${MAX_SIZE_MB} MB limit.`)
      setSelectedFile(null)
      return
    }
    setSelectedFile(file)
  }

  async function handleUpload() {
    if (!selectedFile) return
    setUploading(true)
    setProgress(0)
    setSubmitError(null)

    try {
      // 1. Get presigned upload URL from storage service
      const urlResp = await generateUploadUrl({
        entity_type:       'research_doc',
        entity_id:         problemId,
        original_filename: selectedFile.name,
        content_type:      resolveContentType(selectedFile),
        size_bytes:        selectedFile.size,
      })

      // 2. PUT the file directly to S3/MinIO
      await uploadFileToPresignedUrl(urlResp.presigned_url, selectedFile, setProgress)

      // 3. Create the document record linking to the uploaded object
      await studentSubmitDocument({
        research_problem_id: problemId,
        file_url:  urlResp.object_key,
        file_name: selectedFile.name,
      })

      setSelectedFile(null)
      if (fileRef.current) fileRef.current.value = ''
      addToast('Document submitted successfully.', 'success')
      onUploaded()
    } catch (err) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detail = (err as any)?.response?.data?.detail
      const msg = (typeof detail === 'object' ? detail?.message : detail)
        ?? (err instanceof Error ? err.message : null)
        ?? 'Upload failed. Please try again.'
      setSubmitError(msg)
      addToast('Document upload failed.', 'error')
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
        <h2 className="text-sm font-semibold text-gray-700">Upload Research Document</h2>
        <p className="text-xs text-gray-600 mt-0.5">
          PDF or DOCX · Max {MAX_SIZE_MB} MB · New upload creates a new version
        </p>
      </div>

      <div className="px-5 py-4 space-y-3">
        {/* Drop zone / file picker */}
        <div
          className="rounded-lg border-2 border-dashed border-gray-200 px-4 py-6 flex flex-col items-center gap-2 cursor-pointer hover:border-gray-300 transition-colors"
          onClick={() => !uploading && fileRef.current?.click()}
        >
          <Upload className="h-6 w-6 text-gray-500" />
          {selectedFile ? (
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-indigo-500" />
              <span className="text-sm text-gray-700 font-medium">{selectedFile.name}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setSelectedFile(null); if (fileRef.current) fileRef.current.value = '' }}
                disabled={uploading}
                className="text-gray-600 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <p className="text-sm text-gray-600">
              Click to select file
            </p>
          )}
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_EXT}
            className="hidden"
            onChange={pickFile}
            disabled={uploading}
          />
        </div>

        {fileError && (
          <p className="text-sm text-red-600 flex items-center gap-1.5">
            <AlertCircle className="h-4 w-4 shrink-0" />{fileError}
          </p>
        )}

        {/* Upload progress */}
        {uploading && (
          <div className="space-y-1">
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-indigo-600">Uploading… {progress}%</p>
          </div>
        )}

        {submitError && (
          <p className="text-sm text-red-600">{submitError}</p>
        )}

        <Button
          className="w-full"
          disabled={!selectedFile || uploading}
          onClick={handleUpload}
        >
          {uploading ? (
            <><Loader2 className="h-4 w-4 animate-spin mr-1.5" />Uploading…</>
          ) : (
            <><Upload className="h-4 w-4 mr-1.5" />Submit Document</>
          )}
        </Button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function StudentResearchDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  // All query hooks unconditionally at top
  const {
    data: problem,
    isLoading: problemLoading,
    isError: problemError,
    error: problemErr,
  } = useQuery({
    queryKey: ['student-problem', id],
    queryFn: () => studentGetProblem(id!),
    enabled: !!id,
    retry: 1,
  })

  const { data: guides = [] } = useQuery({
    queryKey: ['research-guides'],
    queryFn: listActiveGuides,
    staleTime: 60_000,
  })

  const { data: docsData, refetch: refetchDocs } = useQuery({
    queryKey: ['student-problem-docs', id],
    queryFn: () => studentListProblemDocuments(id!),
    enabled: !!id && problem?.status === 'ACCEPTED',
    staleTime: 15_000,
  })

  // Derived data — all hooks are above
  const guide = guides.find((g) => g.id === problem?.guide_user_id)
  const docs  = docsData?.items ?? []
  const isAcceptedProposal = problem?.status === 'ACCEPTED'

  function guideDisplay(): string {
    if (guide) {
      return guide.identifier
        ? `${guide.identifier} — ${guide.full_name}`
        : guide.full_name
    }
    if (problem?.guide_user_id) {
      return `ID: ${problem.guide_user_id.slice(0, 8)}…`
    }
    return '—'
  }

  // ── Loading state ──────────────────────────────────────────────────────────

  if (problemLoading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 flex items-center gap-3 text-gray-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading proposal…</span>
      </div>
    )
  }

  // ── Error / not found state ────────────────────────────────────────────────

  if (problemError || !problem) {
    const msg = (() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const d = (problemErr as any)?.response?.data
        return d?.message ?? d?.detail?.message ?? 'Failed to load proposal.'
      } catch {
        return 'Failed to load proposal.'
      }
    })()
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/research')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-6 flex gap-3 text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm">Proposal not found</p>
            <p className="text-sm mt-0.5 text-red-600">{msg}</p>
          </div>
        </div>
      </div>
    )
  }

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">

      {/* Header */}
      <div className="space-y-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/research')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> My Research
        </Button>
        <div className="flex items-start gap-3 flex-wrap">
          <h1 className="text-xl font-bold text-gray-900 flex-1">{problem.title}</h1>
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium flex-shrink-0 ${STATUS_COLOR[problem.status] ?? 'bg-gray-100 text-gray-600'}`}>
            {STATUS_LABEL[problem.status] ?? problem.status}
          </span>
        </div>
      </div>

      {/* Accepted callout */}
      {isAcceptedProposal && (
        <div className="rounded-xl border border-green-200 bg-green-50 px-5 py-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
          <p className="text-sm text-green-800">
            Your proposal is accepted. Upload your research document below to begin the next stage.
          </p>
        </div>
      )}

      {/* Meta row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Submitted</p>
          <p className="text-gray-800 mt-0.5">{fmt(problem.created_at)}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Last Updated</p>
          <p className="text-gray-800 mt-0.5">{fmt(problem.updated_at)}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Guide</p>
          <p className="text-gray-800 mt-0.5 truncate">{guideDisplay()}</p>
        </div>
        {problem.decided_at && (
          <div className="rounded-lg bg-gray-50 px-3 py-2">
            <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Decided</p>
            <p className="text-gray-800 mt-0.5">{fmt(problem.decided_at)}</p>
          </div>
        )}
      </div>

      {/* Abstract */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-1">
        <h2 className="text-sm font-semibold text-gray-700">Abstract</h2>
        <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">{problem.abstract}</p>
      </div>

      {/* Research questions */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-3">
        <h2 className="text-sm font-semibold text-gray-700">
          Research Questions ({problem.research_questions.length})
        </h2>
        <ol className="space-y-2 list-decimal list-inside">
          {problem.research_questions.map((rq, i) => (
            <li key={i} className="text-sm text-gray-600">{rq.question}</li>
          ))}
        </ol>
      </div>

      {/* Guide decision & note */}
      {(problem.guide_decision || problem.guide_note) && (
        <div className={`rounded-xl border px-5 py-4 space-y-1 ${
          problem.guide_decision === 'ACCEPT'
            ? 'border-green-200 bg-green-50'
            : problem.guide_decision === 'REJECT'
            ? 'border-red-200 bg-red-50'
            : 'border-orange-200 bg-orange-50'
        }`}>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-gray-700">Guide Review</h2>
            {problem.guide_decision && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                problem.guide_decision === 'ACCEPT'
                  ? 'bg-green-100 text-green-800'
                  : problem.guide_decision === 'REJECT'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-orange-100 text-orange-800'
              }`}>
                {DECISION_LABEL[problem.guide_decision] ?? problem.guide_decision}
              </span>
            )}
          </div>
          {problem.guide_note && (
            <p className="text-sm text-gray-600 whitespace-pre-line">{problem.guide_note}</p>
          )}
        </div>
      )}

      {/* AI evaluation summary (shown when available) */}
      {(problem.novelty_score !== null || problem.ai_recommendation) && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 space-y-3">
          <h2 className="text-sm font-semibold text-indigo-800">AI Evaluation</h2>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { label: 'Novelty', value: problem.novelty_score },
              { label: 'Feasibility', value: problem.feasibility_score },
              { label: 'Clarity', value: problem.clarity_score },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-white/60 px-2 py-2">
                <p className="text-xs text-indigo-500">{label}</p>
                <p className="text-lg font-bold text-indigo-900">
                  {value !== null && value !== undefined ? value.toFixed(1) : '—'}
                </p>
              </div>
            ))}
          </div>
          {problem.ai_reasoning && (
            <p className="text-xs text-indigo-700 leading-relaxed">{problem.ai_reasoning}</p>
          )}
        </div>
      )}

      {/* ── Document section — only for ACCEPTED proposals ───────────────── */}
      {isAcceptedProposal && (
        <>
          {/* Existing documents */}
          {docs.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
                <h2 className="text-sm font-semibold text-gray-700">
                  Submitted Documents
                  <span className="ml-1.5 text-xs font-normal text-gray-600">({docs.length})</span>
                </h2>
              </div>
              <div>
                {docs.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} />
                ))}
              </div>
            </div>
          )}

          {/* Guide feedback on latest document */}
          {docs.length > 0 && docs[docs.length - 1].guide_comment && (
            <div className={`rounded-xl border px-5 py-4 space-y-1 ${
              docs[docs.length - 1].status === 'APPROVED'
                ? 'border-green-200 bg-green-50'
                : 'border-orange-200 bg-orange-50'
            }`}>
              <h2 className="text-sm font-semibold text-gray-700">
                Guide Feedback on Latest Document
              </h2>
              <p className="text-sm text-gray-600 whitespace-pre-line">
                {docs[docs.length - 1].guide_comment}
              </p>
            </div>
          )}

          {/* Upload new document */}
          <DocumentUploadSection
            problemId={problem.id}
            onUploaded={() => {
              qc.invalidateQueries({ queryKey: ['student-problem-docs', id] })
              refetchDocs()
            }}
          />
        </>
      )}

    </div>
  )
}
