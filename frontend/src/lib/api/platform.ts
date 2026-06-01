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

export interface PlatformSettings {
  platform_name:  string
  company_name:   string
  support_email:  string
  environment:    string
  build_version:  string
  ai_provider:       string
  gemini_configured: boolean
  gemini_model:      string
  groq_configured:   boolean
  groq_model:        string
  storage_provider: string
  s3_endpoint:      string
  s3_bucket:        string
  s3_region:        string
  s3_use_ssl:       boolean
  max_upload_mb:    number
  smtp_host:     string
  smtp_from:     string
  email_enabled: boolean
  jwt_enabled:           boolean
  rbac_enabled:          boolean
  tenant_isolation:      boolean
  audit_logging_enabled: boolean
  soft_delete_enabled:   boolean
  access_token_expire_minutes: number
  refresh_token_expire_days:   number
}

export async function getPlatformSettings(): Promise<PlatformSettings> {
  const { data } = await adminApi.get<PlatformSettings>('/tenants/platform-settings')
  return data
}
