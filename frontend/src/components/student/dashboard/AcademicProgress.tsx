import { useQuery } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import { WidgetCard } from './WidgetCard'

function ProgressBar({ label, pct, detail }: { label: string; pct: number | null; detail: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span className="text-xs text-gray-400">{detail}</span>
      </div>
      <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-sv-primary rounded-full transition-all"
          style={{ width: `${Math.min(100, Math.max(0, pct ?? 0))}%` }}
        />
      </div>
    </div>
  )
}

export function AcademicProgress() {
  const attendanceQ = useQuery({
    queryKey: ['my-attendance-summary'],
    queryFn: () => sisApi.getMyAttendance(),
  })
  const marksQ = useQuery({
    queryKey: ['my-marks'],
    queryFn: sisApi.getMyMarks,
  })
  const transcriptQ = useQuery({
    queryKey: ['my-transcript'],
    queryFn: sisApi.getMyTranscript,
  })

  const marksTotals = (marksQ.data?.courses ?? []).reduce(
    (acc, c) => ({
      obtained: acc.obtained + Number(c.total_marks_obtained ?? 0),
      max: acc.max + Number(c.total_max_marks ?? 0),
    }),
    { obtained: 0, max: 0 },
  )
  const marksPct = marksTotals.max > 0 ? (marksTotals.obtained / marksTotals.max) * 100 : null

  const creditTotals = (transcriptQ.data?.semesters ?? []).reduce(
    (acc, s) => ({
      attempted: acc.attempted + (s.total_credits_attempted ?? 0),
      earned: acc.earned + (s.total_credits_earned ?? 0),
    }),
    { attempted: 0, earned: 0 },
  )
  const creditsPct = creditTotals.attempted > 0 ? (creditTotals.earned / creditTotals.attempted) * 100 : null

  const isLoading = attendanceQ.isLoading || marksQ.isLoading || transcriptQ.isLoading
  const isError = attendanceQ.isError || marksQ.isError || transcriptQ.isError

  return (
    <WidgetCard title="Academic Progress" icon={TrendingUp} isLoading={isLoading} isError={isError}>
      <div className="space-y-4 py-1">
        <ProgressBar
          label="Attendance"
          pct={attendanceQ.data?.overall_pct ?? null}
          detail={attendanceQ.data?.overall_pct != null ? `${attendanceQ.data.overall_pct.toFixed(1)}%` : '—'}
        />
        <ProgressBar
          label="Marks"
          pct={marksPct}
          detail={marksPct != null ? `${Math.round(marksPct)}%` : '—'}
        />
        <ProgressBar
          label="Credits Completed"
          pct={creditsPct}
          detail={creditTotals.attempted > 0 ? `${creditTotals.earned}/${creditTotals.attempted}` : '—'}
        />
      </div>
    </WidgetCard>
  )
}
