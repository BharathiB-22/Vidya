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
import {
  DEFAULT_UNIT_COUNT,
  MAX_UNIT_HOURS,
  MIN_UNIT_HOURS,
  UNIT_COUNT_OPTIONS,
  type CourseInformation,
} from '@/types/syllabus'
import { COURSE_TYPE_DOCUMENT, COURSE_TYPE_LABEL, type CourseType } from '@/types/program'

// ---------------------------------------------------------------------------
// Generate Dialog
//
// The unit count is asked for HERE, before generation, and only for a theory
// syllabus. Five units is not a universal format — plenty of AICTE, VTU and
// autonomous regulations run to four — and a Board that wanted four used to have to
// generate five and delete one, which left it redistributing the hours by hand and
// with an AI that had paced the surviving four for a syllabus that no longer existed.
//
// A lab manual, an internship and a project handbook have no units at all, so they
// are not asked.
// ---------------------------------------------------------------------------

interface GenerateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: {
    instructions?: string
    unitCount?: number
    unitHours?: number[]
  }) => void
  isPending?: boolean
  /** Which document this is. Only THEORY is taught in units. */
  docType: CourseType
  /** What the syllabus currently carries — the starting selection. */
  unitCount?: number
  /** The Board's previous hour plan, if it made one. */
  unitHours?: number[]
  /** The course this syllabus is for, as the curriculum records it. Shown, never
   *  retyped: the Dean's structure is the source of truth for what this course IS. */
  info?: CourseInformation
}

export function GenerateSyllabusDialog({
  open, onOpenChange, onSubmit, isPending, docType,
  unitCount, unitHours, info,
}: GenerateDialogProps) {
  const contactHours = info?.contact_hours ?? 0

  const [hint, setHint] = useState('')
  const [units, setUnits] = useState<number>(unitCount ?? DEFAULT_UNIT_COUNT)
  const [hours, setHours] = useState<number[]>(
    () => seedHours(unitCount ?? DEFAULT_UNIT_COUNT, unitHours, contactHours),
  )

  const isTheory = docType === 'THEORY'
  const total = hours.reduce((sum, h) => sum + (h || 0), 0)

  // A unit taught for more than 15 hours is not a unit, it is two — and one taught
  // for fewer than 4 is a topic. Both are warnings, never blocks: an intensive
  // 18-hour unit is a decision a Board is entitled to make, and this is the place to
  // notice it rather than the printed regulation.
  const heavy = hours.some((h) => h > MAX_UNIT_HOURS)
  const light = hours.some((h) => h > 0 && h < MIN_UNIT_HOURS)

  /** Changing the unit count re-seeds the hours: a four-figure plan means nothing
   *  once the syllabus has five units, and the server refuses it anyway. */
  function chooseUnits(n: number) {
    setUnits(n)
    setHours(seedHours(n, undefined, contactHours))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      instructions: hint || undefined,
      unitCount: isTheory ? units : undefined,
      unitHours: isTheory && hours.every((h) => h > 0) ? hours : undefined,
    })
    setHint('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isTheory
              ? 'Generate Syllabus with AI'
              : `Generate ${COURSE_TYPE_DOCUMENT[docType]} with AI`}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">

          {/*
            The course, as the CURRICULUM records it — shown, not retyped.

            The Board is not asked for the course code, the credits or the contact
            hours: the Dean's approved structure already says what this course is, and
            a syllabus that kept its own copy of those facts would disagree with the
            curriculum the moment one of them was corrected. What the Board decides
            here is the shape of the SYLLABUS: its units, and their hours.
          */}
          {info && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
              {[
                ['Course', `${info.course_code} — ${info.course_name}`],
                ['Credits', `${info.credits}  (L-T-P ${info.ltp})`],
                ['Contact Hours', `${info.contact_hours}`],
                ['Semester', `${info.semester}`],
                ['Course Type', COURSE_TYPE_LABEL[info.course_type] ?? info.course_type],
                ['Regulation', info.regulation_year ? `${info.regulation_year}` : '—'],
              ].map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="text-xs font-medium text-gray-500">{label}</dt>
                  <dd className="truncate font-medium text-black">{value}</dd>
                </div>
              ))}
            </dl>
          )}

          {isTheory && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  How many units?
                </label>
                <div className="flex gap-2">
                  {UNIT_COUNT_OPTIONS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => chooseUnits(n)}
                      aria-pressed={units === n}
                      className={`flex-1 rounded-lg border px-4 py-2.5 text-sm font-semibold transition ${
                        units === n
                          ? 'border-blue-500 bg-blue-50 text-blue-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {n} Units
                      <span className="block text-xs font-normal text-gray-500">
                        Unit I – {n === 4 ? 'IV' : 'V'}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/*
                The hours, per unit, before a word is generated.

                They are a teaching decision — they come out of the timetable and the
                credit structure — and the AI has no way of knowing that Unit III is
                the heavy one this year. So the Board states them and each unit is
                WRITTEN TO its hours, rather than given hours it then has to
                redistribute by hand afterwards.
              */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Hours per unit
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  {hours.map((value, i) => (
                    <div key={i} className="w-[4.5rem]">
                      <span className="mb-0.5 block text-xs font-medium text-gray-500">
                        Unit {ROMAN[i]}
                      </span>
                      <Input
                        type="number"
                        min={1}
                        value={value || ''}
                        aria-label={`Hours for Unit ${ROMAN[i]}`}
                        onChange={(e) =>
                          setHours((prev) =>
                            prev.map((h, j) => (j === i ? Number(e.target.value) : h)),
                          )
                        }
                      />
                    </div>
                  ))}
                  <div className="ml-auto pb-1.5 text-right">
                    <span className="block text-xs text-gray-500">Total</span>
                    <span className="text-sm font-bold text-black">{total} Hours</span>
                  </div>
                </div>
                <div className="mt-1.5 space-y-0.5">
                  {contactHours > 0 && total !== contactHours && (
                    <p className="text-xs text-amber-700">
                      The curriculum teaches this course for {contactHours} hours. Your units
                      add up to {total}.
                    </p>
                  )}
                  {heavy && (
                    <p className="text-xs text-amber-700">
                      A unit taught for more than {MAX_UNIT_HOURS} hours is usually two units.
                    </p>
                  )}
                  {light && (
                    <p className="text-xs text-amber-700">
                      A unit is normally {MIN_UNIT_HOURS}–12 hours; below that it is a topic,
                      not a unit.
                    </p>
                  )}
                </div>
              </div>

              <p className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                The syllabus is written <span className="font-semibold">one unit at a time</span>,
                and every unit is checked before it is saved: a unit that comes back too thin is
                regenerated until it is a real one. You will never be handed a half-written unit
                to finish yourself.
              </p>
            </>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom Instructions (optional)
            </label>
            <Textarea
              rows={2}
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              placeholder="e.g. Follow NEP 2020, emphasise industry tools"
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

const ROMAN = ['I', 'II', 'III', 'IV', 'V']

/**
 * The hours to start from: the Board's last plan if it fits, otherwise the course's
 * contact hours split evenly, otherwise a plain default.
 *
 * The remainder goes on the FIRST unit rather than being scattered — 45 hours across
 * four units is 12/11/11/11, not 11.25 four times, and a Board that wants it
 * elsewhere moves it in one keystroke.
 */
function seedHours(units: number, previous: number[] | undefined, contactHours: number): number[] {
  if (previous?.length === units && previous.every((h) => h > 0)) return [...previous]

  if (contactHours > 0) {
    const base = Math.floor(contactHours / units)
    const rest = contactHours - base * units
    return Array.from({ length: units }, (_, i) => (i === 0 ? base + rest : base))
  }
  return Array<number>(units).fill(10)
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
// Fork Dialog
//
// The Reject, Request Revision and Lock dialogs used to live here. All three are
// gone: the Board writes the official syllabus and signs it off, so there is
// nobody to reject it to; and a syllabus is locked by CURRICULUM approval, never
// on its own.
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
// Delete Confirm
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
