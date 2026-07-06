import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { sisApi, ComponentTemplate, MarksComponent } from '@/lib/api/sis'

const TYPES = ['CIE', 'ASSIGNMENT', 'QUIZ', 'LAB', 'OTHER']
const TYPE_LABELS: Record<string, string> = {
  CIE: 'CIE', ASSIGNMENT: 'Assignment', QUIZ: 'Quiz', LAB: 'Lab', OTHER: 'Other',
}

interface FormState {
  semester_id: string; course_id: string; section_id: string
  component_type: string; name: string; max_marks: string
  weightage: string; due_date: string
}

function emptyForm(defaults?: { courseId?: string; sectionId?: string; semesterId?: string }): FormState {
  return {
    semester_id: defaults?.semesterId ?? '',
    course_id: defaults?.courseId ?? '',
    section_id: defaults?.sectionId ?? '',
    component_type: 'CIE', name: '', max_marks: '', weightage: '', due_date: '',
  }
}

export interface CreateComponentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (component: MarksComponent) => void
  /** Pre-fills the (otherwise raw-UUID) course/section/semester fields when the caller already knows them. */
  defaultCourseId?: string
  defaultSectionId?: string
  defaultSemesterId?: string
}

export function CreateComponentDialog({
  open, onOpenChange, onCreated, defaultCourseId, defaultSectionId, defaultSemesterId,
}: CreateComponentDialogProps) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(() =>
    emptyForm({ courseId: defaultCourseId, sectionId: defaultSectionId, semesterId: defaultSemesterId })
  )

  const { data: templates = [] } = useQuery({
    queryKey: ['component-templates'],
    queryFn:  sisApi.listComponentTemplates,
  })

  const createMutation = useMutation({
    mutationFn: sisApi.createMarksComponent,
    onSuccess:  (component) => {
      qc.invalidateQueries({ queryKey: ['marks-components-my'] })
      qc.invalidateQueries({ queryKey: ['marks-components'] })
      setForm(emptyForm({ courseId: defaultCourseId, sectionId: defaultSectionId, semesterId: defaultSemesterId }))
      onOpenChange(false)
      onCreated?.(component)
    },
  })

  function applyTemplate(t: ComponentTemplate) {
    setForm(f => ({ ...f, component_type: t.component_type, name: t.name, max_marks: String(t.max_marks) }))
  }

  function handleCreate() {
    createMutation.mutate({
      course_id: form.course_id, section_id: form.section_id, semester_id: form.semester_id,
      component_type: form.component_type, name: form.name.trim(),
      max_marks: parseFloat(form.max_marks),
      weightage:  form.weightage ? parseFloat(form.weightage) : undefined,
      due_date:   form.due_date || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Add Assessment Component</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <p className="text-xs text-muted-foreground mb-2">Quick-fill from template</p>
            <div className="flex flex-wrap gap-2">
              {templates.map((t: ComponentTemplate) => (
                <Button key={t.template_key} size="sm" variant="outline" onClick={() => applyTemplate(t)}>
                  {t.name}
                </Button>
              ))}
            </div>
          </div>
          <div className="border-t pt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-medium mb-1">Course ID</p>
                <Input value={form.course_id} onChange={e => setForm(f => ({ ...f, course_id: e.target.value }))} placeholder="UUID" />
              </div>
              <div>
                <p className="text-xs font-medium mb-1">Section ID</p>
                <Input value={form.section_id} onChange={e => setForm(f => ({ ...f, section_id: e.target.value }))} placeholder="UUID" />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium mb-1">Semester ID</p>
              <Input value={form.semester_id} onChange={e => setForm(f => ({ ...f, semester_id: e.target.value }))} placeholder="UUID" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-medium mb-1">Type</p>
                <Select value={form.component_type} onValueChange={v => setForm(f => ({ ...f, component_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TYPES.map(t => <SelectItem key={t} value={t}>{TYPE_LABELS[t]}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <p className="text-xs font-medium mb-1">Name</p>
                <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. CIE-1" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-medium mb-1">Max Marks</p>
                <Input type="number" value={form.max_marks} onChange={e => setForm(f => ({ ...f, max_marks: e.target.value }))} />
              </div>
              <div>
                <p className="text-xs font-medium mb-1">Weightage % (optional)</p>
                <Input type="number" value={form.weightage} onChange={e => setForm(f => ({ ...f, weightage: e.target.value }))} />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium mb-1">Due Date (optional)</p>
              <Input type="date" value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
            </div>
          </div>
          {createMutation.isError && <p className="text-destructive text-sm">Failed to create. Check all fields.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={createMutation.isPending || !form.name || !form.max_marks}>
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
