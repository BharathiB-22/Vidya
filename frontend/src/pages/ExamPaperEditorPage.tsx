// M08 Exam Setter — Faculty: paper editor with Bloom's compliance panel, submit, and seal
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Loader2, CheckCircle2, AlertTriangle,
  LockKeyhole, Send, Pencil, Trash2, XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getExamPaper, listQuestions, getBloomsReport,
  submitForReview, sealPaper, editQuestion, deleteQuestion,
} from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import type { ExamPaper, ExamQuestion, BloomsComplianceReport, ExamQuestionUpdatePayload } from '@/types/exam'

const BLOOM_COLORS: Record<string, string> = {
  REMEMBER:   'bg-red-100 text-red-700',
  UNDERSTAND: 'bg-orange-100 text-orange-700',
  APPLY:      'bg-yellow-100 text-yellow-700',
  ANALYSE:    'bg-green-100 text-green-700',
  EVALUATE:   'bg-blue-100 text-blue-700',
  CREATE:     'bg-purple-100 text-purple-700',
}

const QTYPE_LABEL: Record<string, string> = {
  MCQ:             'MCQ',
  SHORT_ANSWER:    'Short',
  LONG_ANSWER:     'Long',
  PROBLEM_SOLVING: 'Problem',
}

const TERMINAL_STATUSES = new Set(['GENERATED', 'FAILED', 'SUBMITTED', 'BOARD_APPROVED', 'BOARD_RETURNED', 'SEALED', 'RELEASED'])

export default function ExamPaperEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [setLabel, setSetLabel]       = useState<'A' | 'B'>('A')
  const [sealModal, setSealModal]     = useState(false)
  const [releaseAt, setReleaseAt]     = useState('')
  const [editModal, setEditModal]     = useState<ExamQuestion | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: paper, isLoading: paperLoading, isError: paperError } = useQuery({
    queryKey: ['exam-paper', id],
    queryFn:  () => getExamPaper(id!),
    // Poll every 3 s while generating; stop once a terminal status is reached
    refetchInterval: (query) => {
      const p = query.state.data as ExamPaper | undefined
      return p && TERMINAL_STATUSES.has(p.status) ? false : 3000
    },
  })

  const questionsEnabled = !!(
    paper &&
    !['GENERATING', 'DRAFT', 'FAILED'].includes(paper.status)
  )

  const { data: questions, isLoading: qLoading, isError: qError, error: qErrorObj } = useQuery({
    queryKey: ['exam-questions', id, setLabel],
    queryFn:  () => listQuestions(id!, setLabel),
    enabled:  questionsEnabled,
  })

  // Temporary diagnostic: log questions result to browser console
  if (questions !== undefined) {
    console.log('[M08] questions data count:', questions.length, 'set:', setLabel, 'sample:', questions[0])
  }
  if (qError) {
    console.error('[M08] questions query error:', qErrorObj)
  }

  const { data: bloomsReport } = useQuery({
    queryKey: ['exam-blooms', id],
    queryFn:  () => getBloomsReport(id!),
    enabled:  !!(paper && ['GENERATED','SUBMITTED','BOARD_APPROVED','BOARD_RETURNED'].includes(paper.status)),
  })

  const submitMut = useMutation({
    mutationFn: () => submitForReview(id!),
    onSuccess: () => {
      setSubmitError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err) => setSubmitError(getErrorMessage(err)),
  })

  const sealMut = useMutation({
    mutationFn: (ra: string) => sealPaper(id!, { release_at: new Date(ra).toISOString() }),
    onSuccess: () => {
      setSealModal(false)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (qid: string) => deleteQuestion(id!, qid),
    onSuccess: () => {
      setDeleteError(null)
      qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
    },
    onError: (err) => setDeleteError(getErrorMessage(err)),
  })

  if (paperLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading paper…
      </div>
    )
  }

  if (paperError || !paper) {
    return (
      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
          <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-800 text-sm">Exam paper not found</p>
            <p className="text-sm text-red-700 mt-1">
              This paper may have been deleted or you do not have access to it.
            </p>
            <button
              onClick={() => navigate('/exams')}
              className="text-sm text-red-600 underline mt-2"
            >
              Back to Exam Papers
            </button>
          </div>
        </div>
      </div>
    )
  }

  const isEditable = paper.status === 'GENERATED' || paper.status === 'BOARD_RETURNED'
  const canSubmit  = isEditable
  const canSeal    = paper.status === 'BOARD_APPROVED'

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/exams')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{paper.title}</h1>
          <p className="text-sm text-gray-500">
            {paper.exam_type.replace('_', ' ')} · {paper.total_marks} marks · {paper.duration_mins} min
          </p>
        </div>
        <StatusBadge status={paper.status} />
      </div>

      {/* Generating spinner */}
      {paper.status === 'GENERATING' && (
        <div className="flex items-center gap-3 bg-blue-50 border border-blue-100 rounded-xl p-4 text-blue-700">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <div>
            <p className="font-medium">Generating questions…</p>
            <p className="text-sm text-blue-500">This usually takes 30–90 seconds. Page refreshes automatically.</p>
          </div>
        </div>
      )}

      {/* DRAFT before generation has started (edge case: job dispatched but status not yet flipped) */}
      {paper.status === 'DRAFT' && (
        <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-xl p-4 text-gray-600">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <p className="text-sm">Waiting for generation to start…</p>
        </div>
      )}

      {/* Generation failed */}
      {paper.status === 'FAILED' && (
        <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
          <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-800 text-sm">Question generation failed</p>
            <p className="text-sm text-red-700 mt-1">
              {paper.failure_reason || 'An unexpected error occurred during generation.'}
            </p>
            <p className="text-xs text-red-600 mt-2">
              Go back and create a new exam paper to retry.
            </p>
          </div>
        </div>
      )}

      {/* Board return comment */}
      {paper.status === 'BOARD_RETURNED' && paper.board_comment && (
        <div className="flex gap-3 bg-orange-50 border border-orange-200 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-orange-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-orange-800 text-sm">Board returned this paper</p>
            <p className="text-sm text-orange-700 mt-1">{paper.board_comment}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: Question list */}
        <div className="lg:col-span-2 space-y-4">

          {/* Set switcher — only shown when questions are accessible */}
          {questionsEnabled && (
            <div className="flex gap-2">
              {(['A', 'B'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setSetLabel(s)}
                  className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                    setLabel === s
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                  }`}
                >
                  Set {s}
                </button>
              ))}
            </div>
          )}

          {qLoading && <div className="text-gray-400 text-sm py-4">Loading questions…</div>}

          {/* Questions fetch error — surfaces API/serialization errors that were silent before */}
          {qError && (
            <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-800 text-sm">Could not load questions</p>
                <p className="text-sm text-red-700 mt-1 font-mono">
                  {getErrorMessage(qErrorObj)}
                </p>
                <p className="text-xs text-red-500 mt-1">Check browser console and backend logs for details.</p>
              </div>
            </div>
          )}

          {/* Delete error */}
          {deleteError && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {deleteError}
            </div>
          )}

          {/* Empty state when generation hasn't produced questions yet */}
          {questionsEnabled && !qLoading && questions && questions.length === 0 && (
            <div className="text-gray-500 text-center py-8 border border-dashed border-gray-200 rounded-xl">
              No questions in Set {setLabel}.
            </div>
          )}

          {questions && questions.map((q, idx) => (
            <QuestionCard
              key={q.id}
              question={q}
              index={idx + 1}
              editable={isEditable}
              onEdit={() => setEditModal(q)}
              onDelete={() => {
                setDeleteError(null)
                deleteMut.mutate(q.id)
              }}
            />
          ))}
        </div>

        {/* Right: Bloom's compliance + actions */}
        <div className="space-y-4">
          {bloomsReport && <BloomsPanel report={bloomsReport} />}

          {/* Action buttons */}
          <div className="space-y-2">
            {canSubmit && (
              <div className="space-y-2">
                <Button
                  onClick={() => { setSubmitError(null); submitMut.mutate() }}
                  disabled={submitMut.isPending}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
                >
                  {submitMut.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  Submit for Board Review
                </Button>
                {submitError && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {submitError}
                  </p>
                )}
              </div>
            )}

            {canSeal && (
              <Button
                onClick={() => setSealModal(true)}
                className="w-full bg-purple-600 hover:bg-purple-700 text-white gap-2"
              >
                <LockKeyhole className="w-4 h-4" />
                Seal Paper
              </Button>
            )}

            {paper.status === 'SEALED' && (
              <div className="text-center text-sm text-purple-700 bg-purple-50 rounded-lg p-3 border border-purple-100">
                <LockKeyhole className="w-4 h-4 inline mr-1" />
                Paper is sealed. Questions are inaccessible until{' '}
                {paper.release_at ? new Date(paper.release_at).toLocaleString() : 'release time'}.
              </div>
            )}

            {paper.status === 'RELEASED' && (
              <div className="text-center text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                <CheckCircle2 className="w-4 h-4 inline mr-1" />
                Paper released on {paper.released_at ? new Date(paper.released_at).toLocaleString() : '—'}.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Seal modal */}
      {sealModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <LockKeyhole className="w-5 h-5 text-purple-600" />
              Seal Exam Paper
            </h2>
            <p className="text-sm text-gray-600">
              After sealing, the paper is encrypted and inaccessible to everyone (including you) until the release time.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Release Date &amp; Time *</label>
              <input
                type="datetime-local"
                value={releaseAt}
                onChange={e => setReleaseAt(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setSealModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={!releaseAt || sealMut.isPending}
                onClick={() => sealMut.mutate(releaseAt)}
                className="flex-1 bg-purple-600 hover:bg-purple-700 text-white gap-2"
              >
                {sealMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Confirm Seal
              </Button>
            </div>
            {sealMut.isError && (
              <p className="text-sm text-red-600">
                {getErrorMessage(sealMut.error)}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Edit question modal */}
      {editModal && (
        <EditQuestionModal
          paperId={id!}
          question={editModal}
          onClose={() => { setEditModal(null); qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] }) }}
        />
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
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
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-semibold ${colors[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function QuestionCard({
  question, index, editable, onEdit, onDelete,
}: {
  question: ExamQuestion
  index:    number
  editable: boolean
  onEdit:   () => void
  onDelete: () => void
}) {
  const bloomColor = BLOOM_COLORS[question.bloom_level] ?? 'bg-gray-100 text-gray-600'
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-2 hover:border-gray-300 transition-colors">
      <div className="flex items-start gap-3">
        <span className="text-xs font-bold text-gray-400 mt-0.5 shrink-0">Q{index}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900 leading-snug">{question.question_text}</p>
        </div>
        {editable && (
          <div className="flex gap-1 shrink-0">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit}>
              <Pencil className="w-3.5 h-3.5 text-gray-400" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDelete}>
              <Trash2 className="w-3.5 h-3.5 text-red-400" />
            </Button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 items-center">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bloomColor}`}>
          {question.bloom_level}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 font-medium">
          {QTYPE_LABEL[question.question_type] ?? question.question_type}
        </span>
        <span className="text-xs text-gray-500">Unit {question.unit_number}</span>
        <span className="text-xs text-gray-500 ml-auto">{question.marks} marks</span>
        <span className="text-xs text-gray-400">Set: {question.set_membership.join(', ')}</span>
        {question.is_edited && (
          <span className="text-xs text-orange-500 font-medium">edited</span>
        )}
      </div>
    </div>
  )
}

function BloomsPanel({ report }: { report: BloomsComplianceReport }) {
  const levels = Object.entries(report.actual_dist) as Array<[string, number]>
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Bloom's Compliance</h3>
        {report.compliance_ok ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> OK
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-600 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> {report.violations.length} violation{report.violations.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {levels.map(([lvl, actual]) => {
          const reqDist = report.requested_dist as unknown as Record<string, number>
          const requested = reqDist[lvl] ?? 0
          const isViolation = report.violations.some(v => v.level === lvl.toUpperCase())
          return (
            <div key={lvl} className="space-y-0.5">
              <div className="flex justify-between text-xs text-gray-500">
                <span className={isViolation ? 'text-orange-600 font-medium' : ''}>
                  {lvl.charAt(0) + lvl.slice(1).toLowerCase()}
                </span>
                <span>{actual.toFixed(0)}% <span className="text-gray-300">(req {requested.toFixed(0)}%)</span></span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${isViolation ? 'bg-orange-400' : 'bg-indigo-400'}`}
                  style={{ width: `${Math.min(actual, 100)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function EditQuestionModal({
  paperId, question, onClose,
}: {
  paperId:  string
  question: ExamQuestion
  onClose:  () => void
}) {
  const [text,  setText]  = useState(question.question_text)
  const [marks, setMarks] = useState(question.marks)
  const [bloom, setBloom] = useState(question.bloom_level)

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: (payload: ExamQuestionUpdatePayload) =>
      editQuestion(paperId, question.id, payload),
    onSuccess: onClose,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Pencil className="w-5 h-5 text-indigo-600" />
          Edit Question
        </h2>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Question Text</label>
            <textarea
              rows={4}
              value={text}
              onChange={e => setText(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Marks</label>
              <input
                type="number" min={0.5} step={0.5}
                value={marks}
                onChange={e => setMarks(Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Bloom Level</label>
              <select
                value={bloom}
                onChange={e => setBloom(e.target.value as typeof bloom)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                {['REMEMBER','UNDERSTAND','APPLY','ANALYSE','EVALUATE','CREATE'].map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {isError && (
          <p className="text-sm text-red-600">{getErrorMessage(error)}</p>
        )}
        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={isPending}
            onClick={() => mutate({ question_text: text, marks, bloom_level: bloom })}
          >
            {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
