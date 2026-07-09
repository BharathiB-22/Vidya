import { useEffect, useState } from 'react'
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
import type { Program, ProgramUpdate } from '@/types/program'

// ---------------------------------------------------------------------------
// Edit Dialog
// ---------------------------------------------------------------------------

interface EditProgramDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  program: Program
  onSubmit: (payload: ProgramUpdate) => void
  isPending?: boolean
}

export function EditProgramDialog({
  open,
  onOpenChange,
  program,
  onSubmit,
  isPending,
}: EditProgramDialogProps) {
  const [title,           setTitle]           = useState(program.title)
  const [degreeType,      setDegreeType]      = useState(program.degree_type)
  const [department,      setDepartment]      = useState(program.department)
  const [durationYears,   setDurationYears]   = useState(String(program.duration_years))
  const [totalCredits,    setTotalCredits]    = useState(String(program.total_credits))
  const [aiInstructions,  setAiInstructions]  = useState(program.ai_instructions ?? '')

  useEffect(() => {
    if (open) {
      setTitle(program.title)
      setDegreeType(program.degree_type)
      setDepartment(program.department)
      setDurationYears(String(program.duration_years))
      setTotalCredits(String(program.total_credits))
      setAiInstructions(program.ai_instructions ?? '')
    }
  }, [open, program])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload: ProgramUpdate = {}
    if (title        !== program.title)                        payload.title         = title
    if (degreeType   !== program.degree_type)                  payload.degree_type   = degreeType
    if (department   !== program.department)                   payload.department    = department
    if (Number(durationYears) !== program.duration_years)      payload.duration_years = Number(durationYears)
    if (Number(totalCredits)  !== program.total_credits)       payload.total_credits  = Number(totalCredits)
    const instrNorm = aiInstructions.trim() || null
    if (instrNorm !== (program.ai_instructions ?? null))       payload.ai_instructions = instrNorm ?? undefined
    if (Object.keys(payload).length === 0) { onOpenChange(false); return }
    onSubmit(payload)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <Input value={title} onChange={e => setTitle(e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Degree Type</label>
              <Input value={degreeType} onChange={e => setDegreeType(e.target.value)} required />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
              <Input value={department} onChange={e => setDepartment(e.target.value)} required />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Duration (years)</label>
              <Input
                type="number" min={1} max={10}
                value={durationYears}
                onChange={e => setDurationYears(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Total Credits</label>
              <Input
                type="number" min={1}
                value={totalCredits}
                onChange={e => setTotalCredits(e.target.value)}
                required
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              AI Instructions
              <span className="text-gray-400 font-normal ml-1">(optional)</span>
            </label>
            <Textarea
              rows={3}
              value={aiInstructions}
              onChange={e => setAiInstructions(e.target.value)}
              placeholder="e.g. Final semester only project and internship. Major project 10 credits."
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Delete Dialog
// ---------------------------------------------------------------------------

interface DeleteProgramDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  programTitle: string
  onConfirm: () => void
  isPending?: boolean
}

export function DeleteProgramDialog({
  open,
  onOpenChange,
  programTitle,
  onConfirm,
  isPending,
}: DeleteProgramDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Program</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-gray-700">
            Delete <strong>{programTitle}</strong>? This will permanently remove the program,
            all its courses, and outcomes. This cannot be undone.
          </p>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Draft and Pending Approval programs can be deleted. Once Approved or Published, a
            program can no longer be deleted — create a new version to make changes instead.
          </p>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={isPending} onClick={onConfirm}>
            {isPending ? 'Deleting…' : 'Delete Program'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Generate Dialog
// ---------------------------------------------------------------------------

interface GenerateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (promptHint?: string, aiInstructions?: string) => void
  isPending?: boolean
  storedInstructions?: string | null
}

export function GenerateDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
  storedInstructions,
}: GenerateDialogProps) {
  const [hint, setHint] = useState('')
  const [instructions, setInstructions] = useState('')

  // Sync instructions from program when dialog opens
  useEffect(() => {
    if (open) setInstructions(storedInstructions ?? '')
  }, [open, storedInstructions])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(hint || undefined, instructions || undefined)
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
              AI Instructions
              <span className="text-gray-400 font-normal ml-1">(persisted on program)</span>
            </label>
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="e.g. Final semester must contain only project and internship. Major project 10 credits."
            />
            <p className="text-xs text-gray-400 mt-1">
              Saved and reused every generation. Changes here update the program record.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              One-time Prompt Hint
              <span className="text-gray-400 font-normal ml-1">(this run only)</span>
            </label>
            <Textarea
              rows={2}
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
  onSubmit: (comment?: string) => void
  isPending?: boolean
  hasAcadLink?: boolean
}

export function ApproveDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
  hasAcadLink,
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
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          {hasAcadLink === false && (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
              This program is not linked to an Academic Structure entry. You may still approve — this is advisory only.
            </p>
          )}
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Approved programs stay editable. Use Publish when ready to lock the program and make
            its elective courses available in Elective Offerings.
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
// Publish Dialog
// ---------------------------------------------------------------------------

interface PublishDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (comment?: string) => void
  isPending?: boolean
}

export function PublishDialog({
  open,
  onOpenChange,
  onSubmit,
  isPending,
}: PublishDialogProps) {
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
        <DialogHeader>
          <DialogTitle>Publish Program</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Publish Notes (optional)
            </label>
            <Textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
            Publishing permanently locks this program — no further edits or deletion. Its
            elective-tagged courses become available in Elective Offerings.
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
              {isPending ? 'Publishing…' : 'Publish'}
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
