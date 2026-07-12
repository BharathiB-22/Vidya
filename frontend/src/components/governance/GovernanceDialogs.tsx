import { useState } from 'react'
import { Lock, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface BaseProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isPending?: boolean
}

// ---------------------------------------------------------------------------
// Board → Generate the official syllabus for every subject
// ---------------------------------------------------------------------------

export function GenerateSyllabiDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  missingCount,
  totalCount,
}: BaseProps & {
  onConfirm: (regenerateAll: boolean) => void
  missingCount: number
  totalCount: number
}) {
  const [regenerateAll, setRegenerateAll] = useState(false)
  const count = regenerateAll ? totalCount : missingCount

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-black font-bold">Generate the Official Syllabus</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-gray-700">
            One AI call per subject, run in the background. Each subject is generated
            independently, so a failure on one costs you nothing on the others — and you can
            leave this page while it runs.
          </p>

          {missingCount > 0 && (
            <label className="flex items-start gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
              <input
                type="checkbox"
                className="mt-1"
                checked={regenerateAll}
                onChange={(e) => setRegenerateAll(e.target.checked)}
              />
              <span className="text-sm text-gray-800">
                <span className="font-semibold text-black">Regenerate everything</span>
                <span className="block text-gray-600">
                  Also rewrite the {totalCount - missingCount} subject
                  {totalCount - missingCount === 1 ? '' : 's'} that already have a syllabus,
                  discarding any edits you have made to them. Leave this off to generate only
                  the {missingCount} that are missing.
                </span>
              </span>
            </label>
          )}

          <div className="flex gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
            <Sparkles className="h-4 w-4 shrink-0 text-blue-600 mt-0.5" />
            <p className="text-sm text-blue-900">
              Every generated syllabus arrives as a <span className="font-semibold">draft</span>.
              The AI advises; you decide. Each one has to be reviewed and approved by a member
              of the board before the curriculum can be approved.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={isPending || count === 0}
            onClick={() => onConfirm(regenerateAll)}
          >
            <Sparkles className="h-4 w-4 mr-1" />
            {isPending ? 'Queueing…' : `Generate ${count} Syllab${count === 1 ? 'us' : 'i'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Board → Approve + Lock. Permanent.
// ---------------------------------------------------------------------------

export function ApproveCurriculumDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  subjectCount,
}: BaseProps & { onConfirm: (comment?: string) => void; subjectCount?: number }) {
  const [comment, setComment] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onConfirm(comment || undefined)
    setComment('')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-black font-bold">Approve Curriculum</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-semibold text-black mb-1">
              Approval notes (optional)
            </label>
            <Textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Recorded against this approval…"
            />
          </div>
          <div className="flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
            <Lock className="h-4 w-4 shrink-0 text-emerald-700 mt-0.5" />
            <div className="text-sm text-emerald-900 space-y-1">
              <p className="font-semibold">This is permanent.</p>
              <p>
                The program structure
                {typeof subjectCount === 'number' && subjectCount > 0
                  ? ` and all ${subjectCount} official syllabi`
                  : ' and every official syllabus'}{' '}
                are frozen for everyone — the Dean, an Admin, and the board itself. Elective
                baskets are frozen too: no subject can be added afterwards. A future academic
                change means a new curriculum version.
              </p>
              <p>The Dean will be notified, shown what changed, and can then publish it.</p>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending} className="bg-emerald-600 hover:bg-emerald-700">
              <Lock className="h-4 w-4 mr-1" />
              {isPending ? 'Approving…' : 'Approve & Lock'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// SubmitForApprovalDialog now lives in SubmitToBoardFlow, which validates the
// curriculum FIRST and only shows a confirmation once it is actually ready —
// submitting is irreversible, so a checklist beforehand beats an error afterwards.
//
// ReturnToDeanDialog is gone entirely. The Board never returns a curriculum to the
// Dean; it enhances the curriculum itself. There is no transition to drive.
