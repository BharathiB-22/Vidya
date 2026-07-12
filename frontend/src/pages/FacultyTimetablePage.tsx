import { useQuery } from '@tanstack/react-query'
import { CalendarClock, Clock, Coffee, ArrowRight } from 'lucide-react'
import { getMyFacultyTimetable } from '@/lib/api/timetable'
import { DAYS_OF_WEEK, formatClockTime, type FacultyTimetableSlot } from '@/types/timetable'

/** Our day indexing is Mon=0..Sun=6; JS Date.getDay() is Sun=0..Sat=6. */
function todayIndex(): number {
  return (new Date().getDay() + 6) % 7
}

/** "HH:MM[:SS]" -> minutes since midnight, or null. */
function toMinutes(t: string | null): number | null {
  if (!t) return null
  const [h, m] = t.split(':')
  return Number(h) * 60 + Number(m)
}

function nowMinutes(): number {
  const d = new Date()
  return d.getHours() * 60 + d.getMinutes()
}

function slotTimeLabel(s: FacultyTimetableSlot): string {
  return s.start_time && s.end_time
    ? `${formatClockTime(s.start_time)}–${formatClockTime(s.end_time)}`
    : s.period_label ?? `Period ${s.period_number}`
}

function ClassRow({ s }: { s: FacultyTimetableSlot }) {
  return (
    <div className="px-5 py-3 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-gray-800 truncate">
          {s.course_code} — {s.course_title}
        </p>
        <p className="text-xs text-gray-400 truncate">
          Sec {s.section_name} · {s.semester_name}
          {s.room && ` · Room ${s.room}`}
          {s.remarks && ` · ${s.remarks}`}
        </p>
      </div>
      <span className="text-xs font-medium text-gray-500 shrink-0">{slotTimeLabel(s)}</span>
    </div>
  )
}

function DaySection({ dayIdx, slots }: { dayIdx: number; slots: FacultyTimetableSlot[] }) {
  const sorted = [...slots].sort((a, b) => a.period_number - b.period_number)
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-700">{DAYS_OF_WEEK[dayIdx]}</h2>
      </div>
      <div className="divide-y divide-gray-100">
        {sorted.map((s) => <ClassRow key={s.id} s={s} />)}
      </div>
    </div>
  )
}

export default function FacultyTimetablePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-faculty-timetable'],
    queryFn: getMyFacultyTimetable,
  })

  const slots = data?.slots ?? []
  const today = todayIndex()

  const byDay = new Map<number, FacultyTimetableSlot[]>()
  for (const s of slots) {
    const list = byDay.get(s.day_of_week) ?? []
    list.push(s)
    byDay.set(s.day_of_week, list)
  }
  const activeDays = [...byDay.keys()].sort((a, b) => a - b)

  const todaysClasses = [...(byDay.get(today) ?? [])].sort((a, b) => a.period_number - b.period_number)

  // Upcoming = the next class today whose start time is still ahead of now.
  const now = nowMinutes()
  const upcoming = todaysClasses.filter((s) => {
    const start = toMinutes(s.start_time)
    return start === null ? false : start >= now
  })

  // Free periods today: the set of period numbers the faculty teaches on ANY
  // day (a reasonable proxy for the working-day period grid, since the faculty
  // feed carries no template) minus the ones occupied today.
  const allPeriods = [...new Set(slots.map((s) => s.period_number))].sort((a, b) => a - b)
  const occupiedToday = new Set(todaysClasses.map((s) => s.period_number))
  const freePeriodsToday = allPeriods.filter((p) => !occupiedToday.has(p))

  return (
    // Wide enough that six day columns clear the grid's minimum and never
    // scroll horizontally (see MIN_DAY_COL_PX in TimetableGrid).
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Timetable</h1>
        <p className="text-sm text-gray-400 mt-0.5">Your weekly teaching schedule across all sections.</p>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your timetable. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white h-64 animate-pulse" />
      ) : activeDays.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <CalendarClock className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No published teaching slots yet.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Today's Classes */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-5 py-2.5 bg-indigo-50 border-b border-indigo-100 flex items-center gap-2">
              <Clock className="h-4 w-4 text-indigo-600" />
              <h2 className="text-sm font-semibold text-indigo-800">Today · {DAYS_OF_WEEK[today]}</h2>
            </div>
            {todaysClasses.length === 0 ? (
              <p className="px-5 py-4 text-sm text-gray-400">No classes scheduled today.</p>
            ) : (
              <div className="divide-y divide-gray-100">
                {todaysClasses.map((s) => <ClassRow key={s.id} s={s} />)}
              </div>
            )}
          </div>

          {/* Upcoming + Free periods */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
                <ArrowRight className="h-4 w-4 text-gray-500" />
                <h2 className="text-sm font-semibold text-gray-700">Upcoming Today</h2>
              </div>
              {upcoming.length === 0 ? (
                <p className="px-5 py-4 text-xs text-gray-400">No more classes today.</p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {upcoming.map((s) => <ClassRow key={s.id} s={s} />)}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
                <Coffee className="h-4 w-4 text-gray-500" />
                <h2 className="text-sm font-semibold text-gray-700">Free Periods Today</h2>
              </div>
              {freePeriodsToday.length === 0 ? (
                <p className="px-5 py-4 text-xs text-gray-400">No free periods today.</p>
              ) : (
                <div className="px-5 py-4 flex flex-wrap gap-1.5">
                  {freePeriodsToday.map((p) => (
                    <span key={p} className="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">
                      Period {p}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Weekly timetable */}
          <div className="space-y-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Weekly Timetable</h2>
            {activeDays.map((dayIdx) => (
              <DaySection key={dayIdx} dayIdx={dayIdx} slots={byDay.get(dayIdx)!} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
