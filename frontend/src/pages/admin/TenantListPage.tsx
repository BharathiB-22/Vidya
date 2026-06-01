import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PlusCircle, Building2, CheckCircle2, AlertTriangle, Shield, Search,
  Pencil, Archive, RotateCcw,
} from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { listTenants, updateTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_CFG: Record<TenantStatus, { bg: string; color: string; border: string }> = {
  ACTIVE:       { bg: 'rgba(16,185,129,0.1)',  color: '#34d399', border: 'rgba(16,185,129,0.2)' },
  PROVISIONING: { bg: 'rgba(245,158,11,0.1)',  color: '#fbbf24', border: 'rgba(245,158,11,0.2)' },
  FAILED:       { bg: 'rgba(239,68,68,0.1)',   color: '#f87171', border: 'rgba(239,68,68,0.2)'  },
  INACTIVE:     { bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.2)' },
  ARCHIVED:     { bg: 'rgba(120,113,108,0.12)', color: '#a8a29e', border: 'rgba(120,113,108,0.2)' },
}

function StatusBadge({ status }: { status: TenantStatus }) {
  const { bg, color, border } = STATUS_CFG[status] ?? STATUS_CFG.INACTIVE
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-bold"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Tenant row
// ---------------------------------------------------------------------------

type LifecycleAction = 'deactivate' | 'archive' | 'reactivate'

function TenantRow({
  tenant, onSelect, onLifecycle, onEdit,
}: {
  tenant: Tenant
  onSelect: (t: Tenant) => void
  onLifecycle: (t: Tenant, action: LifecycleAction) => void
  onEdit: (t: Tenant) => void
}) {
  const isArchived  = tenant.status === 'ARCHIVED'
  const isInactive  = tenant.status === 'INACTIVE' || !tenant.is_active
  const canDeactivate = tenant.is_active && !isArchived
  const canArchive    = !isArchived
  const canReactivate = isArchived || (isInactive && tenant.status !== 'FAILED' && tenant.status !== 'PROVISIONING')

  const btnBase = 'text-[10px] px-1.5 py-0.5 rounded font-medium transition-colors flex items-center gap-0.5 whitespace-nowrap'

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
        <div className="flex items-center gap-1 flex-wrap">
          {/* Edit */}
          <button
            onClick={() => onEdit(tenant)}
            className={btnBase}
            style={{ background: 'rgba(99,102,241,0.08)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}
          >
            <Pencil className="h-2.5 w-2.5" /> Edit
          </button>

          {/* Deactivate */}
          {canDeactivate && (
            <button
              onClick={() => onLifecycle(tenant, 'deactivate')}
              className={btnBase}
              style={{ background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
            >
              Deactivate
            </button>
          )}

          {/* Archive */}
          {canArchive && (
            <button
              onClick={() => onLifecycle(tenant, 'archive')}
              className={btnBase}
              style={{ background: 'rgba(245,158,11,0.08)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)' }}
            >
              <Archive className="h-2.5 w-2.5" /> Archive
            </button>
          )}

          {/* Reactivate */}
          {canReactivate && (
            <button
              onClick={() => onLifecycle(tenant, 'reactivate')}
              className={btnBase}
              style={{ background: 'rgba(16,185,129,0.08)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)' }}
            >
              <RotateCcw className="h-2.5 w-2.5" /> Reactivate
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Edit tenant dialog
// ---------------------------------------------------------------------------

interface EditForm {
  name: string
  contact_email: string
  logo_url: string
  primary_color: string
  secondary_color: string
}

function EditTenantDialog({
  tenant,
  saving,
  onSave,
  onClose,
}: {
  tenant: Tenant
  saving: boolean
  onSave: (updates: Partial<EditForm>) => void
  onClose: () => void
}) {
  const [form, setForm] = useState<EditForm>({
    name:            tenant.name,
    contact_email:   tenant.contact_email ?? '',
    logo_url:        tenant.logo_url ?? '',
    primary_color:   tenant.primary_color ?? '',
    secondary_color: tenant.secondary_color ?? '',
  })

  const field = (key: keyof EditForm) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value })),
  })

  const inputCls = 'w-full px-3 py-2 text-sm text-slate-200 rounded-lg outline-none transition-all'
  const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }
  const labelCls = 'block text-xs font-medium text-slate-400 mb-1'

  function handleSave() {
    const updates: Partial<EditForm> = {}
    if (form.name.trim() !== tenant.name) updates.name = form.name.trim()
    if (form.contact_email !== (tenant.contact_email ?? '')) updates.contact_email = form.contact_email || ''
    if (form.logo_url !== (tenant.logo_url ?? '')) updates.logo_url = form.logo_url || ''
    if (form.primary_color !== (tenant.primary_color ?? '')) updates.primary_color = form.primary_color || ''
    if (form.secondary_color !== (tenant.secondary_color ?? '')) updates.secondary_color = form.secondary_color || ''
    onSave(updates)
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit University</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* Slug — read-only */}
          <div>
            <label className={labelCls}>Slug (read-only)</label>
            <div
              className="px-3 py-2 text-sm font-mono text-slate-500 rounded-lg"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              {tenant.slug}
            </div>
          </div>

          {/* Status — read-only display */}
          <div>
            <label className={labelCls}>Status</label>
            <div className="flex items-center gap-2 py-1">
              <StatusBadge status={tenant.status} />
              <span className="text-xs text-slate-600">(change via Deactivate / Archive / Reactivate)</span>
            </div>
          </div>

          {/* Name */}
          <div>
            <label className={labelCls}>University name</label>
            <input className={inputCls} style={inputStyle} {...field('name')} maxLength={100} />
          </div>

          {/* Contact email */}
          <div>
            <label className={labelCls}>Contact email</label>
            <input type="email" className={inputCls} style={inputStyle} {...field('contact_email')} />
          </div>

          {/* Logo URL */}
          <div>
            <label className={labelCls}>Logo URL</label>
            <input className={inputCls} style={inputStyle} {...field('logo_url')} placeholder="https://…" />
          </div>

          {/* Colors */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Primary color</label>
              <div className="flex gap-2 items-center">
                <input
                  type="color"
                  value={form.primary_color || '#10b981'}
                  onChange={(e) => setForm((f) => ({ ...f, primary_color: e.target.value }))}
                  className="h-8 w-8 rounded cursor-pointer border-0 bg-transparent"
                />
                <input className={`${inputCls} flex-1`} style={inputStyle} {...field('primary_color')} placeholder="#10b981" />
              </div>
            </div>
            <div>
              <label className={labelCls}>Secondary color</label>
              <div className="flex gap-2 items-center">
                <input
                  type="color"
                  value={form.secondary_color || '#059669'}
                  onChange={(e) => setForm((f) => ({ ...f, secondary_color: e.target.value }))}
                  className="h-8 w-8 rounded cursor-pointer border-0 bg-transparent"
                />
                <input className={`${inputCls} flex-1`} style={inputStyle} {...field('secondary_color')} placeholder="#059669" />
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TenantListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [includeInactive, setIncludeInactive]       = useState(true)
  const [sortByName,      setSortByName]             = useState(false)
  const [search,          setSearch]                 = useState('')
  const [editTenant,      setEditTenant]             = useState<Tenant | null>(null)
  const [lifecycleState,  setLifecycleState]         = useState<{ tenant: Tenant; action: LifecycleAction } | null>(null)

  const { data: tenants, isLoading, isError, refetch } = useQuery<Tenant[]>({
    queryKey: ['admin-tenants', includeInactive],
    queryFn:  () => listTenants(includeInactive),
  })

  const lifecycleMut = useMutation({
    mutationFn: ({ tenant, action }: { tenant: Tenant; action: LifecycleAction }) => {
      const statusMap: Record<LifecycleAction, 'ACTIVE' | 'INACTIVE' | 'ARCHIVED'> = {
        deactivate: 'INACTIVE',
        archive:    'ARCHIVED',
        reactivate: 'ACTIVE',
      }
      return updateTenant(tenant.id, { status: statusMap[action] })
    },
    onSuccess: (_data, { action }) => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      const msg: Record<LifecycleAction, string> = {
        deactivate: 'Tenant deactivated.',
        archive:    'Tenant archived.',
        reactivate: 'Tenant reactivated.',
      }
      addToast(msg[action], 'success')
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
    onSettled: () => setLifecycleState(null),
  })

  const editMut = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: object }) =>
      updateTenant(id, updates as Parameters<typeof updateTenant>[1]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant updated.', 'success')
      setEditTenant(null)
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
  })

  const all           = tenants ?? []
  const query         = search.toLowerCase().trim()
  const filtered      = query
    ? all.filter((t) => t.name.toLowerCase().includes(query) || t.slug.toLowerCase().includes(query))
    : all
  const rows          = sortByName ? [...filtered].sort((a, b) => a.name.localeCompare(b.name)) : filtered
  const activeCount   = all.filter((t) => t.status === 'ACTIVE').length
  const inactiveCount = all.filter((t) => t.status === 'INACTIVE').length
  const archivedCount = all.filter((t) => t.status === 'ARCHIVED').length
  const pendingCount  = all.filter((t) => t.status === 'PROVISIONING').length
  const failedCount   = all.filter((t) => t.status === 'FAILED').length

  const confirmConfig = lifecycleState ? {
    deactivate: {
      title: 'Deactivate tenant?',
      description: `Users at "${lifecycleState.tenant.name}" will no longer be able to log in.`,
      confirmLabel: 'Deactivate',
      danger: true,
    },
    archive: {
      title: 'Archive tenant?',
      description: `"${lifecycleState.tenant.name}" will be hidden from active workspaces. Data is fully preserved and the tenant can be reactivated at any time. The database schema will not be dropped.`,
      confirmLabel: 'Archive',
      danger: true,
    },
    reactivate: {
      title: 'Reactivate tenant?',
      description: `Re-enable access for all users at "${lifecycleState.tenant.name}".`,
      confirmLabel: 'Reactivate',
      danger: false,
    },
  }[lifecycleState.action] : null

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
            Show inactive / archived
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
            label="Inactive / Archived"
            value={inactiveCount + archivedCount}
            icon={Archive}
            accentColor="#94a3b8"
            sub={archivedCount > 0 ? `${archivedCount} archived` : 'None archived'}
          />
          <StatCard
            label="Platform Health"
            value={failedCount === 0 && pendingCount === 0 ? 'OK' : failedCount > 0 ? `${failedCount} Failed` : `${pendingCount} Pending`}
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
          <PageEmpty icon={Building2} message="No universities found. Create one to get started." />
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
                  onLifecycle={(tenant, action) => setLifecycleState({ tenant, action })}
                  onEdit={(tenant) => setEditTenant(tenant)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Lifecycle confirm dialog */}
      {lifecycleState && confirmConfig && (
        <ConfirmDialog
          open
          title={confirmConfig.title}
          description={confirmConfig.description}
          confirmLabel={confirmConfig.confirmLabel}
          danger={confirmConfig.danger}
          loading={lifecycleMut.isPending}
          onConfirm={() => lifecycleMut.mutate(lifecycleState)}
          onCancel={() => setLifecycleState(null)}
        />
      )}

      {/* Edit dialog */}
      {editTenant && (
        <EditTenantDialog
          tenant={editTenant}
          saving={editMut.isPending}
          onSave={(updates) => {
            if (Object.keys(updates).length === 0) {
              setEditTenant(null)
              return
            }
            editMut.mutate({ id: editTenant.id, updates })
          }}
          onClose={() => setEditTenant(null)}
        />
      )}
    </main>
  )
}
