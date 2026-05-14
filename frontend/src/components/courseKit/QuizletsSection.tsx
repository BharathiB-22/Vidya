import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock } from 'lucide-react'
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
}

export function QuizletsSection({ kitId, quizlets, isEditable, showAnswerKey }: Props) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<KitQuizlet | null>(null)

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

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Quizlets ({quizlets.length})</h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            Add Quizlet
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No quizlets yet.{isEditable ? ' Click "Add Quizlet" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((q) => (
            <div
              key={q.id}
              className="rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
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
                </div>
                {isEditable && (
                  <div className="flex gap-1 shrink-0">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      onClick={() => openEdit(q)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-red-500 hover:text-red-700"
                      onClick={() => deleteQuizlet.mutate(q.id)}
                      disabled={deleteQuizlet.isPending}
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
