import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlusCircle, Building2, CheckCircle2, Clock, AlertTriangle, Shield, Search } from 'lucide-react'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { listTenants, updateTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'

function StatusBadge({ status }: { status: TenantStatus }) {
  const cfg: Record<TenantStatus, { bg: string; color: string; border: string }> = {
    ACTIVE:       { bg: 'rgba(16,185,129,0.1)',  color: '#34d399', border: 'rgba(16,185,129,0.2)' },
    PROVISIONING: { bg: 'rgba(245,158,11,0.1)',  color: '#fbbf24', border: 'rgba(245,158,11,0.2)' },
    FAILED:       { bg: 'rgba(239,68,68,0.1)',   color: '#f87171', border: 'rgba(239,68,68,0.2)'  },
  }
  const { bg, color, border } = cfg[status]
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-bold"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {status}
    </span>
  )
}

function StatCard({
  label, value, icon: Icon, accentColor, sub,
}: {
  label: string; value: string | number; icon: typeof Building2; accentColor: string; sub?: string
}) {
  return (
    <div
      className="rounded-xl p-5 flex items-center gap-4"
      style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: accentColor + '18', border: `1px solid ${accentColor}30` }}
      >
        <Icon className="h-5 w-5" style={{ color: accentColor }} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-slate-100 leading-tight">{value}</p>
        <p className="text-xs font-medium text-slate-500 truncate">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function TenantRow({
  tenant, onSelect, onToggle,
}: {
  tenant: Tenant; onSelect: (t: Tenant) => void; onToggle: (t: Tenant) => void
}) {
  return (
    <tr
      className="cursor-pointer transition-colors"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.02)' }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
      onClick={() => onSelect(tenant)}
    >
      <td className="px-4 py-3">
        <div className="font-medium text-slate-200">{tenant.name}</div>
        <div className="text-xs text-slate-600">{tenant.slug}</div>
      </td>
      <td className="px-4 py-3"><StatusBadge status={tenant.status} /></td>
      <td className="px-4 py-3 text-sm text-slate-500">{tenant.contact_email ?? '—'}</td>
      <td className="px-4 py-3 text-xs text-slate-600">
        {new Date(tenant.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => onToggle(tenant)}
          className="text-xs px-2 py-0.5 rounded font-medium transition-colors"
          style={
            tenant.is_active
              ? { background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }
              : { background: 'rgba(16,185,129,0.08)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)' }
          }
          onMouseEnter={(e) => {
            if (tenant.is_active) {
              e.currentTarget.style.background = 'rgba(239,68,68,0.15)'
            } else {
              e.currentTarget.style.background = 'rgba(16,185,129,0.15)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = tenant.is_active
              ? 'rgba(239,68,68,0.08)'
              : 'rgba(16,185,129,0.08)'
          }}
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
  const [sortByName,      setSortByName]      = useState(false)
  const [search,          setSearch]          = useState('')
  const [confirmTenant,   setConfirmTenant]   = useState<Tenant | null>(null)

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

  const all          = tenants ?? []
  const query        = search.toLowerCase().trim()
  const filtered     = query
    ? all.filter((t) => t.name.toLowerCase().includes(query) || t.slug.toLowerCase().includes(query))
    : all
  const rows         = sortByName ? [...filtered].sort((a, b) => a.name.localeCompare(b.name)) : filtered
  const activeCount  = all.filter((t) => t.is_active).length
  const pendingCount = all.filter((t) => t.status === 'PROVISIONING').length
  const failedCount  = all.filter((t) => t.status === 'FAILED').length

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">

      {/* Search bar */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or slug…"
          className="w-full pl-9 pr-4 py-2 text-sm text-slate-200 placeholder:text-slate-600 rounded-xl outline-none transition-all"
          style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
          onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(16,185,129,0.3)' }}
          onBlur={(e)  => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)' }}
        />
      </div>

      {/* Header row */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">Universities</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {isLoading
              ? 'Loading…'
              : `${all.length} institution${all.length !== 1 ? 's' : ''} · ${activeCount} active`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-500 cursor-pointer">
            <input
              type="checkbox"
              checked={sortByName}
              onChange={(e) => setSortByName(e.target.checked)}
              className="rounded accent-emerald-500"
            />
            Sort A–Z
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-500 cursor-pointer">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="rounded accent-emerald-500"
            />
            Show inactive
          </label>
          <button
            onClick={() => navigate('/admin/tenants/new')}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-semibold text-white transition-all"
            style={{
              background: 'linear-gradient(135deg, #10b981, #059669)',
              boxShadow: '0 0 16px rgba(16,185,129,0.2)',
            }}
          >
            <PlusCircle className="h-4 w-4" />
            New University
          </button>
        </div>
      </div>

      {/* Stat cards */}
      {!isLoading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard label="Total Universities" value={all.length}    icon={Building2}    accentColor="#6366f1" />
          <StatCard label="Active Tenants"     value={activeCount}   icon={CheckCircle2} accentColor="#10b981" />
          <StatCard
            label="Pending Setup"
            value={pendingCount}
            icon={Clock}
            accentColor="#f59e0b"
            sub={pendingCount > 0 ? 'Provisioning in progress' : 'All clear'}
          />
          <StatCard
            label="Platform Health"
            value={failedCount === 0 ? 'OK' : `${failedCount} Failed`}
            icon={failedCount === 0 ? Shield : AlertTriangle}
            accentColor={failedCount === 0 ? '#10b981' : '#ef4444'}
            sub={failedCount === 0 ? 'Operational' : 'Needs attention'}
          />
        </div>
      )}

      {isError && (
        <div className="mb-4">
          <PageError message="Failed to load tenants." onRetry={() => refetch()} />
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}>
        {isLoading ? (
          <PageLoading message="Loading universities…" />
        ) : rows.length === 0 ? (
          <PageEmpty icon={Building2} message="No universities yet. Create one to get started." />
        ) : (
          <table className="w-full text-sm">
            <thead style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
              <tr>
                {['Institution', 'Status', 'Contact', 'Created', 'Actions'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wide"
                    style={{ color: '#475569' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
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
