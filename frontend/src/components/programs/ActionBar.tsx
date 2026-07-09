import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, GitFork, Download, CheckCircle, XCircle, Zap, AlertTriangle, Pencil, Trash2, Rocket, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  EditProgramDialog,
  DeleteProgramDialog,
  GenerateDialog,
  ApproveDialog,
  PublishDialog,
  RejectDialog,
  ExportDialog,
} from './ActionDialogs'
import {
  useGenerateProgram,
  useApproveProgram,
  usePublishProgram,
  useRejectProgram,
  useExportProgram,
  useForkProgram,
  useUpdateProgram,
  useDeleteProgram,
} from '@/hooks/programs'
import { addToast } from '@/hooks/useToast'
import type { Program } from '@/types/program'
import { useWorkspace } from '@/lib/workspace'

const WRITE_ROLES = ['ADMIN', 'DEAN']
const APPROVE_ROLES = ['ADMIN', 'DEAN']

interface Props {
  program: Program
}

export function ActionBar({ program }: Props) {
  const navigate = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const canWrite = WRITE_ROLES.includes(role)
  const canApprove = APPROVE_ROLES.includes(role)

  const [generateOpen, setGenerateOpen] = useState(false)
  const [approveOpen,  setApproveOpen]  = useState(false)
  const [publishOpen,  setPublishOpen]  = useState(false)
  const [rejectOpen,   setRejectOpen]   = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)
  const [editOpen,     setEditOpen]     = useState(false)
  const [deleteOpen,   setDeleteOpen]   = useState(false)

  const generate = useGenerateProgram(program.id)
  const approve  = useApproveProgram()
  const publish  = usePublishProgram()
  const reject   = useRejectProgram()
  const exportJob = useExportProgram()
  const fork     = useForkProgram()
  const update   = useUpdateProgram()
  const del      = useDeleteProgram()

  async function handleFork() {
    const forked = await fork.mutateAsync(program.id)
    navigate(`/programs/${forked.id}`)
  }

  async function handleDelete() {
    await del.mutateAsync(program.id)
    addToast('Program deleted.', 'success')
    navigate('/programs')
  }

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
      {/* DRAFT — edit + delete + generate */}
      {program.status === 'DRAFT' && canWrite && (
        <>
          <Button size="sm" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
            <Zap className="h-4 w-4 mr-1" />
            Generate with AI
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
            <Pencil className="h-4 w-4 mr-1" />
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-red-600 border-red-200 hover:bg-red-50"
            onClick={() => setDeleteOpen(true)}
            disabled={del.isPending}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Delete
          </Button>
        </>
      )}
      {program.status === 'DRAFT' && !canWrite && (
        <span className="text-sm text-gray-600">Awaiting generation by Admin/Dean.</span>
      )}

      {/* GENERATION_FAILED */}
      {program.status === 'GENERATION_FAILED' && canWrite && (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 text-red-600" />
            AI generation failed.
          </div>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setGenerateOpen(true)}
            disabled={generate.isPending}
          >
            <Zap className="h-4 w-4 mr-1" />
            Retry
          </Button>
        </div>
      )}
      {program.status === 'GENERATION_FAILED' && !canWrite && (
        <div className="flex items-center gap-1.5 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          AI generation failed. Contact your administrator.
        </div>
      )}

      {/* AI_GENERATING */}
      {program.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          AI is generating the program structure…
        </div>
      )}

      {/* PENDING_APPROVAL — Approve/Reject, and delete is still permitted */}
      {program.status === 'PENDING_APPROVAL' && canApprove && (
        <>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-700"
            onClick={() => setApproveOpen(true)}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            Approve
          </Button>
          <Button size="sm" variant="destructive" onClick={() => setRejectOpen(true)}>
            <XCircle className="h-4 w-4 mr-1" />
            Reject
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-red-600 border-red-200 hover:bg-red-50"
            onClick={() => setDeleteOpen(true)}
            disabled={del.isPending}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Delete
          </Button>
        </>
      )}
      {program.status === 'PENDING_APPROVAL' && !canApprove && (
        <span className="text-sm text-gray-600">Awaiting Dean approval.</span>
      )}

      {/* APPROVED — editable, but deletion is locked (create a new version
          instead); plus Export/Publish */}
      {program.status === 'APPROVED' && canWrite && (
        <>
          <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
            <Pencil className="h-4 w-4 mr-1" />
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleFork}
            disabled={fork.isPending}
          >
            <GitFork className="h-4 w-4 mr-1" />
            {fork.isPending ? 'Creating…' : 'Create New Version'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setExportOpen(true)}
            disabled={exportJob.isPending}
          >
            <Download className="h-4 w-4 mr-1" />
            Export
          </Button>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-700"
            onClick={() => setPublishOpen(true)}
            disabled={publish.isPending}
          >
            <Rocket className="h-4 w-4 mr-1" />
            Publish
          </Button>
        </>
      )}
      {program.status === 'APPROVED' && !canWrite && (
        <span className="text-sm text-gray-600">Approved — awaiting Dean publish.</span>
      )}

      {/* PUBLISHED — permanently read-only, Fork/Export remain available */}
      {program.status === 'PUBLISHED' && (
        <>
          <div className="flex items-center gap-1.5 text-sm text-gray-700">
            <Lock className="h-4 w-4 text-gray-500" />
            Published — locked. No further edits or deletion.
          </div>
          {canWrite && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleFork}
              disabled={fork.isPending}
            >
              <GitFork className="h-4 w-4 mr-1" />
              {fork.isPending ? 'Creating…' : 'Create New Version'}
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => setExportOpen(true)}
            disabled={exportJob.isPending}
          >
            <Download className="h-4 w-4 mr-1" />
            Export
          </Button>
        </>
      )}

      {/* Dialogs */}
      <EditProgramDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        program={program}
        onSubmit={(payload) => update.mutate({ id: program.id, payload })}
        isPending={update.isPending}
      />
      <DeleteProgramDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        programTitle={program.title}
        onConfirm={handleDelete}
        isPending={del.isPending}
      />
      <GenerateDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onSubmit={(hint, aiInstructions) => generate.mutate({ prompt_hint: hint, ai_instructions: aiInstructions })}
        isPending={generate.isPending}
        storedInstructions={program.ai_instructions}
      />
      <ApproveDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        onSubmit={(comment) => approve.mutate({ id: program.id, payload: { comment } })}
        isPending={approve.isPending}
        hasAcadLink={Boolean(program.acad_program_id)}
      />
      <PublishDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        onSubmit={(comment) => publish.mutate({ id: program.id, payload: { comment } })}
        isPending={publish.isPending}
      />
      <RejectDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        onSubmit={(reason) => reject.mutate({ id: program.id, payload: { reason } })}
        isPending={reject.isPending}
      />
      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        onSubmit={(format) => exportJob.mutate({ id: program.id, payload: { format } })}
        isPending={exportJob.isPending}
      />
    </div>
  )
}
