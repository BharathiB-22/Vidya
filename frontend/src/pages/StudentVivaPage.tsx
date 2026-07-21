// M07 Research Supervision — Student: Viva session (respond to questions)
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Loader2, Video, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  recordConsent,
  submitResponse,
  completeViva,
} from '@/lib/api/research'
import type { VivaQuestion } from '@/types/research'

export default function StudentVivaPage() {
  const { token }  = useParams<{ token: string }>()
  const navigate   = useNavigate()
  const qc         = useQueryClient()

  const [currentQIdx, setCurrentQIdx] = useState(0)
  const [response, setResponse]       = useState('')

  // Token-based lookup — reuse getViva but via student route
  const { data: viva, isLoading, isError } = useQuery({
    queryKey: ['student-viva-token', token],
    queryFn: async () => {
      const { data } = await import('@/lib/api').then((m) => m.default.get(`/research/student/vivas`))
      // Find the session by token from the list
      const items = data.items ?? []
      return items.find((v: { session_token: string }) => v.session_token === token) ?? null
    },
    enabled: !!token,
    refetchInterval: 5000,
  })

  const { mutate: consent, isPending: consenting } = useMutation({
    mutationFn: () => recordConsent(token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['student-viva-token', token] }),
  })

  const { mutate: respond, isPending: responding } = useMutation({
    mutationFn: () => submitResponse(token!, { response_text: response }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['student-viva-token', token] })
      setResponse('')
      // Advance to next question
      const q: VivaQuestion[] = updated.ai_questions ?? []
      const answered = (updated.ai_responses ?? []).map((r: { question_id: string }) => r.question_id)
      const nextIdx = q.findIndex((q) => !answered.includes(q.id))
      setCurrentQIdx(nextIdx >= 0 ? nextIdx : currentQIdx + 1)
    },
  })

  const { mutate: complete, isPending: completing } = useMutation({
    mutationFn: () => completeViva(token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['student-viva-token', token] }),
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
    </div>
  )
  if (isError || !viva) return (
    <div className="max-w-4xl mx-auto px-4 py-8 text-sm text-red-600">
      Viva session not found or expired.
    </div>
  )

  const questions: VivaQuestion[] = viva.ai_questions ?? []
  const answered   = new Set((viva.ai_responses ?? []).map((r: { question_id: string }) => r.question_id))
  const currentQ   = questions[currentQIdx] ?? null
  const allDone    = questions.length > 0 && questions.every((q) => answered.has(q.id))
  const isExpired  = new Date(viva.expires_at) < new Date()

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      <div className="flex items-center gap-3">
        <Video className="h-5 w-5 text-indigo-500" />
        <h1 className="text-xl font-bold text-gray-900">Viva Session</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          viva.status === 'GUIDE_RATIFIED' ? 'bg-green-100 text-green-700' :
          viva.status === 'COMPLETED'      ? 'bg-blue-100 text-blue-700' :
          viva.status === 'IN_PROGRESS'    ? 'bg-indigo-100 text-indigo-700' :
          'bg-gray-100 text-gray-600'
        }`}>
          {viva.status.replace('_', ' ')}
        </span>
      </div>

      <div className="text-xs text-gray-600">
        Expires {new Date(viva.expires_at).toLocaleString()}
        {isExpired && <span className="ml-2 text-red-500 font-medium">· EXPIRED</span>}
      </div>

      {/* DPDP Consent gate */}
      {!viva.consent_recorded && viva.status === 'SCHEDULED' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 space-y-3">
          <p className="text-sm font-medium text-amber-800">Consent Required (DPDP Act 2023)</p>
          <p className="text-sm text-amber-700">
            This session may record your audio/video responses. By proceeding, you consent to recording
            and processing of your responses for evaluation purposes.
          </p>
          <Button onClick={() => consent()} disabled={consenting}>
            {consenting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            I Consent — Start Viva
          </Button>
        </div>
      )}

      {/* Completed / ratified */}
      {(viva.status === 'COMPLETED' || viva.status === 'GUIDE_RATIFIED' || viva.status === 'EVALUATED') && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-5 space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-600" />
            <p className="text-sm font-medium text-green-800">
              {viva.status === 'GUIDE_RATIFIED' ? 'Viva ratified by guide' : 'Viva session completed'}
            </p>
          </div>
          {viva.status === 'GUIDE_RATIFIED' && viva.overall_guide_score !== null && (
            <p className="text-2xl font-bold text-gray-900 pl-7">
              {viva.overall_guide_score} / 10
            </p>
          )}
        </div>
      )}

      {/* Active Q&A */}
      {viva.status === 'IN_PROGRESS' && !allDone && currentQ && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <div className="flex items-center justify-between text-xs text-gray-600">
            <span>Question {currentQIdx + 1} of {questions.length}</span>
            <span>{answered.size} answered</span>
          </div>
          <p className="text-base font-medium text-gray-900">{currentQ.text}</p>
          {currentQ.source === 'followup' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
              Follow-up
            </span>
          )}
          <textarea
            rows={5}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            placeholder="Type your response here…"
            disabled={responding}
          />
          <div className="flex justify-end">
            <Button
              onClick={() => respond()}
              disabled={responding || !response.trim()}
            >
              {responding ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Submit Response
            </Button>
          </div>
        </div>
      )}

      {/* All answered — finish */}
      {viva.status === 'IN_PROGRESS' && allDone && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 space-y-3">
          <p className="text-sm font-medium text-indigo-800">
            All {questions.length} questions answered.
          </p>
          <Button onClick={() => complete()} disabled={completing}>
            {completing ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Complete Viva
          </Button>
        </div>
      )}

      {/* Progress summary */}
      {questions.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
          {questions.map((q, i) => (
            <div
              key={q.id}
              className={`px-5 py-3 flex items-start gap-3 text-sm ${
                i === currentQIdx && viva.status === 'IN_PROGRESS' ? 'bg-indigo-50' : ''
              }`}
            >
              <span className={`flex-shrink-0 h-5 w-5 rounded-full flex items-center justify-center text-xs font-bold ${
                answered.has(q.id) ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'
              }`}>
                {i + 1}
              </span>
              <p className="text-gray-700">{q.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
