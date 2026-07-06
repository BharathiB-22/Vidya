import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Award, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useActiveSemester } from '@/hooks/useActiveSemester'

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-40 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

const STATUS_CLS: Record<string, string> = {
  PASS: 'bg-green-50 text-green-700',
  FAIL: 'bg-red-50 text-red-700',
  WITHHELD: 'bg-yellow-50 text-yellow-700',
}

export default function SemesterResultsPage() {
  const navigate = useNavigate()
  const { profile } = useActiveSemester()
  const batchId = profile?.batch?.id

  const { data: results, isLoading: resultsLoading, isError } = useQuery({
    queryKey: ['my-results'],
    queryFn: sisApi.getMyResults,
  })

  const { data: semesters, isLoading: semestersLoading } = useQuery({
    queryKey: ['semesters', batchId, 'all'],
    queryFn: () => academicsApi.listSemesters(batchId, true),
    enabled: !!batchId,
  })

  const isLoading = resultsLoading || (!!batchId && semestersLoading)

  const rows = useMemo(() => {
    const semMap = new Map((semesters ?? []).map((s) => [s.id, s]))
    return (results ?? [])
      .map((r) => ({ result: r, semester: semMap.get(r.semester_id) }))
      .sort((a, b) => (b.semester?.number ?? 0) - (a.semester?.number ?? 0))
  }, [results, semesters])

  return (
    <PageShell>
      <PageHeader
        icon={Award}
        title="Semester Results"
        subtitle="SGPA, CGPA and rank per semester."
      />

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your results. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Award className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No semester results published yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {rows.map(({ result, semester }) => (
            <button
              key={result.id}
              type="button"
              onClick={() => navigate(`/sis/my-grade-card/${result.declaration_id}`)}
              className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors flex items-center justify-between gap-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-gray-800">
                    {semester ? (semester.label || `Semester ${semester.number}`) : 'Semester'}
                  </span>
                  {result.overall_result_status && (
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STATUS_CLS[result.overall_result_status] ?? 'bg-gray-50 text-gray-600'}`}>
                      {result.overall_result_status}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1 flex-wrap text-xs text-gray-400">
                  {result.sgpa != null && <span>SGPA {result.sgpa.toFixed(2)}</span>}
                  {result.cgpa != null && <span>CGPA {result.cgpa.toFixed(2)}</span>}
                  {result.total_credits_earned != null && (
                    <span>{result.total_credits_earned}/{result.total_credits_attempted ?? '—'} credits</span>
                  )}
                  {result.section_rank != null && <span>Section rank #{result.section_rank}</span>}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-gray-300 shrink-0" />
            </button>
          ))}
        </div>
      )}
    </PageShell>
  )
}
