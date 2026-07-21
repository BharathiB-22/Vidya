import { useQuery } from '@tanstack/react-query'
import { CalendarClock, Clock, ArrowRight } from 'lucide-react'
import { TimetableGrid } from '@/components/timetable/TimetableGrid'
import { getMyStudentTimetable } from '@/lib/api/timetable'
import { DAYS_OF_WEEK, formatClockTime, type TimetableSlot } from '@/types/timetable'

function todayIndex(): number {
  return (new Date().getDay() + 6) % 7 // Mon=0..Sun=6
}

function toMinutes(t: string | null): number | null {
  if (!t) return null
  const [h, m] = t.split(':')
  return Number(h) * 60 + Number(m)
}

function nowMinutes(): number {
  const d = new Date()
  return d.getHours() * 60 + d.getMinutes()
}

function slotTime(s: TimetableSlot): string {
  return s.start_time && s.end_time
    ? `${formatClockTime(s.start_time)}–${formatClockTime(s.end_time)}`
    : s.period_label ?? `Period ${s.period_number}`
}

function ClassRow({ s }: { s: TimetableSlot }) {
  return (
    <div className="px-5 py-3 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-gray-800 truncate">
          {s.course_code} — {s.course_title}
        </p>
        <p className="text-xs text-gray-600 truncate">
          {s.faculty_name ?? 'Faculty TBA'}
          {s.room && ` · Room ${s.room}`}
          {s.remarks && ` · ${s.remarks}`}
        </p>
      </div>
      <span className="text-xs font-medium text-gray-500 shrink-0">{slotTime(s)}</span>
    </div>
  )
}

function Chip({ label }: { label: string }) {
  return (
    <span className="text-xs px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100">
      {label}
    </span>
  )
}

export default function TimetablePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-student-timetable'],
    queryFn: getMyStudentTimetable,
  })

  const today = todayIndex()
  const slots = data?.slots ?? []
  const todaysClasses = slots
    .filter((s) => s.day_of_week === today)
    .sort((a, b) => a.period_number - b.period_number)

  const now = nowMinutes()
  const nextClass = todaysClasses.find((s) => {
    const start = toMinutes(s.start_time)
    return start === null ? false : start >= now
  })

  return (
    // Wide enough for a seven-day grid (a timetable with no template shows all
    // days) to clear the grid's minimum without scrolling horizontally.
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Timetable</h1>
        <p className="text-sm text-gray-600 mt-0.5">Your weekly class schedule.</p>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your timetable. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white h-64 animate-pulse" />
      ) : !data ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <CalendarClock className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-600">Your timetable hasn't been published yet.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Context chips */}
          <div className="flex flex-wrap gap-2">
            {data.program_name && <Chip label={data.program_name} />}
            {data.semester_label && <Chip label={data.semester_label} />}
            {data.section_name && <Chip label={`Section ${data.section_name}`} />}
            {data.academic_year && <Chip label={`AY ${data.academic_year}`} />}
          </div>

          {/* Today + Upcoming */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-5 py-2.5 bg-indigo-50 border-b border-indigo-100 flex items-center gap-2">
                <Clock className="h-4 w-4 text-indigo-600" />
                <h2 className="text-sm font-semibold text-indigo-800">Today · {DAYS_OF_WEEK[today]}</h2>
              </div>
              {todaysClasses.length === 0 ? (
                <p className="px-5 py-4 text-sm text-gray-600">No classes scheduled today.</p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {todaysClasses.map((s) => <ClassRow key={s.id} s={s} />)}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
                <ArrowRight className="h-4 w-4 text-gray-500" />
                <h2 className="text-sm font-semibold text-gray-700">Upcoming Class</h2>
              </div>
              {nextClass ? (
                <div className="divide-y divide-gray-100"><ClassRow s={nextClass} /></div>
              ) : (
                <p className="px-5 py-4 text-xs text-gray-600">No more classes today.</p>
              )}
            </div>
          </div>

          {/* Weekly grid */}
          <div className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Weekly Timetable</h2>
            <TimetableGrid
              slots={data.slots}
              periods={data.template?.periods}
              workingDays={data.template?.working_days}
              saturdayMode={data.template?.saturday_mode}
              editable={false}
            />
          </div>
        </div>
      )}
    </div>
  )
}
