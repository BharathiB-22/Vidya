// Academic Calendar — the student's one view of every dated academic thing.
//
// This merges what used to be two pages. "Calendar" showed deadlines and exams;
// "Events" showed holidays and announcements — from the SAME endpoint, each
// filtering out what the other kept. A student had to know which page a date
// lived on before they could look it up, which is exactly backwards.
//
// One page now, with the month a student is asking about on the left and that
// day's work on the right. Every source the backend aggregates shows up here:
// holidays (government/university), department events, assignment and lab
// deadlines, quizzes, internal assessments, exams, lab exams, project reviews,
// research milestones, and the student's own notes.
//
// Student-only, as it always was.
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, Plus, Trash2, X } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import {
  createMyPersonalEvent,
  deleteMyPersonalEvent,
  getMyCalendar,
  getMyTeachingDays,
  type CalendarItem,
  type CalendarItemType,
} from '@/lib/api/calendar'

/** The kinds that mean "no class today". A day carrying one of these is a
 *  holiday whatever the timetable says. */
const HOLIDAY_TYPES = new Set<CalendarItemType>([
  'HOLIDAY', 'GOVERNMENT_HOLIDAY', 'UNIVERSITY_HOLIDAY',
])

// How each kind of item reads and colours. `dot` paints the month grid; `cls`
// paints the agenda pill.
const TYPE_CONFIG: Record<CalendarItemType, { label: string; cls: string; dot: string }> = {
  HOLIDAY:             { label: 'Holiday',             cls: 'bg-rose-50 text-rose-700',       dot: 'bg-rose-400' },
  GOVERNMENT_HOLIDAY:  { label: 'Government Holiday',  cls: 'bg-rose-50 text-rose-700',       dot: 'bg-rose-400' },
  UNIVERSITY_HOLIDAY:  { label: 'University Holiday',  cls: 'bg-rose-50 text-rose-700',       dot: 'bg-rose-400' },
  EVENT:               { label: 'Event',               cls: 'bg-indigo-50 text-indigo-700',   dot: 'bg-indigo-400' },
  DEPARTMENT_EVENT:    { label: 'Department Event',    cls: 'bg-indigo-50 text-indigo-700',   dot: 'bg-indigo-400' },
  ANNOUNCEMENT:        { label: 'Announcement',        cls: 'bg-amber-50 text-amber-700',     dot: 'bg-amber-400' },
  INTERNAL_ASSESSMENT: { label: 'Internal Assessment', cls: 'bg-orange-50 text-orange-700',   dot: 'bg-orange-400' },
  QUIZ:                { label: 'Quiz',                cls: 'bg-orange-50 text-orange-700',   dot: 'bg-orange-400' },
  LAB_EXAM:            { label: 'Lab Exam',            cls: 'bg-red-50 text-red-700',         dot: 'bg-red-400' },
  PROJECT_REVIEW:      { label: 'Project Review',      cls: 'bg-cyan-50 text-cyan-700',       dot: 'bg-cyan-400' },
  RESEARCH_MILESTONE:  { label: 'Research Milestone',  cls: 'bg-teal-50 text-teal-700',       dot: 'bg-teal-400' },
  SUBMISSION_DEADLINE: { label: 'Submission Deadline', cls: 'bg-purple-50 text-purple-700',   dot: 'bg-purple-400' },
  PERSONAL:            { label: 'Personal',            cls: 'bg-slate-100 text-slate-700',    dot: 'bg-slate-400' },
  OTHER:               { label: 'Other',               cls: 'bg-gray-50 text-gray-600',       dot: 'bg-gray-400' },
  ASSIGNMENT_DUE:      { label: 'Assignment Due',      cls: 'bg-purple-50 text-purple-700',   dot: 'bg-purple-400' },
  LAB_DUE:             { label: 'Lab Due',             cls: 'bg-blue-50 text-blue-700',       dot: 'bg-blue-400' },
  EXAM:                { label: 'Exam',                cls: 'bg-red-50 text-red-700',         dot: 'bg-red-400' },
  VIVA:                { label: 'Viva',                cls: 'bg-teal-50 text-teal-700',       dot: 'bg-teal-400' },
}

function cfgFor(t: CalendarItemType) {
  return TYPE_CONFIG[t] ?? { label: String(t).replace(/_/g, ' '), cls: 'bg-gray-50 text-gray-600', dot: 'bg-gray-400' }
}

// Anything with a deadline or a seat is "work"; the rest is context. This is the
// only grouping a student actually acts on.
const PENDING_TYPES = new Set<CalendarItemType>([
  'ASSIGNMENT_DUE', 'LAB_DUE', 'EXAM', 'VIVA', 'QUIZ', 'INTERNAL_ASSESSMENT',
  'LAB_EXAM', 'PROJECT_REVIEW', 'RESEARCH_MILESTONE', 'SUBMISSION_DEADLINE',
])

/** Local YYYY-MM-DD. Never toISOString(), which shifts the day across a UTC
 *  boundary and lands a deadline on the wrong date. */
function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function sameDay(a: Date, b: Date): boolean {
  return isoDate(a) === isoDate(b)
}

/** The 6x7 grid a month is drawn on, Monday-first, including the neighbouring
 *  days that fill the corners. */
function monthGrid(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function fmtTime(t: string | null): string | null {
  if (!t) return null
  const [h, m] = t.split(':')
  const hh = Number(h)
  const suffix = hh >= 12 ? 'pm' : 'am'
  const h12 = hh % 12 === 0 ? 12 : hh % 12
  return `${h12}:${m}${suffix}`
}

export default function CalendarPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const today = useMemo(() => new Date(), [])
  const [month, setMonth] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1))
  const [selected, setSelected] = useState<Date>(today)
  const [adding, setAdding] = useState(false)

  // Fetch the whole visible grid, not just the month — the corner days belong to
  // the neighbouring months and would otherwise render as empty.
  const { dateFrom, dateTo } = useMemo(() => {
    const grid = monthGrid(month)
    return { dateFrom: isoDate(grid[0]), dateTo: isoDate(grid[grid.length - 1]) }
  }, [month])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['student-calendar', dateFrom, dateTo],
    queryFn: () => getMyCalendar(dateFrom, dateTo),
  })

  // Saturday is not a holiday by decree — it depends on whether THIS student has
  // Saturday classes. Read their timetable rather than assuming.
  const { data: teachingDays } = useQuery({
    queryKey: ['student-teaching-days'],
    queryFn: getMyTeachingDays,
    staleTime: 30 * 60 * 1000,
  })

  const items = data ?? []

  const byDate = useMemo(() => {
    const m = new Map<string, CalendarItem[]>()
    for (const i of items) m.set(i.date, [...(m.get(i.date) ?? []), i])
    return m
  }, [items])

  const selectedItems = byDate.get(isoDate(selected)) ?? []

  /** Why a day is off, or null when it is a normal working day.
   *
   *  Sunday is always off. Saturday only when the student's own timetable has no
   *  Saturday class — a student WITH Saturday classes must never see it marked as
   *  a holiday. A declared holiday beats the timetable either way. */
  function nonTeaching(d: Date): 'SUNDAY' | 'HOLIDAY' | 'NO_CLASS' | null {
    const dow = (d.getDay() + 6) % 7      // 0=Monday .. 6=Sunday
    if (dow === 6) return 'SUNDAY'
    if ((byDate.get(isoDate(d)) ?? []).some(i => HOLIDAY_TYPES.has(i.item_type))) {
      return 'HOLIDAY'
    }
    // Until the timetable loads, assume nothing rather than grey out Saturday.
    if (teachingDays && !teachingDays.includes(dow)) return 'NO_CLASS'
    return null
  }

  const selectedOff = nonTeaching(selected)

  // What is still ahead of them, so the calendar answers "what do I owe?"
  // without the student having to click through each day to find out.
  const upcoming = useMemo(
    () => items
      .filter(i => PENDING_TYPES.has(i.item_type) && i.date >= isoDate(today))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 5),
    [items, today],
  )

  const remove = useMutation({
    mutationFn: deleteMyPersonalEvent,
    onSuccess: () => {
      addToast('Removed from your calendar.', 'success')
      qc.invalidateQueries({ queryKey: ['student-calendar'] })
    },
    onError: (err) => addToast(getErrorMessage(err), 'error'),
  })

  const grid = monthGrid(month)

  return (
    <PageShell>
      <PageHeader
        icon={CalendarDays}
        title="Academic Calendar"
        subtitle="Holidays, events, deadlines, exams and your own notes — everything on its date."
      />

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load your calendar. Please refresh.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_22rem] gap-6 items-start">
        {/* Month */}
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-800">
              {month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
            </h2>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setMonth(m => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
                aria-label="Previous month"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => { setMonth(new Date(today.getFullYear(), today.getMonth(), 1)); setSelected(today) }}
                className="px-2.5 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-xs text-gray-600"
              >
                Today
              </button>
              <button
                type="button"
                onClick={() => setMonth(m => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
                aria-label="Next month"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-7 border-b border-gray-100">
            {WEEKDAYS.map((d, i) => (
              <div
                key={d}
                className={`py-2 text-center text-[11px] font-medium uppercase tracking-wide ${
                  i === 6 ? 'text-red-500' : 'text-gray-600'
                }`}
              >
                {d}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7">
            {grid.map((d, i) => {
              const dayItems = byDate.get(isoDate(d)) ?? []
              const inMonth = d.getMonth() === month.getMonth()
              const isToday = sameDay(d, today)
              const isSelected = sameDay(d, selected)
              const off = nonTeaching(d)
              // Sundays and declared holidays read red; a Saturday the student
              // simply has no class on is merely greyed — it is not a holiday,
              // and calling it one would be a claim the timetable cannot support.
              const isRed = off === 'SUNDAY' || off === 'HOLIDAY'
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelected(new Date(d))}
                  title={
                    off === 'SUNDAY' ? 'Sunday'
                    : off === 'HOLIDAY' ? 'Holiday'
                    : off === 'NO_CLASS' ? 'No scheduled classes'
                    : undefined
                  }
                  className={`min-h-[4.5rem] border-b border-r border-gray-100 p-1.5 text-left align-top transition-colors ${
                    isSelected ? 'bg-indigo-50 ring-1 ring-inset ring-indigo-300'
                    : isRed ? 'bg-red-50/60 hover:bg-red-50'
                    : off === 'NO_CLASS' ? 'bg-gray-50/70 hover:bg-gray-100/70'
                    : 'hover:bg-gray-50'
                  } ${inMonth ? '' : 'opacity-40'}`}
                >
                  <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                    isToday ? 'bg-indigo-600 text-white font-semibold'
                            : isRed ? 'text-red-600 font-semibold'
                            : inMonth ? 'text-gray-700' : 'text-gray-600'
                  }`}>
                    {d.getDate()}
                  </span>
                  <div className="mt-1 flex flex-wrap gap-0.5">
                    {dayItems.slice(0, 4).map(it => (
                      <span
                        key={it.id}
                        title={it.title}
                        className={`h-1.5 w-1.5 rounded-full ${cfgFor(it.item_type).dot}`}
                      />
                    ))}
                    {dayItems.length > 4 && (
                      <span className="text-[9px] leading-none text-gray-600">+{dayItems.length - 4}</span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* The selected day, and what's coming */}
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-800">
                {selected.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}
              </h2>
              <Button
                type="button" variant="ghost" size="sm"
                className="text-indigo-600 h-7"
                onClick={() => setAdding(true)}
              >
                <Plus className="h-3.5 w-3.5 mr-1" /> Add
              </Button>
            </div>

            {/* Why this day is off, said once at the top rather than repeated on
                every row. A NO_CLASS Saturday says exactly that and not
                "holiday". */}
            {selectedOff && (
              <p className={`px-4 py-2 text-xs border-b ${
                selectedOff === 'NO_CLASS'
                  ? 'bg-gray-50 border-gray-100 text-gray-500'
                  : 'bg-red-50 border-red-100 text-red-700 font-medium'
              }`}>
                {selectedOff === 'SUNDAY' ? 'Sunday — no classes.'
                  : selectedOff === 'HOLIDAY' ? 'Holiday — no classes.'
                  : 'No classes scheduled on this day.'}
              </p>
            )}

            {isLoading ? (
              <div className="px-4 py-6 space-y-3 animate-pulse">
                <div className="h-4 w-40 rounded bg-gray-200" />
                <div className="h-4 w-28 rounded bg-gray-100" />
              </div>
            ) : selectedItems.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-gray-600">Nothing on this day.</p>
            ) : (
              <div className="divide-y divide-gray-100">
                {selectedItems.map(item => {
                  const cfg = cfgFor(item.item_type)
                  return (
                    <div
                      key={item.id}
                      className={`px-4 py-3 flex items-start justify-between gap-3 ${
                        item.link ? 'cursor-pointer hover:bg-gray-50 transition-colors' : ''
                      }`}
                      onClick={() => item.link && navigate(item.link)}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-gray-800">{item.title}</span>
                          <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium shrink-0 ${cfg.cls}`}>
                            {cfg.label}
                          </span>
                        </div>
                        <p className="text-xs text-gray-600 mt-0.5">
                          {item.detail && <>{item.detail} · </>}
                          {item.all_day
                            ? 'All day'
                            : [fmtTime(item.start_time), fmtTime(item.end_time)].filter(Boolean).join('–') || 'All day'}
                        </p>
                      </div>
                      {item.editable && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); remove.mutate(item.id) }}
                          className="text-gray-500 hover:text-red-500 transition-colors shrink-0"
                          aria-label="Remove personal event"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {upcoming.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <h2 className="px-4 py-3 border-b border-gray-100 text-sm font-semibold text-gray-800">
                Pending
              </h2>
              <div className="divide-y divide-gray-100">
                {upcoming.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      const d = new Date(`${item.date}T00:00:00`)
                      setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
                      setSelected(d)
                    }}
                    className="w-full px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-gray-50 transition-colors text-left"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-gray-700 truncate">{item.title}</p>
                      <p className="text-[11px] text-gray-600">{cfgFor(item.item_type).label}</p>
                    </div>
                    <span className="text-xs text-gray-600 shrink-0">
                      {new Date(`${item.date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {adding && (
        <AddPersonalEventDialog
          date={selected}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false)
            qc.invalidateQueries({ queryKey: ['student-calendar'] })
          }}
        />
      )}
    </PageShell>
  )
}

/** A student's own note. Only a title, a date and an optional time — anything
 *  more and it starts pretending to be a thing the institution declared. */
function AddPersonalEventDialog({
  date, onClose, onSaved,
}: { date: Date; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [time, setTime] = useState('')

  const save = useMutation({
    mutationFn: () => {
      const startAt = new Date(date)
      if (time) {
        const [h, m] = time.split(':')
        startAt.setHours(Number(h), Number(m), 0, 0)
      } else {
        startAt.setHours(0, 0, 0, 0)
      }
      return createMyPersonalEvent({
        title: title.trim(),
        description: description.trim() || null,
        start_at: startAt.toISOString(),
        is_all_day: !time,
      })
    },
    onSuccess: () => {
      addToast('Added to your calendar.', 'success')
      onSaved()
    },
    onError: (err) => addToast(getErrorMessage(err), 'error'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white shadow-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">
            Add to {date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </h3>
          <button type="button" onClick={onClose} className="text-gray-600 hover:text-gray-600" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form
          className="p-4 space-y-3"
          onSubmit={(e) => { e.preventDefault(); if (title.trim()) save.mutate() }}
        >
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Title</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Revise Unit 3"
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Time (optional)</label>
            <input
              type="time"
              value={time}
              onChange={e => setTime(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <p className="text-[11px] text-gray-600">Leave blank for an all-day note.</p>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Note (optional)</label>
            <textarea
              rows={2}
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <p className="text-[11px] text-gray-600">Only you can see this.</p>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button type="submit" size="sm" disabled={save.isPending || !title.trim()}>
              {save.isPending ? 'Adding…' : 'Add'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
