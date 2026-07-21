// Advisory AI evaluation panel — shown inside the evaluator's grading row.
//
// Read-only by design: it surfaces the AI's suggestion but never sets a mark.
// "Accept AI marks" only prefills the evaluator's own input, which they can then
// change or clear. The AI results stay visible regardless of what the evaluator
// enters — the human decision and the AI advice never overwrite each other.
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, ChevronDown, ChevronRight, RefreshCw, Loader2, AlertTriangle } from 'lucide-react'
import { getAiEvaluation, reEvaluateSubmission } from '@/lib/api/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { AiEvaluation } from '@/types/coursework'

const IN_PROGRESS = new Set(['PENDING', 'EXTRACTING', 'EVALUATING'])

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">{title}</p>
      <ul className="mt-0.5 list-disc list-inside space-y-0.5">
        {items.map((t, i) => <li key={i} className="text-xs text-gray-700">{t}</li>)}
      </ul>
    </div>
  )
}

function confidenceTone(c?: string | null) {
  return c === 'HIGH' ? 'text-green-700 bg-green-50'
    : c === 'LOW' ? 'text-orange-700 bg-orange-50'
    : 'text-amber-700 bg-amber-50'
}

export function CourseworkAiPanel({
  submissionId,
  onAcceptMarks,
}: {
  submissionId: string
  onAcceptMarks?: (marks: number) => void
}) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data: ai } = useQuery<AiEvaluation | null>({
    queryKey: ['ai-evaluation', submissionId],
    queryFn: () => getAiEvaluation(submissionId),
    // Poll while the background job is still running; stop once terminal.
    refetchInterval: (q) => (IN_PROGRESS.has((q.state.data as AiEvaluation | null)?.status ?? '') ? 5000 : false),
  })

  const retry = useMutation({
    mutationFn: () => reEvaluateSubmission(submissionId),
    onSuccess: () => {
      addToast('AI re-evaluation queued.', 'success')
      qc.invalidateQueries({ queryKey: ['ai-evaluation', submissionId] })
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  if (!ai) return null  // no AI row yet (older submission / not enrolled path)

  const running = IN_PROGRESS.has(ai.status)
  const failed = ai.status === 'FAILED'

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-indigo-50"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5 text-indigo-500" /> : <ChevronRight className="h-3.5 w-3.5 text-indigo-500" />}
        <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
        <span className="text-xs font-semibold text-indigo-800">AI Evaluation (advisory)</span>
        {running && <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />}
        {ai.status === 'COMPLETED' && ai.overall_suggested_marks != null && (
          <span className="text-xs text-indigo-700">
            · Suggests {ai.overall_suggested_marks} ({ai.percentage}%)
          </span>
        )}
        {failed && <span className="text-xs text-orange-600">· Failed</span>}
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-3">
          {running && (
            <p className="text-xs text-gray-600">AI is analysing this submission… ({ai.status.toLowerCase()})</p>
          )}

          {failed && (
            <div className="rounded-md bg-orange-50 border border-orange-200 px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-xs text-orange-800">AI evaluation failed — grade this manually.</p>
                {ai.error_log && <p className="text-[11px] text-orange-600 mt-0.5 break-words">{ai.error_log}</p>}
              </div>
              <button
                type="button"
                onClick={() => retry.mutate()}
                disabled={retry.isPending}
                className="text-xs font-medium text-indigo-600 hover:text-indigo-700 flex items-center gap-1 shrink-0"
              >
                <RefreshCw className="h-3 w-3" /> Retry
              </button>
            </div>
          )}

          {ai.status === 'COMPLETED' && (
            <>
              {/* Submission summary */}
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-600">
                {ai.file_type && <span>Type: <b className="text-gray-800">{ai.file_type}</b></span>}
                {ai.word_count != null && <span>Words: <b className="text-gray-800">{ai.word_count}</b></span>}
                {ai.processing_ms != null && <span>Processed in {(ai.processing_ms / 1000).toFixed(1)}s</span>}
                {ai.provider_used && <span>Provider: <b className="text-gray-800">{ai.provider_used}</b></span>}
                {ai.ai_model && <span>Model: {ai.ai_model}</span>}
                {ai.fallback_chain && ai.fallback_chain.includes('→') && (
                  <span className="text-gray-400">Chain: {ai.fallback_chain}</span>
                )}
              </div>

              {/* Suggested marks */}
              <div className="rounded-md bg-white border border-gray-100 px-3 py-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-xs font-semibold text-gray-700">
                    Suggested: {ai.overall_suggested_marks} · {ai.percentage}%
                    <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${confidenceTone(ai.confidence_level)}`}>
                      {ai.confidence_level} confidence
                    </span>
                  </p>
                  {onAcceptMarks && ai.overall_suggested_marks != null && (
                    <button
                      type="button"
                      onClick={() => onAcceptMarks(ai.overall_suggested_marks as number)}
                      className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
                    >
                      Accept AI marks →
                    </button>
                  )}
                </div>
                {ai.suggested_marks && ai.suggested_marks.length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {ai.suggested_marks.map((q) => (
                      <div key={q.question_number} className="text-[11px] text-gray-600">
                        <b className="text-gray-800">Q{q.question_number}: {q.suggested}/{q.max}</b>
                        {q.reason && <span> — {q.reason}</span>}
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-gray-400 mt-1">Advisory only — you decide the final marks.</p>
              </div>

              {/* Feedback */}
              {ai.feedback && (
                <div className="grid sm:grid-cols-2 gap-3">
                  <List title="Strengths" items={ai.feedback.strengths} />
                  <List title="Weaknesses" items={ai.feedback.weaknesses} />
                  <List title="Missing concepts" items={ai.feedback.missing_concepts} />
                  <List title="Suggestions" items={ai.feedback.suggestions} />
                  {ai.feedback.writing_quality && (
                    <div><p className="text-[11px] font-semibold text-gray-500 uppercase">Writing quality</p>
                      <p className="text-xs text-gray-700">{ai.feedback.writing_quality}</p></div>
                  )}
                  {ai.feedback.technical_correctness && (
                    <div><p className="text-[11px] font-semibold text-gray-500 uppercase">Technical correctness</p>
                      <p className="text-xs text-gray-700">{ai.feedback.technical_correctness}</p></div>
                  )}
                </div>
              )}

              {/* Rubric */}
              {ai.rubric_scores && ai.rubric_scores.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Rubric</p>
                  <div className="mt-1 grid sm:grid-cols-2 gap-1">
                    {ai.rubric_scores.map((c, i) => (
                      <div key={i} className="text-[11px] text-gray-700 flex justify-between gap-2">
                        <span>{c.criterion}</span><b>{c.score}/{c.max}</b>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bloom + CO (advisory) */}
              <div className="grid sm:grid-cols-2 gap-3">
                {ai.bloom_analysis && (ai.bloom_analysis.expected_level || ai.bloom_analysis.detected_level) && (
                  <div>
                    <p className="text-[11px] font-semibold text-gray-500 uppercase">Bloom's (advisory)</p>
                    <p className="text-xs text-gray-700">
                      Expected: {ai.bloom_analysis.expected_level ?? '—'} · Detected: {ai.bloom_analysis.detected_level ?? '—'}
                      {ai.bloom_analysis.alignment_percent != null && <> · {ai.bloom_analysis.alignment_percent}% aligned</>}
                    </p>
                  </div>
                )}
                {ai.co_analysis && (
                  <div>
                    <p className="text-[11px] font-semibold text-gray-500 uppercase">Course outcomes (advisory)</p>
                    <p className="text-xs text-gray-700">
                      {ai.co_analysis.covered?.length ? `Covered: ${ai.co_analysis.covered.join(', ')}` : ''}
                      {ai.co_analysis.weak?.length ? ` · Weak: ${ai.co_analysis.weak.join(', ')}` : ''}
                      {ai.co_analysis.missing?.length ? ` · Missing: ${ai.co_analysis.missing.join(', ')}` : ''}
                    </p>
                  </div>
                )}
              </div>

              {/* Similarity + plagiarism */}
              <div className="text-[11px] text-gray-600">
                {ai.similarity_score != null ? (
                  <span>Internal similarity: <b className={ai.similarity_score > 0.7 ? 'text-red-600' : 'text-gray-800'}>
                    {(ai.similarity_score * 100).toFixed(1)}%</b>
                    {ai.similarity_matches?.length ? ` (top match ${(ai.similarity_matches[0].similarity * 100).toFixed(1)}%)` : ''}
                  </span>
                ) : <span>Internal similarity: no other submissions to compare yet.</span>}
                <span className="ml-3">External plagiarism: <b className="text-gray-500">{ai.plagiarism_status}</b></span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
