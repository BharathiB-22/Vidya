import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Database, CheckCircle2, AlertTriangle, Clock, RefreshCw, Loader2,
} from 'lucide-react'
import { listTenantMigrations, retryTenantMigration } from '@/lib/api/tenants'
import type { TenantMigrationStatus } from '@/lib/api/tenants'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortRev(rev: string | null): string {
  if (!rev) return '—'
  return rev.length > 10 ? rev.slice(0, 10) + '…' : rev
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

type BadgeVariant = 'current' | 'pending' | 'failed' | 'unknown'

function MigBadge({ variant }: { variant: BadgeVariant }) {
  const cfg: Record<BadgeVariant, { label: string; bg: string; color: string; border: string }> = {
    current: { label: 'Up to date',  bg: 'rgba(16,185,129,0.12)',  color: '#34d399', border: 'rgba(16,185,129,0.3)' },
    pending: { label: 'Pending',     bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24', border: 'rgba(245,158,11,0.3)' },
    failed:  { label: 'Failed',      bg: 'rgba(239,68,68,0.12)',   color: '#f87171', border: 'rgba(239,68,68,0.3)'  },
    unknown: { label: 'Unknown',     bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.25)' },
  }
  const { label, bg, color, border } = cfg[variant]
  return (
    <span
      className="text-[11px] px-2.5 py-0.5 rounded-full font-semibold"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {label}
    </span>
  )
}

function getVariant(row: TenantMigrationStatus): BadgeVariant {
  if (row.is_current) return 'current'
  if (row.last_status === 'failed') return 'failed'
  if (!row.current_revision) return 'unknown'
  return 'pending'
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function MigRow({
  row,
  onRetry,
  retrying,
}: {
  row: TenantMigrationStatus
  onRetry: (id: string) => void
  retrying: boolean
}) {
  const [showError, setShowError] = useState(false)
  const variant = getVariant(row)
  const canRetry = !row.is_current

  return (
    <>
      <tr
        className="border-b transition-colors"
        style={{ borderColor: 'rgba(255,255,255,0.04)' }}
      >
        {/* Tenant */}
        <td className="py-3 px-4">
          <p className="text-sm font-medium text-gray-100">{row.tenant_name}</p>
          <p className="text-xs text-gray-500 font-mono mt-0.5">{row.schema_name}</p>
        </td>

        {/* Current version */}
        <td className="py-3 px-4">
          <span className="text-xs font-mono text-gray-300">
            {shortRev(row.current_revision)}
          </span>
        </td>

        {/* Latest version */}
        <td className="py-3 px-4">
          <span className="text-xs font-mono text-gray-300">
            {shortRev(row.head_revision)}
          </span>
        </td>

        {/* Status */}
        <td className="py-3 px-4">
          <MigBadge variant={variant} />
        </td>

        {/* Last migration */}
        <td className="py-3 px-4">
          <span className="text-xs text-gray-400">{fmtDate(row.last_migration_at)}</span>
        </td>

        {/* Actions */}
        <td className="py-3 px-4">
          <div className="flex items-center gap-2">
            {canRetry && (
              <button
                onClick={() => onRetry(row.tenant_id)}
                disabled={retrying}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-medium transition-all disabled:opacity-50"
                style={{
                  background: 'rgba(99,102,241,0.15)',
                  color: '#818cf8',
                  border: '1px solid rgba(99,102,241,0.3)',
                }}
              >
                {retrying
                  ? <Loader2 className="h-3 w-3 animate-spin" />
                  : <RefreshCw className="h-3 w-3" />}
                Retry
              </button>
            )}
            {row.last_error && (
              <button
                onClick={() => setShowError(v => !v)}
                className="text-xs text-red-400 underline underline-offset-2"
              >
                {showError ? 'Hide error' : 'Show error'}
              </button>
            )}
          </div>
        </td>
      </tr>

      {/* Expandable error row */}
      {showError && row.last_error && (
        <tr style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
          <td colSpan={6} className="px-4 pb-3">
            <pre
              className="text-xs p-3 rounded-lg overflow-x-auto whitespace-pre-wrap"
              style={{ background: 'rgba(239,68,68,0.08)', color: '#fca5a5', border: '1px solid rgba(239,68,68,0.2)' }}
            >
              {row.last_error}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TenantMigrationsPage() {
  const qc = useQueryClient()
  const [retryingId, setRetryingId] = useState<string | null>(null)

  const { data: rows = [], isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-migrations'],
    queryFn: listTenantMigrations,
    refetchInterval: 30_000,
  })

  const retryMut = useMutation({
    mutationFn: retryTenantMigration,
    onMutate: (id) => setRetryingId(id),
    onSettled: () => {
      setRetryingId(null)
      qc.invalidateQueries({ queryKey: ['tenant-migrations'] })
    },
  })

  const totalPending  = rows.filter(r => !r.is_current).length
  const totalFailed   = rows.filter(r => r.last_status === 'failed' && !r.is_current).length
  const totalCurrent  = rows.filter(r => r.is_current).length

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)' }}
          >
            <Database className="h-5 w-5" style={{ color: '#818cf8' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Tenant Migrations</h1>
            <p className="text-sm text-gray-400">Schema version status for all tenants</p>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg"
          style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Up to date',  value: totalCurrent, icon: CheckCircle2, color: '#34d399', bg: 'rgba(16,185,129,0.1)',  border: 'rgba(16,185,129,0.2)' },
          { label: 'Pending',     value: totalPending,  icon: Clock,       color: '#fbbf24', bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.2)' },
          { label: 'Failed',      value: totalFailed,   icon: AlertTriangle, color: '#f87171', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.2)'  },
        ].map(({ label, value, icon: Icon, color, bg, border }) => (
          <div
            key={label}
            className="rounded-xl p-4 flex items-center gap-4"
            style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: bg, border: `1px solid ${border}` }}>
              <Icon className="h-4 w-4" style={{ color }} />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{value}</p>
              <p className="text-xs text-gray-400">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}>
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-gray-500 text-sm gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center py-16 text-red-400 text-sm gap-2">
            <AlertTriangle className="h-4 w-4" /> Failed to load migration status.
          </div>
        )}

        {!isLoading && !error && rows.length === 0 && (
          <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
            No tenants found.
          </div>
        )}

        {!isLoading && !error && rows.length > 0 && (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                {['Tenant', 'Current Version', 'Latest Version', 'Status', 'Last Migration', 'Actions'].map(h => (
                  <th key={h} className="py-3 px-4 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <MigRow
                  key={row.tenant_id}
                  row={row}
                  onRetry={(id) => retryMut.mutate(id)}
                  retrying={retryingId === row.tenant_id && retryMut.isPending}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-600 text-right">Auto-refreshes every 30 seconds · Migrations run automatically at backend startup</p>
    </div>
  )
}
