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

function pct(present: number, late: number, absent: number): string {
  const total = present + late + absent
  if (total === 0) return '—'
  return `${Math.round(((present + late) / total) * 100)}%`
}

function StatusBadge({ session }: { session: AttendanceSessionOut }) {
  if (session.status === 'LOCKED') {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
        style={{ background: 'rgba(148,163,184,0.1)', color: '#94a3b8', border: '1px solid rgba(148,163,184,0.25)' }}>
        <Lock size={10} /> Locked
      </span>
    )
  }
  if (!session.is_editable) {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
        style={{ background: 'rgba(251,191,36,0.1)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
        <Clock size={10} /> Window closed
      </span>
    )
  }
  if (session.first_marked_at === null) {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
        style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
        <AlertTriangle size={10} /> Pending
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
      style={{ background: 'rgba(34,197,94,0.1)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}>
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

  const inputClass = "w-full rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-2 focus:ring-indigo-500"
  const inputStyle = { background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}>
      <div className="w-full max-w-md rounded-2xl p-6 space-y-4"
        style={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)' }}>
        <h3 className="text-base font-semibold text-slate-200">New Attendance Session</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Date *</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className={inputClass} style={inputStyle} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Period (optional)</label>
            <input type="number" min={1} max={20} placeholder="e.g. 2" value={period}
              onChange={e => setPeriod(e.target.value)}
              className={inputClass} style={inputStyle} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Topic covered (optional)</label>
            <input type="text" placeholder="e.g. Linked Lists" value={topic}
              onChange={e => setTopic(e.target.value)}
              className={inputClass} style={inputStyle} />
          </div>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button variant="ghost" onClick={onClose} className="flex-1 text-slate-400">Cancel</Button>
          <Button onClick={() => create.mutate()} disabled={!date || create.isPending} className="flex-1"
            style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}>
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

type StatusToggle = 'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
const STATUS_COLORS: Record<StatusToggle, { bg: string; color: string; border: string }> = {
  PRESENT: { bg: 'rgba(34,197,94,0.18)',   color: '#4ade80', border: 'rgba(34,197,94,0.4)' },
  ABSENT:  { bg: 'rgba(239,68,68,0.18)',   color: '#f87171', border: 'rgba(239,68,68,0.4)' },
  LATE:    { bg: 'rgba(251,191,36,0.18)',  color: '#fbbf24', border: 'rgba(251,191,36,0.4)' },
  EXCUSED: { bg: 'rgba(99,102,241,0.18)',  color: '#a5b4fc', border: 'rgba(99,102,241,0.4)' },
}
const ALL_STATUSES: StatusToggle[] = ['PRESENT', 'ABSENT', 'LATE', 'EXCUSED']

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
  const late    = records.filter(r => effectiveStatus(r) === 'LATE').length
  const absent  = records.filter(r => effectiveStatus(r) === 'ABSENT').length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)' }}>
      <div className="w-full max-w-3xl rounded-2xl flex flex-col max-h-[90vh]"
        style={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)' }}>
        {/* Header */}
        <div className="p-5 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h3 className="text-base font-semibold text-slate-200">
                {session.course_code} / {session.section_name} / {session.session_date}
                {session.period_number ? ` · Period ${session.period_number}` : ''}
              </h3>
              {session.topic_covered && (
                <p className="text-xs text-slate-400 mt-0.5">{session.topic_covered}</p>
              )}
            </div>
            <div className="flex gap-2 text-xs text-slate-400">
              <span className="text-green-400 font-semibold">{present}P</span>
              <span className="text-yellow-400 font-semibold">{late}L</span>
              <span className="text-red-400 font-semibold">{absent}A</span>
              <span className="text-slate-500">{pct(present, late, absent)}</span>
              {session.minutes_until_lock !== null && (
                <span className="text-indigo-400">
                  <Clock size={11} className="inline" /> {Math.floor(session.minutes_until_lock / 60)}h{session.minutes_until_lock % 60}m left
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            {(['PRESENT', 'ABSENT', 'LATE', 'EXCUSED'] as StatusToggle[]).map(s => (
              <button key={s} onClick={() => markAll(s)}
                className="text-xs px-3 py-1 rounded-lg font-medium transition-all hover:scale-105"
                style={{ background: STATUS_COLORS[s].bg, color: STATUS_COLORS[s].color, border: `1px solid ${STATUS_COLORS[s].border}` }}>
                All {s}
              </button>
            ))}
          </div>
        </div>

        {/* Records */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-slate-400 text-sm">Loading students…</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                  {['USN', 'Name', 'Status', 'Remarks'].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map(r => {
                  const cur = effectiveStatus(r)
                  const sc  = STATUS_COLORS[cur]
                  return (
                    <tr key={r.student_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
                      className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2.5 text-xs font-mono text-slate-400">{r.usn ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-200">{r.student_name}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex gap-1">
                          {ALL_STATUSES.map(s => (
                            <button key={s} onClick={() => setLocalStatus(p => ({ ...p, [r.student_id]: s }))}
                              className="text-xs px-2 py-0.5 rounded font-semibold transition-all"
                              style={cur === s
                                ? { background: sc.bg, color: sc.color, border: `1px solid ${sc.border}` }
                                : { background: 'rgba(255,255,255,0.04)', color: '#475569', border: '1px solid rgba(255,255,255,0.08)' }}>
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
                          className="w-full text-xs rounded px-2 py-1 text-slate-300 outline-none"
                          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
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
        <div className="p-4 border-t space-y-3" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
          {!isFirstMark && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Edit reason <span className="text-red-400">*</span>
                <span className="text-slate-500 ml-1">(required — attendance already saved)</span>
              </label>
              <input type="text" placeholder="Reason for editing attendance…"
                value={editReason} onChange={e => setEditReason(e.target.value)}
                className="w-full text-sm rounded-lg px-3 py-2 text-slate-200 outline-none focus:ring-2 focus:ring-indigo-500"
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }} />
            </div>
          )}
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} className="flex-1 text-slate-400">Cancel</Button>
            <Button
              onClick={() => markMut.mutate()}
              disabled={(!isFirstMark && !editReason.trim()) || markMut.isPending}
              className="flex-1"
              style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}>
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
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Course</label>
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
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Section</label>
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
            <h2 className="text-sm font-semibold text-slate-300">
              Sessions <span className="text-slate-500 font-normal">({sessions.length})</span>
            </h2>
            <Button onClick={() => setShowNewSession(true)}
              style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}>
              <Plus size={14} className="mr-1" /> New Session
            </Button>
          </div>

          {sessions.length === 0 ? (
            <div className="rounded-xl py-12 text-center text-slate-500 text-sm"
              style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
              <Users size={32} className="mx-auto mb-3 opacity-30" />
              No sessions yet. Create one to start taking attendance.
            </div>
          ) : (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,0.04)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                    {['Date', 'Period', 'Topic', 'Attendance', 'Status', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-400">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sessions.map(s => (
                    <tr key={s.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
                      className="hover:bg-white/[0.02]">
                      <td className="px-4 py-3 text-xs text-slate-200 font-medium">{s.session_date}</td>
                      <td className="px-4 py-3 text-xs text-slate-400">{s.period_number ?? '—'}</td>
                      <td className="px-4 py-3 text-xs text-slate-400 max-w-[200px] truncate">
                        {s.topic_covered ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-xs font-semibold">
                        {s.first_marked_at
                          ? <span style={{ color: '#4ade80' }}>{pct(s.present_count, s.late_count, s.absent_count)}</span>
                          : <span className="text-slate-500">Not marked</span>
                        }
                      </td>
                      <td className="px-4 py-3"><StatusBadge session={s} /></td>
                      <td className="px-4 py-3">
                        <button onClick={() => setMarkSession(s)}
                          className="text-xs flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors">
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
