import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { assignmentsApi } from '@/lib/api/assignments'
import { DAYS_OF_WEEK, type TimetableSlot } from '@/types/timetable'

export interface SlotDraft {
  course_id: string
  faculty_user_id?: string
  room?: string
  remarks?: string
}

/** Adds a new entry, or edits an existing one in place.
 *
 *  On edit the subject is fixed: swapping one course for another is a different
 *  class, not an edit, and is expressed as delete-then-add. What the Dean can
 *  change here is who teaches it, where, and why — which is exactly the
 *  "change rooms / change faculty" half of the human-in-the-loop workflow.
 *
 *  The course list comes from `listCoursesForSlot`, which returns published
 *  curriculum only, so no subject can be typed in by hand. */
export function SlotDialog({
  open,
  onOpenChange,
  semesterId,
  sectionId,
  dayOfWeek,
  periodNumber,
  editing,
  onSubmit,
  isSubmitting,
  error,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  semesterId: string
  sectionId: string
  dayOfWeek: number | null
  periodNumber: number | null
  /** Present when editing an existing entry. */
  editing?: TimetableSlot | null
  onSubmit: (payload: SlotDraft) => void
  isSubmitting: boolean
  error: string | null
}) {
  const isEdit = !!editing

  const [courseId, setCourseId] = useState('')
  const [facultyUserId, setFacultyUserId] = useState('')
  const [room, setRoom] = useState('')
  const [remarks, setRemarks] = useState('')

  // Seed from the entry being edited, and reset between openings so a previous
  // slot's room never leaks into the next one.
  useEffect(() => {
    if (!open) return
    setCourseId(editing?.course_id ?? '')
    setFacultyUserId(editing?.faculty_user_id ?? '')
    setRoom(editing?.room ?? '')
    setRemarks(editing?.remarks ?? '')
  }, [open, editing])

  const coursesQ = useQuery({
    queryKey: ['courses-for-slot', semesterId, sectionId],
    queryFn: () => assignmentsApi.listCoursesForSlot(semesterId, sectionId),
    enabled: open,
  })

  const courses = coursesQ.data ?? []
  const selectedCourse = courses.find((c) => c.course_id === courseId)
  const facultyForCourse = selectedCourse?.assignments ?? []
  const needsFacultyPicker = facultyForCourse.length > 1

  function handleCourseChange(id: string) {
    setCourseId(id)
    const options = courses.find((c) => c.course_id === id)?.assignments ?? []
    setFacultyUserId(options.length === 1 ? (options[0].faculty_user_id ?? '') : '')
  }

  const resolvedFacultyName = facultyForCourse.length === 1
    ? (facultyForCourse[0].faculty?.full_name ?? 'Unassigned faculty')
    : null

  const canSubmit = !!courseId && (!needsFacultyPicker || !!facultyUserId)
  const where = `${dayOfWeek != null ? DAYS_OF_WEEK[dayOfWeek] : ''} · Period ${periodNumber}`

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${editing.course_code}` : 'Add subject'} — {where}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Subject</label>
            {isEdit ? (
              <p className="text-sm text-gray-900 px-3 py-2 rounded-md border border-gray-200 bg-gray-50">
                {editing.course_code} — {editing.course_title}
              </p>
            ) : (
              <Select value={courseId} onValueChange={handleCourseChange}>
                <SelectTrigger>
                  <SelectValue placeholder={coursesQ.isLoading ? 'Loading…' : 'Select a subject'} />
                </SelectTrigger>
                <SelectContent>
                  {courses.map((c) => (
                    <SelectItem key={c.course_id} value={c.course_id}>
                      {c.code} — {c.title}{c.is_elective ? ' (elective)' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {isEdit && (
              <p className="text-xs text-gray-500 mt-1">
                To teach a different subject here, delete this entry and add the new one.
              </p>
            )}
            {!isEdit && !coursesQ.isLoading && courses.length === 0 && (
              <p className="text-xs text-gray-500 mt-1">
                No published subjects for this semester. Publish the programme first.
              </p>
            )}
          </div>

          {needsFacultyPicker ? (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Faculty</label>
              <Select value={facultyUserId} onValueChange={setFacultyUserId}>
                <SelectTrigger><SelectValue placeholder="Multiple faculty teach this subject — pick one" /></SelectTrigger>
                <SelectContent>
                  {facultyForCourse.map((a) => (
                    <SelectItem key={a.id} value={a.faculty_user_id ?? ''}>
                      {a.faculty?.full_name ?? 'Unassigned faculty'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : resolvedFacultyName ? (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Faculty</label>
              <p className="text-sm text-gray-900 px-3 py-2 rounded-md border border-gray-200 bg-gray-50">
                {resolvedFacultyName}
              </p>
            </div>
          ) : courseId ? (
            <p className="text-xs text-gray-500">
              No faculty assigned to this subject yet — the entry can still be saved without one.
            </p>
          ) : null}

          <div>
            <label className="block text-xs text-gray-500 mb-1">Room / Lab (optional)</label>
            <Input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="e.g. Block A, Room 204" />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Remarks (optional)</label>
            <Input value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="e.g. Tutorial, Guest lecture" />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={!canSubmit || isSubmitting}
            onClick={() => {
              if (!courseId) return
              onSubmit({
                course_id: courseId,
                faculty_user_id: facultyUserId || undefined,
                room: room || undefined,
                remarks: remarks || undefined,
              })
            }}
          >
            {isSubmitting ? 'Saving…' : isEdit ? 'Save changes' : 'Add subject'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
