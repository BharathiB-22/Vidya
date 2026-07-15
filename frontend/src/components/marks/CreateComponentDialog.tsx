import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { sisApi, ComponentTemplate, MarksComponent } from '@/lib/api/sis'
import { assignmentsApi } from '@/lib/api/assignments'

// Assessment component types offered in the UI. QUIZ is intentionally absent —
// VIDYA has no quiz workflow (see the audit in the PR). LAB is added only for
// subjects that actually have a lab component. The backend still accepts QUIZ
// for backward compatibility with any legacy rows; it is simply never offered.
const BASE_TYPES = ['CIE', 'ASSIGNMENT', 'OTHER'] as const
const TYPE_LABELS: Record<string, string> = {
  CIE: 'CIE', ASSIGNMENT: 'Assignment', LAB: 'Lab Assessment', OTHER: 'Other',
}

/** The class a component is being created for. Resolved from page context (the
 *  faculty subject workspace) or from an assignment the user picks here — never
 *  typed as a raw UUID. */
export interface ComponentContext {
  courseId:        string
  sectionId?:      string
  semesterId:      string
  courseLabel:     string
  sectionLabel?:   string
  semesterLabel:   string
  hasLabComponent?: boolean
}

interface FormState {
  component_type: string; name: string; max_marks: string
  weightage: string; due_date: string
}

const EMPTY_FORM: FormState = {
  component_type: 'CIE', name: '', max_marks: '', weightage: '', due_date: '',
}

export interface CreateComponentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (component: MarksComponent) => void
  /** The target class. When provided (e.g. the subject workspace already knows
   *  the course/section/semester) it is shown read-only. When omitted, the user
   *  picks one of their assigned classes here. Raw IDs are never exposed. */
  context?: ComponentContext
}

export function CreateComponentDialog({
  open, onOpenChange, onCreated, context,
}: CreateComponentDialogProps) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  // Only used when no context is supplied by the caller: the assignment the user
  // selects, from which the class context is derived.
  const [pickedAssignmentId, setPickedAssignmentId] = useState<string>('')

  const { data: templates = [] } = useQuery({
    queryKey: ['component-templates'],
    queryFn:  sisApi.listComponentTemplates,
  })

  // Faculty's own assigned classes — only fetched in the picker case (no context).
  const { data: myAssignments } = useQuery({
    queryKey: ['my-assignments'],
    queryFn:  () => assignmentsApi.listMine(),
    enabled:  open && !context,
    staleTime: 5 * 60 * 1000,
  })
  const assignments = myAssignments?.items ?? []

  // The class in force: caller-supplied context, or the picked assignment mapped
  // into the same shape.
  const resolved: ComponentContext | null = useMemo(() => {
    if (context) return context
    const a = assignments.find((x) => x.id === pickedAssignmentId)
    if (!a) return null
    return {
      courseId:        a.course_id,
      sectionId:       a.section_id ?? undefined,
      semesterId:      a.semester_id,
      courseLabel:     `${a.course?.code ?? ''} — ${a.course?.title ?? 'Course'}`.replace(/^ — /, ''),
      sectionLabel:    a.section?.name ?? undefined,
      semesterLabel:   a.semester ? `Semester ${a.semester.number}` : '',
      hasLabComponent: a.course?.has_lab_component,
    }
  }, [context, assignments, pickedAssignmentId])

  // LAB only for lab subjects; QUIZ never offered.
  const types = resolved?.hasLabComponent
    ? [...BASE_TYPES, 'LAB']
    : [...BASE_TYPES]

  // Quick-fill templates minus Quiz, minus Lab for non-lab subjects.
  const visibleTemplates = templates.filter((t: ComponentTemplate) => {
    if (t.component_type === 'QUIZ') return false
    if (t.component_type === 'LAB' && !resolved?.hasLabComponent) return false
    return true
  })

  function reset() {
    setForm(EMPTY_FORM)
    setPickedAssignmentId('')
  }

  const createMutation = useMutation({
    mutationFn: sisApi.createMarksComponent,
    onSuccess:  (component) => {
      qc.invalidateQueries({ queryKey: ['marks-components-my'] })
      qc.invalidateQueries({ queryKey: ['marks-components'] })
      reset()
      onOpenChange(false)
      onCreated?.(component)
    },
  })

  function applyTemplate(t: ComponentTemplate) {
    setForm(f => ({ ...f, component_type: t.component_type, name: t.name, max_marks: String(t.max_marks) }))
  }

  function handleCreate() {
    if (!resolved) return
    createMutation.mutate({
      course_id:      resolved.courseId,
      section_id:     resolved.sectionId,
      semester_id:    resolved.semesterId,
      component_type: form.component_type,
      name:           form.name.trim(),
      max_marks:      parseFloat(form.max_marks),
      weightage:      form.weightage ? parseFloat(form.weightage) : undefined,
      due_date:       form.due_date || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o) }}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Add Assessment Component</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          {/* Class context — a picker when unknown, read-only when the page knows it */}
          {context ? (
            <div className="rounded-md border bg-muted/20 px-3 py-2 text-sm space-y-0.5">
              <p><span className="text-muted-foreground">Course:</span> <span className="font-medium">{resolved?.courseLabel}</span></p>
              <p><span className="text-muted-foreground">Semester:</span> <span className="font-medium">{resolved?.semesterLabel}</span></p>
              <p><span className="text-muted-foreground">Section:</span> <span className="font-medium">{resolved?.sectionLabel ?? 'All sections (elective)'}</span></p>
            </div>
          ) : (
            <div>
              <p className="text-xs font-medium mb-1">Course</p>
              <Select value={pickedAssignmentId} onValueChange={setPickedAssignmentId}>
                <SelectTrigger><SelectValue placeholder="Select one of your assigned classes" /></SelectTrigger>
                <SelectContent>
                  {assignments.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.course?.code} {a.course?.title} — {a.section?.name ? `Sec ${a.section.name}` : 'All sections'}
                      {a.semester ? ` · Semester ${a.semester.number}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="border-t pt-4 space-y-3">
            <div>
              <p className="text-xs text-muted-foreground mb-2">Quick-fill from template</p>
              <div className="flex flex-wrap gap-2">
                {visibleTemplates.map((t: ComponentTemplate) => (
                  <Button key={t.template_key} size="sm" variant="outline" onClick={() => applyTemplate(t)}>
                    {t.name}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-medium mb-1">Type</p>
                <Select value={form.component_type} onValueChange={v => setForm(f => ({ ...f, component_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {types.map(t => <SelectItem key={t} value={t}>{TYPE_LABELS[t]}</SelectItem>)}
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
          <Button onClick={handleCreate} disabled={createMutation.isPending || !resolved || !form.name || !form.max_marks}>
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
