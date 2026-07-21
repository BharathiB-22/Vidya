import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Check, ChevronLeft, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { sisApi } from '@/lib/api/sis'
import type { AttendanceMarkEntry, AttendanceRecordOut } from '@/lib/api/sis'
import { getErrorMessage } from '@/lib/api'

type Status = 'PRESENT' | 'ABSENT'

/**
 * The two-tap take-attendance screen: a plain list of students, each Present or
 * Absent, one Save.
 *
 * The class comes as query params from a dashboard card. A session is created
 * once (seeding the roster) and its records loaded; a brand-new session shows
 * everyone Present by default because marking the few absentees is the fast
 * path, while an already-taken class loads its saved values for editing.
 *
 * There is deliberately no session lifecycle here — no lock button, no window
 * countdown, no percentages. Those still exist server-side (attendance is an
 * auditable record) but never surface to the faculty mid-flow.
 */
export default function TakeAttendancePage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const courseId = params.get('course_id') ?? ''
  const sectionId = params.get('section_id') || undefined      // absent for electives
  const semesterId = params.get('semester_id') ?? ''
  const period = params.get('period') ? Number(params.get('period')) : undefined
  const date = params.get('date') ?? ''
  const existingSessionId = params.get('session_id') || undefined
  const title = params.get('title') ?? 'Attendance'
  const where = params.get('where') ?? ''
  const when = params.get('when') ?? ''

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<Record<string, Status>>({})
  const [error, setError] = useState<string | null>(null)

  // Resolve the session: open the existing one, or create it (which seeds the
  // roster as ABSENT — the UI overrides the default to Present locally).
  const sessionQ = useQuery({
    queryKey: ['take-attendance-session', courseId, sectionId ?? semesterId, period, date],
    queryFn: async () => {
      if (existingSessionId) return { id: existingSessionId, isNew: false }
      const s = await sisApi.createAttendanceSession({
        course_id: courseId,
        section_id: sectionId,
        semester_id: sectionId ? undefined : semesterId,
        session_date: date,
        period_number: period,
      })
      return { id: s.id, isNew: s.first_marked_at === null }
    },
    enabled: !!courseId && !!date,
  })

  const sessionId = sessionQ.data?.id
  const isFresh = sessionQ.data?.isNew ?? false

  const recordsQ = useQuery({
    queryKey: ['session-records', sessionId],
    queryFn: () => sisApi.getSessionRecords(sessionId as string),
    enabled: !!sessionId,
  })

  const records = recordsQ.data ?? []
  const isFirstMark = isFresh || records.every((r) => r.marked_at === null)

  // Effective status: local override, else the server value, else Present for a
  // fresh class (the default that lets a full class be saved in one tap).
  function statusOf(r: AttendanceRecordOut): Status {
    if (status[r.student_id]) return status[r.student_id]
    if (isFirstMark) return 'PRESENT'
    return r.status
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return records
    return records.filter(
      (r) => r.student_name.toLowerCase().includes(q) || (r.usn ?? '').toLowerCase().includes(q),
    )
  }, [records, search])

  const presentCount = records.filter((r) => statusOf(r) === 'PRESENT').length
  const absentCount = records.length - presentCount

  function set(studentId: string, s: Status) {
    setStatus((prev) => ({ ...prev, [studentId]: s }))
  }
  function presentAll() {
    setStatus(Object.fromEntries(records.map((r) => [r.student_id, 'PRESENT' as Status])))
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const entries: AttendanceMarkEntry[] = records.map((r) => ({
        student_id: r.student_id,
        status: statusOf(r),
      }))
      return sisApi.markAttendance(sessionId as string, { records: entries })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['faculty-today'] })
      navigate('/sis/attendance')
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const loading = sessionQ.isLoading || recordsQ.isLoading

  return (
    <div className="w-full max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-4">
      <button
        onClick={() => navigate('/sis/attendance')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ChevronLeft className="h-4 w-4" /> Back to today's classes
      </button>

      <div>
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        <p className="text-sm text-gray-500">
          {[where, when].filter(Boolean).join(' · ')}
          {records.length > 0 && ` · ${records.length} students`}
        </p>
      </div>

      {(sessionQ.isError || error) && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error ?? 'Could not open this class for attendance.'}
        </div>
      )}

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search student by name or USN…"
            className="pl-8"
          />
        </div>
        <Button variant="outline" onClick={presentAll} disabled={loading || records.length === 0}>
          <Check className="h-4 w-4 mr-1" /> Present All
        </Button>
      </div>

      {loading ? (
        <div className="h-64 rounded-xl bg-gray-50 animate-pulse" />
      ) : records.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center text-sm text-gray-500">
          No students in this class.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2.5 text-left font-semibold w-32">USN</th>
                <th className="px-4 py-2.5 text-left font-semibold">Name</th>
                <th className="px-4 py-2.5 text-center font-semibold w-40">Attendance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((r) => {
                const s = statusOf(r)
                return (
                  <tr key={r.student_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.usn ?? '—'}</td>
                    <td className="px-4 py-2.5 text-gray-900">{r.student_name}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-center gap-1">
                        <ToggleButton active={s === 'PRESENT'} tone="present"
                          onClick={() => set(r.student_id, 'PRESENT')}>Present</ToggleButton>
                        <ToggleButton active={s === 'ABSENT'} tone="absent"
                          onClick={() => set(r.student_id, 'ABSENT')}>Absent</ToggleButton>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {records.length > 0 && (
        <div className="sticky bottom-0 flex items-center justify-between gap-4 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
          <span className="text-sm text-gray-600">
            <strong className="text-emerald-700">{presentCount} present</strong>
            {' · '}
            <strong className="text-gray-700">{absentCount} absent</strong>
          </span>
          <Button disabled={saveMut.isPending} onClick={() => saveMut.mutate()}>
            {saveMut.isPending ? 'Saving…' : 'Save Attendance'}
          </Button>
        </div>
      )}
    </div>
  )
}

function ToggleButton({
  active, tone, onClick, children,
}: {
  active: boolean
  tone: 'present' | 'absent'
  onClick: () => void
  children: React.ReactNode
}) {
  const activeCls =
    tone === 'present'
      ? 'bg-emerald-600 text-white border-emerald-600'
      : 'bg-red-500 text-white border-red-500'
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
        active ? activeCls : 'border-gray-200 text-gray-500 hover:bg-gray-100'
      }`}
    >
      {children}
    </button>
  )
}
