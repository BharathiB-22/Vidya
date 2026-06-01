import adminApi from '@/lib/adminApi'

export interface AuditLogEntry {
  id: string
  event_type: string
  actor_user_id: string | null
  actor_role: string | null
  tenant_id: string | null
  schema_name: string | null
  target_entity: string | null
  target_id: string | null
  metadata: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export interface AuditLogListResponse {
  total: number
  page: number
  page_size: number
  items: AuditLogEntry[]
}

export interface PlatformAuditStats {
  total_events: number
  tenant_events: number
  login_events: number
  ai_events: number
  security_events: number
  recent: AuditLogEntry[]
}

export interface AuditLogFilters {
  tenant_id?: string
  event_type?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

export async function getAuditStats(): Promise<PlatformAuditStats> {
  const { data } = await adminApi.get<PlatformAuditStats>('/platform/audit-logs/stats')
  return data
}

export async function listAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogListResponse> {
  const params: Record<string, unknown> = {}
  if (filters.tenant_id)  params.tenant_id  = filters.tenant_id
  if (filters.event_type) params.event_type = filters.event_type
  if (filters.date_from)  params.date_from  = filters.date_from
  if (filters.date_to)    params.date_to    = filters.date_to
  if (filters.page)       params.page       = filters.page
  if (filters.page_size)  params.page_size  = filters.page_size
  const { data } = await adminApi.get<AuditLogListResponse>('/platform/audit-logs', { params })
  return data
}
