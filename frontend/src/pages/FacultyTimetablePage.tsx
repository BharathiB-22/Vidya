import { useQuery } from '@tanstack/react-query'
import { CalendarClock } from 'lucide-react'
import { getMyFacultyTimetable } from '@/lib/api/timetable'
import { DAYS_OF_WEEK, formatClockTime, type FacultyTimetableSlot } from '@/types/timetable'

function DaySection({ dayIdx, slots }: { dayIdx: number; slots: FacultyTimetableSlot[] }) {
  const sorted = [...slots].sort((a, b) => a.period_number - b.period_number)
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-700">{DAYS_OF_WEEK[dayIdx]}</h2>
      </div>
      <div className="divide-y divide-gray-100">
        {sorted.map((s) => (
          <div key={s.id} className="px-5 py-3 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-800 truncate">
                {s.course_code} — {s.course_title}
              </p>
              <p className="text-xs text-gray-400 truncate">
                Sec {s.section_name} · {s.semester_name}
                {s.room && ` · Room ${s.room}`}
              </p>
            </div>
            <span className="text-xs font-medium text-gray-500 shrink-0">
              {s.start_time && s.end_time
                ? `${formatClockTime(s.start_time)}–${formatClockTime(s.end_time)}`
                : s.period_label ?? `Period ${s.period_number}`}
            </span>
          </div>
        ))}
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
  const byDay = new Map<number, FacultyTimetableSlot[]>()
  for (const s of slots) {
    const list = byDay.get(s.day_of_week) ?? []
    list.push(s)
    byDay.set(s.day_of_week, list)
  }
  const activeDays = [...byDay.keys()].sort((a, b) => a - b)

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
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
        <div className="space-y-4">
          {activeDays.map((dayIdx) => (
            <DaySection key={dayIdx} dayIdx={dayIdx} slots={byDay.get(dayIdx)!} />
          ))}
        </div>
      )}
    </div>
  )
}
