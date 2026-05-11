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
import type { SyllabusUnit, SyllabusUnitCreate, SyllabusUnitUpdate } from '@/types/syllabus'

type Mode = 'add' | 'edit'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: Mode
  initial?: SyllabusUnit | null
  onAdd?: (payload: SyllabusUnitCreate) => void
  onEdit?: (unitId: string, payload: SyllabusUnitUpdate) => void
  isPending?: boolean
}

const DEFAULTS = {
  unit_number: 1,
  title:       '',
  total_hours: 6,
  pedagogy:    '',
}

export function UnitDialog({ open, onOpenChange, mode, initial, onAdd, onEdit, isPending }: Props) {
  const [form, setForm] = useState(DEFAULTS)

  useEffect(() => {
    if (mode === 'edit' && initial) {
      setForm({
        unit_number: initial.unit_number,
        title:       initial.title,
        total_hours: initial.total_hours,
        pedagogy:    initial.pedagogy ?? '',
      })
    } else {
      setForm(DEFAULTS)
    }
  }, [mode, initial, open])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === 'add' && onAdd) {
      onAdd({
        unit_number: Number(form.unit_number),
        title:       form.title,
        total_hours: Number(form.total_hours),
        pedagogy:    form.pedagogy || undefined,
      })
    } else if (mode === 'edit' && onEdit && initial) {
      onEdit(initial.id, {
        title:       form.title,
        total_hours: Number(form.total_hours),
        pedagogy:    form.pedagogy || undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Unit' : 'Edit Unit'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {mode === 'add' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Unit # <span className="text-red-500">*</span>
                </label>
                <Input
                  type="number"
                  min={1}
                  required
                  value={form.unit_number}
                  onChange={(e) => setForm((f) => ({ ...f, unit_number: Number(e.target.value) }))}
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Hours <span className="text-red-500">*</span>
              </label>
              <Input
                type="number"
                min={1}
                required
                value={form.total_hours}
                onChange={(e) => setForm((f) => ({ ...f, total_hours: Number(e.target.value) }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Title <span className="text-red-500">*</span>
            </label>
            <Input
              required
              maxLength={200}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Introduction to Algorithms"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Pedagogy (optional)
            </label>
            <Textarea
              rows={2}
              value={form.pedagogy}
              onChange={(e) => setForm((f) => ({ ...f, pedagogy: e.target.value }))}
              placeholder="e.g. Lecture, Lab, Case study…"
            />
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : mode === 'add' ? 'Add Unit' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
