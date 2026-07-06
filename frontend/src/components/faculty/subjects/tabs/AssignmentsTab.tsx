import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, Plus, Pencil, Send, Lock as LockIcon, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useAssignments, usePublishAssignment, useCloseAssignment } from '@/hooks/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { AssignmentForm } from '@/components/coursework/AssignmentForm'
import { AssignmentGradingPanel } from '@/components/coursework/AssignmentGradingPanel'
import type { CourseworkStatus } from '@/types/coursework'
import type { FacultySubjectTabProps } from './types'

const STATUS_VARIANT: Record<CourseworkStatus, 'default' | 'success' | 'warning' | 'info'> = {
  DRAFT: 'default',
  PUBLISHED: 'success',
  CLOSED: 'warning',
  ARCHIVED: 'info',
}

type DialogState =
  | { type: 'create' }
  | { type: 'edit'; id: string }
  | { type: 'grade'; id: string }
  | null

export function AssignmentsTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const { syllabusId } = ctx
  const [dialog, setDialog] = useState<DialogState>(null)

  const { data, isLoading, isError } = useAssignments({ syllabus_id: syllabusId ?? undefined })
  const items = data?.items ?? []

  const publish = usePublishAssignment()
  const close = useCloseAssignment()

  function handlePublish(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    publish.mutate(id, {
      onSuccess: () => addToast('Assignment published — students have been notified.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleClose(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    close.mutate(id, {
      onSuccess: () => addToast('Assignment closed.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          {data ? `${data.total} assignment${data.total !== 1 ? 's' : ''}` : 'Assignments'}
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setDialog({ type: 'create' })}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Create Assignment
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/faculty/assignments${syllabusId ? `?syllabus_id=${syllabusId}` : ''}`)}
          >
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            Open Full Page
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading assignments…</div>
      ) : isError ? (
        <div className="text-sm text-gray-400 py-8 text-center">Failed to load assignments.</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <ClipboardList className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No assignments yet for this subject.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setDialog({ type: 'grade', id: a.id })}
              className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{a.title}</p>
                <p className="text-xs text-gray-400">
                  {a.assignment_type} · {a.max_marks} marks · Due {new Date(a.due_date).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                {a.status === 'DRAFT' && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => setDialog({ type: 'edit', id: a.id })}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={(e) => handlePublish(a.id, e)}>
                      <Send className="h-3.5 w-3.5 mr-1" />
                      Publish
                    </Button>
                  </>
                )}
                {a.status === 'PUBLISHED' && (
                  <Button size="sm" variant="outline" onClick={(e) => handleClose(a.id, e)}>
                    <LockIcon className="h-3.5 w-3.5 mr-1" />
                    Close
                  </Button>
                )}
                <Badge variant={STATUS_VARIANT[a.status]}>{a.status}</Badge>
              </div>
            </button>
          ))}
        </div>
      )}

      <Dialog open={dialog?.type === 'create'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <AssignmentForm
            syllabusId={syllabusId ?? undefined}
            onCreated={() => setDialog(null)}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={dialog?.type === 'edit'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {dialog?.type === 'edit' && (
            <AssignmentForm
              assignmentId={dialog.id}
              onUpdated={() => setDialog(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={dialog?.type === 'grade'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          {dialog?.type === 'grade' && <AssignmentGradingPanel assignmentId={dialog.id} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
