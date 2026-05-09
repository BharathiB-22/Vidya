import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCreateProgram } from '@/hooks/programs'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DEFAULTS = {
  title: '',
  degree_type: '',
  department: '',
  duration_years: 2,
  total_credits: 60,
}

export function CreateProgramDialog({ open, onOpenChange }: Props) {
  const [form, setForm] = useState(DEFAULTS)
  const create = useCreateProgram()

  function set(field: keyof typeof DEFAULTS, value: string | number) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    await create.mutateAsync({
      title: form.title,
      degree_type: form.degree_type,
      department: form.department,
      duration_years: Number(form.duration_years),
      total_credits: Number(form.total_credits),
    })
    setForm(DEFAULTS)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <Input
              required
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="MSc Computer Science"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Degree Type</label>
            <Input
              required
              value={form.degree_type}
              onChange={(e) => set('degree_type', e.target.value)}
              placeholder="MSc"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
            <Input
              required
              value={form.department}
              onChange={(e) => set('department', e.target.value)}
              placeholder="Computer Science"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Duration (years)
              </label>
              <Input
                type="number"
                min={1}
                max={6}
                required
                value={form.duration_years}
                onChange={(e) => set('duration_years', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Total Credits
              </label>
              <Input
                type="number"
                min={1}
                required
                value={form.total_credits}
                onChange={(e) => set('total_credits', e.target.value)}
              />
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
