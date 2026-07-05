import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { listNotifications, notificationCategory, notificationHref } from '@/lib/api/notifications'
import { WidgetCard } from './WidgetCard'

function timeAgo(dateStr: string): string {
  const mins = Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function NotificationsWidget() {
  const navigate = useNavigate()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['notifications', 'dashboard-recent'],
    queryFn: () => listNotifications({ page_size: 5 }),
  })

  return (
    <WidgetCard
      title={`Notifications${data?.unread_count ? ` (${data.unread_count})` : ''}`}
      icon={Bell}
      isLoading={isLoading}
      isError={isError}
      action={{ label: 'View All', to: '/notifications' }}
    >
      {!data?.items?.length ? (
        <p className="text-sm text-gray-400 py-2">No notifications yet.</p>
      ) : (
        <ul className="space-y-2.5">
          {data.items.map((n) => {
            const href = notificationHref(n)
            return (
              <li
                key={n.id}
                onClick={() => href && navigate(href)}
                className={`text-sm ${href ? 'cursor-pointer hover:text-sv-primary' : ''}`}
              >
                <div className="flex items-center gap-2">
                  {!n.is_read && <span className="h-1.5 w-1.5 rounded-full bg-sv-primary flex-shrink-0" />}
                  <span className={`truncate ${n.is_read ? 'text-gray-500' : 'font-semibold text-gray-800'}`}>
                    {n.title}
                  </span>
                  <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{timeAgo(n.created_at)}</span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{notificationCategory(n.notification_type)}</p>
              </li>
            )
          })}
        </ul>
      )}
    </WidgetCard>
  )
}
