import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, Lock, AlertTriangle, BookOpen } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { SyllabusActionBar } from '@/components/syllabus/SyllabusActionBar'
import { COSection } from '@/components/syllabus/COSection'
import { COPOMatrix } from '@/components/syllabus/COPOMatrix'
import { ReferencesSection } from '@/components/syllabus/ReferencesSection'
import { CompliancePanel } from '@/components/syllabus/CompliancePanel'
import { SyllabusApprovalPanel } from '@/components/syllabus/SyllabusApprovalPanel'
import { CourseInformationHeader } from '@/components/syllabus/CourseInformationHeader'
import { OfficialSyllabusDocument } from '@/components/syllabus/OfficialSyllabusDocument'
import {
  useDeanEditDocument,
  useGenerationProgress,
  useSyllabus,
  useSyllabusOutcomes,
  useSyllabusUnits,
  useSyllabusReferences,
} from '@/hooks/syllabuses'
import { isExecutionDocument } from '@/types/program'
import { syllabusKeys } from '@/hooks/syllabuses/useSyllabuses'
import { AIGeneratingBanner } from '@/components/shared/AIGeneratingBanner'
import { useWorkspace } from '@/lib/workspace'

type Tab =
  | 'document'
  | 'outcomes'
  | 'matrix'
  | 'references'
  | 'compliance'
  | 'approval'

interface TabDef {
  key:   Tab
  label: string
  badge?: (counts: ContentCounts) => number | null
}

interface ContentCounts {
  outcomes:   number
  units:      number
  references: number
}

// The DOCUMENT comes first, and it is where the Board works. What survives beside it
// are the structured editors the document cannot be: the CO-PO matrix is a grid, the
// reference search calls CrossRef, compliance is a report, approval is a gate.
//
// TWO TABS ARE GONE (P1.10), and their absence is the point:
//
//   Units      the units ARE the document — title, topics, hours, all editable in
//              place on the Official Syllabus page, which is where a syllabus is
//              read and therefore where it should be written. A separate tab holding
//              a second editor for the same rows was the Board editing its syllabus
//              in a form and then going somewhere else to see what it had said.
//
//   Overview   a page of counts. "5 units, 6 outcomes, 12 references" is not a thing
//              anybody needs a tab for: the document shows all three by existing, and
//              a dashboard about a document you are two clicks from reading is
//              furniture.
const TABS: TabDef[] = [
  { key: 'document',   label: 'Official Syllabus' },
  { key: 'outcomes',   label: 'Course Outcomes',  badge: (c) => c.outcomes || null },
  { key: 'matrix',     label: 'CO-PO Matrix' },
  { key: 'references', label: 'References',        badge: (c) => c.references || null },
  { key: 'compliance', label: 'Compliance' },
  { key: 'approval',   label: 'Approval' },
]

/**
 * Who owns this document: the Board, and only the Board.
 *
 * DRAFT and APPROVED are both editable by the Board — approval is a sign-off, not
 * a freeze, and editing an approved syllabus simply returns it to draft for
 * re-approval. LOCKED means the curriculum was approved, and nothing inside a
 * locked curriculum ever changes again.
 *
 * Faculty never edit any of it, in any state. They teach to the published
 * syllabus and build lesson plans, PPTs, course kits and assignments under it.
 */
const EDITABLE_STATUSES = new Set(['DRAFT', 'APPROVED'])

export default function SyllabusDetailPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()
  const [tab, setTab] = useState<Tab>('document')
  const { activeWorkspace: role } = useWorkspace()
  const isFaculty = role === 'FACULTY'

  const syllabusId = id ?? ''
  const { data: syllabus, isLoading, isError } = useSyllabus(syllabusId)
  const { data: outcomes   = [] } = useSyllabusOutcomes(syllabusId)
  const { data: units      = [] } = useSyllabusUnits(syllabusId)
  const { data: references = [] } = useSyllabusReferences(syllabusId)

  const isGenerating = syllabus?.status === 'AI_GENERATING'
  const isLocked     = syllabus?.status === 'LOCKED'
  const isApproved   = syllabus?.status === 'APPROVED'

  /*
   * WHO owns this document — and therefore who may edit it.
   *
   * The Board owns the taught curriculum: theory syllabi and lab manuals. The Dean
   * owns the execution documents: internship, mini project, major project, seminar,
   * whose content depends on the host company, the supervisor and the review calendar.
   * Each authority edits its own and reads the other's. The API enforces this with a
   * 403 either way; this decides what the page offers.
   */
  const deanOwned = !!syllabus && isExecutionDocument(syllabus.doc_type)
  const isOwner = deanOwned
    ? role === 'DEAN' || role === 'ADMIN'
    : role === 'BOARD' || role === 'ADMIN'

  const isEditable =
    !!syllabus && EDITABLE_STATUSES.has(syllabus.status) && isOwner

  /*
   * The Dean's edit of an execution document he has ALREADY approved.
   *
   * These documents change after they are signed off, and legitimately: the host
   * company changes, a supervisor leaves, the review calendar moves. So the Dean may
   * still adapt them, and his approval survives the edit — it is stamped against his
   * name rather than withdrawn.
   *
   * Before approval he edits through the ordinary path, like any owner of a draft.
   * A theory syllabus is never editable this way and the API refuses it with 403.
   */
  const deanEdit = useDeanEditDocument(syllabusId)
  const canDeanEditApproved =
    deanOwned &&
    (role === 'DEAN' || role === 'ADMIN') &&
    (isApproved || isLocked)

  // What the AI is doing right now — "Generating Unit III…". The job writes it as it
  // works; this only prints it.
  const progressMessage = useGenerationProgress(syllabusId, isGenerating)

  // Track whether AI generation was running in this session so we can detect failure
  const [wasGenerating, setWasGenerating] = useState(false)
  useEffect(() => {
    if (isGenerating) setWasGenerating(true)
  }, [isGenerating])
  const generationFailed =
    wasGenerating && !isGenerating &&
    syllabus?.status === 'DRAFT' &&
    outcomes.length === 0 && units.length === 0

  // Auto-poll the detail query while AI generation is running
  useEffect(() => {
    if (!isGenerating) return
    const timer = setInterval(() => {
      qc.invalidateQueries({ queryKey: syllabusKeys.detail(syllabusId) })
    }, 5000)
    return () => clearInterval(timer)
  }, [isGenerating, syllabusId, qc])

  const counts: ContentCounts = {
    outcomes:   outcomes.length,
    units:      units.length,
    references: references.length,
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError || !syllabus) {
    return (
      <div className="p-8 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-3 text-red-400" />
        <p className="text-sm text-red-600 mb-3">Failed to load syllabus.</p>
        <Button variant="outline" onClick={() => navigate(-1)}>Go back</Button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-5">

      {/* ── Header ── */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="shrink-0 mt-1">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1 min-w-0">

          {/* Course name */}
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight leading-snug">
            {syllabus.course_title ?? 'Syllabus'}
          </h1>

          {/* Program · Semester */}
          {(syllabus.program_name || syllabus.semester) && (
            <p className="text-sm text-gray-500 mt-0.5">
              {[
                syllabus.program_name,
                syllabus.semester ? `Semester ${syllabus.semester}` : null,
              ].filter(Boolean).join(' · ')}
            </p>
          )}

          {/* Course code + status + version row */}
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            {syllabus.course_code && syllabus.course_code !== '—' && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-600 bg-gray-100 border border-gray-200 px-2.5 py-1 rounded-full">
                <BookOpen className="h-3 w-3" />
                {syllabus.course_code}
              </span>
            )}
            <SyllabusStatusBadge status={syllabus.status} viewerRole={role} />
            <span className="text-xs text-gray-600 font-medium">Version {syllabus.version}</span>
            <span className="text-gray-300 text-xs select-none">·</span>
            <span className="text-xs text-gray-500">
              Created {new Date(syllabus.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}
            </span>
          </div>

        </div>
      </div>

      {/* ── Action bar ── */}
      <SyllabusActionBar syllabus={syllabus} />

      {/* ── Course Information — the official syllabus header ── */}
      {syllabus.course_information && (
        <CourseInformationHeader info={syllabus.course_information} />
      )}

      {/* ── Status banners ── */}
      {isLocked && (
        <div className="flex items-start gap-2 rounded-lg border border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-800">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-gray-600" />
          <span>
            This is the <strong>official syllabus</strong> of an approved curriculum, and it is
            locked permanently. Nobody may edit it — not Faculty, not the Dean, not the board.
            {isFaculty
              ? ' Teach to it, and build your lesson plans, materials and assessments under it.'
              : ' A change means a new curriculum version.'}
          </span>
        </div>
      )}

      {isApproved && isOwner && !deanOwned && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <span>
            You have <strong>approved</strong> this syllabus. It will be locked when the curriculum
            is approved. You may still revise it until then — but editing it returns it to draft,
            and it will need approving again.
          </span>
        </div>
      )}

      {isFaculty && !isLocked && (
        <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
          <span>
            This document is still being written{deanOwned ? ' by the Dean' : ' by the governance authority'} and
            is not yet official. It is <strong>read-only</strong> for you.
          </span>
        </div>
      )}

      <AIGeneratingBanner
        isGenerating={isGenerating}
        failed={generationFailed}
        entity="syllabus"
        message={progressMessage}
      />

      {/* ── Tab bar ── */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0 overflow-x-auto" role="tablist">
          {TABS.map((t) => {
            const badge = t.badge?.(counts)
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  tab === t.key
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {t.label}
                {badge != null && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                    tab === t.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'
                  }`}>
                    {badge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* ── Tab content ── */}
      <div className="min-h-[24rem]">

        {tab === 'document' && (
          <>
            {canDeanEditApproved && (
              <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                <p className="font-semibold">
                  You may still adapt this document after approving it.
                </p>
                <p className="mt-0.5 text-blue-800">
                  Internship, project and seminar documents depend on the host company, the
                  supervisor and the review calendar — and those change. Your edits do not
                  withdraw your approval; they are recorded against your name in the governance
                  trail.
                </p>
              </div>
            )}
            <OfficialSyllabusDocument
              syllabus={syllabus}
              outcomes={outcomes}
              units={units}
              references={references}
              // The owner edits a DRAFT; the Dean may additionally edit an execution
              // document he has already approved. Each is refused server-side if it is
              // not theirs.
              canEdit={isEditable || canDeanEditApproved}
              onSaveDocument={
                canDeanEditApproved
                  ? (document) => deanEdit.mutate({ document })
                  : undefined
              }
              onSaveDocumentPending={deanEdit.isPending}
            />
          </>
        )}

        {tab === 'outcomes' && (
          <COSection
            syllabusId={syllabusId}
            outcomes={outcomes}
            isEditable={isEditable}
          />
        )}

        {tab === 'matrix' && (
          <COPOMatrix
            syllabusId={syllabusId}
            isEditable={isEditable}
          />
        )}

        {tab === 'references' && (
          <ReferencesSection
            syllabusId={syllabusId}
            references={references}
            isEditable={isEditable}
          />
        )}

        {tab === 'compliance' && (
          <CompliancePanel syllabusId={syllabusId} />
        )}

        {tab === 'approval' && (
          <SyllabusApprovalPanel
            syllabus={syllabus}
            onTabChange={(t) => setTab(t as Tab)}
          />
        )}
      </div>
    </div>
  )
}

