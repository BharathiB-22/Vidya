import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutList, ChevronLeft, Plus, Trash2, CheckCircle2, Users } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { SeatingAllocationResult } from '@/lib/api/sis'

type RoomSpec = { room_number: string; capacity: string }

export default function ExamSeatAllocationPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [centerId, setCenterId] = useState('')
  const [rooms, setRooms] = useState<RoomSpec[]>([{ room_number: '', capacity: '' }])
  const [result, setResult] = useState<SeatingAllocationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sessionQ = useQuery({
    queryKey: ['exam-session', id],
    queryFn: () => sisApi.getExamSession(id!),
    enabled: !!id,
  })
  const centersQ = useQuery({
    queryKey: ['exam-centers'],
    queryFn: () => sisApi.listExamCenters(),
  })
  const seatingQ = useQuery({
    queryKey: ['seating', id],
    queryFn: () => sisApi.listSeating(id!),
    enabled: !!id,
  })

  const allocate = useMutation({
    mutationFn: () => sisApi.allocateSeats(id!, {
      center_id: centerId,
      rooms: rooms
        .filter(r => r.room_number && r.capacity)
        .map(r => ({ room_number: r.room_number, capacity: parseInt(r.capacity) })),
    }),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries({ queryKey: ['seating', id] })
      qc.invalidateQueries({ queryKey: ['exam-session', id] })
    },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Allocation failed'),
  })

  const addRoom = () => setRooms(r => [...r, { room_number: '', capacity: '' }])
  const removeRoom = (i: number) => setRooms(r => r.filter((_, j) => j !== i))
  const setRoom = (i: number, k: keyof RoomSpec, v: string) =>
    setRooms(r => r.map((row, j) => j === i ? { ...row, [k]: v } : row))

  const seats = seatingQ.data ?? []

  return (
    <PageShell>
      <PageHeader
        title="Seat Allocation"
        icon={LayoutList}
        action={
          <Button variant="ghost" size="sm" onClick={() => navigate(`/sis/exam/sessions/${id}`)}>
            <ChevronLeft size={14} className="mr-1" /> Session
          </Button>
        }
      />

      <div className="px-6 py-5 max-w-3xl space-y-5">

        {sessionQ.data && (
          <p className="text-xs text-slate-500">
            Session: <span className="text-slate-300 font-semibold">{sessionQ.data.session_name}</span>
            {' · '}Status: <span className="text-slate-300 font-semibold">{sessionQ.data.status}</span>
          </p>
        )}

        {/* Allocation form */}
        <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
          <h3 className="text-sm font-bold text-white mb-4">Run Seat Allocation</h3>

          <div className="mb-3">
            <label className="block text-xs text-slate-400 mb-1">Exam Center</label>
            <select value={centerId} onChange={e => setCenterId(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500">
              <option value="">— Select center —</option>
              {(centersQ.data ?? []).map(c => (
                <option key={c.id} value={c.id}>{c.center_name} (cap: {c.capacity ?? '?'})</option>
              ))}
            </select>
          </div>

          <div className="mb-3">
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs text-slate-400">Rooms</label>
              <button onClick={addRoom}
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <Plus size={11} /> Add room
              </button>
            </div>
            <div className="space-y-2">
              {rooms.map((r, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input type="text" placeholder="Room number" value={r.room_number}
                    onChange={e => setRoom(i, 'room_number', e.target.value)}
                    className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  <input type="number" placeholder="Capacity" value={r.capacity} min={1}
                    onChange={e => setRoom(i, 'capacity', e.target.value)}
                    className="w-24 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  {rooms.length > 1 && (
                    <button onClick={() => removeRoom(i)} className="text-slate-600 hover:text-red-400">
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

          <Button size="sm" onClick={() => allocate.mutate()}
            disabled={allocate.isPending || !centerId || rooms.every(r => !r.room_number)}>
            {allocate.isPending ? 'Allocating…' : 'Allocate Seats'}
          </Button>
        </div>

        {/* Result */}
        {result && (
          <div className="rounded-2xl border border-green-500/20 bg-green-500/8 p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle2 size={16} className="text-green-400" />
              <h3 className="text-sm font-bold text-green-400">Allocation Complete</h3>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div>
                <p className="text-[11px] text-slate-500">Allocated</p>
                <p className="text-xl font-black text-white">{result.allocated}</p>
              </div>
              <div>
                <p className="text-[11px] text-slate-500">Rooms Used</p>
                <p className="text-xl font-black text-white">{result.rooms_used}</p>
              </div>
              <div>
                <p className="text-[11px] text-slate-500">Total Capacity</p>
                <p className="text-xl font-black text-white">{result.total_capacity}</p>
              </div>
            </div>
            {result.details.map(d => (
              <div key={d.room_number} className="flex justify-between text-xs text-slate-400 py-1 border-t border-white/5">
                <span>Room {d.room_number}</span>
                <span>{d.assigned} / {d.capacity}</span>
              </div>
            ))}
          </div>
        )}

        {/* Existing seating table */}
        {seats.length > 0 && (
          <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
            <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
              <Users size={14} /> Current Seating ({seats.length} students)
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/8 text-left text-[11px] text-slate-500 uppercase">
                    <th className="px-3 py-2">Student</th>
                    <th className="px-3 py-2">USN</th>
                    <th className="px-3 py-2">Hall Ticket</th>
                    <th className="px-3 py-2">Room</th>
                    <th className="px-3 py-2">Seat</th>
                  </tr>
                </thead>
                <tbody>
                  {seats.slice(0, 50).map(s => (
                    <tr key={s.student_id} className="border-b border-white/5 hover:bg-white/3">
                      <td className="px-3 py-2 text-white">{s.student_name ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-400 font-mono text-xs">{s.usn ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-300 font-mono text-xs">{s.hall_ticket_number ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-400">{s.room_number ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-400">{s.seat_number ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {seats.length > 50 && (
                <p className="text-xs text-slate-500 mt-2 text-center">Showing first 50 of {seats.length}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </PageShell>
  )
}
