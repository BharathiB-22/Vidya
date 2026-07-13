import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PlusCircle, Building2, CheckCircle2, AlertTriangle, Shield, Search,
  Pencil, Archive, RotateCcw, Trash2, TriangleAlert, X,
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
import { listTenants, updateTenant, deleteTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'
import { tint } from '@/lib/platformPalette'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_CFG: Record<TenantStatus, { bg: string; color: string; border: string }> = {
  ACTIVE:               { bg: 'var(--pc-t-emerald-12)',  color: 'var(--pc-emerald-400)', border: 'var(--pc-t-emerald-25)' },
  PROVISIONING:         { bg: 'var(--pc-t-amber-12)',  color: 'var(--pc-amber-400)', border: 'var(--pc-t-amber-25)' },
  FAILED:               { bg: 'var(--pc-t-red-12)',   color: 'var(--pc-red-400)', border: 'var(--pc-t-red-25)'  },
  INACTIVE:             { bg: 'var(--pc-t-slate-14)', color: 'var(--pc-slate-400)', border: 'var(--pc-t-slate-25)' },
  ARCHIVED:             { bg: 'var(--pc-t-stone-14)', color: 'var(--pc-stone-400)', border: 'var(--pc-t-stone-25)' },
  DELETED:              { bg: 'var(--pc-t-red-08)',   color: 'var(--pc-gray-400)', border: 'var(--pc-t-red-15)'  },
  PERMANENTLY_DELETED:  { bg: 'var(--pc-t-slate-06)', color: 'var(--pc-slate-600)', border: 'var(--pc-t-slate-12)' },
}

function StatusBadge({ status }: { status: TenantStatus }) {
  const { bg, color, border } = STATUS_CFG[status] ?? STATUS_CFG.INACTIVE
  return (
    <span
      className="text-[11px] px-2.5 py-0.5 rounded-full font-bold tracking-wide"
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
      style={{
        background: 'linear-gradient(135deg, var(--pc-t-surf3-95), var(--pc-t-surf4-95))',
        border: '1px solid var(--pc-t-overlay-08)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.25)',
      }}
    >
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: tint(accentColor, 10.2), border: `1px solid ${tint(accentColor, 20.78)}` }}
      >
        <Icon className="h-5 w-5" style={{ color: accentColor }} />
      </div>
      <div className="min-w-0">
        <p className="text-3xl font-bold text-white leading-tight">{value}</p>
        <p className="text-xs font-semibold text-slate-400 truncate mt-0.5">{label}</p>
        {sub && <p className="text-[11px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tenant row
// ---------------------------------------------------------------------------

type LifecycleAction = 'deactivate' | 'archive' | 'reactivate'

function TenantRow({
  tenant, onSelect, onLifecycle, onEdit, onDelete,
}: {
  tenant: Tenant
  onSelect: (t: Tenant) => void
  onLifecycle: (t: Tenant, action: LifecycleAction) => void
  onEdit: (t: Tenant) => void
  onDelete: (t: Tenant) => void
}) {
  const isDeleted   = tenant.status === 'DELETED'
  const isArchived  = tenant.status === 'ARCHIVED'
  const isInactive  = tenant.status === 'INACTIVE' || !tenant.is_active
  const canDeactivate = tenant.is_active && !isArchived && !isDeleted
  const canArchive    = !isArchived && !isDeleted
  const canReactivate = !isDeleted && (isArchived || (isInactive && tenant.status !== 'FAILED' && tenant.status !== 'PROVISIONING'))
  const canDelete     = !isDeleted

  const btnBase = 'text-[11px] px-2 py-1 rounded-md font-semibold transition-all flex items-center gap-1 whitespace-nowrap'

  return (
    <tr
      className={`cursor-pointer transition-colors ${isDeleted ? 'opacity-50' : ''}`}
      style={{ borderBottom: '1px solid var(--pc-t-overlay-05)' }}
      onMouseEnter={(e) => { if (!isDeleted) (e.currentTarget as HTMLElement).style.background = 'var(--pc-t-overlay-2p5)' }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
      onClick={() => !isDeleted && onSelect(tenant)}
    >
      <td className="px-5 py-4">
        <div className="font-semibold text-base text-slate-100">{tenant.name}</div>
        <div className="text-sm text-slate-500 font-mono mt-0.5">{tenant.slug}</div>
      </td>
      <td className="px-5 py-4"><StatusBadge status={tenant.status} /></td>
      <td className="px-5 py-4 text-sm text-slate-400">{tenant.contact_email ?? '—'}</td>
      <td className="px-5 py-4 text-sm text-slate-500">
        {new Date(tenant.created_at).toLocaleDateString()}
      </td>
      <td className="px-5 py-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Edit */}
          {!isDeleted && (
            <button
              onClick={() => onEdit(tenant)}
              className={btnBase}
              style={{ background: 'var(--pc-t-indigo-10)', color: 'var(--pc-indigo-300)', border: '1px solid var(--pc-t-indigo-25)' }}
            >
              <Pencil className="h-3 w-3" /> Edit
            </button>
          )}

          {/* Deactivate */}
          {canDeactivate && (
            <button
              onClick={() => onLifecycle(tenant, 'deactivate')}
              className={btnBase}
              style={{ background: 'var(--pc-t-red-08)', color: 'var(--pc-red-300)', border: '1px solid var(--pc-t-red-20)' }}
            >
              Deactivate
            </button>
          )}

          {/* Archive */}
          {canArchive && (
            <button
              onClick={() => onLifecycle(tenant, 'archive')}
              className={btnBase}
              style={{ background: 'var(--pc-t-amber-08)', color: 'var(--pc-amber-400)', border: '1px solid var(--pc-t-amber-20)' }}
            >
              <Archive className="h-3 w-3" /> Archive
            </button>
          )}

          {/* Reactivate */}
          {canReactivate && (
            <button
              onClick={() => onLifecycle(tenant, 'reactivate')}
              className={btnBase}
              style={{ background: 'var(--pc-t-emerald-08)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-20)' }}
            >
              <RotateCcw className="h-3 w-3" /> Reactivate
            </button>
          )}

          {/* Delete */}
          {canDelete && (
            <button
              onClick={() => onDelete(tenant)}
              className={btnBase}
              style={{ background: 'var(--pc-t-red-10)', color: 'var(--pc-red-400)', border: '1px solid var(--pc-t-red-30)' }}
            >
              <Trash2 className="h-3 w-3" /> Delete
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
  tenant, saving, onSave, onClose,
}: {
  tenant: Tenant; saving: boolean; onSave: (updates: Partial<EditForm>) => void; onClose: () => void
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
  const inputStyle = { background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }
  const labelCls = 'block text-xs font-semibold text-slate-400 mb-1'

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
          <div>
            <label className={labelCls}>Slug (read-only)</label>
            <div className="px-3 py-2 text-sm font-mono text-slate-500 rounded-lg"
              style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-06)' }}>
              {tenant.slug}
            </div>
          </div>
          <div>
            <label className={labelCls}>Status</label>
            <div className="flex items-center gap-2 py-1">
              <StatusBadge status={tenant.status} />
              <span className="text-xs text-slate-600">(change via lifecycle buttons)</span>
            </div>
          </div>
          <div>
            <label className={labelCls}>University name</label>
            <input className={inputCls} style={inputStyle} {...field('name')} maxLength={100} />
          </div>
          <div>
            <label className={labelCls}>Contact email</label>
            <input type="email" className={inputCls} style={inputStyle} {...field('contact_email')} />
          </div>
          <div>
            <label className={labelCls}>Logo URL</label>
            <input className={inputCls} style={inputStyle} {...field('logo_url')} placeholder="https://…" />
          </div>
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
// Delete confirmation dialog — custom modal (no Radix Dialog)
// Radix UI's modal pointer-event guards can block inputs inside controlled
// dialogs. This implementation is a plain CSS portal overlay so the slug
// input is always fully interactive.
// ---------------------------------------------------------------------------

function DeleteTenantDialog({
  tenant, deleting, onConfirm, onClose,
}: {
  tenant: Tenant; deleting: boolean; onConfirm: (slug: string) => void; onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const match = typed === tenant.slug

  // Escape key closes the dialog
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !deleting) onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [deleting, onClose])

  return (
    /* Backdrop — click outside to close */
    <div
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.72)', zIndex: 9999 }}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !deleting) onClose() }}
    >
      {/* Modal panel */}
      <div
        className="w-full max-w-md rounded-xl"
        style={{
          background: 'linear-gradient(180deg, var(--pc-panel-from) 0%, var(--pc-panel-to) 100%)',
          border: '1px solid var(--pc-t-overlay-10)',
          boxShadow: '0 30px 70px rgba(0,0,0,0.65)',
          zIndex: 10000,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center gap-2 px-5 py-4"
          style={{ borderBottom: '1px solid var(--pc-t-overlay-07)' }}
        >
          <TriangleAlert className="h-5 w-5 text-red-400 flex-shrink-0" />
          <h2 className="text-base font-semibold text-red-400 flex-1">Delete tenant permanently</h2>
          <button
            onClick={onClose}
            disabled={deleting}
            className="p-1 rounded text-slate-600 hover:text-slate-300 hover:bg-white/10 disabled:pointer-events-none transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Warning banner */}
          <div
            className="rounded-lg px-4 py-3 space-y-2"
            style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
          >
            <p className="text-sm font-semibold text-red-300 flex items-center gap-1.5">
              <TriangleAlert className="h-4 w-4 flex-shrink-0" /> This action is permanent
            </p>
            <ul className="text-sm text-slate-400 space-y-1 pl-1">
              <li>• Tenant data may be deleted or become inaccessible.</li>
              <li>• All users at this institution will lose access immediately.</li>
              <li>• The tenant schema is not dropped, but the tenant is marked DELETED.</li>
              <li className="text-amber-400 font-medium">• Only use this for test or demo tenants.</li>
            </ul>
          </div>

          {/* Tenant being deleted */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Tenant</p>
            <div
              className="px-3 py-2.5 rounded-lg flex items-center justify-between gap-3"
              style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-07)' }}
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-200">{tenant.name}</p>
                <p className="text-xs font-mono text-slate-500 mt-0.5">{tenant.slug}</p>
              </div>
              <StatusBadge status={tenant.status} />
            </div>
          </div>

          {/* Slug confirmation input */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">
              Type <span className="font-mono text-slate-200">{tenant.slug}</span> to confirm
            </label>
            <input
              type="text"
              autoFocus
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={tenant.slug}
              autoComplete="off"
              spellCheck={false}
              disabled={deleting}
              className="w-full px-3 py-2.5 text-sm font-mono text-slate-100 rounded-lg outline-none transition-all disabled:opacity-50"
              style={{
                background: 'var(--pc-t-overlay-07)',
                border: typed.length === 0
                  ? '1px solid var(--pc-t-overlay-12)'
                  : match
                    ? '1px solid var(--pc-t-red-50)'
                    : '1px solid var(--pc-t-amber-40)',
              }}
            />
            {typed.length > 0 && !match && (
              <p className="text-[11px] text-amber-400 mt-1">Slug does not match — keep typing.</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex justify-end gap-2 px-5 py-4"
          style={{ borderTop: '1px solid var(--pc-t-overlay-07)' }}
        >
          <Button variant="ghost" onClick={onClose} disabled={deleting}>
            Cancel
          </Button>
          <Button
            disabled={!match || deleting}
            onClick={() => onConfirm(typed)}
            style={match && !deleting ? {
              background: 'linear-gradient(135deg, var(--pc-red-600), var(--pc-red-700))',
              color: 'white',
              border: '1px solid var(--pc-t-red-40)',
            } : {}}
          >
            {deleting ? 'Deleting…' : 'Delete tenant'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TenantListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [includeInactive, setIncludeInactive]       = useState(true)
  const [showDeleted,     setShowDeleted]            = useState(false)
  const [sortByName,      setSortByName]             = useState(false)
  const [search,          setSearch]                 = useState('')
  const [editTenant,      setEditTenant]             = useState<Tenant | null>(null)
  const [lifecycleState,  setLifecycleState]         = useState<{ tenant: Tenant; action: LifecycleAction } | null>(null)
  const [deleteTarget,    setDeleteTarget]           = useState<Tenant | null>(null)

  // When showDeleted is on we must fetch with include_inactive=true so the
  // backend returns DELETED rows (they have is_active=false).
  const { data: tenants, isLoading, isError, refetch } = useQuery<Tenant[]>({
    queryKey: ['admin-tenants', includeInactive, showDeleted],
    queryFn:  () => listTenants(includeInactive || showDeleted),
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

  const deleteMut = useMutation({
    mutationFn: ({ id, slug }: { id: string; slug: string }) => deleteTenant(id, slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant deleted.', 'success')
      setDeleteTarget(null)
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
    onSettled: () => setDeleteTarget(null),
  })

  const all = tenants ?? []

  // Two-pass visibility filter (applied before search)
  let baseRows = all
  if (!showDeleted)     baseRows = baseRows.filter((t) => t.status !== 'DELETED')
  if (!includeInactive) baseRows = baseRows.filter((t) => t.status !== 'INACTIVE' && t.status !== 'ARCHIVED')

  const query    = search.toLowerCase().trim()
  const filtered = query
    ? baseRows.filter((t) => t.name.toLowerCase().includes(query) || t.slug.toLowerCase().includes(query))
    : baseRows
  const rows = sortByName ? [...filtered].sort((a, b) => a.name.localeCompare(b.name)) : filtered

  // Stat counts always exclude DELETED so the numbers reflect live institutions
  const allNonDeleted = all.filter((t) => t.status !== 'DELETED')
  const activeCount   = allNonDeleted.filter((t) => t.status === 'ACTIVE').length
  const inactiveCount = allNonDeleted.filter((t) => t.status === 'INACTIVE').length
  const archivedCount = allNonDeleted.filter((t) => t.status === 'ARCHIVED').length
  const pendingCount  = allNonDeleted.filter((t) => t.status === 'PROVISIONING').length
  const failedCount   = allNonDeleted.filter((t) => t.status === 'FAILED').length
  const deletedCount  = all.filter((t) => t.status === 'DELETED').length

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
      <div className="relative mb-5">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or slug…"
          className="w-full pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 rounded-xl outline-none transition-all"
          style={{ background: 'var(--pc-t-overlay-04)', border: '1px solid var(--pc-t-overlay-08)' }}
          onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--pc-t-emerald-35)' }}
          onBlur={(e)  => { e.currentTarget.style.borderColor = 'var(--pc-t-overlay-08)' }}
        />
      </div>

      {/* Header row */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Universities</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            {isLoading
              ? 'Loading…'
              : `${allNonDeleted.length} institution${allNonDeleted.length !== 1 ? 's' : ''} · ${activeCount} active${deletedCount > 0 ? ` · ${deletedCount} deleted` : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={sortByName}
              onChange={(e) => setSortByName(e.target.checked)}
              className="rounded accent-emerald-500"
            />
            Sort A–Z
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="rounded accent-emerald-500"
            />
            Show inactive / archived
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={(e) => setShowDeleted(e.target.checked)}
              className="rounded accent-red-500"
            />
            <span className={showDeleted ? 'text-red-400' : ''}>Show deleted</span>
          </label>
          <button
            onClick={() => navigate('/admin/tenants/new')}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold text-white transition-all"
            style={{
              background: 'linear-gradient(135deg, var(--pc-accent), var(--pc-accent-hover))',
              boxShadow: '0 0 20px color-mix(in srgb, var(--pc-accent) 25%, transparent)',
              color: 'var(--pc-accent-fg)',
            }}
          >
            <PlusCircle className="h-4 w-4" />
            New University
          </button>
        </div>
      </div>

      {/* Stat cards */}
      {!isLoading && (
        <div className={`grid grid-cols-2 gap-4 mb-7 ${showDeleted ? 'lg:grid-cols-5' : 'lg:grid-cols-4'}`}>
          <StatCard label="Total Universities" value={allNonDeleted.length} icon={Building2}    accentColor="var(--pc-indigo-500)" />
          <StatCard label="Active Tenants"     value={activeCount}          icon={CheckCircle2} accentColor="var(--pc-emerald-500)" />
          <StatCard
            label="Inactive / Archived"
            value={inactiveCount + archivedCount}
            icon={Archive}
            accentColor="var(--pc-slate-400)"
            sub={archivedCount > 0 ? `${archivedCount} archived` : 'None archived'}
          />
          <StatCard
            label="Platform Health"
            value={failedCount === 0 && pendingCount === 0 ? 'OK' : failedCount > 0 ? `${failedCount} Failed` : `${pendingCount} Pending`}
            icon={failedCount === 0 ? Shield : AlertTriangle}
            accentColor={failedCount === 0 ? 'var(--pc-emerald-500)' : 'var(--pc-red-500)'}
            sub={failedCount === 0 ? 'Operational' : 'Needs attention'}
          />
          {showDeleted && (
            <StatCard
              label="Deleted Tenants"
              value={deletedCount}
              icon={Trash2}
              accentColor="var(--pc-red-500)"
              sub="Soft-deleted, schema intact"
            />
          )}
        </div>
      )}

      {isError && (
        <div className="mb-4">
          <PageError message="Failed to load tenants." onRetry={() => refetch()} />
        </div>
      )}

      {/* Table */}
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
          border: '1px solid var(--pc-t-overlay-08)',
          boxShadow: '0 8px 40px rgba(0,0,0,0.3)',
        }}
      >
        {isLoading ? (
          <PageLoading message="Loading universities…" />
        ) : rows.length === 0 ? (
          <PageEmpty icon={Building2} message="No universities found. Create one to get started." />
        ) : (
          <table className="w-full">
            <thead style={{ borderBottom: '1px solid var(--pc-t-overlay-07)', background: 'var(--pc-t-overlay-2p5)' }}>
              <tr>
                {['Institution', 'Status', 'Contact', 'Created', 'Actions'].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3.5 text-left text-[11px] font-bold uppercase tracking-widest"
                    style={{ color: 'var(--pc-slate-500)' }}
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
                  onDelete={(tenant) => setDeleteTarget(tenant)}
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

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <DeleteTenantDialog
          tenant={deleteTarget}
          deleting={deleteMut.isPending}
          onConfirm={(slug) => deleteMut.mutate({ id: deleteTarget.id, slug })}
          onClose={() => setDeleteTarget(null)}
        />
      )}
    </main>
  )
}
