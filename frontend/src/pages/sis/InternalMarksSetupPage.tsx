import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, ChevronRight, Lock, Eye, Trash2, BookOpen, Info, BookMarked } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { sisApi, MarksComponent } from '@/lib/api/sis'
import { CreateComponentDialog } from '@/components/marks/CreateComponentDialog'
import { PublishComponentDialog, DeleteComponentDialog } from '@/components/marks/ComponentConfirmDialogs'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:     'bg-yellow-100 text-yellow-800 border-yellow-200',
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}

const TYPE_LABELS: Record<string, string> = {
  CIE: 'CIE', ASSIGNMENT: 'Assignment', QUIZ: 'Quiz', LAB: 'Lab', OTHER: 'Other',
}

export default function InternalMarksSetupPage() {
  const navigate = useNavigate()

  const [showAdd, setShowAdd]           = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<MarksComponent | null>(null)
  const [publishTarget, setPublishTarget] = useState<MarksComponent | null>(null)

  const { data: components = [], isLoading } = useQuery({
    queryKey: ['marks-components-my'],
    queryFn:  () => sisApi.listMarksComponents({}),
  })

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

      <CreateComponentDialog open={showAdd} onOpenChange={setShowAdd} />
      <PublishComponentDialog component={publishTarget} onClose={() => setPublishTarget(null)} />
      <DeleteComponentDialog component={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </PageShell>
  )
}
