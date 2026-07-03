import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardCheck, Plus, Lock, Clock, CheckCircle2, AlertTriangle,
  ChevronRight, RefreshCw, Users,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type {
  AttendanceSessionOut, AttendanceRecordOut, AttendanceMarkEntry,
} from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useQuery as useAssignmentQuery } from '@tanstack/react-query'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(present: number, absent: number): string {
  const total = present + absent
  if (total === 0) return '—'
  return `${Math.round((present / total) * 100)}%`
}

function StatusBadge({ session }: { session: AttendanceSessionOut }) {
  if (session.status === 'LOCKED') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-gray-300 bg-gray-100 text-gray-700">
        <Lock size={10} /> Locked
      </span>
    )
  }
  if (!session.is_editable) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-800">
        <Clock size={10} /> Window closed
      </span>
    )
  }
  if (session.first_marked_at === null) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-red-300 bg-red-50 text-red-700">
        <AlertTriangle size={10} /> Pending
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-green-300 bg-green-50 text-green-700">
      <CheckCircle2 size={10} /> Open
    </span>
  )
}

// ---------------------------------------------------------------------------
// New Session Modal
// ---------------------------------------------------------------------------

function NewSessionModal({
  courseId, sectionId, onClose, onSaved,
}: { courseId: string; sectionId: string; onClose: () => void; onSaved: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [period, setPeriod] = useState('')
  const [topic, setTopic] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => sisApi.createAttendanceSession({
      course_id: courseId,
      section_id: sectionId,
      session_date: date,
      period_number: period ? parseInt(period) : undefined,
      topic_covered: topic || undefined,
    }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail?.message ?? 'Failed to create session.'),
  })

  const inputClass = "w-full rounded-lg px-3 py-2 text-sm text-foreground border border-gray-300 bg-white outline-none focus:ring-2 focus:ring-blue-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-2xl p-6 space-y-4 bg-white border border-gray-200 shadow-xl">
        <h3 className="text-base font-semibold text-foreground">New Attendance Session</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">Date *</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">Period (optional)</label>
            <input type="number" min={1} max={20} placeholder="e.g. 2" value={period}
              onChange={e => setPeriod(e.target.value)}
              className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">Topic covered (optional)</label>
            <input type="text" placeholder="e.g. Linked Lists" value={topic}
              onChange={e => setTopic(e.target.value)}
              className={inputClass} />
          </div>
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button variant="ghost" onClick={onClose} className="flex-1">Cancel</Button>
          <Button onClick={() => create.mutate()} disabled={!date || create.isPending} className="flex-1">
            {create.isPending ? 'Creating…' : 'Create Session'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mark Attendance Modal
// ---------------------------------------------------------------------------

type StatusToggle = 'PRESENT' | 'ABSENT'
const STATUS_COLORS: Record<StatusToggle, { bg: string; text: string; border: string }> = {
  PRESENT: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-400' },
  ABSENT:  { bg: 'bg-red-100',   text: 'text-red-800',   border: 'border-red-400' },
}
const ALL_STATUSES: StatusToggle[] = ['PRESENT', 'ABSENT']

function MarkModal({
  session, onClose, onSaved,
}: { session: AttendanceSessionOut; onClose: () => void; onSaved: () => void }) {
  const qc = useQueryClient()
  const isFirstMark = session.first_marked_at === null

  const { data: records = [], isLoading } = useQuery({
    queryKey: ['session-records', session.id],
    queryFn: () => sisApi.getSessionRecords(session.id),
  })

  const [localStatus, setLocalStatus] = useState<Record<string, StatusToggle>>({})
  const [localRemarks, setLocalRemarks] = useState<Record<string, string>>({})
  const [editReason, setEditReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const effectiveStatus = (r: AttendanceRecordOut): StatusToggle =>
    (localStatus[r.student_id] ?? r.status) as StatusToggle

  const markMut = useMutation({
    mutationFn: () => {
      const entries: AttendanceMarkEntry[] = records.map(r => ({
        student_id: r.student_id,
        status: effectiveStatus(r),
        remarks: localRemarks[r.student_id] ?? r.remarks ?? undefined,
      }))
      return sisApi.markAttendance(session.id, {
        records: entries,
        edit_reason: isFirstMark ? undefined : editReason || undefined,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendance-sessions'] })
      qc.invalidateQueries({ queryKey: ['session-records', session.id] })
      onSaved(); onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail?.message ?? 'Save failed.'),
  })

  function markAll(status: StatusToggle) {
    const patch: Record<string, StatusToggle> = {}
    records.forEach(r => { patch[r.student_id] = status })
    setLocalStatus(prev => ({ ...prev, ...patch }))
  }

  const present = records.filter(r => effectiveStatus(r) === 'PRESENT').length
  const absent  = records.filter(r => effectiveStatus(r) === 'ABSENT').length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-3xl rounded-2xl flex flex-col max-h-[90vh] bg-white border border-gray-200 shadow-xl">
        {/* Header */}
        <div className="p-5 border-b border-gray-200">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h3 className="text-base font-semibold text-foreground">
                {session.course_code} / {session.section_name} / {session.session_date}
                {session.period_number ? ` · Period ${session.period_number}` : ''}
              </h3>
              {session.topic_covered && (
                <p className="text-xs text-muted-foreground mt-0.5">{session.topic_covered}</p>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-green-700 font-semibold">{present}P</span>
              <span className="text-red-700 font-semibold">{absent}A</span>
              <span className="text-foreground font-semibold">{pct(present, absent)}</span>
              {session.minutes_until_lock !== null && (
                <span className="text-blue-700 font-medium">
                  <Clock size={11} className="inline" /> {Math.floor(session.minutes_until_lock / 60)}h{session.minutes_until_lock % 60}m left
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            {(['PRESENT', 'ABSENT'] as StatusToggle[]).map(s => (
              <button key={s} onClick={() => markAll(s)}
                className={`text-xs px-3 py-1 rounded-lg font-medium border transition-all hover:scale-105 ${STATUS_COLORS[s].bg} ${STATUS_COLORS[s].text} ${STATUS_COLORS[s].border}`}>
                All {s}
              </button>
            ))}
          </div>
        </div>

        {/* Records */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">Loading students…</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {['USN', 'Name', 'Status', 'Remarks'].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold text-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map(r => {
                  const cur = effectiveStatus(r)
                  const sc  = STATUS_COLORS[cur]
                  return (
                    <tr key={r.student_id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-2.5 text-xs font-mono font-medium text-foreground">{r.usn ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs font-medium text-foreground">{r.student_name}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex gap-1">
                          {ALL_STATUSES.map(s => (
                            <button key={s} onClick={() => setLocalStatus(p => ({ ...p, [r.student_id]: s }))}
                              className={cur === s
                                ? `text-xs px-2 py-0.5 rounded font-semibold border transition-all ${sc.bg} ${sc.text} ${sc.border}`
                                : 'text-xs px-2 py-0.5 rounded font-semibold border border-gray-300 bg-gray-100 text-gray-600 transition-all'}>
                              {s[0]}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <input
                          type="text"
                          placeholder="Optional note"
                          value={localRemarks[r.student_id] ?? r.remarks ?? ''}
                          onChange={e => setLocalRemarks(p => ({ ...p, [r.student_id]: e.target.value }))}
                          className="w-full text-xs rounded px-2 py-1 text-foreground border border-gray-300 bg-white outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 space-y-3">
          {!isFirstMark && (
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Edit reason <span className="text-red-600">*</span>
                <span className="text-muted-foreground ml-1">(required — attendance already saved)</span>
              </label>
              <input type="text" placeholder="Reason for editing attendance…"
                value={editReason} onChange={e => setEditReason(e.target.value)}
                className="w-full text-sm rounded-lg px-3 py-2 text-foreground border border-gray-300 bg-white outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} className="flex-1">Cancel</Button>
            <Button
              onClick={() => markMut.mutate()}
              disabled={(!isFirstMark && !editReason.trim()) || markMut.isPending}
              className="flex-1">
              {markMut.isPending ? <><RefreshCw size={14} className="animate-spin mr-2" />Saving…</> : 'Save Attendance'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AttendanceMarkPage() {
  const [selectedCourseId, setSelectedCourseId] = useState('')
  const [selectedSemesterId, setSelectedSemesterId] = useState('')
  const [selectedSectionId, setSelectedSectionId] = useState('')
  const [selectedAssignmentId, setSelectedAssignmentId] = useState('')
  const [showNewSession, setShowNewSession] = useState(false)
  const [markSession, setMarkSession] = useState<AttendanceSessionOut | null>(null)
  const qc = useQueryClient()

  // Faculty assignments → course + semester options
  const { data: assignments } = useAssignmentQuery({
    queryKey: ['my-assignments'],
    queryFn: async () => {
      const r = await (await import('@/lib/api')).default.get('/course-assignments/mine')
      return r.data
    },
  })

  const items: any[] = assignments?.items ?? []

  // Sections for selected semester
  const { data: sections = [] } = useQuery({
    queryKey: ['sections-for-attendance', selectedSemesterId],
    queryFn: () => academicsApi.listSections(selectedSemesterId),
    enabled: !!selectedSemesterId,
  })

  // Sessions
  const { data: sessions = [] } = useQuery({
    queryKey: ['attendance-sessions', selectedCourseId, selectedSectionId],
    queryFn: () => sisApi.listAttendanceSessions({ course_id: selectedCourseId, section_id: selectedSectionId }),
    enabled: !!selectedCourseId && !!selectedSectionId,
  })

  function onAssignmentChange(value: string) {
    setSelectedAssignmentId(value)
    const item = items.find(i => i.id === value)
    if (!item) { setSelectedCourseId(''); setSelectedSemesterId(''); return }
    setSelectedCourseId(item.course_id)
    setSelectedSemesterId(item.semester_id)
    setSelectedSectionId('')
  }

  return (
    <PageShell>
      <PageHeader icon={ClipboardCheck} title="Mark Attendance" subtitle="Record attendance for your classes" />

      {/* Selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6 mt-6 max-w-2xl">
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">Course</label>
          <Select value={selectedAssignmentId || undefined} onValueChange={onAssignmentChange}>
            <SelectTrigger className="w-full"><SelectValue placeholder="— select course —" /></SelectTrigger>
            <SelectContent>
              {items.filter(i => i.is_active).map((i: any) => (
                <SelectItem key={i.id} value={i.id}>
                  {i.course?.code} – {i.course?.title} ({i.role_in_course})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">Section</label>
          <Select value={selectedSectionId || undefined} onValueChange={setSelectedSectionId}
            disabled={!selectedSemesterId}>
            <SelectTrigger className="w-full"><SelectValue placeholder="— select section —" /></SelectTrigger>
            <SelectContent>
              {sections.map(s => (
                <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Session list */}
      {selectedCourseId && selectedSectionId && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">
              Sessions <span className="text-muted-foreground font-normal">({sessions.length})</span>
            </h2>
            <Button onClick={() => setShowNewSession(true)}>
              <Plus size={14} className="mr-1" /> New Session
            </Button>
          </div>

          {sessions.length === 0 ? (
            <div className="rounded-xl py-12 text-center text-muted-foreground text-sm border border-gray-200">
              <Users size={32} className="mx-auto mb-3 opacity-30" />
              No sessions yet. Create one to start taking attendance.
            </div>
          ) : (
            <div className="rounded-xl overflow-hidden border border-gray-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    {['Date', 'Period', 'Topic', 'Attendance', 'Status', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sessions.map(s => (
                    <tr key={s.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-3 text-xs text-foreground font-medium">{s.session_date}</td>
                      <td className="px-4 py-3 text-xs text-foreground">{s.period_number ?? '—'}</td>
                      <td className="px-4 py-3 text-xs text-foreground max-w-[200px] truncate">
                        {s.topic_covered ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {s.first_marked_at
                          ? (
                            <div className="flex flex-col leading-tight">
                              <span className="text-foreground font-semibold">
                                {s.present_count} / {s.present_count + s.absent_count} present
                              </span>
                              <span className="text-muted-foreground font-medium">
                                {s.absent_count} absent · {pct(s.present_count, s.absent_count)}
                              </span>
                            </div>
                          )
                          : <span className="text-muted-foreground font-medium">Not marked</span>
                        }
                      </td>
                      <td className="px-4 py-3"><StatusBadge session={s} /></td>
                      <td className="px-4 py-3">
                        <button onClick={() => setMarkSession(s)}
                          className="text-xs font-medium flex items-center gap-1 text-blue-700 hover:text-blue-800 transition-colors">
                          {s.is_editable ? 'Mark' : 'View'} <ChevronRight size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {showNewSession && selectedCourseId && selectedSectionId && (
        <NewSessionModal
          courseId={selectedCourseId}
          sectionId={selectedSectionId}
          onClose={() => setShowNewSession(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['attendance-sessions'] })}
        />
      )}
      {markSession && (
        <MarkModal
          session={markSession}
          onClose={() => setMarkSession(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['attendance-sessions'] })}
        />
      )}
    </PageShell>
  )
}
