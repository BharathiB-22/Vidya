// M08 Exam Setter — Examination Board: review + approve/return + seal + release
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, CheckCircle2, XCircle, Loader2, AlertTriangle, Lock, Unlock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getExamPaper, listQuestions, getBloomsReport, boardDecision, sealPaper, releasePaper } from '@/lib/api/exam'
import type { BoardDecisionPayload, ExamQuestion, BloomsComplianceReport } from '@/types/exam'

const BLOOM_COLORS: Record<string, string> = {
  REMEMBER:   'bg-red-100 text-red-700',
  UNDERSTAND: 'bg-orange-100 text-orange-700',
  APPLY:      'bg-yellow-100 text-yellow-700',
  ANALYSE:    'bg-green-100 text-green-700',
  EVALUATE:   'bg-blue-100 text-blue-700',
  CREATE:     'bg-purple-100 text-purple-700',
}

export default function BoardReviewPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [setLabel, setSetLabel]   = useState<'A' | 'B'>('A')
  const [decision, setDecision]   = useState<'approve' | 'return' | null>(null)
  const [comment, setComment]     = useState('')
  const [error, setError]         = useState<string | null>(null)
  const [releaseAt, setReleaseAt] = useState('')
  const [sealError, setSealError] = useState<string | null>(null)
  const [releaseError, setReleaseError] = useState<string | null>(null)

  const { data: paper, isLoading: paperLoading } = useQuery({
    queryKey: ['exam-paper', id],
    queryFn:  () => getExamPaper(id!),
  })

  const { data: questions } = useQuery({
    queryKey: ['exam-questions', id, setLabel],
    queryFn:  () => listQuestions(id!, setLabel),
    enabled:  !!paper,
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
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Decision failed.')
    },
  })

  const sealMut = useMutation({
    mutationFn: () => {
      if (!releaseAt) throw new Error('Select a release date and time.')
      const iso = new Date(releaseAt).toISOString()
      return sealPaper(id!, { release_at: iso })
    },
    onSuccess: () => {
      setSealError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setSealError(msg ?? 'Seal failed.')
    },
  })

  const releaseMut = useMutation({
    mutationFn: () => releasePaper(id!),
    onSuccess: () => {
      setReleaseError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setReleaseError(msg ?? 'Release failed.')
    },
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

  const alreadyDecided    = paper.status !== 'SUBMITTED'
  const canSeal           = paper.status === 'BOARD_APPROVED'
  const canRelease        = paper.status === 'SEALED'
  const isTerminal        = paper.status === 'RELEASED'

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
            Board Review · {paper.exam_type.replace('_', ' ')} · {paper.total_marks} marks · {paper.duration_mins} min
          </p>
        </div>
      </div>

      {alreadyDecided && !canSeal && !canRelease && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-sm text-gray-600">
          This paper has already been processed (status: <strong>{paper.status.replace('_', ' ')}</strong>).
          {paper.board_comment && (
            <p className="mt-1 text-gray-500">Board comment: {paper.board_comment}</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Questions (read-only) */}
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

          {questions && questions.length === 0 && (
            <div className="text-gray-500 text-center py-8">No questions in Set {setLabel}.</div>
          )}

          {questions && questions.map((q, idx) => (
            <ReadOnlyQuestionCard key={q.id} question={q} index={idx + 1} />
          ))}
        </div>

        {/* Right panel: compliance + decision */}
        <div className="space-y-4">
          {bloomsReport && <BloomsPanel report={bloomsReport} />}

          {/* GATE 3 — Seal Paper (after Board Approval) */}
          {canSeal && (
            <div className="border border-purple-200 rounded-xl bg-purple-50 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-purple-800 flex items-center gap-1.5">
                <Lock className="w-4 h-4" /> Seal Paper
              </h3>
              <p className="text-xs text-purple-700">
                Set a release date and time. The paper will be encrypted and automatically released at the scheduled time.
              </p>
              <div className="space-y-1">
                <label className="text-xs font-medium text-purple-700">Release Date &amp; Time (UTC) *</label>
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

          {/* Sealed info + Release Now */}
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
                {decision === 'approve' ? 'Confirm Approval' : decision === 'return' ? 'Return Paper' : 'Select Decision'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ReadOnlyQuestionCard({ question, index }: { question: ExamQuestion; index: number }) {
  const bloomColor = BLOOM_COLORS[question.bloom_level] ?? 'bg-gray-100 text-gray-600'
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-2">
      <div className="flex items-start gap-3">
        <span className="text-xs font-bold text-gray-400 mt-0.5 shrink-0">Q{index}</span>
        <p className="text-sm text-gray-900 leading-snug">{question.question_text}</p>
      </div>
      {question.options && (
        <div className="ml-7 space-y-1">
          {question.options.map(opt => (
            <div key={opt.label} className="flex gap-2 text-xs text-gray-600">
              <span className="font-medium text-gray-400">{opt.label}.</span>
              <span>{opt.text}</span>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5 items-center ml-7">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bloomColor}`}>
          {question.bloom_level}
        </span>
        <span className="text-xs text-gray-500">Unit {question.unit_number}</span>
        <span className="text-xs text-gray-500 ml-auto">{question.marks} marks</span>
        <span className="text-xs text-gray-400">Set: {question.set_membership.join(', ')}</span>
      </div>
    </div>
  )
}

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
          <span className="font-medium text-orange-700">{v.level}</span>: requested {v.requested_pct.toFixed(0)}%, actual {v.actual_pct.toFixed(0)}%
          {' '}(Δ {v.delta_pct > 0 ? '+' : ''}{v.delta_pct.toFixed(0)}%)
        </div>
      ))}
      {report.compliance_ok && (
        <p className="text-xs text-green-600">All Bloom's levels within ±5% tolerance.</p>
      )}
    </div>
  )
}
