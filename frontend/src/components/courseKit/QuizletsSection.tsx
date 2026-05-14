import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { QuizletDialog } from './QuizletDialog'
import {
  useAddQuizlet,
  useUpdateQuizlet,
  useDeleteQuizlet,
} from '@/hooks/courseKit'
import type { KitQuizlet, KitQuizletCreate, KitQuizletUpdate } from '@/types/courseKit'

interface Props {
  kitId:         string
  quizlets:      KitQuizlet[]
  isEditable:    boolean
  showAnswerKey: boolean
  isLoading?:    boolean
}

function SkeletonQuizlet() {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="h-4 w-6 rounded bg-gray-200 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-full rounded bg-gray-200" />
          <div className="h-3 w-1/2 rounded bg-gray-100" />
        </div>
      </div>
    </div>
  )
}

export function QuizletsSection({ kitId, quizlets, isEditable, showAnswerKey, isLoading }: Props) {
  const [dialogOpen,      setDialogOpen]      = useState(false)
  const [editTarget,      setEditTarget]      = useState<KitQuizlet | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const addQuizlet    = useAddQuizlet(kitId)
  const updateQuizlet = useUpdateQuizlet(kitId)
  const deleteQuizlet = useDeleteQuizlet(kitId)

  const sorted = [...quizlets].sort((a, b) => a.question_number - b.question_number)

  function openAdd() {
    setEditTarget(null)
    setDialogOpen(true)
  }

  function openEdit(q: KitQuizlet) {
    setEditTarget(q)
    setDialogOpen(true)
  }

  function handleAdd(payload: KitQuizletCreate) {
    addQuizlet.mutate(payload)
  }

  function handleEdit(quizletId: string, payload: KitQuizletUpdate) {
    updateQuizlet.mutate({ quizletId, payload })
  }

  function handleDeleteClick(quizletId: string) {
    if (pendingDeleteId === quizletId) {
      deleteQuizlet.mutate(quizletId)
      setPendingDeleteId(null)
    } else {
      setPendingDeleteId(quizletId)
    }
  }

  const mutationError = addQuizlet.isError || updateQuizlet.isError || deleteQuizlet.isError

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          Quizlets ({isLoading ? '…' : quizlets.length})
        </h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd} disabled={addQuizlet.isPending}>
            <Plus className="h-4 w-4 mr-1" />
            Add Quizlet
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
          {[1, 2, 3].map((n) => <SkeletonQuizlet key={n} />)}
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No quizlets yet.{isEditable ? ' Click "Add Quizlet" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((q) => {
            const isConfirmDelete = pendingDeleteId === q.id
            return (
              <div
                key={q.id}
                className={`rounded-lg border px-4 py-3 hover:bg-gray-50 ${
                  isConfirmDelete ? 'border-red-300 bg-red-50' : 'border-gray-200'
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="min-w-[2rem] text-sm font-bold text-gray-400 shrink-0">
                    Q{q.question_number}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800">{q.question_text}</p>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className="text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded">
                        {q.question_type}
                      </span>
                      {q.bloom_level && (
                        <span className="text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 px-1.5 py-0.5 rounded">
                          {q.bloom_level}
                        </span>
                      )}
                      {q.co_reference && (
                        <span className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          {q.co_reference}
                        </span>
                      )}
                      {!showAnswerKey && (
                        <span className="flex items-center gap-1 text-[10px] text-gray-400">
                          <Lock className="h-3 w-3" /> answers hidden
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
                        onClick={() => openEdit(q)}
                        aria-label={`Edit quizlet ${q.question_number}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`h-7 w-7 ${isConfirmDelete ? 'text-red-700' : 'text-red-500 hover:text-red-700'}`}
                        onClick={() => handleDeleteClick(q.id)}
                        disabled={deleteQuizlet.isPending}
                        aria-label={isConfirmDelete ? `Confirm delete quizlet ${q.question_number}` : `Delete quizlet ${q.question_number}`}
                      >
                        {deleteQuizlet.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <QuizletDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={editTarget ? 'edit' : 'add'}
        initial={editTarget}
        nextNumber={quizlets.length + 1}
        onAdd={handleAdd}
        onEdit={handleEdit}
        isPending={addQuizlet.isPending || updateQuizlet.isPending}
        showAnswerKey={showAnswerKey}
      />
    </div>
  )
}
