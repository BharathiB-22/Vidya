import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentDialog } from './AssignmentDialog'
import {
  useAddAssignment,
  useUpdateAssignment,
  useDeleteAssignment,
} from '@/hooks/courseKit'
import type { KitAssignment, KitAssignmentCreate, KitAssignmentUpdate, RubricCriterion } from '@/types/courseKit'

const TYPE_LABELS: Record<string, string> = {
  CLASSWORK:  'Classwork',
  HOMEWORK:   'Homework',
  CASE_STUDY: 'Case Study',
}

interface Props {
  kitId:           string
  assignments:     KitAssignment[]
  isEditable:      boolean
  showModelAnswer: boolean
  isLoading?:      boolean
}

function SkeletonAssignment() {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="h-4 w-6 rounded bg-gray-200 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-40 rounded bg-gray-200" />
          <div className="h-3 w-full rounded bg-gray-100" />
          <div className="h-3 w-2/3 rounded bg-gray-100" />
        </div>
      </div>
    </div>
  )
}

export function AssignmentsSection({ kitId, assignments, isEditable, showModelAnswer, isLoading }: Props) {
  const [dialogOpen,      setDialogOpen]      = useState(false)
  const [editTarget,      setEditTarget]      = useState<KitAssignment | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [expandedIds,     setExpandedIds]     = useState<Set<string>>(new Set())

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const addAssignment    = useAddAssignment(kitId)
  const updateAssignment = useUpdateAssignment(kitId)
  const deleteAssignment = useDeleteAssignment(kitId)

  const sorted = [...assignments].sort((a, b) => a.assignment_number - b.assignment_number)

  function openAdd() {
    setEditTarget(null)
    setDialogOpen(true)
  }

  function openEdit(a: KitAssignment) {
    setEditTarget(a)
    setDialogOpen(true)
  }

  function handleAdd(payload: KitAssignmentCreate) {
    addAssignment.mutate(payload)
  }

  function handleEdit(assignmentId: string, payload: KitAssignmentUpdate) {
    updateAssignment.mutate({ assignmentId, payload })
  }

  function handleDeleteClick(assignmentId: string) {
    if (pendingDeleteId === assignmentId) {
      deleteAssignment.mutate(assignmentId)
      setPendingDeleteId(null)
    } else {
      setPendingDeleteId(assignmentId)
    }
  }

  const mutationError = addAssignment.isError || updateAssignment.isError || deleteAssignment.isError

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          Assignments ({isLoading ? '…' : assignments.length})
        </h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd} disabled={addAssignment.isPending}>
            <Plus className="h-4 w-4 mr-1" />
            Add Assignment
          </Button>
        )}
      </div>

      {mutationError && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-1.5">
          Action failed — please try again.
        </p>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => <SkeletonAssignment key={n} />)}
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-gray-600 py-4 text-center">
          No assignments yet.{isEditable ? ' Click "Add Assignment" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((a) => {
            const isConfirmDelete = pendingDeleteId === a.id
            const isExpanded      = expandedIds.has(a.id)
            const rubric = Array.isArray(a.rubric)
              ? (a.rubric as unknown as RubricCriterion[])
              : []
            const modelAnswerRaw = a.model_answer as Record<string, unknown> | string | null
            const modelAnswerText = modelAnswerRaw
              ? typeof modelAnswerRaw === 'string'
                ? modelAnswerRaw
                : String(
                    (modelAnswerRaw as Record<string, unknown>).text ??
                    (modelAnswerRaw as Record<string, unknown>).answer ??
                    JSON.stringify(modelAnswerRaw)
                  )
              : null

            return (
              <div
                key={a.id}
                className={`rounded-lg border px-4 py-3 hover:bg-gray-50 ${
                  isConfirmDelete ? 'border-red-300 bg-red-50' : 'border-gray-200'
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="min-w-[2rem] text-sm font-bold text-gray-600 shrink-0">
                    A{a.assignment_number}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-800">{a.title}</p>
                    <p className={`text-xs text-gray-500 mt-0.5 ${isExpanded ? '' : 'line-clamp-2'}`}>
                      {a.question_text}
                    </p>

                    {/* Expand / collapse toggle */}
                    {(rubric.length > 0 || modelAnswerText || a.question_text.length > 120) && (
                      <button
                        type="button"
                        onClick={() => toggleExpand(a.id)}
                        className="flex items-center gap-0.5 mt-1 text-[11px] text-blue-600 hover:underline"
                      >
                        {isExpanded
                          ? <><ChevronUp className="h-3 w-3" /> Show less</>
                          : <><ChevronDown className="h-3 w-3" /> Show details</>
                        }
                      </button>
                    )}

                    {/* Extra content when expanded */}
                    {isExpanded && (
                      <div className="mt-2 space-y-2">
                        {rubric.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Rubric</p>
                            <div className="space-y-1">
                              {rubric.map((rc, i) => (
                                <div key={i} className="flex items-start gap-2 text-xs border border-gray-100 rounded px-2 py-1.5">
                                  <span className="font-medium text-gray-700 flex-1">{rc.criterion}</span>
                                  {rc.description && (
                                    <span className="text-gray-500 flex-1">{rc.description}</span>
                                  )}
                                  {rc.max_marks != null && (
                                    <span className="text-gray-600 shrink-0 tabular-nums">{rc.max_marks}m</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {showModelAnswer && modelAnswerText && (
                          <div className="text-xs bg-green-50 border border-green-100 rounded px-3 py-2">
                            <p className="font-semibold text-green-700 mb-0.5">Model Answer</p>
                            <p className="text-gray-700 whitespace-pre-wrap">{modelAnswerText}</p>
                          </div>
                        )}
                        {!showModelAnswer && a.model_answer && (
                          <span className="flex items-center gap-1 text-[10px] text-gray-600">
                            <Lock className="h-3 w-3" /> model answer hidden
                          </span>
                        )}
                      </div>
                    )}

                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className="text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-200 px-1.5 py-0.5 rounded">
                        {TYPE_LABELS[a.assignment_type] ?? a.assignment_type}
                      </span>
                      <span className="text-[10px] font-semibold bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                        {a.complexity_level}
                      </span>
                      {a.current_events_toggle && (
                        <span className="text-[10px] font-semibold bg-green-50 text-green-700 border border-green-200 px-1.5 py-0.5 rounded">
                          Current Events
                        </span>
                      )}
                      {a.bloom_level && (
                        <span className="text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 px-1.5 py-0.5 rounded">
                          {a.bloom_level}
                        </span>
                      )}
                      {a.co_reference && (
                        <span className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          {a.co_reference}
                        </span>
                      )}
                      {!showModelAnswer && !isExpanded && a.model_answer && (
                        <span className="flex items-center gap-1 text-[10px] text-gray-600">
                          <Lock className="h-3 w-3" /> model answer hidden
                        </span>
                      )}
                    </div>
                    {isConfirmDelete && (
                      <p className="text-xs text-red-600 mt-1">Click delete again to confirm.</p>
                    )}
                  </div>
                  {isEditable && (
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => openEdit(a)}
                        aria-label={`Edit assignment ${a.assignment_number}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`h-7 w-7 ${isConfirmDelete ? 'text-red-700' : 'text-red-500 hover:text-red-700'}`}
                        onClick={() => handleDeleteClick(a.id)}
                        disabled={deleteAssignment.isPending}
                        aria-label={isConfirmDelete ? `Confirm delete assignment ${a.assignment_number}` : `Delete assignment ${a.assignment_number}`}
                      >
                        {deleteAssignment.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <AssignmentDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={editTarget ? 'edit' : 'add'}
        initial={editTarget}
        nextNumber={assignments.length + 1}
        onAdd={handleAdd}
        onEdit={handleEdit}
        isPending={addAssignment.isPending || updateAssignment.isPending}
        showModelAnswer={showModelAnswer}
      />
    </div>
  )
}
