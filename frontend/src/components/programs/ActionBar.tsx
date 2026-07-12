import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2, GitFork, Download, Zap, AlertTriangle, Pencil, Trash2, Rocket, Lock,
  Send, Eye, Landmark, ClipboardList,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  EditProgramDialog,
  DeleteProgramDialog,
  GenerateDialog,
  PublishDialog,
  ExportDialog,
} from './ActionDialogs'
import { SubmitToBoardFlow } from '@/components/governance/SubmitToBoardFlow'
import { BoardChangeSummary } from '@/components/governance/BoardChangeSummary'
import {
  useGenerateProgram,
  usePublishProgram,
  useExportProgram,
  useForkProgram,
  useUpdateProgram,
  useDeleteProgram,
} from '@/hooks/programs'
import { useSubmitForApproval } from '@/hooks/governance'
import { addToast } from '@/hooks/useToast'
import type { Program } from '@/types/program'
import type { SubmissionSection } from '@/types/governance'
import { useWorkspace } from '@/lib/workspace'
import { useGovernance } from '@/lib/governance'

/**
 * Who can do what to a curriculum, by state (Phase A — Academic Governance).
 *
 *   DRAFT / GENERATION_FAILED   Dean edits, generates, deletes, SUBMITS.
 *   PENDING_APPROVAL            The Board owns it. It edits the structure here and
 *                               does its syllabus work in the Curriculum Workbench,
 *                               which is also where it approves. The Dean sees a
 *                               read-only banner — permanently: there is no return.
 *   APPROVED (locked)           Dean reads what the Board changed, then PUBLISHES.
 *                               Nobody edits.
 *   PUBLISHED                   Read-only forever. New version for any change.
 *
 * This component only decides what to SHOW. The API enforces the same rules — a
 * hidden button is a courtesy, not a control.
 */

const DEAN_ROLES = ['ADMIN', 'DEAN']

interface Props {
  program: Program
  /**
   * Switch the page to a tab. Lets the submission checklist take the Dean
   * straight to whatever is missing instead of leaving them to hunt for it.
   */
  onNavigateToSection?: (section: SubmissionSection) => void
}

export function ActionBar({ program, onNavigateToSection }: Props) {
  const navigate = useNavigate()
  const { activeWorkspace: role } = useWorkspace()
  const { bodyLabel } = useGovernance()

  const isDean       = DEAN_ROLES.includes(role)
  const isGovernance = role === 'BOARD'

  const [generateOpen, setGenerateOpen] = useState(false)
  const [submitOpen,   setSubmitOpen]   = useState(false)
  const [publishOpen,  setPublishOpen]  = useState(false)
  const [exportOpen,   setExportOpen]   = useState(false)
  const [editOpen,     setEditOpen]     = useState(false)
  const [deleteOpen,   setDeleteOpen]   = useState(false)

  const generate  = useGenerateProgram(program.id)
  const submit    = useSubmitForApproval()
  const publish   = usePublishProgram()
  const exportJob = useExportProgram()
  const fork      = useForkProgram()
  const update    = useUpdateProgram()
  const del       = useDeleteProgram()

  async function handleFork() {
    const forked = await fork.mutateAsync(program.id)
    addToast(
      'New version created as a Draft, with the official syllabi carried forward. ' +
        'Revise it, then submit it.',
      'success',
      9000,
    )
    navigate(`/programs/${forked.id}`)
  }

  async function handleDelete() {
    await del.mutateAsync(program.id)
    addToast('Curriculum deleted.', 'success')
    navigate('/programs')
  }

  const deanHoldsIt = program.status === 'DRAFT'
  const locked = program.status === 'APPROVED' || program.status === 'PUBLISHED'

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm px-4 py-3">
      {/*
        Once the Board has finalized the curriculum, the Dean gets it back as
        something they cannot edit and can only publish. So the first thing they
        need is not a button — it is an answer to "what did the Board change?".
      */}
      {locked && isDean && <BoardChangeSummary programId={program.id} />}

      <div className="flex items-center gap-2 flex-wrap">
        {/* ---------------- Dean's window: DRAFT ---------------- */}
        {deanHoldsIt && isDean && (
          <>
            <Button size="sm" onClick={() => setSubmitOpen(true)} disabled={submit.isPending}>
              <Send className="h-4 w-4 mr-1" />
              {submit.isPending ? 'Submitting…' : `Submit to the ${bodyLabel}`}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
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
        {deanHoldsIt && !isDean && (
          <span className="text-sm text-gray-600">
            The Dean is still preparing this curriculum. It has not been submitted yet.
          </span>
        )}

        {/* ---------------- GENERATION_FAILED ---------------- */}
        {program.status === 'GENERATION_FAILED' && isDean && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 text-red-600" />
              AI generation failed.
            </div>
            <Button size="sm" variant="destructive" onClick={() => setGenerateOpen(true)} disabled={generate.isPending}>
              <Zap className="h-4 w-4 mr-1" />
              Retry
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4 mr-1" />
              Edit
            </Button>
          </div>
        )}

        {/* ---------------- AI_GENERATING ---------------- */}
        {program.status === 'AI_GENERATING' && (
          <div className="flex items-center gap-2 text-sm text-amber-700">
            <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
            AI is drafting the curriculum structure. It will come back to you as a Draft to review.
          </div>
        )}

        {/* ---------------- The Board's window: PENDING_APPROVAL ----------------
            The Board may keep editing the structure here for the whole review.
            Its syllabus work and its approval both live in the Workbench, which
            is the screen built for them. */}
        {program.status === 'PENDING_APPROVAL' && isGovernance && (
          <>
            <Button size="sm" onClick={() => navigate(`/governance/curriculum/${program.id}`)}>
              <Landmark className="h-4 w-4 mr-1" />
              Open Curriculum Workbench
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4 mr-1" />
              Edit Structure
            </Button>
            <span className="ml-1 text-sm text-gray-600">
              Revise subjects, credits and semesters freely — then write the official syllabus and
              approve in the Workbench.
            </span>
          </>
        )}
        {program.status === 'PENDING_APPROVAL' && !isGovernance && (
          <div className="flex items-center gap-1.5 text-sm text-gray-700">
            <Eye className="h-4 w-4 text-gray-500" />
            With the {bodyLabel} — read-only. They will review it, enhance it where the academics
            require, write the official syllabus and finalize it. You will be notified when it is
            ready to publish.
          </div>
        )}

        {/* ---------------- APPROVED (locked) ---------------- */}
        {program.status === 'APPROVED' && (
          <>
            <div className="flex items-center gap-1.5 text-sm text-gray-700">
              <Lock className="h-4 w-4 text-emerald-600" />
              Reviewed and finalized by the {bodyLabel}. Locked.
            </div>
            {isDean && (
              <Button
                size="sm"
                className="bg-emerald-600 hover:bg-emerald-700"
                onClick={() => setPublishOpen(true)}
                disabled={publish.isPending}
              >
                <Rocket className="h-4 w-4 mr-1" />
                Publish
              </Button>
            )}
            {isDean && (
              <Button size="sm" variant="outline" onClick={handleFork} disabled={fork.isPending}>
                <GitFork className="h-4 w-4 mr-1" />
                {fork.isPending ? 'Creating…' : 'Create New Version'}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExportOpen(true)} disabled={exportJob.isPending}>
              <Download className="h-4 w-4 mr-1" />
              Export
            </Button>
          </>
        )}

        {/* ---------------- PUBLISHED ---------------- */}
        {program.status === 'PUBLISHED' && (
          <>
            <div className="flex items-center gap-1.5 text-sm text-gray-700">
              <Lock className="h-4 w-4 text-gray-500" />
              Published and locked. Faculty now hold their assigned subjects under this curriculum.
            </div>
            {isDean && (
              <Button size="sm" variant="outline" onClick={() => navigate('/dean/academic-ownership')}>
                <ClipboardList className="h-4 w-4 mr-1" />
                Assign Faculty
              </Button>
            )}
            {isDean && (
              <Button size="sm" variant="outline" onClick={handleFork} disabled={fork.isPending}>
                <GitFork className="h-4 w-4 mr-1" />
                {fork.isPending ? 'Creating…' : 'Create New Version'}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExportOpen(true)} disabled={exportJob.isPending}>
              <Download className="h-4 w-4 mr-1" />
              Export
            </Button>
          </>
        )}
      </div>

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
      <SubmitToBoardFlow
        open={submitOpen}
        onOpenChange={setSubmitOpen}
        programId={program.id}
        onSubmit={(note) =>
          submit.mutate(
            { id: program.id, payload: { note } },
            { onSuccess: () => setSubmitOpen(false) },
          )
        }
        onNavigate={(section) => {
          // 'settings' is not a tab — the Academic Year and Batch live on the
          // programme itself, so send the Dean to the dialog that edits them.
          if (section === 'settings') setEditOpen(true)
          else onNavigateToSection?.(section)
        }}
        isPending={submit.isPending}
      />
      <PublishDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        onSubmit={(comment) => publish.mutate({ id: program.id, payload: { comment } })}
        isPending={publish.isPending}
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
