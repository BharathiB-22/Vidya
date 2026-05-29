// M08 Exam Setter — Faculty: paper editor with coverage panels, section grouping, regenerate
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Loader2, CheckCircle2, AlertTriangle,
  LockKeyhole, Send, Pencil, Trash2, XCircle, RefreshCw,
  BookOpen, BarChart2, ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getExamPaper, listQuestions, getBloomsReport,
  submitForReview, sealPaper, editQuestion, deleteQuestion,
  facultyApprovePaper, regenerateQuestion,
} from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type {
  ExamPaper, ExamQuestion, BloomsComplianceReport,
  ExamQuestionUpdatePayload, SectionConfig,
  CoCoverageEntry, UnitCoverageEntry,
} from '@/types/exam'

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

const TERMINAL_STATUSES = new Set([
  'GENERATED', 'FAILED', 'SUBMITTED', 'BOARD_APPROVED', 'BOARD_RETURNED', 'SEALED', 'RELEASED',
])

export default function ExamPaperEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { user } = useAuth()

  const [setLabel,      setSetLabel]      = useState<'A' | 'B'>('A')
  const [sealModal,     setSealModal]     = useState(false)
  const [releaseAt,     setReleaseAt]     = useState('')
  const [editModal,     setEditModal]     = useState<ExamQuestion | null>(null)
  const [submitError,   setSubmitError]   = useState<string | null>(null)
  const [deleteError,   setDeleteError]   = useState<string | null>(null)
  const [approveError,  setApproveError]  = useState<string | null>(null)
  const [regenQueued,   setRegenQueued]   = useState<Set<string>>(new Set())
  const [regenError,    setRegenError]    = useState<string | null>(null)

  const isBoard   = user?.role === 'BOARD'   || user?.role === 'ADMIN'
  const isFaculty = user?.role === 'FACULTY' || user?.role === 'ADMIN'

  const { data: paper, isLoading: paperLoading, isError: paperError } = useQuery({
    queryKey: ['exam-paper', id],
    queryFn:  () => getExamPaper(id!),
    refetchInterval: (query) => {
      const p = query.state.data as ExamPaper | undefined
      return p && TERMINAL_STATUSES.has(p.status) ? false : 3000
    },
  })

  const questionsEnabled = !!(
    paper && !['GENERATING', 'DRAFT', 'FAILED'].includes(paper.status)
  )

  const hasRegenInFlight = regenQueued.size > 0

  const { data: questions, isLoading: qLoading, isError: qError, error: qErrorObj } = useQuery({
    queryKey: ['exam-questions', id, setLabel],
    queryFn:  () => listQuestions(id!, setLabel),
    enabled:  questionsEnabled,
    refetchInterval: hasRegenInFlight ? 3000 : false,
  })

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

  const approveMut = useMutation({
    mutationFn: () => facultyApprovePaper(id!),
    onSuccess: () => {
      setApproveError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err) => setApproveError(getErrorMessage(err)),
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

  async function handleRegenerate(questionId: string) {
    setRegenError(null)
    setRegenQueued(prev => new Set(prev).add(questionId))
    try {
      await regenerateQuestion(id!, questionId)
      // Questions query auto-refetches every 3s while regenQueued has entries.
      // Clear the queued flag after 30s maximum.
      setTimeout(() => {
        setRegenQueued(prev => {
          const next = new Set(prev)
          next.delete(questionId)
          return next
        })
        qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
      }, 30_000)
    } catch (err) {
      setRegenQueued(prev => {
        const next = new Set(prev)
        next.delete(questionId)
        return next
      })
      setRegenError(getErrorMessage(err))
    }
  }

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

  const isEditable       = paper.status === 'GENERATED' || paper.status === 'BOARD_RETURNED'
  const isInternalPaper  = paper.exam_workflow === 'INTERNAL'

  // Faculty approve: INTERNAL papers that are GENERATED (skips board)
  const canFacultyApprove = isInternalPaper && paper.status === 'GENERATED' && isFaculty

  // Submit for board review: BOARD_EXAM papers that are editable
  const canSubmit = isEditable && !isInternalPaper && isFaculty

  // Seal: BOARD/ADMIN only, when paper is BOARD_APPROVED
  const canSeal = paper.status === 'BOARD_APPROVED' && isBoard

  // Section grouping: only when paper has section_config
  const hasSections = !!(paper.section_config && paper.section_config.length > 0)

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
            {paper.exam_type.replace('_', ' ')}
            {' · '}
            <span className={`font-medium ${isInternalPaper ? 'text-amber-600' : 'text-indigo-600'}`}>
              {isInternalPaper ? 'Internal Assessment' : 'Board Exam'}
            </span>
            {' · '}{paper.total_marks} marks · {paper.duration_mins} min
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

      {paper.status === 'DRAFT' && (
        <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-xl p-4 text-gray-600">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <p className="text-sm">Waiting for generation to start…</p>
        </div>
      )}

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

      {paper.status === 'BOARD_RETURNED' && paper.board_comment && (
        <div className="flex gap-3 bg-orange-50 border border-orange-200 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-orange-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-orange-800 text-sm">Board returned this paper</p>
            <p className="text-sm text-orange-700 mt-1">{paper.board_comment}</p>
          </div>
        </div>
      )}

      {regenError && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {regenError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: Question list */}
        <div className="lg:col-span-2 space-y-4">

          {/* Set switcher */}
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

          {qError && (
            <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-800 text-sm">Could not load questions</p>
                <p className="text-sm text-red-700 mt-1 font-mono">
                  {getErrorMessage(qErrorObj)}
                </p>
              </div>
            </div>
          )}

          {deleteError && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {deleteError}
            </div>
          )}

          {questionsEnabled && !qLoading && questions && questions.length === 0 && (
            <div className="text-gray-500 text-center py-8 border border-dashed border-gray-200 rounded-xl">
              No questions in Set {setLabel}.
            </div>
          )}

          {questions && (
            hasSections
              ? <SectionedQuestionList
                  questions={questions}
                  sectionConfig={paper.section_config!}
                  editable={isEditable}
                  regenQueued={regenQueued}
                  onEdit={setEditModal}
                  onDelete={(qid) => { setDeleteError(null); deleteMut.mutate(qid) }}
                  onRegenerate={handleRegenerate}
                />
              : <FlatQuestionList
                  questions={questions}
                  editable={isEditable}
                  regenQueued={regenQueued}
                  onEdit={setEditModal}
                  onDelete={(qid) => { setDeleteError(null); deleteMut.mutate(qid) }}
                  onRegenerate={handleRegenerate}
                />
          )}
        </div>

        {/* Right: Coverage panels + Bloom's + actions */}
        <div className="space-y-4">

          {/* CO Coverage */}
          {paper.co_coverage_report && paper.co_coverage_report.length > 0 && (
            <CoCoveragePanel report={paper.co_coverage_report} />
          )}

          {/* Unit Coverage */}
          {paper.unit_coverage_report && paper.unit_coverage_report.length > 0 && (
            <UnitCoveragePanel report={paper.unit_coverage_report} />
          )}

          {/* Bloom's compliance */}
          {bloomsReport && <BloomsPanel report={bloomsReport} />}

          {/* Action buttons */}
          <div className="space-y-2">

            {/* INTERNAL workflow: Faculty Approve (skips board) */}
            {canFacultyApprove && (
              <div className="space-y-2">
                <Button
                  onClick={() => { setApproveError(null); approveMut.mutate() }}
                  disabled={approveMut.isPending}
                  className="w-full bg-green-600 hover:bg-green-700 text-white gap-2"
                >
                  {approveMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <ShieldCheck className="w-4 h-4" />
                  }
                  Approve Paper
                </Button>
                <p className="text-xs text-gray-500 text-center">
                  Internal Assessment — no Board review required
                </p>
                {approveError && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {approveError}
                  </p>
                )}
              </div>
            )}

            {/* BOARD_EXAM workflow: Submit for board review */}
            {canSubmit && (
              <div className="space-y-2">
                <Button
                  onClick={() => { setSubmitError(null); submitMut.mutate() }}
                  disabled={submitMut.isPending}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
                >
                  {submitMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Send className="w-4 h-4" />
                  }
                  Submit for Board Review
                </Button>
                {submitError && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {submitError}
                  </p>
                )}
              </div>
            )}

            {/* Seal: BOARD/ADMIN only */}
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
                Paper sealed. Available from{' '}
                {paper.release_at ? new Date(paper.release_at).toLocaleString() : '—'}.
              </div>
            )}

            {paper.status === 'RELEASED' && (
              <div className="text-center text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                <CheckCircle2 className="w-4 h-4 inline mr-1" />
                Released on {paper.released_at ? new Date(paper.released_at).toLocaleString() : '—'}.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Seal modal — rendered for BOARD/ADMIN only (canSeal is already gated) */}
      {sealModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <LockKeyhole className="w-5 h-5 text-purple-600" />
              Seal Exam Paper
            </h2>
            <p className="text-sm text-gray-600">
              After sealing, the paper is encrypted and inaccessible until the release time.
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
              <p className="text-sm text-red-600">{getErrorMessage(sealMut.error)}</p>
            )}
          </div>
        </div>
      )}

      {/* Edit question modal */}
      {editModal && (
        <EditQuestionModal
          paperId={id!}
          question={editModal}
          onClose={() => {
            setEditModal(null)
            qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Question list variants
// ---------------------------------------------------------------------------

interface QuestionListProps {
  questions:    ExamQuestion[]
  editable:     boolean
  regenQueued:  Set<string>
  onEdit:       (q: ExamQuestion) => void
  onDelete:     (id: string) => void
  onRegenerate: (id: string) => void
}

function FlatQuestionList({ questions, editable, regenQueued, onEdit, onDelete, onRegenerate }: QuestionListProps) {
  return (
    <div className="space-y-3">
      {questions.map((q, idx) => (
        <QuestionCard
          key={q.id}
          question={q}
          index={idx + 1}
          editable={editable}
          isRegenerating={regenQueued.has(q.id)}
          onEdit={() => onEdit(q)}
          onDelete={() => onDelete(q.id)}
          onRegenerate={() => onRegenerate(q.id)}
        />
      ))}
    </div>
  )
}

function SectionedQuestionList({
  questions, sectionConfig, editable, regenQueued, onEdit, onDelete, onRegenerate,
}: QuestionListProps & { sectionConfig: SectionConfig[] }) {
  const bySection = new Map<string, ExamQuestion[]>()
  const uncat: ExamQuestion[] = []

  for (const q of questions) {
    if (q.section_label) {
      const group = bySection.get(q.section_label) ?? []
      group.push(q)
      bySection.set(q.section_label, group)
    } else {
      uncat.push(q)
    }
  }

  const ordered = [...sectionConfig].sort((a, b) => a.order - b.order)

  return (
    <div className="space-y-6">
      {ordered.map(sec => {
        const qs = bySection.get(sec.label) ?? []
        return (
          <div key={sec.label} className="space-y-3">
            <SectionHeader section={sec} count={qs.length} />
            {qs.length === 0 ? (
              <p className="text-sm text-gray-400 py-2 pl-2">No questions generated for Part {sec.label}.</p>
            ) : (
              qs.map((q, idx) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  index={idx + 1}
                  editable={editable}
                  isRegenerating={regenQueued.has(q.id)}
                  onEdit={() => onEdit(q)}
                  onDelete={() => onDelete(q.id)}
                  onRegenerate={() => onRegenerate(q.id)}
                />
              ))
            )}
          </div>
        )
      })}
      {uncat.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Other</p>
          {uncat.map((q, idx) => (
            <QuestionCard
              key={q.id}
              question={q}
              index={idx + 1}
              editable={editable}
              isRegenerating={regenQueued.has(q.id)}
              onEdit={() => onEdit(q)}
              onDelete={() => onDelete(q.id)}
              onRegenerate={() => onRegenerate(q.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SectionHeader({ section, count }: { section: SectionConfig; count: number }) {
  const allMustAnswer = section.answer_q === section.total_q
  const rule = allMustAnswer
    ? `Answer all ${section.total_q}`
    : `Answer any ${section.answer_q} of ${section.total_q}`
  return (
    <div className="flex items-center gap-3 pb-2 border-b border-gray-200">
      <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 text-sm font-bold shrink-0">
        {section.label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-800">Part {section.label}</p>
        <p className="text-xs text-gray-500">
          {rule} · {section.marks_each} marks each
          {section.mcq_only ? ' · MCQ only' : ''}
          {' · '}{count} generated
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Question card
// ---------------------------------------------------------------------------

function QuestionCard({
  question, index, editable, isRegenerating, onEdit, onDelete, onRegenerate,
}: {
  question:       ExamQuestion
  index:          number
  editable:       boolean
  isRegenerating: boolean
  onEdit:         () => void
  onDelete:       () => void
  onRegenerate:   () => void
}) {
  const bloomColor = BLOOM_COLORS[question.bloom_level] ?? 'bg-gray-100 text-gray-600'
  return (
    <div className={`border rounded-xl bg-white p-4 space-y-2 transition-colors ${
      isRegenerating ? 'border-indigo-300 bg-indigo-50/40' : 'border-gray-200 hover:border-gray-300'
    }`}>
      <div className="flex items-start gap-3">
        <span className="text-xs font-bold text-gray-400 mt-0.5 shrink-0">Q{index}</span>
        <div className="flex-1 min-w-0">
          {isRegenerating ? (
            <div className="flex items-center gap-2 text-sm text-indigo-600">
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              Regenerating question…
            </div>
          ) : (
            <p className="text-sm text-gray-900 leading-snug">{question.question_text}</p>
          )}
        </div>
        {editable && !isRegenerating && (
          <div className="flex gap-1 shrink-0">
            <Button
              variant="ghost" size="icon" className="h-7 w-7"
              title="Regenerate question"
              onClick={onRegenerate}
            >
              <RefreshCw className="w-3.5 h-3.5 text-indigo-400" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit}>
              <Pencil className="w-3.5 h-3.5 text-gray-400" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDelete}>
              <Trash2 className="w-3.5 h-3.5 text-red-400" />
            </Button>
          </div>
        )}
      </div>

      {!isRegenerating && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bloomColor}`}>
            {question.bloom_level}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 font-medium">
            {QTYPE_LABEL[question.question_type] ?? question.question_type}
          </span>
          {question.section_label && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 font-medium">
              Part {question.section_label}
            </span>
          )}
          <span className="text-xs text-gray-500">Unit {question.unit_number}</span>
          {question.co_ids && question.co_ids.length > 0 && (
            <span className="text-xs text-gray-400">{question.co_ids.length} CO</span>
          )}
          <span className="text-xs text-gray-500 ml-auto">{question.marks} marks</span>
          <span className="text-xs text-gray-400">Set: {question.set_membership.join(', ')}</span>
          {question.is_edited && (
            <span className="text-xs text-orange-500 font-medium">edited</span>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Coverage panels
// ---------------------------------------------------------------------------

function CoCoveragePanel({ report }: { report: CoCoverageEntry[] }) {
  const allCovered = report.every(e => e.covered)
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-gray-400" />
          CO Coverage
        </h3>
        {allCovered ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> All covered
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> Gaps
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {report.map(entry => (
          <div key={entry.co_id} className="flex items-center gap-2 text-xs">
            <span className={`font-medium w-12 shrink-0 ${entry.covered ? 'text-gray-700' : 'text-orange-600'}`}>
              {entry.co_code}
            </span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${entry.covered ? 'bg-green-400' : 'bg-orange-300'}`}
                style={{ width: entry.covered ? '100%' : '20%' }} />
            </div>
            <span className="text-gray-400 w-8 text-right shrink-0">{entry.question_count}Q</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400 italic">Advisory only — does not block workflow.</p>
    </div>
  )
}

function UnitCoveragePanel({ report }: { report: UnitCoverageEntry[] }) {
  const allCovered = report.every(e => e.covered)
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <BarChart2 className="w-3.5 h-3.5 text-gray-400" />
          Unit Coverage
        </h3>
        {allCovered ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> All units
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> Gaps
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {report.map(entry => (
          <div
            key={entry.unit_no}
            className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border ${
              entry.covered
                ? 'bg-green-50 text-green-700 border-green-200'
                : 'bg-orange-50 text-orange-700 border-orange-200'
            }`}
          >
            U{entry.unit_no}
            <span className={`${entry.covered ? 'text-green-500' : 'text-orange-400'}`}>
              {entry.question_count}Q
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400 italic">Advisory only — does not block workflow.</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Bloom's panel (unchanged)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Edit question modal (unchanged)
// ---------------------------------------------------------------------------

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
