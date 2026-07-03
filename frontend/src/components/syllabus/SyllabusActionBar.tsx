import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2, GitFork, Download, CheckCircle, XCircle, Zap,
  Lock, Unlock, Eye, Send, Trash2, RotateCcw, MessageSquareWarning,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  GenerateSyllabusDialog,
  ApproveSyllabusDialog,
  RejectSyllabusDialog,
  RequestRevisionDialog,
  LockSyllabusDialog,
  ForkSyllabusDialog,
  ExportSyllabusDialog,
  DeleteConfirmDialog,
} from './SyllabusActionDialogs'
import {
  useGenerateSyllabus,
  useSubmitSyllabusForReview,
  useApproveSyllabus,
  useRejectSyllabus,
  useRequestRevision,
  useResubmitSyllabus,
  useLockSyllabus,
  useUnlockSyllabus,
  useForkSyllabus,
  useExportSyllabus,
} from '@/hooks/syllabuses'
import { useDeleteSyllabus } from '@/hooks/syllabuses'
import type { Syllabus } from '@/types/syllabus'
import { useWorkspace } from '@/lib/workspace'

// Governance roles
const FACULTY_ROLES = ['FACULTY']
const DEAN_ROLES    = ['DEAN']
const VIEW_ROLES    = ['ADMIN', 'FACULTY', 'DEAN', 'STUDENT']

// Faculty may delete in these statuses
const FACULTY_DELETABLE = new Set(['DRAFT', 'AI_GENERATING', 'PENDING_REVIEW', 'REJECTED'])

interface Props {
  syllabus: Syllabus
}

export function SyllabusActionBar({ syllabus }: Props) {
  const navigate   = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const isFaculty  = FACULTY_ROLES.includes(role)
  const isDean     = DEAN_ROLES.includes(role)
  const canView    = VIEW_ROLES.includes(role)

  const [generateOpen,        setGenerateOpen]        = useState(false)
  const [submitOpen,          setSubmitOpen]          = useState(false)
  const [resubmitOpen,        setResubmitOpen]        = useState(false)
  const [approveOpen,         setApproveOpen]         = useState(false)
  const [rejectOpen,          setRejectOpen]          = useState(false)
  const [requestRevisionOpen, setRequestRevisionOpen] = useState(false)
  const [lockOpen,            setLockOpen]            = useState(false)
  const [forkOpen,            setForkOpen]            = useState(false)
  const [exportOpen,          setExportOpen]          = useState(false)
  const [deleteOpen,          setDeleteOpen]          = useState(false)

  const generate       = useGenerateSyllabus(syllabus.id)
  const submit         = useSubmitSyllabusForReview()
  const resubmit       = useResubmitSyllabus()
  const approve        = useApproveSyllabus()
  const reject         = useRejectSyllabus()
  const requestRevision = useRequestRevision()
  const lock           = useLockSyllabus()
  const unlock         = useUnlockSyllabus()
  const fork           = useForkSyllabus()
  const exportJob      = useExportSyllabus()
  const deleteSyllabus = useDeleteSyllabus()

  async function handleFork(changeNote?: string) {
    const result = await fork.mutateAsync({ id: syllabus.id, payload: { change_note: changeNote } })
    navigate(`/syllabuses/${result.id}`)
  }

  function handleDelete() {
    deleteSyllabus.mutate(syllabus.id, {
      onSuccess: () => navigate(-1),
    })
  }

  const canExport     = syllabus.status === 'DEAN_APPROVED' || syllabus.status === 'DEAN_LOCKED'
  const canFacDelete  = isFaculty && FACULTY_DELETABLE.has(syllabus.status)

  if (!canView) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <Eye className="h-4 w-4 text-gray-400" />
        <span className="text-sm text-gray-400">Read-only view.</span>
      </div>
    )
  }

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
            className="bg-orange-600 hover:bg-orange-700"
            onClick={() => setRequestRevisionOpen(true)}
            disabled={requestRevision.isPending}
          >
            <MessageSquareWarning className="h-4 w-4 mr-1" />
            Request Revision
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

      {/* ── REJECTED — faculty actions ── */}
      {syllabus.status === 'REJECTED' && isFaculty && (
        <>
          <Button
            size="sm"
            className="bg-blue-600 hover:bg-blue-700"
            onClick={() => setResubmitOpen(true)}
            disabled={resubmit.isPending}
          >
            <RotateCcw className="h-4 w-4 mr-1" />
            Resubmit for Review
          </Button>
        </>
      )}

      {/* ── REJECTED — dean read-only notice ── */}
      {syllabus.status === 'REJECTED' && isDean && (
        <div className="flex items-center gap-2 text-sm text-orange-700 bg-orange-50 border border-orange-200 rounded px-3 py-1.5">
          <XCircle className="h-4 w-4 text-orange-500" />
          Returned to faculty for revision.
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

      {/* ── Delete — Faculty (allowed statuses) ── */}
      {canFacDelete && (
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

      {/* Resubmit — simple confirm */}
      <Dialog open={resubmitOpen} onOpenChange={setResubmitOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Resubmit for Dean Review</DialogTitle></DialogHeader>
          <p className="text-sm text-gray-600 py-2">
            Confirm that you have addressed the Dean's feedback and are ready to resubmit.
            A compliance check will run before submission.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResubmitOpen(false)}>Cancel</Button>
            <Button
              className="bg-blue-600 hover:bg-blue-700"
              onClick={() => { resubmit.mutate(syllabus.id); setResubmitOpen(false) }}
              disabled={resubmit.isPending}
            >
              {resubmit.isPending ? 'Resubmitting…' : 'Resubmit'}
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
      <RequestRevisionDialog
        open={requestRevisionOpen}
        onOpenChange={setRequestRevisionOpen}
        onSubmit={(comments) => requestRevision.mutate({ id: syllabus.id, payload: { comments } })}
        isPending={requestRevision.isPending}
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
