import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, GitFork, Download, CheckCircle, XCircle, Zap, Lock, Unlock, Eye, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
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
  useSubmitSyllabusForReview,
  useApproveSyllabus,
  useRejectSyllabus,
  useLockSyllabus,
  useUnlockSyllabus,
  useForkSyllabus,
  useExportSyllabus,
} from '@/hooks/syllabuses'
import type { Syllabus } from '@/types/syllabus'

// Corrected governance roles:
//   FACULTY — create, edit, generate, submit-for-review
//   DEAN    — approve, reject, lock, unlock
//   ADMIN   — read-only (operational support, not academic governance)
const FACULTY_ROLES = ['FACULTY']
const DEAN_ROLES    = ['DEAN']
const VIEW_ROLES    = ['ADMIN', 'FACULTY', 'DEAN', 'STUDENT']

interface Props {
  syllabus: Syllabus
}

export function SyllabusActionBar({ syllabus }: Props) {
  const navigate = useNavigate()
  const role     = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const isFaculty = FACULTY_ROLES.includes(role)
  const isDean    = DEAN_ROLES.includes(role)
  const canView   = VIEW_ROLES.includes(role)

  const [generateOpen, setGenerateOpen] = useState(false)
  const [submitOpen,   setSubmitOpen]   = useState(false)
  const [approveOpen,  setApproveOpen]  = useState(false)
  const [rejectOpen,   setRejectOpen]   = useState(false)
  const [lockOpen,     setLockOpen]     = useState(false)
  const [forkOpen,     setForkOpen]     = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)

  const generate  = useGenerateSyllabus(syllabus.id)
  const submit    = useSubmitSyllabusForReview()
  const approve   = useApproveSyllabus()
  const reject    = useRejectSyllabus()
  const lock      = useLockSyllabus()
  const unlock    = useUnlockSyllabus()
  const fork      = useForkSyllabus()
  const exportJob = useExportSyllabus()

  async function handleFork(changeNote?: string) {
    const result = await fork.mutateAsync({ id: syllabus.id, payload: { change_note: changeNote } })
    navigate(`/syllabuses/${result.id}`)
  }

  const canExport = syllabus.status === 'DEAN_APPROVED' || syllabus.status === 'DEAN_LOCKED'

  if (!canView) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <Eye className="h-4 w-4 text-gray-400" />
        <span className="text-sm text-gray-400">Read-only view.</span>
      </div>
    )
  }

  const hasAnyAction =
    (syllabus.status === 'DRAFT' && isFaculty) ||
    (syllabus.status === 'PENDING_REVIEW' && isDean) ||
    (syllabus.status === 'DEAN_APPROVED' && isDean) ||
    (syllabus.status === 'DEAN_LOCKED' && isDean) ||
    canExport

  return (
    <div className="flex items-center gap-2 flex-wrap rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">

      {/* ── DRAFT — faculty actions ── */}
      {syllabus.status === 'DRAFT' && isFaculty && (
        <Button size="sm" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
          <Zap className="h-4 w-4 mr-1" />
          Generate with AI
        </Button>
      )}
      {syllabus.status === 'DRAFT' && isFaculty && (
        <Button
          size="sm"
          className="bg-blue-600 hover:bg-blue-700"
          onClick={() => setSubmitOpen(true)}
          disabled={submit.isPending}
        >
          <Send className="h-4 w-4 mr-1" />
          Submit for Review
        </Button>
      )}

      {/* ── AI_GENERATING ── */}
      {syllabus.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
          AI is generating the syllabus…
        </div>
      )}

      {/* ── PENDING_REVIEW — Dean actions ── */}
      {syllabus.status === 'PENDING_REVIEW' && isDean && (
        <>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-700"
            onClick={() => setApproveOpen(true)}
            disabled={approve.isPending}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setRejectOpen(true)}
            disabled={reject.isPending}
          >
            <XCircle className="h-4 w-4 mr-1" />
            Reject
          </Button>
        </>
      )}

      {/* ── PENDING_REVIEW — faculty read-only notice ── */}
      {syllabus.status === 'PENDING_REVIEW' && isFaculty && (
        <div className="flex items-center gap-2 text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-1.5">
          <Send className="h-4 w-4 text-blue-500" />
          Awaiting Dean review — syllabus is locked for editing.
        </div>
      )}

      {/* ── DEAN_APPROVED — Dean lock action ── */}
      {syllabus.status === 'DEAN_APPROVED' && isDean && (
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

      {/* ── DEAN_LOCKED — Dean unlock ── */}
      {syllabus.status === 'DEAN_LOCKED' && isDean && (
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

      {/* ── Fork — Dean/Faculty on approved+ ── */}
      {canExport && (isDean || isFaculty) && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setForkOpen(true)}
          disabled={fork.isPending}
        >
          <GitFork className="h-4 w-4 mr-1" />
          {fork.isPending ? 'Forking…' : 'Fork Version'}
        </Button>
      )}

      {/* ── Export — Dean_Approved / Dean_Locked ── */}
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

      {/* No actions for this role/status */}
      {!hasAnyAction && syllabus.status !== 'AI_GENERATING' && (
        <span className="text-sm text-gray-400">No actions available for your role.</span>
      )}

      {/* Role chip */}
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
      {/* Submit for review — simple confirm */}
      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Submit for Dean Review</DialogTitle></DialogHeader>
          <p className="text-sm text-gray-600 py-2">
            This will lock the syllabus for editing and send it to the Dean for approval.
            Ensure all content is complete before submitting.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSubmitOpen(false)}>Cancel</Button>
            <Button
              className="bg-blue-600 hover:bg-blue-700"
              onClick={() => { submit.mutate(syllabus.id); setSubmitOpen(false) }}
              disabled={submit.isPending}
            >
              {submit.isPending ? 'Submitting…' : 'Submit'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
