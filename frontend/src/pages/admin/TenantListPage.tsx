import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlusCircle, Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { listTenants, updateTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'

function StatusBadge({ status }: { status: TenantStatus }) {
  const cfg: Record<TenantStatus, string> = {
    PROVISIONING: 'bg-yellow-100 text-yellow-700',
    ACTIVE:       'bg-green-100 text-green-700',
    FAILED:       'bg-red-100 text-red-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg[status]}`}>
      {status}
    </span>
  )
}

function TenantRow({
  tenant,
  onSelect,
  onToggle,
}: {
  tenant: Tenant
  onSelect: (t: Tenant) => void
  onToggle: (t: Tenant) => void
}) {
  return (
    <tr className="hover:bg-gray-50 cursor-pointer" onClick={() => onSelect(tenant)}>
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{tenant.name}</div>
        <div className="text-xs text-gray-500">{tenant.slug}</div>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={tenant.status} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">{tenant.contact_email ?? '—'}</td>
      <td className="px-4 py-3 text-xs text-gray-500">
        {new Date(tenant.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => onToggle(tenant)}
          className={`text-xs px-2 py-0.5 rounded border font-medium transition-colors ${
            tenant.is_active
              ? 'border-red-200 text-red-600 hover:bg-red-50'
              : 'border-green-200 text-green-600 hover:bg-green-50'
          }`}
        >
          {tenant.is_active ? 'Deactivate' : 'Activate'}
        </button>
      </td>
    </tr>
  )
}

export default function TenantListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [includeInactive, setIncludeInactive] = useState(true)
  const [sortByName, setSortByName] = useState(false)
  const [confirmTenant, setConfirmTenant] = useState<Tenant | null>(null)

  const { data: tenants, isLoading, isError, refetch } = useQuery<Tenant[]>({
    queryKey: ['admin-tenants', includeInactive],
    queryFn:  () => listTenants(includeInactive),
  })

  const toggleMut = useMutation({
    mutationFn: (t: Tenant) => updateTenant(t.id, { is_active: !t.is_active }),
    onSuccess: (_data, t) => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast(t.is_active ? 'Tenant deactivated.' : 'Tenant activated.', 'success')
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
    onSettled: () => setConfirmTenant(null),
  })

  const all = tenants ?? []
  const rows = sortByName ? [...all].sort((a, b) => a.name.localeCompare(b.name)) : all
  const activeCount = all.filter((t) => t.is_active).length

  return (
    <main className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Tenants</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {isLoading ? 'Loading…' : `${all.length} institution${all.length !== 1 ? 's' : ''} · ${activeCount} active`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={sortByName}
              onChange={(e) => setSortByName(e.target.checked)}
              className="rounded"
            />
            Sort A–Z
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="rounded"
            />
            Show inactive
          </label>
          <Button onClick={() => navigate('/admin/tenants/new')}>
            <PlusCircle className="h-4 w-4 mr-1.5" />
            New Tenant
          </Button>
        </div>
      </div>

      {isError && (
        <div className="mb-4">
          <PageError message="Failed to load tenants." onRetry={() => refetch()} />
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <PageLoading message="Loading tenants…" />
        ) : rows.length === 0 ? (
          <PageEmpty
            icon={Building2}
            message="No tenants yet. Create one to get started."
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Institution', 'Status', 'Contact', 'Created', 'Actions'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((t) => (
                <TenantRow
                  key={t.id}
                  tenant={t}
                  onSelect={(tenant) => navigate(`/admin/tenants/${tenant.id}`)}
                  onToggle={(tenant) => setConfirmTenant(tenant)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {confirmTenant && (
        <ConfirmDialog
          open={!!confirmTenant}
          title={confirmTenant.is_active ? 'Deactivate tenant?' : 'Activate tenant?'}
          description={
            confirmTenant.is_active
              ? `Users at "${confirmTenant.name}" will no longer be able to log in.`
              : `Re-enable access for all users at "${confirmTenant.name}".`
          }
          confirmLabel={confirmTenant.is_active ? 'Deactivate' : 'Activate'}
          danger={confirmTenant.is_active}
          loading={toggleMut.isPending}
          onConfirm={() => toggleMut.mutate(confirmTenant)}
          onCancel={() => setConfirmTenant(null)}
        />
      )}
    </main>
  )
}
