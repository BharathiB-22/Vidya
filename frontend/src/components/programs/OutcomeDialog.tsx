import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { ProgramOutcome, ProgramOutcomeCreate, ProgramOutcomeUpdate } from '@/types/program'

const BLOOM_LEVELS = ['Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create']

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'add' | 'edit'
  initial?: ProgramOutcome | null
  onAdd?: (payload: ProgramOutcomeCreate) => void
  onEdit?: (outcomeId: string, payload: ProgramOutcomeUpdate) => void
  isPending?: boolean
}

const EMPTY = { code: '', description: '', bloom_level: '', display_order: '' }

export function OutcomeDialog({
  open,
  onOpenChange,
  mode,
  initial,
  onAdd,
  onEdit,
  isPending,
}: Props) {
  const [f, setF] = useState(EMPTY)

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && initial) {
      setF({
        code: initial.code,
        description: initial.description,
        bloom_level: initial.bloom_level ?? '',
        display_order: initial.display_order.toString(),
      })
    } else {
      setF(EMPTY)
    }
  }, [open, mode, initial])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === 'add') {
      onAdd?.({
        code: f.code,
        description: f.description,
        bloom_level: f.bloom_level || undefined,
        display_order: f.display_order ? Number(f.display_order) : undefined,
      })
    } else if (mode === 'edit' && initial) {
      onEdit?.(initial.id, {
        description: f.description,
        bloom_level: f.bloom_level || undefined,
        display_order: f.display_order ? Number(f.display_order) : undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === 'add' ? 'Add Program Outcome' : 'Edit Program Outcome'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'add' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Code</label>
              <Input
                required
                value={f.code}
                onChange={(e) => setF((p) => ({ ...p, code: e.target.value }))}
                placeholder="PO1"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <Textarea
              required
              rows={3}
              value={f.description}
              onChange={(e) => setF((p) => ({ ...p, description: e.target.value }))}
              placeholder="Student will be able to…"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bloom Level</label>
              <select
                className="flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={f.bloom_level}
                onChange={(e) => setF((p) => ({ ...p, bloom_level: e.target.value }))}
              >
                <option value="">— none —</option>
                {BLOOM_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Display Order
              </label>
              <Input
                type="number"
                min={0}
                value={f.display_order}
                onChange={(e) => setF((p) => ({ ...p, display_order: e.target.value }))}
                placeholder="0"
              />
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
