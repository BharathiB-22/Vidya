import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, ChevronRight, Clock, AlertTriangle,
  Loader2, CheckCircle2, Save, WifiOff,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAttemptQuestions } from '@/hooks/digitalExams'
import { saveResponse, submitAttempt } from '@/lib/api/digitalExam'
import type { DigitalQuestionOut } from '@/types/digitalExam'

// ---------------------------------------------------------------------------
// Countdown timer hook
// ---------------------------------------------------------------------------

function useCountdown(expiresAt: string | null): {
  display: string
  urgent: boolean
  expired: boolean
} {
  const [secsLeft, setSecsLeft] = useState<number>(() => {
    if (!expiresAt) return 0
    return Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000))
  })

  useEffect(() => {
    if (!expiresAt) return
    const id = setInterval(() => {
      setSecsLeft(Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)))
    }, 1000)
    return () => clearInterval(id)
  }, [expiresAt])

  const h = Math.floor(secsLeft / 3600)
  const m = Math.floor((secsLeft % 3600) / 60)
  const s = secsLeft % 60
  const display = h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`

  return {
    display,
    urgent: secsLeft > 0 && secsLeft <= 300,
    expired: secsLeft === 0 && Boolean(expiresAt),
  }
}

// ---------------------------------------------------------------------------
// Auto-save indicator
// ---------------------------------------------------------------------------

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

function AutoSaveIndicator({ state }: { state: SaveState }) {
  if (state === 'idle') return null
  return (
    <span className={`flex items-center gap-1 text-xs ${
      state === 'saving'  ? 'text-gray-400' :
      state === 'saved'   ? 'text-green-600' :
      'text-red-500'
    }`}>
      {state === 'saving'  && <Loader2 className="h-3 w-3 animate-spin" />}
      {state === 'saved'   && <Save className="h-3 w-3" />}
      {state === 'error'   && <WifiOff className="h-3 w-3" />}
      {state === 'saving'  ? 'Saving…' :
       state === 'saved'   ? 'Saved' :
       'Save failed — check connection'}
    </span>
  )
}

// ---------------------------------------------------------------------------
// MCQ option row
// ---------------------------------------------------------------------------

function MCQOption({
  label, text, selected, onClick,
}: { label: string; text: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
        selected
          ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
          : 'border-gray-200 bg-white hover:bg-gray-50 text-gray-700'
      }`}
    >
      <span className={`mt-0.5 h-5 w-5 rounded-full border-2 flex items-center justify-center shrink-0 text-xs font-bold ${
        selected ? 'border-indigo-500 bg-indigo-500 text-white' : 'border-gray-300 text-gray-400'
      }`}>
        {label}
      </span>
      <span className="text-sm leading-relaxed">{text}</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Confirm submit dialog
// ---------------------------------------------------------------------------

function ConfirmSubmitDialog({
  unanswered,
  onCancel,
  onConfirm,
  isPending,
}: {
  unanswered: number
  onCancel: () => void
  onConfirm: () => void
  isPending: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 space-y-4">
        <h2 className="font-bold text-gray-900 text-lg">Submit Exam?</h2>

        {unanswered > 0 && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-sm text-amber-700">
              <strong>{unanswered} question{unanswered > 1 ? 's' : ''}</strong> left unanswered.
            </p>
          </div>
        )}

        <p className="text-sm text-gray-600">
          Once submitted, you cannot change your answers. MCQ answers will be auto-scored immediately.
        </p>

        <div className="flex gap-2 pt-1">
          <Button variant="outline" className="flex-1" onClick={onCancel} disabled={isPending}>
            Keep Reviewing
          </Button>
          <Button className="flex-1" onClick={onConfirm} disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Submit'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ActiveExamPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const sid = sessionId ?? ''

  // Recover attemptId: first from navigation state, then from sessionStorage
  const attemptId: string =
    (location.state as { attemptId?: string } | null)?.attemptId
    ?? sessionStorage.getItem(`exam_attempt_${sid}`)
    ?? ''

  const { data, isLoading, isError } = useAttemptQuestions(attemptId)

  // Local responses map: questionId → { selected_option?, response_text? }
  const [responses, setResponses] = useState<Record<string, { selected_option?: string; response_text?: string }>>({})
  const [currentIdx, setCurrentIdx] = useState(0)
  const [showConfirm, setShowConfirm] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const qc = useQueryClient()

  // Populate from server-saved responses on load
  useEffect(() => {
    if (!data) return
    const initial: Record<string, { selected_option?: string; response_text?: string }> = {}
    data.questions.forEach(q => {
      if (q.saved_response) {
        initial[q.id] = {
          selected_option: q.saved_response.selected_option ?? undefined,
          response_text:   q.saved_response.response_text   ?? undefined,
        }
      }
    })
    setResponses(initial)
  }, [data])

  // Timer
  const attempt = data?.attempt
  const { display: timerDisplay, urgent: timerUrgent, expired: timerExpired } = useCountdown(
    attempt?.expires_at ?? null
  )

  // Auto-submit on timer expiry
  const { mutate: doSubmit, isPending: isSubmitting } = useMutation({
    mutationFn: () => submitAttempt(attemptId),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['digitalExams'] })
      navigate(`/student/exams/digital/${sid}/submitted`, {
        state: { attemptId, result },
        replace: true,
      })
    },
  })

  const autoSubmitFiredRef = useRef(false)
  useEffect(() => {
    if (timerExpired && !autoSubmitFiredRef.current && attemptId) {
      autoSubmitFiredRef.current = true
      doSubmit()
    }
  }, [timerExpired, attemptId, doSubmit])

  // Save response (debounced)
  const persist = useCallback((questionId: string, payload: { selected_option?: string; response_text?: string }) => {
    if (!attemptId) return
    setSaveState('saving')
    saveResponse(attemptId, questionId, payload)
      .then(() => setSaveState('saved'))
      .catch(() => setSaveState('error'))
      .finally(() => {
        setTimeout(() => setSaveState('idle'), 2000)
      })
  }, [attemptId])

  const handleMCQSelect = (question: DigitalQuestionOut, option: string) => {
    const updated = { selected_option: option }
    setResponses(prev => ({ ...prev, [question.id]: { ...prev[question.id], ...updated } }))
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => persist(question.id, updated), 800)
  }

  const handleTextChange = (question: DigitalQuestionOut, text: string) => {
    const updated = { response_text: text }
    setResponses(prev => ({ ...prev, [question.id]: { ...prev[question.id], ...updated } }))
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => persist(question.id, updated), 800)
  }

  // ---------------------------------------------------------------------------

  if (!attemptId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <AlertTriangle className="h-8 w-8 text-amber-400" />
        <p className="text-sm text-gray-500">No active exam found.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/exams/digital')}>
          Go to Exams
        </Button>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center space-y-2">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mx-auto" />
          <p className="text-sm text-gray-500">Loading exam…</p>
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <AlertTriangle className="h-8 w-8 text-red-400" />
        <p className="text-sm text-gray-500">Failed to load exam. Please refresh.</p>
        <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
          Refresh
        </Button>
      </div>
    )
  }

  if (attempt?.status === 'SUBMITTED' || attempt?.status === 'SCORED') {
    navigate(`/student/exams/digital/attempts/${attemptId}/result`, { replace: true })
    return null
  }

  const questions = data.questions
  const currentQ  = questions[currentIdx]
  const answered  = Object.keys(responses).filter(id => {
    const r = responses[id]
    return r?.selected_option || (r?.response_text && r.response_text.trim())
  })
  const unanswered = questions.length - answered.length

  const isAnswered = (q: DigitalQuestionOut) => {
    const r = responses[q.id]
    return Boolean(r?.selected_option || (r?.response_text && r.response_text.trim()))
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
      {/* Sticky top bar */}
      <header className="shrink-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between gap-4">
        <h1 className="font-semibold text-gray-900 truncate text-sm sm:text-base">
          {/* session title not in attempt; show generic */}
          Digital Exam
        </h1>

        <div className="flex items-center gap-3">
          <AutoSaveIndicator state={saveState} />

          {/* Timer */}
          <div className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono font-bold text-sm ${
            timerExpired
              ? 'bg-red-100 text-red-700'
              : timerUrgent
              ? 'bg-red-50 text-red-600 animate-pulse'
              : 'bg-gray-100 text-gray-700'
          }`}>
            <Clock className="h-3.5 w-3.5" />
            {timerExpired ? 'Submitting…' : timerDisplay}
          </div>

          <Button
            size="sm"
            onClick={() => setShowConfirm(true)}
            disabled={isSubmitting || timerExpired}
            className="hidden sm:flex"
          >
            Submit Exam
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Question navigation sidebar — hidden on mobile, shown on lg+ */}
        <nav className="hidden lg:flex flex-col w-56 bg-white border-r border-gray-200 overflow-y-auto py-3 px-2">
          <div className="text-xs font-semibold text-gray-400 uppercase px-2 mb-2">
            {answered.length} / {questions.length} answered
          </div>

          {questions.map((q, i) => {
            const done = isAnswered(q)
            const active = i === currentIdx
            return (
              <button
                key={q.id}
                onClick={() => setCurrentIdx(i)}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
                  active
                    ? 'bg-indigo-50 text-indigo-700 font-semibold'
                    : done
                    ? 'text-green-700 hover:bg-green-50'
                    : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                <span className={`h-5 w-5 rounded-full border-2 flex items-center justify-center text-xs font-bold shrink-0 ${
                  active  ? 'border-indigo-500 bg-indigo-500 text-white' :
                  done    ? 'border-green-500 bg-green-50 text-green-600' :
                  'border-gray-300 text-gray-400'
                }`}>
                  {done && !active ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
                </span>
                <span className="truncate">
                  Q{i + 1}
                  {q.section_label && <span className="text-xs text-gray-400 ml-1">§{q.section_label}</span>}
                </span>
                <span className="ml-auto text-xs text-gray-400">{q.marks}m</span>
              </button>
            )
          })}
        </nav>

        {/* Main question area */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">

            {/* Mobile progress */}
            <div className="lg:hidden flex items-center justify-between text-sm text-gray-500">
              <span>{answered.length}/{questions.length} answered</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowConfirm(true)}
                disabled={isSubmitting}
              >
                Submit
              </Button>
            </div>

            {/* Question card */}
            <div className="rounded-xl bg-white border border-gray-200 shadow-sm overflow-hidden">
              {/* Question header */}
              <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50 flex-wrap">
                <span className="font-bold text-gray-700">Q{currentIdx + 1}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  currentQ.question_type === 'MCQ'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-purple-100 text-purple-700'
                }`}>
                  {currentQ.question_type.replace('_', ' ')}
                </span>
                {currentQ.section_label && (
                  <span className="rounded-full bg-gray-100 text-gray-500 px-2 py-0.5 text-xs">
                    Section {currentQ.section_label}
                  </span>
                )}
                <span className="ml-auto text-xs text-gray-400 font-medium">
                  {currentQ.marks} mark{currentQ.marks !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Question text */}
              <div className="px-5 py-4">
                <p className="text-gray-800 text-sm sm:text-base leading-relaxed whitespace-pre-wrap">
                  {currentQ.question_text}
                </p>
              </div>

              {/* Answer input */}
              <div className="px-5 pb-5 space-y-2">
                {currentQ.question_type === 'MCQ' && currentQ.options ? (
                  <div className="space-y-2">
                    {currentQ.options.map(opt => (
                      <MCQOption
                        key={opt.label}
                        label={opt.label}
                        text={opt.text}
                        selected={responses[currentQ.id]?.selected_option === opt.label}
                        onClick={() => handleMCQSelect(currentQ, opt.label)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="space-y-1">
                    <label className="text-xs text-gray-500">Your answer</label>
                    <textarea
                      className="w-full min-h-[160px] rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 resize-y focus:outline-none focus:border-indigo-400 focus:bg-white transition-colors"
                      placeholder="Write your answer here…"
                      value={responses[currentQ.id]?.response_text ?? ''}
                      onChange={e => handleTextChange(currentQ, e.target.value)}
                    />
                    {currentQ.question_type === 'LONG_ANSWER' && (
                      <p className="text-xs text-gray-400">
                        {(responses[currentQ.id]?.response_text ?? '').length} characters
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Prev / Next */}
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentIdx(i => Math.max(0, i - 1))}
                disabled={currentIdx === 0}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>

              <span className="text-sm text-gray-400">{currentIdx + 1} of {questions.length}</span>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentIdx(i => Math.min(questions.length - 1, i + 1))}
                disabled={currentIdx === questions.length - 1}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>

          </div>
        </main>
      </div>

      {/* Confirm submit dialog */}
      {showConfirm && (
        <ConfirmSubmitDialog
          unanswered={unanswered}
          onCancel={() => setShowConfirm(false)}
          onConfirm={() => { setShowConfirm(false); doSubmit() }}
          isPending={isSubmitting}
        />
      )}

      {/* Full-screen submitting overlay */}
      {isSubmitting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-sm">
          <div className="text-center space-y-3">
            <Loader2 className="h-10 w-10 animate-spin text-indigo-500 mx-auto" />
            <p className="font-semibold text-gray-700">Submitting your exam…</p>
            <p className="text-sm text-gray-400">Scoring MCQ answers…</p>
          </div>
        </div>
      )}
    </div>
  )
}
