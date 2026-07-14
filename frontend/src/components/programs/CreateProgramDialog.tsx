import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
import { useCreateProgram } from '@/hooks/programs'
import { academicsApi } from '@/lib/api/academics'

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
  ai_instructions: '',
}

export function CreateProgramDialog({ open, onOpenChange }: Props) {
  const [form, setForm] = useState(DEFAULTS)
  const [linkedAcadProgramId, setLinkedAcadProgramId] = useState<string | undefined>(undefined)
  const create = useCreateProgram()

  const { data: acadPrograms = [] } = useQuery({
    queryKey: ['acad-programs-active'],
    queryFn: () => academicsApi.listPrograms(undefined, false),
    enabled: open,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['acad-departments'],
    queryFn: () => academicsApi.listDepartments(false),
    enabled: open,
  })

  function set(field: keyof typeof DEFAULTS, value: string | number) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function handleAcadProgramSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value
    if (!id) {
      setLinkedAcadProgramId(undefined)
      return
    }
    const acad = acadPrograms.find((p) => p.id === id)
    if (!acad) return
    setLinkedAcadProgramId(id)
    // Auto-populate degree_type from academic program
    set('degree_type', acad.degree_type)
    // Auto-populate department name from departments list
    const dept = departments.find((d) => d.id === acad.department_id)
    if (dept) set('department', dept.name)
    // The credit target belongs to the PROGRAMME, not to whoever fills in this
    // form: an MCA is worth what the institution says it is worth. Leaving the
    // hardcoded 60 in place is how an 80-credit MCA came to be generated — and
    // rebalanced — against a 60-credit target, with nothing anywhere saying so.
    //
    // Only when the institution has actually configured it. An unset programme
    // keeps the old default rather than being handed a number nobody chose, and
    // the Dean can still override either way.
    if (acad.min_credits_for_degree != null) {
      set('total_credits', Number(acad.min_credits_for_degree))
    }
    set('duration_years', acad.duration_years)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    await create.mutateAsync({
      title: form.title,
      degree_type: form.degree_type,
      department: form.department,
      duration_years: Number(form.duration_years),
      total_credits: Number(form.total_credits),
      acad_program_id: linkedAcadProgramId,
      ai_instructions: form.ai_instructions || undefined,
    })
    setForm(DEFAULTS)
    setLinkedAcadProgramId(undefined)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">

          {/* Academic Program link (optional) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Link to Academic Program
              <span className="text-gray-400 font-normal ml-1">(optional)</span>
            </label>
            <select
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 bg-white"
              value={linkedAcadProgramId ?? ''}
              onChange={handleAcadProgramSelect}
            >
              <option value="">— Not linked —</option>
              {acadPrograms.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.code}) · {p.degree_type} · {p.duration_years}yr
                </option>
              ))}
            </select>
            {linkedAcadProgramId && (
              <p className="text-xs text-indigo-600 mt-1">
                Degree type and department auto-populated. You can still edit them below.
              </p>
            )}
          </div>

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
          {/* AI Instructions */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              AI Instructions
              <span className="text-gray-400 font-normal ml-1">(optional — curriculum design guidance)</span>
            </label>
            <Textarea
              rows={3}
              value={form.ai_instructions}
              onChange={(e) => set('ai_instructions', e.target.value)}
              placeholder="e.g. Final semester must contain only project and internship. Major project 10 credits. Internship 10 credits."
            />
            <p className="text-xs text-gray-400 mt-1">
              Stored on the program and passed to AI every time you generate the structure.
            </p>
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
