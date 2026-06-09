import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, RefreshCw, CheckCircle2, XCircle, ChevronLeft, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { ImportBatch } from '@/lib/api/sis'

const PAGE_SIZE = 20

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
// Main page
// ---------------------------------------------------------------------------

export default function ImportHistoryPage() {
  const [page, setPage] = useState(0)
  const offset = page * PAGE_SIZE

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['sis-import-batches', page],
    queryFn:  () => sisApi.listImportBatches(PAGE_SIZE, offset),
  })

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <PageShell>
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
