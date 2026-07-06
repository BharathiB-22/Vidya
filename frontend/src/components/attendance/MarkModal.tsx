import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { AttendanceSessionOut, AttendanceRecordOut, AttendanceMarkEntry } from '@/lib/api/sis'

function pct(present: number, absent: number): string {
  const total = present + absent
  if (total === 0) return '—'
  return `${Math.round((present / total) * 100)}%`
}

type StatusToggle = 'PRESENT' | 'ABSENT'
const STATUS_COLORS: Record<StatusToggle, { bg: string; text: string; border: string }> = {
  PRESENT: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-400' },
  ABSENT:  { bg: 'bg-red-100',   text: 'text-red-800',   border: 'border-red-400' },
}
const ALL_STATUSES: StatusToggle[] = ['PRESENT', 'ABSENT']

export function MarkModal({
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
