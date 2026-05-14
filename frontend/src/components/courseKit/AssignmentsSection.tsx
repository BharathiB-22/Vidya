import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentDialog } from './AssignmentDialog'
import {
  useAddAssignment,
  useUpdateAssignment,
  useDeleteAssignment,
} from '@/hooks/courseKit'
import type { KitAssignment, KitAssignmentCreate, KitAssignmentUpdate } from '@/types/courseKit'

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
}

export function AssignmentsSection({ kitId, assignments, isEditable, showModelAnswer }: Props) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<KitAssignment | null>(null)

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

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Assignments ({assignments.length})</h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            Add Assignment
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No assignments yet.{isEditable ? ' Click "Add Assignment" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((a) => (
            <div
              key={a.id}
              className="rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
            >
              <div className="flex items-start gap-3">
                <span className="min-w-[2rem] text-sm font-bold text-gray-400 shrink-0">
                  A{a.assignment_number}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-800">{a.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{a.question_text}</p>
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
                    {!showModelAnswer && (
                      <span className="flex items-center gap-1 text-[10px] text-gray-400">
                        <Lock className="h-3 w-3" /> model answer hidden
                      </span>
                    )}
                  </div>
                </div>
                {isEditable && (
                  <div className="flex gap-1 shrink-0">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      onClick={() => openEdit(a)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-red-500 hover:text-red-700"
                      onClick={() => deleteAssignment.mutate(a.id)}
                      disabled={deleteAssignment.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
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
