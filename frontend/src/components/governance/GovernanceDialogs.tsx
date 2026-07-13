import { useState } from 'react'
import { Lock } from 'lucide-react'
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
// GenerateSyllabiDialog is gone, with the bulk endpoint it drove.
//
// It asked the Board one question — "shall I draft all forty of these?" — and a Board of
// Studies does not think that way. It decides subject by subject whether THIS syllabus
// wants an AI draft or is better written by the professor who has taught it for fifteen
// years. That choice now lives on each row of the curriculum workbench, and the AI runs
// only when somebody asks it to. See PrepareSyllabusDialog.
// ---------------------------------------------------------------------------

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
