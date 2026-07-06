import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Users, AlertTriangle } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import type { FacultySubjectTabProps } from './types'

export function StudentsTab({ ctx }: FacultySubjectTabProps) {
  const sectionId = ctx.assignment.section_id
  const [search, setSearch] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['section-attendance', sectionId],
    queryFn: () => sisApi.getSectionAttendance(sectionId!),
    enabled: !!sectionId,
  })

  const students = useMemo(() => {
    const all = data?.students ?? []
    const q = search.trim().toLowerCase()
    if (!q) return all
    return all.filter(
      (s) => s.student_name.toLowerCase().includes(q) || (s.usn ?? '').toLowerCase().includes(q)
    )
  }, [data, search])

  if (!sectionId) {
    return <div className="text-sm text-gray-400 py-8 text-center">No section on record for this subject.</div>
  }

  if (isLoading) {
    return <div className="text-sm text-gray-400 py-8 text-center">Loading students…</div>
  }

  if (isError || !data) {
    return <div className="text-sm text-gray-400 py-8 text-center">Failed to load the student roster.</div>
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          {data.students.length} student{data.students.length !== 1 ? 's' : ''} · Section {data.section_name}
        </p>
        <div className="relative w-56">
          <Search className="h-3.5 w-3.5 text-gray-300 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or USN…"
            className="w-full text-sm pl-8 pr-3 py-1.5 rounded-lg border border-gray-200 outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {students.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <Users className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No students match your search.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {students.map((s) => (
            <div key={s.student_id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{s.student_name}</p>
                <p className="text-xs text-gray-400 font-mono">{s.usn ?? '—'}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {s.is_at_risk && <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />}
                <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-50 text-gray-600">
                  {s.attendance_pct != null ? `${s.attendance_pct.toFixed(0)}% attendance` : '—'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Student profile pages are currently Admin/Dean-only; this roster is read-only for faculty.
      </p>
    </div>
  )
}
