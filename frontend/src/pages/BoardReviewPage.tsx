// M08 Exam Setter — Examination Board: review with model answers + coverage + approve/return/seal/release
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, CheckCircle2, XCircle, Loader2, AlertTriangle,
  Lock, Unlock, BookOpen, BarChart2, ChevronDown, ChevronUp,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getExamPaper, listQuestionsWithAnswers, getBloomsReport,
  boardDecision, sealPaper, releasePaper,
} from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import type {
  BoardDecisionPayload, ExamQuestion, BloomsComplianceReport,
  SectionConfig, CoCoverageEntry, UnitCoverageEntry,
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

// Statuses where Board can request model answers
const ANSWER_ELIGIBLE = new Set(['SUBMITTED', 'BOARD_APPROVED', 'BOARD_RETURNED', 'SEALED', 'RELEASED'])

export default function BoardReviewPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [setLabel,      setSetLabel]      = useState<'A' | 'B'>('A')
  const [decision,      setDecision]      = useState<'approve' | 'return' | null>(null)
  const [comment,       setComment]       = useState('')
  const [error,         setError]         = useState<string | null>(null)
  const [releaseAt,     setReleaseAt]     = useState('')
  const [sealError,     setSealError]     = useState<string | null>(null)
  const [releaseError,  setReleaseError]  = useState<string | null>(null)

  const { data: paper, isLoading: paperLoading } = useQuery({
    queryKey: ['exam-paper', id],
    queryFn:  () => getExamPaper(id!),
  })

  const canFetchAnswers = !!(paper && ANSWER_ELIGIBLE.has(paper.status))

  const { data: questions, isLoading: qLoading } = useQuery({
    queryKey: ['exam-questions-answers', id, setLabel],
    queryFn:  () => listQuestionsWithAnswers(id!, setLabel),
    enabled:  canFetchAnswers,
  })

  const { data: bloomsReport } = useQuery({
    queryKey: ['exam-blooms', id],
    queryFn:  () => getBloomsReport(id!),
    enabled:  !!paper,
  })

  const decideMut = useMutation({
    mutationFn: (payload: BoardDecisionPayload) => boardDecision(id!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
      navigate('/exams/board/pending')
    },
    onError: (err: unknown) => {
      setError(getErrorMessage(err))
    },
  })

  const sealMut = useMutation({
    mutationFn: () => {
      if (!releaseAt) throw new Error('Select a release date and time.')
      return sealPaper(id!, { release_at: new Date(releaseAt).toISOString() })
    },
    onSuccess: () => {
      setSealError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err: unknown) => setSealError(getErrorMessage(err)),
  })

  const releaseMut = useMutation({
    mutationFn: () => releasePaper(id!),
    onSuccess: () => {
      setReleaseError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err: unknown) => setReleaseError(getErrorMessage(err)),
  })

  function handleDecide() {
    setError(null)
    if (!decision) return
    if (decision === 'return' && !comment.trim()) {
      setError('A comment is required when returning a paper.')
      return
    }
    decideMut.mutate({
      approved:      decision === 'approve',
      board_comment: decision === 'return' ? comment : undefined,
    })
  }

  if (paperLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading paper for review…
      </div>
    )
  }

  if (!paper) return <div className="p-8 text-red-600">Exam paper not found.</div>

  const alreadyDecided = paper.status !== 'SUBMITTED'
  const canSeal        = paper.status === 'BOARD_APPROVED'
  const canRelease     = paper.status === 'SEALED'
  const isTerminal     = paper.status === 'RELEASED'
  const hasSections    = !!(paper.section_config && paper.section_config.length > 0)

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{paper.title}</h1>
          <p className="text-sm text-gray-500">
            Board Review · {paper.exam_type.replace('_', ' ')}
            {' · '}
            <span className={`font-medium ${paper.exam_workflow === 'INTERNAL' ? 'text-amber-600' : 'text-indigo-600'}`}>
              {paper.exam_workflow === 'INTERNAL' ? 'Internal Assessment' : 'Board Exam'}
            </span>
            {' · '}{paper.total_marks} marks · {paper.duration_mins} min
          </p>
        </div>
        <StatusBadge status={paper.status} />
      </div>

      {alreadyDecided && !canSeal && !canRelease && !isTerminal && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-sm text-gray-600">
          This paper has already been processed (status:{' '}
          <strong>{paper.status.replace('_', ' ')}</strong>).
          {paper.board_comment && (
            <p className="mt-1 text-gray-500">Board comment: {paper.board_comment}</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: Questions with model answers */}
        <div className="lg:col-span-2 space-y-4">
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

          {qLoading && (
            <div className="text-gray-400 text-sm py-4 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading questions with model answers…
            </div>
          )}

          {!canFetchAnswers && (
            <div className="text-gray-500 text-sm py-4 bg-gray-50 rounded-xl text-center border border-dashed border-gray-200">
              Model answers are available once the paper is submitted for Board review.
            </div>
          )}

          {questions && questions.length === 0 && (
            <div className="text-gray-500 text-center py-8">No questions in Set {setLabel}.</div>
          )}

          {questions && (
            hasSections
              ? <SectionedAnswerList questions={questions} sectionConfig={paper.section_config!} />
              : <FlatAnswerList questions={questions} />
          )}
        </div>

        {/* Right: Coverage + Bloom's + decision */}
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

          {/* GATE 3 — Seal Paper */}
          {canSeal && (
            <div className="border border-purple-200 rounded-xl bg-purple-50 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-purple-800 flex items-center gap-1.5">
                <Lock className="w-4 h-4" /> Seal Paper
              </h3>
              <p className="text-xs text-purple-700">
                Set a release time. The paper will be encrypted and automatically released.
              </p>
              <div className="space-y-1">
                <label className="text-xs font-medium text-purple-700">Release Date &amp; Time *</label>
                <input
                  type="datetime-local"
                  value={releaseAt}
                  onChange={e => setReleaseAt(e.target.value)}
                  className="w-full border border-purple-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300 bg-white"
                />
              </div>
              {sealError && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  {sealError}
                </div>
              )}
              <Button
                onClick={() => { setSealError(null); sealMut.mutate() }}
                disabled={!releaseAt || sealMut.isPending}
                className="w-full bg-purple-600 hover:bg-purple-700 text-white gap-2"
              >
                {sealMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
                Seal &amp; Schedule Release
              </Button>
            </div>
          )}

          {/* Sealed + Release Now */}
          {canRelease && (
            <div className="border border-emerald-200 rounded-xl bg-emerald-50 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-emerald-800 flex items-center gap-1.5">
                <Lock className="w-4 h-4" /> Paper Sealed
              </h3>
              {paper.sealed_at && (
                <p className="text-xs text-emerald-700">
                  Sealed at: {new Date(paper.sealed_at).toLocaleString()}
                </p>
              )}
              {paper.release_at && (
                <p className="text-xs text-emerald-700">
                  Scheduled release: {new Date(paper.release_at).toLocaleString()}
                </p>
              )}
              {releaseError && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  {releaseError}
                </div>
              )}
              <Button
                onClick={() => { setReleaseError(null); releaseMut.mutate() }}
                disabled={releaseMut.isPending}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
              >
                {releaseMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Unlock className="w-4 h-4" />}
                Release Now
              </Button>
            </div>
          )}

          {isTerminal && (
            <div className="border border-emerald-200 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-700">
              <div className="flex items-center gap-1.5 font-semibold">
                <CheckCircle2 className="w-4 h-4" /> Paper Released
              </div>
              {paper.released_at && (
                <p className="text-xs mt-1 text-emerald-600">
                  Released at: {new Date(paper.released_at).toLocaleString()}
                </p>
              )}
            </div>
          )}

          {/* Board Decision — only when SUBMITTED */}
          {!alreadyDecided && (
            <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-4">
              <h3 className="text-sm font-semibold text-gray-700">Board Decision</h3>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setDecision('approve')}
                  className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    decision === 'approve'
                      ? 'bg-green-600 text-white border-green-600'
                      : 'border-gray-200 text-gray-600 hover:border-green-300'
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Approve
                </button>
                <button
                  onClick={() => setDecision('return')}
                  className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    decision === 'return'
                      ? 'bg-orange-500 text-white border-orange-500'
                      : 'border-gray-200 text-gray-600 hover:border-orange-300'
                  }`}
                >
                  <XCircle className="w-4 h-4" />
                  Return
                </button>
              </div>

              {decision === 'return' && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-600">Comment (required) *</label>
                  <textarea
                    rows={3}
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    placeholder="Explain what needs to be revised…"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 resize-none"
                  />
                </div>
              )}

              {error && (
                <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}

              <Button
                onClick={handleDecide}
                disabled={!decision || decideMut.isPending}
                className={`w-full gap-2 ${
                  decision === 'approve'
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : decision === 'return'
                    ? 'bg-orange-500 hover:bg-orange-600 text-white'
                    : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                }`}
              >
                {decideMut.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : decision === 'approve' ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : decision === 'return' ? (
                  <XCircle className="w-4 h-4" />
                ) : null}
                {decision === 'approve'
                  ? 'Confirm Approval'
                  : decision === 'return'
                  ? 'Return Paper'
                  : 'Select Decision'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Question list variants (with model answers)
// ---------------------------------------------------------------------------

function FlatAnswerList({ questions }: { questions: ExamQuestion[] }) {
  return (
    <div className="space-y-3">
      {questions.map((q, idx) => (
        <BoardQuestionCard key={q.id} question={q} index={idx + 1} />
      ))}
    </div>
  )
}

function SectionedAnswerList({
  questions, sectionConfig,
}: {
  questions:     ExamQuestion[]
  sectionConfig: SectionConfig[]
}) {
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
        const allAnswer = sec.answer_q === sec.total_q
        const rule = allAnswer
          ? `Answer all ${sec.total_q}`
          : `Answer any ${sec.answer_q} of ${sec.total_q}`
        return (
          <div key={sec.label} className="space-y-3">
            <div className="flex items-center gap-3 pb-2 border-b border-gray-200">
              <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 text-sm font-bold shrink-0">
                {sec.label}
              </span>
              <div>
                <p className="text-sm font-semibold text-gray-800">Part {sec.label}</p>
                <p className="text-xs text-gray-500">
                  {rule} · {sec.marks_each} marks each
                  {sec.mcq_only ? ' · MCQ only' : ''}
                  {' · '}{qs.length} questions
                </p>
              </div>
            </div>
            {qs.map((q, idx) => (
              <BoardQuestionCard key={q.id} question={q} index={idx + 1} />
            ))}
          </div>
        )
      })}
      {uncat.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Other</p>
          {uncat.map((q, idx) => (
            <BoardQuestionCard key={q.id} question={q} index={idx + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Board question card — shows question + model answer (collapsible)
// ---------------------------------------------------------------------------

function BoardQuestionCard({ question, index }: { question: ExamQuestion; index: number }) {
  const [showAnswers, setShowAnswers] = useState(false)
  const bloomColor = BLOOM_COLORS[question.bloom_level] ?? 'bg-gray-100 text-gray-600'
  const hasAnswerData = !!(question.model_answer || question.correct_option)

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">

      {/* Question text */}
      <div className="flex items-start gap-3">
        <span className="text-xs font-bold text-gray-400 mt-0.5 shrink-0">Q{index}</span>
        <p className="text-sm text-gray-900 leading-snug flex-1">{question.question_text}</p>
      </div>

      {/* MCQ options */}
      {question.options && (
        <div className="ml-7 space-y-1">
          {question.options.map(opt => {
            const isCorrect = question.correct_option === opt.label
            return (
              <div
                key={opt.label}
                className={`flex gap-2 text-xs rounded-lg px-2 py-1 ${
                  isCorrect ? 'bg-green-50 text-green-800 font-medium' : 'text-gray-600'
                }`}
              >
                <span className={`font-semibold shrink-0 ${isCorrect ? 'text-green-600' : 'text-gray-400'}`}>
                  {opt.label}.
                </span>
                <span>{opt.text}</span>
                {isCorrect && (
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0 ml-auto mt-0.5" />
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Metadata row */}
      <div className="flex flex-wrap gap-1.5 items-center ml-7">
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

      {/* Model answer toggle — only if answer data exists */}
      {hasAnswerData && (
        <div className="ml-7">
          <button
            onClick={() => setShowAnswers(v => !v)}
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            {showAnswers ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showAnswers ? 'Hide model answer' : 'Show model answer'}
          </button>

          {showAnswers && (
            <div className="mt-2 space-y-2">
              {question.model_answer && (
                <div className="bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2">
                  <p className="text-xs font-semibold text-indigo-700 mb-1">Model Answer</p>
                  <p className="text-xs text-indigo-900 leading-relaxed whitespace-pre-wrap">
                    {question.model_answer}
                  </p>
                </div>
              )}

              {question.correct_option && !question.model_answer && (
                <div className="bg-green-50 border border-green-100 rounded-lg px-3 py-2 text-xs text-green-800">
                  <span className="font-semibold">Correct option: </span>
                  {question.correct_option}
                </div>
              )}

              {/* Marking scheme */}
              {Array.isArray((question as ExamQuestion & { marking_scheme?: unknown[] }).marking_scheme) &&
               (question as ExamQuestion & { marking_scheme?: unknown[] }).marking_scheme!.length > 0 && (
                <MarkingSchemePanel
                  scheme={(question as ExamQuestion & { marking_scheme?: MarkingCriterionRaw[] }).marking_scheme!}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Minimal local type for marking scheme rows returned by the API
interface MarkingCriterionRaw {
  criterion?: string
  marks?:     number
  note?:      string
}

function MarkingSchemePanel({ scheme }: { scheme: MarkingCriterionRaw[] }) {
  return (
    <div className="bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
      <p className="text-xs font-semibold text-amber-700 mb-1.5">Marking Scheme</p>
      <div className="space-y-1">
        {scheme.map((c, i) => (
          <div key={i} className="flex items-start gap-2 text-xs text-amber-900">
            <span className="font-medium shrink-0 text-amber-600 w-8">
              {c.marks != null ? `${c.marks}m` : '—'}
            </span>
            <span className="flex-1">{c.criterion ?? ''}</span>
          </div>
        ))}
      </div>
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
              <div
                className={`h-full rounded-full ${entry.covered ? 'bg-green-400' : 'bg-orange-300'}`}
                style={{ width: entry.covered ? '100%' : '20%' }}
              />
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
            <span className={entry.covered ? 'text-green-500' : 'text-orange-400'}>
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
// Bloom's panel
// ---------------------------------------------------------------------------

function BloomsPanel({ report }: { report: BloomsComplianceReport }) {
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Bloom's Compliance</h3>
        {report.compliance_ok ? (
          <span className="text-xs text-green-600 font-medium flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" /> OK
          </span>
        ) : (
          <span className="text-xs text-orange-600 font-medium flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5" /> {report.violations.length} violation{report.violations.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      {report.violations.map(v => (
        <div key={v.level} className="text-xs bg-orange-50 border border-orange-100 rounded-lg px-3 py-2">
          <span className="font-medium text-orange-700">{v.level}</span>: requested{' '}
          {v.requested_pct.toFixed(0)}%, actual {v.actual_pct.toFixed(0)}%
          {' '}(Δ {v.delta_pct > 0 ? '+' : ''}{v.delta_pct.toFixed(0)}%)
        </div>
      ))}
      {report.compliance_ok && (
        <p className="text-xs text-green-600">All Bloom's levels within ±5% tolerance.</p>
      )}
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
