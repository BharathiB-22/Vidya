import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, Clock, AlertTriangle, CheckCircle2, Circle,
  Upload, FileText, X, Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useStudentAssignments, useMySubmissions } from '@/hooks/labs'
import { useStudentSubmit } from '@/hooks/labs'
import {
  requestSubmissionUploadUrl,
  uploadFileToPresignedUrl,
} from '@/lib/api/labs'
import { addToast } from '@/hooks/useToast'
import type { LabAssignment, LabSubmission, SubmissionStatus } from '@/types/labs'

const TIMELINE_STEPS: { status: SubmissionStatus; label: string; desc: string }[] = [
  { status: 'SUBMITTED',  label: 'Submitted',    desc: 'Your work was received.' },
  { status: 'EVALUATING', label: 'AI Evaluation', desc: 'Automated review in progress.' },
  { status: 'EVALUATED',  label: 'Evaluated',     desc: 'AI scoring complete.' },
  { status: 'REVIEWED',   label: 'Under Review',  desc: 'Faculty is reviewing.' },
  { status: 'RATIFIED',   label: 'Graded',        desc: 'Grade finalised by faculty.' },
]
const STATUS_ORDER: SubmissionStatus[] = ['SUBMITTED', 'EVALUATING', 'EVALUATED', 'REVIEWED', 'RATIFIED']

const ACCEPTED_WRITTEN_EXT = '.pdf,.docx,.zip'
const MAX_SIZE_MB = 50

function resolveContentType(file: File): string {
  // Browsers sometimes report ZIP as application/octet-stream; normalise by extension.
  if (file.name.toLowerCase().endsWith('.zip')) return 'application/zip'
  if (file.name.toLowerCase().endsWith('.docx'))
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  if (file.name.toLowerCase().endsWith('.pdf')) return 'application/pdf'
  return file.type
}

function isAcceptedType(file: File): boolean {
  const ext = file.name.toLowerCase()
  return ext.endsWith('.pdf') || ext.endsWith('.docx') || ext.endsWith('.zip')
}

function mimeLabel(file: File): string {
  const ct = resolveContentType(file)
  if (ct === 'application/pdf') return 'PDF'
  if (ct.includes('wordprocessingml')) return 'DOCX'
  if (ct.includes('zip')) return 'ZIP'
  return ct
}

function EvaluationTimeline({ submission }: { submission: LabSubmission }) {
  const current = STATUS_ORDER.indexOf(submission.status)
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Evaluation Progress</span>
      </div>
      <div className="px-4 py-3 space-y-3">
        {TIMELINE_STEPS.map((step, i) => {
          const done   = i < current
          const active = i === current
          return (
            <div key={step.status} className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0">
                {done ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                ) : active ? (
                  <div className="h-4 w-4 rounded-full border-2 border-blue-500 bg-blue-100" />
                ) : (
                  <Circle className="h-4 w-4 text-gray-200" />
                )}
              </div>
              <div>
                <p className={`text-sm font-medium ${done ? 'text-green-700' : active ? 'text-blue-700' : 'text-gray-300'}`}>
                  {step.label}
                </p>
                <p className={`text-xs ${done || active ? 'text-gray-400' : 'text-gray-200'}`}>
                  {step.desc}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DeadlineWarning({ deadline }: { deadline: string }) {
  const ms = new Date(deadline).getTime() - Date.now()
  if (ms < 0) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        Deadline has passed. Late submissions may not be accepted.
      </div>
    )
  }
  if (ms < 48 * 60 * 60 * 1000) {
    const hrs = Math.floor(ms / (60 * 60 * 1000))
    return (
      <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-3 flex items-start gap-2 text-sm text-orange-700">
        <Clock className="h-4 w-4 shrink-0 mt-0.5" />
        Deadline in ~{hrs}h. Due {new Date(deadline).toLocaleString()}.
      </div>
    )
  }
  return null
}

export default function StudentSubmitPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const assignmentId = id ?? ''

  const { data: assignData } = useStudentAssignments()
  const { data: mySubData }  = useMySubmissions()
  const { mutateAsync: submit, isPending: submitting } = useStudentSubmit(assignmentId)

  // Text submission state
  const [content, setContent] = useState('')
  const [submitted, setSubmitted] = useState(false)

  // File submission state (WRITTEN only)
  const [submitMode, setSubmitMode] = useState<'text' | 'file'>('text')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const assignment: LabAssignment | undefined = assignData?.items.find((a) => a.id === assignmentId)
  const existingSub = mySubData?.items.find((s) => s.assignment_id === assignmentId)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    if (!isAcceptedType(file)) {
      addToast('Only PDF, DOCX, or ZIP files are accepted.', 'error')
      return
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      addToast(`File must be under ${MAX_SIZE_MB} MB.`, 'error')
      return
    }
    setSelectedFile(file)
    setUploadProgress(0)
  }

  function clearFile() {
    setSelectedFile(null)
    setUploadProgress(0)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    if (submitMode === 'file' && selectedFile) {
      // ── File upload path ──────────────────────────────────────────────
      setIsUploading(true)
      try {
        const urlResp = await requestSubmissionUploadUrl({
          entity_type: 'submission',
          entity_id: assignmentId,
          original_filename: selectedFile.name,
          content_type: resolveContentType(selectedFile),
          size_bytes: selectedFile.size,
        })

        await uploadFileToPresignedUrl(urlResp.presigned_url, selectedFile, setUploadProgress)

        await submit({ content_url: urlResp.object_key })
        setSubmitted(true)
      } catch (err) {
        addToast(
          err instanceof Error ? err.message : 'File upload failed. Please try again.',
          'error'
        )
        setIsUploading(false)
        return
      }
      setIsUploading(false)
    } else {
      // ── Inline text path ──────────────────────────────────────────────
      if (!content.trim()) return
      await submit({ content_text: content })
      setSubmitted(true)
    }
  }

  if (!assignment) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4 animate-pulse">
        <div className="h-4 w-24 bg-gray-200 rounded" />
        <div className="h-8 w-64 bg-gray-200 rounded" />
      </div>
    )
  }

  if ((submitted || existingSub) && !isUploading) {
    const sub = existingSub
    const isRatified = sub?.status === 'RATIFIED'
    const hasScore = isRatified && sub?.final_score != null && sub?.graded_max_marks != null
    const pct = hasScore ? Math.round((sub!.final_score! / sub!.graded_max_marks!) * 100) : null
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/labs')}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          All Assignments
        </Button>

        {isRatified && hasScore ? (
          <div className="rounded-xl border border-green-200 bg-green-50 px-6 py-6 text-center">
            <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-600" />
            <h2 className="text-lg font-semibold text-green-900">{assignment.title}</h2>
            <p className="text-sm text-green-600 mt-0.5">Grade finalised</p>
            <div className="mt-4">
              <span className="text-4xl font-extrabold text-green-800">{sub!.final_score}</span>
              <span className="text-lg text-green-600"> / {sub!.graded_max_marks}</span>
            </div>
            <p className="text-base font-semibold text-green-700 mt-1">{pct}%</p>
            {sub?.is_late && <p className="text-xs text-orange-600 mt-1">Late submission</p>}
            <div className="mt-5 flex gap-3 justify-center">
              <Button variant="outline" onClick={() => navigate('/student/labs')}>All Assignments</Button>
              <Button onClick={() => navigate(`/student/submissions/${sub!.id}/result`)}>
                Full Breakdown
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-green-200 bg-green-50 px-6 py-6 text-center">
            <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-500" />
            <h2 className="text-lg font-semibold text-green-900 mb-1">Submission received</h2>
            <p className="text-sm text-green-700">
              Your work has been submitted for <strong>{assignment.title}</strong>.
              You will be notified when evaluation is complete.
            </p>
            {sub && (
              <div className="mt-3 text-xs text-green-600">
                Submitted {new Date(sub.submitted_at).toLocaleString()}
                {sub.is_late && <span className="ml-2 text-orange-600">· Late</span>}
                {sub.content_url && <span className="ml-2">· File uploaded</span>}
              </div>
            )}
            <div className="mt-5 flex gap-3 justify-center">
              <Button variant="outline" onClick={() => navigate('/student/labs')}>All Assignments</Button>
            </div>
          </div>
        )}

        {sub && <EvaluationTimeline submission={sub} />}
      </div>
    )
  }

  const isCode = assignment.submission_type === 'CODE'
  const isPending = submitting || isUploading

  const canSubmit = isPending
    ? false
    : submitMode === 'file'
    ? selectedFile != null
    : content.trim().length > 0

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/labs')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">{assignment.title}</h1>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
            isCode ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
          }`}>
            {assignment.submission_type}
          </span>
          {assignment.max_marks != null && (
            <span className="text-xs text-gray-400">{assignment.max_marks} marks</span>
          )}
          {assignment.ai_not_permitted && (
            <span className="text-xs text-red-600 bg-red-50 px-1.5 py-0.5 rounded">AI not permitted</span>
          )}
        </div>
      </div>

      {assignment.deadline && <DeadlineWarning deadline={assignment.deadline} />}

      {assignment.description && (
        <p className="text-sm text-gray-700 leading-relaxed">{assignment.description}</p>
      )}

      {/* Rubric summary */}
      {assignment.rubric.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
            <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Rubric</span>
          </div>
          <div className="divide-y divide-gray-100">
            {assignment.rubric.map((c) => (
              <div key={c.criterion_id} className="px-4 py-2.5 flex items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">{c.name}</p>
                  <p className="text-xs text-gray-400">{c.description}</p>
                </div>
                <span className="text-xs text-gray-400 shrink-0">{c.max_marks} marks</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Visible test cases (CODE only) */}
      {isCode && (assignment.test_cases?.filter((tc) => !tc.is_hidden) ?? []).length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
            <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Sample Test Cases</span>
          </div>
          <div className="divide-y divide-gray-100">
            {assignment.test_cases.filter((tc) => !tc.is_hidden).map((tc) => (
              <div key={tc.id} className="px-4 py-3">
                <p className="text-xs font-medium text-gray-700 mb-1">{tc.name} — {tc.points} pts</p>
                {tc.stdin && (
                  <pre className="text-xs font-mono bg-gray-50 rounded p-2 text-gray-600 overflow-x-auto">
                    Input: {tc.stdin}
                  </pre>
                )}
                <pre className="text-xs font-mono bg-gray-50 rounded p-2 text-gray-600 mt-1 overflow-x-auto">
                  Expected: {tc.expected_stdout}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Submission form */}
      <form onSubmit={handleSubmit} className="space-y-3">

        {/* Mode switcher — WRITTEN only */}
        {!isCode && (
          <div className="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
            <button
              type="button"
              onClick={() => setSubmitMode('text')}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                submitMode === 'text'
                  ? 'bg-white text-gray-800 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Write response
            </button>
            <button
              type="button"
              onClick={() => setSubmitMode('file')}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                submitMode === 'file'
                  ? 'bg-white text-gray-800 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Upload file
            </button>
          </div>
        )}

        {/* Text input */}
        {(isCode || submitMode === 'text') && (
          <>
            <label className="text-sm font-medium text-gray-700">
              {isCode ? `Your ${assignment.language ?? 'code'} solution` : 'Your response'}
            </label>
            <textarea
              className={`w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-y ${
                isCode ? 'font-mono bg-gray-950 text-green-300 leading-relaxed' : 'leading-relaxed'
              }`}
              rows={isCode ? 20 : 14}
              placeholder={isCode
                ? `# Write your ${assignment.language ?? 'code'} solution here`
                : 'Write your response here…'}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required={!isCode}
            />
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-400">{content.length} characters</p>
              <Button type="submit" disabled={!canSubmit}>
                {submitting ? 'Submitting…' : 'Submit'}
              </Button>
            </div>
          </>
        )}

        {/* File upload input */}
        {!isCode && submitMode === 'file' && (
          <div className="space-y-3">
            <label className="text-sm font-medium text-gray-700">
              Upload your submission (PDF, DOCX, or ZIP — max {MAX_SIZE_MB} MB)
            </label>

            {!selectedFile ? (
              <label
                htmlFor="submission-file"
                className="flex flex-col items-center justify-center w-full h-36 rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 hover:bg-gray-100 cursor-pointer transition-colors"
              >
                <Upload className="h-8 w-8 text-gray-300 mb-2" />
                <p className="text-sm text-gray-400">Click to select file</p>
                <p className="text-xs text-gray-300 mt-0.5">PDF · DOCX · ZIP</p>
                <input
                  id="submission-file"
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept={ACCEPTED_WRITTEN_EXT}
                  onChange={handleFileChange}
                />
              </label>
            ) : (
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 flex items-start gap-3">
                <FileText className="h-8 w-8 text-purple-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{selectedFile.name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {mimeLabel(selectedFile)} · {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </p>

                  {/* Upload progress bar */}
                  {isUploading && (
                    <div className="mt-2">
                      <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all duration-200"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                      <p className="text-xs text-blue-600 mt-1">Uploading… {uploadProgress}%</p>
                    </div>
                  )}
                </div>
                {!isUploading && (
                  <button
                    type="button"
                    onClick={clearFile}
                    className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                    title="Remove file"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}

            <div className="flex justify-end">
              <Button type="submit" disabled={!canSubmit}>
                {isUploading ? (
                  <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" />Uploading…</>
                ) : submitting ? (
                  'Submitting…'
                ) : (
                  'Submit'
                )}
              </Button>
            </div>
          </div>
        )}

      </form>
    </div>
  )
}
