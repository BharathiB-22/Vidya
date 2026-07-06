import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardCheck, Plus, ChevronRight, Users,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type { AttendanceSessionOut } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useQuery as useAssignmentQuery } from '@tanstack/react-query'
import { StatusBadge } from '@/components/attendance/AttendanceStatusBadge'
import { NewSessionModal } from '@/components/attendance/NewSessionModal'
import { MarkModal } from '@/components/attendance/MarkModal'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(present: number, absent: number): string {
  const total = present + absent
  if (total === 0) return '—'
  return `${Math.round((present / total) * 100)}%`
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
