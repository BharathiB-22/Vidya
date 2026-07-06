import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'

export function NewSessionModal({
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
