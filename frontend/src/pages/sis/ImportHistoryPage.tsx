import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { History, RefreshCw, CheckCircle2, XCircle, ChevronLeft, ChevronRight, RotateCcw, AlertTriangle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { ImportBatch } from '@/lib/api/sis'

const PAGE_SIZE = 20

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

function StatusBadge({ rolledBack }: { rolledBack: boolean }) {
  if (rolledBack) {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded"
        style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}
      >
        <XCircle size={11} /> Rolled Back
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded"
      style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}
    >
      <CheckCircle2 size={11} /> Active
    </span>
  )
}

function RecordTypeBadge({ type }: { type: string }) {
  return (
    <span
      className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded"
      style={{ background: 'rgba(139,92,246,0.12)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.25)' }}
    >
      {type}
    </span>
  )
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    year:   'numeric',
    month:  'short',
    day:    '2-digit',
    hour:   '2-digit',
    minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Rollback confirmation modal
// ---------------------------------------------------------------------------

interface RollbackModalProps {
  batch: ImportBatch
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
  error: string | null
}

function RollbackModal({ batch, onConfirm, onCancel, isPending, error }: RollbackModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div
        className="rounded-xl border p-6 max-w-md w-full mx-4 space-y-4"
        style={{ background: '#1a1a2e', borderColor: 'rgba(239,68,68,0.3)' }}
      >
        <div className="flex items-center gap-3">
          <AlertTriangle size={22} style={{ color: '#f87171' }} />
          <h2 className="text-base font-semibold">Roll Back Import Batch?</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          This will detach <strong>{batch.success_count} profile record{batch.success_count !== 1 ? 's' : ''}</strong> from
          batch <span className="font-mono text-purple-400">{batch.batch_ref}</span>.
          The profiles themselves are kept — only the import tracking link is removed.
          This action <strong>cannot be undone</strong>.
        </p>
        {error && (
          <div
            className="rounded px-3 py-2 text-xs"
            style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
          >
            {error}
          </div>
        )}
        <div className="flex gap-3 justify-end pt-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={onConfirm}
            disabled={isPending}
            className="gap-2"
            style={{ background: '#dc2626', color: '#fff' }}
          >
            <RotateCcw size={13} />
            {isPending ? 'Rolling back…' : 'Confirm Rollback'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ImportHistoryPage() {
  const [page, setPage]               = useState(0)
  const [rollbackTarget, setRollbackTarget] = useState<ImportBatch | null>(null)
  const [rollbackError, setRollbackError]   = useState<string | null>(null)
  const queryClient = useQueryClient()
  const offset = page * PAGE_SIZE

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['sis-import-batches', page],
    queryFn:  () => sisApi.listImportBatches(PAGE_SIZE, offset),
  })

  const rollbackMutation = useMutation({
    mutationFn: (batchId: string) => sisApi.rollbackImportBatch(batchId),
    onSuccess: () => {
      setRollbackTarget(null)
      setRollbackError(null)
      queryClient.invalidateQueries({ queryKey: ['sis-import-batches'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail?.message ?? 'Rollback failed. Please try again.'
      setRollbackError(msg)
    },
  })

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <PageShell>
      {rollbackTarget && (
        <RollbackModal
          batch={rollbackTarget}
          onConfirm={() => rollbackMutation.mutate(rollbackTarget.id)}
          onCancel={() => { setRollbackTarget(null); setRollbackError(null) }}
          isPending={rollbackMutation.isPending}
          error={rollbackError}
        />
      )}

      <PageHeader
        title="Import History"
        subtitle="Audit trail of every bulk profile import committed to this institution."
        icon={History}
        action={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="gap-2"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </Button>
        }
      />

      <div className="mt-6">
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            Loading import history…
          </div>
        )}

        {isError && (
          <div
            className="flex items-center gap-2 rounded-lg px-4 py-3 text-sm"
            style={{ background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
          >
            <XCircle size={16} />
            Failed to load import history. Try refreshing.
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <History size={40} className="opacity-30" />
            <p className="text-sm">No import batches found.</p>
            <p className="text-xs opacity-60">Batches appear here after a bulk profile import is committed.</p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <>
            {/* Summary bar */}
            <div className="flex items-center justify-between mb-4 text-sm text-muted-foreground">
              <span>{data.total} batch{data.total !== 1 ? 'es' : ''} total</span>
              {totalPages > 1 && (
                <span>Page {page + 1} of {totalPages}</span>
              )}
            </div>

            {/* Table */}
            <div className="rounded-xl border border-white/[0.06] overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Batch Ref</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Total</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Success</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Failed</th>
                    <th className="text-center px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="text-center px-4 py-3 font-medium text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((batch: ImportBatch, idx: number) => (
                    <tr
                      key={batch.id}
                      style={{
                        borderBottom: idx < data.items.length - 1 ? '1px solid rgba(255,255,255,0.04)' : undefined,
                        background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                      }}
                    >
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: '#a78bfa' }}>
                        {batch.batch_ref}
                      </td>
                      <td className="px-4 py-3">
                        <RecordTypeBadge type={batch.record_type} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(batch.imported_at)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {batch.total_records}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums" style={{ color: '#4ade80' }}>
                        {batch.success_count}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums" style={{ color: batch.failed_count > 0 ? '#f87171' : undefined }}>
                        {batch.failed_count}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <StatusBadge rolledBack={batch.is_rolled_back} />
                      </td>
                      <td className="px-4 py-3 text-center">
                        {!batch.is_rolled_back && (
                          <button
                            onClick={() => { setRollbackTarget(batch); setRollbackError(null) }}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors hover:bg-red-900/30"
                            style={{ color: '#f87171' }}
                            title="Roll back this import"
                          >
                            <RotateCcw size={11} /> Rollback
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-end gap-2 mt-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="gap-1"
                >
                  <ChevronLeft size={14} /> Prev
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="gap-1"
                >
                  Next <ChevronRight size={14} />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
