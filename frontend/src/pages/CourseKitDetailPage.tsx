import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, AlertTriangle, Archive, CheckCircle2, Circle, Zap } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { CourseKitStatusBadge } from '@/components/courseKit/CourseKitStatusBadge'
import { CourseKitActionBar } from '@/components/courseKit/CourseKitActionBar'
import { SlidesSection } from '@/components/courseKit/SlidesSection'
import { QuizletsSection } from '@/components/courseKit/QuizletsSection'
import { AssignmentsSection } from '@/components/courseKit/AssignmentsSection'
import { TeachingPlanSection } from '@/components/courseKit/TeachingPlanSection'
import { KitCompliancePanel } from '@/components/courseKit/KitCompliancePanel'
import { ExportPanel } from '@/components/courseKit/ExportPanel'
import { KitVersionHistory } from '@/components/courseKit/KitVersionHistory'
import {
  useCourseKit,
  useKitSlides,
  useKitQuizlets,
  useKitAssignments,
} from '@/hooks/courseKit'
import { courseKitKeys } from '@/hooks/courseKit/useCourseKit'
import type { CourseKitStatus } from '@/types/courseKit'

type Tab = 'overview' | 'slides' | 'quizlets' | 'assignments' | 'teaching-plan' | 'compliance' | 'exports'

interface TabDef {
  key:    Tab
  label:  string
  badge?: (counts: ContentCounts) => number | null
}

interface ContentCounts {
  slides:      number
  quizlets:    number
  assignments: number
}

const TABS: TabDef[] = [
  { key: 'overview',      label: 'Overview' },
  { key: 'slides',        label: 'Slides',       badge: (c) => c.slides      || null },
  { key: 'quizlets',      label: 'Quizlets',     badge: (c) => c.quizlets    || null },
  { key: 'assignments',   label: 'Assignments',  badge: (c) => c.assignments || null },
  { key: 'teaching-plan', label: 'Teaching Plan' },
  { key: 'compliance',    label: 'Compliance' },
  { key: 'exports',       label: 'Exports' },
]

// DEAN sees and can export but cannot create/edit/delete
const WRITE_ROLES  = ['ADMIN', 'FACULTY']

export default function CourseKitDetailPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')

  const kitId = id ?? ''
  const role  = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const isDean    = role === 'DEAN'
  const canWrite  = WRITE_ROLES.includes(role)

  // DEAN: speaker_notes, answer_key, model_answer are fully hidden (not rendered at all)
  const showSpeakerNotes = !isDean
  const showAnswerKey    = !isDean
  const showModelAnswer  = !isDean

  const { data: kit, isLoading, isError }                      = useCourseKit(kitId)
  const { data: slides      = [], isLoading: slidesLoading }   = useKitSlides(kitId)
  const { data: quizlets    = [], isLoading: quizletsLoading } = useKitQuizlets(kitId)
  const { data: assignments = [], isLoading: assignsLoading }  = useKitAssignments(kitId)

  const isGenerating = kit?.status === 'AI_GENERATING'
  const isEditable   = kit?.status === 'DRAFT' && canWrite
  const isArchived   = kit?.status === 'ARCHIVED'
  const canExport    = kit?.status === 'PUBLISHED' || kit?.status === 'ARCHIVED'

  // Track generation start so we can detect failure
  const [wasGenerating, setWasGenerating] = useState(false)
  useEffect(() => {
    if (isGenerating) setWasGenerating(true)
  }, [isGenerating])
  const generationFailed =
    wasGenerating && !isGenerating &&
    !slidesLoading && !quizletsLoading && !assignsLoading &&
    kit?.status === 'DRAFT' &&
    slides.length === 0 && quizlets.length === 0 && assignments.length === 0

  // Auto-poll while AI_GENERATING
  useEffect(() => {
    if (!isGenerating) return
    const timer = setInterval(() => {
      qc.invalidateQueries({ queryKey: courseKitKeys.detail(kitId) })
    }, 5000)
    return () => clearInterval(timer)
  }, [isGenerating, kitId, qc])

  // A2: invalidate child caches once generation completes so slides/quizlets/assignments refresh
  useEffect(() => {
    if (wasGenerating && !isGenerating) {
      qc.invalidateQueries({ queryKey: courseKitKeys.slides(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.quizlets(kitId) })
      qc.invalidateQueries({ queryKey: courseKitKeys.assignments(kitId) })
    }
  }, [wasGenerating, isGenerating, kitId, qc])

  const counts: ContentCounts = {
    slides:      slides.length,
    quizlets:    quizlets.length,
    assignments: assignments.length,
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError || !kit) {
    return (
      <div className="p-8 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-3 text-red-400" />
        <p className="text-sm text-red-600 mb-3">Failed to load course kit.</p>
        <Button variant="outline" onClick={() => navigate(-1)}>Go back</Button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-5">

      {/* ── Header ── */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="shrink-0 mt-0.5">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">
              Course Kit — Unit {kit.unit_number} v{kit.version}
            </h1>
            <CourseKitStatusBadge status={kit.status} />
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-medium">
              {kit.complexity_level}
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-0.5 font-mono">{kit.syllabus_id}</p>
          {kit.tone && (
            <p className="text-xs text-gray-400 mt-0.5 italic">Tone: {kit.tone}</p>
          )}
        </div>
      </div>

      {/* ── Action bar ── */}
      <CourseKitActionBar kit={kit} />

      {/* ── Archived banner ── */}
      {isArchived && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
          <Archive className="h-4 w-4 shrink-0" />
          <span>
            This kit is <strong>archived</strong> and read-only.
            Use <strong>Fork</strong> to create a new version.
          </span>
        </div>
      )}

      {/* ── AI Generating notice ── */}
      {isGenerating && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" />
          <span>AI is generating the course kit. This page refreshes automatically every 5 s.</span>
        </div>
      )}

      {/* ── Generation failed ── */}
      {generationFailed && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            AI generation did not complete. The kit has been reset to Draft.
            Check provider configuration or quota, then use <strong>Generate with AI</strong> to retry.
          </span>
        </div>
      )}

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
      <div className="min-h-[24rem]" role="tabpanel">

        {tab === 'overview' && (
          <div className="space-y-5">
            {/* E1 — Pipeline stepper */}
            <KitPipelineStepper status={kit.status} />

            {/* Stats grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <StatCard label="Slides"      value={counts.slides}      onClick={() => setTab('slides')}      />
              <StatCard label="Quizlets"    value={counts.quizlets}    onClick={() => setTab('quizlets')}    />
              <StatCard label="Assignments" value={counts.assignments} onClick={() => setTab('assignments')} />
            </div>

            {/* Custom instructions */}
            {kit.custom_instructions && (
              <div className="rounded-lg border border-gray-200 px-4 py-3">
                <p className="text-xs font-semibold text-gray-500 mb-1">Custom Instructions</p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{kit.custom_instructions}</p>
              </div>
            )}

            {/* Metadata */}
            <div className="flex items-center gap-4 text-xs text-gray-400 flex-wrap">
              {kit.ai_model && (
                <span>AI model: <span className="font-mono">{kit.ai_model}</span></span>
              )}
              {kit.published_at && (
                <span>Published: {new Date(kit.published_at).toLocaleDateString()}</span>
              )}
              {kit.parent_version_id && (
                <span className="font-mono">Forked from: {kit.parent_version_id.slice(0, 8)}</span>
              )}
              <span>Created: {new Date(kit.created_at).toLocaleDateString()}</span>
            </div>

            {/* E2 — Version history */}
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-2">Version History</p>
              <KitVersionHistory kitId={kitId} currentKitId={kitId} />
            </div>

            {/* Get started hint */}
            {isEditable && counts.slides === 0 && counts.quizlets === 0 && counts.assignments === 0 && (
              <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-700 space-y-1">
                <p className="font-semibold">Get started</p>
                <p>
                  Use <strong>Generate with AI</strong> to populate slides, quizlets, and assignments automatically,
                  or add them manually via the Slides, Quizlets, and Assignments tabs.
                </p>
              </div>
            )}
          </div>
        )}

        {tab === 'slides' && (
          <SlidesSection
            kitId={kitId}
            slides={slides}
            isEditable={isEditable}
            showSpeakerNotes={showSpeakerNotes}
            isLoading={slidesLoading}
          />
        )}

        {tab === 'quizlets' && (
          <QuizletsSection
            kitId={kitId}
            quizlets={quizlets}
            isEditable={isEditable}
            showAnswerKey={showAnswerKey}
            isLoading={quizletsLoading}
          />
        )}

        {tab === 'assignments' && (
          <AssignmentsSection
            kitId={kitId}
            assignments={assignments}
            isEditable={isEditable}
            showModelAnswer={showModelAnswer}
            isLoading={assignsLoading}
          />
        )}

        {tab === 'teaching-plan' && (
          <TeachingPlanSection teachingPlan={kit.teaching_plan ?? []} kitStatus={kit.status} />
        )}

        {tab === 'compliance' && (
          <KitCompliancePanel kitId={kitId} />
        )}

        {tab === 'exports' && (
          <ExportPanel kit={kit} canExport={canExport} />
        )}
      </div>
    </div>
  )
}

// ── E1: Inline pipeline stepper ──────────────────────────────────────────────

const PIPELINE_STEPS: Array<{ status: CourseKitStatus; label: string }> = [
  { status: 'DRAFT',         label: 'Draft' },
  { status: 'AI_GENERATING', label: 'Generating' },
  { status: 'PUBLISHED',     label: 'Published' },
  { status: 'ARCHIVED',      label: 'Archived' },
]

const STATUS_ORDER: Record<CourseKitStatus, number> = {
  DRAFT: 0, AI_GENERATING: 1, PUBLISHED: 2, ARCHIVED: 3,
}

function KitPipelineStepper({ status }: { status: CourseKitStatus }) {
  const current = STATUS_ORDER[status]
  return (
    <div className="flex items-center gap-0">
      {PIPELINE_STEPS.map((step, idx) => {
        const done    = STATUS_ORDER[step.status] < current
        const active  = step.status === status
        return (
          <div key={step.status} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
              active ? 'bg-blue-100 text-blue-700'
              : done  ? 'bg-green-50 text-green-600'
              :         'text-gray-400'
            }`}>
              {done
                ? <CheckCircle2 className="h-3.5 w-3.5" />
                : active && step.status === 'AI_GENERATING'
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : active
                ? <Zap className="h-3.5 w-3.5" />
                : <Circle className="h-3.5 w-3.5" />
              }
              {step.label}
            </div>
            {idx < PIPELINE_STEPS.length - 1 && (
              <div className={`h-px w-4 ${
                STATUS_ORDER[PIPELINE_STEPS[idx + 1].status] <= current ? 'bg-green-300' : 'bg-gray-200'
              }`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

interface StatCardProps {
  label:    string
  value:    number
  onClick?: () => void
}

function StatCard({ label, value, onClick }: StatCardProps) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-center w-full ${
        onClick ? 'hover:bg-gray-100 hover:border-gray-300 cursor-pointer transition-colors' : ''
      }`}
    >
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </Tag>
  )
}
