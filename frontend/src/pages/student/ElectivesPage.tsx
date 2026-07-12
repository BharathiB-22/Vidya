import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ListChecks, Check, Lock } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import {
  getMyElectiveSlots,
  registerElective,
  dropElective,
  getMyElectives,
  type ElectiveSlot,
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

/** One elective slot: choose exactly ONE of its subjects.
 *
 *  A student never picks "AI" from a flat list of every elective — they pick one
 *  subject inside Elective 1, then one inside Elective 2, and so on. A radio
 *  group per slot is what makes that structure visible and unambiguous.
 *
 *  Registerable only while the slot is OPEN. A PUBLISHED slot is shown so the
 *  student knows what is coming; a CLOSED one shows their final choice. */
function SlotCard({ slot }: { slot: ElectiveSlot }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const registerMut = useMutation({
    mutationFn: (courseId: string) => registerElective(slot.basket_id, courseId),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['elective-slots'] })
      queryClient.invalidateQueries({ queryKey: ['my-electives'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const locked = !slot.can_register
  const notYetOpen = slot.status === 'PUBLISHED'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-900">{slot.name}</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
              {slot.credits} credits
            </span>
          </div>
          {slot.description && (
            <p className="text-sm text-gray-600 mt-1 line-clamp-3">{slot.description}</p>
          )}
          <p className="text-xs text-gray-500 mt-1">Choose ONE.</p>
        </div>
        {locked && (
          <span className="flex items-center gap-1 text-xs text-gray-500 shrink-0">
            <Lock className="h-3.5 w-3.5" />
            {notYetOpen ? 'Not open yet' : 'Registration closed'}
          </span>
        )}
      </div>

      {error && <div className="text-xs text-red-600">{error}</div>}

      <fieldset disabled={locked || registerMut.isPending}>
        <legend className="sr-only">{slot.name} — choose one subject</legend>
        <div className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
          {slot.options.map((c) => {
            const isChosen = slot.chosen_course_id === c.course_id

            return (
              <label
                key={c.course_id}
                className={`flex items-center gap-3 px-4 py-3 ${
                  isChosen ? 'bg-indigo-50/50' : ''
                } ${locked ? 'cursor-default' : 'cursor-pointer hover:bg-gray-50'}`}
              >
                <input
                  type="radio"
                  name={`slot-${slot.basket_id}`}
                  className="h-4 w-4 shrink-0 accent-indigo-600"
                  checked={isChosen}
                  disabled={locked || registerMut.isPending}
                  onChange={() => registerMut.mutate(c.course_id)}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-900">{c.title}</span>
                    <span className="text-xs text-gray-500">{c.code}</span>
                    <span className="text-xs text-gray-500">{c.credits} credits</span>
                  </div>
                  {c.faculty_name && (
                    <div className="text-xs text-gray-600 mt-1">Faculty: {c.faculty_name}</div>
                  )}
                </div>
                {isChosen && (
                  <span className="flex items-center gap-1 text-xs font-medium text-indigo-700 shrink-0">
                    <Check className="h-4 w-4" />
                    Selected
                  </span>
                )}
              </label>
            )
          })}
        </div>
      </fieldset>

      {registerMut.isPending && <p className="text-xs text-gray-500">Saving…</p>}
    </div>
  )
}

function ChooseElectivesTab() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['elective-slots'],
    queryFn: getMyElectiveSlots,
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
        {[1, 2, 3].map((n) => (
          <SkeletonCard key={n} />
        ))}
      </div>
    )
  }

  const slots = data ?? []

  if (slots.length === 0) {
    return (
      <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
        <ListChecks className="h-10 w-10 mx-auto mb-3 text-gray-200" />
        <p className="text-sm text-gray-500">
          Your semester has no elective slots to choose from.
        </p>
      </div>
    )
  }

  // Every slot belongs to the student's own current semester, so one heading.
  return (
    <div className="space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        Semester {slots[0].semester}
      </h2>
      {slots.map((s) => (
        <SlotCard key={s.basket_id} slot={s} />
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
  const { data: slots } = useQuery({
    queryKey: ['elective-slots'],
    queryFn: getMyElectiveSlots,
  })

  const dropMut = useMutation({
    mutationFn: (basketId: string) => dropElective(basketId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-electives'] })
      queryClient.invalidateQueries({ queryKey: ['elective-slots'] })
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
  // A choice can only be dropped while its slot is still open for registration.
  const openSlots = new Set((slots ?? []).filter((s) => s.can_register).map((s) => s.basket_id))

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
          Current
        </h2>
        {current.length === 0 ? (
          <p className="text-sm text-gray-500">No current elective selections.</p>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {current.map((r) => (
              <div key={r.id} className="px-5 py-4 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-gray-900">{r.course_title}</div>
                  <div className="text-xs text-gray-600">{r.basket_name} · {r.course_code} · {r.status}</div>
                </div>
                {r.status === 'REGISTERED' && openSlots.has(r.basket_id) && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={dropMut.isPending}
                    onClick={() => dropMut.mutate(r.basket_id)}
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
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
          Past
        </h2>
        {past.length === 0 ? (
          <p className="text-sm text-gray-500">No past elective selections.</p>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {past.map((r) => (
              <div key={r.id} className="px-5 py-4">
                <div className="text-sm font-semibold text-gray-900">{r.course_title}</div>
                <div className="text-xs text-gray-600">{r.basket_name} · {r.course_code} · {r.status}</div>
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
        <p className="text-sm text-gray-500 mt-0.5">
          Choose one subject for each elective slot in your semester.
        </p>
      </div>

      <Tabs defaultValue="choose">
        <TabsList>
          <TabsTrigger value="choose">Choose Electives</TabsTrigger>
          <TabsTrigger value="mine">My Electives</TabsTrigger>
        </TabsList>
        <TabsContent value="choose">
          <ChooseElectivesTab />
        </TabsContent>
        <TabsContent value="mine">
          <MyElectivesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
