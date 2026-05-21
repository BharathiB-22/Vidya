import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Building2, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getTenant, retryTenantProvisioning, updateTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'
import { useState } from 'react'

function StatusBadge({ status }: { status: TenantStatus }) {
  const cfg: Record<TenantStatus, { cls: string; icon: React.ReactNode }> = {
    PROVISIONING: {
      cls: 'bg-yellow-100 text-yellow-700 border-yellow-200',
      icon: <RefreshCw className="h-3 w-3 animate-spin" />,
    },
    ACTIVE: {
      cls: 'bg-green-100 text-green-700 border-green-200',
      icon: <CheckCircle2 className="h-3 w-3" />,
    },
    FAILED: {
      cls: 'bg-red-100 text-red-700 border-red-200',
      icon: <AlertTriangle className="h-3 w-3" />,
    },
  }
  const { cls, icon } = cfg[status]
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium border ${cls}`}>
      {icon}
      {status}
    </span>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm text-gray-900 font-medium">{value}</span>
    </div>
  )
}

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  const { data: tenant, isLoading } = useQuery<Tenant>({
    queryKey: ['admin-tenant', id],
    queryFn: () => getTenant(id!),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data?.status === 'PROVISIONING' ? 3000 : false,
  })

  const retryMut = useMutation({
    mutationFn: () => retryTenantProvisioning(id!),
    onSuccess: () => {
      setActionError(null)
      setActionSuccess('Provisioning retried successfully. Tenant is now ACTIVE.')
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
    },
    onError: (err: unknown) => {
      setActionSuccess(null)
      setActionError(getAdminErrorMessage(err))
    },
  })

  const toggleMut = useMutation({
    mutationFn: () => updateTenant(id!, { is_active: !tenant?.is_active }),
    onSuccess: () => {
      setActionError(null)
      setActionSuccess(
        tenant?.is_active ? 'Tenant deactivated.' : 'Tenant activated.'
      )
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
    },
    onError: (err: unknown) => {
      setActionSuccess(null)
      setActionError(getAdminErrorMessage(err))
    },
  })

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 text-gray-400 gap-2">
        <RefreshCw className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    )
  }

  if (!tenant) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 text-red-600">
        Tenant not found.
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <button onClick={() => navigate('/admin/tenants')} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <Building2 className="h-5 w-5 text-indigo-600" />
        <span className="text-lg font-semibold text-indigo-700">{tenant.name}</span>
        <div className="ml-2">
          <StatusBadge status={tenant.status} />
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        {/* Info card */}
        <div className="bg-white rounded-xl border border-gray-200 px-6 py-2">
          <InfoRow label="Institution name" value={tenant.name} />
          <InfoRow label="Slug" value={<code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{tenant.slug}</code>} />
          <InfoRow label="Schema" value={<code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{tenant.schema_name}</code>} />
          <InfoRow label="Status" value={<StatusBadge status={tenant.status} />} />
          <InfoRow label="Active" value={tenant.is_active ? 'Yes' : 'No'} />
          <InfoRow label="Contact email" value={tenant.contact_email ?? '—'} />
          <InfoRow label="Provisioned" value={new Date(tenant.created_at).toLocaleString()} />
        </div>

        {/* Feedback */}
        {actionError && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {actionError}
          </div>
        )}
        {actionSuccess && (
          <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
            {actionSuccess}
          </div>
        )}

        {/* Actions */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h3 className="text-sm font-semibold text-gray-700">Actions</h3>

          {tenant.status === 'FAILED' && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-4 space-y-3">
              <p className="text-sm text-red-700 font-medium flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4" />
                Provisioning failed
              </p>
              <p className="text-xs text-red-600">
                The schema or admin seed step did not complete. Click Retry to attempt provisioning
                again without creating a new tenant record.
              </p>
              <Button
                size="sm"
                onClick={() => retryMut.mutate()}
                disabled={retryMut.isPending}
              >
                <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${retryMut.isPending ? 'animate-spin' : ''}`} />
                {retryMut.isPending ? 'Retrying…' : 'Retry provisioning'}
              </Button>
            </div>
          )}

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700">
                {tenant.is_active ? 'Deactivate tenant' : 'Activate tenant'}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {tenant.is_active
                  ? 'Users will no longer be able to log in.'
                  : 'Re-enable access for all users in this institution.'}
              </p>
            </div>
            <Button
              variant={tenant.is_active ? 'destructive' : 'default'}
              size="sm"
              onClick={() => toggleMut.mutate()}
              disabled={toggleMut.isPending || tenant.status === 'PROVISIONING'}
            >
              {toggleMut.isPending
                ? 'Updating…'
                : tenant.is_active
                ? 'Deactivate'
                : 'Activate'}
            </Button>
          </div>
        </div>
      </main>
    </div>
  )
}
