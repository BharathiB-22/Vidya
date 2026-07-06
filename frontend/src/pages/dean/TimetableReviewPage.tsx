import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardCheck, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { TimetableGrid } from '@/components/timetable/TimetableGrid'
import {
  listPendingTimetables,
  getTimetable,
  approveTimetable,
  rejectTimetable,
} from '@/lib/api/timetable'
import { getErrorMessage } from '@/lib/api'
import type { TimetableListItem } from '@/types/timetable'

function PendingRow({ item }: { item: TimetableListItem }) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  const detailQ = useQuery({
    queryKey: ['timetable-detail', item.id],
    queryFn: () => getTimetable(item.id),
    enabled: expanded,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['pending-timetables'] })
    queryClient.invalidateQueries({ queryKey: ['timetable-detail', item.id] })
  }

  const approveMut = useMutation({
    mutationFn: () => approveTimetable(item.id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const rejectMut = useMutation({
    mutationFn: () => rejectTimetable(item.id, comment),
    onSuccess: () => {
      setRejecting(false)
      setComment('')
      invalidate()
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        <div className="text-left">
          <p className="text-sm font-semibold text-gray-800">Section {item.section_name}</p>
          <p className="text-xs text-gray-400">Submitted {item.submitted_at ? new Date(item.submitted_at).toLocaleString() : '—'}</p>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-gray-100 pt-4">
          {detailQ.isLoading ? (
            <div className="h-48 rounded-xl bg-gray-50 animate-pulse" />
          ) : detailQ.data ? (
            <TimetableGrid
              slots={detailQ.data.slots}
              periods={detailQ.data.template?.periods}
              workingDays={detailQ.data.template?.working_days}
              saturdayMode={detailQ.data.template?.saturday_mode}
              editable={false}
            />
          ) : null}

          {error && <div className="text-xs text-red-600">{error}</div>}

          {rejecting ? (
            <div className="space-y-2">
              <Textarea
                placeholder="Reason for rejection…"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
              />
              <div className="flex gap-2 justify-end">
                <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={!comment.trim() || rejectMut.isPending}
                  onClick={() => rejectMut.mutate()}
                >
                  {rejectMut.isPending ? 'Rejecting…' : 'Confirm Reject'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2 justify-end">
              <Button size="sm" variant="outline" onClick={() => setRejecting(true)}>Reject</Button>
              <Button size="sm" disabled={approveMut.isPending} onClick={() => approveMut.mutate()}>
                {approveMut.isPending ? 'Approving…' : 'Approve'}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TimetableReviewPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['pending-timetables'],
    queryFn: listPendingTimetables,
  })

  const items = data ?? []

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Timetable Review</h1>
        <p className="text-sm text-gray-400 mt-0.5">Approve or reject timetables submitted for review.</p>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load pending timetables. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((n) => <div key={n} className="h-16 rounded-xl bg-gray-50 animate-pulse" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <ClipboardCheck className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No timetables are pending review.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => <PendingRow key={item.id} item={item} />)}
        </div>
      )}
    </div>
  )
}
