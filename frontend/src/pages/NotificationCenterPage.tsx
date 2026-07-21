import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import {
  listNotifications, markNotificationRead, markAllRead,
  notificationCategory, notificationHref, type NotificationItem,
} from '@/lib/api/notifications'
import { useAuth } from '@/lib/auth'

const PAGE_SIZE = 25

const CATEGORY_COLORS: Record<string, string> = {
  Academic:      '#6366f1',
  Assignments:   '#f59e0b',
  Labs:          '#0ea5e9',
  Research:      '#8b5cf6',
  Attendance:    '#ec4899',
  Exam:          '#10b981',
  Announcements: '#64748b',
  System:        '#94a3b8',
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

function CategoryChip({ category }: { category: string }) {
  const c = CATEGORY_COLORS[category] ?? '#64748b'
  return (
    <span
      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: `${c}18`, color: c, border: `1px solid ${c}33` }}
    >
      {category}
    </span>
  )
}

export default function NotificationCenterPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  // The reader of these notifications is their recipient, so their role is what
  // decides which surface a shared entity type should open.
  const { user } = useAuth()
  const [tab, setTab] = useState<'all' | 'unread'>('all')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['notification-center', tab, page],
    queryFn: () => listNotifications({
      page,
      page_size: PAGE_SIZE,
      is_read: tab === 'unread' ? false : undefined,
    }),
  })

  const readMut = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notification-center'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['notifications-count'] })
    },
  })

  const markAllMut = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notification-center'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['notifications-count'] })
    },
  })

  function handleClick(n: NotificationItem) {
    if (!n.is_read) readMut.mutate(n.id)
    const href = notificationHref(n, user?.role)
    if (href) navigate(href)
  }

  const items = data?.items ?? []
  const unread = data?.unread_count ?? 0
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <PageShell>
      <PageHeader
        icon={Bell}
        title="Notifications"
        subtitle={`${unread} unread`}
        action={unread > 0 ? (
          <Button variant="outline" size="sm" className="gap-1.5"
            onClick={() => markAllMut.mutate()} disabled={markAllMut.isPending}>
            {markAllMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCheck className="h-3.5 w-3.5" />}
            Mark all read
          </Button>
        ) : undefined}
      />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['all', 'unread'] as const).map(t => (
          <button
            key={t}
            onClick={() => { setTab(t); setPage(1) }}
            className="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px capitalize transition-colors"
            style={{
              borderColor: tab === t ? '#4f46e5' : 'transparent',
              color: tab === t ? '#4f46e5' : '#6b7280',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-16" style={{ color: '#9CA3AF' }}>
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : isError ? (
        <div className="py-16 text-center text-sm" style={{ color: '#dc2626' }}>
          Could not load notifications. Please refresh.
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center">
          <Bell className="h-10 w-10 mx-auto mb-3" style={{ color: '#D1D5DB' }} />
          <p className="text-sm" style={{ color: '#4B5563' }}>
            {tab === 'unread' ? 'No unread notifications.' : 'No notifications yet.'}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
          {items.map(n => {
            const href = notificationHref(n, user?.role)
            return (
              <div
                key={n.id}
                onClick={() => handleClick(n)}
                className={`px-4 py-3 flex items-start gap-3 ${href || !n.is_read ? 'cursor-pointer hover:bg-gray-50' : ''}`}
              >
                <div className="mt-1.5 flex-shrink-0">
                  <span
                    className="block w-2 h-2 rounded-full"
                    style={{ background: n.is_read ? '#D1D5DB' : '#4f46e5' }}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold" style={{ color: n.is_read ? '#4B5563' : '#111827' }}>
                      {n.title}
                    </p>
                    <CategoryChip category={notificationCategory(n.notification_type)} />
                  </div>
                  {n.body && <p className="text-xs mt-0.5" style={{ color: '#6B7280' }}>{n.body}</p>}
                  <p className="text-[10px] mt-1" style={{ color: '#9CA3AF' }}>{timeAgo(n.created_at)}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="p-1.5 rounded-lg disabled:opacity-30" style={{ color: '#6B7280' }}>
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-xs" style={{ color: '#4B5563' }}>Page {page} of {totalPages} · {total} total</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="p-1.5 rounded-lg disabled:opacity-30" style={{ color: '#6B7280' }}>
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </PageShell>
  )
}
