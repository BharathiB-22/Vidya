import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import {
  ChevronLeft, Clock, AlertTriangle, Loader2,
  CheckSquare, Square, Monitor, BookOpen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDigitalSession } from '@/hooks/digitalExams'
import { startOrResumeAttempt } from '@/lib/api/digitalExam'

const RULES = [
  'The timer starts immediately when you click "Start Exam" and cannot be paused.',
  'Your answers are auto-saved as you type — you do not need to click save.',
  'MCQ answers are automatically scored after submission.',
  'You cannot change answers after final submission.',
  'Do not refresh or close this tab during the exam — your answers may be lost.',
  'You are allowed one attempt per session.',
]

export default function ExamInstructionsPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const sid = sessionId ?? ''
  const [acknowledged, setAcknowledged] = useState(false)

  const { data: session, isLoading, isError } = useDigitalSession(sid)

  const { mutate: start, isPending } = useMutation({
    mutationFn: () => startOrResumeAttempt(sid),
    onSuccess: (attempt) => {
      sessionStorage.setItem(`exam_attempt_${sid}`, attempt.id)
      if (attempt.status === 'SCORED' || attempt.status === 'SUBMITTED') {
        navigate(`/student/exams/digital/attempts/${attempt.id}/result`)
        return
      }
      navigate(`/student/exams/digital/${sid}/take`, {
        state: { attemptId: attempt.id },
      })
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const detail = err?.response?.data?.detail ?? ''
      if (detail.includes('already submitted') || detail.includes('already been scored')) {
        const stored = sessionStorage.getItem(`exam_attempt_${sid}`)
        if (stored) navigate(`/student/exams/digital/attempts/${stored}/result`)
      }
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  if (isError || !session) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-400" />
        <p className="text-sm text-gray-500">Exam session not found.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/exams/digital')}>
          Back to Exams
        </Button>
      </div>
    )
  }

  if (session.status !== 'ACTIVE') {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center space-y-3">
        <Monitor className="h-8 w-8 mx-auto text-gray-500" />
        <p className="font-medium text-gray-700">
          {session.status === 'DRAFT'
            ? 'This exam has not opened yet.'
            : 'This exam session is closed.'}
        </p>
        <Button variant="ghost" size="sm" onClick={() => navigate('/student/exams/digital')}>
          Back to Exams
        </Button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Back */}
      <Button
        variant="ghost"
        size="sm"
        className="-ml-1"
        onClick={() => navigate('/student/exams/digital')}
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Exams
      </Button>

      {/* Header card */}
      <div className="rounded-2xl border border-indigo-100 bg-indigo-50 px-6 py-5 space-y-4">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-indigo-600 shrink-0" />
          <h1 className="text-lg font-bold text-gray-900">{session.title}</h1>
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <div className="flex items-center gap-1.5 text-indigo-700">
            <Clock className="h-4 w-4" />
            <span className="font-medium">{session.max_duration_mins} minutes</span>
          </div>
          {session.window_end && (
            <div className="text-gray-500">
              Closes {new Date(session.window_end).toLocaleString()}
            </div>
          )}
        </div>

        {session.instructions && (
          <div className="rounded-lg bg-white border border-indigo-100 px-4 py-3">
            <p className="text-sm font-semibold text-gray-700 mb-1">Instructions from examiner:</p>
            <p className="text-sm text-gray-600 whitespace-pre-wrap">{session.instructions}</p>
          </div>
        )}
      </div>

      {/* Rules */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-3">
        <h2 className="font-semibold text-gray-800">Exam Rules</h2>
        <ul className="space-y-2">
          {RULES.map((rule, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
              <span className="mt-0.5 h-4 w-4 rounded-full bg-amber-100 text-amber-700 text-xs flex items-center justify-center font-bold shrink-0">
                {i + 1}
              </span>
              {rule}
            </li>
          ))}
        </ul>
      </div>

      {/* Acknowledgement */}
      <button
        type="button"
        onClick={() => setAcknowledged(v => !v)}
        className="flex items-start gap-3 w-full text-left rounded-xl border border-gray-200 bg-white px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        {acknowledged
          ? <CheckSquare className="h-5 w-5 text-indigo-600 shrink-0 mt-0.5" />
          : <Square className="h-5 w-5 text-gray-500 shrink-0 mt-0.5" />
        }
        <span className="text-sm text-gray-700">
          I have read and understood the instructions and exam rules. I am ready to begin.
        </span>
      </button>

      {/* Start button */}
      <Button
        className="w-full py-6 text-base font-semibold"
        disabled={!acknowledged || isPending}
        onClick={() => start()}
      >
        {isPending ? (
          <><Loader2 className="h-4 w-4 animate-spin mr-2" />Starting Exam…</>
        ) : (
          <>Start Exam — {session.max_duration_mins} min</>
        )}
      </Button>

      <p className="text-center text-xs text-gray-600">
        The timer begins the moment you click Start Exam.
      </p>
    </div>
  )
}
