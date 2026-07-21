import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Users, Clock, Download, UserCheck, Trash2, BookOpen, AlertCircle, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { SubmissionRow } from '@/components/labs/SubmissionRow'
import {
  useLabAssignment, useSubmissions, usePublishAssignment, useCloseAssignment,
  useAssignmentEvaluators, useAssignEvaluator, useRemoveEvaluator, useTenantEvaluators,
} from '@/hooks/labs'
import { useUpdateAssignment } from '@/hooks/labs'
import { getModerationReportUrl } from '@/lib/api/labs'
import { addToast } from '@/hooks/useToast'
import type { RubricCriterion } from '@/types/labs'
import { useWorkspace } from '@/lib/workspace'

type Tab = 'overview' | 'submissions' | 'evaluators'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

function InfoCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 bg-white">
      <p className="text-xs text-gray-600">{label}</p>
      <p className="text-sm font-semibold text-gray-800 mt-0.5">{String(value)}</p>
    </div>
  )
}

function EvaluatorsPanel({
  assignmentId,
  canWrite,
}: {
  assignmentId: string
  canWrite: boolean
}) {
  const [selectedId, setSelectedId] = useState('')

  const { data: evalsData } = useAssignmentEvaluators(assignmentId)
  const evaluators = evalsData?.items ?? []
  const { data: available = [] } = useTenantEvaluators()
  const { mutate: assign, isPending: assigning } = useAssignEvaluator(assignmentId)
  const { mutate: remove } = useRemoveEvaluator(assignmentId)

  const unassigned = available.filter(
    (u) => !evaluators.some((ev) => ev.evaluator_user_id === u.id)
  )

  function handleAssign(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedId) return
    assign(selectedId, {
      onSuccess: () => {
        addToast('Evaluator assigned.', 'success')
        setSelectedId('')
      },
    })
  }

  return (
    <div className="space-y-4">
      {canWrite && (
        <form onSubmit={handleAssign} className="flex gap-2">
          <select
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300 bg-white"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            required
          >
            <option value="">Select evaluator…</option>
            {unassigned.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email})
              </option>
            ))}
          </select>
          <Button type="submit" size="sm" disabled={assigning || !selectedId}>
            {assigning ? 'Assigning…' : 'Assign'}
          </Button>
        </form>
      )}

      {evaluators.length === 0 ? (
        <div className="text-center py-10 rounded-xl border border-dashed border-gray-200">
          <UserCheck className="h-7 w-7 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No evaluators assigned.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
          {evaluators.map((ev) => {
            const user = available.find((u) => u.id === ev.evaluator_user_id)
            return (
              <div key={ev.id} className="px-4 py-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    {user ? `${user.full_name} (${user.email})` : ev.evaluator_user_id}
                  </p>
                  <p className="text-xs text-gray-600 mt-0.5">
                    Assigned {new Date(ev.assigned_at).toLocaleDateString()}
                  </p>
                </div>
                {canWrite && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-500 hover:text-red-700 hover:bg-red-50"
                    onClick={() =>
                      remove(ev.evaluator_user_id, {
                        onSuccess: () => addToast('Evaluator removed.', 'success'),
                      })
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Rubric Editor (DRAFT assignments only) ───────────────────────────────────

type DraftCriterion = RubricCriterion & { _key: string }

function makeKey() {
  return Math.random().toString(36).slice(2)
}

function toDraft(rubric: RubricCriterion[]): DraftCriterion[] {
  return rubric.map((c) => ({ ...c, _key: makeKey() }))
}

function RubricEditor({
  assignmentId,
  initialRubric,
}: {
  assignmentId: string
  initialRubric: RubricCriterion[]
}) {
  const [rows, setRows] = useState<DraftCriterion[]>(() =>
    initialRubric.length > 0
      ? toDraft(initialRubric)
      : [{ _key: makeKey(), criterion_id: 'c1', name: '', description: '', max_marks: 100, weight: 1.0 }]
  )
  const { mutate: updateAssignment, isPending: saving } = useUpdateAssignment(assignmentId)

  function addRow() {
    const idx = rows.length + 1
    setRows((prev) => [
      ...prev,
      { _key: makeKey(), criterion_id: `c${idx}`, name: '', description: '', max_marks: 10, weight: 0 },
    ])
  }

  function removeRow(key: string) {
    if (rows.length <= 1) return
    setRows((prev) => prev.filter((r) => r._key !== key))
  }

  function updateRow(key: string, field: keyof RubricCriterion, value: string | number) {
    setRows((prev) =>
      prev.map((r) => (r._key === key ? { ...r, [field]: value } : r))
    )
  }

  function handleSave() {
    // Validate
    for (const r of rows) {
      if (!r.name.trim()) {
        addToast('All criteria must have a name.', 'error')
        return
      }
      if (r.max_marks < 1) {
        addToast('Max marks must be at least 1 for each criterion.', 'error')
        return
      }
    }

    // Weights: if all zero, distribute evenly; otherwise normalise to decimal (user entered %)
    const rawWeights = rows.map((r) => Number(r.weight))
    const allZero = rawWeights.every((w) => w === 0)
    let weights: number[]
    if (allZero) {
      weights = rows.map(() => 1 / rows.length)
    } else {
      const total = rawWeights.reduce((s, w) => s + w, 0)
      weights = rawWeights.map((w) => w / total)
    }

    const rubric: RubricCriterion[] = rows.map((r, i) => ({
      criterion_id: r.criterion_id || `c${i + 1}`,
      name: r.name.trim(),
      description: r.description.trim(),
      max_marks: Number(r.max_marks),
      weight: Math.round(weights[i] * 10000) / 10000,
    }))

    updateAssignment(
      { rubric },
      {
        onSuccess: () => addToast('Rubric saved.', 'success'),
        onError:   () => addToast('Failed to save rubric.', 'error'),
      }
    )
  }

  // Display weight as percentage for easier editing
  const totalWeight = rows.reduce((s, r) => s + Number(r.weight), 0)
  const weightOk = totalWeight === 0 || Math.abs(totalWeight - 100) <= 1

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
        Add criteria and set weights (as percentages that sum to 100). Rubric editing is only available on DRAFT assignments.
      </div>

      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        {/* Header row */}
        <div className="grid grid-cols-[1fr_1.5fr_5rem_6rem_2rem] gap-2 px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <span>Criterion Name</span>
          <span>Description</span>
          <span>Max Marks</span>
          <span>Weight %</span>
          <span />
        </div>

        {rows.map((row) => (
          <div
            key={row._key}
            className="grid grid-cols-[1fr_1.5fr_5rem_6rem_2rem] gap-2 px-3 py-2 border-b border-gray-100 last:border-0 items-center"
          >
            <input
              className="rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
              placeholder="e.g. Code Quality"
              value={row.name}
              onChange={(e) => updateRow(row._key, 'name', e.target.value)}
            />
            <input
              className="rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
              placeholder="Description (optional)"
              value={row.description}
              onChange={(e) => updateRow(row._key, 'description', e.target.value)}
            />
            <input
              type="number"
              min={1}
              className="rounded border border-gray-200 px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-gray-300"
              value={row.max_marks}
              onChange={(e) => updateRow(row._key, 'max_marks', Number(e.target.value))}
            />
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              placeholder="e.g. 40"
              className={`rounded border px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 ${
                weightOk ? 'border-gray-200 focus:ring-gray-300' : 'border-red-300 focus:ring-red-300'
              }`}
              value={row.weight === 0 ? '' : row.weight}
              onChange={(e) => updateRow(row._key, 'weight', Number(e.target.value) || 0)}
            />
            <button
              type="button"
              title="Remove criterion"
              disabled={rows.length <= 1}
              onClick={() => removeRow(row._key)}
              className="text-gray-500 hover:text-red-500 disabled:opacity-30 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {!weightOk && (
        <p className="text-xs text-red-600">
          Weights sum to {totalWeight.toFixed(0)}% — they must sum to 100%.
          Leave all blank to distribute equally.
        </p>
      )}

      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-600">
          Total max marks: {rows.reduce((s, r) => s + Number(r.max_marks), 0)}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={addRow} className="gap-1">
            <Plus className="h-3.5 w-3.5" />
            Add Criterion
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !weightOk}>
            {saving ? 'Saving…' : 'Save Rubric'}
          </Button>
        </div>
      </div>
    </div>
  )
}


export default function LabAssignmentDetailPage() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const canWrite  = WRITE_ROLES.includes(role)
  const [tab, setTab] = useState<Tab>('overview')

  const assignmentId = id ?? ''
  const { data: assignment, isLoading } = useLabAssignment(assignmentId)
  const { data: subsData } = useSubmissions(assignmentId)
  const submissions = subsData?.items ?? []

  const { mutate: publish, isPending: publishing } = usePublishAssignment()
  const { mutate: close,   isPending: closing }    = useCloseAssignment()

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-4 animate-pulse">
        <div className="h-4 w-24 bg-gray-200 rounded" />
        <div className="h-8 w-64 bg-gray-200 rounded" />
        <div className="h-4 w-32 bg-gray-100 rounded" />
      </div>
    )
  }

  if (!assignment) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-gray-600 text-sm">
        Assignment not found.
      </div>
    )
  }

  const totalMarks = assignment.rubric.reduce((s, c) => s + c.max_marks, 0)

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate('/labs')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          {(assignment.course_code || assignment.course_title) && (
            <div className="flex items-center gap-1.5 mb-1.5">
              <BookOpen className="h-3.5 w-3.5 text-gray-600" />
              <span className="text-xs font-medium text-gray-500">
                {[assignment.course_code, assignment.course_title].filter(Boolean).join(' · ')}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">{assignment.title}</h1>
            <LabStatusBadge status={assignment.status} />
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              assignment.submission_type === 'CODE' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
            }`}>
              {assignment.submission_type}
            </span>
          </div>
          {assignment.deadline && (
            <p className="text-sm text-gray-600 mt-1 flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              Due {new Date(assignment.deadline).toLocaleString()}
              {assignment.allow_late && (
                <span className="text-xs text-green-600 ml-1">(Late allowed)</span>
              )}
            </p>
          )}
        </div>

        {canWrite && (
          <div className="flex items-center gap-2 flex-wrap">
            {assignment.status === 'DRAFT' && (
              <div title={!assignment.description?.trim() ? 'Add a problem statement before publishing' : undefined}>
                <Button
                  size="sm"
                  className="bg-green-700 hover:bg-green-800 text-white disabled:opacity-50"
                  onClick={() => publish(assignmentId)}
                  disabled={publishing || !assignment.description?.trim()}
                >
                  Publish
                </Button>
              </div>
            )}
            {assignment.status === 'PUBLISHED' && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-orange-700 border-orange-200 hover:bg-orange-50"
                  onClick={() => close(assignmentId)}
                  disabled={closing}
                >
                  Close
                </Button>
                <a
                  href={getModerationReportUrl(assignmentId)}
                  download
                  className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 font-medium"
                >
                  <Download className="h-3.5 w-3.5" />
                  Report
                </a>
              </>
            )}
            {assignment.status === 'CLOSED' && (
              <a
                href={getModerationReportUrl(assignmentId)}
                download
                className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 font-medium"
              >
                <Download className="h-3.5 w-3.5" />
                Report
              </a>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['overview', 'submissions', ...(canWrite ? ['evaluators'] : [])] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
              tab === t
                ? 'text-gray-900 border-b-2 border-gray-900 -mb-px'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t}
            {t === 'submissions' && submissions.length > 0 && (
              <span className="ml-1.5 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">
                {submissions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-6">
          {/* Problem Statement */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Problem Statement</span>
              {!assignment.description?.trim() && (
                <span className="flex items-center gap-1 text-xs text-amber-600">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Required to publish
                </span>
              )}
            </div>
            <div className="px-4 py-3">
              {assignment.description ? (
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{assignment.description}</p>
              ) : (
                <p className="text-sm text-gray-600 italic">No problem statement yet. Edit this assignment to add one.</p>
              )}
            </div>
          </div>

          {/* Student Instructions */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Student Instructions</span>
            </div>
            <div className="px-4 py-3">
              {assignment.instructions ? (
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{assignment.instructions}</p>
              ) : (
                <p className="text-sm text-gray-600 italic">No specific submission instructions. Edit to add guidance for students.</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <InfoCard label="Max Marks" value={assignment.max_marks ?? totalMarks} />
            <InfoCard label="Rubric Criteria" value={assignment.rubric.length} />
            {assignment.submission_type === 'CODE' && (
              <InfoCard label="Test Cases" value={assignment.test_cases?.length ?? 0} />
            )}
            <InfoCard label="AI Permitted" value={assignment.ai_not_permitted ? 'No' : 'Yes'} />
            <InfoCard label="Late Submissions" value={assignment.allow_late ? 'Allowed' : 'Not allowed'} />
            {assignment.language && (
              <InfoCard label="Language" value={assignment.language} />
            )}
          </div>

          {/* Rubric */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Rubric</h2>

            {canWrite && assignment.status === 'DRAFT' ? (
              <RubricEditor
                assignmentId={assignmentId}
                initialRubric={assignment.rubric}
              />
            ) : (
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {assignment.rubric.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-gray-600">
                    No rubric criteria defined.
                  </div>
                ) : (
                  assignment.rubric.map((c) => (
                    <div key={c.criterion_id} className="px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-gray-800">{c.name}</span>
                        <span className="text-xs text-gray-500 shrink-0">
                          {c.max_marks} marks · {(c.weight * 100).toFixed(0)}%
                        </span>
                      </div>
                      {c.description && (
                        <p className="text-xs text-gray-600 mt-0.5">{c.description}</p>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Test cases — CODE only */}
          {assignment.submission_type === 'CODE' && (assignment.test_cases?.length ?? 0) > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-3">Test Cases</h2>
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {assignment.test_cases.map((tc) => (
                  <div key={tc.id} className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{tc.name}</span>
                      {tc.is_hidden && (
                        <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">Hidden</span>
                      )}
                      <span className="text-xs text-gray-600 ml-auto">{tc.points} pts</span>
                    </div>
                    {tc.stdin && (
                      <pre className="text-xs text-gray-500 mt-1.5 font-mono bg-gray-50 rounded p-2 overflow-x-auto">
                        stdin: {tc.stdin}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'submissions' && (
        <div>
          {submissions.length === 0 ? (
            <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
              <Users className="h-8 w-8 mx-auto mb-2 text-gray-200" />
              <p className="text-sm text-gray-600">No submissions yet.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
              {submissions.map((sub) => (
                <SubmissionRow
                  key={sub.id}
                  sub={sub}
                  onReview={() => navigate(`/labs/review/${sub.id}`)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'evaluators' && canWrite && (
        <EvaluatorsPanel assignmentId={assignmentId} canWrite={canWrite} />
      )}
    </div>
  )
}
