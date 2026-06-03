import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, ChevronRight, Lock, Eye, Trash2, BookOpen, Info, AlertTriangle, BookMarked } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { sisApi, MarksComponent, ComponentTemplate } from '@/lib/api/sis'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:     'bg-yellow-100 text-yellow-800 border-yellow-200',
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}

const TYPES = ['CIE', 'ASSIGNMENT', 'QUIZ', 'LAB', 'OTHER']
const TYPE_LABELS: Record<string, string> = {
  CIE: 'CIE', ASSIGNMENT: 'Assignment', QUIZ: 'Quiz', LAB: 'Lab', OTHER: 'Other',
}

interface FormState {
  semester_id: string; course_id: string; section_id: string
  component_type: string; name: string; max_marks: string
  weightage: string; due_date: string
}

const EMPTY_FORM: FormState = {
  semester_id: '', course_id: '', section_id: '',
  component_type: 'CIE', name: '', max_marks: '', weightage: '', due_date: '',
}

export default function InternalMarksSetupPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [showAdd, setShowAdd]           = useState(false)
  const [form, setForm]                 = useState<FormState>(EMPTY_FORM)
  const [deleteTarget, setDeleteTarget] = useState<MarksComponent | null>(null)
  const [publishTarget, setPublishTarget] = useState<MarksComponent | null>(null)

  const { data: templates = [] } = useQuery({
    queryKey: ['component-templates'],
    queryFn:  sisApi.listComponentTemplates,
  })

  const { data: components = [], isLoading } = useQuery({
    queryKey: ['marks-components-my'],
    queryFn:  () => sisApi.listMarksComponents({}),
  })

  const createMutation = useMutation({
    mutationFn: sisApi.createMarksComponent,
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['marks-components-my'] }); setShowAdd(false); setForm(EMPTY_FORM) },
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => sisApi.deleteMarksComponent(id),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['marks-components-my'] }); setDeleteTarget(null) },
  })
  const publishMutation = useMutation({
    mutationFn: (id: string) => sisApi.publishMarksComponent(id),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['marks-components-my'] }); setPublishTarget(null) },
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

  // Group by course+section
  const grouped: Record<string, { label: string; items: MarksComponent[] }> = {}
  for (const c of components) {
    const key = `${c.course_id}::${c.section_id}`
    if (!grouped[key]) grouped[key] = { label: `${c.course_code ?? 'Course'} — ${c.section_name ?? 'Section'}`, items: [] }
    grouped[key].items.push(c)
  }

  return (
    <PageShell>
      <PageHeader
        icon={BookMarked}
        title="Internal Marks Setup"
        subtitle="Define and manage assessment components for your assigned courses."
        action={<Button size="sm" onClick={() => setShowAdd(true)}><Plus className="mr-1 h-4 w-4" />Add Component</Button>}
      />

      {/* Advisory */}
      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-4">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          <strong>DRAFT</strong> components are not visible to students. Publish when ready.
          After publishing, any marks edit requires a reason.
        </span>
      </div>

      {isLoading && <p className="text-muted-foreground">Loading…</p>}

      {Object.entries(grouped).map(([key, group]) => (
        <div key={key} className="rounded-md border mb-4 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2 bg-muted/30 border-b">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium text-sm">{group.label}</span>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Name</th>
                <th className="px-4 py-2 text-left">Type</th>
                <th className="px-4 py-2 text-right">Max</th>
                <th className="px-4 py-2 text-right">Fill</th>
                <th className="px-4 py-2 text-center">Status</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {group.items.map(c => (
                <tr key={c.id} className="hover:bg-muted/10">
                  <td className="px-4 py-2 font-medium">{c.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{TYPE_LABELS[c.component_type] ?? c.component_type}</td>
                  <td className="px-4 py-2 text-right">{c.max_marks}</td>
                  <td className="px-4 py-2 text-right text-muted-foreground">{c.filled_count}/{c.entries_count}</td>
                  <td className="px-4 py-2 text-center">
                    <Badge variant="outline" className={`text-xs ${STATUS_COLORS[c.status]}`}>{c.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {c.status === 'DRAFT' && (
                        <>
                          <Button size="sm" variant="ghost" onClick={() => setPublishTarget(c)}>
                            <Eye className="h-3 w-3 mr-1" />Publish
                          </Button>
                          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDeleteTarget(c)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                      {(c.status === 'DRAFT' || c.status === 'PUBLISHED') && (
                        <Button size="sm" variant="ghost" onClick={() => navigate(`/sis/marks/entry/${c.id}`)}>
                          Enter Marks <ChevronRight className="h-3 w-3 ml-1" />
                        </Button>
                      )}
                      {c.status === 'LOCKED' && <Lock className="h-4 w-4 text-muted-foreground mt-1 mr-2" />}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {components.length === 0 && !isLoading && (
        <div className="text-center py-16 text-muted-foreground">
          No components yet. Click "Add Component" to create your first assessment component.
        </div>
      )}

      {/* Add Component Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
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
            <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending || !form.name || !form.max_marks}>
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Publish Confirm */}
      <Dialog open={!!publishTarget} onOpenChange={() => setPublishTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Publish Component</DialogTitle></DialogHeader>
          <div className="flex gap-2 items-start rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            Publishing <strong>{publishTarget?.name}</strong> makes it visible to students and requires a reason for future mark edits.
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishTarget(null)}>Cancel</Button>
            <Button onClick={() => publishTarget && publishMutation.mutate(publishTarget.id)} disabled={publishMutation.isPending}>
              {publishMutation.isPending ? 'Publishing…' : 'Publish'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Component</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Delete <strong>{deleteTarget?.name}</strong>? This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)} disabled={deleteMutation.isPending}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  )
}
