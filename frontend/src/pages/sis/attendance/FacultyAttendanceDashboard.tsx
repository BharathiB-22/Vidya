import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { CalendarCheck, CheckCircle2, Clock, Plus, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDayClass } from '@/lib/api/sis'
import { ExtraClassDialog } from './ExtraClassDialog'

const DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
// Full month names so the header reads "Wednesday, 15 July 2026" (not "15 Jul 2026").
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function prettyDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${DOW[(date.getDay() + 6) % 7]}, ${d} ${MONTHS[m - 1]} ${y}`
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  const [h, m] = t.split(':')
  return `${Number(h)}:${m}`
}

function timeRange(c: FacultyDayClass): string {
  if (c.start_time && c.end_time) return `${fmtTime(c.start_time)}–${fmtTime(c.end_time)}`
  return c.period_label ?? `Period ${c.period_number}`
}

/**
 * The faculty's attendance home: today's classes as cards, taken from their
 * published timetable. Two taps to attendance — pick a class, mark, save.
 *
 * No course/section pickers, no session list, no "New Session" — the timetable
 * already knows what runs today. A class with attendance already taken shows its
 * result and an Edit action instead of Take Attendance.
 */
export default function FacultyAttendanceDashboard() {
  const navigate = useNavigate()
  const date = todayISO()
  const [extraOpen, setExtraOpen] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['faculty-today', date],
    queryFn: () => sisApi.getFacultyToday(date),
  })

  const classes = data?.today ?? []
  const { pending, done } = useMemo(() => ({
    pending: classes.filter((c) => !c.is_taken),
    done: classes.filter((c) => c.is_taken),
  }), [classes])

  function openTakeAttendance(c: FacultyDayClass) {
    const p = new URLSearchParams({
      course_id: c.course_id,
      semester_id: c.semester_id,
      date,
      title: `${c.course_code} ${c.course_title}`,
      where: c.is_elective ? 'Combined class' : (c.section_name ? `Section ${c.section_name}` : ''),
      when: timeRange(c),
    })
    if (c.section_id) p.set('section_id', c.section_id)
    if (c.period_number != null) p.set('period', String(c.period_number))
    if (c.session_id) p.set('session_id', c.session_id)
    navigate(`/sis/attendance/take?${p.toString()}`)
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Attendance</h1>
          <p className="text-sm text-gray-500 mt-0.5">Mark attendance for today's classes.</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-500">{prettyDate(date)}</span>
          <Button size="sm" variant="outline" onClick={() => setExtraOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Extra Class
          </Button>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load today's classes. Please refresh.
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((n) => <div key={n} className="h-36 rounded-xl bg-gray-50 animate-pulse" />)}
        </div>
      ) : classes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
          <CalendarCheck className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-500">No classes scheduled for today.</p>
          <p className="text-xs text-gray-400 mt-1">
            Classes come from your published timetable. If one is missing, ask your Dean to publish
            the section's timetable.
          </p>
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                To mark ({pending.length})
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {pending.map((c) => (
                  <ClassCard key={cardKey(c)} c={c} onTake={() => openTakeAttendance(c)} />
                ))}
              </div>
            </section>
          )}

          {done.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Completed ({done.length})
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {done.map((c) => (
                  <ClassCard key={cardKey(c)} c={c} onTake={() => openTakeAttendance(c)} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <ExtraClassDialog
        open={extraOpen}
        onOpenChange={setExtraOpen}
        onStart={(p) => { setExtraOpen(false); navigate(`/sis/attendance/take?${p.toString()}`) }}
      />
    </div>
  )
}

function cardKey(c: FacultyDayClass): string {
  return `${c.course_id}:${c.section_id ?? 'elective'}:${c.period_number}`
}

function ClassCard({ c, onTake }: { c: FacultyDayClass; onTake: () => void }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-gray-500">{c.course_code}</span>
            {c.is_elective && (
              <span className="rounded bg-violet-100 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-violet-700">
                Combined
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-gray-900 leading-tight mt-0.5">{c.course_title}</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-gray-500 shrink-0">
          <Clock className="h-3.5 w-3.5" />
          {timeRange(c)}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-500 flex-wrap">
        <span>{c.is_elective ? 'All sections' : (c.section_name ? `Section ${c.section_name}` : '—')}</span>
        <span>·</span>
        <span>{c.semester_label}</span>
        <span className="inline-flex items-center gap-1">
          <Users className="h-3.5 w-3.5" />
          {c.student_count} student{c.student_count === 1 ? '' : 's'}
        </span>
      </div>

      {c.is_taken ? (
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Taken · {c.present_count}/{c.total_marked} present
          </span>
          <Button size="sm" variant="outline" onClick={onTake}>Edit</Button>
        </div>
      ) : (
        <Button size="sm" className="w-full" onClick={onTake}>Take Attendance</Button>
      )}
    </div>
  )
}
