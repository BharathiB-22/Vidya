import { useNavigate } from 'react-router-dom'
import { BookLock, Lock, Rocket, ArrowRight, Inbox } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useReviewQueue } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'

/**
 * Every curriculum this authority has approved and locked, plus the ones Deans
 * have since published. Read-only by design: an approved curriculum is frozen,
 * and changing it means a new version.
 */
export default function ApprovedCurriculaPage() {
  const navigate = useNavigate()
  const { bodyLabel } = useGovernance()
  const { data, isLoading, isError } = useReviewQueue()

  if (isLoading) {
    return <div className="p-6"><PageLoading message="Loading approved curricula…" /></div>
  }
  if (isError || !data) {
    return <div className="p-6"><PageError message="Could not load approved curricula." /></div>
  }

  const rows = [
    ...data.approved.map((i) => ({ ...i, published: false })),
    ...data.published.map((i) => ({ ...i, published: true })),
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-black">Approved Curricula</h1>
        <p className="mt-1 text-sm text-gray-600">
          Locked by the {bodyLabel}. These are frozen — no one edits them, not even you. A change
          means a new version, prepared by the Dean and submitted again.
        </p>
      </header>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
          <Inbox className="mx-auto h-8 w-8 text-gray-600" />
          <p className="mt-2 text-sm text-gray-600">
            Nothing approved yet. Approved curricula appear here and stay locked.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((item) => (
            <article
              key={item.program_id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-gray-400 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-lg font-bold text-black">{item.title}</h2>
                    {item.published ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                        <Rocket className="h-3.5 w-3.5" />
                        Published
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-gray-100 px-2 py-0.5 text-xs font-semibold text-black">
                        <Lock className="h-3.5 w-3.5" />
                        Locked — awaiting Dean publish
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm text-gray-600">
                    {item.department} · {item.degree_type} · v{item.version}
                    {item.regulation_year ? ` · R${item.regulation_year}` : ''} ·{' '}
                    {item.total_credits} credits
                  </p>
                  <p className="mt-2 flex items-center gap-1.5 text-xs text-gray-500">
                    <BookLock className="h-3.5 w-3.5" />
                    {item.locked_at
                      ? `Locked on ${new Date(item.locked_at).toLocaleDateString()}`
                      : 'Locked'}
                    {item.published_at &&
                      ` · Published on ${new Date(item.published_at).toLocaleDateString()}`}
                  </p>
                </div>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/programs/${item.program_id}`)}
                >
                  View
                  <ArrowRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
