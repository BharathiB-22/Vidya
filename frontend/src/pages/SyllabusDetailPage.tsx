import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, Lock, AlertTriangle } from 'lucide-react'
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

const EDITABLE_STATUSES = new Set(['DRAFT'])

export default function SyllabusDetailPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')

  const syllabusId = id ?? ''
  const { data: syllabus, isLoading, isError } = useSyllabus(syllabusId)
  const { data: outcomes   = [] } = useSyllabusOutcomes(syllabusId)
  const { data: units      = [] } = useSyllabusUnits(syllabusId)
  const { data: references = [] } = useSyllabusReferences(syllabusId)

  const isEditable   = syllabus ? EDITABLE_STATUSES.has(syllabus.status) : false
  const isGenerating = syllabus?.status === 'AI_GENERATING'
  const isLocked     = syllabus?.status === 'ADMIN_LOCKED'

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
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="shrink-0 mt-0.5">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">
              Syllabus — v{syllabus.version}
            </h1>
            <SyllabusStatusBadge status={syllabus.status} />
          </div>
          <p className="text-sm text-gray-400 mt-0.5 font-mono">{syllabus.course_id}</p>
          {syllabus.change_note && (
            <p className="text-sm text-gray-400 mt-1 italic">{syllabus.change_note}</p>
          )}
        </div>
      </div>

      {/* ── Action bar ── */}
      <SyllabusActionBar syllabus={syllabus} />

      {/* ── Immutability banner ── */}
      {isLocked && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
          <Lock className="h-4 w-4 shrink-0" />
          <span>
            This syllabus is <strong>locked for the semester</strong> and cannot be edited.
            Use <strong>Unlock</strong> or <strong>Fork Version</strong> to make changes.
          </span>
        </div>
      )}
      {!isEditable && !isLocked && syllabus.status === 'FACULTY_APPROVED' && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            This syllabus has been <strong>faculty-approved</strong> and is immutable.
            Use <strong>Reject</strong> to return it to draft, or <strong>Fork</strong> for a new version.
          </span>
        </div>
      )}

      {/* ── AI Generating notice ── */}
      {isGenerating && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" />
          <span>
            AI is generating the syllabus. This page refreshes automatically every 5 s.
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
              {syllabus.ai_model && <span>AI model: <span className="font-mono">{syllabus.ai_model}</span></span>}
              {syllabus.approved_at && (
                <span>Approved: {new Date(syllabus.approved_at).toLocaleDateString()}</span>
              )}
              {syllabus.locked_at && (
                <span>Locked: {new Date(syllabus.locked_at).toLocaleDateString()}</span>
              )}
              <span>Created: {new Date(syllabus.created_at).toLocaleDateString()}</span>
            </div>

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
