import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen, FileText, Video, Loader2,
  AlertCircle, CheckCircle2, Clock, ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getProblem,
  decideProblem,
  listDocumentsForGuide,
  listVivasForGuide,
  scheduleViva,
} from '@/lib/api/research'
import { addToast } from '@/hooks/useToast'
import type {
  GuideDecision,
  ResearchDocument,
  VivaSession,
} from '@/types/research'

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const PROBLEM_STATUS_COLOR: Record<string, string> = {
  DRAFT:              'bg-gray-100 text-gray-600',
  PENDING_REVIEW:     'bg-yellow-100 text-yellow-700',
  ACCEPTED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
  REJECTED:           'bg-red-100 text-red-600',
}

const DOC_STATUS_COLOR: Record<string, string> = {
  SUBMITTED:          'bg-gray-100 text-gray-600',
  EVALUATING:         'bg-blue-100 text-blue-700',
  EVALUATED:          'bg-indigo-100 text-indigo-700',
  GUIDE_REVIEWED:     'bg-yellow-100 text-yellow-700',
  APPROVED:           'bg-green-100 text-green-700',
  REVISION_REQUESTED: 'bg-orange-100 text-orange-700',
}

const VIVA_STATUS_COLOR: Record<string, string> = {
  SCHEDULED:      'bg-blue-100 text-blue-700',
  IN_PROGRESS:    'bg-yellow-100 text-yellow-700',
  COMPLETED:      'bg-indigo-100 text-indigo-700',
  ASR_PROCESSING: 'bg-purple-100 text-purple-700',
  EVALUATED:      'bg-teal-100 text-teal-700',
  GUIDE_RATIFIED: 'bg-green-100 text-green-700',
}

// ── Document row ──────────────────────────────────────────────────────────────

export function DocumentRow({ doc, onOpen }: { doc: ResearchDocument; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex items-center gap-3 min-w-0">
        <FileText className="h-4 w-4 text-gray-400 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {doc.file_name ?? `Document v${doc.version}`}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Version {doc.version} · Submitted {fmt(doc.submitted_at)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-4">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${DOC_STATUS_COLOR[doc.status] ?? 'bg-gray-100 text-gray-600'}`}>
          {doc.status.replace(/_/g, ' ')}
        </span>
        <ChevronRight className="h-4 w-4 text-gray-300" />
      </div>
    </button>
  )
}

// ── Viva row ──────────────────────────────────────────────────────────────────

export function VivaRow({ viva, onOpen }: { viva: VivaSession; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex items-center gap-3 min-w-0">
        <Video className="h-4 w-4 text-gray-400 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800">Viva Session</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Scheduled {fmt(viva.scheduled_at)}
            {viva.completed_at ? ` · Completed ${fmt(viva.completed_at)}` : ''}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-4">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${VIVA_STATUS_COLOR[viva.status] ?? 'bg-gray-100 text-gray-600'}`}>
          {viva.status.replace(/_/g, ' ')}
        </span>
        <ChevronRight className="h-4 w-4 text-gray-300" />
      </div>
    </button>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

export interface ResearchProblemPanelProps {
  problemId: string
}

export function ResearchProblemPanel({ problemId }: ResearchProblemPanelProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  // All state hooks unconditionally at top
  const [decisionChoice, setDecisionChoice] = useState<GuideDecision>('ACCEPT')
  const [decisionNote, setDecisionNote] = useState('')
  const [decisionOpen, setDecisionOpen] = useState(false)
  const [schedulingViva, setSchedulingViva] = useState(false)

  // All query hooks unconditionally at top
  const {
    data: problem,
    isLoading,
    isError,
    error: loadErr,
  } = useQuery({
    queryKey: ['research-problem', problemId],
    queryFn: () => getProblem(problemId!),
    enabled: !!problemId,
    retry: 1,
  })

  const { data: docsData } = useQuery({
    queryKey: ['research-docs-guide'],
    queryFn: () => listDocumentsForGuide({ limit: 200 }),
    enabled: !!problem,
    staleTime: 30_000,
  })

  const { data: vivasData } = useQuery({
    queryKey: ['research-vivas-guide'],
    queryFn: () => listVivasForGuide({ limit: 200 }),
    enabled: !!problem,
    staleTime: 30_000,
  })

  // All mutation hooks unconditionally at top
  const { mutate: submitDecision, isPending: decidingPending, isError: decideError } = useMutation({
    mutationFn: () =>
      decideProblem(problemId!, {
        decision: decisionChoice,
        guide_note: decisionNote || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-problem', problemId] })
      qc.invalidateQueries({ queryKey: ['research-problems'] })
      qc.invalidateQueries({ queryKey: ['guide-problems'] })
      setDecisionOpen(false)
      setDecisionNote('')
      addToast('Decision submitted.', 'success')
    },
  })

  const { mutate: doScheduleViva, isPending: vivaScheduling } = useMutation({
    mutationFn: (documentId: string) =>
      scheduleViva({ research_problem_id: problemId!, document_id: documentId }),
    onSuccess: (viva) => {
      qc.invalidateQueries({ queryKey: ['research-vivas-guide'] })
      qc.invalidateQueries({ queryKey: ['guide-vivas'] })
      setSchedulingViva(false)
      addToast('Viva session scheduled.', 'success')
      navigate(`/research/vivas/${viva.id}`)
    },
    onError: () => {
      setSchedulingViva(false)
      addToast('Failed to schedule viva.', 'error')
    },
  })

  // Derived data — safe because all hooks are above this point
  const problemDocs = (docsData?.items ?? []).filter(
    (d) => d.research_problem_id === problemId
  )
  const problemVivas = (vivasData?.items ?? []).filter(
    (v) => v.research_problem_id === problemId
  )
  const approvedDoc = problemDocs.find((d) => d.status === 'APPROVED')
  const canScheduleViva =
    problem?.status === 'ACCEPTED' && !!approvedDoc && problemVivas.length === 0

  // ── Loading state ──────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="px-4 py-16 flex items-center gap-3 text-gray-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading proposal…</span>
      </div>
    )
  }

  // ── Error / not found state ────────────────────────────────────────────────

  if (isError || !problem) {
    const msg = (() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const d = (loadErr as any)?.response?.data
        return d?.message ?? d?.detail?.message ?? 'Could not load the research proposal.'
      } catch {
        return 'Could not load the research proposal.'
      }
    })()
    return (
      <div className="px-4 py-10 space-y-4">
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-6 flex gap-3 text-red-700">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm">Proposal not found</p>
            <p className="text-sm mt-0.5 text-red-600">{msg}</p>
          </div>
        </div>
      </div>
    )
  }

  // ── Main render ────────────────────────────────────────────────────────────

  const isPendingReview = problem.status === 'PENDING_REVIEW'
  const isAccepted      = problem.status === 'ACCEPTED'

  return (
    <div className="space-y-6">

      {/* Title bar */}
      <div className="flex items-start gap-3 flex-wrap">
        <BookOpen className="h-5 w-5 text-gray-400 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-gray-900 flex-1">{problem.title}</h1>
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium shrink-0 ${PROBLEM_STATUS_COLOR[problem.status] ?? 'bg-gray-100 text-gray-600'}`}>
              {problem.status.replace(/_/g, ' ')}
            </span>
          </div>
          {problem.source === 'AI_GENERATED' && (
            <span className="text-xs text-indigo-500 font-medium">AI-generated proposal</span>
          )}
        </div>
      </div>

      {/* Meta row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Submitted</p>
          <p className="text-sm text-gray-800 mt-0.5">{fmt(problem.created_at)}</p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Updated</p>
          <p className="text-sm text-gray-800 mt-0.5">{fmt(problem.updated_at)}</p>
        </div>
        {problem.decided_at && (
          <div className="rounded-lg bg-gray-50 px-3 py-2">
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Decided</p>
            <p className="text-sm text-gray-800 mt-0.5">{fmt(problem.decided_at)}</p>
          </div>
        )}
        {problem.student_user_id && (
          <div className="rounded-lg bg-gray-50 px-3 py-2">
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Student ID</p>
            <p className="text-sm text-gray-800 mt-0.5 font-mono truncate">
              {problem.student_user_id.slice(0, 8)}…
            </p>
          </div>
        )}
      </div>

      {/* Abstract */}
      <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-1">
        <h2 className="text-sm font-semibold text-gray-700">Abstract</h2>
        <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">{problem.abstract}</p>
      </div>

      {/* Research questions */}
      {problem.research_questions.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Research Questions ({problem.research_questions.length})
          </h2>
          <ol className="space-y-2 list-decimal list-inside">
            {problem.research_questions.map((rq, i) => (
              <li key={i} className="text-sm text-gray-600">{rq.question}</li>
            ))}
          </ol>
        </div>
      )}

      {/* AI Evaluation */}
      {(problem.novelty_score !== null || problem.ai_recommendation) && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-sm font-semibold text-indigo-800">AI Evaluation</h2>
            {problem.ai_recommendation && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                problem.ai_recommendation === 'ACCEPT'
                  ? 'bg-green-100 text-green-800'
                  : problem.ai_recommendation === 'REJECT'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-orange-100 text-orange-800'
              }`}>
                AI: {problem.ai_recommendation}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { label: 'Novelty',      value: problem.novelty_score },
              { label: 'Feasibility',  value: problem.feasibility_score },
              { label: 'Clarity',      value: problem.clarity_score },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-white/60 px-2 py-2">
                <p className="text-xs text-indigo-500">{label}</p>
                <p className="text-lg font-bold text-indigo-900">
                  {value !== null && value !== undefined ? value.toFixed(1) : '—'}
                </p>
              </div>
            ))}
          </div>
          {problem.ai_reasoning && (
            <p className="text-xs text-indigo-700 leading-relaxed">{problem.ai_reasoning}</p>
          )}
        </div>
      )}

      {/* Guide decision history */}
      {(problem.guide_decision || problem.guide_note) && (
        <div className={`rounded-xl border px-5 py-4 space-y-2 ${
          problem.guide_decision === 'ACCEPT'
            ? 'border-green-200 bg-green-50'
            : problem.guide_decision === 'REJECT'
            ? 'border-red-200 bg-red-50'
            : 'border-orange-200 bg-orange-50'
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-gray-500 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-700">Guide Review Decision</h2>
            {problem.guide_decision && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                problem.guide_decision === 'ACCEPT'
                  ? 'bg-green-100 text-green-800'
                  : problem.guide_decision === 'REJECT'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-orange-100 text-orange-800'
              }`}>
                {problem.guide_decision}
              </span>
            )}
            {problem.decided_at && (
              <span className="text-xs text-gray-400 ml-auto">{fmt(problem.decided_at)}</span>
            )}
          </div>
          {problem.guide_note && (
            <p className="text-sm text-gray-600 whitespace-pre-line">{problem.guide_note}</p>
          )}
        </div>
      )}

      {/* Decide panel — HUMAN GATE 1 */}
      {isPendingReview && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-4">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-yellow-500 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-700">Awaiting Your Decision</h2>
          </div>

          {!decisionOpen ? (
            <Button onClick={() => setDecisionOpen(true)}>
              Review &amp; Decide
            </Button>
          ) : (
            <div className="space-y-4">
              <div className="flex gap-2">
                {(['ACCEPT', 'REVISE', 'REJECT'] as GuideDecision[]).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDecisionChoice(d)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      decisionChoice === d
                        ? d === 'ACCEPT'
                          ? 'bg-green-600 text-white border-green-600'
                          : d === 'REJECT'
                          ? 'bg-red-600 text-white border-red-600'
                          : 'bg-orange-500 text-white border-orange-500'
                        : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>

              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">
                  Guide note <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  rows={3}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-none"
                  placeholder="Feedback for the student…"
                  value={decisionNote}
                  onChange={(e) => setDecisionNote(e.target.value)}
                />
              </div>

              {decideError && (
                <p className="text-sm text-red-600">Failed to submit decision. Please try again.</p>
              )}

              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  onClick={() => { setDecisionOpen(false); setDecisionNote('') }}
                  disabled={decidingPending}
                >
                  Cancel
                </Button>
                <Button onClick={() => submitDecision()} disabled={decidingPending}>
                  {decidingPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                  Confirm Decision
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Research Documents */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            Research Documents
            {problemDocs.length > 0 && (
              <span className="ml-1.5 text-xs font-normal text-gray-400">({problemDocs.length})</span>
            )}
          </h2>
        </div>
        {problemDocs.length === 0 ? (
          <div className="px-5 py-6 text-center text-sm text-gray-400">
            {isAccepted
              ? 'No documents submitted yet. Student can upload after proposal is accepted.'
              : 'Documents will appear here once the proposal is accepted.'}
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {problemDocs.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                onOpen={() => navigate(`/research/documents/${doc.id}`)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Viva Sessions */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            Viva Sessions
            {problemVivas.length > 0 && (
              <span className="ml-1.5 text-xs font-normal text-gray-400">({problemVivas.length})</span>
            )}
          </h2>
          {canScheduleViva && (
            <Button
              size="sm"
              variant="outline"
              disabled={vivaScheduling || schedulingViva}
              onClick={() => {
                setSchedulingViva(true)
                doScheduleViva(approvedDoc!.id)
              }}
            >
              {vivaScheduling ? (
                <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />Scheduling…</>
              ) : (
                'Schedule Viva'
              )}
            </Button>
          )}
        </div>
        {problemVivas.length === 0 ? (
          <div className="px-5 py-6 text-center text-sm text-gray-400">
            {isAccepted && approvedDoc
              ? 'No viva scheduled. Use the Schedule Viva button above.'
              : isAccepted
              ? 'Viva can be scheduled once a document is approved.'
              : 'Viva scheduling is available after proposal acceptance.'}
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {problemVivas.map((viva) => (
              <VivaRow
                key={viva.id}
                viva={viva}
                onOpen={() => navigate(`/research/vivas/${viva.id}`)}
              />
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
