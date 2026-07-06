import { useQuery } from '@tanstack/react-query'
import { CalendarClock } from 'lucide-react'
import { TimetableGrid } from '@/components/timetable/TimetableGrid'
import { getMyStudentTimetable } from '@/lib/api/timetable'

export default function TimetablePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-student-timetable'],
    queryFn: getMyStudentTimetable,
  })

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Timetable</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          {data?.section_name ? `Section ${data.section_name}` : 'Your weekly class schedule.'}
        </p>
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
          <p className="text-sm text-gray-400">Your timetable hasn't been published yet.</p>
        </div>
      ) : (
        <TimetableGrid
          slots={data.slots}
          periods={data.template?.periods}
          workingDays={data.template?.working_days}
          saturdayMode={data.template?.saturday_mode}
          editable={false}
        />
      )}
    </div>
  )
}
