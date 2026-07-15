import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, PartyPopper } from 'lucide-react'
import { getMyCalendar, type CalendarItem, type CalendarItemType } from '@/lib/api/calendar'

const TYPE_CONFIG: Record<CalendarItemType, { label: string; cls: string }> = {
  HOLIDAY: { label: 'Holiday', cls: 'bg-rose-50 text-rose-700' },
  EVENT: { label: 'Event', cls: 'bg-indigo-50 text-indigo-700' },
  ANNOUNCEMENT: { label: 'Announcement', cls: 'bg-amber-50 text-amber-700' },
  ASSIGNMENT_DUE: { label: 'Assignment Due', cls: 'bg-purple-50 text-purple-700' },
  LAB_DUE: { label: 'Lab Due', cls: 'bg-blue-50 text-blue-700' },
  EXAM: { label: 'Exam', cls: 'bg-red-50 text-red-700' },
  VIVA: { label: 'Viva', cls: 'bg-teal-50 text-teal-700' },
}

function fmtISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function startOfDay(d: Date): Date {
  const c = new Date(d)
  c.setHours(0, 0, 0, 0)
  return c
}

function groupLabel(dateStr: string, today: Date): string {
  const d = startOfDay(new Date(dateStr))
  const t = startOfDay(today)
  const diffDays = Math.round((d.getTime() - t.getTime()) / 86400000)
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Tomorrow'
  if (diffDays > 1 && diffDays <= 7) return 'This Week'
  if (diffDays < 0) return 'Past'
  return 'Later'
}

const GROUP_ORDER = ['Today', 'Tomorrow', 'This Week', 'Later', 'Past']

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-56 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-32 rounded bg-gray-100" />
    </div>
  )
}

export default function CalendarPage() {
  const navigate = useNavigate()
  const [rangeOffset, setRangeOffset] = useState(0) // in 60-day windows

  const { dateFrom, dateTo } = useMemo(() => {
    const from = new Date()
    from.setDate(from.getDate() + rangeOffset * 60)
    const to = new Date(from)
    to.setDate(to.getDate() + 60)
    return { dateFrom: fmtISODate(from), dateTo: fmtISODate(to) }
  }, [rangeOffset])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['student-calendar', dateFrom, dateTo],
    queryFn: () => getMyCalendar(dateFrom, dateTo),
  })

  const items = data ?? []

  const grouped = useMemo(() => {
    const today = new Date()
    const groups: Record<string, CalendarItem[]> = {}
    for (const item of items) {
      const g = groupLabel(item.date, today)
      if (!groups[g]) groups[g] = []
      groups[g].push(item)
    }
    for (const g of Object.keys(groups)) {
      groups[g].sort((a, b) => a.date.localeCompare(b.date))
    }
    return groups
  }, [items])

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Academic Calendar</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Assignment &amp; lab deadlines, exams, viva sessions, events and holidays.
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => setRangeOffset((o) => o - 1)}
            className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
            aria-label="Previous range"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setRangeOffset((o) => o + 1)}
            className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
            aria-label="Next range"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your calendar. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3, 4].map((n) => (
            <SkeletonRow key={n} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <CalendarDays className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No upcoming academic events.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {GROUP_ORDER.filter((g) => grouped[g]?.length).map((g) => (
            <section key={g}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">
                {g}
              </h2>
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {grouped[g].map((item) => {
                  const cfg = TYPE_CONFIG[item.item_type] ?? {
                    label: item.item_type,
                    cls: 'bg-gray-50 text-gray-600',
                  }
                  const clickable = !!item.link
                  return (
                    <div
                      key={item.id}
                      onClick={() => item.link && navigate(item.link)}
                      className={`px-5 py-4 flex items-center justify-between gap-4 ${
                        clickable ? 'cursor-pointer hover:bg-gray-50 transition-colors' : ''
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-gray-800 truncate">
                            {item.title}
                          </span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${cfg.cls}`}>
                            {cfg.label}
                          </span>
                        </div>
                        <div className="text-xs text-gray-400 mt-1">
                          {new Date(item.date).toLocaleDateString(undefined, {
                            weekday: 'short',
                            month: 'short',
                            day: 'numeric',
                          })}
                          {!item.all_day && item.start_time && <> · {item.start_time}</>}
                          {!item.all_day && item.end_time && <>–{item.end_time}</>}
                          {item.all_day && <> · All day</>}
                        </div>
                      </div>
                      {item.item_type === 'HOLIDAY' && (
                        <PartyPopper className="h-4 w-4 text-rose-300 shrink-0" />
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
