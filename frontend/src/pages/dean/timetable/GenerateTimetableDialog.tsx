import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { assignmentsApi } from '@/lib/api/assignments'
import { periodsRequired, planTimetable, type AutofillCourse, type AutofillPlan } from '@/lib/timetable/autofill'
import type { Timetable } from '@/types/timetable'

/** L-T-P as the Dean writes it on a curriculum sheet. */
function ltp(c: { hours_lecture: number | null; hours_tutorial: number | null; hours_practical: number | null }): string | null {
  const has = c.hours_lecture !== null || c.hours_tutorial !== null || c.hours_practical !== null
  if (!has) return null
  return `${c.hours_lecture ?? 0}–${c.hours_tutorial ?? 0}–${c.hours_practical ?? 0}`
}

/**
 * Seeds the whole week from the published curriculum, so the Dean never types a
 * subject name.
 *
 * The plan is computed and shown before anything is written — the numbers on
 * screen are the numbers that will be applied. Placement is deterministic and
 * unoptimised (see `lib/timetable/autofill.ts`); it is a starting point the Dean
 * then rearranges, not a schedule anyone should trust blindly.
 *
 * Existing entries and locked cells are never touched, so this is safe to run on
 * a half-built draft.
 */
export function GenerateTimetableDialog({
  open,
  onOpenChange,
  timetable,
  onGenerate,
  isGenerating,
  progress,
  error,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  timetable: Timetable
  onGenerate: (plan: AutofillPlan) => void
  isGenerating: boolean
  /** `[written, total]` while the plan is being applied. */
  progress: [number, number] | null
  error: string | null
}) {
  const [applied, setApplied] = useState(false)

  const coursesQ = useQuery({
    queryKey: ['courses-for-slot', timetable.semester_id, timetable.section_id],
    queryFn: () => assignmentsApi.listCoursesForSlot(timetable.semester_id, timetable.section_id),
    enabled: open,
  })

  const courses: AutofillCourse[] = useMemo(
    () => (coursesQ.data ?? []).map((c) => ({
      course_id: c.course_id,
      code: c.code,
      title: c.title,
      credits: c.credits,
      hours_lecture: c.hours_lecture,
      hours_tutorial: c.hours_tutorial,
      hours_practical: c.hours_practical,
      is_elective: c.is_elective,
      assignments: c.assignments.map((a) => ({ faculty_user_id: a.faculty_user_id })),
    })),
    [coursesQ.data],
  )

  // Every existing entry is occupied ground, locked or not: Generate only ever
  // fills gaps, so a lock adds nothing here. Locks matter for move and delete.
  const plan: AutofillPlan | null = useMemo(() => {
    if (courses.length === 0) return null
    return planTimetable({
      courses,
      periods: timetable.template?.periods,
      workingDays: timetable.template?.working_days,
      saturdayMode: timetable.template?.saturday_mode,
      occupied: timetable.slots.map((s) => ({
        day_of_week: s.day_of_week,
        period_number: s.period_number,
      })),
    })
  }, [courses, timetable.template, timetable.slots])

  const required = courses.reduce((sum, c) => sum + periodsRequired(c), 0)
  const nothingToPlace = plan !== null && plan.slots.length === 0

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!isGenerating) { onOpenChange(v); setApplied(false) } }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-gray-600" />
            Generate from Published Curriculum
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          <p className="text-sm leading-relaxed text-gray-500">
            Every published subject for this semester, spread across the week using its weekly
            L–T–P hours. Existing entries and locked cells are left untouched — this is a
            starting point you can move, swap and edit afterwards.
          </p>

          {coursesQ.isLoading ? (
            <div className="h-40 rounded-xl bg-gray-50 animate-pulse" />
          ) : courses.length === 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-800">
              No published subjects for this semester. Academic Ownership only counts published
              curriculum — publish the programme, and its elective papers, first.
            </div>
          ) : (
            <>
              <section className="space-y-2.5">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                  Published Subjects
                </h3>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                  {courses.map((c) => (
                    <CourseCard key={c.course_id} course={c} />
                  ))}
                </div>
              </section>

              {plan && (
                <section className="grid grid-cols-3 gap-3">
                  <Stat label="Weekly periods required" value={required} />
                  <Stat label="Available periods" value={plan.totalCells} />
                  <Stat
                    label="Free after generating"
                    value={plan.freeCells}
                    hint={plan.freeCells === 0 ? 'The week is exactly full' : undefined}
                  />
                </section>
              )}

              {plan && plan.unplaced.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-800">
                  <p className="font-semibold">The week is too small for everything.</p>
                  <ul className="mt-1.5 space-y-0.5">
                    {plan.unplaced.map((u) => (
                      <li key={u.course.course_id}>
                        <span className="font-semibold">{u.course.code}</span> — {u.missing} period
                        {u.missing === 1 ? '' : 's'} will not fit
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1.5">Add periods to the template, or place these by hand afterwards.</p>
                </div>
              )}

              {nothingToPlace && (
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-600">
                  Every teachable cell is already filled or locked. Nothing to generate.
                </div>
              )}
            </>
          )}

          {progress && (
            <p className="flex items-center gap-2 text-xs font-medium text-gray-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Placing {progress[0]} of {progress[1]}…
            </p>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
          {applied && !isGenerating && !error && (
            <p className="text-xs font-medium text-emerald-700">Done. Close this dialog to review the week.</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" disabled={isGenerating} onClick={() => onOpenChange(false)}>
            {applied ? 'Close' : 'Cancel'}
          </Button>
          <Button
            disabled={!plan || nothingToPlace || isGenerating}
            onClick={() => { if (plan) { setApplied(true); onGenerate(plan) } }}
          >
            {isGenerating ? 'Generating…' : `Generate ${plan?.slots.length ?? 0} periods`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** One published subject and what it will cost the week. */
function CourseCard({ course }: { course: AutofillCourse }) {
  const hours = ltp(course)
  return (
    <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-bold text-gray-900">{course.code}</p>
          {course.is_elective && (
            <span className="rounded bg-violet-50 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-violet-600">
              Combined
            </span>
          )}
        </div>
        <p className="truncate text-xs font-medium text-gray-700">{course.title}</p>
      </div>

      <div className="shrink-0 text-right">
        <p className="text-[11px] font-medium text-gray-500 tabular-nums">
          {course.credits} credit{course.credits === 1 ? '' : 's'}
        </p>
        <p className="text-[11px] text-gray-600 tabular-nums">
          {hours ? `L–T–P ${hours}` : 'L–T–P not set — using credits'}
        </p>
      </div>

      <div className="w-16 shrink-0 text-right">
        <p className="text-base font-bold leading-none text-gray-900 tabular-nums">
          {periodsRequired(course)}
        </p>
        <p className="mt-1 text-[10px] uppercase tracking-wide text-gray-600">periods</p>
      </div>
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50/70 px-4 py-3">
      <p className="text-2xl font-bold leading-none text-gray-900 tabular-nums">{value}</p>
      <p className="mt-1.5 text-[11px] font-medium leading-snug text-gray-500">{label}</p>
      {hint && <p className="mt-0.5 text-[10px] text-gray-600">{hint}</p>}
    </div>
  )
}
