import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clock, RefreshCw, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { AttendanceSessionOut, AttendanceRecordOut, AttendanceMarkEntry } from '@/lib/api/sis'

function pct(present: number, absent: number): string {
  const total = present + absent
  if (total === 0) return '—'
  return `${Math.round((present / total) * 100)}%`
}

type StatusToggle = 'PRESENT' | 'ABSENT'

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
  const [search, setSearch] = useState('')

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

  function toggle(studentId: string, current: StatusToggle) {
    setLocalStatus(p => ({ ...p, [studentId]: current === 'PRESENT' ? 'ABSENT' : 'PRESENT' }))
  }

  const present = records.filter(r => effectiveStatus(r) === 'PRESENT').length
  const absent = records.filter(r => effectiveStatus(r) === 'ABSENT').length

  // Search keeps large classes navigable; marking still writes every record.
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return records
    return records.filter(r =>
      r.student_name.toLowerCase().includes(q) || (r.usn ?? '').toLowerCase().includes(q),
    )
  }, [records, search])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-4xl rounded-2xl flex flex-col max-h-[92vh] bg-white border border-gray-200 shadow-xl">

        {/* Header */}
        <div className="px-5 pt-5 pb-4 border-b border-gray-200">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-foreground truncate">
                {session.course_code} · {session.section_name}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {session.session_date}
                {session.period_number ? ` · Period ${session.period_number}` : ''}
                {session.topic_covered ? ` · ${session.topic_covered}` : ''}
              </p>
            </div>
            <button onClick={onClose} aria-label="Close"
              className="text-muted-foreground hover:text-foreground transition-colors shrink-0">
              <X size={18} />
            </button>
          </div>

          {/* Live tally */}
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-green-50 text-green-700 border border-green-200">
              {present} Present
            </span>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
              {absent} Absent
            </span>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
              {pct(present, absent)}
            </span>
            {session.minutes_until_lock !== null && (
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 inline-flex items-center gap-1">
                <Clock size={11} />
                {Math.floor(session.minutes_until_lock / 60)}h {session.minutes_until_lock % 60}m left to edit
              </span>
            )}
          </div>

          {/* Bulk actions + search */}
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <button onClick={() => markAll('PRESENT')}
              className="text-xs px-3 py-1.5 rounded-lg font-semibold border transition-colors bg-green-50 text-green-800 border-green-300 hover:bg-green-100">
              Mark all Present
            </button>
            <button onClick={() => markAll('ABSENT')}
              className="text-xs px-3 py-1.5 rounded-lg font-semibold border transition-colors bg-red-50 text-red-800 border-red-300 hover:bg-red-100">
              Mark all Absent
            </button>
            <div className="relative flex-1 min-w-[180px]">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search name or USN…"
                className="w-full text-xs rounded-lg pl-8 pr-2 py-1.5 text-foreground border border-gray-300 bg-white outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            Tap a row to toggle Present / Absent. Saving always writes every student,
            not just the ones matching the search.
          </p>
        </div>

        {/* Roster */}
        <div className="flex-1 overflow-y-auto px-3 py-3">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">Loading students…</div>
          ) : visible.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">No students match “{search}”.</div>
          ) : (
            <ul className="space-y-1.5">
              {visible.map(r => {
                const cur = effectiveStatus(r)
                const isPresent = cur === 'PRESENT'
                return (
                  <li key={r.student_id}>
                    <div className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      isPresent ? 'bg-green-50/60 border-green-200' : 'bg-red-50/50 border-red-200'
                    }`}>
                      {/* Tap target: the whole identity block toggles */}
                      <button
                        type="button"
                        onClick={() => toggle(r.student_id, cur)}
                        aria-pressed={isPresent}
                        aria-label={`${r.student_name} is ${isPresent ? 'Present' : 'Absent'}. Tap to toggle.`}
                        className="flex flex-1 items-center gap-3 min-w-0 text-left"
                      >
                        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${
                          isPresent
                            ? 'bg-green-600 border-green-600 text-white'
                            : 'bg-white border-gray-300 text-gray-600'
                        }`}>
                          {isPresent ? <Check size={15} /> : 'A'}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-foreground truncate">{r.student_name}</span>
                          <span className="block text-[11px] font-mono text-muted-foreground">{r.usn ?? '—'}</span>
                        </span>
                      </button>

                      {/* Explicit two-state control for pointer users */}
                      <div className="flex shrink-0 rounded-lg border border-gray-300 overflow-hidden">
                        {(['PRESENT', 'ABSENT'] as StatusToggle[]).map(s => {
                          const active = cur === s
                          const activeCls = s === 'PRESENT'
                            ? 'bg-green-600 text-white'
                            : 'bg-red-600 text-white'
                          return (
                            <button
                              key={s}
                              type="button"
                              onClick={() => setLocalStatus(p => ({ ...p, [r.student_id]: s }))}
                              className={`px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                                active ? activeCls : 'bg-white text-gray-600 hover:bg-gray-50'
                              }`}
                            >
                              {s === 'PRESENT' ? 'P' : 'A'}
                            </button>
                          )
                        })}
                      </div>

                      <input
                        type="text"
                        placeholder="Note"
                        value={localRemarks[r.student_id] ?? r.remarks ?? ''}
                        onChange={e => setLocalRemarks(p => ({ ...p, [r.student_id]: e.target.value }))}
                        className="hidden sm:block w-32 shrink-0 text-xs rounded-lg px-2 py-1.5 text-foreground border border-gray-300 bg-white outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </li>
                )
              })}
            </ul>
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
