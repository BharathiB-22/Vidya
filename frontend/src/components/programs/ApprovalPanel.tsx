import { CheckCircle2, Circle } from 'lucide-react'
import { useProgramVersions } from '@/hooks/programs'
import { ProgramStatusBadge } from './ProgramStatusBadge'
import type { Program, ProgramStatus } from '@/types/program'

interface Step {
  label: string
  order: number
}

const STEPS: Step[] = [
  { label: 'Draft',            order: 0 },
  { label: 'AI Generating',    order: 1 },
  { label: 'Pending Approval', order: 2 },
  { label: 'Approved',         order: 3 },
]

const STATUS_ORDER: Record<ProgramStatus, number> = {
  DRAFT:             0,
  AI_GENERATING:     1,
  GENERATION_FAILED: 1,
  PENDING_APPROVAL:  2,
  APPROVED:          3,
}

interface Props {
  program: Program
}

export function ApprovalPanel({ program }: Props) {
  const { data: versions = [], isLoading } = useProgramVersions(program.id)
  const current = STATUS_ORDER[program.status]

  const sorted = [...versions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )

  return (
    <div className="space-y-5">
      {/* Status pipeline */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-5">Approval Pipeline</h3>
        <div className="flex items-start">
          {STEPS.map((step, idx) => {
            const isPast    = step.order < current
            const isCurrent = step.order === current
            return (
              <div key={step.label} className="flex items-start flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1.5 min-w-0">
                  {isPast ? (
                    <CheckCircle2 className="h-6 w-6 text-green-500 shrink-0" />
                  ) : isCurrent ? (
                    <div className="h-6 w-6 rounded-full border-2 border-blue-600 bg-blue-600 flex items-center justify-center shrink-0">
                      <div className="h-2 w-2 rounded-full bg-white" />
                    </div>
                  ) : (
                    <Circle className="h-6 w-6 text-gray-300 shrink-0" />
                  )}
                  <span
                    className={`text-xs text-center px-1 ${
                      isCurrent
                        ? 'text-blue-700 font-semibold'
                        : isPast
                        ? 'text-green-600'
                        : 'text-gray-400'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mt-3 mx-1 ${
                      isPast ? 'bg-green-400' : 'bg-gray-200'
                    }`}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Approval details */}
      {program.status === 'APPROVED' && program.approved_at && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-5">
          <h3 className="text-sm font-semibold text-green-800 mb-3">Approval Details</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex gap-3">
              <dt className="text-gray-500 w-28 shrink-0">Approved at</dt>
              <dd className="text-gray-800">
                {new Date(program.approved_at).toLocaleString()}
              </dd>
            </div>
            {program.approved_by_user_id && (
              <div className="flex gap-3">
                <dt className="text-gray-500 w-28 shrink-0">Approver ID</dt>
                <dd className="font-mono text-xs text-gray-700 break-all">
                  {program.approved_by_user_id}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* Version history */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Version History</h3>
        {isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : sorted.length === 0 ? (
          <p className="text-sm text-gray-400">No version history available.</p>
        ) : (
          <div className="space-y-2">
            {sorted.map(v => (
              <div
                key={v.id}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                  v.id === program.id
                    ? 'border border-blue-200 bg-blue-50'
                    : 'border border-gray-100 bg-gray-50'
                }`}
              >
                <span
                  className={`font-semibold shrink-0 ${
                    v.id === program.id ? 'text-blue-700' : 'text-gray-700'
                  }`}
                >
                  v{v.version}
                </span>
                <ProgramStatusBadge status={v.status} />
                {v.parent_version_id && (
                  <span className="text-xs text-gray-400">↳ fork</span>
                )}
                <span className="text-gray-400 ml-auto text-xs">
                  {new Date(v.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
