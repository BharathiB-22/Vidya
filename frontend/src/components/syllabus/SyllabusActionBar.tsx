import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, GitFork, Download, CheckCircle, XCircle, Zap, Lock, Unlock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  GenerateSyllabusDialog,
  ApproveSyllabusDialog,
  RejectSyllabusDialog,
  LockSyllabusDialog,
  ForkSyllabusDialog,
  ExportSyllabusDialog,
} from './SyllabusActionDialogs'
import {
  useGenerateSyllabus,
  useApproveSyllabus,
  useRejectSyllabus,
  useLockSyllabus,
  useUnlockSyllabus,
  useForkSyllabus,
  useExportSyllabus,
} from '@/hooks/syllabuses'
import type { Syllabus } from '@/types/syllabus'

// ADMIN + FACULTY: create, edit, generate, approve, reject, fork
const WRITE_ROLES = ['ADMIN', 'FACULTY']
// ADMIN + DEAN: lock, unlock
const LOCK_ROLES = ['ADMIN', 'DEAN']

interface Props {
  syllabus: Syllabus
}

export function SyllabusActionBar({ syllabus }: Props) {
  const navigate = useNavigate()
  const role = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canWrite = WRITE_ROLES.includes(role)
  const canLock  = LOCK_ROLES.includes(role)

  const [generateOpen, setGenerateOpen] = useState(false)
  const [approveOpen,  setApproveOpen]  = useState(false)
  const [rejectOpen,   setRejectOpen]   = useState(false)
  const [lockOpen,     setLockOpen]     = useState(false)
  const [forkOpen,     setForkOpen]     = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)

  const generate   = useGenerateSyllabus(syllabus.id)
  const approve    = useApproveSyllabus()
  const reject     = useRejectSyllabus()
  const lock       = useLockSyllabus()
  const unlock     = useUnlockSyllabus()
  const fork       = useForkSyllabus()
  const exportJob  = useExportSyllabus()

  async function handleFork(changeNote?: string) {
    const result = await fork.mutateAsync({ id: syllabus.id, payload: { change_note: changeNote } })
    navigate(`/syllabuses/${result.id}`)
  }

  const canExport = syllabus.status === 'FACULTY_APPROVED' || syllabus.status === 'ADMIN_LOCKED'

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">

      {/* DRAFT */}
      {syllabus.status === 'DRAFT' && canWrite && (
        <Button size="sm" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
          <Zap className="h-4 w-4 mr-1" />
          Generate with AI
        </Button>
      )}
      {syllabus.status === 'DRAFT' && canWrite && (
        <Button
          size="sm"
          className="bg-green-600 hover:bg-green-700"
          onClick={() => setApproveOpen(true)}
          disabled={approve.isPending}
        >
          <CheckCircle className="h-4 w-4 mr-1" />
          Approve
        </Button>
      )}
      {syllabus.status === 'DRAFT' && !canWrite && (
        <span className="text-sm text-gray-400">No actions available for your role.</span>
      )}

      {/* AI_GENERATING */}
      {syllabus.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          AI is generating the syllabus…
        </div>
      )}

      {/* FACULTY_APPROVED */}
      {syllabus.status === 'FACULTY_APPROVED' && canLock && (
        <Button
          size="sm"
          className="bg-orange-600 hover:bg-orange-700"
          onClick={() => setLockOpen(true)}
          disabled={lock.isPending}
        >
          <Lock className="h-4 w-4 mr-1" />
          Lock for Semester
        </Button>
      )}
      {syllabus.status === 'FACULTY_APPROVED' && canWrite && (
        <Button
          size="sm"
          variant="destructive"
          onClick={() => setRejectOpen(true)}
          disabled={reject.isPending}
        >
          <XCircle className="h-4 w-4 mr-1" />
          Reject
        </Button>
      )}

      {/* ADMIN_LOCKED */}
      {syllabus.status === 'ADMIN_LOCKED' && canLock && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => unlock.mutate(syllabus.id)}
          disabled={unlock.isPending}
        >
          <Unlock className="h-4 w-4 mr-1" />
          {unlock.isPending ? 'Unlocking…' : 'Unlock'}
        </Button>
      )}

      {/* Fork — available on FACULTY_APPROVED + ADMIN_LOCKED for canWrite or canLock */}
      {canExport && (canWrite || canLock) && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setForkOpen(true)}
          disabled={fork.isPending}
        >
          <GitFork className="h-4 w-4 mr-1" />
          Fork Version
        </Button>
      )}

      {/* Export — available on FACULTY_APPROVED + ADMIN_LOCKED */}
      {canExport && (
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
      <RejectSyllabusDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        onSubmit={(reason) => reject.mutate({ id: syllabus.id, payload: { reason } })}
        isPending={reject.isPending}
      />
      <LockSyllabusDialog
        open={lockOpen}
        onOpenChange={setLockOpen}
        onSubmit={(comment) => lock.mutate({ id: syllabus.id, payload: { comment } })}
        isPending={lock.isPending}
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
    </div>
  )
}
