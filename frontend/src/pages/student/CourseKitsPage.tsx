import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Presentation, Search } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { sisApi } from '@/lib/api/sis'
import { studentListKits } from '@/lib/api/courseKit'

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

export default function CourseKitsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const { data: subjectsData, isLoading: subjectsLoading, isError: subjectsError } = useQuery({
    queryKey: ['my-subjects'],
    queryFn: () => sisApi.getMySubjects(),
  })

  const subjects = (subjectsData?.subjects ?? []).filter((s) => !!s.syllabus_id)

  const kitQueries = useQueries({
    queries: subjects.map((s) => ({
      queryKey: ['student-course-kits', s.syllabus_id],
      queryFn: () => studentListKits(s.syllabus_id as string),
      enabled: !!s.syllabus_id,
    })),
  })

  const isLoading = subjectsLoading || kitQueries.some((q) => q.isLoading)

  const groups = useMemo(() => {
    return subjects
      .map((s, i) => ({
        subject: s,
        kits: kitQueries[i]?.data?.items ?? [],
      }))
      .filter((g) => g.kits.length > 0)
      .filter((g) =>
        search.trim() === '' ||
        g.subject.course_title.toLowerCase().includes(search.toLowerCase()) ||
        g.subject.course_code.toLowerCase().includes(search.toLowerCase())
      )
  }, [subjects, kitQueries, search])

  return (
    <PageShell>
      <PageHeader
        icon={Presentation}
        title="Course Kits"
        subtitle="Published slide decks, resources and course content, grouped by subject."
      />

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by subject…"
          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-sv-primary/30"
        />
      </div>

      {subjectsError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your subjects. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Presentation className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-600">No course kits available yet.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <section key={g.subject.course_id} className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <button
                type="button"
                onClick={() => navigate(`/student/subjects/${g.subject.course_id}`)}
                className="w-full text-left px-5 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors"
              >
                <span className="text-sm font-semibold text-gray-800">{g.subject.course_title}</span>
                <span className="text-xs text-gray-600 ml-2">{g.subject.course_code} · {g.kits.length} kit{g.kits.length === 1 ? '' : 's'}</span>
              </button>
              <div className="divide-y divide-gray-100">
                {g.kits.map((kit) => (
                  <button
                    key={kit.id}
                    type="button"
                    onClick={() => navigate(`/student/subjects/${g.subject.course_id}`)}
                    className="w-full text-left px-5 py-3 hover:bg-gray-50 transition-colors flex items-center justify-between gap-4"
                  >
                    <span className="text-sm text-gray-700">Unit {kit.unit_number}</span>
                    <span className="text-xs text-gray-600 capitalize">{kit.complexity_level?.toLowerCase()}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </PageShell>
  )
}
