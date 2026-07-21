import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, Clock, AlertTriangle, CheckCircle2,
  Upload, FileText, X, Loader2, Lock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentQuestionsView } from '@/components/coursework/AssignmentQuestionsView'
import { useStudentAssignments, useMySubmissions, useStudentSubmit } from '@/hooks/coursework'
import {
  requestSubmissionUploadUrl,
  studentGetQuestionPaperUrl,
  uploadFileToPresignedUrl,
} from '@/lib/api/coursework'
import { addToast } from '@/hooks/useToast'
import type { CourseworkAssignment } from '@/types/coursework'

const MAX_SIZE_MB = 50
const DEFAULT_EXTENSIONS = ['pdf', 'doc', 'docx', 'zip']

const CONTENT_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  zip: 'application/zip',
  txt: 'text/plain',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

function extOf(file: File): string {
  const parts = file.name.toLowerCase().split('.')
  return parts.length > 1 ? parts[parts.length - 1] : ''
}

function resolveContentType(file: File): string {
  return CONTENT_TYPES[extOf(file)] ?? file.type
}

function DeadlineWarning({ dueDate, allowLate }: { dueDate: string; allowLate: boolean }) {
  const ms = new Date(dueDate).getTime() - Date.now()
  if (ms < 0) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        {allowLate
          ? 'Deadline has passed. This will be recorded as a late submission.'
          : 'Deadline has passed. Late submissions are not accepted for this assignment.'}
      </div>
    )
  }
  if (ms < 48 * 60 * 60 * 1000) {
    const hrs = Math.floor(ms / (60 * 60 * 1000))
    return (
      <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-3 flex items-start gap-2 text-sm text-orange-700">
        <Clock className="h-4 w-4 shrink-0 mt-0.5" />
        Deadline in ~{hrs}h. Due {new Date(dueDate).toLocaleString()}.
      </div>
    )
  }
  return null
}

export default function StudentAssignmentSubmitPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const assignmentId = id ?? ''

  const { data: assignData } = useStudentAssignments()
  const { data: subData } = useMySubmissions()
  const { mutateAsync: submit, isPending: submitting } = useStudentSubmit(assignmentId)

  const [content, setContent] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitMode, setSubmitMode] = useState<'text' | 'file'>('text')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const assignment: CourseworkAssignment | undefined = assignData?.items.find((a) => a.id === assignmentId)
  const attempts = (subData?.items ?? [])
    .filter((s) => s.assignment_id === assignmentId)
    .sort((a, b) => a.attempt_number - b.attempt_number)
  const latestAttempt = attempts[attempts.length - 1]

  if (!assignment) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4 animate-pulse">
        <div className="h-4 w-24 bg-gray-200 rounded" />
        <div className="h-8 w-64 bg-gray-200 rounded" />
      </div>
    )
  }

  const allowedExtensions = assignment.allowed_file_types?.length ? assignment.allowed_file_types : DEFAULT_EXTENSIONS
  const acceptAttr = allowedExtensions.map((e) => `.${e}`).join(',')
  const maxAttempts = assignment.max_attempts ?? 1
  const atMaxAttempts = attempts.length >= maxAttempts

  function isAcceptedType(file: File): boolean {
    return allowedExtensions.includes(extOf(file))
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!isAcceptedType(file)) {
      addToast(`Only ${allowedExtensions.join(', ').toUpperCase()} files are accepted.`, 'error')
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
      setIsUploading(true)
      try {
        const urlResp = await requestSubmissionUploadUrl({
          // Must be the StorageEntityType enum value 'submission' (same as Labs).
          // 'assignment_submission' is not a valid entity type and made
          // /storage/upload-url reject with 400 INVALID_ENTITY_TYPE.
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
        addToast(err instanceof Error ? err.message : 'File upload failed. Please try again.', 'error')
        setIsUploading(false)
        return
      }
      setIsUploading(false)
    } else {
      if (!content.trim()) return
      await submit({ content_text: content })
      setSubmitted(true)
    }
  }

  if ((submitted || (latestAttempt && atMaxAttempts)) && !isUploading) {
    const sub = latestAttempt
    const isGraded = sub?.status === 'GRADED' || sub?.status === 'RETURNED'
    const pct = isGraded && sub?.marks_obtained != null
      ? Math.round((sub.marks_obtained / assignment.max_marks) * 100)
      : null

    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/assignments')}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          All Assignments
        </Button>

        {isGraded && sub?.marks_obtained != null ? (
          <div className="rounded-xl border border-green-200 bg-green-50 px-6 py-6 text-center">
            <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-600" />
            <h2 className="text-lg font-semibold text-green-900">{assignment.title}</h2>
            <p className="text-sm text-green-600 mt-0.5">{sub.status === 'RETURNED' ? 'Returned by faculty' : 'Graded'}</p>
            <div className="mt-4">
              <span className="text-4xl font-extrabold text-green-800">{sub.marks_obtained}</span>
              <span className="text-lg text-green-600"> / {assignment.max_marks}</span>
            </div>
            <p className="text-base font-semibold text-green-700 mt-1">{pct}%</p>
            {sub.is_late && <p className="text-xs text-orange-600 mt-1">Late submission</p>}
            {sub.feedback && (
              <div className="mt-4 text-left bg-white rounded-lg px-4 py-3 border border-green-100">
                <p className="text-xs font-semibold text-gray-500 mb-1">Faculty feedback</p>
                <p className="text-sm text-gray-700 italic">"{sub.feedback}"</p>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-green-200 bg-green-50 px-6 py-6 text-center">
            <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-500" />
            <h2 className="text-lg font-semibold text-green-900 mb-1">Submission received</h2>
            <p className="text-sm text-green-700">
              Your work has been submitted for <strong>{assignment.title}</strong>. You will be notified once it is graded.
            </p>
            {sub && (
              <div className="mt-3 text-xs text-green-600">
                Submitted {new Date(sub.submitted_at).toLocaleString()}
                {sub.is_late && <span className="ml-2 text-orange-600">· Late</span>}
                {sub.content_url && <span className="ml-2">· File uploaded</span>}
              </div>
            )}
          </div>
        )}

        {attempts.length > 1 && (
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Submission History</span>
            </div>
            <div className="divide-y divide-gray-100">
              {attempts.map((a) => (
                <div key={a.id} className="px-4 py-2.5 flex items-center justify-between text-sm">
                  <span className="text-gray-600">Attempt {a.attempt_number}</span>
                  <span className="text-gray-600">{new Date(a.submitted_at).toLocaleString()}</span>
                  <span className="text-gray-800 font-medium">
                    {a.marks_obtained != null ? `${a.marks_obtained}/${assignment.max_marks}` : a.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {atMaxAttempts && (
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 flex items-center gap-2 text-sm text-gray-600">
            <Lock className="h-4 w-4" />
            Maximum attempts ({maxAttempts}) reached for this assignment.
          </div>
        )}
      </div>
    )
  }

  const isPending = submitting || isUploading
  const canSubmit = isPending
    ? false
    : submitMode === 'file'
    ? selectedFile != null
    : content.trim().length > 0

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/student/assignments')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">{assignment.title}</h1>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700">
            {assignment.assignment_type}
          </span>
          <span className="text-xs text-gray-600">{assignment.max_marks} marks</span>
          {assignment.weightage_percent != null && (
            <span className="text-xs text-gray-600">{assignment.weightage_percent}% weightage</span>
          )}
          {maxAttempts > 1 && (
            <span className="text-xs text-gray-600">Attempt {attempts.length + 1} of {maxAttempts}</span>
          )}
        </div>
      </div>

      <DeadlineWarning dueDate={assignment.due_date} allowLate={assignment.allow_late} />

      {assignment.description && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
            <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Description</span>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{assignment.description}</p>
          </div>
        </div>
      )}

      {assignment.instructions && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-blue-100">
            <span className="text-xs font-semibold text-blue-700 uppercase tracking-wide">Submission Instructions</span>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-blue-900 leading-relaxed whitespace-pre-wrap">{assignment.instructions}</p>
          </div>
        </div>
      )}

      <AssignmentQuestionsView
        questions={assignment.questions ?? []}
        hasQuestionPaper={Boolean(assignment.question_paper_url)}
        fetchQuestionPaperUrl={() => studentGetQuestionPaperUrl(assignmentId)}
      />

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
          <button
            type="button"
            onClick={() => setSubmitMode('text')}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
              submitMode === 'text' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Write response
          </button>
          <button
            type="button"
            onClick={() => setSubmitMode('file')}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
              submitMode === 'file' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Upload file
          </button>
        </div>

        {submitMode === 'text' && (
          <>
            <label className="text-sm font-medium text-gray-700">Your response</label>
            <textarea
              className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-gray-400 resize-y"
              rows={14}
              placeholder="Write your response here…"
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-600">{content.length} characters</p>
              <Button type="submit" disabled={!canSubmit}>
                {submitting ? 'Submitting…' : 'Submit'}
              </Button>
            </div>
          </>
        )}

        {submitMode === 'file' && (
          <div className="space-y-3">
            <label className="text-sm font-medium text-gray-700">
              Upload your submission ({allowedExtensions.join(', ').toUpperCase()} — max {MAX_SIZE_MB} MB)
            </label>

            {!selectedFile ? (
              <label
                htmlFor="submission-file"
                className="flex flex-col items-center justify-center w-full h-36 rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 hover:bg-gray-100 cursor-pointer transition-colors"
              >
                <Upload className="h-8 w-8 text-gray-500 mb-2" />
                <p className="text-sm text-gray-600">Click to select file</p>
                <p className="text-xs text-gray-500 mt-0.5">{allowedExtensions.join(' · ').toUpperCase()}</p>
                <input
                  id="submission-file"
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept={acceptAttr}
                  onChange={handleFileChange}
                />
              </label>
            ) : (
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 flex items-start gap-3">
                <FileText className="h-8 w-8 text-purple-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{selectedFile.name}</p>
                  <p className="text-xs text-gray-600 mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
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
                    className="p-1 rounded hover:bg-gray-100 text-gray-600 hover:text-gray-600"
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
