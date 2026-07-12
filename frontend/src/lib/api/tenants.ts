import adminApi from '@/lib/adminApi'

export type TenantStatus = 'PROVISIONING' | 'ACTIVE' | 'INACTIVE' | 'ARCHIVED' | 'FAILED' | 'DELETED' | 'PERMANENTLY_DELETED'

/** What an institution calls its academic governance authority.
 *  A DISPLAY NAME ONLY — the permissions behind both are identical. */
export type GovernanceType = 'BOARD' | 'UNIVERSITY_MEMBERS'

export interface Tenant {
  id: string
  name: string
  slug: string
  schema_name: string
  status: TenantStatus
  is_active: boolean
  contact_email: string | null
  logo_url: string | null
  primary_color: string | null
  secondary_color: string | null
  governance_type: GovernanceType
  created_at: string
  deleted_at: string | null
  deleted_by_user_id: string | null
}

export interface CreateTenantPayload {
  name: string
  admin_email: string
  admin_password: string
  admin_full_name: string
  contact_email?: string
  logo_url?: string
  primary_color?: string
  secondary_color?: string
  governance_type?: GovernanceType
}

export async function listTenants(includeInactive = true): Promise<Tenant[]> {
  const { data } = await adminApi.get<Tenant[]>('/tenants', {
    params: { include_inactive: includeInactive },
  })
  return data
}

export async function getTenant(id: string): Promise<Tenant> {
  const { data } = await adminApi.get<Tenant>(`/tenants/${id}`)
  return data
}

export async function createTenant(payload: CreateTenantPayload): Promise<Tenant> {
  const { data } = await adminApi.post<Tenant>('/tenants', payload)
  return data
}

export async function retryTenantProvisioning(id: string): Promise<Tenant> {
  const { data } = await adminApi.post<Tenant>(`/tenants/${id}/retry`)
  return data
}

export async function updateTenant(
  id: string,
  updates: {
    name?: string
    contact_email?: string | null
    status?: 'ACTIVE' | 'INACTIVE' | 'ARCHIVED'
    is_active?: boolean
    logo_url?: string | null
    primary_color?: string | null
    secondary_color?: string | null
  },
): Promise<Tenant> {
  const { data } = await adminApi.patch<Tenant>(`/tenants/${id}`, updates)
  return data
}

export async function deleteTenant(id: string, confirmSlug: string): Promise<Tenant> {
  const { data } = await adminApi.delete<Tenant>(`/tenants/${id}`, {
    data: { confirm_slug: confirmSlug },
  })
  return data
}

export async function restoreTenant(id: string): Promise<Tenant> {
  const { data } = await adminApi.post<Tenant>(`/tenants/${id}/restore`)
  return data
}

export async function permanentlyDeleteTenant(id: string, confirmSlug: string): Promise<Tenant> {
  const { data } = await adminApi.delete<Tenant>(`/tenants/${id}/permanent`, {
    data: { confirm_slug: confirmSlug },
  })
  return data
}

// ---------------------------------------------------------------------------
// Tenant migration status
// ---------------------------------------------------------------------------

export interface TenantMigrationStatus {
  tenant_id: string
  tenant_name: string
  schema_name: string
  current_revision: string | null
  head_revision: string
  is_current: boolean
  last_status: 'success' | 'failed' | null
  last_migration_at: string | null
  last_error: string | null
}

export interface TenantMigrationResult {
  schema_name: string
  status: 'success' | 'failed' | 'current'
  from_revision: string | null
  to_revision: string | null
  error?: string
}

export async function listTenantMigrations(): Promise<TenantMigrationStatus[]> {
  const { data } = await adminApi.get<TenantMigrationStatus[]>('/tenants/migrations')
  return data
}

export async function retryTenantMigration(tenantId: string): Promise<TenantMigrationResult> {
  const { data } = await adminApi.post<TenantMigrationResult>(`/tenants/${tenantId}/migrations/retry`)
  return data
}
