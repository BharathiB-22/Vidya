import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, Lock, AlertTriangle, Package, BookOpen } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { SyllabusActionBar } from '@/components/syllabus/SyllabusActionBar'
import { COSection } from '@/components/syllabus/COSection'
import { COPOMatrix } from '@/components/syllabus/COPOMatrix'
import { UnitsSection } from '@/components/syllabus/UnitsSection'
import { ReferencesSection } from '@/components/syllabus/ReferencesSection'
import { CompliancePanel } from '@/components/syllabus/CompliancePanel'
import { SyllabusApprovalPanel } from '@/components/syllabus/SyllabusApprovalPanel'
import {
  useSyllabus,
  useSyllabusOutcomes,
  useSyllabusUnits,
  useSyllabusReferences,
} from '@/hooks/syllabuses'
import { syllabusKeys } from '@/hooks/syllabuses/useSyllabuses'
import { AIGeneratingBanner } from '@/components/shared/AIGeneratingBanner'
import { useWorkspace } from '@/lib/workspace'

type Tab = 'overview' | 'outcomes' | 'matrix' | 'units' | 'references' | 'compliance' | 'approval'

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

const TABS: TabDef[] = [
  { key: 'overview',   label: 'Overview' },
  { key: 'outcomes',   label: 'Course Outcomes',  badge: (c) => c.outcomes || null },
  { key: 'matrix',     label: 'CO-PO Matrix' },
  { key: 'units',      label: 'Units',             badge: (c) => c.units || null },
  { key: 'references', label: 'References',        badge: (c) => c.references || null },
  { key: 'compliance', label: 'Compliance' },
  { key: 'approval',   label: 'Approval' },
]

const EDITABLE_STATUSES = new Set(['DRAFT', 'REJECTED'])

export default function SyllabusDetailPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const { activeWorkspace: role } = useWorkspace()
  const isFaculty = role === 'FACULTY'

  const syllabusId = id ?? ''
  const { data: syllabus, isLoading, isError } = useSyllabus(syllabusId)
  const { data: outcomes   = [] } = useSyllabusOutcomes(syllabusId)
  const { data: units      = [] } = useSyllabusUnits(syllabusId)
  const { data: references = [] } = useSyllabusReferences(syllabusId)

  const isEditable   = syllabus ? EDITABLE_STATUSES.has(syllabus.status) : false
  const isGenerating = syllabus?.status === 'AI_GENERATING'
  const isLocked     = syllabus?.status === 'DEAN_LOCKED'
  const isRejected   = syllabus?.status === 'REJECTED'

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

      {/* ── Status banners ── */}
      {isLocked && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
          <Lock className="h-4 w-4 shrink-0" />
          <span>
            This syllabus is <strong>Published</strong> and locked for the semester.
            {isFaculty
              ? ' It is final and cannot be edited.'
              : <> Use <strong>Unlock</strong> or <strong>Fork Version</strong> to make changes.</>}
          </span>
        </div>
      )}
      {syllabus.status === 'PENDING_REVIEW' && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            This syllabus is <strong>pending Dean review</strong> and cannot be edited.
            The Dean may approve, reject, or request revisions.
          </span>
        </div>
      )}
      {syllabus.status === 'DEAN_APPROVED' && isFaculty && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            This syllabus has been reviewed and approved by the Dean and is <strong>pending publication</strong>.
            It becomes <strong>Published</strong> — the only final state — once the Dean publishes it.
          </span>
        </div>
      )}
      {syllabus.status === 'DEAN_APPROVED' && !isFaculty && (
        <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            This syllabus has been <strong>Dean-approved</strong> and is immutable.
            Use <strong>Lock</strong> to publish it for the semester, or <strong>Fork Version</strong> to start a new revision.
          </span>
        </div>
      )}

      {/* ── REJECTED banner with Dean feedback ── */}
      {isRejected && syllabus.dean_comment && (
        <div className="flex items-start gap-3 rounded-lg bg-red-50 border border-red-200 px-4 py-4 text-red-900 text-sm">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5 text-red-500" />
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-red-800">
              {syllabus.dean_comment.startsWith('[REVISION REQUESTED]')
                ? 'Revision Requested by Dean'
                : 'Syllabus Rejected by Dean'}
            </p>
            <p className="mt-1 text-red-700 whitespace-pre-wrap">
              {syllabus.dean_comment.replace(/^\[REVISION REQUESTED\]\s*/, '')}
            </p>
            <p className="mt-2 text-xs text-red-600">
              Address the feedback above, then use <strong>Resubmit for Review</strong> to send it back to the Dean.
            </p>
          </div>
        </div>
      )}
      {isRejected && !syllabus.dean_comment && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-800 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-500" />
          <span>
            This syllabus was <strong>rejected</strong> by the Dean. Edit and resubmit for review.
          </span>
        </div>
      )}

      <AIGeneratingBanner isGenerating={isGenerating} failed={generationFailed} entity="syllabus" />

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

        {tab === 'overview' && (
          <div className="space-y-5">
            {/* Stats grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Course Outcomes"  value={counts.outcomes}   onClick={() => setTab('outcomes')}   />
              <StatCard label="Units"            value={counts.units}      onClick={() => setTab('units')}      />
              <StatCard label="References"       value={counts.references} onClick={() => setTab('references')} />
              <StatCard label="Total Hours"      value={units.reduce((s, u) => s + u.total_hours, 0)} />
            </div>

            {/* Custom instructions */}
            {syllabus.custom_instructions && (
              <div className="rounded-lg border border-gray-200 px-4 py-3">
                <p className="text-xs font-semibold text-gray-500 mb-1">Custom Instructions</p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{syllabus.custom_instructions}</p>
              </div>
            )}

            {/* Metadata row */}
            <div className="flex items-center gap-4 text-xs text-gray-400 flex-wrap">
              {syllabus.approved_at && (
                <span>Dean approved: {new Date(syllabus.approved_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
              )}
              {syllabus.locked_at && (
                <span>Locked for semester: {new Date(syllabus.locked_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
              )}
            </div>

            {/* Course Kits link (G1) */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/course-kits?syllabus_id=${syllabusId}`)}
              className="w-fit"
            >
              <Package className="h-4 w-4 mr-1.5" />
              View Course Kits
            </Button>

            {/* Quick-action hints when empty and editable */}
            {isEditable && counts.outcomes === 0 && counts.units === 0 && (
              <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-700 space-y-1">
                <p className="font-semibold">Get started</p>
                <p>
                  Use <strong>Generate with AI</strong> to populate COs, units, and reference queries automatically,
                  or add them manually via the Course Outcomes and Units tabs.
                </p>
              </div>
            )}
          </div>
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

        {tab === 'units' && (
          <UnitsSection
            syllabusId={syllabusId}
            units={units}
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
