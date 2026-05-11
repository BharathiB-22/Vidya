import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
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

type Tab = 'overview' | 'outcomes' | 'matrix' | 'units' | 'references' | 'compliance' | 'approval'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'overview',    label: 'Overview' },
  { key: 'outcomes',    label: 'Course Outcomes' },
  { key: 'matrix',      label: 'CO-PO Matrix' },
  { key: 'units',       label: 'Units' },
  { key: 'references',  label: 'References' },
  { key: 'compliance',  label: 'Compliance' },
  { key: 'approval',    label: 'Approval' },
]

const EDITABLE_STATUSES = new Set(['DRAFT'])

export default function SyllabusDetailPage() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const [tab, setTab] = useState<Tab>('overview')

  const syllabusId = id ?? ''
  const { data: syllabus, isLoading, isError } = useSyllabus(syllabusId)
  const { data: outcomes    = [] } = useSyllabusOutcomes(syllabusId)
  const { data: units       = [] } = useSyllabusUnits(syllabusId)
  const { data: references  = [] } = useSyllabusReferences(syllabusId)

  const isEditable = syllabus ? EDITABLE_STATUSES.has(syllabus.status) : false

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError || !syllabus) {
    return (
      <div className="p-8 text-center text-red-500">
        <p>Failed to load syllabus.</p>
        <Button variant="outline" className="mt-3" onClick={() => navigate(-1)}>Go back</Button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="shrink-0 mt-0.5">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">
              Syllabus — Version {syllabus.version}
            </h1>
            <SyllabusStatusBadge status={syllabus.status} />
          </div>
          <p className="text-sm text-gray-500 mt-0.5 font-mono">{syllabus.course_id}</p>
          {syllabus.change_note && (
            <p className="text-sm text-gray-400 mt-1 italic">{syllabus.change_note}</p>
          )}
        </div>
      </div>

      {/* Action bar */}
      <SyllabusActionBar syllabus={syllabus} />

      {/* AI Generating polling notice */}
      {syllabus.status === 'AI_GENERATING' && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" />
          AI generation in progress. Content will appear once complete — this page will not auto-refresh.
        </div>
      )}

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="min-h-[24rem]">
        {tab === 'overview' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Course Outcomes" value={outcomes.length} />
              <StatCard label="Units" value={units.length} />
              <StatCard label="References" value={references.length} />
              <StatCard label="Total Hours" value={units.reduce((s, u) => s + u.total_hours, 0)} />
            </div>
            {syllabus.custom_instructions && (
              <div className="rounded-lg border border-gray-200 px-4 py-3">
                <p className="text-xs font-semibold text-gray-500 mb-1">Custom Instructions</p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{syllabus.custom_instructions}</p>
              </div>
            )}
            {syllabus.ai_model && (
              <p className="text-xs text-gray-400">AI Model: {syllabus.ai_model}</p>
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
          <SyllabusApprovalPanel syllabus={syllabus} />
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-center">
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}
