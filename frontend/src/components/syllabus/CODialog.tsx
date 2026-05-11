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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { BloomLevel, CourseOutcome, CourseOutcomeCreate, CourseOutcomeUpdate } from '@/types/syllabus'

const BLOOM_LEVELS: BloomLevel[] = [
  'REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE',
]

const BLOOM_LABELS: Record<BloomLevel, string> = {
  REMEMBER:   'Remember',
  UNDERSTAND: 'Understand',
  APPLY:      'Apply',
  ANALYSE:    'Analyse',
  EVALUATE:   'Evaluate',
  CREATE:     'Create',
}

type Mode = 'add' | 'edit'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: Mode
  initial?: CourseOutcome | null
  onAdd?: (payload: CourseOutcomeCreate) => void
  onEdit?: (coId: string, payload: CourseOutcomeUpdate) => void
  isPending?: boolean
}

const DEFAULTS = {
  code: '',
  description: '',
  bloom_level: 'APPLY' as BloomLevel,
  display_order: 0,
}

export function CODialog({
  open, onOpenChange, mode, initial, onAdd, onEdit, isPending,
}: Props) {
  const [form, setForm] = useState(DEFAULTS)

  useEffect(() => {
    if (mode === 'edit' && initial) {
      setForm({
        code:          initial.code,
        description:   initial.description,
        bloom_level:   initial.bloom_level,
        display_order: initial.display_order,
      })
    } else {
      setForm(DEFAULTS)
    }
  }, [mode, initial, open])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === 'add' && onAdd) {
      onAdd({
        code:          form.code,
        description:   form.description,
        bloom_level:   form.bloom_level,
        display_order: Number(form.display_order),
      })
    } else if (mode === 'edit' && onEdit && initial) {
      onEdit(initial.id, {
        description:   form.description,
        bloom_level:   form.bloom_level,
        display_order: Number(form.display_order),
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Course Outcome' : 'Edit Course Outcome'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'add' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Code <span className="text-red-500">*</span>
              </label>
              <Input
                required
                maxLength={20}
                value={form.code}
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="e.g. CO1"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description <span className="text-red-500">*</span>
            </label>
            <Textarea
              required
              minLength={10}
              rows={3}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Students will be able to…"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Bloom Level <span className="text-red-500">*</span>
              </label>
              <Select
                value={form.bloom_level}
                onValueChange={(v) => setForm((f) => ({ ...f, bloom_level: v as BloomLevel }))}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {BLOOM_LEVELS.map((bl) => (
                    <SelectItem key={bl} value={bl}>{BLOOM_LABELS[bl]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Display Order
              </label>
              <Input
                type="number"
                min={0}
                value={form.display_order}
                onChange={(e) => setForm((f) => ({ ...f, display_order: Number(e.target.value) }))}
              />
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : mode === 'add' ? 'Add' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
