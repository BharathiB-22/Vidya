// M08 Exam Setter — Faculty: paper editor with coverage panels, section grouping, regenerate
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Loader2, CheckCircle2, AlertTriangle,
  LockKeyhole, Send, Pencil, Trash2, XCircle, RefreshCw,
  BookOpen, BarChart2, ShieldCheck, FileDown, Plus, GripVertical,
  Copy, ArrowUp, ArrowDown, ClipboardCheck,
} from 'lucide-react'
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button } from '@/components/ui/button'
import {
  getExamPaper, listQuestions, getBloomsReport,
  submitForReview, sealPaper, releasePaper, editQuestion, deleteQuestion,
  deleteExamPaper, regenerateQuestion, exportPdf, addQuestion, reorderQuestions,
  boardDecision, duplicateQuestion,
} from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import { examStatusColor, examStatusLabel, canDeletePaper } from '@/lib/examStatus'
import {
  defaultRuleText,
  mapQuestionsToTemplate,
  normaliseDefinition,
  stableId,
  type MappedTemplate,
} from '@/lib/paperTemplate'
import { useWorkspace } from '@/lib/workspace'
import type {
  ExamPaper, ExamQuestion, BloomsComplianceReport,
  ExamQuestionUpdatePayload, ManualQuestionPayload, SectionConfig,
  CoCoverageEntry, UnitCoverageEntry, ExamWorkflow, PaperTemplateDefinition,
} from '@/types/exam'

const BLOOM_COLORS: Record<string, string> = {
  REMEMBER:   'bg-red-100 text-red-700',
  UNDERSTAND: 'bg-orange-100 text-orange-700',
  APPLY:      'bg-yellow-100 text-yellow-700',
  ANALYSE:    'bg-green-100 text-green-700',
  EVALUATE:   'bg-blue-100 text-blue-700',
  CREATE:     'bg-purple-100 text-purple-700',
}

const QTYPE_LABEL: Record<string, string> = {
  MCQ:             'MCQ',
  SHORT_ANSWER:    'Short',
  LONG_ANSWER:     'Long',
  PROBLEM_SOLVING: 'Problem',
}

const TERMINAL_STATUSES = new Set([
  'GENERATED', 'FAILED', 'SUBMITTED', 'BOARD_APPROVED', 'BOARD_RETURNED', 'SEALED', 'RELEASED',
])

export default function ExamPaperEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  // Gate UI on the ACTIVE WORKSPACE, not the base login role. The backend gates
  // every M08 action on viewing_role (= the active workspace, sent as
  // X-Active-Workspace), so a multi-responsibility account (e.g. base DEAN/BOARD
  // holding a FACULTY grant) acting in the Faculty workspace must be treated as
  // Faculty here too. Using user.role silently hid Faculty actions (Delete,
  // Submit, Seal, Release) whenever the base role wasn't FACULTY/ADMIN.
  const { activeWorkspace } = useWorkspace()

  const [setLabel,      setSetLabel]      = useState<'A' | 'B'>('A')
  const [sealModal,     setSealModal]     = useState(false)
  const [releaseAt,     setReleaseAt]     = useState('')
  const [editModal,     setEditModal]     = useState<ExamQuestion | null>(null)
  const [addModal,      setAddModal]      = useState(false)
  const [submitError,   setSubmitError]   = useState<string | null>(null)
  const [deleteError,   setDeleteError]   = useState<string | null>(null)
  const [actionError,   setActionError]   = useState<string | null>(null)
  const [regenQueued,   setRegenQueued]   = useState<Set<string>>(new Set())
  const [regenError,    setRegenError]    = useState<string | null>(null)
  const [pdfLoading,    setPdfLoading]    = useState(false)
  const [pdfError,      setPdfError]      = useState<string | null>(null)

  const isBoard   = activeWorkspace === 'BOARD'   || activeWorkspace === 'ADMIN'
  const isFaculty = activeWorkspace === 'FACULTY' || activeWorkspace === 'ADMIN'
  const isDean    = activeWorkspace === 'DEAN'    || activeWorkspace === 'ADMIN'

  const { data: paper, isLoading: paperLoading, isError: paperError } = useQuery({
    queryKey: ['exam-paper', id],
    queryFn:  () => getExamPaper(id!),
    refetchInterval: (query) => {
      const p = query.state.data as ExamPaper | undefined
      return p && TERMINAL_STATUSES.has(p.status) ? false : 3000
    },
  })

  const questionsEnabled = !!(
    paper && !['GENERATING', 'DRAFT', 'FAILED'].includes(paper.status)
  )

  // The template owns this paper's structure, and a template paper is a single
  // paper — so it is never filtered by set. Legacy blueprint/flat papers keep the
  // Set A / Set B split exactly as before.
  const hasTemplate = !!(
    paper?.template_definition && (paper.template_definition.blocks?.length || 0) > 0
  )
  const effectiveSet: 'A' | 'B' | undefined = hasTemplate ? undefined : setLabel

  const hasRegenInFlight = regenQueued.size > 0

  const { data: questions, isLoading: qLoading, isError: qError, error: qErrorObj } = useQuery({
    queryKey: ['exam-questions', id, effectiveSet],
    queryFn:  () => listQuestions(id!, effectiveSet),
    enabled:  questionsEnabled,
    refetchInterval: hasRegenInFlight ? 3000 : false,
  })

  const { data: bloomsReport } = useQuery({
    queryKey: ['exam-blooms', id],
    queryFn:  () => getBloomsReport(id!),
    enabled:  !!(paper && ['GENERATED','SUBMITTED','BOARD_APPROVED','BOARD_RETURNED'].includes(paper.status)),
  })

  const submitMut = useMutation({
    mutationFn: () => submitForReview(id!),
    onSuccess: () => {
      setSubmitError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err) => setSubmitError(getErrorMessage(err)),
  })

  // Board approves/publishes a semester paper directly from the editor.
  const boardApproveMut = useMutation({
    mutationFn: () => boardDecision(id!, { approved: true }),
    onSuccess: () => {
      setActionError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err) => setActionError(getErrorMessage(err)),
  })

  const reorderMut = useMutation({
    mutationFn: (orderedIds: string[]) => reorderQuestions(id!, orderedIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] }),
    onError: (err) => setActionError(getErrorMessage(err)),
  })

  const duplicateMut = useMutation({
    mutationFn: (qid: string) => duplicateQuestion(id!, qid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] }),
    onError: (err) => setActionError(getErrorMessage(err)),
  })

  // Move a question one position up/down. Works alongside drag-and-drop by
  // reusing the same reorder endpoint.
  function moveQuestion(qid: string, dir: 'up' | 'down') {
    if (!questions) return
    const ids = questions.map(q => q.id)
    const i = ids.indexOf(qid)
    const j = dir === 'up' ? i - 1 : i + 1
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    reorderMut.mutate(ids)
  }

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id || !questions) return
    const ids = questions.map(q => q.id)
    const from = ids.indexOf(String(active.id))
    const to = ids.indexOf(String(over.id))
    if (from < 0 || to < 0) return
    reorderMut.mutate(arrayMove(ids, from, to))
  }

  const sealMut = useMutation({
    mutationFn: (ra: string) => sealPaper(id!, { release_at: new Date(ra).toISOString() }),
    onSuccess: () => {
      setSealModal(false)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (qid: string) => deleteQuestion(id!, qid),
    onSuccess: () => {
      setDeleteError(null)
      qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
    },
    onError: (err) => setDeleteError(getErrorMessage(err)),
  })

  // Delete the whole paper. Only offered while Faculty owns it (see canDelete
  // below); on success there is nothing left to show, so return to the list.
  const deletePaperMut = useMutation({
    mutationFn: () => deleteExamPaper(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exam-papers'] })
      navigate('/exams')
    },
    onError: (err) => setActionError(getErrorMessage(err)),
  })

  // Board/Admin immediate release of a sealed paper (force_release — bypasses
  // the scheduled release_at).
  const releaseMut = useMutation({
    mutationFn: () => releasePaper(id!),
    onSuccess: () => {
      setActionError(null)
      qc.invalidateQueries({ queryKey: ['exam-paper', id] })
    },
    onError: (err) => setActionError(getErrorMessage(err)),
  })

  async function handleRegenerate(questionId: string) {
    setRegenError(null)
    setRegenQueued(prev => new Set(prev).add(questionId))
    try {
      await regenerateQuestion(id!, questionId)
      // Questions query auto-refetches every 3s while regenQueued has entries.
      // Clear the queued flag after 30s maximum.
      setTimeout(() => {
        setRegenQueued(prev => {
          const next = new Set(prev)
          next.delete(questionId)
          return next
        })
        qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
      }, 30_000)
    } catch (err) {
      setRegenQueued(prev => {
        const next = new Set(prev)
        next.delete(questionId)
        return next
      })
      setRegenError(getErrorMessage(err))
    }
  }

  if (paperLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading paper…
      </div>
    )
  }

  if (paperError || !paper) {
    return (
      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
          <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-800 text-sm">Exam paper not found</p>
            <p className="text-sm text-red-700 mt-1">
              This paper may have been deleted or you do not have access to it.
            </p>
            <button
              onClick={() => navigate('/exams')}
              className="text-sm text-red-600 underline mt-2"
            >
              Back to Exam Papers
            </button>
          </div>
        </div>
      </div>
    )
  }

  const isEditable       = paper.status === 'GENERATED' || paper.status === 'BOARD_RETURNED'
  const isInternalPaper  = paper.exam_workflow === 'INTERNAL'

  // Two totals for university patterns: paper.total_marks is the evaluation (max)
  // total; printed includes optional/choice questions. Derived from the blueprint.
  const printedMarks = (paper.blueprint ?? []).reduce(
    (sum, u) => sum + (u.rows ?? []).reduce((s, r) => s + (r.count || 0) * (r.marks || 0), 0),
    0,
  )
  const hasChoiceBlueprint = !!(paper.blueprint && paper.blueprint.length > 0 && printedMarks !== paper.total_marks)

  // Paper Template is the source of truth: reconstruct the exact Section /
  // Unit-Group / Full-Question hierarchy from the stored definition. Legacy
  // papers (no template) fall back to section/blueprint/flat rendering.
  const mappedTemplate: MappedTemplate | null =
    hasTemplate && questions ? mapQuestionsToTemplate(paper.template_definition!, questions) : null

  // Submit: both workflows submit for review. INTERNAL → Dean, BOARD_EXAM → Board.
  const canSubmit = isEditable && isFaculty

  // Board publishes a board-owned semester paper directly from the editor.
  const canBoardApprove = isBoard && !isInternalPaper && paper.status === 'GENERATED'

  // Delete and finalise (seal + release) are gated here by ROLE + status only;
  // the backend is the ownership authority (_assert_can_delete /
  // _assert_can_finalize re-check created_by and 403 a non-owner). This mirrors
  // the Exam Papers list, which offers Delete on the same role+status basis, so
  // the two views stay consistent — an earlier client-side
  // `created_by === user.id` check diverged from the list and silently hid the
  // button (e.g. Delete never appeared on a FAILED paper).
  //
  //   INTERNAL   finaliser = Dean (locks + releases, enforced server-side).
  //   BOARD_EXAM finaliser = Board.  (isDean/isBoard both include ADMIN.)
  const canFinalize = isInternalPaper ? isDean : isBoard
  const canSeal = paper.status === 'BOARD_APPROVED' && canFinalize
  const canRelease = paper.status === 'SEALED' && canFinalize

  // Deletable while Faculty owns it (canDeletePaper mirrors the backend
  // _DELETABLE_STATUSES: DRAFT / GENERATED / FAILED / BOARD_RETURNED).
  const canDelete = canDeletePaper(paper.status) && isFaculty

  // Section grouping: only when paper has section_config
  const hasSections = !!(paper.section_config && paper.section_config.length > 0)

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/exams')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{paper.title}</h1>
          <p className="text-sm text-gray-500">
            {paper.exam_type.replace('_', ' ')}
            {' · '}
            <span className={`font-medium ${isInternalPaper ? 'text-amber-600' : 'text-indigo-600'}`}>
              {isInternalPaper ? 'Internal Assessment' : 'Board Exam'}
            </span>
            {' · '}
            {hasChoiceBlueprint
              ? `Max ${paper.total_marks} · Printed ${printedMarks} marks`
              : `${paper.total_marks} marks`}
            {' · '}{paper.duration_mins} min
          </p>
        </div>
        <StatusBadge status={paper.status} workflow={paper.exam_workflow} />
      </div>

      {/* Generating spinner */}
      {paper.status === 'GENERATING' && (
        <div className="flex items-center gap-3 bg-blue-50 border border-blue-100 rounded-xl p-4 text-blue-700">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <div>
            <p className="font-medium">Generating questions…</p>
            <p className="text-sm text-blue-500">This usually takes 30–90 seconds. Page refreshes automatically.</p>
          </div>
        </div>
      )}

      {paper.status === 'DRAFT' && (
        <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-xl p-4 text-gray-600">
          <Loader2 className="w-5 h-5 animate-spin shrink-0" />
          <p className="text-sm">Waiting for generation to start…</p>
        </div>
      )}

      {paper.status === 'FAILED' && (
        <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
          <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-800 text-sm">Question generation failed</p>
            <p className="text-sm text-red-700 mt-1">
              {paper.failure_reason || 'An unexpected error occurred during generation.'}
            </p>
            <p className="text-xs text-red-600 mt-2">
              Go back and create a new exam paper to retry.
            </p>
          </div>
        </div>
      )}

      {paper.status === 'BOARD_RETURNED' && paper.board_comment && (
        <div className="flex gap-3 bg-orange-50 border border-orange-200 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-orange-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-orange-800 text-sm">
              {isInternalPaper ? 'Dean returned this paper' : 'Board returned this paper'}
            </p>
            <p className="text-sm text-orange-700 mt-1">{paper.board_comment}</p>
          </div>
        </div>
      )}

      {regenError && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {regenError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: Question list */}
        <div className="lg:col-span-2 space-y-4">

          {/* Set switcher — legacy blueprint/flat papers only. A template paper is
              ONE paper: two sets would split its questions between them and neither
              set would then hold the structure the template promised. */}
          {questionsEnabled && !hasTemplate && (
            <div className="flex gap-2">
              {(['A', 'B'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setSetLabel(s)}
                  className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                    setLabel === s
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                  }`}
                >
                  Set {s}
                </button>
              ))}
            </div>
          )}

          {/* Manual builder — Add Question (owner, while editable) */}
          {isEditable && questionsEnabled && (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddModal(true)}>
              <Plus className="w-4 h-4" /> Add Question
            </Button>
          )}

          {qLoading && <div className="text-gray-600 text-sm py-4">Loading questions…</div>}

          {qError && (
            <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-800 text-sm">Could not load questions</p>
                <p className="text-sm text-red-700 mt-1 font-mono">
                  {getErrorMessage(qErrorObj)}
                </p>
              </div>
            </div>
          )}

          {deleteError && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {deleteError}
            </div>
          )}

          {questionsEnabled && !qLoading && questions && questions.length === 0 && (
            <div className="text-gray-500 text-center py-8 border border-dashed border-gray-200 rounded-xl">
              {hasTemplate ? 'No questions in this paper yet.' : `No questions in Set ${setLabel}.`}
            </div>
          )}

          {questions && (
            mappedTemplate ? (
              <TemplateQuestionList
                mapped={mappedTemplate}
                editable={isEditable}
                regenQueued={regenQueued}
                onEdit={setEditModal}
                onDelete={(qid) => { setDeleteError(null); deleteMut.mutate(qid) }}
                onRegenerate={handleRegenerate}
              />
            ) : hasSections ? (
              <SectionedQuestionList
                questions={questions}
                sectionConfig={paper.section_config!}
                editable={isEditable}
                regenQueued={regenQueued}
                onEdit={setEditModal}
                onDelete={(qid) => { setDeleteError(null); deleteMut.mutate(qid) }}
                onRegenerate={handleRegenerate}
                onMoveUp={(qid) => moveQuestion(qid, 'up')}
                onMoveDown={(qid) => moveQuestion(qid, 'down')}
                onDuplicate={(qid) => { setActionError(null); duplicateMut.mutate(qid) }}
                orderIds={questions.map(q => q.id)}
              />
            ) : isEditable ? (
              // Drag-and-drop reorder for the flat manual/AI question list.
              // Move Up/Down + Duplicate buttons coexist with drag-and-drop.
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={questions.map(q => q.id)} strategy={verticalListSortingStrategy}>
                  <div className="space-y-3">
                    {questions.map((q, idx) => (
                      <SortableQuestionCard
                        key={q.id}
                        question={q}
                        index={idx + 1}
                        isRegenerating={regenQueued.has(q.id)}
                        onEdit={() => setEditModal(q)}
                        onDelete={() => { setDeleteError(null); deleteMut.mutate(q.id) }}
                        onRegenerate={() => handleRegenerate(q.id)}
                        onMoveUp={() => moveQuestion(q.id, 'up')}
                        onMoveDown={() => moveQuestion(q.id, 'down')}
                        onDuplicate={() => { setActionError(null); duplicateMut.mutate(q.id) }}
                        canMoveUp={idx > 0}
                        canMoveDown={idx < questions.length - 1}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            ) : (
              <FlatQuestionList
                questions={questions}
                editable={isEditable}
                regenQueued={regenQueued}
                onEdit={setEditModal}
                onDelete={(qid) => { setDeleteError(null); deleteMut.mutate(qid) }}
                onRegenerate={handleRegenerate}
              />
            )
          )}
        </div>

        {/* Right: Coverage panels + Bloom's + actions */}
        <div className="space-y-4">

          {/* CO Coverage */}
          {paper.co_coverage_report && paper.co_coverage_report.length > 0 && (
            <CoCoveragePanel report={paper.co_coverage_report} />
          )}

          {/* Unit Coverage */}
          {paper.unit_coverage_report && paper.unit_coverage_report.length > 0 && (
            <UnitCoveragePanel report={paper.unit_coverage_report} />
          )}

          {/* Bloom's compliance */}
          {bloomsReport && <BloomsPanel report={bloomsReport} />}

          {/* Paper validation summary — advisory, shown before submission */}
          {isEditable && questions && questions.length > 0 && (
            <PaperValidationPanel paper={paper} questions={questions} bloomsReport={bloomsReport} />
          )}

          {/* Action buttons */}
          <div className="space-y-2">

            {/* Submit for review — INTERNAL → Dean, BOARD_EXAM → Board */}
            {canSubmit && (
              <div className="space-y-2">
                <Button
                  onClick={() => { setSubmitError(null); submitMut.mutate() }}
                  disabled={submitMut.isPending}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
                >
                  {submitMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Send className="w-4 h-4" />
                  }
                  {isInternalPaper ? 'Submit for Dean Review' : 'Submit for Board Review'}
                </Button>
                <p className="text-xs text-gray-500 text-center">
                  {isInternalPaper
                    ? 'Internal Assessment — reviewed by the Dean, not the Board.'
                    : 'Semester paper — reviewed by the Board.'}
                </p>
                {submitError && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {submitError}
                  </p>
                )}
              </div>
            )}

            {/* Board publishes its own semester paper directly */}
            {canBoardApprove && (
              <div className="space-y-2">
                <Button
                  onClick={() => { setActionError(null); boardApproveMut.mutate() }}
                  disabled={boardApproveMut.isPending}
                  className="w-full bg-green-600 hover:bg-green-700 text-white gap-2"
                >
                  {boardApproveMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <ShieldCheck className="w-4 h-4" />
                  }
                  Approve &amp; Publish
                </Button>
                <p className="text-xs text-gray-500 text-center">Board owns this paper — approve, then seal.</p>
              </div>
            )}

            {actionError && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {actionError}
              </p>
            )}

            {/* Seal: BOARD/ADMIN only */}
            {canSeal && (
              <Button
                onClick={() => setSealModal(true)}
                className="w-full bg-purple-600 hover:bg-purple-700 text-white gap-2"
              >
                <LockKeyhole className="w-4 h-4" />
                Seal Paper
              </Button>
            )}

            {paper.status === 'SEALED' && (
              <div className="text-center text-sm text-purple-700 bg-purple-50 rounded-lg p-3 border border-purple-100">
                <LockKeyhole className="w-4 h-4 inline mr-1" />
                Paper sealed. Available from{' '}
                {paper.release_at ? new Date(paper.release_at).toLocaleString() : '—'}.
              </div>
            )}

            {/* Release now — BOARD/ADMIN immediate release, bypassing release_at */}
            {canRelease && (
              <Button
                onClick={() => { setActionError(null); releaseMut.mutate() }}
                disabled={releaseMut.isPending}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
              >
                {releaseMut.isPending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <CheckCircle2 className="w-4 h-4" />
                }
                Release Now
              </Button>
            )}

            {paper.status === 'RELEASED' && (
              <div className="text-center text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                <CheckCircle2 className="w-4 h-4 inline mr-1" />
                Released on {paper.released_at ? new Date(paper.released_at).toLocaleString() : '—'}.
              </div>
            )}

            {/* Export PDF — available when questions are readable */}
            {['GENERATED','SUBMITTED','BOARD_APPROVED','BOARD_RETURNED','RELEASED'].includes(paper.status) && (
              <div className="space-y-1 pt-1">
                <Button
                  variant="outline"
                  disabled={pdfLoading}
                  onClick={async () => {
                    setPdfError(null)
                    setPdfLoading(true)
                    try {
                      await exportPdf(id!, effectiveSet)
                    } catch (err: unknown) {
                      setPdfError(err instanceof Error ? err.message : 'PDF export failed.')
                    } finally {
                      setPdfLoading(false)
                    }
                  }}
                  className="w-full gap-2"
                >
                  {pdfLoading
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <FileDown className="w-4 h-4" />
                  }
                  {hasTemplate ? 'Export PDF' : `Export PDF (Set ${setLabel})`}
                </Button>
                {pdfError && (
                  <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {pdfError}
                  </p>
                )}
              </div>
            )}

            {/* Delete paper — only while Faculty owns it (DRAFT / GENERATED /
                FAILED / BOARD_RETURNED). Backend re-checks ownership and state. */}
            {canDelete && (
              <div className="pt-1">
                <Button
                  variant="outline"
                  disabled={deletePaperMut.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete "${paper.title}"? This cannot be undone.`)) {
                      setActionError(null)
                      deletePaperMut.mutate()
                    }
                  }}
                  className="w-full gap-2 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                >
                  {deletePaperMut.isPending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Trash2 className="w-4 h-4" />
                  }
                  Delete Paper
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Seal modal — opened only via the Lock button, which canSeal gates to the
          paper's finaliser (Dean for INTERNAL, Board for BOARD_EXAM). */}
      {sealModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <LockKeyhole className="w-5 h-5 text-purple-600" />
              Lock Exam Paper
            </h2>
            <p className="text-sm text-gray-600">
              After locking, the paper is encrypted and inaccessible until you release it.
              The paper is <b>not</b> released automatically — you release it manually when ready.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Planned Release Date &amp; Time *</label>
              <input
                type="datetime-local"
                value={releaseAt}
                onChange={e => setReleaseAt(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setSealModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={!releaseAt || sealMut.isPending}
                onClick={() => sealMut.mutate(releaseAt)}
                className="flex-1 bg-purple-600 hover:bg-purple-700 text-white gap-2"
              >
                {sealMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Confirm Seal
              </Button>
            </div>
            {sealMut.isError && (
              <p className="text-sm text-red-600">{getErrorMessage(sealMut.error)}</p>
            )}
          </div>
        </div>
      )}

      {/* Edit question modal */}
      {editModal && (
        <EditQuestionModal
          paperId={id!}
          question={editModal}
          onClose={() => {
            setEditModal(null)
            qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
          }}
        />
      )}

      {/* Add question modal (manual builder) */}
      {addModal && (
        <AddQuestionModal
          paperId={id!}
          template={hasTemplate ? paper.template_definition : null}
          onClose={() => {
            setAddModal(false)
            qc.invalidateQueries({ queryKey: ['exam-questions', id, setLabel] })
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sortable wrapper for a question card (drag & drop reorder)
// ---------------------------------------------------------------------------

function SortableQuestionCard({
  question, index, isRegenerating, onEdit, onDelete, onRegenerate,
  onMoveUp, onMoveDown, onDuplicate, canMoveUp, canMoveDown,
}: {
  question:       ExamQuestion
  index:          number
  isRegenerating: boolean
  onEdit:         () => void
  onDelete:       () => void
  onRegenerate:   () => void
  onMoveUp?:      () => void
  onMoveDown?:    () => void
  onDuplicate?:   () => void
  canMoveUp?:     boolean
  canMoveDown?:   boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: question.id })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.6 : 1 }
  return (
    <div ref={setNodeRef} style={style} className="flex items-start gap-2">
      <button
        type="button"
        className="mt-3 text-gray-500 hover:text-gray-500 cursor-grab active:cursor-grabbing shrink-0"
        title="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="w-4 h-4" />
      </button>
      <div className="flex-1 min-w-0">
        <QuestionCard
          question={question}
          index={index}
          editable
          isRegenerating={isRegenerating}
          onEdit={onEdit}
          onDelete={onDelete}
          onRegenerate={onRegenerate}
          onMoveUp={onMoveUp}
          onMoveDown={onMoveDown}
          onDuplicate={onDuplicate}
          canMoveUp={canMoveUp}
          canMoveDown={canMoveDown}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Question list variants
// ---------------------------------------------------------------------------

interface QuestionListProps {
  questions:    ExamQuestion[]
  editable:     boolean
  regenQueued:  Set<string>
  onEdit:       (q: ExamQuestion) => void
  onDelete:     (id: string) => void
  onRegenerate: (id: string) => void
  onMoveUp?:    (id: string) => void
  onMoveDown?:  (id: string) => void
  onDuplicate?: (id: string) => void
  orderIds?:    string[]
}

function FlatQuestionList({ questions, editable, regenQueued, onEdit, onDelete, onRegenerate }: QuestionListProps) {
  return (
    <div className="space-y-3">
      {questions.map((q, idx) => (
        <QuestionCard
          key={q.id}
          question={q}
          index={idx + 1}
          editable={editable}
          isRegenerating={regenQueued.has(q.id)}
          onEdit={() => onEdit(q)}
          onDelete={() => onDelete(q.id)}
          onRegenerate={() => onRegenerate(q.id)}
        />
      ))}
    </div>
  )
}

function SectionedQuestionList({
  questions, sectionConfig, editable, regenQueued, onEdit, onDelete, onRegenerate,
  onMoveUp, onMoveDown, onDuplicate, orderIds,
}: QuestionListProps & { sectionConfig: SectionConfig[] }) {
  const globalIndex = (qid: string) => (orderIds ? orderIds.indexOf(qid) : -1)
  const total = orderIds?.length ?? 0
  const bySection = new Map<string, ExamQuestion[]>()
  const uncat: ExamQuestion[] = []

  for (const q of questions) {
    if (q.section_label) {
      const group = bySection.get(q.section_label) ?? []
      group.push(q)
      bySection.set(q.section_label, group)
    } else {
      uncat.push(q)
    }
  }

  const ordered = [...sectionConfig].sort((a, b) => a.order - b.order)

  return (
    <div className="space-y-6">
      {ordered.map(sec => {
        const qs = bySection.get(sec.label) ?? []
        return (
          <div key={sec.label} className="space-y-3">
            <SectionHeader section={sec} count={qs.length} />
            {qs.length === 0 ? (
              <p className="text-sm text-gray-600 py-2 pl-2">No questions generated for Part {sec.label}.</p>
            ) : (
              qs.map((q, idx) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  index={idx + 1}
                  editable={editable}
                  isRegenerating={regenQueued.has(q.id)}
                  onEdit={() => onEdit(q)}
                  onDelete={() => onDelete(q.id)}
                  onRegenerate={() => onRegenerate(q.id)}
                  onMoveUp={onMoveUp ? () => onMoveUp(q.id) : undefined}
                  onMoveDown={onMoveDown ? () => onMoveDown(q.id) : undefined}
                  onDuplicate={onDuplicate ? () => onDuplicate(q.id) : undefined}
                  canMoveUp={globalIndex(q.id) > 0}
                  canMoveDown={globalIndex(q.id) < total - 1}
                />
              ))
            )}
          </div>
        )
      })}
      {uncat.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Other</p>
          {uncat.map((q, idx) => (
            <QuestionCard
              key={q.id}
              question={q}
              index={idx + 1}
              editable={editable}
              isRegenerating={regenQueued.has(q.id)}
              onEdit={() => onEdit(q)}
              onDelete={() => onDelete(q.id)}
              onRegenerate={() => onRegenerate(q.id)}
              onMoveUp={onMoveUp ? () => onMoveUp(q.id) : undefined}
              onMoveDown={onMoveDown ? () => onMoveDown(q.id) : undefined}
              onDuplicate={onDuplicate ? () => onDuplicate(q.id) : undefined}
              canMoveUp={globalIndex(q.id) > 0}
              canMoveDown={globalIndex(q.id) < total - 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SectionHeader({ section, count }: { section: SectionConfig; count: number }) {
  const allMustAnswer = section.answer_q === section.total_q
  const rule = allMustAnswer
    ? `Answer all ${section.total_q}`
    : `Answer any ${section.answer_q} of ${section.total_q}`
  return (
    <div className="flex items-center gap-3 pb-2 border-b border-gray-200">
      <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 text-sm font-bold shrink-0">
        {section.label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-800">Part {section.label}</p>
        <p className="text-xs text-gray-500">
          {rule} · {section.marks_each} marks each
          {section.mcq_only ? ' · MCQ only' : ''}
          {' · '}{count} generated
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Template-structured question list — Sections of Question Definitions
// ---------------------------------------------------------------------------
// Mirrors the PDF's `_render_template`: same section headers, same rule lines,
// same numbering, same "— OR —". A template is sections and definitions and
// nothing else, so this renders exactly those and never a block "kind".

interface TemplateListProps {
  mapped:       MappedTemplate
  editable:     boolean
  regenQueued:  Set<string>
  onEdit:       (q: ExamQuestion) => void
  onDelete:     (id: string) => void
  onRegenerate: (id: string) => void
}

// "A" -> "SECTION A"; "Part A" -> "PART A". Mirrors the PDF's header so the
// editor and the printed paper read the same.
function sectionHeading(name: string): string {
  const n = (name || '').trim()
  if (!n) return 'SECTION'
  return /^(SECTION|PART|MODULE|UNIT|GROUP)/i.test(n) ? n.toUpperCase() : `SECTION ${n.toUpperCase()}`
}

function TemplateQuestionList({ mapped, editable, regenQueued, onEdit, onDelete, onRegenerate }: TemplateListProps) {
  // Numbering follows the printed layout, not generation order: each printed
  // question takes one number, and a full question takes one however many parts
  // it has.
  let n = 0

  return (
    <div className="space-y-8">
      {mapped.sections.map(sec => {
        const printedQuestions = sec.definitions.reduce((s, d) => s + d.questions.length, 0)

        return (
          <div key={sec.id} className="space-y-3">
            <div className="flex items-center gap-3 pb-2 border-b border-gray-200">
              <span className="inline-flex items-center px-2.5 h-8 rounded-lg bg-indigo-100 text-indigo-700 text-sm font-bold shrink-0">
                {sectionHeading(sec.name)}
              </span>
              <p className="text-xs text-gray-500">
                {sec.instruction?.trim() || defaultRuleText({
                  ...sec, definitions: sec.definitions.map(d => d.definition),
                })}
                {' · '}{sec.evaluation} evaluated · {sec.printed} printed
              </p>
            </div>

            {printedQuestions === 0 ? (
              <p className="text-sm text-gray-600 pl-2">No questions generated for this section yet.</p>
            ) : (
              sec.definitions.flatMap(def =>
                def.questions.map((mq, qi) => {
                  const num = ++n
                  const key = `${def.id}-${qi}`

                  // A full question — "Q1 a) b) c)". An either/or part labels its
                  // two alternatives with consecutive letters, the way a real
                  // paper reads.
                  if (mq.parts.length > 0) {
                    let letter = 0
                    const rows = mq.parts.flatMap(p =>
                      p.questions.map((q, ai) => ({
                        q, label: String.fromCharCode(97 + letter++), orBefore: ai > 0,
                      })),
                    )
                    return (
                      <div key={key} className="space-y-2 border border-gray-200 rounded-xl p-3">
                        <p className="text-sm font-bold text-gray-800">
                          Q{num} <span className="text-gray-600 font-normal">({mq.marks} Marks)</span>
                        </p>
                        {rows.map(({ q, label, orBefore }) => (
                          <div key={q.id}>
                            {orBefore && (
                              <p className="text-xs text-center text-gray-600 font-medium py-0.5">— OR —</p>
                            )}
                            <div className="flex items-start gap-2 pl-1">
                              <span className="text-xs font-bold text-gray-600 mt-3 w-5 shrink-0">{label})</span>
                              <div className="flex-1 min-w-0">
                                <QuestionCard
                                  question={q} index={num} hideIndex editable={editable}
                                  isRegenerating={regenQueued.has(q.id)}
                                  onEdit={() => onEdit(q)} onDelete={() => onDelete(q.id)}
                                  onRegenerate={() => onRegenerate(q.id)}
                                />
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  }

                  // A plain question, or an either/or printed as two alternatives
                  // under one number.
                  return (
                    <div key={key} className="space-y-1">
                      {mq.alternatives.map((q, ai) => (
                        <div key={q.id}>
                          {ai > 0 && (
                            <p className="text-xs text-center text-gray-600 font-medium py-0.5">— OR —</p>
                          )}
                          <QuestionCard
                            question={q} index={num} hideIndex={ai > 0} editable={editable}
                            isRegenerating={regenQueued.has(q.id)}
                            onEdit={() => onEdit(q)} onDelete={() => onDelete(q.id)}
                            onRegenerate={() => onRegenerate(q.id)}
                          />
                        </div>
                      ))}
                    </div>
                  )
                }),
              )
            )}
          </div>
        )
      })}

      {/* A paper that cannot be rebuilt from its own template is a bug, and it is
          reported as one. Quietly listing the questions under "Other" would show
          the faculty a paper that is not the template they configured. */}
      {mapped.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <p className="font-semibold">This paper does not match its template.</p>
          <p className="mt-0.5">{mapped.error} Please report this paper — regenerating it will rebuild the structure.</p>
        </div>
      )}

      {mapped.leftover.length > 0 && (
        <div className="space-y-3">
          {/* Legacy papers (generated before questions recorded their template
              definition) can still have questions the template cannot place. */}
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
            Unplaced — this paper predates template tracking
          </p>
          {mapped.leftover.map((q, i) => (
            <QuestionCard
              key={q.id} question={q} index={i + 1} editable={editable}
              isRegenerating={regenQueued.has(q.id)}
              onEdit={() => onEdit(q)} onDelete={() => onDelete(q.id)} onRegenerate={() => onRegenerate(q.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Question card
// ---------------------------------------------------------------------------

function QuestionCard({
  question, index, editable, isRegenerating, onEdit, onDelete, onRegenerate,
  onMoveUp, onMoveDown, onDuplicate, canMoveUp = true, canMoveDown = true, hideIndex = false,
}: {
  question:       ExamQuestion
  index:          number
  editable:       boolean
  isRegenerating: boolean
  onEdit:         () => void
  onDelete:       () => void
  onRegenerate:   () => void
  onMoveUp?:      () => void
  onMoveDown?:    () => void
  onDuplicate?:   () => void
  canMoveUp?:     boolean
  canMoveDown?:   boolean
  hideIndex?:     boolean
}) {
  const bloomColor = BLOOM_COLORS[question.bloom_level] ?? 'bg-gray-100 text-gray-600'
  return (
    <div className={`border rounded-xl bg-white p-4 space-y-2 transition-colors ${
      isRegenerating ? 'border-indigo-300 bg-indigo-50/40' : 'border-gray-200 hover:border-gray-300'
    }`}>
      <div className="flex items-start gap-3">
        {!hideIndex && <span className="text-xs font-bold text-gray-600 mt-0.5 shrink-0">Q{index}</span>}
        <div className="flex-1 min-w-0">
          {isRegenerating ? (
            <div className="flex items-center gap-2 text-sm text-indigo-600">
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              Regenerating question…
            </div>
          ) : (
            <p className="text-sm text-gray-900 leading-snug">{question.question_text}</p>
          )}
        </div>
        {editable && !isRegenerating && (
          <div className="flex gap-1 shrink-0">
            {onMoveUp && (
              <Button
                variant="ghost" size="icon" className="h-7 w-7"
                title="Move up" disabled={!canMoveUp} onClick={onMoveUp}
              >
                <ArrowUp className="w-3.5 h-3.5 text-gray-600" />
              </Button>
            )}
            {onMoveDown && (
              <Button
                variant="ghost" size="icon" className="h-7 w-7"
                title="Move down" disabled={!canMoveDown} onClick={onMoveDown}
              >
                <ArrowDown className="w-3.5 h-3.5 text-gray-600" />
              </Button>
            )}
            {onDuplicate && (
              <Button
                variant="ghost" size="icon" className="h-7 w-7"
                title="Duplicate question" onClick={onDuplicate}
              >
                <Copy className="w-3.5 h-3.5 text-gray-600" />
              </Button>
            )}
            <Button
              variant="ghost" size="icon" className="h-7 w-7"
              title="Regenerate question"
              onClick={onRegenerate}
            >
              <RefreshCw className="w-3.5 h-3.5 text-indigo-400" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="Edit question" onClick={onEdit}>
              <Pencil className="w-3.5 h-3.5 text-gray-600" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="Delete question" onClick={onDelete}>
              <Trash2 className="w-3.5 h-3.5 text-red-400" />
            </Button>
          </div>
        )}
      </div>

      {!isRegenerating && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bloomColor}`}>
            {question.bloom_level}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 font-medium">
            {QTYPE_LABEL[question.question_type] ?? question.question_type}
          </span>
          {question.section_label && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 font-medium">
              Part {question.section_label}
            </span>
          )}
          <span className="text-xs text-gray-500">Unit {question.unit_number}</span>
          {question.co_ids && question.co_ids.length > 0 && (
            <span className="text-xs text-gray-600">{question.co_ids.length} CO</span>
          )}
          <span className="text-xs text-gray-500 ml-auto">{question.marks} marks</span>
          <span className="text-xs text-gray-600">Set: {question.set_membership.join(', ')}</span>
          {question.is_edited && (
            <span className="text-xs text-orange-500 font-medium">edited</span>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Coverage panels
// ---------------------------------------------------------------------------

function CoCoveragePanel({ report }: { report: CoCoverageEntry[] }) {
  const allCovered = report.every(e => e.covered)
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-gray-600" />
          CO Coverage
        </h3>
        {allCovered ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> All covered
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> Gaps
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {report.map(entry => (
          <div key={entry.co_id} className="flex items-center gap-2 text-xs">
            <span className={`font-medium w-12 shrink-0 ${entry.covered ? 'text-gray-700' : 'text-orange-600'}`}>
              {entry.co_code}
            </span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${entry.covered ? 'bg-green-400' : 'bg-orange-300'}`}
                style={{ width: entry.covered ? '100%' : '20%' }} />
            </div>
            <span className="text-gray-600 w-8 text-right shrink-0">{entry.question_count}Q</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-600 italic">Advisory only — does not block workflow.</p>
    </div>
  )
}

function UnitCoveragePanel({ report }: { report: UnitCoverageEntry[] }) {
  const allCovered = report.every(e => e.covered)
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <BarChart2 className="w-3.5 h-3.5 text-gray-600" />
          Unit Coverage
        </h3>
        {allCovered ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> All units
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> Gaps
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {report.map(entry => (
          <div
            key={entry.unit_no}
            className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border ${
              entry.covered
                ? 'bg-green-50 text-green-700 border-green-200'
                : 'bg-orange-50 text-orange-700 border-orange-200'
            }`}
          >
            U{entry.unit_no}
            <span className={`${entry.covered ? 'text-green-500' : 'text-orange-400'}`}>
              {entry.question_count}Q
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-600 italic">Advisory only — does not block workflow.</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Paper validation summary (advisory — does not block submission)
// ---------------------------------------------------------------------------

function PaperValidationPanel({
  paper, questions, bloomsReport,
}: {
  paper:        ExamPaper
  questions:    ExamQuestion[]
  bloomsReport?: BloomsComplianceReport
}) {
  const totalQ       = questions.length
  const marksSum     = questions.reduce((s, q) => s + (Number(q.marks) || 0), 0)
  const missingText  = questions.filter(q => !q.question_text || !q.question_text.trim()).length
  const missingMarks = questions.filter(q => !(Number(q.marks) > 0)).length
  const missingCO    = questions.filter(
    q => !((q.co_code && q.co_code.trim()) || (q.co_ids && q.co_ids.length > 0))
  ).length
  const uncoveredUnits = paper.units_included.filter(u => !questions.some(q => q.unit_number === u))
  const marksMatch     = marksSum === paper.total_marks

  const checks: Array<{ ok: boolean | null; label: string; detail: string }> = [
    { ok: totalQ > 0,            label: 'Questions present',        detail: `${totalQ} question${totalQ !== 1 ? 's' : ''}` },
    { ok: missingText === 0,     label: 'Every question has text',  detail: missingText === 0 ? 'OK' : `${missingText} missing` },
    { ok: missingMarks === 0,    label: 'Every question has marks', detail: missingMarks === 0 ? 'OK' : `${missingMarks} missing` },
    { ok: marksMatch,            label: 'Total marks',              detail: `${marksSum} / ${paper.total_marks}` },
    { ok: uncoveredUnits.length === 0, label: 'Unit coverage',      detail: uncoveredUnits.length === 0 ? 'All units covered' : `Units ${uncoveredUnits.join(', ')} not covered` },
    { ok: missingCO === 0,       label: 'CO mapping',               detail: missingCO === 0 ? 'OK' : `${missingCO} without a CO` },
    {
      ok:     bloomsReport ? bloomsReport.compliance_ok : null,
      label:  "Bloom's distribution",
      detail: bloomsReport
        ? (bloomsReport.compliance_ok ? 'Within tolerance' : `${bloomsReport.violations.length} deviation${bloomsReport.violations.length !== 1 ? 's' : ''}`)
        : 'Not evaluated',
    },
  ]

  const warnCount = checks.filter(c => c.ok === false).length

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <ClipboardCheck className="w-3.5 h-3.5 text-gray-600" />
          Paper Validation
        </h3>
        {warnCount === 0 ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> Ready
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> {warnCount} to review
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {checks.map(c => (
          <div key={c.label} className="flex items-center gap-2 text-xs">
            {c.ok === true ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
            ) : c.ok === false ? (
              <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0" />
            ) : (
              <span className="w-3.5 h-3.5 rounded-full bg-gray-200 shrink-0" />
            )}
            <span className={`flex-1 ${c.ok === false ? 'text-orange-700 font-medium' : 'text-gray-600'}`}>
              {c.label}
            </span>
            <span className="text-gray-600 text-right">{c.detail}</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-600 italic">
        Advisory only — checks do not block submission unless enforced by the server.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Bloom's panel (unchanged)
// ---------------------------------------------------------------------------

function BloomsPanel({ report }: { report: BloomsComplianceReport }) {
  const levels = Object.entries(report.actual_dist) as Array<[string, number]>
  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Bloom's Compliance</h3>
        {report.compliance_ok ? (
          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> OK
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-orange-600 font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> {report.violations.length} violation{report.violations.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {levels.map(([lvl, actual]) => {
          const reqDist = report.requested_dist as unknown as Record<string, number>
          const requested = reqDist[lvl] ?? 0
          const isViolation = report.violations.some(v => v.level === lvl.toUpperCase())
          return (
            <div key={lvl} className="space-y-0.5">
              <div className="flex justify-between text-xs text-gray-500">
                <span className={isViolation ? 'text-orange-600 font-medium' : ''}>
                  {lvl.charAt(0) + lvl.slice(1).toLowerCase()}
                </span>
                <span>{actual.toFixed(0)}% <span className="text-gray-500">(req {requested.toFixed(0)}%)</span></span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${isViolation ? 'bg-orange-400' : 'bg-indigo-400'}`}
                  style={{ width: `${Math.min(actual, 100)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status, workflow }: { status: string; workflow?: ExamWorkflow }) {
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-semibold ${examStatusColor(status)}`}>
      {examStatusLabel(status, workflow)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Edit question modal (unchanged)
// ---------------------------------------------------------------------------

function EditQuestionModal({
  paperId, question, onClose,
}: {
  paperId:  string
  question: ExamQuestion
  onClose:  () => void
}) {
  const [text,  setText]  = useState(question.question_text)
  const [marks, setMarks] = useState(question.marks)
  const [bloom, setBloom] = useState(question.bloom_level)
  const [unit,  setUnit]  = useState(question.unit_number)
  const [co,    setCo]    = useState(question.co_code ?? '')

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: (payload: ExamQuestionUpdatePayload) =>
      editQuestion(paperId, question.id, payload),
    onSuccess: onClose,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Pencil className="w-5 h-5 text-indigo-600" />
          Edit Question
        </h2>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Question Text</label>
            <textarea
              rows={4}
              value={text}
              onChange={e => setText(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Marks</label>
              <input
                type="number" min={0.5} step={0.5}
                value={marks}
                onChange={e => setMarks(Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Bloom Level</label>
              <select
                value={bloom}
                onChange={e => setBloom(e.target.value as typeof bloom)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                {['REMEMBER','UNDERSTAND','APPLY','ANALYSE','EVALUATE','CREATE'].map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Unit</label>
              <input
                type="number" min={0} value={unit}
                onChange={e => setUnit(Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">CO</label>
              <input
                value={co} onChange={e => setCo(e.target.value)} placeholder="e.g. CO2"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
          </div>
        </div>
        {isError && (
          <p className="text-sm text-red-600">{getErrorMessage(error)}</p>
        )}
        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={isPending}
            onClick={() => mutate({ question_text: text, marks, bloom_level: bloom, unit_number: unit, co_code: co.trim() || null })}
          >
            {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add question modal (manual builder)
// ---------------------------------------------------------------------------

const BLOOMS = ['REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE'] as const
const QTYPES = ['MCQ', 'SHORT_ANSWER', 'LONG_ANSWER', 'PROBLEM_SOLVING',
  'CASE_STUDY', 'PROGRAMMING'] as const

// Every place a question can live in a templated paper: a question definition, or
// one sub-part of a definition that has parts. A question must be added into one
// of these — the template is the paper's structure, so there is nowhere else to
// put it.
//
// `unit` is null when the definition pools more than one unit (the compiler
// distributes those), and the faculty picks which one this hand-written question
// covers.
interface BlockChoice {
  key:      string
  label:    string
  block_id: string
  subpart:  number | null
  unit:     number | null
  marks:    number
}

function templateBlockChoices(def: PaperTemplateDefinition | null): BlockChoice[] {
  const doc = normaliseDefinition(def)
  const out: BlockChoice[] = []

  doc.sections.forEach((sec, si) => {
    const secName = sectionHeading(sec.name || String(si + 1))
    sec.definitions.forEach((qd, di) => {
      const id = stableId(qd, 'qd', di)
      // A pool of exactly one unit pins it; anything else is the faculty's call.
      const pinned = qd.units.length === 1 ? qd.units[0] : null

      if (!qd.parts.length) {
        out.push({
          key: id,
          label: `${secName} — ${qd.marks} marks`
            + (qd.units.length ? ` (Unit${qd.units.length > 1 ? 's' : ''} ${qd.units.join(', ')})` : ''),
          block_id: id, subpart: null, unit: pinned, marks: qd.marks,
        })
        return
      }

      qd.parts.forEach((p, pi) => {
        const partUnits = p.units.length ? p.units : qd.units
        out.push({
          key: `${id}:${pi}`,
          label: `${secName} — part ${String.fromCharCode(97 + pi)}) — ${p.marks} marks`
            + (partUnits.length ? ` (Unit${partUnits.length > 1 ? 's' : ''} ${partUnits.join(', ')})` : ''),
          block_id: id, subpart: pi,
          unit: partUnits.length === 1 ? partUnits[0] : null,
          marks: p.marks,
        })
      })
    })
  })
  return out
}

function AddQuestionModal({ paperId, template, onClose }: {
  paperId: string
  template: PaperTemplateDefinition | null
  onClose: () => void
}) {
  const choices = useMemo(() => templateBlockChoices(template), [template])
  const [blockKey, setBlockKey] = useState(choices[0]?.key ?? '')
  const chosen = choices.find(c => c.key === blockKey) ?? null

  const [text,    setText]    = useState('')
  const [qtype,   setQtype]   = useState<typeof QTYPES[number]>('SHORT_ANSWER')
  const [marks,   setMarks]   = useState(chosen?.marks ?? 5)
  const [bloom,   setBloom]   = useState<typeof BLOOMS[number]>('REMEMBER')
  const [unit,    setUnit]    = useState(chosen?.unit ?? 1)
  const [co,      setCo]      = useState('')
  const [section, setSection] = useState('')
  const [answer,  setAnswer]  = useState('')

  // The chosen block fixes the marks — that is structure, not a per-question
  // choice. The unit follows the block only when the block pins one; a section
  // spans units, so there the faculty says which unit this question covers.
  function selectBlock(key: string) {
    setBlockKey(key)
    const c = choices.find(x => x.key === key)
    if (!c) return
    setMarks(c.marks)
    if (c.unit != null) setUnit(c.unit)
  }

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: (payload: ManualQuestionPayload) => addQuestion(paperId, payload),
    onSuccess: onClose,
  })

  const inputCls = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Plus className="w-5 h-5 text-indigo-600" /> Add Question
        </h2>
        <div className="space-y-3">
          {choices.length > 0 && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Add to *</label>
              <select value={blockKey} onChange={e => selectBlock(e.target.value)} className={inputCls}>
                {choices.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
              <p className="text-[11px] text-gray-600">
                This paper follows a template — the question prints inside the block you pick,
                which sets its unit and marks.
              </p>
            </div>
          )}
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Question Text *</label>
            <textarea rows={4} value={text} onChange={e => setText(e.target.value)} className={`${inputCls} resize-none`} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Type</label>
              <select value={qtype} onChange={e => setQtype(e.target.value as typeof qtype)} className={inputCls}>
                {QTYPES.map(t => <option key={t} value={t}>{QTYPE_LABEL[t] ?? t}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Marks *</label>
              <input type="number" min={0.5} step={0.5} value={marks} onChange={e => setMarks(Number(e.target.value))} className={inputCls} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Bloom's Level</label>
              <select value={bloom} onChange={e => setBloom(e.target.value as typeof bloom)} className={inputCls}>
                {BLOOMS.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Unit</label>
              <input type="number" min={0} value={unit} onChange={e => setUnit(Number(e.target.value))} className={inputCls} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">CO (optional)</label>
              <input value={co} onChange={e => setCo(e.target.value)} placeholder="e.g. CO2" className={inputCls} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Section (optional)</label>
              <input value={section} onChange={e => setSection(e.target.value)} placeholder="A / B / C" className={inputCls} />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Model Answer (optional)</label>
            <textarea rows={2} value={answer} onChange={e => setAnswer(e.target.value)} className={`${inputCls} resize-none`} />
          </div>
        </div>
        {isError && <p className="text-sm text-red-600">{getErrorMessage(error)}</p>}
        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={isPending || !text.trim() || marks <= 0 || (choices.length > 0 && !chosen)}
            onClick={() => mutate({
              question_text: text.trim(),
              question_type: qtype,
              marks,
              bloom_level: bloom,
              unit_number: unit,
              co_code: co.trim() || null,
              section_label: section.trim() || null,
              model_answer: answer.trim() || null,
              template_block_id:      chosen?.block_id ?? null,
              template_subpart_index: chosen?.subpart ?? null,
            })}
          >
            {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add'}
          </Button>
        </div>
      </div>
    </div>
  )
}
