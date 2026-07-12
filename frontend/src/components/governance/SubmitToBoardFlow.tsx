import { useState } from 'react'
import {
  AlertTriangle, ArrowRight, CheckCircle2, Loader2, Send, TriangleAlert, XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useSubmissionChecklist } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'
import type { SubmissionCheckItem, SubmissionSection } from '@/types/governance'

/**
 * Submitting a curriculum to the Board is the single most irreversible thing a
 * Dean does in this system. From that click they can never edit it again — the
 * Board takes it, may rewrite it, and hands back something they can only publish.
 *
 * So this is deliberately not one button and one toast. It is:
 *
 *   click Submit
 *      │
 *      ├── something is missing  → a CHECKLIST of what, each line pointing at the
 *      │                           section that fixes it, with a button that takes
 *      │                           you there. Nothing is submitted.
 *      │
 *      └── everything is ready   → a CONFIRMATION spelling out exactly what the
 *                                  Dean is giving up, and only then the handover.
 *
 * The old behaviour — attempt the submit, catch a 422, flash a one-line toast —
 * told the Dean they had failed without telling them what to finish. That is the
 * wrong shape for an act you cannot take back.
 *
 * The server still refuses a bad submission regardless. This is a better door, not
 * the lock.
 */
export function SubmitToBoardFlow({
  open,
  onOpenChange,
  programId,
  onSubmit,
  onNavigate,
  isPending,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  programId: string
  onSubmit: (note?: string) => void
  /** Take the Dean to the section that fixes the first failing check. */
  onNavigate: (section: SubmissionSection) => void
  isPending?: boolean
}) {
  const { data: checklist, isLoading } = useSubmissionChecklist(programId, open)

  if (isLoading || !checklist) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md">
          <div className="flex items-center gap-2 py-6 text-sm text-gray-600">
            <Loader2 className="h-4 w-4 animate-spin" />
            Checking the curriculum…
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return checklist.can_submit ? (
    <ConfirmSubmit
      open={open}
      onOpenChange={onOpenChange}
      items={checklist.items}
      onSubmit={onSubmit}
      isPending={isPending}
    />
  ) : (
    <BlockedByChecklist
      open={open}
      onOpenChange={onOpenChange}
      items={checklist.items}
      firstFailingSection={checklist.first_failing_section}
      onNavigate={onNavigate}
    />
  )
}

// ---------------------------------------------------------------------------
// Not ready — here is what is missing, and here is where to fix it
// ---------------------------------------------------------------------------

function BlockedByChecklist({
  open, onOpenChange, items, firstFailingSection, onNavigate,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: SubmissionCheckItem[]
  firstFailingSection: SubmissionSection | null
  onNavigate: (section: SubmissionSection) => void
}) {
  const { bodyLabel } = useGovernance()
  const blockedCount = items.filter((i) => i.blocking && !i.passed).length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-bold text-black">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-amber-100">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            </span>
            Cannot Submit to the {bodyLabel} Yet
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-gray-600">
          {blockedCount === 1
            ? 'One thing still needs finishing'
            : `${blockedCount} things still need finishing`}{' '}
          before this curriculum can be handed over.
        </p>

        <ul className="max-h-80 space-y-1.5 overflow-y-auto">
          {items.map((item) => (
            <ChecklistRow key={item.key} item={item} />
          ))}
        </ul>

        <DialogFooter className="sm:justify-between">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {firstFailingSection && (
            <Button
              onClick={() => {
                onOpenChange(false)
                onNavigate(firstFailingSection)
              }}
            >
              Go to Missing Information
              <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ChecklistRow({ item }: { item: SubmissionCheckItem }) {
  const failedHard = item.blocking && !item.passed
  const isWarning = !item.blocking && !item.passed

  const { Icon, iconClass, rowClass } = item.passed
    ? { Icon: CheckCircle2, iconClass: 'text-emerald-600', rowClass: 'border-transparent' }
    : failedHard
    ? { Icon: XCircle, iconClass: 'text-red-600', rowClass: 'border-red-200 bg-red-50' }
    : { Icon: TriangleAlert, iconClass: 'text-amber-600', rowClass: 'border-amber-200 bg-amber-50' }

  return (
    <li className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${rowClass}`}>
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${iconClass}`} />
      <div className="min-w-0">
        <p
          className={`text-sm ${
            item.passed ? 'text-gray-600' : 'font-semibold text-black'
          }`}
        >
          {item.label}
          {isWarning && (
            <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
              Warning only
            </span>
          )}
        </p>
        {!item.passed && item.detail && (
          <p className="mt-0.5 text-xs text-gray-600">{item.detail}</p>
        )}
      </div>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Ready — but say plainly what is being given up
// ---------------------------------------------------------------------------

function ConfirmSubmit({
  open, onOpenChange, items, onSubmit, isPending,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: SubmissionCheckItem[]
  onSubmit: (note?: string) => void
  isPending?: boolean
}) {
  const { bodyLabel } = useGovernance()
  const [note, setNote] = useState('')
  const warnings = items.filter((i) => !i.blocking && !i.passed)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-bold text-black">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-emerald-100">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            </span>
            Submit Curriculum to the {bodyLabel}?
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-gray-700">Once submitted:</p>
        <ul className="space-y-1.5 rounded-lg border border-amber-200 bg-amber-50 p-3">
          {[
            'You can no longer edit this curriculum — subjects, credits, semesters and elective baskets all become read-only for you.',
            `Ownership moves to the ${bodyLabel}.`,
            `The ${bodyLabel} may improve the curriculum and will generate the official syllabus for every subject.`,
            `You will receive the finalized curriculum after ${bodyLabel} approval, and can then publish it.`,
          ].map((line) => (
            <li key={line} className="flex items-start gap-2 text-sm text-amber-900">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-600" />
              {line}
            </li>
          ))}
        </ul>

        <p className="text-xs text-gray-500">
          There is no way to take this back. The curriculum does not return to you for corrections —
          the {bodyLabel} will make any changes it needs itself, and you will be shown exactly what
          changed before you publish.
        </p>

        {warnings.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-white p-3">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-amber-800">
              <TriangleAlert className="h-3.5 w-3.5" />
              {warnings.length} warning{warnings.length === 1 ? '' : 's'} — these will not stop the
              submission, but the {bodyLabel} will see them
            </p>
            <ul className="space-y-0.5">
              {warnings.map((w) => (
                <li key={w.key} className="text-xs text-gray-600">
                  {w.label}
                  {w.detail && <span className="text-gray-500"> — {w.detail}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <label className="mb-1 block text-sm font-semibold text-black">
            Note for the {bodyLabel} <span className="font-normal text-gray-400">(optional)</span>
          </label>
          <Textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Anything the reviewers should know…"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={isPending} onClick={() => onSubmit(note.trim() || undefined)}>
            {isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-1 h-4 w-4" />
            )}
            {isPending ? 'Submitting…' : `Submit to the ${bodyLabel}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
