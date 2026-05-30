import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, CheckCircle2, AlertTriangle, Loader2, Shield, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import { ConfidenceBadge } from '@/components/labs/ConfidenceBadge'
import { useReviewPanel, useSubmissionFileUrl } from '@/hooks/labs'
import { useUpdateScores, useRatify } from '@/hooks/labs'
import type { CriterionScore, RubricCriterion } from '@/types/labs'

// ── Criterion row with editable human score ───────────────────────────────────

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
          <p className="text-xs text-gray-400 mt-0.5">{rubric.description}</p>
        </div>
        <span className="text-xs text-gray-400 shrink-0">/ {rubric.max_marks}</span>
      </div>

      {/* AI score + justification */}
      {aiScore != null && (
        <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-blue-700">AI Score</span>
            <span className="text-sm font-bold text-blue-900">{aiScore}</span>
          </div>
          {score?.ai_justification && (
            <p className="text-xs text-blue-700 mt-1 leading-relaxed">{score.ai_justification}</p>
          )}
        </div>
      )}

      {/* Human override */}
      <div className="flex items-start gap-2">
        <div className="w-20 shrink-0">
          <label className="text-xs text-gray-500 mb-0.5 block">Human score</label>
          <input
            type="number"
            min={0}
            max={rubric.max_marks}
            step={0.5}
            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:bg-gray-50"
            value={humanScore}
            onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value), humanNote)}
            disabled={readOnly}
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-gray-500 mb-0.5 block">Note (optional)</label>
          <input
            type="text"
            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:bg-gray-50"
            placeholder="Faculty note..."
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

export default function LabReviewPanel() {
  const { submissionId } = useParams<{ submissionId: string }>()
  const navigate = useNavigate()
  const sid = submissionId ?? ''

  const { data: panel, isLoading, isError } = useReviewPanel(sid)

  // draft human scores keyed by criterion_id
  const [draftScores, setDraftScores] = useState<Record<string, { score: number | ''; note: string }>>({})
  const [ratifyNote, setRatifyNote] = useState('')
  const [ratifyConfirm, setRatifyConfirm] = useState(false)

  const { mutate: saveScores, isPending: saving } = useUpdateScores(sid)
  const { mutate: ratify, isPending: ratifying }  = useRatify(sid)

  const [fileUrlRequested, setFileUrlRequested] = useState(false)
  const { data: fileUrlData, isFetching: fetchingFileUrl } = useSubmissionFileUrl(sid, fileUrlRequested)

  // Auto-open the file as soon as the presigned URL resolves
  useEffect(() => {
    if (fileUrlData?.url && fileUrlRequested) {
      window.open(fileUrlData.url, '_blank', 'noreferrer')
      setFileUrlRequested(false)
    }
  }, [fileUrlData, fileUrlRequested])

  // Seed draft scores from evaluation data
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
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError || !panel) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-red-400" />
        <p className="text-sm text-gray-500">Failed to load review panel.</p>
      </div>
    )
  }

  const { submission, assignment, grade_entry } = panel
  const evaluation = submission.evaluation
  const isRatified = submission.status === 'RATIFIED'
  const canRatify  = submission.status === 'REVIEWED' && !isRatified
  const [contextOpen, setContextOpen] = useState(false)

  function handleScoreChange(criterionId: string, score: number | '', note: string) {
    setDraftScores((prev) => ({ ...prev, [criterionId]: { score, note } }))
  }

  function handleSaveScores() {
    const scores = Object.entries(draftScores)
      .filter(([, v]) => v.score !== '')
      .map(([criterion_id, v]) => ({
        criterion_id,
        human_score: Number(v.score),
        human_note: v.note || undefined,
      }))
    saveScores({ scores })
  }

  function handleRatify() {
    if (!ratifyConfirm) { setRatifyConfirm(true); return }
    ratify({ ratification_note: ratifyNote || undefined }, {
      onSuccess: () => setRatifyConfirm(false),
    })
  }

  const submittedContent = submission.content_text
  const isCode = assignment.submission_type === 'CODE'

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      {/* Nav */}
      <Button
        variant="ghost"
        size="sm"
        className="-ml-1"
        onClick={() => navigate(`/labs/${assignment.id}`)}
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        {assignment.title}
      </Button>

      {/* Title bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-900">Review Panel</h1>
        <LabStatusBadge status={assignment.status} />
        <AIScanBadge status={submission.ai_scan_status} probability={submission.ai_scan_result?.probability} />
        {evaluation?.confidence_level && <ConfidenceBadge level={evaluation.confidence_level} />}
        {isRatified && (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-800 border border-green-200 px-2.5 py-0.5 text-xs font-semibold">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Ratified
          </span>
        )}
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
                <span className="ml-2 text-xs text-gray-400">
                  {[assignment.course_code, assignment.course_title].filter(Boolean).join(' · ')}
                </span>
              )}
            </div>
            {contextOpen
              ? <ChevronUp className="h-4 w-4 text-gray-400 shrink-0" />
              : <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />
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

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        {/* ── Left: Submission content ─────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Student Submission</span>
              <span className="text-xs text-gray-400 font-mono">{submission.student_user_id}</span>
            </div>

            {submittedContent ? (
              isCode ? (
                <pre className="p-4 text-xs font-mono text-gray-800 overflow-auto max-h-[70vh] bg-gray-950 text-green-300 leading-relaxed">
                  {submittedContent}
                </pre>
              ) : (
                <div className="p-4 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap max-h-[70vh] overflow-auto">
                  {submittedContent}
                </div>
              )
            ) : submission.content_url ? (
              <div className="p-4 flex flex-col items-center gap-2 text-sm text-gray-500">
                <p className="text-xs text-gray-400">Student submitted a file upload.</p>
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
              <div className="p-4 text-sm text-gray-400 text-center">No content available.</div>
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
                    <span className={`h-2 w-2 rounded-full shrink-0 ${tr.passed ? 'bg-green-500' : 'bg-red-400'}`} />
                    <span className="text-sm text-gray-700 flex-1">{tr.name}</span>
                    <span className="text-xs text-gray-400">{tr.points_awarded} pts</span>
                    {tr.timed_out && <span className="text-xs text-orange-600">Timeout</span>}
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
                <span className="ml-2 text-xs text-gray-400">
                  Complexity: {evaluation.static_analysis.complexity_label} ({evaluation.static_analysis.complexity_score})
                </span>
              </div>
              {evaluation.static_analysis.parse_error ? (
                <div className="px-4 py-3 text-sm text-red-600">{evaluation.static_analysis.parse_error}</div>
              ) : evaluation.static_analysis.issues.length > 0 ? (
                <div className="divide-y divide-gray-100 max-h-40 overflow-auto">
                  {evaluation.static_analysis.issues.map((issue, i) => (
                    <div key={i} className="px-4 py-2 text-xs text-gray-600 font-mono">
                      L{issue.line}: {issue.message}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-3 text-xs text-gray-400">No issues found.</div>
              )}
            </div>
          )}
        </div>

        {/* ── Right: Scores + ratification ────────────────────────────── */}
        <div className="w-full lg:w-96 shrink-0 space-y-4">

          {/* AI overview */}
          {evaluation && (
            <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-700">AI Evaluation Overview</h2>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-blue-50 px-3 py-2">
                  <p className="text-xs text-blue-600">AI Score</p>
                  <p className="text-lg font-bold text-blue-900">
                    {evaluation.overall_ai_score != null ? evaluation.overall_ai_score.toFixed(1) : '—'}
                  </p>
                </div>
                <div className="rounded-lg bg-green-50 px-3 py-2">
                  <p className="text-xs text-green-600">Human Score</p>
                  <p className="text-lg font-bold text-green-900">
                    {evaluation.overall_human_score != null ? evaluation.overall_human_score.toFixed(1) : '—'}
                  </p>
                </div>
              </div>
              {evaluation.plagiarism_score != null && (
                <div className={`rounded-lg px-3 py-2 ${
                  evaluation.plagiarism_score > 0.7
                    ? 'bg-red-50 border border-red-200'
                    : 'bg-gray-50'
                }`}>
                  <p className="text-xs text-gray-500">Plagiarism similarity</p>
                  <p className={`text-sm font-semibold ${
                    evaluation.plagiarism_score > 0.7 ? 'text-red-700' : 'text-gray-700'
                  }`}>
                    {(evaluation.plagiarism_score * 100).toFixed(1)}%
                  </p>
                  {evaluation.plagiarism_matches && evaluation.plagiarism_matches.length > 0 && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      Top match: {(evaluation.plagiarism_matches[0].similarity * 100).toFixed(1)}%
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Per-criterion scores */}
          {evaluation && (
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-1">Rubric Scores</h2>
              {assignment.rubric.map((rubric) => {
                const score = evaluation.rubric_scores.find((s) => s.criterion_id === rubric.criterion_id)
                const draft = draftScores[rubric.criterion_id] ?? { score: score?.human_score ?? '', note: score?.human_note ?? '' }
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

              {!isRatified && (
                <Button
                  className="mt-3 w-full"
                  variant="outline"
                  onClick={handleSaveScores}
                  disabled={saving}
                >
                  {saving ? 'Saving…' : 'Save Scores'}
                </Button>
              )}
            </div>
          )}

          {/* Ratification */}
          {isRatified && grade_entry ? (
            <div className="rounded-xl border border-green-200 bg-green-50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="h-5 w-5 text-green-700" />
                <h2 className="text-sm font-semibold text-green-800">Grade Ratified</h2>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className="text-xs text-green-600">Final Score</p>
                  <p className="font-bold text-green-900 text-lg">
                    {grade_entry.final_score} / {grade_entry.max_marks}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-green-600">Ratified at</p>
                  <p className="text-green-800 text-xs">{new Date(grade_entry.ratified_at).toLocaleString()}</p>
                </div>
              </div>
              {grade_entry.ratification_note && (
                <p className="mt-2 text-xs text-green-700 italic">"{grade_entry.ratification_note}"</p>
              )}
            </div>
          ) : canRatify ? (
            <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
              <div className="flex items-start gap-2">
                <Shield className="h-4 w-4 text-gray-400 mt-0.5 shrink-0" />
                <p className="text-xs text-gray-500 leading-relaxed">
                  Ratification is permanent and writes to the grade ledger. Verify all human scores before proceeding.
                </p>
              </div>

              {ratifyConfirm && (
                <div className="space-y-2">
                  <label className="text-xs text-gray-600 font-medium">Ratification note (optional)</label>
                  <textarea
                    className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-400"
                    rows={2}
                    placeholder="Faculty note for this grade…"
                    value={ratifyNote}
                    onChange={(e) => setRatifyNote(e.target.value)}
                  />
                </div>
              )}

              <Button
                className={`w-full ${
                  ratifyConfirm
                    ? 'bg-green-700 hover:bg-green-800 text-white'
                    : ''
                }`}
                variant={ratifyConfirm ? 'default' : 'outline'}
                onClick={handleRatify}
                disabled={ratifying}
              >
                {ratifying
                  ? 'Ratifying…'
                  : ratifyConfirm
                    ? 'Confirm Ratification'
                    : 'Ratify Grade'}
              </Button>
              {ratifyConfirm && (
                <button
                  type="button"
                  className="w-full text-xs text-gray-400 hover:text-gray-600 py-1"
                  onClick={() => { setRatifyConfirm(false); setRatifyNote('') }}
                >
                  Cancel
                </button>
              )}
            </div>
          ) : !isRatified && evaluation && (
            <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
              <p className="text-xs text-gray-400 text-center">
                Save scores to unlock ratification.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
