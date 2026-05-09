import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, GitFork, Download, CheckCircle, XCircle, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  GenerateDialog,
  ApproveDialog,
  RejectDialog,
  ExportDialog,
} from './ActionDialogs'
import {
  useGenerateProgram,
  useApproveProgram,
  useRejectProgram,
  useExportProgram,
  useForkProgram,
} from '@/hooks/programs'
import type { Program } from '@/types/program'

const WRITE_ROLES = ['ADMIN', 'DEAN']
const APPROVE_ROLES = ['ADMIN', 'DEAN']

interface Props {
  program: Program
}

export function ActionBar({ program }: Props) {
  const navigate = useNavigate()
  const role = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canWrite = WRITE_ROLES.includes(role)
  const canApprove = APPROVE_ROLES.includes(role)

  const [generateOpen, setGenerateOpen] = useState(false)
  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const generate = useGenerateProgram(program.id)
  const approve = useApproveProgram()
  const reject = useRejectProgram()
  const exportJob = useExportProgram()
  const fork = useForkProgram()

  async function handleFork() {
    const forked = await fork.mutateAsync(program.id)
    navigate(`/programs/${forked.id}`)
  }

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
      {/* DRAFT */}
      {program.status === 'DRAFT' && canWrite && (
        <Button size="sm" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
          <Zap className="h-4 w-4 mr-1" />
          Generate with AI
        </Button>
      )}
      {program.status === 'DRAFT' && !canWrite && (
        <span className="text-sm text-gray-400">No actions available for your role.</span>
      )}

      {/* AI_GENERATING */}
      {program.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          AI is generating the program structure…
        </div>
      )}

      {/* PENDING_APPROVAL */}
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
        </>
      )}
      {program.status === 'PENDING_APPROVAL' && !canApprove && (
        <span className="text-sm text-gray-400">Awaiting Dean approval.</span>
      )}

      {/* APPROVED */}
      {program.status === 'APPROVED' && canWrite && (
        <Button
          size="sm"
          variant="outline"
          onClick={handleFork}
          disabled={fork.isPending}
        >
          <GitFork className="h-4 w-4 mr-1" />
          {fork.isPending ? 'Forking…' : 'Fork Version'}
        </Button>
      )}
      {program.status === 'APPROVED' && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setExportOpen(true)}
          disabled={exportJob.isPending}
        >
          <Download className="h-4 w-4 mr-1" />
          Export
        </Button>
      )}

      {/* Dialogs */}
      <GenerateDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onSubmit={(hint) => generate.mutate({ prompt_hint: hint })}
        isPending={generate.isPending}
      />
      <ApproveDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        onSubmit={(notes) => approve.mutate({ id: program.id, payload: { notes } })}
        isPending={approve.isPending}
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
