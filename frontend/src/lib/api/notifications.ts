import api from '@/lib/api'

export interface NotificationItem {
  id: string
  notification_type: string
  title: string
  body: string
  entity_type: string | null
  entity_id: string | null
  is_read: boolean
  created_at: string
  read_at: string | null
}

export interface NotificationListResponse {
  total: number
  unread_count: number
  page: number
  page_size: number
  items: NotificationItem[]
}

export async function listNotifications(params?: {
  is_read?: boolean
  page?: number
  page_size?: number
}): Promise<NotificationListResponse> {
  const { data } = await api.get('/notifications', { params })
  return data
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await api.patch(`/notifications/${notificationId}/read`)
}

export async function markAllRead(): Promise<void> {
  await api.post('/notifications/read-all')
}