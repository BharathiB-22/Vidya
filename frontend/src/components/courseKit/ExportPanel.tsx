import { useRef, useState } from 'react'
import { Download, FileType, RefreshCw, Loader2, Upload, RotateCcw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  useKitExports,
  useExportKit,
  useUploadExport,
  useDeleteExport,
} from '@/hooks/courseKit'
import { ExportKitDialog } from './CourseKitActionDialogs'
import * as courseKitApi from '@/lib/api/courseKit'
import type { CourseKit } from '@/types/courseKit'

interface Props {
  kit:       CourseKit
  canExport: boolean
  /** Write permission — gates Upload / Replace / Delete. Download stays open. */
  canWrite?: boolean
}

// Editable office decks only. Matches the course_kit_export MIME whitelist.
const DECK_ACCEPT =
  '.pptx,.pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/pdf'

export function ExportPanel({ kit, canExport, canWrite = false }: Props) {
  const [exportOpen,   setExportOpen]   = useState(false)
  const [downloading,  setDownloading]  = useState<string | null>(null)
  const [actionError,  setActionError]  = useState<string | null>(null)
  // asset id currently being replaced (null = a brand-new upload)
  const [replaceFor,   setReplaceFor]   = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const { data: exports = [], isLoading, refetch, isFetching } = useKitExports(kit.id)
  const exportKit    = useExportKit()
  const uploadExport = useUploadExport()
  const deleteExport = useDeleteExport()

  async function handleDownload(assetId: string) {
    setDownloading(assetId)
    try {
      const result = await courseKitApi.getExportDownload(kit.id, assetId)
      window.open(result.download_url, '_blank', 'noopener,noreferrer')
    } finally {
      setDownloading(null)
    }
  }

  function pickFile(replaceAssetId: string | null) {
    setActionError(null)
    setReplaceFor(replaceAssetId)
    fileInputRef.current?.click()
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    // Reset the input so choosing the same file again re-triggers change.
    e.target.value = ''
    if (!file) return
    setActionError(null)
    try {
      await uploadExport.mutateAsync({
        kitId: kit.id,
        file,
        replaceAssetId: replaceFor ?? undefined,
      })
    } catch (err: any) {
      setActionError(
        err?.response?.data?.detail?.message ??
        err?.message ??
        'Upload failed. Ensure the file is a .pptx or .pdf.',
      )
    } finally {
      setReplaceFor(null)
    }
  }

  async function handleDelete(assetId: string) {
    setActionError(null)
    try {
      await deleteExport.mutateAsync({ kitId: kit.id, assetId })
    } catch (err: any) {
      setActionError(err?.response?.data?.detail?.message ?? 'Delete failed.')
    }
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const uploading = uploadExport.isPending

  return (
    <div className="space-y-4">
      {/* Hidden file input shared by New upload + per-row Replace */}
      <input
        ref={fileInputRef}
        type="file"
        accept={DECK_ACCEPT}
        className="hidden"
        onChange={onFileChosen}
      />

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Exports</h3>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {canWrite && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => pickFile(null)}
              disabled={uploading}
              title="Upload an edited .pptx / .pdf back to this kit"
            >
              {uploading && replaceFor === null
                ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                : <Upload className="h-4 w-4 mr-1" />}
              Upload Deck
            </Button>
          )}
          {canExport && (
            <Button size="sm" onClick={() => setExportOpen(true)} disabled={exportKit.isPending}>
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

      {actionError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {isLoading && (
        <p className="text-sm text-gray-600 py-4 text-center">Loading exports…</p>
      )}

      {!isLoading && exports.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-200 py-10 text-center">
          <FileType className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No exports yet.</p>
          {canExport && (
            <Button variant="outline" size="sm" className="mt-3" onClick={() => setExportOpen(true)}>
              Create Export
            </Button>
          )}
        </div>
      )}

      {exports.length > 0 && (
        <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
          {exports.map((asset) => {
            const busy = uploading && replaceFor === asset.id
            return (
              <div key={asset.id} className="flex items-center gap-3 px-4 py-3">
                <FileType className="h-5 w-5 text-gray-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {asset.original_filename}
                  </p>
                  <p className="text-xs text-gray-600">
                    {formatBytes(asset.size_bytes)} · {new Date(asset.created_at).toLocaleString()}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDownload(asset.id)}
                  disabled={downloading === asset.id}
                  title="Download"
                >
                  {downloading === asset.id
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <Download className="h-4 w-4" />}
                </Button>
                {canWrite && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => pickFile(asset.id)}
                      disabled={uploading}
                      title="Replace with an edited file"
                    >
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => handleDelete(asset.id)}
                      disabled={deleteExport.isPending}
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </>
                )}
              </div>
            )
          })}
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
