import { useState } from 'react'
import { Download, FileType, RefreshCw, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useKitExports, useExportKit } from '@/hooks/courseKit'
import { ExportKitDialog } from './CourseKitActionDialogs'
import * as courseKitApi from '@/lib/api/courseKit'
import type { CourseKit } from '@/types/courseKit'

interface Props {
  kit:      CourseKit
  canExport: boolean
}

export function ExportPanel({ kit, canExport }: Props) {
  const [exportOpen,   setExportOpen]   = useState(false)
  const [downloading,  setDownloading]  = useState<string | null>(null)

  const { data: exports = [], isLoading, refetch, isFetching } = useKitExports(kit.id)
  const exportKit = useExportKit()

  async function handleDownload(assetId: string) {
    setDownloading(assetId)
    try {
      const result = await courseKitApi.getExportDownload(kit.id, assetId)
      window.open(result.download_url, '_blank', 'noopener,noreferrer')
    } finally {
      setDownloading(null)
    }
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Exports</h3>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {canExport && (
            <Button
              size="sm"
              onClick={() => setExportOpen(true)}
              disabled={exportKit.isPending}
            >
              <Download className="h-4 w-4 mr-1" />
              New Export
            </Button>
          )}
        </div>
      </div>

      {exportKit.isSuccess && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-700">
          Export job queued — refresh in a few seconds to see the download link.
        </div>
      )}

      {isLoading && (
        <p className="text-sm text-gray-400 py-4 text-center">Loading exports…</p>
      )}

      {!isLoading && exports.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-200 py-10 text-center">
          <FileType className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No exports yet.</p>
          {canExport && (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => setExportOpen(true)}
            >
              Create Export
            </Button>
          )}
        </div>
      )}

      {exports.length > 0 && (
        <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
          {exports.map((asset) => (
            <div key={asset.id} className="flex items-center gap-3 px-4 py-3">
              <FileType className="h-5 w-5 text-gray-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {asset.original_filename}
                </p>
                <p className="text-xs text-gray-400">
                  {formatBytes(asset.size_bytes)} · {new Date(asset.created_at).toLocaleString()}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleDownload(asset.id)}
                disabled={downloading === asset.id}
              >
                {downloading === asset.id
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <Download className="h-4 w-4" />}
              </Button>
            </div>
          ))}
        </div>
      )}

      <ExportKitDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        onSubmit={(format) => exportKit.mutate({ id: kit.id, payload: { format } })}
        isPending={exportKit.isPending}
      />
    </div>
  )
}
