import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2, GitFork, Download, CheckCircle, Zap, Lock, Eye, Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  GenerateSyllabusDialog,
  ApproveSyllabusDialog,
  ForkSyllabusDialog,
  ExportSyllabusDialog,
  DeleteConfirmDialog,
} from './SyllabusActionDialogs'
import {
  useGenerateSyllabus,
  useApproveSyllabus,
  useForkSyllabus,
  useExportSyllabus,
  useDeleteSyllabus,
} from '@/hooks/syllabuses'
import type { Syllabus } from '@/types/syllabus'
import { useWorkspace } from '@/lib/workspace'

/**
 * What can be done to an official syllabus, and by whom.
 *
 * The syllabus is CURRICULUM, and the curriculum belongs to the Board. So this
 * bar is, for almost everyone, empty: Faculty get a read-only notice, the Dean
 * gets a read-only notice, and only a board member sees buttons.
 *
 * That is the point of Phase A. Faculty teach to the official syllabus and build
 * lesson plans, PPTs, course kits, assignments and question papers underneath it
 * — they never write it. The Dean reads it.
 *
 *   DRAFT      board: generate with AI, approve, delete
 *   APPROVED   board: still editable (an edit returns it to draft), export, fork
 *   LOCKED     nobody edits. Export and fork only.
 */

const BOARD_ROLES = ['ADMIN', 'BOARD']

interface Props {
  syllabus: Syllabus
}

export function SyllabusActionBar({ syllabus }: Props) {
  const navigate = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const isBoard = BOARD_ROLES.includes(role)

  const [generateOpen, setGenerateOpen] = useState(false)
  const [approveOpen,  setApproveOpen]  = useState(false)
  const [forkOpen,     setForkOpen]     = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)
  const [deleteOpen,   setDeleteOpen]   = useState(false)

  const generate       = useGenerateSyllabus(syllabus.id)
  const approve        = useApproveSyllabus()
  const fork           = useForkSyllabus()
  const exportJob      = useExportSyllabus()
  const deleteSyllabus = useDeleteSyllabus()

  async function handleFork(changeNote?: string) {
    const result = await fork.mutateAsync({ id: syllabus.id, payload: { change_note: changeNote } })
    navigate(`/syllabuses/${result.id}`)
  }

  function handleDelete() {
    deleteSyllabus.mutate(syllabus.id, { onSuccess: () => navigate(-1) })
  }

  const isLocked  = syllabus.status === 'LOCKED'
  const isDraft   = syllabus.status === 'DRAFT'
  const canExport = syllabus.status === 'APPROVED' || isLocked

  // Everyone who is not on the board reads this document; they do not act on it.
  if (!isBoard) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <Eye className="h-4 w-4 text-gray-400" />
        <span className="text-sm text-gray-600">
          The official syllabus is owned by the governance authority. This is a read-only view.
        </span>
        {canExport && (
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            onClick={() => setExportOpen(true)}
            disabled={exportJob.isPending}
          >
            <Download className="h-4 w-4 mr-1" />
            Export
          </Button>
        )}
        <ExportSyllabusDialog
          open={exportOpen}
          onOpenChange={setExportOpen}
          onSubmit={(format) => exportJob.mutate({ id: syllabus.id, payload: { format } })}
          isPending={exportJob.isPending}
        />
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">

      {syllabus.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          Writing the official syllabus…
        </div>
      )}

      {isDraft && (
        <>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-700"
            onClick={() => setApproveOpen(true)}
            disabled={approve.isPending}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            Approve Syllabus
          </Button>
          <Button size="sm" variant="outline" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
            <Zap className="h-4 w-4 mr-1" />
            Regenerate with AI
          </Button>
        </>
      )}

      {syllabus.status === 'APPROVED' && (
        <div className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm text-emerald-800">
          <CheckCircle className="h-4 w-4 text-emerald-600" />
          Approved. It locks when the curriculum is approved; editing it now returns it to draft.
        </div>
      )}

      {isLocked && (
        <div className="flex items-center gap-2 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700">
          <Lock className="h-4 w-4 text-gray-500" />
          Locked with the curriculum. Nobody edits this — create a new curriculum version.
        </div>
      )}

      {canExport && (
        <Button size="sm" variant="outline" onClick={() => setForkOpen(true)} disabled={fork.isPending}>
          <GitFork className="h-4 w-4 mr-1" />
          {fork.isPending ? 'Forking…' : 'Fork Version'}
        </Button>
      )}

      {canExport && (
        <Button size="sm" variant="outline" onClick={() => setExportOpen(true)} disabled={exportJob.isPending}>
          <Download className="h-4 w-4 mr-1" />
          Export
        </Button>
      )}

      {!isLocked && (
        <Button
          size="sm"
          variant="outline"
          className="text-red-600 border-red-200 hover:bg-red-50 hover:border-red-400"
          onClick={() => setDeleteOpen(true)}
          disabled={deleteSyllabus.isPending}
        >
          <Trash2 className="h-4 w-4 mr-1" />
          Delete
        </Button>
      )}

      <span className="ml-auto text-xs font-medium bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
        {role}
      </span>

      {/* Dialogs */}
      <GenerateSyllabusDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onSubmit={(hint) => generate.mutate({ custom_instructions: hint })}
        isPending={generate.isPending}
      />
      <ApproveSyllabusDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        onSubmit={(comment) => approve.mutate({ id: syllabus.id, payload: { comment } })}
        isPending={approve.isPending}
      />
      <ForkSyllabusDialog
        open={forkOpen}
        onOpenChange={setForkOpen}
        onSubmit={handleFork}
        isPending={fork.isPending}
      />
      <ExportSyllabusDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        onSubmit={(format) => exportJob.mutate({ id: syllabus.id, payload: { format } })}
        isPending={exportJob.isPending}
      />
      <DeleteConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={handleDelete}
        status={syllabus.status}
        isPending={deleteSyllabus.isPending}
      />
    </div>
  )
}
