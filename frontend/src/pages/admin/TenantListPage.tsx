import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlusCircle, LogOut, RefreshCw, Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAdminAuth } from '@/lib/adminAuth'
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

function TenantRow({ tenant, onSelect }: { tenant: Tenant; onSelect: (t: Tenant) => void }) {
  const qc = useQueryClient()
  const toggleMut = useMutation({
    mutationFn: () => updateTenant(tenant.id, { is_active: !tenant.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-tenants'] }),
  })

  return (
    <tr
      className="hover:bg-gray-50 cursor-pointer"
      onClick={() => onSelect(tenant)}
    >
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
          onClick={() => toggleMut.mutate()}
          disabled={toggleMut.isPending}
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
  const auth = useAdminAuth()
  const [includeInactive, setIncludeInactive] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { data: tenants, isLoading, refetch, error: queryError } = useQuery<Tenant[]>({
    queryKey: ['admin-tenants', includeInactive],
    queryFn: () => listTenants(includeInactive),
  })

  useEffect(() => {
    if (queryError) setError(getAdminErrorMessage(queryError))
  }, [queryError])

  const rows = tenants ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-indigo-600" />
          <span className="text-lg font-semibold text-indigo-700">Vidya Admin Console</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="text-gray-500 hover:text-gray-700"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <Button variant="ghost" size="sm" onClick={auth.logout}>
            <LogOut className="h-4 w-4 mr-1" />
            Sign out
          </Button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Tenants</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Manage institution accounts on this platform.
            </p>
          </div>
          <div className="flex items-center gap-3">
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

        {error && (
          <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading tenants…
            </div>
          ) : rows.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <Building2 className="h-8 w-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No tenants yet. Create one to get started.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Institution</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Contact</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((t) => (
                  <TenantRow
                    key={t.id}
                    tenant={t}
                    onSelect={(tenant) => navigate(`/admin/tenants/${tenant.id}`)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  )
}
