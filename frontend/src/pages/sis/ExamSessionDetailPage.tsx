import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CalendarDays, ChevronLeft, Plus, Trash2, Lock,
  Send, CheckCircle2, Users, LayoutList,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { ExamScheduleOut } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function SessionStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string; border: string }> = {
    DRAFT:             { label: 'Draft',             color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' },
    PUBLISHED:         { label: 'Published',         color: '#60a5fa', bg: 'rgba(59,130,246,0.12)',  border: 'rgba(59,130,246,0.25)' },
    SEATING_ALLOCATED: { label: 'Seating Allocated', color: '#a78bfa', bg: 'rgba(139,92,246,0.12)', border: 'rgba(139,92,246,0.25)' },
    LOCKED:            { label: 'Locked',            color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.25)' },
    COMPLETED:         { label: 'Completed',         color: '#4ade80', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.25)' },
  }
  const s = map[status] ?? { label: status, color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' }
  return (
    <span className="inline-flex items-center text-sm px-2.5 py-0.5 rounded-lg font-semibold"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
      {s.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Add schedule modal
// ---------------------------------------------------------------------------

function AddScheduleModal({
  sessionId, onClose, onSaved,
}: { sessionId: string; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    course_id: '', section_id: '', exam_date: '', start_time: '09:00', end_time: '12:00',
    center_id: '', room_number: '', notes: '',
  })
  const [error, setError] = useState<string | null>(null)

  const centersQ = useQuery({ queryKey: ['exam-centers'], queryFn: () => sisApi.listExamCenters() })

  const create = useMutation({
    mutationFn: () => sisApi.createExamSchedule(sessionId, {
      course_id: form.course_id,
      section_id: form.section_id,
      exam_date: form.exam_date,
      start_time: form.start_time,
      end_time: form.end_time,
      center_id: form.center_id || undefined,
      room_number: form.room_number || undefined,
      notes: form.notes || undefined,
    }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Failed to add schedule'),
  })

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[520px] max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-4">Add Exam Schedule</h3>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Course ID</label>
              <input type="text" value={form.course_id} onChange={e => set('course_id', e.target.value)}
                placeholder="Course UUID"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Section ID</label>
              <input type="text" value={form.section_id} onChange={e => set('section_id', e.target.value)}
                placeholder="Section UUID"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Exam Date</label>
            <input type="date" value={form.exam_date} onChange={e => set('exam_date', e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Start Time</label>
              <input type="time" value={form.start_time} onChange={e => set('start_time', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">End Time</label>
              <input type="time" value={form.end_time} onChange={e => set('end_time', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Exam Center (optional)</label>
              <select value={form.center_id} onChange={e => set('center_id', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500">
                <option value="">— None —</option>
                {(centersQ.data ?? []).map(c => (
                  <option key={c.id} value={c.id}>{c.center_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Room Number (optional)</label>
              <input type="text" value={form.room_number} onChange={e => set('room_number', e.target.value)}
                placeholder="e.g. Hall A"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Notes (optional)</label>
            <textarea rows={2} value={form.notes} onChange={e => set('notes', e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none" />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => create.mutate()}
            disabled={create.isPending || !form.course_id || !form.section_id || !form.exam_date}>
            {create.isPending ? 'Saving…' : 'Add Schedule'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ExamSessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showAddSchedule, setShowAddSchedule] = useState(false)

  const sessionQ = useQuery({
    queryKey: ['exam-session', id],
    queryFn: () => sisApi.getExamSession(id!),
    enabled: !!id,
  })

  const schedulesQ = useQuery({
    queryKey: ['exam-schedules', id],
    queryFn: () => sisApi.listExamSchedules(id!),
    enabled: !!id,
  })

  const publish = useMutation({
    mutationFn: () => sisApi.publishExamSession(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-session', id] }),
  })

  const lock = useMutation({
    mutationFn: () => sisApi.lockExamSession(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-session', id] }),
  })

  const complete = useMutation({
    mutationFn: () => sisApi.completeExamSession(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-session', id] }),
  })

  const deleteSchedule = useMutation({
    mutationFn: (schId: string) => sisApi.deleteExamSchedule(schId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-schedules', id] }),
  })

  const sess = sessionQ.data
  const schedules: ExamScheduleOut[] = schedulesQ.data ?? []

  // Group schedules by date
  const byDate: Record<string, ExamScheduleOut[]> = {}
  for (const s of schedules) {
    if (!byDate[s.exam_date]) byDate[s.exam_date] = []
    byDate[s.exam_date].push(s)
  }
  const sortedDates = Object.keys(byDate).sort()

  if (sessionQ.isLoading)
    return <PageShell><p className="p-8 text-slate-500 text-sm">Loading…</p></PageShell>

  if (!sess)
    return <PageShell><p className="p-8 text-red-400 text-sm">Session not found.</p></PageShell>

  const isDraft = sess.status === 'DRAFT'
  const isPublished = sess.status === 'PUBLISHED'
  const isSeatingAllocated = sess.status === 'SEATING_ALLOCATED'

  return (
    <PageShell>
      <PageHeader
        title={sess.session_name}
        icon={CalendarDays}
        action={
          <Button variant="ghost" size="sm" onClick={() => navigate('/sis/exam/sessions')}>
            <ChevronLeft size={14} className="mr-1" /> Sessions
          </Button>
        }
      />

      <div className="px-6 py-5 max-w-4xl space-y-5">

        {/* Session info card */}
        <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wide text-blue-400">{sess.session_type}</span>
                <SessionStatusBadge status={sess.status} />
              </div>
              <h2 className="text-lg font-bold text-white mt-1">{sess.session_name}</h2>
              <p className="text-sm text-slate-400 mt-0.5">
                {sess.academic_year} · {sess.start_date} → {sess.end_date}
              </p>
              {sess.notes && <p className="text-xs text-slate-500 mt-1 italic">{sess.notes}</p>}
            </div>
            <div className="flex gap-2 flex-wrap">
              {isDraft && (
                <Button size="sm" onClick={() => publish.mutate()} disabled={publish.isPending}>
                  <Send size={13} className="mr-1" /> Publish
                </Button>
              )}
              {(isPublished || isSeatingAllocated) && (
                <Button size="sm" variant="outline" onClick={() => lock.mutate()} disabled={lock.isPending}
                  className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10">
                  <Lock size={13} className="mr-1" /> Lock
                </Button>
              )}
              {sess.status === 'LOCKED' && (
                <Button size="sm" variant="outline" onClick={() => complete.mutate()} disabled={complete.isPending}
                  className="border-green-500/30 text-green-400 hover:bg-green-500/10">
                  <CheckCircle2 size={13} className="mr-1" /> Complete
                </Button>
              )}
            </div>
          </div>

          {/* Quick-nav links */}
          <div className="mt-4 flex gap-2 flex-wrap">
            <Link to={`/sis/exam/sessions/${id}/invigilation`}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white border border-white/8 rounded-lg px-3 py-1.5 hover:bg-white/8 transition-colors">
              <Users size={12} /> Invigilators
            </Link>
            <Link to={`/sis/exam/sessions/${id}/seating`}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white border border-white/8 rounded-lg px-3 py-1.5 hover:bg-white/8 transition-colors">
              <LayoutList size={12} /> Seat Allocation
            </Link>
          </div>
        </div>

        {/* Timetable */}
        <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-white">Timetable ({schedules.length} schedules)</h3>
            {isDraft && (
              <Button size="sm" variant="outline" onClick={() => setShowAddSchedule(true)}>
                <Plus size={13} className="mr-1" /> Add Schedule
              </Button>
            )}
          </div>

          {schedules.length === 0 && (
            <div className="text-center py-8 text-slate-500">
              <CalendarDays size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">No schedules yet. Add exam entries for each course + section.</p>
            </div>
          )}

          {sortedDates.map(date => (
            <div key={date} className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="text-[11px] text-slate-500 uppercase tracking-wide font-bold">
                  {new Date(date + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })}
                </div>
                <div className="flex-1 h-px bg-white/8" />
              </div>
              <div className="space-y-2 pl-2">
                {byDate[date].map(sch => (
                  <div key={sch.id}
                    className="flex items-center gap-3 rounded-lg border border-white/6 bg-white/3 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white">
                        {sch.course_code} — {sch.course_title}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {sch.section_name} · {sch.start_time.slice(0, 5)}–{sch.end_time.slice(0, 5)}
                        {sch.center_name && ` · ${sch.center_name}`}
                        {sch.room_number && ` Room ${sch.room_number}`}
                      </p>
                    </div>
                    {isDraft && (
                      <button
                        onClick={() => { if (confirm('Delete this schedule?')) deleteSchedule.mutate(sch.id) }}
                        className="text-slate-600 hover:text-red-400 transition-colors">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {showAddSchedule && id && (
        <AddScheduleModal
          sessionId={id}
          onClose={() => setShowAddSchedule(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['exam-schedules', id] })}
        />
      )}
    </PageShell>
  )
}
