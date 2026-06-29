import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ---------------------------------------------------------------------------
// Generate Dialog
// ---------------------------------------------------------------------------

interface GenerateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (instructions?: string) => void
  isPending?: boolean
}

export function GenerateSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: GenerateDialogProps) {
  const [hint, setHint] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(hint || undefined)
    setHint('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Generate Syllabus with AI</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom Instructions (optional)
            </label>
            <Textarea
              rows={3}
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              placeholder="e.g. Emphasise hands-on labs and industry tools"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Submitting…' : 'Generate'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Approve Dialog
// ---------------------------------------------------------------------------

interface ApproveDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (comment?: string) => void
  isPending?: boolean
}

export function ApproveSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: ApproveDialogProps) {
  const [comment, setComment] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(comment || undefined)
    setComment('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Approve Syllabus</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Approval Comment (optional)
            </label>
            <Textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Once approved, this syllabus becomes immutable. Future changes require a version fork or rejection.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending} className="bg-green-600 hover:bg-green-700">
              {isPending ? 'Approving…' : 'Approve'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Reject Dialog
// ---------------------------------------------------------------------------

interface RejectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (reason: string) => void
  isPending?: boolean
}

export function RejectSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: RejectDialogProps) {
  const [reason, setReason] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (reason.length < 5) return
    onSubmit(reason)
    setReason('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Reject Syllabus</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Rejection Reason <span className="text-red-500">*</span>
            </label>
            <Textarea
              rows={3}
              required
              minLength={5}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Please provide the reason for rejection…"
            />
          </div>
          <p className="text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded-md p-3">
            Rejection creates a new DRAFT version for revision. The approved version is preserved.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="destructive" disabled={isPending || reason.length < 5}>
              {isPending ? 'Rejecting…' : 'Reject'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Lock Dialog
// ---------------------------------------------------------------------------

interface LockDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (comment?: string) => void
  isPending?: boolean
}

export function LockSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: LockDialogProps) {
  const [comment, setComment] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(comment || undefined)
    setComment('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Lock Syllabus for Semester</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Lock Comment (optional)
            </label>
            <Input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. Locked for Semester 5 AY 2025-26"
            />
          </div>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Locking freezes the syllabus for the current semester. Only Admins/Deans can unlock.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending} className="bg-orange-600 hover:bg-orange-700">
              {isPending ? 'Locking…' : 'Lock'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Fork Dialog
// ---------------------------------------------------------------------------

interface ForkDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (changeNote?: string) => void
  isPending?: boolean
}

export function ForkSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: ForkDialogProps) {
  const [note, setNote] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(note || undefined)
    setNote('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Fork Syllabus Version</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Change Note (optional)
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Updating lab component for new curriculum"
            />
          </div>
          <p className="text-sm text-gray-500">
            Creates a new DRAFT version copying all outcomes, units, and references.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Forking…' : 'Fork Version'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Request Revision Dialog (Dean — from PENDING_REVIEW)
// ---------------------------------------------------------------------------

interface RequestRevisionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (comments: string) => void
  isPending?: boolean
}

export function RequestRevisionDialog({
  open, onOpenChange, onSubmit, isPending,
}: RequestRevisionDialogProps) {
  const [comments, setComments] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (comments.length < 5) return
    onSubmit(comments)
    setComments('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Request Revision</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Revision Comments <span className="text-red-500">*</span>
            </label>
            <Textarea
              rows={4}
              required
              minLength={5}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="e.g. Improve CO mapping. Add Bloom levels. Add practical outcomes."
            />
          </div>
          <p className="text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded-md p-3">
            The syllabus will be returned to faculty as REJECTED with your comments. Faculty can revise and resubmit.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button
              type="submit"
              disabled={isPending || comments.length < 5}
              className="bg-orange-600 hover:bg-orange-700"
            >
              {isPending ? 'Sending…' : 'Request Revision'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Delete Confirm Dialog
// ---------------------------------------------------------------------------

interface DeleteConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  status: string
  isPending?: boolean
}

export function DeleteConfirmDialog({
  open, onOpenChange, onConfirm, status, isPending,
}: DeleteConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Delete Syllabus</DialogTitle></DialogHeader>
        <p className="text-sm text-gray-600 py-2">
          Are you sure you want to delete this <strong>{status}</strong> syllabus?
          This action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="destructive"
            onClick={() => { onConfirm(); onOpenChange(false) }}
            disabled={isPending}
          >
            {isPending ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Export Dialog
// ---------------------------------------------------------------------------

interface ExportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (format: 'pdf' | 'docx' | 'json') => void
  isPending?: boolean
}

export function ExportSyllabusDialog({
  open, onOpenChange, onSubmit, isPending,
}: ExportDialogProps) {
  const [format, setFormat] = useState<'pdf' | 'docx' | 'json'>('pdf')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(format)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Export Syllabus</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Format</label>
            <Select value={format} onValueChange={(v) => setFormat(v as typeof format)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pdf">PDF</SelectItem>
                <SelectItem value="docx">DOCX (Word)</SelectItem>
                <SelectItem value="json">JSON</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-sm text-gray-500">
            Export runs in the background. The download link will appear in the job result.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Starting…' : 'Export'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
