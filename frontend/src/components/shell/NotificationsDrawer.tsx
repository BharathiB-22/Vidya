import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, X, CheckCheck, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  listNotifications, markAllRead, markNotificationRead, notificationHref,
  type NotificationItem,
} from '@/lib/api/notifications'
import { useAuth } from '@/lib/auth'

interface NotificationsDrawerProps {
  open: boolean
  onClose: () => void
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function NotificationsDrawer({ open, onClose }: NotificationsDrawerProps) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  // The reader of these notifications is their recipient, so their role is what
  // decides which surface a shared entity type should open.
  const { user } = useAuth()

  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['notifications'],
    queryFn:  () => listNotifications({ page: 1, page_size: 20 }),
    enabled:  open,
    refetchInterval: 60000,
  })

  const markAllMut = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['notifications-count'] })
    },
  })

  const readMut = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['notifications-count'] })
    },
  })

  function handleItemClick(n: NotificationItem) {
    if (!n.is_read) readMut.mutate(n.id)
    const href = notificationHref(n, user?.role)
    if (href) { onClose(); navigate(href) }
  }

  const items = data?.items ?? []
  const unread = data?.unread_count ?? 0

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      )}

      <div
        data-testid="notifications-drawer"
        className={`fixed inset-y-0 right-0 z-50 w-80 max-w-full bg-white border-l border-gray-200 shadow-xl flex flex-col
          transform transition-transform duration-200 ease-in-out
          ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-sv-primary" />
            <span className="font-semibold text-gray-900 text-sm">Notifications</span>
            {unread > 0 && (
              <span className="bg-sv-primary text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                {unread}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {unread > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => markAllMut.mutate()}
                disabled={markAllMut.isPending}
                className="text-xs text-sv-primary h-7 px-2 gap-1"
              >
                {markAllMut.isPending
                  ? <Loader2 className="w-3 h-3 animate-spin" />
                  : <CheckCheck className="w-3.5 h-3.5" />}
                Mark all read
              </Button>
            )}
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-gray-100 text-gray-600 transition-colors"
              aria-label="Close notifications"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-12 text-gray-600 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading…
            </div>
          )}

          {isError && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-600 text-sm gap-2 px-4 text-center">
              <Bell className="w-6 h-6 text-gray-200" />
              Could not load notifications.
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-gray-600 text-sm gap-3">
              <Bell className="w-8 h-8 text-gray-200" />
              No notifications
            </div>
          )}

          {items.map((n) => (
            <div
              key={n.id}
              onClick={() => handleItemClick(n)}
              className={`px-4 py-3 border-b border-gray-50 cursor-pointer hover:bg-gray-50 transition-colors ${!n.is_read ? 'bg-indigo-50/50' : ''}`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className={`text-sm leading-snug ${!n.is_read ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
                  {n.title}
                </p>
                {!n.is_read && (
                  <span className="w-2 h-2 mt-1.5 rounded-full bg-sv-primary flex-shrink-0" />
                )}
              </div>
              {n.body && (
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.body}</p>
              )}
              <p className="text-[10px] text-gray-600 mt-1">{timeAgo(n.created_at)}</p>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 px-4 py-2.5 flex-shrink-0">
          <Link
            to="/notifications"
            onClick={onClose}
            className="block text-center text-xs font-medium text-sv-primary hover:underline"
          >
            View all notifications
          </Link>
        </div>
      </div>
    </>
  )
}
