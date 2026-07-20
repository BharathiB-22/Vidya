import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2, Upload, FileText, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAssignment, useCreateAssignment, useUpdateAssignment } from '@/hooks/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import {
  listEligibleEvaluators,
  requestSubmissionUploadUrl,
  uploadFileToPresignedUrl,
  updateAssignment,
} from '@/lib/api/coursework'
import type { CourseworkAssignment, CourseworkQuestion, CourseworkType } from '@/types/coursework'

const TYPE_OPTIONS: Array<{ value: CourseworkType; label: string }> = [
  { value: 'ESSAY', label: 'Essay' },
  { value: 'CASE_STUDY', label: 'Case Study' },
  { value: 'REPORT', label: 'Report' },
  { value: 'HOMEWORK', label: 'Homework' },
  { value: 'OTHER', label: 'Other' },
]

const FILE_TYPE_OPTIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'zip', 'txt']

// Question paper fallback: uploaded through the generic storage flow under the
// existing `faculty_note` entity type, whose whitelist already permits PDF/DOCX.
const PAPER_MAX_SIZE_MB = 50
const PAPER_MIME: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

/** Local, editable shape for one question row — marks kept as a string so the
 *  input can be cleared without snapping back to 0. */
interface QuestionDraft {
  question_text: string
  marks: string
  notes: string
}

function extOf(name: string): string {
  const parts = name.toLowerCase().split('.')
  return parts.length > 1 ? parts[parts.length - 1] : ''
}

function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export interface AssignmentFormProps {
  /** Omit to create a new assignment; pass an id to edit an existing one. */
  assignmentId?: string
  /** Only used when creating. */
  syllabusId?: string
  onCreated?: (assignment: CourseworkAssignment) => void
  onUpdated?: (assignment: CourseworkAssignment) => void
}

export function AssignmentForm({ assignmentId, syllabusId, onCreated, onUpdated }: AssignmentFormProps) {
  const isEdit = Boolean(assignmentId)

  const { data: existing } = useAssignment(assignmentId ?? '')
  const create = useCreateAssignment()
  const update = useUpdateAssignment(assignmentId ?? '')

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [assignmentType, setAssignmentType] = useState<CourseworkType>('ESSAY')
  const [maxMarks, setMaxMarks] = useState(100)
  const [weightagePercent, setWeightagePercent] = useState<string>('')
  const [dueDate, setDueDate] = useState('')
  const [allowLate, setAllowLate] = useState(true)
  const [latePenaltyPercent, setLatePenaltyPercent] = useState<string>('')
  const [maxAttempts, setMaxAttempts] = useState(1)
  const [allowedFileTypes, setAllowedFileTypes] = useState<string[]>(['pdf', 'docx'])
  const [evaluatorIds, setEvaluatorIds] = useState<string[]>([])

  // Question builder + its upload fallback. `questionPaperUrl` is an object key
  // already stored on the assignment; `questionPaperFile` is a newly picked file
  // not yet uploaded. Only used while there are no structured questions.
  const [questions, setQuestions] = useState<QuestionDraft[]>([])
  const [questionPaperUrl, setQuestionPaperUrl] = useState<string | null>(null)
  const [questionPaperFile, setQuestionPaperFile] = useState<File | null>(null)
  const [uploadingPaper, setUploadingPaper] = useState(false)

  // Who holds the EVALUATOR responsibility. Nominating one here is not allocating
  // it: each student submission raises its own work item through the existing
  // evaluation engine, and the department can still override.
  const { data: evaluators = [], isLoading: evaluatorsLoading } = useQuery({
    queryKey: ['coursework-evaluators'],
    queryFn: listEligibleEvaluators,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (existing) {
      setTitle(existing.title)
      setDescription(existing.description ?? '')
      setInstructions(existing.instructions ?? '')
      setAssignmentType(existing.assignment_type)
      setMaxMarks(existing.max_marks)
      setWeightagePercent(existing.weightage_percent != null ? String(existing.weightage_percent) : '')
      setDueDate(toLocalInputValue(existing.due_date))
      setAllowLate(existing.allow_late)
      setLatePenaltyPercent(existing.late_penalty_percent != null ? String(existing.late_penalty_percent) : '')
      setMaxAttempts(existing.max_attempts)
      setAllowedFileTypes(existing.allowed_file_types ?? ['pdf', 'docx'])
      setEvaluatorIds(existing.evaluator_user_ids ?? [])
      setQuestions(
        (existing.questions ?? []).map((q) => ({
          question_text: q.question_text,
          marks: String(q.marks),
          notes: q.notes ?? '',
        })),
      )
      setQuestionPaperUrl(existing.question_paper_url ?? null)
      setQuestionPaperFile(null)
    }
  }, [existing])

  function toggleFileType(ext: string) {
    setAllowedFileTypes((prev) => (prev.includes(ext) ? prev.filter((e) => e !== ext) : [...prev, ext]))
  }

  function toggleEvaluator(id: string) {
    setEvaluatorIds((prev) => (prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]))
  }

  // ── Question builder actions ────────────────────────────────────────────────
  function addQuestion() {
    setQuestions((prev) => [...prev, { question_text: '', marks: '', notes: '' }])
  }
  function removeQuestion(index: number) {
    setQuestions((prev) => prev.filter((_, i) => i !== index))
  }
  function patchQuestion(index: number, patch: Partial<QuestionDraft>) {
    setQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, ...patch } : q)))
  }

  function handlePaperChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const ext = extOf(file.name)
    if (ext !== 'pdf' && ext !== 'docx') {
      addToast('Only PDF or DOCX files are accepted for the question paper.', 'error')
      return
    }
    if (file.size > PAPER_MAX_SIZE_MB * 1024 * 1024) {
      addToast(`Question paper must be under ${PAPER_MAX_SIZE_MB} MB.`, 'error')
      return
    }
    setQuestionPaperFile(file)
    e.target.value = ''
  }

  async function uploadQuestionPaper(entityId: string, file: File): Promise<string> {
    const resp = await requestSubmissionUploadUrl({
      entity_type: 'faculty_note',
      entity_id: entityId,
      original_filename: file.name,
      content_type: PAPER_MIME[extOf(file.name)] ?? file.type,
      size_bytes: file.size,
    })
    await uploadFileToPresignedUrl(resp.presigned_url, file)
    return resp.object_key
  }

  const questionsTotal = questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0)
  const marksMatch = questions.length === 0 || Math.abs(questionsTotal - maxMarks) < 0.01

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    // Validate the question builder before anything is sent.
    if (questions.length > 0) {
      for (let i = 0; i < questions.length; i++) {
        const q = questions[i]
        if (!q.question_text.trim()) {
          addToast(`Question ${i + 1} needs text.`, 'error')
          return
        }
        if (!(Number(q.marks) > 0)) {
          addToast(`Question ${i + 1} needs marks greater than 0.`, 'error')
          return
        }
      }
      if (!marksMatch) {
        addToast(`Question marks total ${questionsTotal}, which must equal Max Marks (${maxMarks}).`, 'error')
        return
      }
    }

    const questionsPayload: CourseworkQuestion[] = questions.map((q, i) => ({
      question_number: i + 1,
      question_text: q.question_text.trim(),
      marks: Number(q.marks),
      notes: q.notes.trim() || null,
    }))

    const payload = {
      title,
      description: description || undefined,
      instructions: instructions || undefined,
      assignment_type: assignmentType,
      max_marks: maxMarks,
      weightage_percent: weightagePercent ? Number(weightagePercent) : undefined,
      due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
      allow_late: allowLate,
      late_penalty_percent: latePenaltyPercent ? Number(latePenaltyPercent) : undefined,
      max_attempts: maxAttempts,
      allowed_file_types: allowedFileTypes,
      evaluator_user_ids: evaluatorIds,
      questions: questionsPayload,
    }

    try {
      if (isEdit) {
        // Questions win over a paper. With questions present the paper is cleared;
        // otherwise a freshly picked file is uploaded, or the existing key kept.
        let paperKey: string | null = null
        if (questions.length === 0) {
          if (questionPaperFile) {
            setUploadingPaper(true)
            paperKey = await uploadQuestionPaper(assignmentId ?? '', questionPaperFile)
          } else {
            paperKey = questionPaperUrl
          }
        }
        const updated = await update.mutateAsync({ ...payload, question_paper_url: paperKey })
        addToast('Assignment updated.', 'success')
        onUpdated?.(updated)
      } else {
        const created = await create.mutateAsync({ ...payload, due_date: payload.due_date!, syllabus_id: syllabusId })
        // The draft exists now, so the paper can be uploaded against its id and
        // saved with a follow-up update (only DRAFT assignments accept edits).
        if (questions.length === 0 && questionPaperFile) {
          setUploadingPaper(true)
          const paperKey = await uploadQuestionPaper(created.id, questionPaperFile)
          await updateAssignment(created.id, { question_paper_url: paperKey })
        }
        addToast('Assignment created as draft.', 'success')
        onCreated?.(created)
      }
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    } finally {
      setUploadingPaper(false)
    }
  }

  const saving = create.isPending || update.isPending || uploadingPaper

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{isEdit ? 'Edit Assignment' : 'New Assignment'}</h1>
        {isEdit && existing?.status !== 'DRAFT' && (
          <p className="text-sm text-orange-600 mt-1">Only draft assignments can be edited.</p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700">Title</label>
          <input
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Description</label>
          <textarea
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Submission Instructions</label>
          <textarea
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            rows={3}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </div>

        {/* Assignment Questions — the builder, or a question-paper upload fallback. */}
        <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Assignment Questions</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Add the questions students must answer — their marks must add up to Max Marks.
                Or leave this empty and upload a question paper instead.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={addQuestion}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Question
            </Button>
          </div>

          {questions.length === 0 ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-500">Question Paper (optional — .pdf or .docx)</label>
              {questionPaperFile ? (
                <div className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2">
                  <FileText className="h-4 w-4 text-purple-400 shrink-0" />
                  <span className="text-sm text-gray-700 flex-1 truncate">{questionPaperFile.name}</span>
                  <button
                    type="button"
                    onClick={() => setQuestionPaperFile(null)}
                    className="p-1 rounded hover:bg-gray-100 text-gray-500"
                    title="Remove file"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : questionPaperUrl ? (
                <div className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2">
                  <FileText className="h-4 w-4 text-purple-400 shrink-0" />
                  <span className="text-sm text-gray-700 flex-1 truncate">Question paper attached</span>
                  <button
                    type="button"
                    onClick={() => setQuestionPaperUrl(null)}
                    className="p-1 rounded hover:bg-gray-100 text-gray-500"
                    title="Remove question paper"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <label
                  htmlFor="question-paper-file"
                  className="flex flex-col items-center justify-center w-full h-28 rounded-lg border-2 border-dashed border-gray-200 bg-gray-50 hover:bg-gray-100 cursor-pointer transition-colors"
                >
                  <Upload className="h-6 w-6 text-gray-400 mb-1" />
                  <p className="text-xs text-gray-500">Click to upload a question paper</p>
                  <p className="text-[11px] text-gray-400 mt-0.5">PDF or DOCX · max {PAPER_MAX_SIZE_MB} MB</p>
                  <input
                    id="question-paper-file"
                    type="file"
                    accept=".pdf,.docx"
                    className="hidden"
                    onChange={handlePaperChange}
                  />
                </label>
              )}
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {questions.map((q, i) => (
                  <div key={i} className="rounded-lg border border-gray-200 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-gray-500">Question {i + 1}</span>
                      <button
                        type="button"
                        onClick={() => removeQuestion(i)}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"
                        title="Delete question"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    <textarea
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                      rows={2}
                      placeholder="Question text"
                      value={q.question_text}
                      onChange={(e) => patchQuestion(i, { question_text: e.target.value })}
                    />
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="text-xs font-medium text-gray-500">Marks</label>
                        <input
                          type="number"
                          min={0}
                          step="0.5"
                          className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                          value={q.marks}
                          onChange={(e) => patchQuestion(i, { marks: e.target.value })}
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs font-medium text-gray-500">Notes / Instructions (optional)</label>
                        <input
                          className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                          value={q.notes}
                          onChange={(e) => patchQuestion(i, { notes: e.target.value })}
                          placeholder="e.g. Answer in ~200 words"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                  marksMatch ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'
                }`}
              >
                <span>Total question marks</span>
                <span className="font-semibold">
                  {questionsTotal} / {maxMarks}
                  {!marksMatch && ' — must equal Max Marks'}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Type</label>
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={assignmentType}
              onChange={(e) => setAssignmentType(e.target.value as CourseworkType)}
            >
              {TYPE_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Max Marks</label>
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={maxMarks}
              onChange={(e) => setMaxMarks(Number(e.target.value))}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Weightage % (Internal Assessment)</label>
            <input
              type="number"
              min={0}
              max={100}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={weightagePercent}
              onChange={(e) => setWeightagePercent(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Due Date</label>
            <input
              type="datetime-local"
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 items-end">
          <div className="flex items-center gap-2">
            <input
              id="allow-late"
              type="checkbox"
              checked={allowLate}
              onChange={(e) => setAllowLate(e.target.checked)}
            />
            <label htmlFor="allow-late" className="text-sm font-medium text-gray-700">Allow late submissions</label>
          </div>
          {allowLate && (
            <div>
              <label className="text-sm font-medium text-gray-700">Late Penalty %</label>
              <input
                type="number"
                min={0}
                max={100}
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                value={latePenaltyPercent}
                onChange={(e) => setLatePenaltyPercent(e.target.value)}
                placeholder="Optional"
              />
            </div>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Maximum Attempts</label>
          <input
            type="number"
            min={1}
            className="mt-1 w-32 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={maxAttempts}
            onChange={(e) => setMaxAttempts(Number(e.target.value))}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Allowed File Types</label>
          <div className="mt-2 flex gap-2 flex-wrap">
            {FILE_TYPE_OPTIONS.map((ext) => (
              <button
                key={ext}
                type="button"
                onClick={() => toggleFileType(ext)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium border transition-colors ${
                  allowedFileTypes.includes(ext)
                    ? 'bg-gray-900 text-white border-gray-900'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
              >
                .{ext}
              </button>
            ))}
          </div>
        </div>

        {/* Evaluators — who marks this coursework. */}
        <div>
          <label className="text-sm font-medium text-gray-700">Evaluators</label>
          <p className="text-xs text-gray-500 mt-0.5">
            Each student's submission is routed to one of these automatically. Pick
            several to share the load — submissions are spread evenly, and a
            student's re-attempt stays with the same evaluator. Leave empty to let
            the department allocate by hand.
          </p>
          {evaluatorsLoading ? (
            <p className="mt-2 text-sm text-gray-400">Loading evaluators…</p>
          ) : evaluators.length === 0 ? (
            <p className="mt-2 text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
              Nobody currently holds the Evaluator responsibility. The department
              will need to allocate this coursework by hand.
            </p>
          ) : (
            <div className="mt-2 flex gap-2 flex-wrap">
              {evaluators.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => toggleEvaluator(ev.id)}
                  title={ev.email ?? undefined}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium border transition-colors ${
                    evaluatorIds.includes(ev.id)
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  {ev.full_name || ev.email || ev.id.slice(0, 8)}
                </button>
              ))}
            </div>
          )}
          {evaluatorIds.length > 1 && (
            <p className="mt-1.5 text-xs text-gray-500">
              {evaluatorIds.length} evaluators — submissions will be split between them.
            </p>
          )}
        </div>

        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Draft'}
          </Button>
        </div>
      </form>
    </div>
  )
}
