import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PartyPopper } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { getMyCalendar, type CalendarItem, type CalendarItemType } from '@/lib/api/calendar'

const EVENT_TYPES: CalendarItemType[] = ['HOLIDAY', 'EVENT', 'ANNOUNCEMENT']

const TYPE_CONFIG: Record<string, { label: string; cls: string }> = {
  HOLIDAY: { label: 'Holiday', cls: 'bg-rose-50 text-rose-700' },
  EVENT: { label: 'Event', cls: 'bg-indigo-50 text-indigo-700' },
  ANNOUNCEMENT: { label: 'Announcement', cls: 'bg-amber-50 text-amber-700' },
}

function fmtISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-56 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-32 rounded bg-gray-100" />
    </div>
  )
}

export default function EventsPage() {
  const { dateFrom, dateTo } = useMemo(() => {
    const from = new Date()
    const to = new Date(from)
    to.setDate(to.getDate() + 60)
    return { dateFrom: fmtISODate(from), dateTo: fmtISODate(to) }
  }, [])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['student-calendar', dateFrom, dateTo],
    queryFn: () => getMyCalendar(dateFrom, dateTo),
  })

  const items: CalendarItem[] = useMemo(
    () => (data ?? []).filter((i) => EVENT_TYPES.includes(i.item_type)).sort((a, b) => a.date.localeCompare(b.date)),
    [data]
  )

  return (
    <PageShell>
      <PageHeader
        icon={PartyPopper}
        title="Events"
        subtitle="Institutional holidays, events and announcements — see Calendar for deadlines and exams."
      />

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load events. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <PartyPopper className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No upcoming events or holidays.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((item) => {
            const cfg = TYPE_CONFIG[item.item_type] ?? { label: item.item_type, cls: 'bg-gray-50 text-gray-600' }
            return (
              <div key={item.id} className="px-5 py-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800 truncate">{item.title}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${cfg.cls}`}>{cfg.label}</span>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {new Date(item.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                    {item.all_day && <> · All day</>}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </PageShell>
  )
}
