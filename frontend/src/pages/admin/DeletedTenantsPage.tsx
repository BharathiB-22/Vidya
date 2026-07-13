import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Trash2, RotateCcw, Search, AlertTriangle, Building2, RefreshCw, X, TriangleAlert, Shield,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { getAdminErrorMessage } from '@/lib/adminApi'
import { listTenants, restoreTenant, permanentlyDeleteTenant } from '@/lib/api/tenants'
import type { Tenant } from '@/lib/api/tenants'

// ---------------------------------------------------------------------------
// Permanent delete dialog (slug confirmation)
// ---------------------------------------------------------------------------

function PermanentDeleteDialog({
  tenant,
  deleting,
  onConfirm,
  onClose,
}: {
  tenant: Tenant
  deleting: boolean
  onConfirm: (slug: string) => void
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const match = typed === tenant.slug

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !deleting) onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [deleting, onClose])

  return (
    <div
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.80)', zIndex: 9999 }}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !deleting) onClose() }}
    >
      <div
        className="w-full max-w-md rounded-xl"
        style={{
          background: 'linear-gradient(180deg, var(--pc-panel-from) 0%, var(--pc-panel-to) 100%)',
          border: '1px solid var(--pc-t-red-30)',
          boxShadow: '0 30px 70px rgba(0,0,0,0.65)',
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center gap-2 px-5 py-4"
          style={{ borderBottom: '1px solid var(--pc-t-overlay-07)' }}
        >
          <TriangleAlert className="h-5 w-5 text-red-400 flex-shrink-0" />
          <h2 className="text-base font-semibold text-red-400 flex-1">Permanently delete tenant</h2>
          <button
            onClick={onClose}
            disabled={deleting}
            className="p-1 rounded text-slate-600 hover:text-slate-300 transition-colors disabled:pointer-events-none"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div
            className="rounded-lg px-4 py-3 space-y-1.5"
            style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
          >
            <p className="text-sm font-semibold text-red-300">⚠ This action cannot be undone</p>
            <ul className="text-sm text-slate-400 space-y-0.5 pl-1">
              <li>• Permanent Delete removes this tenant from all application views.</li>
              <li>• Database audit records are <span className="text-emerald-400 font-medium">preserved for compliance</span>.</li>
              <li>• Tenant schema is <span className="text-amber-400 font-medium">NOT dropped</span> — data remains on disk.</li>
              <li>• The tenant row is marked PERMANENTLY_DELETED, not physically removed.</li>
              <li>• Restore will be permanently unavailable after this action.</li>
            </ul>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Tenant being deleted</p>
            <div
              className="px-3 py-2.5 rounded-lg"
              style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-07)' }}
            >
              <p className="text-sm font-semibold text-slate-200">{tenant.name}</p>
              <p className="text-xs font-mono text-slate-500 mt-0.5">{tenant.slug}</p>
              {tenant.deleted_at && (
                <p className="text-xs text-slate-600 mt-1">
                  Soft-deleted {new Date(tenant.deleted_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>

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

        <div
          className="flex justify-end gap-2 px-5 py-4"
          style={{ borderTop: '1px solid var(--pc-t-overlay-07)' }}
        >
          <Button variant="ghost" onClick={onClose} disabled={deleting}>Cancel</Button>
          <Button
            disabled={!match || deleting}
            onClick={() => onConfirm(typed)}
            style={match && !deleting ? {
              background: 'linear-gradient(135deg, var(--pc-red-600), var(--pc-red-700))',
              color: 'white',
              border: '1px solid var(--pc-t-red-40)',
            } : {}}
          >
            {deleting ? 'Deleting…' : 'Permanently delete'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tenant row for deleted list
// ---------------------------------------------------------------------------

function DeletedTenantRow({
  tenant,
  onRestore,
  onPermanentDelete,
}: {
  tenant: Tenant
  onRestore: (t: Tenant) => void
  onPermanentDelete: (t: Tenant) => void
}) {
  const btnBase = 'text-[11px] px-2 py-1 rounded-md font-semibold transition-all flex items-center gap-1 whitespace-nowrap'

  return (
    <tr style={{ borderBottom: '1px solid var(--pc-t-overlay-04)' }}>
      <td className="px-5 py-4">
        <div className="font-semibold text-slate-300">{tenant.name}</div>
        <div className="text-xs font-mono text-slate-600 mt-0.5">{tenant.slug}</div>
      </td>
      <td className="px-5 py-4 text-sm text-slate-400">
        {tenant.deleted_at ? new Date(tenant.deleted_at).toLocaleDateString() : '—'}
      </td>
      <td className="px-5 py-4 text-sm text-slate-500">
        Super Admin
      </td>
      <td className="px-5 py-4 text-sm text-slate-500 font-mono text-xs">
        {tenant.schema_name}
      </td>
      <td className="px-5 py-4">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onRestore(tenant)}
            className={btnBase}
            style={{ background: 'var(--pc-t-emerald-08)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-20)' }}
          >
            <RotateCcw className="h-3 w-3" /> Restore
          </button>
          <button
            onClick={() => onPermanentDelete(tenant)}
            className={btnBase}
            style={{ background: 'var(--pc-t-red-10)', color: 'var(--pc-red-400)', border: '1px solid var(--pc-t-red-30)' }}
          >
            <Trash2 className="h-3 w-3" /> Permanent Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DeletedTenantsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [restoreTarget, setRestoreTarget] = useState<Tenant | null>(null)
  const [permanentTarget, setPermanentTarget] = useState<Tenant | null>(null)

  const { data: tenants, isLoading, isError, refetch } = useQuery<Tenant[]>({
    queryKey: ['admin-tenants', true, true],
    queryFn: () => listTenants(true),
  })

  const deleted = (tenants ?? []).filter((t) => t.status === 'DELETED')
  const query = search.toLowerCase().trim()
  const rows = query
    ? deleted.filter((t) => t.name.toLowerCase().includes(query) || t.slug.toLowerCase().includes(query))
    : deleted

  const restoreMut = useMutation({
    mutationFn: (t: Tenant) => restoreTenant(t.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant restored to INACTIVE status.', 'success')
      setRestoreTarget(null)
    },
    onError: (err) => {
      addToast(getAdminErrorMessage(err), 'error')
      setRestoreTarget(null)
    },
  })

  const permanentMut = useMutation({
    mutationFn: ({ id, slug }: { id: string; slug: string }) => permanentlyDeleteTenant(id, slug),
    onSuccess: (_data) => {
      qc.invalidateQueries({ queryKey: ['admin-tenants'] })
      addToast('Tenant permanently deleted. Audit records are preserved.', 'success')
      setPermanentTarget(null)
    },
    onError: (err) => {
      addToast(getAdminErrorMessage(err), 'error')
      setPermanentTarget(null)
    },
  })

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Trash2 className="h-6 w-6 text-red-400" />
            Deleted Tenants
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {isLoading ? 'Loading…' : `${deleted.length} soft-deleted tenant${deleted.length !== 1 ? 's' : ''} — schemas are preserved on disk`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin/tenants')}
            className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-400 transition-all"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            ← Active Tenants
          </button>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold text-slate-400"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {/* Warning banner */}
      <div
        className="rounded-xl px-5 py-4 mb-6 flex items-start gap-3"
        style={{ background: 'var(--pc-t-red-06)', border: '1px solid var(--pc-t-red-15)' }}
      >
        <AlertTriangle className="h-4.5 w-4.5 text-red-400 flex-shrink-0 mt-0.5" style={{ width: 18, height: 18 }} />
        <div>
          <p className="text-sm font-semibold text-red-300">These tenants have been soft-deleted</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Database schemas are intact. Restore to make a tenant accessible again. Permanent Delete marks the tenant as PERMANENTLY_DELETED — it
            removes it from all application lists but <span className="text-emerald-400 font-medium">preserves audit logs for compliance</span> and does{' '}
            <span className="text-amber-400 font-medium">not</span> drop the database schema.
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search deleted tenants by name or slug…"
          className="w-full pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 rounded-xl outline-none transition-all"
          style={{ background: 'var(--pc-t-overlay-04)', border: '1px solid var(--pc-t-overlay-08)' }}
          onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--pc-t-red-35)' }}
          onBlur={(e)  => { e.currentTarget.style.borderColor = 'var(--pc-t-overlay-08)' }}
        />
      </div>

      {isError && (
        <div
          className="rounded-xl px-6 py-5 mb-4 flex items-center gap-3"
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
        >
          <Shield className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-sm font-semibold text-red-300">Failed to load tenants.</p>
          <button onClick={() => refetch()} className="ml-auto text-xs text-slate-400 hover:text-slate-200">Retry</button>
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
          <PageLoading message="Loading deleted tenants…" />
        ) : rows.length === 0 ? (
          <PageEmpty icon={Building2} message={search ? 'No deleted tenants match your search.' : 'No deleted tenants — great!'} />
        ) : (
          <table className="w-full">
            <thead style={{ borderBottom: '1px solid var(--pc-t-overlay-07)', background: 'var(--pc-t-overlay-2p5)' }}>
              <tr>
                {['Institution', 'Deleted Date', 'Deleted By', 'Schema', 'Actions'].map((h) => (
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
                <DeletedTenantRow
                  key={t.id}
                  tenant={t}
                  onRestore={(tenant) => setRestoreTarget(tenant)}
                  onPermanentDelete={(tenant) => setPermanentTarget(tenant)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Restore confirm dialog */}
      {restoreTarget && (
        <ConfirmDialog
          open
          title={`Restore "${restoreTarget.name}"?`}
          description={`The tenant will be restored to INACTIVE status. Users will not be able to log in until the tenant is explicitly reactivated from the Tenants page.`}
          confirmLabel="Restore"
          danger={false}
          loading={restoreMut.isPending}
          onConfirm={() => restoreMut.mutate(restoreTarget)}
          onCancel={() => setRestoreTarget(null)}
        />
      )}

      {/* Permanent delete dialog */}
      {permanentTarget && (
        <PermanentDeleteDialog
          tenant={permanentTarget}
          deleting={permanentMut.isPending}
          onConfirm={(slug) => permanentMut.mutate({ id: permanentTarget.id, slug })}
          onClose={() => setPermanentTarget(null)}
        />
      )}
    </main>
  )
}
