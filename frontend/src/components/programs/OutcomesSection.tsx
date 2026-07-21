import { useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { OutcomeDialog } from './OutcomeDialog'
import {
  useProgramOutcomes,
  useAddOutcome,
  useUpdateOutcome,
  useDeleteOutcome,
} from '@/hooks/programs'
import type { Program, ProgramOutcome } from '@/types/program'

interface Props {
  program: Program
}

export function OutcomesSection({ program }: Props) {
  const isDraft = program.status === 'DRAFT'
  const { data: outcomes = [] } = useProgramOutcomes(program.id)
  const add = useAddOutcome(program.id)
  const update = useUpdateOutcome(program.id)
  const del = useDeleteOutcome(program.id)

  const [addOpen, setAddOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ProgramOutcome | null>(null)

  const sorted = [...outcomes].sort((a, b) => a.display_order - b.display_order)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">
          Program Outcomes ({outcomes.length})
        </h3>
        {isDraft && (
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            Add PO
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-600 text-center py-8">No outcomes defined yet.</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((outcome) => (
            <div
              key={outcome.id}
              className="flex items-start gap-3 rounded-md border border-gray-200 bg-white p-3"
            >
              <span className="shrink-0 rounded bg-blue-100 px-2 py-0.5 text-xs font-mono font-semibold text-blue-700">
                {outcome.code}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800">{outcome.description}</p>
                {outcome.bloom_level && (
                  <p className="text-xs text-gray-600 mt-0.5">Bloom: {outcome.bloom_level}</p>
                )}
              </div>
              {isDraft && (
                <div className="flex gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setEditTarget(outcome)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50"
                    onClick={() => del.mutate(outcome.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <OutcomeDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        mode="add"
        onAdd={(payload) => add.mutate(payload)}
        isPending={add.isPending}
      />
      <OutcomeDialog
        open={editTarget !== null}
        onOpenChange={(o) => {
          if (!o) setEditTarget(null)
        }}
        mode="edit"
        initial={editTarget}
        onEdit={(id, payload) => update.mutate({ outcomeId: id, payload })}
        isPending={update.isPending}
      />
    </div>
  )
}
