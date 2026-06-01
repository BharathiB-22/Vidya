import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RefreshCw, AlertTriangle, CheckCircle2, Archive, RotateCcw, Pencil } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { getTenant, retryTenantProvisioning, updateTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_CFG: Record<TenantStatus, { bg: string; color: string; border: string; icon: React.ReactNode }> = {
  PROVISIONING: {
    bg: 'rgba(245,158,11,0.1)', color: '#fbbf24', border: 'rgba(245,158,11,0.2)',
    icon: <RefreshCw className="h-3 w-3 animate-spin" />,
  },
  ACTIVE: {
    bg: 'rgba(16,185,129,0.1)', color: '#34d399', border: 'rgba(16,185,129,0.2)',
    icon: <CheckCircle2 className="h-3 w-3" />,
  },
  INACTIVE: {
    bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.2)',
    icon: <AlertTriangle className="h-3 w-3" />,
  },
  ARCHIVED: {
    bg: 'rgba(120,113,108,0.12)', color: '#a8a29e', border: 'rgba(120,113,108,0.2)',
    icon: <Archive className="h-3 w-3" />,
  },
  FAILED: {
    bg: 'rgba(239,68,68,0.1)', color: '#f87171', border: 'rgba(239,68,68,0.2)',
    icon: <AlertTriangle className="h-3 w-3" />,
  },
}

function StatusBadge({ status }: { status: TenantStatus }) {
  const { bg, color, border, icon } = STATUS_CFG[status] ?? STATUS_CFG.INACTIVE
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {icon}
      {status}
    </span>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      className="flex items-center justify-between py-3 last:border-0"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
    >
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm text-slate-200 font-medium">{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline edit dialog (name + contact email only)
// ---------------------------------------------------------------------------

function EditDialog({
  tenant, saving, onSave, onClose,
}: {
  tenant: Tenant
  saving: boolean
  onSave: (name: string, contactEmail: string) => void
  onClose: () => void
}) {
  const [name, setName]   = useState(tenant.name)
  const [email, setEmail] = useState(tenant.contact_email ?? '')

  const inputCls   = 'w-full px-3 py-2 text-sm text-slate-200 rounded-lg outline-none'
  const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Edit University</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Slug (read-only)</label>
            <div
              className="px-3 py-2 text-sm font-mono text-slate-500 rounded-lg"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              {tenant.slug}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">University name</label>
            <input
              className={inputCls}
              style={inputStyle}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Contact email</label>
            <input
              type="email"
              className={inputCls}
              style={inputStyle}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={() => onSave(name.trim(), email)} disabled={saving || name.trim().length < 3}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showToggleConfirm,   setShowToggleConfirm]   = useState(false)
  const [showArchiveConfirm,  setShowArchiveConfirm]  = useState(false)
  const [showReactivateConfirm, setShowReactivateConfirm] = useState(false)
  const [showEdit,            setShowEdit]            = useState(false)

  const { data: tenant, isLoading } = useQuery<Tenant>({
    queryKey: ['admin-tenant', id],
    queryFn:  () => getTenant(id!),
    enabled:  !!id,
    refetchInterval: (query) =>
      query.state.data?.status === 'PROVISIONING' ? 3000 : false,
  })

  const retryMut = useMutation({
    mutationFn: () => retryTenantProvisioning(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Provisioning retried — tenant is now ACTIVE.', 'success')
    },
    onError: (err: unknown) => addToast(getAdminErrorMessage(err), 'error'),
  })

  const toggleMut = useMutation({
    mutationFn: () => updateTenant(id!, { status: tenant?.is_active ? 'INACTIVE' : 'ACTIVE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast(tenant?.is_active ? 'Tenant deactivated.' : 'Tenant activated.', 'success')
      setShowToggleConfirm(false)
    },
    onError: (err: unknown) => {
      addToast(getAdminErrorMessage(err), 'error')
      setShowToggleConfirm(false)
    },
  })

  const archiveMut = useMutation({
    mutationFn: () => updateTenant(id!, { status: 'ARCHIVED' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant archived. Data is preserved.', 'success')
      setShowArchiveConfirm(false)
    },
    onError: (err: unknown) => {
      addToast(getAdminErrorMessage(err), 'error')
      setShowArchiveConfirm(false)
    },
  })

  const reactivateMut = useMutation({
    mutationFn: () => updateTenant(id!, { status: 'ACTIVE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant reactivated.', 'success')
      setShowReactivateConfirm(false)
    },
    onError: (err: unknown) => {
      addToast(getAdminErrorMessage(err), 'error')
      setShowReactivateConfirm(false)
    },
  })

  const editMut = useMutation({
    mutationFn: (updates: Parameters<typeof updateTenant>[1]) => updateTenant(id!, updates),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenant', id] })
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant updated.', 'success')
      setShowEdit(false)
    },
    onError: (err: unknown) => addToast(getAdminErrorMessage(err), 'error'),
  })

  if (isLoading) return <PageLoading message="Loading tenant…" />

  if (!tenant) {
    return <div className="text-center py-24 text-sm" style={{ color: '#f87171' }}>Tenant not found.</div>
  }

  const isArchived  = tenant.status === 'ARCHIVED'
  const isInactive  = tenant.status === 'INACTIVE'
  const canActivate = !tenant.is_active && !isArchived
  const canDeactivate = tenant.is_active && !isArchived
  const canArchive    = !isArchived
  const canReactivate = isArchived || isInactive

  return (
    <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">

      {/* Back + title */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/admin/tenants')}
          className="p-1.5 rounded-lg text-slate-600 transition-colors"
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#cbd5e1' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = ''; e.currentTarget.style.color = '' }}
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h2 className="text-xl font-semibold text-slate-100">{tenant.name}</h2>
        <StatusBadge status={tenant.status} />
        <button
          onClick={() => setShowEdit(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          style={{ background: 'rgba(99,102,241,0.08)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}
        >
          <Pencil className="h-3 w-3" /> Edit
        </button>
      </div>

      {/* Info card */}
      <div
        className="rounded-xl px-6 py-2"
        style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        <InfoRow label="Institution name" value={tenant.name} />
        <InfoRow
          label="Slug"
          value={
            <code
              className="text-xs px-1.5 py-0.5 rounded font-mono"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#94a3b8' }}
            >
              {tenant.slug}
            </code>
          }
        />
        <InfoRow
          label="Schema"
          value={
            <code
              className="text-xs px-1.5 py-0.5 rounded font-mono"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#94a3b8' }}
            >
              {tenant.schema_name}
            </code>
          }
        />
        <InfoRow label="Status"        value={<StatusBadge status={tenant.status} />} />
        <InfoRow label="Contact email" value={tenant.contact_email ?? '—'} />
        <InfoRow label="Provisioned"   value={new Date(tenant.created_at).toLocaleString()} />
      </div>

      {/* Actions card */}
      <div
        className="rounded-xl p-6 space-y-4"
        style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        <h3 className="text-sm font-semibold text-slate-400">Actions</h3>

        {/* Retry provisioning */}
        {tenant.status === 'FAILED' && (
          <div
            className="rounded-lg p-4 space-y-3"
            style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}
          >
            <p className="text-sm font-medium flex items-center gap-1.5" style={{ color: '#fca5a5' }}>
              <AlertTriangle className="h-4 w-4" />
              Provisioning failed
            </p>
            <p className="text-xs" style={{ color: '#f87171' }}>
              The schema or admin seed step did not complete. Click Retry to attempt provisioning
              again without creating a new tenant record.
            </p>
            <button
              onClick={() => retryMut.mutate()}
              disabled={retryMut.isPending}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
              style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5' }}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${retryMut.isPending ? 'animate-spin' : ''}`} />
              {retryMut.isPending ? 'Retrying…' : 'Retry provisioning'}
            </button>
          </div>
        )}

        {/* Deactivate */}
        {canDeactivate && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Deactivate tenant</p>
              <p className="text-xs text-slate-500 mt-0.5">Users will no longer be able to log in.</p>
            </div>
            <button
              onClick={() => setShowToggleConfirm(true)}
              disabled={toggleMut.isPending}
              className="px-3.5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-40"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171' }}
            >
              Deactivate
            </button>
          </div>
        )}

        {/* Activate (from INACTIVE without full reactivate) */}
        {canActivate && !canReactivate && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Activate tenant</p>
              <p className="text-xs text-slate-500 mt-0.5">Re-enable access for all users.</p>
            </div>
            <button
              onClick={() => setShowToggleConfirm(true)}
              disabled={toggleMut.isPending}
              className="px-3.5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-40"
              style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)', color: '#34d399' }}
            >
              Activate
            </button>
          </div>
        )}

        {/* Archive */}
        {canArchive && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Archive tenant</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Hides tenant from active workspaces. Data is preserved; can be reactivated later.
              </p>
            </div>
            <button
              onClick={() => setShowArchiveConfirm(true)}
              disabled={archiveMut.isPending}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-40"
              style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)', color: '#fbbf24' }}
            >
              <Archive className="h-3.5 w-3.5" />
              {archiveMut.isPending ? 'Archiving…' : 'Archive'}
            </button>
          </div>
        )}

        {/* Reactivate */}
        {canReactivate && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Reactivate tenant</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Restore full access for all users in this institution.
              </p>
            </div>
            <button
              onClick={() => setShowReactivateConfirm(true)}
              disabled={reactivateMut.isPending}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-40"
              style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)', color: '#34d399' }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {reactivateMut.isPending ? 'Reactivating…' : 'Reactivate'}
            </button>
          </div>
        )}
      </div>

      {/* Confirm dialogs */}
      <ConfirmDialog
        open={showToggleConfirm}
        title={tenant.is_active ? 'Deactivate tenant?' : 'Activate tenant?'}
        description={
          tenant.is_active
            ? `All users at "${tenant.name}" will be locked out immediately.`
            : `Re-enable login for all users at "${tenant.name}".`
        }
        confirmLabel={tenant.is_active ? 'Deactivate' : 'Activate'}
        danger={tenant.is_active}
        loading={toggleMut.isPending}
        onConfirm={() => toggleMut.mutate()}
        onCancel={() => setShowToggleConfirm(false)}
      />

      <ConfirmDialog
        open={showArchiveConfirm}
        title="Archive tenant?"
        description={`"${tenant.name}" will be hidden from active workspaces. The database schema is preserved and the tenant can be reactivated at any time.`}
        confirmLabel="Archive"
        danger
        loading={archiveMut.isPending}
        onConfirm={() => archiveMut.mutate()}
        onCancel={() => setShowArchiveConfirm(false)}
      />

      <ConfirmDialog
        open={showReactivateConfirm}
        title="Reactivate tenant?"
        description={`Restore full access for all users at "${tenant.name}".`}
        confirmLabel="Reactivate"
        loading={reactivateMut.isPending}
        onConfirm={() => reactivateMut.mutate()}
        onCancel={() => setShowReactivateConfirm(false)}
      />

      {/* Edit dialog */}
      {showEdit && (
        <EditDialog
          tenant={tenant}
          saving={editMut.isPending}
          onSave={(name, contactEmail) => {
            const updates: Parameters<typeof updateTenant>[1] = {}
            if (name !== tenant.name) updates.name = name
            if (contactEmail !== (tenant.contact_email ?? '')) updates.contact_email = contactEmail
            if (Object.keys(updates).length === 0) { setShowEdit(false); return }
            editMut.mutate(updates)
          }}
          onClose={() => setShowEdit(false)}
        />
      )}
    </main>
  )
}
