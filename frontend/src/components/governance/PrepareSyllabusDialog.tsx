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
import {
  DEFAULT_HOURS_PER_WEEK, DEFAULT_TEACHING_HOURS, DEFAULT_UNIT_COUNT,
  MAX_HOURS_PER_WEEK, MAX_TEACHING_HOURS, MAX_UNIT_HOURS, MIN_HOURS_PER_WEEK,
  MIN_TEACHING_HOURS, MIN_UNIT_HOURS, UNIT_COUNT_OPTIONS,
} from '@/types/syllabus'
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
 *
 * NOTHING IN THIS FORM IS COMPUTED AND LEFT UNREAD. Every figure it shows — the total
 * hours, the weeks, the hours of each unit — is a SUGGESTION the Board looks at and may
 * overrule. (L + T + P) x 15 weeks is arithmetic, not knowledge: for a 4-0-0 course it
 * says 60 hours whatever the Board knows about the term it is actually planning for,
 * and a term shortened by an election is 45. The AI is then told the figure the human
 * left in the box, never the one the multiplication produced.
 *
 * THEORY ONLY, and deliberately. The unit boxes below make sense for a taught subject
 * and for nothing else — a lab has experiments, an internship has weeks at a company,
 * a project has milestones and reviews. Each of those is getting its own dialog; until
 * it does, they go through this one with the structure fields hidden, and their
 * generators (which have never read unit_count or unit_hours) are unaffected.
 */

const ROMAN = ['I', 'II', 'III', 'IV', 'V']

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  subject: ReadinessItem | null
}

export function PrepareSyllabusDialog({ open, onOpenChange, subject }: Props) {
  const navigate = useNavigate()
  const prepare = usePrepareSyllabus()

  const isTheory = subject?.course_type === 'THEORY'

  const [units, setUnits] = useState<number>(DEFAULT_UNIT_COUNT)
  const [totalHours, setTotalHours] = useState<number>(DEFAULT_TEACHING_HOURS)
  const [perWeek, setPerWeek] = useState<number>(DEFAULT_HOURS_PER_WEEK)
  const [hours, setHours] = useState<number[]>(
    () => seed(DEFAULT_UNIT_COUNT, DEFAULT_TEACHING_HOURS),
  )
  const [instructions, setInstructions] = useState('')

  // A different subject is a different form. Back to the opening figures — which are a
  // convenience and nothing more: 60 hours at 4 a week is the common case, not a rule,
  // and 40, 45, 48 and 52 are all ordinary answers the Board types straight over it.
  useEffect(() => {
    setTotalHours(DEFAULT_TEACHING_HOURS)
    setPerWeek(DEFAULT_HOURS_PER_WEEK)
  }, [subject?.course_id])

  // The units are apportioned out of whatever total is in the box. Re-spread whenever
  // the total or the number of units changes, because an allocation of 60 across five
  // is not an allocation of 52 across four — leaving the old figures would show the
  // Board an hour plan for a course it has just said it is not teaching.
  useEffect(() => {
    setHours(seed(units, totalHours))
  }, [units, totalHours, subject?.course_id])

  if (!subject) return null

  const total = hours.reduce((sum, h) => sum + (h || 0), 0)

  // THE ONE RULE, and the only thing that blocks the button: the units are the course,
  // so they must add up to it. The server enforces the same rule at generation and
  // again at approval — this is only the earliest, cheapest place to see it.
  const balanced = total === totalHours
  const sane =
    hours.every((h) => h >= 1) &&
    totalHours >= MIN_TEACHING_HOURS &&
    perWeek >= MIN_HOURS_PER_WEEK &&
    balanced

  async function start() {
    const syllabus = await prepare.mutateAsync({
      courseId: subject!.course_id,
      mode: 'AI',
      // The Board's academic structure, saved before a model is asked for anything.
      unitCount: isTheory ? units : undefined,
      unitHours: isTheory ? hours : undefined,
      // And the header's two figures. The AI paces the whole syllabus against the
      // total — nothing assumes 60, and nothing derives it from the L-T-P.
      teachingHours: isTheory ? totalHours : undefined,
      hoursPerWeek: isTheory ? perWeek : undefined,
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
                {/* The two figures a real syllabus prints at the top of the page:
                    "Total Teaching Hours: 52   No. of Hours / Week: 04". They open at
                    60 and 4 because that is the common case and an empty box is a
                    chore — nothing derives them, nothing enforces 60, and the Board
                    types straight over them. */}
                <div className="mt-3 flex items-end gap-2">
                  <div className="flex-1">
                    <label
                      htmlFor="teaching-hours"
                      className="mb-0.5 block text-[11px] font-medium text-gray-500"
                    >
                      Total Teaching Hours
                    </label>
                    <Input
                      id="teaching-hours"
                      type="number"
                      min={MIN_TEACHING_HOURS}
                      max={MAX_TEACHING_HOURS}
                      value={totalHours || ''}
                      onChange={(e) => setTotalHours(Number(e.target.value) || 0)}
                      className="h-8 bg-white"
                    />
                  </div>
                  <div className="flex-1">
                    <label
                      htmlFor="hours-per-week"
                      className="mb-0.5 block text-[11px] font-medium text-gray-500"
                    >
                      No. of Hours / Week
                    </label>
                    <Input
                      id="hours-per-week"
                      type="number"
                      min={MIN_HOURS_PER_WEEK}
                      max={MAX_HOURS_PER_WEEK}
                      value={perWeek || ''}
                      onChange={(e) => setPerWeek(Number(e.target.value) || 0)}
                      className="h-8 bg-white"
                    />
                  </div>
                </div>

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
                      className={`font-bold ${balanced ? 'text-black' : 'text-amber-700'}`}
                    >
                      {total} Hours
                    </span>
                  </span>
                </div>

                {/* The units are the course: they must add up to it. This is the only
                    rule the form enforces, and the button below stays disabled until it
                    holds — the server refuses to generate against units that do not add
                    up, so failing here, on the form, is the cheap way to find out. */}
                {!balanced && (
                  <p className="mt-1 text-xs text-amber-700">
                    This course is taught for {totalHours} hours; your units add up to{' '}
                    {total}. Adjust either until they agree.
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

/** What the hour boxes show before the Board touches them — the total it stated, spread
 *  across the units. A suggestion, not a decision. */
function seed(units: number, totalHours: number): number[] {
  if (totalHours <= 0) return Array<number>(units).fill(10)
  const base = Math.floor(totalHours / units)
  const rest = totalHours - base * units
  return Array.from({ length: units }, (_, i) => (i === 0 ? base + rest : base))
}
