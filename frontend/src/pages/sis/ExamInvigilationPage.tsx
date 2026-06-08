import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, ChevronLeft, Plus, Trash2, Clock } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'

function AssignModal({
  sessionId, onClose, onSaved,
}: { sessionId: string; onClose: () => void; onSaved: () => void }) {
  const [facultyId, setFacultyId] = useState('')
  const [room, setRoom] = useState('')
  const [notes, setNotes] = useState('')
  const [scheduleId, setScheduleId] = useState('')
  const [centerId, setCenterId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const schedulesQ = useQuery({
    queryKey: ['exam-schedules', sessionId],
    queryFn: () => sisApi.listExamSchedules(sessionId),
  })
  const centersQ = useQuery({
    queryKey: ['exam-centers'],
    queryFn: () => sisApi.listExamCenters(),
  })

  const assign = useMutation({
    mutationFn: () => sisApi.assignInvigilation(sessionId, {
      faculty_user_id: facultyId,
      schedule_id: scheduleId || undefined,
      center_id: centerId || undefined,
      room_number: room || undefined,
      notes: notes || undefined,
    }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Assignment failed'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[440px] rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-4">Assign Invigilator</h3>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Faculty User ID</label>
            <input type="text" value={facultyId} onChange={e => setFacultyId(e.target.value)}
              placeholder="Faculty UUID"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs" />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Schedule (optional)</label>
            <select value={scheduleId} onChange={e => setScheduleId(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none">
              <option value="">— General duty (no specific schedule) —</option>
              {(schedulesQ.data ?? []).map(s => (
                <option key={s.id} value={s.id}>
                  {s.exam_date} · {s.course_code} · {s.section_name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Center (optional)</label>
              <select value={centerId} onChange={e => setCenterId(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none">
                <option value="">— None —</option>
                {(centersQ.data ?? []).map(c => (
                  <option key={c.id} value={c.id}>{c.center_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Room (optional)</label>
              <input type="text" value={room} onChange={e => setRoom(e.target.value)}
                placeholder="Hall A"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Notes (optional)</label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none resize-none" />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => assign.mutate()} disabled={assign.isPending || !facultyId}>
            {assign.isPending ? 'Assigning…' : 'Assign'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ExamInvigilationPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showAssign, setShowAssign] = useState(false)

  const sessionQ = useQuery({
    queryKey: ['exam-session', id],
    queryFn: () => sisApi.getExamSession(id!),
    enabled: !!id,
  })

  const invigilationQ = useQuery({
    queryKey: ['invigilation', id],
    queryFn: () => sisApi.listInvigilation(id!),
    enabled: !!id,
  })

  const remove = useMutation({
    mutationFn: (invId: string) => sisApi.deleteInvigilation(invId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['invigilation', id] }),
  })

  const sess = sessionQ.data
  const assignments = invigilationQ.data ?? []
  const isDraft = sess?.status === 'DRAFT' || sess?.status === 'PUBLISHED'

  return (
    <PageShell>
      <PageHeader
        title="Invigilation Assignments"
        icon={Users}
        action={
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate(`/sis/exam/sessions/${id}`)}>
              <ChevronLeft size={14} className="mr-1" /> Session
            </Button>
            {isDraft && (
              <Button size="sm" onClick={() => setShowAssign(true)}>
                <Plus size={13} className="mr-1" /> Assign
              </Button>
            )}
          </div>
        }
      />

      <div className="px-6 py-5 max-w-3xl">
        {sess && (
          <p className="text-xs text-slate-500 mb-4">
            Session: <span className="text-slate-300 font-semibold">{sess.session_name}</span>
          </p>
        )}

        {assignments.length === 0 && !invigilationQ.isLoading && (
          <div className="flex flex-col items-center justify-center py-16 text-slate-500">
            <Users size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No invigilators assigned yet.</p>
          </div>
        )}

        <div className="space-y-2">
          {assignments.map(a => (
            <div key={a.id}
              className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-white">
                  {a.faculty_name ?? <span className="font-mono text-xs text-slate-400">{a.faculty_user_id}</span>}
                </p>
                <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-2 flex-wrap">
                  {a.exam_date && (
                    <span className="flex items-center gap-1"><Clock size={10} /> {a.exam_date}</span>
                  )}
                  {a.center_name && <span>{a.center_name}</span>}
                  {a.room_number && <span>Room {a.room_number}</span>}
                  {!a.exam_date && !a.center_name && <span className="text-slate-600">General duty</span>}
                </p>
              </div>
              {isDraft && (
                <button
                  onClick={() => { if (confirm('Remove this invigilator?')) remove.mutate(a.id) }}
                  className="text-slate-600 hover:text-red-400 transition-colors">
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {showAssign && id && (
        <AssignModal
          sessionId={id}
          onClose={() => setShowAssign(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['invigilation', id] })}
        />
      )}
    </PageShell>
  )
}
