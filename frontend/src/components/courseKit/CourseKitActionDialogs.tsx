import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ComplexityLevel } from '@/types/courseKit'

// ---------------------------------------------------------------------------
// Generate Dialog
// ---------------------------------------------------------------------------

interface GenerateDialogProps {
  open:               boolean
  onOpenChange:       (open: boolean) => void
  onSubmit:           (opts: { custom_instructions?: string; complexity_level?: ComplexityLevel; tone?: string }) => void
  isPending?:         boolean
  initialComplexity?: ComplexityLevel
}

export function GenerateKitDialog({
  open, onOpenChange, onSubmit, isPending, initialComplexity,
}: GenerateDialogProps) {
  const [instructions, setInstructions] = useState('')
  const [complexity,   setComplexity]   = useState<ComplexityLevel>(initialComplexity ?? 'UG')
  const [tone,         setTone]         = useState('')

  useEffect(() => {
    if (open) {
      setInstructions('')
      setComplexity(initialComplexity ?? 'UG')
      setTone('')
    }
  }, [open, initialComplexity])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      custom_instructions: instructions || undefined,
      complexity_level:    complexity,
      tone:                tone || undefined,
    })
    setInstructions('')
    setTone('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Generate Course Kit with AI</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Complexity Level</label>
            <Select value={complexity} onValueChange={(v) => setComplexity(v as ComplexityLevel)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="UG">UG (Undergraduate)</SelectItem>
                <SelectItem value="PG">PG (Postgraduate)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tone (optional)
            </label>
            <Input
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              placeholder="e.g. formal, engaging, concise"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom Instructions (optional)
            </label>
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="e.g. Include real-world industry examples for each topic"
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
// Publish Dialog
// ---------------------------------------------------------------------------

interface PublishDialogProps {
  open:         boolean
  onOpenChange: (open: boolean) => void
  onSubmit:     (comment?: string) => void
  isPending?:   boolean
}

export function PublishKitDialog({ open, onOpenChange, onSubmit, isPending }: PublishDialogProps) {
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
        <DialogHeader><DialogTitle>Publish Course Kit</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Publish Comment (optional)
            </label>
            <Textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Once published, this kit becomes available to students. Use Archive or Fork to make changes.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending} className="bg-green-600 hover:bg-green-700">
              {isPending ? 'Publishing…' : 'Publish'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Archive Dialog
// ---------------------------------------------------------------------------

interface ArchiveDialogProps {
  open:         boolean
  onOpenChange: (open: boolean) => void
  onSubmit:     (reason: string) => void
  isPending?:   boolean
}

export function ArchiveKitDialog({ open, onOpenChange, onSubmit, isPending }: ArchiveDialogProps) {
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
        <DialogHeader><DialogTitle>Archive Course Kit</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Archive Reason <span className="text-red-500">*</span>
            </label>
            <Textarea
              rows={3}
              required
              minLength={5}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Please provide a reason for archiving…"
            />
          </div>
          <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-md p-3">
            Archived kits are read-only. Use Fork to create a new version from an archived kit.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={isPending || reason.length < 5}
            >
              {isPending ? 'Archiving…' : 'Archive'}
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
  open:         boolean
  onOpenChange: (open: boolean) => void
  onSubmit:     (changeNote?: string) => void
  isPending?:   boolean
}

export function ForkKitDialog({ open, onOpenChange, onSubmit, isPending }: ForkDialogProps) {
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
        <DialogHeader><DialogTitle>Fork Course Kit</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Change Note (optional)
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Updated for revised curriculum AY 2025-26"
            />
          </div>
          <p className="text-sm text-gray-500">
            Creates a new DRAFT kit copying all slides and assignments.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Forking…' : 'Fork'}
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
  open:         boolean
  onOpenChange: (open: boolean) => void
  onSubmit:     (format: 'pdf' | 'pptx' | 'handout') => void
  isPending?:   boolean
}

export function ExportKitDialog({ open, onOpenChange, onSubmit, isPending }: ExportDialogProps) {
  const [format, setFormat] = useState<'pdf' | 'pptx' | 'handout'>('pptx')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(format)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Export Course Kit</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Format</label>
            <Select value={format} onValueChange={(v) => setFormat(v as 'pdf' | 'pptx' | 'handout')}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pptx">PowerPoint (PPTX) — faculty deck with notes</SelectItem>
                <SelectItem value="pdf">PDF — faculty slide deck</SelectItem>
                <SelectItem value="handout">Student Handout (PDF) — sanitized, no answer keys</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-sm text-gray-500">
            Export runs in the background. The download link will appear in the Exports tab.
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
