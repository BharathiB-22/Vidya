import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { usePrepareSyllabus } from '@/hooks/syllabuses'
import { useProgramCourses } from '@/hooks/programs'
import {
  DEFAULT_UNIT_COUNT, MAX_UNIT_HOURS, MIN_UNIT_HOURS, UNIT_COUNT_OPTIONS,
} from '@/types/syllabus'
import { WEEKS_PER_SEMESTER } from '@/types/program'
import type { ReadinessItem } from '@/types/governance'

/**
 * How ONE subject's syllabus begins — and the Board decides which way, one subject at a
 * time.
 *
 * This is the whole of the refactor. There used to be a button that generated forty
 * syllabi: three hundred model calls on one click, whether anybody wanted them or not.
 * A Board of Studies does not decide to draft forty syllabi. It decides whether THIS
 * subject wants an AI draft — or is better written by the professor who has taught it
 * for fifteen years, and needs no machine at all.
 *
 * Two doors, one room. Both create the same empty syllabus and open the same editor.
 * The only difference is whether a first draft is written for the Board or by it, and
 * nothing downstream — not the editor, not the validation, not the readiness, not the
 * approval — can tell which door a syllabus came through.
 *
 * The AI door asks for the academic structure first, because the generator will not
 * draft a theory syllabus without it: how a subject is divided, and how long each part
 * is taught, is the Board's decision and never the model's. The manual door asks for
 * nothing — the Board writes the units, and the structure follows what it writes.
 */

const ROMAN = ['I', 'II', 'III', 'IV', 'V']

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  subject: ReadinessItem | null
  programId: string
}

export function PrepareSyllabusDialog({ open, onOpenChange, subject, programId }: Props) {
  const navigate = useNavigate()
  const prepare = usePrepareSyllabus()

  // The course's contact hours come from its L-T-P — the curriculum's own record of how
  // long this subject is taught. Used only to SEED the hour boxes; the Board reads them,
  // edits them, and saves them. A suggestion a human accepts is not a decision the
  // system made.
  const { data: courses = [] } = useProgramCourses(programId)
  const course = courses.find((c) => c.id === subject?.course_id)
  const contactHours = course
    ? ((course.hours_lecture ?? 0) + (course.hours_tutorial ?? 0) +
       (course.hours_practical ?? 0)) * WEEKS_PER_SEMESTER
    : 0

  const isTheory = subject?.course_type === 'THEORY'

  const [units, setUnits] = useState<number>(DEFAULT_UNIT_COUNT)
  const [hours, setHours] = useState<number[]>(() => seed(DEFAULT_UNIT_COUNT, 0))
  const [instructions, setInstructions] = useState('')

  useEffect(() => {
    setHours(seed(units, contactHours))
  }, [units, contactHours, subject?.course_id])

  if (!subject) return null

  const total = hours.reduce((sum, h) => sum + (h || 0), 0)
  const sane = hours.every((h) => h >= 1)

  async function start() {
    const syllabus = await prepare.mutateAsync({
      courseId: subject!.course_id,
      mode: 'AI',
      // The Board's academic structure, saved before a model is asked for anything.
      unitCount: isTheory ? units : undefined,
      unitHours: isTheory ? hours : undefined,
      instructions: instructions || undefined,
    })
    onOpenChange(false)
    // The same editor the manual door opens. There is only one.
    navigate(`/syllabuses/${syllabus.id}`)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-1.5 font-bold text-black">
            <Sparkles className="h-4 w-4 text-blue-600" />
            Generate AI Draft — {subject.course_title}
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-gray-600">
          {subject.course_code} · Semester {subject.semester}
          {contactHours > 0 && ` · ${contactHours} contact hours`}
        </p>

        <div className="space-y-4">
          {/* ── The AI door ────────────────────────────────────────────── */}
          <section className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
            <p className="text-xs text-gray-600">
              The AI writes a first draft against the structure you set below — unit by unit,
              then the objectives, outcomes and reading. You review and edit it like any other
              syllabus.
            </p>

            {isTheory && (
              <>
                <div className="mt-3 flex gap-2">
                  {UNIT_COUNT_OPTIONS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setUnits(n)}
                      aria-pressed={units === n}
                      className={`flex-1 rounded-md border px-3 py-1.5 text-xs font-semibold transition ${
                        units === n
                          ? 'border-blue-500 bg-white text-blue-700'
                          : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {n} Units
                    </button>
                  ))}
                </div>

                <div className="mt-2 flex flex-wrap items-end gap-2">
                  {hours.map((value, i) => (
                    <div key={i} className="w-14">
                      <span className="mb-0.5 block text-[11px] font-medium text-gray-500">
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
                        className="h-8 bg-white"
                      />
                    </div>
                  ))}
                  <span className="ml-auto pb-1 text-right text-xs">
                    <span className="block text-gray-500">Total</span>
                    <span
                      className={`font-bold ${
                        contactHours && total !== contactHours ? 'text-amber-700' : 'text-black'
                      }`}
                    >
                      {total} Hours
                    </span>
                  </span>
                </div>

                {/* Advisory only. The Board may have a reason; this is where a mistake is
                    cheapest to notice. */}
                {contactHours > 0 && total !== contactHours && (
                  <p className="mt-1 text-xs text-amber-700">
                    This course is taught for {contactHours} hours; your units add up to {total}.
                  </p>
                )}
                {hours.some((h) => h > MAX_UNIT_HOURS) && (
                  <p className="mt-1 text-xs text-amber-700">
                    A unit taught for more than {MAX_UNIT_HOURS} hours is usually two units.
                  </p>
                )}
                {hours.some((h) => h > 0 && h < MIN_UNIT_HOURS) && (
                  <p className="mt-1 text-xs text-amber-700">
                    A unit is normally at least {MIN_UNIT_HOURS} hours.
                  </p>
                )}
              </>
            )}

            <Textarea
              rows={2}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Optional guidance — e.g. follow NEP 2020, emphasise industry tools"
              className="mt-2 bg-white text-sm"
            />

            <Button
              className="mt-2 w-full"
              disabled={prepare.isPending || (isTheory && !sane)}
              onClick={() => start()}
            >
              <Sparkles className="mr-1 h-4 w-4" />
              {prepare.isPending ? 'Starting…' : 'Generate AI Draft'}
            </Button>
          </section>

        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** What the hour boxes show before the Board touches them. A suggestion, not a decision. */
function seed(units: number, contactHours: number): number[] {
  if (contactHours <= 0) return Array<number>(units).fill(10)
  const base = Math.floor(contactHours / units)
  const rest = contactHours - base * units
  return Array.from({ length: units }, (_, i) => (i === 0 ? base + rest : base))
}
