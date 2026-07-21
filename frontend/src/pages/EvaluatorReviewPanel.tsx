import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, CheckCircle2, AlertTriangle, Loader2, Send, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { ConfidenceBadge } from '@/components/labs/ConfidenceBadge'
import { addToast } from '@/hooks/useToast'
import { useEvaluatorReviewPanel, useEvaluatorRecommend, useSubmissionFileUrl } from '@/hooks/labs'
import type { CriterionScore, RubricCriterion } from '@/types/labs'

// ── Criterion row ─────────────────────────────────────────────────────────────

function CriterionRow({
  rubric,
  score,
  humanScore,
  humanNote,
  onChange,
  readOnly,
}: {
  rubric: RubricCriterion
  score: CriterionScore | undefined
  humanScore: number | ''
  humanNote: string
  onChange: (score: number | '', note: string) => void
  readOnly: boolean
}) {
  const aiScore = score?.ai_score ?? null
  return (
    <div className="py-4 border-b border-gray-100 last:border-0">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <p className="text-sm font-medium text-gray-800">{rubric.name}</p>
          <p className="text-xs text-gray-600 mt-0.5">{rubric.description}</p>
        </div>
        <span className="text-xs text-gray-600 shrink-0">/ {rubric.max_marks}</span>
      </div>

      {aiScore != null && (
        <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-blue-700">AI Score</span>
            <span className="text-sm font-bold text-blue-900">{aiScore}</span>
          </div>
          {score?.ai_justification && (
            <p className="text-xs text-blue-700 mt-1 leading-relaxed">
              {score.ai_justification}
            </p>
          )}
        </div>
      )}

      <div className="flex items-start gap-2">
        <div className="w-24 shrink-0">
          <label className="text-xs text-gray-500 mb-0.5 block">My score</label>
          <input
            type="number"
            min={0}
            max={rubric.max_marks}
            step={0.5}
            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 disabled:bg-gray-50"
            value={humanScore}
            onChange={(e) =>
              onChange(e.target.value === '' ? '' : Number(e.target.value), humanNote)
            }
            disabled={readOnly}
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-gray-500 mb-0.5 block">Evaluator note</label>
          <input
            type="text"
            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 disabled:bg-gray-50"
            placeholder="Add evaluation note…"
            value={humanNote}
            onChange={(e) => onChange(humanScore, e.target.value)}
            disabled={readOnly}
          />
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EvaluatorReviewPanel() {
  const { submissionId } = useParams<{ submissionId: string }>()
  const navigate = useNavigate()
  const sid = submissionId ?? ''

  const { data: panel, isLoading, isError } = useEvaluatorReviewPanel(sid)

  const [draftScores, setDraftScores] = useState<
    Record<string, { score: number | ''; note: string }>
  >({})
  const [recommendNote, setRecommendNote] = useState('')
  const [confirmSubmit, setConfirmSubmit] = useState(false)

  const { mutate: recommend, isPending: recommending } = useEvaluatorRecommend(sid)
  const [contextOpen, setContextOpen] = useState(false)

  const [fileUrlRequested, setFileUrlRequested] = useState(false)
  const { data: fileUrlData, isFetching: fetchingFileUrl } = useSubmissionFileUrl(sid, fileUrlRequested)

  useEffect(() => {
    if (fileUrlData?.url && fileUrlRequested) {
      window.open(fileUrlData.url, '_blank', 'noreferrer')
      setFileUrlRequested(false)
    }
  }, [fileUrlData, fileUrlRequested])

  useEffect(() => {
    if (!panel?.submission?.evaluation) return
    const init: Record<string, { score: number | ''; note: string }> = {}
    for (const cs of panel.submission.evaluation.rubric_scores) {
      init[cs.criterion_id] = {
        score: cs.human_score ?? '',
        note:  cs.human_note ?? '',
      }
    }
    setDraftScores(init)
  }, [panel?.submission?.evaluation])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
      </div>
    )
  }

  if (isError || !panel) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-red-400" />
        <p className="text-sm text-gray-500">Failed to load submission.</p>
      </div>
    )
  }

  const { submission, assignment, grade_entry } = panel
  const evaluation = submission.evaluation
  const isRatified = submission.status === 'RATIFIED'
  const isCode = assignment.submission_type === 'CODE'

  function handleScoreChange(criterionId: string, score: number | '', note: string) {
    setDraftScores((prev) => ({ ...prev, [criterionId]: { score, note } }))
  }

  function handleSubmitRecommendation() {
    if (!confirmSubmit) { setConfirmSubmit(true); return }
    const scores = Object.entries(draftScores)
      .filter(([, v]) => v.score !== '')
      .map(([criterion_id, v]) => ({
        criterion_id,
        human_score: Number(v.score),
        human_note: v.note || undefined,
      }))
    recommend(
      { scores, recommendation_note: recommendNote || undefined },
      {
        onSuccess: () => {
          setConfirmSubmit(false)
          addToast('Recommendation submitted.', 'success')
        },
      }
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      {/* Nav */}
      <Button
        variant="ghost"
        size="sm"
        className="-ml-1"
        onClick={() => navigate(`/evaluator/${assignment.id}/submissions`)}
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        {assignment.title}
      </Button>

      {/* Role banner */}
      <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-2.5 flex items-center gap-2">
        <span className="text-xs font-semibold text-orange-700 uppercase tracking-wide">
          Evaluator View
        </span>
        <span className="text-xs text-orange-600">
          You can recommend scores. A faculty member will finalize the grade.
        </span>
      </div>

      {/* Assignment context collapsible */}
      {(assignment.description || assignment.instructions) && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <button
            type="button"
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
            onClick={() => setContextOpen((v) => !v)}
          >
            <div>
              <span className="text-sm font-semibold text-gray-700">{assignment.title}</span>
              {(assignment.course_code || assignment.course_title) && (
                <span className="ml-2 text-xs text-gray-600">
                  {[assignment.course_code, assignment.course_title].filter(Boolean).join(' · ')}
                </span>
              )}
            </div>
            {contextOpen
              ? <ChevronUp className="h-4 w-4 text-gray-600 shrink-0" />
              : <ChevronDown className="h-4 w-4 text-gray-600 shrink-0" />
            }
          </button>
          {contextOpen && (
            <div className="border-t border-gray-100 divide-y divide-gray-100">
              {assignment.description && (
                <div className="px-4 py-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Problem Statement</p>
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{assignment.description}</p>
                </div>
              )}
              {assignment.instructions && (
                <div className="px-4 py-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Student Instructions</p>
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{assignment.instructions}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Title bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-900">Review Panel</h1>
        <LabStatusBadge status={assignment.status} />
        <AIScanBadge
          status={submission.ai_scan_status}
          probability={submission.ai_scan_result?.probability}
        />
        {evaluation?.confidence_level && (
          <ConfidenceBadge level={evaluation.confidence_level} />
        )}
        {isRatified && (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-800 border border-green-200 px-2.5 py-0.5 text-xs font-semibold">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Ratified by Faculty
          </span>
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        {/* ── Left: Submission content ──────────────────────────────── */}
        <div className="flex-1 min-w-0">
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Student Submission</span>
              <span className="text-xs text-gray-600 font-mono">
                {submission.student_user_id}
              </span>
            </div>

            {submission.content_text ? (
              isCode ? (
                <pre className="p-4 text-xs font-mono overflow-auto max-h-[70vh] bg-gray-950 text-green-300 leading-relaxed">
                  {submission.content_text}
                </pre>
              ) : (
                <div className="p-4 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap max-h-[70vh] overflow-auto">
                  {submission.content_text}
                </div>
              )
            ) : submission.content_url ? (
              <div className="p-4 flex flex-col items-center gap-2 text-sm text-gray-500">
                <p className="text-xs text-gray-600">Student submitted a file upload.</p>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={fetchingFileUrl}
                  onClick={() => {
                    if (fileUrlData?.url) {
                      window.open(fileUrlData.url, '_blank', 'noreferrer')
                    } else {
                      setFileUrlRequested(true)
                    }
                  }}
                >
                  {fetchingFileUrl ? (
                    <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Generating link…</>
                  ) : (
                    'Open Uploaded File'
                  )}
                </Button>
              </div>
            ) : (
              <div className="p-4 text-sm text-gray-600 text-center">
                No content available.
              </div>
            )}
          </div>

          {/* Test results (CODE) */}
          {isCode && evaluation?.test_results && evaluation.test_results.length > 0 && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                <span className="text-sm font-medium text-gray-700">Test Results</span>
              </div>
              <div className="divide-y divide-gray-100">
                {evaluation.test_results.map((tr) => (
                  <div key={tr.id} className="px-4 py-2.5 flex items-center gap-3">
                    <span
                      className={`h-2 w-2 rounded-full shrink-0 ${
                        tr.passed ? 'bg-green-500' : 'bg-red-400'
                      }`}
                    />
                    <span className="text-sm text-gray-700 flex-1">{tr.name}</span>
                    <span className="text-xs text-gray-600">{tr.points_awarded} pts</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Static analysis (CODE) */}
          {isCode && evaluation?.static_analysis && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                <span className="text-sm font-medium text-gray-700">Static Analysis</span>
                <span className="ml-2 text-xs text-gray-600">
                  Complexity: {evaluation.static_analysis.complexity_label} (
                  {evaluation.static_analysis.complexity_score})
                </span>
              </div>
              {evaluation.static_analysis.issues.length > 0 ? (
                <div className="divide-y divide-gray-100 max-h-40 overflow-auto">
                  {evaluation.static_analysis.issues.map((issue, i) => (
                    <div key={i} className="px-4 py-2 text-xs text-gray-600 font-mono">
                      L{issue.line}: {issue.message}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-3 text-xs text-gray-600">No issues found.</div>
              )}
            </div>
          )}
        </div>

        {/* ── Right: Scores + recommendation ────────────────────────── */}
        <div className="w-full lg:w-96 shrink-0 space-y-4">

          {/* AI overview */}
          {evaluation && (
            <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-700">AI Evaluation Overview</h2>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-blue-50 px-3 py-2">
                  <p className="text-xs text-blue-600">AI Score</p>
                  <p className="text-lg font-bold text-blue-900">
                    {evaluation.overall_ai_score != null
                      ? evaluation.overall_ai_score.toFixed(1)
                      : '—'}
                  </p>
                </div>
                <div className="rounded-lg bg-orange-50 px-3 py-2">
                  <p className="text-xs text-orange-600">Your Score</p>
                  <p className="text-lg font-bold text-orange-900">
                    {evaluation.overall_human_score != null
                      ? evaluation.overall_human_score.toFixed(1)
                      : '—'}
                  </p>
                </div>
              </div>
              {evaluation.plagiarism_score != null && (
                <div
                  className={`rounded-lg px-3 py-2 ${
                    evaluation.plagiarism_score > 0.7
                      ? 'bg-red-50 border border-red-200'
                      : 'bg-gray-50'
                  }`}
                >
                  <p className="text-xs text-gray-500">Plagiarism similarity</p>
                  <p
                    className={`text-sm font-semibold ${
                      evaluation.plagiarism_score > 0.7
                        ? 'text-red-700'
                        : 'text-gray-700'
                    }`}
                  >
                    {(evaluation.plagiarism_score * 100).toFixed(1)}%
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Per-criterion scores */}
          {evaluation && (
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-1">
                {isRatified ? 'Scores' : 'Enter Your Scores'}
              </h2>
              {assignment.rubric.map((rubric) => {
                const score = evaluation.rubric_scores.find(
                  (s) => s.criterion_id === rubric.criterion_id
                )
                const draft = draftScores[rubric.criterion_id] ?? {
                  score: score?.human_score ?? '',
                  note: score?.human_note ?? '',
                }
                return (
                  <CriterionRow
                    key={rubric.criterion_id}
                    rubric={rubric}
                    score={score}
                    humanScore={draft.score}
                    humanNote={draft.note}
                    onChange={(s, n) => handleScoreChange(rubric.criterion_id, s, n)}
                    readOnly={isRatified}
                  />
                )
              })}
            </div>
          )}

          {/* Grade ratified by faculty */}
          {isRatified && grade_entry ? (
            <div className="rounded-xl border border-green-200 bg-green-50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="h-5 w-5 text-green-700" />
                <h2 className="text-sm font-semibold text-green-800">
                  Grade Finalised by Faculty
                </h2>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className="text-xs text-green-600">Final Score</p>
                  <p className="font-bold text-green-900 text-lg">
                    {grade_entry.final_score} / {grade_entry.max_marks}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-green-600">Finalised at</p>
                  <p className="text-green-800 text-xs">
                    {new Date(grade_entry.ratified_at).toLocaleString()}
                  </p>
                </div>
              </div>
              {grade_entry.ratification_note && (
                <p className="mt-2 text-xs text-green-700 italic">
                  "{grade_entry.ratification_note}"
                </p>
              )}
            </div>
          ) : !isRatified && evaluation ? (
            /* Recommendation submission */
            <div className="rounded-xl border border-orange-200 bg-orange-50 p-4 space-y-3">
              <p className="text-xs text-orange-700 leading-relaxed">
                Submit your score recommendation. Faculty will review and finalize the grade.
              </p>

              {confirmSubmit && (
                <div className="space-y-1.5">
                  <label className="text-xs text-orange-700 font-medium">
                    Recommendation note (optional)
                  </label>
                  <textarea
                    className="w-full rounded border border-orange-200 bg-white px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-300"
                    rows={2}
                    placeholder="Any notes for the faculty…"
                    value={recommendNote}
                    onChange={(e) => setRecommendNote(e.target.value)}
                  />
                </div>
              )}

              <Button
                className={`w-full gap-1.5 ${
                  confirmSubmit
                    ? 'bg-orange-600 hover:bg-orange-700 text-white'
                    : 'border-orange-300 text-orange-700 hover:bg-orange-100'
                }`}
                variant={confirmSubmit ? 'default' : 'outline'}
                onClick={handleSubmitRecommendation}
                disabled={recommending}
              >
                <Send className="h-3.5 w-3.5" />
                {recommending
                  ? 'Submitting…'
                  : confirmSubmit
                    ? 'Confirm Recommendation'
                    : 'Submit Recommendation'}
              </Button>

              {confirmSubmit && (
                <button
                  type="button"
                  className="w-full text-xs text-orange-400 hover:text-orange-600 py-1"
                  onClick={() => {
                    setConfirmSubmit(false)
                    setRecommendNote('')
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
