import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ClipboardCheck, ExternalLink, FileBarChart, PenLine, Plus, Eye, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { sisApi, MarksComponent } from '@/lib/api/sis'
import { CreateComponentDialog } from '@/components/marks/CreateComponentDialog'
import { PublishComponentDialog, DeleteComponentDialog } from '@/components/marks/ComponentConfirmDialogs'
import { MarkEntryGrid } from '@/components/marks/MarkEntryGrid'
import type { FacultySubjectTabProps } from './types'

const STATUS_VARIANT: Record<string, 'default' | 'success' | 'info'> = {
  DRAFT: 'default',
  PUBLISHED: 'success',
  LOCKED: 'info',
}

export function MarksTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const { course_id, section_id, semester_id } = ctx.assignment
  const [showCreate, setShowCreate] = useState(false)
  const [entryComponentId, setEntryComponentId] = useState<string | null>(null)
  const [publishTarget, setPublishTarget] = useState<MarksComponent | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<MarksComponent | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['marks-components', course_id, section_id],
    queryFn: () => sisApi.listMarksComponents({ course_id, section_id: section_id ?? undefined }),
  })
  const items = data ?? []
  const publishedCount = items.filter((c) => c.status === 'PUBLISHED').length

  // "Enter Marks" jumps straight into the most actionable existing component
  // (still open for entry) rather than the setup page, when one exists.
  const enterableComponent = items.find((c) => c.status !== 'LOCKED' && c.filled_count < c.entries_count)
    ?? items.find((c) => c.status !== 'LOCKED')

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          {items.length} mark component{items.length !== 1 ? 's' : ''} · {publishedCount} published
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Create Component
          </Button>
          <Button
            size="sm"
            onClick={() => enterableComponent ? setEntryComponentId(enterableComponent.id) : setShowCreate(true)}
          >
            <PenLine className="h-3.5 w-3.5 mr-1.5" />
            Enter Marks
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/sis/marks/report')}>
            <FileBarChart className="h-3.5 w-3.5 mr-1.5" />
            View Full Marks
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading mark components…</div>
      ) : isError ? (
        <div className="text-sm text-gray-400 py-8 text-center">Failed to load mark components.</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <ClipboardCheck className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No internal mark components set up yet for this subject.</p>
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
              <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
              Set Up a Component
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((c) => {
            const pending = Math.max(c.entries_count - c.filled_count, 0)
            return (
              <div
                key={c.id}
                className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <button
                  type="button"
                  onClick={() => setEntryComponentId(c.id)}
                  className="min-w-0 text-left flex-1"
                >
                  <p className="text-sm font-medium text-gray-800 truncate">{c.name}</p>
                  <p className="text-xs text-gray-400">
                    {c.component_type} · Max {c.max_marks}
                    {c.entries_count > 0 && (
                      <> · {c.filled_count}/{c.entries_count} entered{pending > 0 ? ` (${pending} pending)` : ''}</>
                    )}
                  </p>
                </button>
                <div className="flex items-center gap-2 shrink-0">
                  {c.status === 'DRAFT' && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setPublishTarget(c)}>
                        <Eye className="h-3.5 w-3.5 mr-1" />
                        Publish
                      </Button>
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDeleteTarget(c)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  )}
                  <Badge variant={STATUS_VARIANT[c.status] ?? 'default'}>{c.status}</Badge>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <CreateComponentDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        context={{
          courseId:        course_id,
          sectionId:       section_id ?? undefined,
          semesterId:      semester_id,
          courseLabel:     [ctx.assignment.course?.code, ctx.assignment.course?.title].filter(Boolean).join(' — ') || 'Course',
          sectionLabel:    ctx.assignment.section?.name ?? undefined,
          semesterLabel:   ctx.assignment.semester ? `Semester ${ctx.assignment.semester.number}` : '',
          hasLabComponent: ctx.hasLabComponent,
        }}
        onCreated={(created) => setEntryComponentId(created.id)}
      />
      <PublishComponentDialog component={publishTarget} onClose={() => setPublishTarget(null)} />
      <DeleteComponentDialog component={deleteTarget} onClose={() => setDeleteTarget(null)} />

      <Dialog open={!!entryComponentId} onOpenChange={(open) => !open && setEntryComponentId(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          {entryComponentId && <MarkEntryGrid componentId={entryComponentId} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
