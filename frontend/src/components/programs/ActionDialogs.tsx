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
  onSubmit: (promptHint?: string) => void
  isPending?: boolean
}

export function GenerateDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
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
        <DialogHeader>
          <DialogTitle>Generate Program Structure with AI</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Prompt Hint (optional)
            </label>
            <Textarea
              rows={3}
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              placeholder="e.g. Focus on data science and machine learning tracks"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
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
  onSubmit: (notes?: string) => void
  isPending?: boolean
}

export function ApproveDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
}: ApproveDialogProps) {
  const [notes, setNotes] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(notes || undefined)
    setNotes('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Approve Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Approval Notes (optional)
            </label>
            <Textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Once approved, the program becomes immutable. Future changes require a version fork.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isPending}
              className="bg-green-600 hover:bg-green-700"
            >
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
  onSubmit: (reason?: string) => void
  isPending?: boolean
}

export function RejectDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
}: RejectDialogProps) {
  const [reason, setReason] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(reason || undefined)
    setReason('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reject Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Rejection Reason
            </label>
            <Textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Please provide the reason for rejection…"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={isPending}>
              {isPending ? 'Rejecting…' : 'Reject'}
            </Button>
          </DialogFooter>
        </form>
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
  onSubmit: (format: 'pdf' | 'docx') => void
  isPending?: boolean
}

export function ExportDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
}: ExportDialogProps) {
  const [format, setFormat] = useState<'pdf' | 'docx'>('pdf')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(format)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Export Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Format</label>
            <Select value={format} onValueChange={(v) => setFormat(v as 'pdf' | 'docx')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pdf">PDF</SelectItem>
                <SelectItem value="docx">DOCX (Word)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-sm text-gray-500">
            Export runs in the background. The download link will appear in the job result.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Starting…' : 'Export'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
