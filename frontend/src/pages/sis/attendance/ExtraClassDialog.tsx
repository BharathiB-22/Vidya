import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { assignmentsApi } from '@/lib/api/assignments'
import { academicsApi } from '@/lib/api/academics'

function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * The escape hatch for classes that are not on the timetable — a makeup class,
 * an extra lecture, a session held off-schedule.
 *
 * A timetable-driven dashboard can only show scheduled classes, so without this
 * a makeup class simply could not be marked. The faculty picks one of their own
 * assigned courses, a section and period, and the same take-attendance screen
 * opens. Nothing here bypasses assignment: the course list is the caller's own
 * `/course-assignments/mine`.
 */
export function ExtraClassDialog({
  open, onOpenChange, onStart,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  /** Called with the take-attendance query params once the class is chosen. */
  onStart: (params: URLSearchParams) => void
}) {
  const [courseId, setCourseId] = useState('')
  const [sectionId, setSectionId] = useState('')
  const [period, setPeriod] = useState('1')
  const [date, setDate] = useState(todayISO())

  const assignmentsQ = useQuery({
    queryKey: ['my-assignments-extra'],
    queryFn: () => assignmentsApi.listMine(),
    enabled: open,
  })

  // One row per (course, semester) the faculty actively teaches.
  const courses = useMemo(() => {
    const seen = new Map<string, { course_id: string; semester_id: string; label: string }>()
    for (const a of assignmentsQ.data?.items ?? []) {
      if (!a.is_active || !a.course) continue
      const key = `${a.course_id}:${a.semester_id}`
      if (!seen.has(key)) {
        seen.set(key, {
          course_id: a.course_id,
          semester_id: a.semester_id,
          label: `${a.course.code} — ${a.course.title}`,
        })
      }
    }
    return [...seen.values()]
  }, [assignmentsQ.data])

  const chosen = courses.find((c) => c.course_id === courseId)

  const sectionsQ = useQuery({
    queryKey: ['sections-for-extra', chosen?.semester_id],
    queryFn: () => academicsApi.listSections(chosen!.semester_id),
    enabled: open && !!chosen,
  })
  const sections = sectionsQ.data ?? []

  const canStart = !!chosen && !!sectionId && !!date && Number(period) >= 1

  function start() {
    if (!chosen) return
    const p = new URLSearchParams({
      course_id: chosen.course_id,
      semester_id: chosen.semester_id,
      section_id: sectionId,
      period,
      date,
      title: chosen.label,
      where: `Section ${sections.find((s) => s.id === sectionId)?.name ?? ''}`,
      when: `Extra class · Period ${period}`,
    })
    onStart(p)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Extra class</DialogTitle></DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            For a class not on your timetable — a makeup or extra lecture. Only subjects you teach
            appear here.
          </p>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Subject</label>
            <Select value={courseId} onValueChange={(v) => { setCourseId(v); setSectionId('') }}>
              <SelectTrigger>
                <SelectValue placeholder={assignmentsQ.isLoading ? 'Loading…' : 'Select a subject'} />
              </SelectTrigger>
              <SelectContent>
                {courses.map((c) => (
                  <SelectItem key={`${c.course_id}:${c.semester_id}`} value={c.course_id}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Section</label>
              <Select value={sectionId} onValueChange={setSectionId} disabled={!chosen}>
                <SelectTrigger><SelectValue placeholder="Section" /></SelectTrigger>
                <SelectContent>
                  {sections.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Period</label>
              <Input type="number" min={1} max={12} value={period}
                onChange={(e) => setPeriod(e.target.value)} />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Date</label>
            {/* Past dates are unrestricted — an extra class may be recorded long
                after it was held. `max` mirrors the server's one hard rule: a
                class that has not happened yet cannot have a register. */}
            <Input
              type="date"
              value={date}
              max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canStart} onClick={start}>Take Attendance</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
