import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Clock, MapPin, BookOpen, Ticket } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { sisApi } from '@/lib/api/sis'

export default function MyExamTimetablePage() {
  const [sessionId, setSessionId] = useState('')

  const sessionsQ = useQuery({
    queryKey: ['exam-sessions-published'],
    queryFn: () => sisApi.listExamSessions({ status: 'PUBLISHED' }),
  })

  const timetableQ = useQuery({
    queryKey: ['my-timetable', sessionId],
    queryFn: () => sisApi.getMyTimetable(sessionId),
    enabled: !!sessionId,
  })

  const tt = timetableQ.data

  const grouped: Record<string, NonNullable<typeof tt>['courses']> = {}
  for (const row of tt?.courses ?? []) {
    const key = row.exam_date ?? 'Unscheduled'
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(row)
  }
  const dates = Object.keys(grouped).sort()

  return (
    <PageShell>
      <PageHeader title="My Exam Timetable" icon={CalendarDays} />

      <div className="px-6 py-4 max-w-2xl space-y-5">

        {/* Session picker */}
        <div>
          <label className="block text-xs text-slate-800 mb-1">Select Exam Session</label>
          <select
            value={sessionId}
            onChange={e => setSessionId(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">— Choose exam session —</option>
            {(sessionsQ.data ?? []).map(s => (
              <option key={s.id} value={s.id}>
                {s.session_name} ({s.academic_year})
              </option>
            ))}
          </select>
        </div>

        {timetableQ.isLoading && <p className="text-sm text-slate-700">Loading…</p>}

        {timetableQ.isError && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/8 p-4">
            <p className="text-sm text-red-400">
              No timetable found for this session. You may not be enrolled or eligibility hasn't been computed.
            </p>
          </div>
        )}

        {/* Hall ticket + seat assignment banner */}
        {tt?.seat && (
          <div className="rounded-2xl border border-blue-500/20 bg-blue-500/8 px-5 py-3 grid grid-cols-3 gap-4">
            <div>
              <p className="text-[10px] text-slate-800">Seat</p>
              <p className="text-xl font-black text-white font-mono">{tt.seat.seat_number}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-800">Room</p>
              <p className="text-base font-bold text-white">{tt.seat.room_number}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-800">Center</p>
              <p className="text-sm font-semibold text-white">{tt.seat.center_name}</p>
              {tt.seat.address && <p className="text-xs text-slate-700">{tt.seat.address}</p>}
            </div>
          </div>
        )}

        {/* Timetable */}
        {tt && (
          <>
            <p className="text-xs text-slate-700">
              Session: <span className="text-slate-900 font-semibold">{tt.session_name}</span>
              {' · '}{tt.semester_name}
            </p>

            {dates.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 text-slate-700">
                <CalendarDays size={36} className="mb-3 opacity-30" />
                <p className="text-sm">No exams in this session.</p>
              </div>
            )}

            <div className="space-y-5">
              {dates.map(date => (
                <div key={date}>
                  <div className="flex items-center gap-2 mb-2">
                    <CalendarDays size={13} className="text-slate-700" />
                    <p className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      {date === 'Unscheduled' ? 'Not yet scheduled' : date}
                    </p>
                  </div>
                  <div className="space-y-2">
                    {grouped[date].map((row, i) => (
                      <div key={i}
                        className={`rounded-xl border px-4 py-3 ${
                          row.is_scheduled
                            ? 'border-white/8 bg-white/4'
                            : 'border-white/5 bg-white/2 opacity-60'
                        }`}>
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <BookOpen size={12} className="text-blue-400" />
                              <span className="text-sm font-bold text-white">{row.course_code}</span>
                              <span className="text-sm text-slate-900">{row.course_title}</span>
                            </div>
                          </div>
                          {row.is_scheduled && row.start_time && row.end_time && (
                            <div className="text-right flex-shrink-0">
                              <p className="text-xs font-semibold text-white flex items-center gap-1">
                                <Clock size={11} className="text-slate-800" />
                                {String(row.start_time)} – {String(row.end_time)}
                              </p>
                            </div>
                          )}
                        </div>

                        {row.is_scheduled && (
                          <div className="mt-1.5 flex flex-wrap gap-3 text-xs text-slate-700">
                            {row.center_name && (
                              <span className="flex items-center gap-1">
                                <MapPin size={10} /> {row.center_name}
                              </span>
                            )}
                            {row.room_number && <span>Room: {row.room_number}</span>}
                          </div>
                        )}

                        {!row.is_scheduled && (
                          <p className="text-xs text-slate-600 mt-1">Date & time TBA</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {!sessionId && (
          <div className="flex flex-col items-center justify-center py-16 text-slate-700">
            <Ticket size={36} className="mb-3 opacity-30" />
            <p className="text-sm">Select an exam session to view your timetable</p>
          </div>
        )}
      </div>
    </PageShell>
  )
}
