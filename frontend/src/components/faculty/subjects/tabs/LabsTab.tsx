import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FlaskConical, ExternalLink, Plus, Send, Lock as LockIcon, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useLabAssignments, useSubmissions, usePublishAssignment, useCloseAssignment } from '@/hooks/labs'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { CreateLabDialog } from '@/components/labs/CreateLabDialog'
import { LabReviewForm } from '@/components/labs/LabReviewForm'
import { SubmissionRow } from '@/components/labs/SubmissionRow'
import type { AssignmentStatus } from '@/types/labs'
import type { FacultySubjectTabProps } from './types'

const STATUS_VARIANT: Record<AssignmentStatus, 'default' | 'success' | 'warning' | 'info'> = {
  DRAFT: 'default',
  PUBLISHED: 'success',
  CLOSED: 'warning',
  ARCHIVED: 'info',
}

type DialogState =
  | { type: 'create' }
  | { type: 'submissions'; labId: string }
  | { type: 'review'; labId: string; submissionId: string }
  | null

function SubmissionsPanel({ labId, onReview }: { labId: string; onReview: (submissionId: string) => void }) {
  const { data, isLoading } = useSubmissions(labId)
  const submissions = data?.items ?? []

  if (isLoading) {
    return <div className="text-sm text-gray-400 py-8 text-center">Loading submissions…</div>
  }
  if (submissions.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Users className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No submissions yet.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
      {submissions.map((sub) => (
        <SubmissionRow key={sub.id} sub={sub} onReview={() => onReview(sub.id)} />
      ))}
    </div>
  )
}

export function LabsTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const { syllabusId } = ctx
  const [dialog, setDialog] = useState<DialogState>(null)

  const { data, isLoading, isError } = useLabAssignments({ syllabus_id: syllabusId ?? undefined })
  const items = data?.items ?? []

  const publish = usePublishAssignment()
  const close = useCloseAssignment()

  function handlePublish(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    publish.mutate(id, {
      onSuccess: () => addToast('Lab published.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleClose(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    close.mutate(id, {
      onSuccess: () => addToast('Lab closed.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          {data ? `${data.total} lab${data.total !== 1 ? 's' : ''}` : 'Labs'}
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setDialog({ type: 'create' })}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Create Lab
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/labs${syllabusId ? `?syllabus_id=${syllabusId}` : ''}`)}
          >
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            Open Full Page
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading labs…</div>
      ) : isError ? (
        <div className="text-sm text-gray-400 py-8 text-center">Failed to load labs.</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <FlaskConical className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No lab assignments yet for this subject.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setDialog({ type: 'submissions', labId: a.id })}
              className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{a.title}</p>
                <p className="text-xs text-gray-400">
                  {a.submission_type}
                  {a.max_marks != null ? ` · ${a.max_marks} marks` : ''}
                  {a.deadline ? ` · Due ${new Date(a.deadline).toLocaleDateString()}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                {a.status === 'DRAFT' && (
                  <Button size="sm" variant="outline" onClick={(e) => handlePublish(a.id, e)}>
                    <Send className="h-3.5 w-3.5 mr-1" />
                    Publish
                  </Button>
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

      {dialog?.type === 'create' && (
        <CreateLabDialog
          onClose={() => setDialog(null)}
          onCreated={() => setDialog(null)}
        />
      )}

      <Dialog
        open={dialog?.type === 'submissions'}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {dialog?.type === 'submissions' && (
            <SubmissionsPanel
              labId={dialog.labId}
              onReview={(submissionId) => setDialog({ type: 'review', labId: dialog.labId, submissionId })}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={dialog?.type === 'review'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto">
          {dialog?.type === 'review' && (
            <LabReviewForm
              submissionId={dialog.submissionId}
              onBack={() => setDialog({ type: 'submissions', labId: dialog.labId })}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
