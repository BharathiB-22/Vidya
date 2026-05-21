import adminApi from '@/lib/adminApi'

export type TenantStatus = 'PROVISIONING' | 'ACTIVE' | 'FAILED'

export interface Tenant {
  id: string
  name: string
  slug: string
  schema_name: string
  status: TenantStatus
  is_active: boolean
  contact_email: string | null
  created_at: string
}

export interface CreateTenantPayload {
  name: string
  admin_email: string
  admin_password: string
  admin_full_name: string
  contact_email?: string
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
  updates: { name?: string; is_active?: boolean },
): Promise<Tenant> {
  const { data } = await adminApi.patch<Tenant>(`/tenants/${id}`, updates)
  return data
}
