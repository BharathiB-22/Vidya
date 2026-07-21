import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, LayoutTemplate, Rocket, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TimetableGrid, type MoveTarget } from '@/components/timetable/TimetableGrid'
import {
  addSlot, deleteSlot, deleteTimetable, getTimetable, publishTimetable,
  submitTimetable, swapSlots, updateSlot, updateTimetable,
} from '@/lib/api/timetable'
import { getErrorMessage } from '@/lib/api'
import type { AutofillPlan } from '@/lib/timetable/autofill'
import type { TimetableSlot } from '@/types/timetable'
import { GenerateTimetableDialog } from './GenerateTimetableDialog'
import { ChooseTemplateDialog } from './ChooseTemplateDialog'
import { SlotDialog, type SlotDraft } from './SlotDialog'
import { STATUS_COLORS, isEditableStatus, programLabel, timetableLabel } from './shared'

type CellTarget = { day: number; period: number }

/**
 * The Dean's timetable workspace: what this week is, and everything that can be
 * done to it.
 *
 * The action bar is driven by status, so the review workflow stays visible and
 * Publish cannot bypass approval:
 *
 *   DRAFT / REJECTED  Generate · Choose Template · Delete · Submit for Review
 *   PENDING_REVIEW    Delete · (approve/reject live on the review tab)
 *   APPROVED          Delete · Publish
 *   PUBLISHED         nothing — students and faculty are reading it
 *
 * Locks are session state. `timetable_slots` has no `is_locked` column yet, so a
 * lock survives navigation within the page and nothing more; the grid already
 * reads `slot.is_locked ?? lockedSlotIds.has(slot.id)` so the day that column
 * lands, only the source of truth changes.
 */
export function TimetableWorkspace({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient()

  const [addingAt, setAddingAt] = useState<CellTarget | null>(null)
  const [editingSlot, setEditingSlot] = useState<TimetableSlot | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [templateOpen, setTemplateOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [lockedSlotIds, setLockedSlotIds] = useState<ReadonlySet<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [genProgress, setGenProgress] = useState<[number, number] | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['timetable-detail', id],
    queryFn: () => getTimetable(id),
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['timetable-detail', id] })
    queryClient.invalidateQueries({ queryKey: ['timetables'] })
  }

  const addSlotMut = useMutation({
    mutationFn: (payload: SlotDraft) =>
      addSlot(id, { day_of_week: addingAt!.day, period_number: addingAt!.period, ...payload }),
    onSuccess: () => { setAddingAt(null); setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const editSlotMut = useMutation({
    mutationFn: (payload: SlotDraft) =>
      updateSlot(id, editingSlot!.id, {
        faculty_user_id: payload.faculty_user_id ?? null,
        room: payload.room ?? null,
        remarks: payload.remarks ?? null,
      }),
    onSuccess: () => { setEditingSlot(null); setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const moveSlotMut = useMutation({
    mutationFn: ({ slot, to }: { slot: TimetableSlot; to: MoveTarget }) =>
      updateSlot(id, slot.id, { day_of_week: to.day_of_week, period_number: to.period_number }),
    onSuccess: () => { setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const swapSlotsMut = useMutation({
    mutationFn: ({ a, b }: { a: TimetableSlot; b: TimetableSlot }) =>
      swapSlots(id, { slot_a_id: a.id, slot_b_id: b.id }),
    onSuccess: () => { setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const deleteSlotMut = useMutation({
    mutationFn: (slot: TimetableSlot) => deleteSlot(id, slot.id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const templateMut = useMutation({
    mutationFn: (templateId: string | null) => updateTimetable(id, { template_id: templateId }),
    onSuccess: () => { setTemplateOpen(false); setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const submitMut = useMutation({
    mutationFn: () => submitTimetable(id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const publishMut = useMutation({
    mutationFn: () => publishTimetable(id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const deleteMut = useMutation({
    mutationFn: () => deleteTimetable(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['timetables'] }); onBack() },
    onError: (e) => { setConfirmDelete(false); setError(getErrorMessage(e)) },
  })

  /**
   * Applies a generated plan one cell at a time through the ordinary add-slot
   * endpoint, so every placement is checked by the same server-side clash rules
   * a hand-placed entry is. A cell the server refuses is skipped rather than
   * abandoning the run — a faculty member teaching another section at that
   * period is a normal, expected refusal.
   */
  const generateMut = useMutation({
    mutationFn: async (plan: AutofillPlan) => {
      const refused: string[] = []
      for (let i = 0; i < plan.slots.length; i++) {
        const s = plan.slots[i]
        setGenProgress([i + 1, plan.slots.length])
        try {
          await addSlot(id, {
            day_of_week: s.day_of_week,
            period_number: s.period_number,
            course_id: s.course_id,
            faculty_user_id: s.faculty_user_id,
          })
        } catch (e) {
          refused.push(getErrorMessage(e))
        }
      }
      return refused
    },
    onSuccess: (refused) => {
      setGenProgress(null)
      invalidate()
      setError(
        refused.length === 0
          ? null
          : `${refused.length} period${refused.length === 1 ? '' : 's'} could not be placed: ${refused[0]}`,
      )
    },
    onError: (e) => { setGenProgress(null); setError(getErrorMessage(e)) },
  })

  if (isError) {
    return (
      <div className="space-y-4">
        <BackLink onBack={onBack} />
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load this timetable. Please go back and try again.
        </div>
      </div>
    )
  }

  if (isLoading || !data) {
    return <div className="h-64 rounded-xl bg-gray-50 animate-pulse" />
  }

  const editable = isEditableStatus(data.status)
  const published = data.status === 'PUBLISHED'

  function toggleLock(slot: TimetableSlot) {
    setLockedSlotIds((prev) => {
      const next = new Set(prev)
      if (next.has(slot.id)) next.delete(slot.id)
      else next.add(slot.id)
      return next
    })
  }

  function handleMove(slot: TimetableSlot, to: MoveTarget, occupant?: TimetableSlot) {
    if (!occupant) {
      moveSlotMut.mutate({ slot, to })
      return
    }
    // Two entries, one cell: the only non-destructive answer is to exchange them.
    const ok = window.confirm(
      `${occupant.course_code} is already there. Swap it with ${slot.course_code}?`,
    )
    if (ok) swapSlotsMut.mutate({ a: slot, b: occupant })
  }

  const identity = [
    programLabel(data),
    data.semester_label,
    data.section_name ? `Section ${data.section_name}` : null,
  ].filter(Boolean)

  return (
    // The grid is the workspace, so the chrome around it stays to a single
    // compact band and everything below is the week itself.
    <div className="space-y-3">
      <BackLink onBack={onBack} />

      {/* Header — what this timetable is, and what can be done to it */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h2 className="text-lg font-semibold tracking-tight text-gray-900">
              {identity[0] ?? 'Section'}
            </h2>
            {identity.slice(1).map((part) => (
              <span key={part as string} className="text-sm font-medium text-gray-500">
                · {part}
              </span>
            ))}
          </div>
          <div className="mt-1 flex items-center gap-2 flex-wrap text-[11px] text-gray-500">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${STATUS_COLORS[data.status] ?? 'bg-gray-100 text-gray-600'}`}>
              {data.status.replace('_', ' ')}
            </span>
            <span>{data.template ? data.template.name : 'No template — using plain Period 1–8'}</span>
            <span className="text-gray-500">·</span>
            <span>{data.slots.length} entr{data.slots.length === 1 ? 'y' : 'ies'}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {editable && (
            <>
              <Button size="sm" onClick={() => { setError(null); setGenerateOpen(true) }}>
                <Sparkles className="h-4 w-4 mr-1.5" />
                Generate Timetable
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setError(null); setTemplateOpen(true) }}>
                <LayoutTemplate className="h-4 w-4 mr-1.5" />
                Choose Template
              </Button>
            </>
          )}
          {editable && data.slots.length > 0 && (
            <Button size="sm" variant="outline" disabled={submitMut.isPending} onClick={() => submitMut.mutate()}>
              {submitMut.isPending ? 'Submitting…' : 'Submit for Review'}
            </Button>
          )}
          {data.status === 'APPROVED' && (
            <Button size="sm" disabled={publishMut.isPending} onClick={() => publishMut.mutate()}>
              <Rocket className="h-4 w-4 mr-1.5" />
              {publishMut.isPending ? 'Publishing…' : 'Publish'}
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={published || deleteMut.isPending}
            title={published ? 'A published timetable cannot be deleted — students and faculty are using it.' : undefined}
            onClick={() => setConfirmDelete(true)}
            className={published ? '' : 'text-red-600 hover:text-red-700 hover:bg-red-50'}
          >
            <Trash2 className="h-4 w-4 mr-1.5" />
            Delete
          </Button>
        </div>
      </div>

      {data.status === 'REJECTED' && data.review_comment && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <strong>Rejected:</strong> {data.review_comment}
        </div>
      )}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <TimetableGrid
        slots={data.slots}
        periods={data.template?.periods}
        workingDays={data.template?.working_days}
        saturdayMode={data.template?.saturday_mode}
        editable={editable}
        lockedSlotIds={lockedSlotIds}
        onAddSlot={editable ? (day, period) => { setError(null); setAddingAt({ day, period }) } : undefined}
        onEditSlot={editable ? (slot) => { setError(null); setEditingSlot(slot) } : undefined}
        onDeleteSlot={editable ? (slot) => deleteSlotMut.mutate(slot) : undefined}
        onMoveSlot={editable ? handleMove : undefined}
        onToggleLock={editable ? toggleLock : undefined}
      />

      {editable && (
        <p className="pb-2 text-[11px] leading-relaxed text-gray-600">
          Hover an entry for Edit · Move · Lock · Delete. A locked entry cannot be moved,
          overwritten or deleted, and Generate never fills a cell that already holds one.
        </p>
      )}

      {(addingAt || editingSlot) && (
        <SlotDialog
          open
          onOpenChange={(v) => { if (!v) { setAddingAt(null); setEditingSlot(null) } }}
          semesterId={data.semester_id}
          sectionId={data.section_id}
          dayOfWeek={editingSlot?.day_of_week ?? addingAt?.day ?? null}
          periodNumber={editingSlot?.period_number ?? addingAt?.period ?? null}
          editing={editingSlot}
          onSubmit={(p) => (editingSlot ? editSlotMut.mutate(p) : addSlotMut.mutate(p))}
          isSubmitting={addSlotMut.isPending || editSlotMut.isPending}
          error={error}
        />
      )}

      {generateOpen && (
        <GenerateTimetableDialog
          open
          onOpenChange={setGenerateOpen}
          timetable={data}
          onGenerate={(plan) => generateMut.mutate(plan)}
          isGenerating={generateMut.isPending}
          progress={genProgress}
          error={error}
        />
      )}

      {templateOpen && (
        <ChooseTemplateDialog
          open
          onOpenChange={setTemplateOpen}
          currentTemplateId={data.template_id}
          hasSlots={data.slots.length > 0}
          onChoose={(templateId) => templateMut.mutate(templateId)}
          isSaving={templateMut.isPending}
          error={error}
        />
      )}

      {confirmDelete && (
        <ConfirmDelete
          label={timetableLabel(data)}
          slotCount={data.slots.length}
          isDeleting={deleteMut.isPending}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => deleteMut.mutate()}
        />
      )}
    </div>
  )
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button onClick={onBack} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
      <ChevronLeft className="h-4 w-4" /> Back to timetables
    </button>
  )
}

function ConfirmDelete({
  label, slotCount, isDeleting, onCancel, onConfirm,
}: {
  label: string
  slotCount: number
  isDeleting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl space-y-3">
        <h3 className="text-base font-semibold text-gray-900">Delete this timetable?</h3>
        <p className="text-sm text-gray-600">
          <strong>{label}</strong> and its {slotCount} entr{slotCount === 1 ? 'y' : 'ies'} will be
          removed. Nothing else is touched — the programme, semester, subjects, faculty and their
          course assignments all remain.
        </p>
        <p className="text-sm text-gray-600">This cannot be undone.</p>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" disabled={isDeleting} onClick={onCancel}>Cancel</Button>
          <Button
            disabled={isDeleting}
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 text-white"
          >
            {isDeleting ? 'Deleting…' : 'Delete timetable'}
          </Button>
        </div>
      </div>
    </div>
  )
}
