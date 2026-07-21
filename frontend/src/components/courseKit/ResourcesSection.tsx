import { useRef, useState } from 'react'
import { FileText, Upload, Trash2, Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { useUploadResource, useDeleteResource, downloadResource } from '@/hooks/courseKit'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { KitResourceFile } from '@/types/courseKit'

const MAX_SIZE_MB = 50
const ALLOWED_MIME = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
  'text/plain',
]

interface Props {
  kitId:      string
  resources:  KitResourceFile[]
  canUpload: boolean
  isLoading?: boolean
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function SkeletonRow() {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 animate-pulse flex items-center gap-3">
      <div className="h-8 w-8 rounded bg-gray-200 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-40 rounded bg-gray-200" />
        <div className="h-3 w-24 rounded bg-gray-100" />
      </div>
    </div>
  )
}

export function ResourcesSection({ kitId, resources, canUpload, isLoading }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [pendingDelete, setPendingDelete] = useState<KitResourceFile | null>(null)

  const upload = useUploadResource()
  const del    = useDeleteResource()

  function handleFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    if (!ALLOWED_MIME.includes(file.type)) {
      addToast('Only PDF, PPT, DOCX, or plain-text files are allowed.', 'error')
      return
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      addToast(`File must be under ${MAX_SIZE_MB} MB.`, 'error')
      return
    }

    upload.mutate({ kitId, file }, {
      onSuccess: () => addToast('Resource uploaded.', 'success'),
      onError:   (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  async function handleDownload(r: KitResourceFile) {
    try {
      await downloadResource(kitId, r.id, r.original_filename)
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    }
  }

  function handleDeleteConfirm() {
    if (!pendingDelete) return
    del.mutate({ kitId, assetId: pendingDelete.id }, {
      onSuccess: () => {
        addToast('Resource deleted.', 'success')
        setPendingDelete(null)
      },
      onError: (err) => {
        addToast(getErrorMessage(err), 'error')
        setPendingDelete(null)
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Supporting material — PDF, PPT, DOCX, and reference notes shared alongside this kit.
        </p>
        {canUpload && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.ppt,.pptx,.doc,.docx,.txt"
              onChange={handleFileChosen}
            />
            <Button
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={upload.isPending}
            >
              {upload.isPending
                ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                : <Upload className="h-4 w-4 mr-1" />}
              Upload Resource
            </Button>
          </>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : resources.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <FileText className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No resources uploaded yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {resources.map((r) => (
            <div key={r.id} className="flex items-center gap-3 px-4 py-3">
              <FileText className="h-5 w-5 text-gray-600 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{r.original_filename}</p>
                <p className="text-xs text-gray-600">
                  {formatSize(r.size_bytes)} · {new Date(r.created_at).toLocaleDateString()}
                </p>
              </div>
              <button
                type="button"
                title="Download"
                className="p-1.5 text-gray-600 hover:text-blue-600 transition-colors"
                onClick={() => handleDownload(r)}
              >
                <Download className="h-4 w-4" />
              </button>
              {canUpload && (
                <button
                  type="button"
                  title="Delete"
                  className="p-1.5 text-gray-600 hover:text-red-500 transition-colors"
                  onClick={() => setPendingDelete(r)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <Dialog open={!!pendingDelete} onOpenChange={(open) => { if (!open) setPendingDelete(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Resource?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-600 pt-1">
            {pendingDelete?.original_filename} will be permanently removed. This cannot be undone.
          </p>
          <DialogFooter className="gap-2 pt-2">
            <Button variant="outline" onClick={() => setPendingDelete(null)} disabled={del.isPending}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm} disabled={del.isPending}>
              {del.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
