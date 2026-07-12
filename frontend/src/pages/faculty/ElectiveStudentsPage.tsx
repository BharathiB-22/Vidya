import { useQuery } from '@tanstack/react-query'
import { Users2, GraduationCap } from 'lucide-react'
import { getFacultyElectiveRoster, type FacultyElectiveRoster } from '@/lib/api/electives'

function RosterCard({ roster }: { roster: FacultyElectiveRoster }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="flex items-center justify-between gap-4 px-4 py-3 bg-gray-50 border-b border-gray-100">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <GraduationCap className="h-4 w-4 text-indigo-500" />
            <span className="text-sm font-semibold text-gray-900">{roster.course_title}</span>
            <span className="text-xs text-gray-500">{roster.course_code}</span>
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {roster.basket_name} · {roster.semester_label ?? ''}
            {roster.section_count > 1 && ` · combined across ${roster.section_count} sections`}
          </div>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-full px-2.5 py-1 shrink-0">
          <Users2 className="h-3.5 w-3.5" />
          {roster.total_students} student{roster.total_students === 1 ? '' : 's'}
        </span>
      </div>

      {roster.students.length === 0 ? (
        <p className="text-xs text-gray-500 px-4 py-3">No students have registered for this elective yet.</p>
      ) : (
        <ol className="divide-y divide-gray-100">
          {roster.students.map((s, i) => (
            <li key={s.student_id} className="flex items-center gap-3 px-4 py-2.5">
              <span className="text-xs text-gray-400 w-6 shrink-0">{i + 1}.</span>
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium text-gray-900">{s.student_name}</span>
                {s.usn && <span className="text-xs text-gray-500 ml-2">{s.usn}</span>}
              </div>
              {s.section_name && (
                <span className="text-xs text-gray-400 shrink-0">{s.section_name}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export default function ElectiveStudentsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['faculty-elective-roster'],
    queryFn: getFacultyElectiveRoster,
  })

  const rosters = data ?? []

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Elective Students</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Students who chose the elective subjects the Dean assigned you to teach. Everyone
          who picked the same subject forms one class, whichever section they belong to.
        </p>
      </div>

      {isError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your elective students. Please refresh.
        </div>
      ) : isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((n) => <div key={n} className="h-28 rounded-xl bg-gray-50 animate-pulse" />)}
        </div>
      ) : rosters.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Users2 className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-500">
            You have no elective courses with registered students yet.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {rosters.map((r) => <RosterCard key={r.course_id} roster={r} />)}
        </div>
      )}
    </div>
  )
}
