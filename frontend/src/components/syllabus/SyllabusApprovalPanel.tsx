import { CheckCircle, Lock, GitFork, FileText } from 'lucide-react'
import { useSyllabusVersions } from '@/hooks/syllabuses'
import { SyllabusStatusBadge } from './SyllabusStatusBadge'
import type { Syllabus } from '@/types/syllabus'

const STEPS = [
  { key: 'DRAFT',            label: 'Draft',            icon: FileText },
  { key: 'FACULTY_APPROVED', label: 'Faculty Approved', icon: CheckCircle },
  { key: 'ADMIN_LOCKED',     label: 'Admin Locked',     icon: Lock },
] as const

const STATUS_STEP: Record<string, number> = {
  DRAFT:            0,
  AI_GENERATING:    0,
  FACULTY_APPROVED: 1,
  ADMIN_LOCKED:     2,
}

interface Props {
  syllabus: Syllabus
}

export function SyllabusApprovalPanel({ syllabus }: Props) {
  const { data: versions, isLoading } = useSyllabusVersions(syllabus.id)
  const currentStep = STATUS_STEP[syllabus.status] ?? 0

  return (
    <div className="space-y-6">
      {/* Pipeline stepper */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Approval Pipeline</h3>
        <div className="flex items-center gap-0">
          {STEPS.map((step, idx) => {
            const Icon = step.icon
            const done    = idx < currentStep
            const active  = idx === currentStep
            return (
              <div key={step.key} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1">
                  <div className={`h-9 w-9 rounded-full flex items-center justify-center border-2 transition-colors ${
                    done   ? 'border-green-500 bg-green-50 text-green-600' :
                    active ? 'border-blue-500 bg-blue-50 text-blue-600' :
                             'border-gray-200 bg-white text-gray-300'
                  }`}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <span className={`text-xs font-medium whitespace-nowrap ${
                    done   ? 'text-green-600' :
                    active ? 'text-blue-600' :
                             'text-gray-400'
                  }`}>
                    {step.label}
                  </span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div className={`flex-1 h-0.5 mx-1 mb-5 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Current status */}
      <div className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 bg-gray-50">
        <div className="flex-1">
          <p className="text-xs text-gray-500 mb-1">Current Status</p>
          <SyllabusStatusBadge status={syllabus.status} />
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500 mb-1">Version</p>
          <p className="text-sm font-semibold text-gray-700">v{syllabus.version}</p>
        </div>
        {syllabus.approved_at && (
          <div className="text-right">
            <p className="text-xs text-gray-500 mb-1">Approved</p>
            <p className="text-xs text-gray-700">{new Date(syllabus.approved_at).toLocaleDateString()}</p>
          </div>
        )}
        {syllabus.locked_at && (
          <div className="text-right">
            <p className="text-xs text-gray-500 mb-1">Locked</p>
            <p className="text-xs text-gray-700">{new Date(syllabus.locked_at).toLocaleDateString()}</p>
          </div>
        )}
      </div>

      {/* Version history */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Version History</h3>
        {isLoading && (
          <p className="text-sm text-gray-400 text-center py-4">Loading versions…</p>
        )}
        {versions && versions.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">No version history.</p>
        )}
        {versions && versions.length > 0 && (
          <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
            {versions.map((v) => (
              <div key={v.id} className="flex items-center gap-3 px-4 py-3">
                <GitFork className="h-4 w-4 text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-700">v{v.version}</span>
                    <SyllabusStatusBadge status={v.status} />
                    {v.id === syllabus.id && (
                      <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                        current
                      </span>
                    )}
                  </div>
                  {v.change_note && (
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{v.change_note}</p>
                  )}
                </div>
                <p className="text-xs text-gray-400 shrink-0">
                  {new Date(v.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
