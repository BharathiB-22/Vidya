import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, GitFork, Download, CheckCircle, Archive, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  GenerateKitDialog,
  PublishKitDialog,
  ArchiveKitDialog,
  ForkKitDialog,
  ExportKitDialog,
} from './CourseKitActionDialogs'
import {
  useGenerateKit,
  usePublishKit,
  useArchiveKit,
  useForkKit,
  useExportKit,
} from '@/hooks/courseKit'
import type { CourseKit } from '@/types/courseKit'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

interface Props {
  kit: CourseKit
}

export function CourseKitActionBar({ kit }: Props) {
  const navigate = useNavigate()
  const role     = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canWrite = WRITE_ROLES.includes(role)
  const isDean   = role === 'DEAN'

  const [generateOpen, setGenerateOpen] = useState(false)
  const [publishOpen,  setPublishOpen]  = useState(false)
  const [archiveOpen,  setArchiveOpen]  = useState(false)
  const [forkOpen,     setForkOpen]     = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)

  const generate = useGenerateKit(kit.id)
  const publish  = usePublishKit()
  const archive  = useArchiveKit()
  const fork     = useForkKit()
  const exportKit = useExportKit()

  const canExport = kit.status === 'PUBLISHED' || kit.status === 'ARCHIVED'

  async function handleFork(changeNote?: string) {
    const result = await fork.mutateAsync({ id: kit.id, payload: { change_note: changeNote } })
    navigate(`/course-kits/${result.id}`)
  }

  const hasAnyAction =
    (kit.status === 'DRAFT' && canWrite) ||
    (kit.status === 'PUBLISHED' && canWrite) ||
    canExport

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">

      {/* ── DRAFT ── */}
      {kit.status === 'DRAFT' && canWrite && (
        <Button size="sm" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
          <Zap className="h-4 w-4 mr-1" />
          Generate with AI
        </Button>
      )}
      {kit.status === 'DRAFT' && canWrite && (
        <Button
          size="sm"
          className="bg-green-600 hover:bg-green-700"
          onClick={() => setPublishOpen(true)}
          disabled={publish.isPending}
        >
          <CheckCircle className="h-4 w-4 mr-1" />
          Publish
        </Button>
      )}

      {/* ── AI_GENERATING ── */}
      {kit.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          AI is generating the kit…
        </div>
      )}

      {/* ── PUBLISHED ── */}
      {kit.status === 'PUBLISHED' && canWrite && (
        <Button
          size="sm"
          variant="destructive"
          onClick={() => setArchiveOpen(true)}
          disabled={archive.isPending}
        >
          <Archive className="h-4 w-4 mr-1" />
          Archive
        </Button>
      )}

      {/* ── Fork — PUBLISHED + ARCHIVED ── */}
      {canExport && (canWrite || isDean) && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setForkOpen(true)}
          disabled={fork.isPending || isDean}
          title={isDean ? 'DEAN role cannot fork' : undefined}
        >
          <GitFork className="h-4 w-4 mr-1" />
          {fork.isPending ? 'Forking…' : 'Fork'}
        </Button>
      )}

      {/* ── Export — PUBLISHED + ARCHIVED ── */}
      {canExport && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setExportOpen(true)}
          disabled={exportKit.isPending}
        >
          <Download className="h-4 w-4 mr-1" />
          Export
        </Button>
      )}

      {/* No actions */}
      {!hasAnyAction && kit.status !== 'AI_GENERATING' && (
        <span className="text-sm text-gray-400">No actions available for your role.</span>
      )}

      {/* Role chip */}
      <span className="ml-auto text-xs font-medium bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
        {role}
      </span>

      {/* Dialogs */}
      <GenerateKitDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onSubmit={(opts) => generate.mutate(opts)}
        isPending={generate.isPending}
      />
      <PublishKitDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        onSubmit={(comment) => publish.mutate({ id: kit.id, payload: { comment } })}
        isPending={publish.isPending}
      />
      <ArchiveKitDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        onSubmit={(reason) => archive.mutate({ id: kit.id, payload: { reason } })}
        isPending={archive.isPending}
      />
      <ForkKitDialog
        open={forkOpen}
        onOpenChange={setForkOpen}
        onSubmit={handleFork}
        isPending={fork.isPending}
      />
      <ExportKitDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        onSubmit={(format) => exportKit.mutate({ id: kit.id, payload: { format } })}
        isPending={exportKit.isPending}
      />
    </div>
  )
}
