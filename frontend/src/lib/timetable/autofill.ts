/**
 * Deterministic timetable auto-fill from published curriculum.
 *
 * This is NOT a scheduler. There is no optimisation, no preference solving and
 * no backtracking: given the same inputs it always produces the same grid, and a
 * human reads the rule in one sitting. It exists so the Dean never types a
 * subject name — the curriculum already knows which courses a semester teaches
 * and how many periods each needs.
 *
 * The rule, in full:
 *
 *   1. A course needs `hours_lecture + hours_tutorial + hours_practical` periods
 *      a week. Older AI-generated courses left L-T-P null, so those fall back to
 *      `credits`.
 *   2. Sessions are dealt one course at a time in rotation — every course takes
 *      its first session before any course takes its second — so no subject can
 *      monopolise the top of the week.
 *   3. A session always lands on the *first free period of the chosen day*, which
 *      keeps each day packed from the top with no gaps in the middle. The only
 *      real choice is therefore which day, and `pickDay` makes it: never a
 *      second session of a course on a day while another day still has none;
 *      then keep the course's days spread apart (Mon-Wed-Fri, not Mon-Tue-Wed);
 *      then the lightest day, so the week fills evenly.
 *   4. Cells that are not free are never touched: existing entries, locked
 *      cells, break rows, non-working days, and Saturday afternoons under a
 *      half-day template.
 *
 * Anything that will not fit is reported rather than forced. The caller writes
 * the result through the ordinary `POST /slots` endpoint, so every placement is
 * still checked by the server's existing clash validation — this module makes no
 * claim about faculty or room availability in other sections.
 */

/** The subset of `CourseWithAssignments` this module needs. */
export interface AutofillCourse {
  course_id: string
  code: string
  title: string
  credits: number
  hours_lecture: number | null
  hours_tutorial: number | null
  hours_practical: number | null
  is_elective: boolean
  /** Faculty is auto-filled only when a course has exactly one assignment. */
  assignments: { faculty_user_id: string | null }[]
}

/** The subset of `TimetablePeriod` this module needs. */
export interface AutofillPeriod {
  period_type: 'PERIOD' | 'BREAK'
  period_number: number | null
  sequence_number: number
  skip_on_half_day: boolean
}

export interface AutofillCell {
  day_of_week: number
  period_number: number
}

export interface PlannedSlot extends AutofillCell {
  course_id: string
  faculty_user_id?: string
  is_elective: boolean
}

export interface Unplaced {
  course: AutofillCourse
  /** How many periods could not be placed anywhere. */
  missing: number
}

export interface AutofillPlan {
  slots: PlannedSlot[]
  unplaced: Unplaced[]
  /** Free PERIOD cells remaining after the plan is applied. */
  freeCells: number
  /** Teachable PERIOD cells in the whole week, filled or not. */
  totalCells: number
}

export interface AutofillInput {
  courses: AutofillCourse[]
  /** From the linked template. Omit to fall back to Period 1..8 on all days. */
  periods?: AutofillPeriod[]
  workingDays?: number[]
  saturdayMode?: 'FULL' | 'HALF' | 'HOLIDAY' | null
  /** Cells that already hold an entry, or whose entry the Dean has locked. */
  occupied: AutofillCell[]
}

const DEFAULT_PERIOD_NUMBERS = [1, 2, 3, 4, 5, 6, 7, 8]
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
const SATURDAY = 5

/** Two sessions of one subject closer together than this many days is the thing
 *  the spreading rule is trying to avoid; beyond it, the gap no longer matters. */
const COMFORTABLE_DAY_GAP = 2

/**
 * Weekly periods a course needs.
 *
 * L-T-P are contact hours per week, so their sum is the period count directly.
 * When all three are null the course predates the L-T-P fields and `credits` is
 * the only signal available. A course must occupy at least one period, or it
 * would silently vanish from the week.
 */
export function periodsRequired(course: AutofillCourse): number {
  const { hours_lecture: l, hours_tutorial: t, hours_practical: p } = course
  const hasLTP = l !== null || t !== null || p !== null
  const total = hasLTP ? (l ?? 0) + (t ?? 0) + (p ?? 0) : course.credits
  return Math.max(1, total)
}

/** The faculty to pre-fill, or undefined. Mirrors the add-slot dialog: exactly
 *  one assignment auto-fills, zero or many leave the Dean to choose. */
export function autoFaculty(course: AutofillCourse): string | undefined {
  if (course.assignments.length !== 1) return undefined
  return course.assignments[0].faculty_user_id ?? undefined
}

function cellKey(day: number, period: number): string {
  return `${day}:${period}`
}

/**
 * Teachable PERIOD numbers for one day, in template order.
 * Break rows are absent; so are Saturday afternoons on a half-day template.
 */
function teachablePeriods(
  day: number,
  periods: AutofillPeriod[] | undefined,
  saturdayMode: AutofillInput['saturdayMode'],
): number[] {
  if (!periods || periods.length === 0) return DEFAULT_PERIOD_NUMBERS
  return [...periods]
    .sort((a, b) => a.sequence_number - b.sequence_number)
    .filter((p) => p.period_type === 'PERIOD' && p.period_number !== null)
    .filter((p) => !(saturdayMode === 'HALF' && day === SATURDAY && p.skip_on_half_day))
    .map((p) => p.period_number as number)
}

/** Running placement state, shared by the pickers below. */
interface Board {
  days: number[]
  periodsByDay: Map<number, number[]>
  taken: Set<string>
  /** Total entries on a day, existing ones included — the day's "load". */
  loadByDay: Map<number, number>
  /** Days this course already teaches on, per course. */
  daysByCourse: Map<string, number[]>
}

/** The cell a session would take on this day: the first one still free, so a day
 *  always fills from the top and never grows a hole in the middle. */
function firstFreePeriod(board: Board, day: number): number | undefined {
  return (board.periodsByDay.get(day) ?? []).find((p) => !board.taken.has(cellKey(day, p)))
}

/**
 * How badly a day suits the next session of `courseId`. Lower is better; the
 * bands are ordered so a lower-priority term can never outvote a higher one.
 *
 *   same-day repeat   × 1000  — one session per day everywhere before any day doubles up
 *   crowding          ×  100  — a gap of 1 day is worse than a gap of 2; beyond that, free
 *   day load          ×   10  — level the week out rather than front-loading Monday
 *   day index         ×    1  — deterministic tie-break, and it reads left-to-right
 */
function dayCost(board: Board, courseId: string, day: number): number {
  const used = board.daysByCourse.get(courseId) ?? []
  const sameDay = used.filter((d) => d === day).length

  let crowding = 0
  for (const d of used) {
    const gap = Math.abs(d - day)
    if (gap > 0 && gap < COMFORTABLE_DAY_GAP) crowding += COMFORTABLE_DAY_GAP - gap
  }

  return (
    sameDay * 1000 +
    crowding * 100 +
    (board.loadByDay.get(day) ?? 0) * 10 +
    board.days.indexOf(day)
  )
}

/** The best day with a free period left, or undefined when the week is full. */
function pickDay(board: Board, courseId: string): number | undefined {
  let best: number | undefined
  let bestCost = Number.POSITIVE_INFINITY
  for (const day of board.days) {
    if (firstFreePeriod(board, day) === undefined) continue
    const cost = dayCost(board, courseId, day)
    if (cost < bestCost) {
      bestCost = cost
      best = day
    }
  }
  return best
}

/**
 * Plan a week. Pure: reads nothing, writes nothing, returns what it would do.
 *
 * Courses are dealt round-robin — heaviest first within each round — and each
 * session goes to the day that costs least by the rule above. The result is a
 * week where a 4-period subject reads Mon-Wed-Fri-Tue rather than four periods
 * stacked on Monday morning, while every day stays packed from Period 1 down.
 */
export function planTimetable(input: AutofillInput): AutofillPlan {
  const { courses, periods, saturdayMode, occupied } = input
  const days = input.workingDays && input.workingDays.length > 0 ? [...input.workingDays].sort((a, b) => a - b) : ALL_DAYS

  const board: Board = {
    days,
    periodsByDay: new Map(days.map((d) => [d, teachablePeriods(d, periods, saturdayMode)])),
    taken: new Set(occupied.map((c) => cellKey(c.day_of_week, c.period_number))),
    loadByDay: new Map(days.map((d) => [d, occupied.filter((c) => c.day_of_week === d).length])),
    daysByCourse: new Map(),
  }

  // Heaviest first: the subject with the least room to manoeuvre gets first pick
  // in every round, while the grid is still open.
  const ordered = [...courses].sort((a, b) => {
    const diff = periodsRequired(b) - periodsRequired(a)
    return diff !== 0 ? diff : a.code.localeCompare(b.code)
  })

  const remaining = new Map(ordered.map((c) => [c.course_id, periodsRequired(c)]))
  const slots: PlannedSlot[] = []

  // One round = one session for every course that still needs one. Rounds stop
  // as soon as a whole round places nothing, which means the week is full.
  let progressed = true
  while (progressed) {
    progressed = false
    for (const course of ordered) {
      if ((remaining.get(course.course_id) ?? 0) <= 0) continue

      const day = pickDay(board, course.course_id)
      if (day === undefined) continue           // no free cell anywhere for this course
      const period = firstFreePeriod(board, day) as number

      board.taken.add(cellKey(day, period))
      board.loadByDay.set(day, (board.loadByDay.get(day) ?? 0) + 1)
      board.daysByCourse.set(course.course_id, [...(board.daysByCourse.get(course.course_id) ?? []), day])
      remaining.set(course.course_id, (remaining.get(course.course_id) as number) - 1)

      slots.push({
        day_of_week: day,
        period_number: period,
        course_id: course.course_id,
        faculty_user_id: autoFaculty(course),
        is_elective: course.is_elective,
      })
      progressed = true
    }
  }

  const unplaced: Unplaced[] = ordered
    .filter((c) => (remaining.get(c.course_id) ?? 0) > 0)
    .map((c) => ({ course: c, missing: remaining.get(c.course_id) as number }))

  // Stable output: a plan is easier to read, diff and test day by day.
  slots.sort((a, b) => a.day_of_week - b.day_of_week || a.period_number - b.period_number)

  // Count the teachable cells directly rather than subtracting `taken.size` — an
  // existing entry may sit on a cell this template no longer teaches (a slot left
  // behind on a day the template later dropped), and must not be counted.
  let freeCells = 0
  let totalCells = 0
  for (const day of days) {
    for (const period of board.periodsByDay.get(day) ?? []) {
      totalCells++
      if (!board.taken.has(cellKey(day, period))) freeCells++
    }
  }

  return { slots, unplaced, freeCells, totalCells }
}
