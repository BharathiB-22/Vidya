import adminApi from '@/lib/adminApi'

export interface ServiceHealthItem {
  service: string
  label: string
  status: 'healthy' | 'unhealthy' | 'skipped'
  latency_ms: number
  error_msg: string | null
}

export interface TenantCounts {
  total: number
  active: number
  inactive: number
  archived: number
  provisioning: number
  failed: number
}

export interface JobCounts {
  pending: number
  running: number
  completed: number
  failed: number
  total_24h: number
}

export interface AIServiceInfo {
  name: string
  configured: boolean
  model: string
  active: boolean
}

export interface AuditEventSummary {
  event_type: string
  created_at: string
  schema_name: string | null
  metadata_: Record<string, unknown> | null
}

export interface PlatformStats {
  health: ServiceHealthItem[]
  all_healthy: boolean
  tenants: TenantCounts
  jobs: JobCounts
  ai_services: AIServiceInfo[]
  recent_events: AuditEventSummary[]
  generated_at: string
}

export async function getPlatformStats(): Promise<PlatformStats> {
  const { data } = await adminApi.get<PlatformStats>('/tenants/platform-stats')
  return data
}
