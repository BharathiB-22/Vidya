import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ListChecks, Users2 } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { useActiveSemester } from '@/hooks/useActiveSemester'
import {
  listElectiveOfferings,
  registerElective,
  dropElective,
  getMyElectives,
  type ElectiveOffering,
} from '@/lib/api/electives'
import { getErrorMessage } from '@/lib/api'

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-2 h-3 w-full rounded bg-gray-100" />
      <div className="mt-1 h-3 w-2/3 rounded bg-gray-100" />
    </div>
  )
}

function OfferingCard({ offering }: { offering: ElectiveOffering }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const registerMut = useMutation({
    mutationFn: () => registerElective(offering.id),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['elective-offerings'] })
      queryClient.invalidateQueries({ queryKey: ['my-electives'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const seatsLeft = offering.max_seats - offering.seats_taken
  const isFull = seatsLeft <= 0
  const isClosed = offering.status === 'CLOSED'
  const disabled = isFull || isClosed || registerMut.isPending

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-800">{offering.course_title}</span>
            <span className="text-xs text-gray-400">{offering.course_code}</span>
          </div>
          {offering.description && (
            <p className="text-sm text-gray-500 mt-1 line-clamp-3">{offering.description}</p>
          )}
        </div>
        <span className="text-xs px-2 py-1 rounded-full bg-indigo-50 text-indigo-700 font-medium shrink-0">
          {offering.credits} credits
        </span>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
        {offering.faculty_name && <span>Faculty: {offering.faculty_name}</span>}
        <span className="flex items-center gap-1">
          <Users2 className="h-3.5 w-3.5" />
          {seatsLeft > 0 ? `${seatsLeft} seat${seatsLeft === 1 ? '' : 's'} left` : 'Full'}
          {' '}({offering.seats_taken}/{offering.max_seats})
        </span>
        {isClosed && <span className="text-red-500 font-medium">Registration closed</span>}
      </div>

      {error && <div className="text-xs text-red-600">{error}</div>}

      <Button
        size="sm"
        disabled={disabled}
        onClick={() => registerMut.mutate()}
      >
        {registerMut.isPending ? 'Registering…' : isClosed ? 'Closed' : isFull ? 'Full' : 'Register'}
      </Button>
    </div>
  )
}

function AvailableElectivesTab() {
  const { semesterId, isSemestersLoading } = useActiveSemester()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['elective-offerings', semesterId],
    queryFn: () => listElectiveOfferings(semesterId as string),
    enabled: !!semesterId,
  })

  const offerings = data ?? []
  const loading = isSemestersLoading || isLoading

  if (isError) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
        Failed to load available electives. Please refresh.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((n) => (
          <SkeletonCard key={n} />
        ))}
      </div>
    )
  }

  if (offerings.length === 0) {
    return (
      <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
        <ListChecks className="h-10 w-10 mx-auto mb-3 text-gray-200" />
        <p className="text-sm text-gray-400">No electives are open for registration right now.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {offerings.map((o) => (
        <OfferingCard key={o.id} offering={o} />
      ))}
    </div>
  )
}

function MyElectivesTab() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-electives'],
    queryFn: getMyElectives,
  })

  const dropMut = useMutation({
    mutationFn: (offeringId: string) => dropElective(offeringId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-electives'] })
      queryClient.invalidateQueries({ queryKey: ['elective-offerings'] })
    },
  })

  if (isError) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
        Failed to load your electives. Please refresh.
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((n) => (
          <SkeletonCard key={n} />
        ))}
      </div>
    )
  }

  const items = data ?? []
  const current = items.filter((r) => r.is_current)
  const past = items.filter((r) => !r.is_current)

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">
          Current
        </h2>
        {current.length === 0 ? (
          <p className="text-sm text-gray-400">No current elective registrations.</p>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {current.map((r) => (
              <div key={r.id} className="px-5 py-4 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-gray-800">{r.course_title}</div>
                  <div className="text-xs text-gray-400">{r.course_code} · {r.status}</div>
                </div>
                {r.status === 'REGISTERED' && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={dropMut.isPending}
                    onClick={() => dropMut.mutate(r.offering_id)}
                  >
                    Drop
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">
          Past
        </h2>
        {past.length === 0 ? (
          <p className="text-sm text-gray-400">No past elective registrations.</p>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {past.map((r) => (
              <div key={r.id} className="px-5 py-4">
                <div className="text-sm font-semibold text-gray-800">{r.course_title}</div>
                <div className="text-xs text-gray-400">{r.course_code} · {r.status}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default function ElectivesPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Electives</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Register for available electives and track your current and past selections.
        </p>
      </div>

      <Tabs defaultValue="available">
        <TabsList>
          <TabsTrigger value="available">Available Electives</TabsTrigger>
          <TabsTrigger value="mine">My Electives</TabsTrigger>
        </TabsList>
        <TabsContent value="available">
          <AvailableElectivesTab />
        </TabsContent>
        <TabsContent value="mine">
          <MyElectivesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
