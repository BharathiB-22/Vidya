import { History } from 'lucide-react'
import { useMySubmissions } from '@/hooks/labs'
import { useMySubmissions as useMyCourseworkSubmissions } from '@/hooks/coursework'
import { WidgetCard } from './WidgetCard'

interface ActivityItem {
  id: string
  label: string
  timestamp: string
}

/**
 * Real submission activity only (labs + coursework) — notifications already
 * have their own dedicated widget (NotificationsWidget), so they're
 * deliberately excluded here to avoid showing the same items twice.
 */
export function RecentActivity() {
  const labSubmissionsQ = useMySubmissions()
  const courseworkSubmissionsQ = useMyCourseworkSubmissions()

  const isLoading = labSubmissionsQ.isLoading || courseworkSubmissionsQ.isLoading

  const items: ActivityItem[] = [
    ...(labSubmissionsQ.data?.items ?? []).map((s) => ({
      id: `lab-sub-${s.id}`,
      label: `Lab submission — ${s.status.toLowerCase().replace('_', ' ')}`,
      timestamp: s.submitted_at,
    })),
    ...(courseworkSubmissionsQ.data?.items ?? []).map((s) => ({
      id: `coursework-sub-${s.id}`,
      label: `Assignment submission — ${s.status.toLowerCase().replace('_', ' ')}`,
      timestamp: s.submitted_at,
    })),
  ]
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))
    .slice(0, 5)

  return (
    <WidgetCard title="Recent Activity" icon={History} isLoading={isLoading}>
      {items.length === 0 ? (
        <p className="text-sm text-gray-600 py-2">
          Nothing recent yet. Submissions will appear here.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-3 text-sm">
              <p className="text-gray-700 truncate">{item.label}</p>
              <span className="text-xs text-gray-600 flex-shrink-0">
                {new Date(item.timestamp).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
