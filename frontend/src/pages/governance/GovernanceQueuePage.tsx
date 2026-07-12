import { useNavigate } from 'react-router-dom'
import {
  BookLock, ClipboardCheck, Clock, GraduationCap, Layers,
  Landmark, Rocket, ArrowRight, Inbox,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useReviewQueue } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'
import type { GovernanceQueueItem } from '@/types/governance'

/**
 * The governance authority's home: every curriculum the Deans have submitted.
 *
 * This is the queue that did not exist before Phase A — curriculum used to be
 * approved by the same Dean who wrote it, so there was nobody to queue it for.
 */
export default function GovernanceQueuePage() {
  const { bodyLabel } = useGovernance()
  const { data, isLoading, isError } = useReviewQueue()

  if (isLoading) {
    return <div className="p-6"><PageLoading message="Loading curriculum review queue…" /></div>
  }
  if (isError || !data) {
    return (
      <div className="p-6">
        <PageError message="Could not load the review queue. You may not be a member of the governance authority." />
      </div>
    )
  }

  const { pending, approved, published } = data

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <header className="mb-6">
        <div className="flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-black text-white">
            <Landmark className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-black">Curriculum Review</h1>
            <p className="text-sm text-gray-600">
              Curricula submitted by Deans for {bodyLabel} approval. You own the final curriculum:
              review it, revise it, generate the syllabus, then approve and lock.
            </p>
          </div>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-3 mb-6">
        <StatTile label="Awaiting your decision" value={pending.length} icon={Clock} emphasis />
        <StatTile label="Approved & locked" value={approved.length} icon={BookLock} />
        <StatTile label="Published by Deans" value={published.length} icon={Rocket} />
      </div>

      <Tabs defaultValue="pending">
        <TabsList>
          <TabsTrigger value="pending">Pending ({pending.length})</TabsTrigger>
          <TabsTrigger value="approved">Approved ({approved.length})</TabsTrigger>
          <TabsTrigger value="published">Published ({published.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="mt-4">
          <CurriculumList
            items={pending}
            emptyMessage={`Nothing is waiting on the ${bodyLabel} right now. Curricula appear here the moment a Dean submits one.`}
            actionLabel="Review"
          />
        </TabsContent>
        <TabsContent value="approved" className="mt-4">
          <CurriculumList
            items={approved}
            emptyMessage="No curriculum has been approved and locked yet."
            actionLabel="View"
          />
        </TabsContent>
        <TabsContent value="published" className="mt-4">
          <CurriculumList
            items={published}
            emptyMessage="No approved curriculum has been published by a Dean yet."
            actionLabel="View"
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function StatTile({
  label, value, icon: Icon, emphasis,
}: {
  label: string
  value: number
  icon: typeof Clock
  emphasis?: boolean
}) {
  return (
    <div
      className={`rounded-xl border p-4 shadow-sm ${
        emphasis ? 'border-black bg-black text-white' : 'border-gray-200 bg-white'
      }`}
    >
      <div className="flex items-center justify-between">
        <p className={`text-xs font-semibold uppercase tracking-wide ${emphasis ? 'text-gray-300' : 'text-gray-500'}`}>
          {label}
        </p>
        <Icon className={`h-4 w-4 ${emphasis ? 'text-white' : 'text-gray-400'}`} />
      </div>
      <p className={`mt-1 text-3xl font-bold ${emphasis ? 'text-white' : 'text-black'}`}>{value}</p>
    </div>
  )
}

function CurriculumList({
  items, emptyMessage, actionLabel,
}: {
  items: GovernanceQueueItem[]
  emptyMessage: string
  actionLabel: string
}) {
  const navigate = useNavigate()

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
        <Inbox className="mx-auto h-8 w-8 text-gray-400" />
        <p className="mt-2 text-sm text-gray-600">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <article
          key={item.program_id}
          className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-gray-400 hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-black">{item.title}</h2>
              <p className="mt-0.5 text-sm text-gray-600">
                {item.department} · {item.degree_type} · v{item.version}
                {item.academic_year ? ` · ${item.academic_year}` : ''}
                {item.batch_name ? ` · ${item.batch_name}` : ''}
              </p>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Chip icon={GraduationCap} text={`${item.course_count} subjects`} />
                <Chip icon={Layers} text={`${item.elective_slot_count} elective slots`} />
                <Chip icon={BookLock} text={`${item.total_credits} credits`} />
                <SyllabusProgressChip item={item} />
              </div>

              {item.submitted_by_name && (
                <p className="mt-3 text-xs text-gray-500">
                  Submitted by <span className="font-semibold text-black">{item.submitted_by_name}</span>
                  {item.submitted_at && ` on ${new Date(item.submitted_at).toLocaleDateString()}`}
                </p>
              )}
              {item.submission_note && (
                <p className="mt-2 max-w-2xl rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                  “{item.submission_note}”
                </p>
              )}
            </div>

            <Button size="sm" onClick={() => navigate(`/governance/curriculum/${item.program_id}`)}>
              {actionLabel}
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </article>
      ))}
    </div>
  )
}

/**
 * How far the official syllabus has got. This is the single number the Board
 * cares about on this screen: a curriculum cannot be approved until EVERY subject
 * has an approved syllabus, so "18 of 42 approved" is the distance still to go.
 */
function SyllabusProgressChip({ item }: { item: GovernanceQueueItem }) {
  const done = item.approved_syllabus_count
  const total = item.course_count
  const complete = total > 0 && done === total

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${
        complete
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-amber-200 bg-amber-50 text-amber-800'
      }`}
    >
      <ClipboardCheck className={`h-3.5 w-3.5 ${complete ? 'text-emerald-600' : 'text-amber-600'}`} />
      {done} of {total} syllabi approved
    </span>
  )
}

function Chip({ icon: Icon, text }: { icon: typeof Clock; text: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-xs font-medium text-gray-700">
      <Icon className="h-3.5 w-3.5 text-gray-500" />
      {text}
    </span>
  )
}
