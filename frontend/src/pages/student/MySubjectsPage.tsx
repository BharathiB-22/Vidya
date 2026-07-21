import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, ChevronRight, Search } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { sisApi, MySubjectSummary } from '@/lib/api/sis'
import { useActiveSemester } from '@/hooks/useActiveSemester'

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

function SubjectRow({ subject, onClick }: { subject: MySubjectSummary; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-800">{subject.course_code}</span>
            <span className="text-sm text-gray-600 truncate">{subject.course_title}</span>
            {subject.is_elective && (
              <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700">
                Elective
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap text-xs text-gray-600">
            <span>{subject.credits} credits</span>
            <span>Semester {subject.semester}</span>
            <span>Section {subject.section_name}</span>
            {subject.faculty_name && <span>{subject.faculty_name}</span>}
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-gray-500 shrink-0" />
      </div>
    </button>
  )
}

export default function MySubjectsPage() {
  const navigate = useNavigate()
  const { semesterId } = useActiveSemester()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('ALL')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-subjects', semesterId],
    queryFn: () => sisApi.getMySubjects(semesterId),
  })

  const subjects = data?.subjects ?? []

  const courseTypes = useMemo(
    () => Array.from(new Set(subjects.map((s) => s.course_type).filter(Boolean))) as string[],
    [subjects],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return subjects.filter((s) => {
      const matchesSearch =
        !q ||
        s.course_code.toLowerCase().includes(q) ||
        s.course_title.toLowerCase().includes(q)
      const matchesType =
        typeFilter === 'ALL' ||
        (typeFilter === 'ELECTIVE' ? s.is_elective : s.course_type === typeFilter)
      return matchesSearch && matchesType
    })
  }, [subjects, search, typeFilter])

  return (
    <PageShell>
      <PageHeader
        icon={BookOpen}
        title="My Subjects"
        subtitle={data ? `${data.student_name}${data.usn ? ` · USN: ${data.usn}` : ''}` : 'Your subjects for the current semester'}
      />

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="h-4 w-4 text-gray-600 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by subject code or title…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        {courseTypes.length > 0 && (
          <div className="flex gap-1.5 overflow-x-auto">
            {['ALL', ...courseTypes, 'ELECTIVE'].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTypeFilter(t)}
                className={`shrink-0 text-xs px-3 py-1.5 rounded-full font-medium border transition-colors ${
                  typeFilter === t
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
              >
                {t === 'ALL' ? 'All' : t === 'ELECTIVE' ? 'Electives' : t}
              </button>
            ))}
          </div>
        )}
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your subjects. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-600">
            {subjects.length === 0 ? 'No subjects enrolled yet.' : 'No subjects match your search.'}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {filtered.map((s) => (
            <SubjectRow
              key={s.course_id}
              subject={s}
              onClick={() => navigate(`/student/subjects/${s.course_id}`)}
            />
          ))}
        </div>
      )}
    </PageShell>
  )
}
