import { CheckCircle2, Circle, Lock, Send } from 'lucide-react'
import { useProgramVersions } from '@/hooks/programs'
import { useApprovalHistory } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'
import { ProgramStatusBadge } from './ProgramStatusBadge'
import { GovernanceTrail } from '@/components/governance/GovernanceTrail'
import type { Program, ProgramStatus } from '@/types/program'
import type { AcadProgram } from '@/lib/api/academics'

// The Phase A pipeline. Note who acts at each step — that is the whole point of
// the redesign: the Dean plans and publishes, the Board owns and approves, and
// nobody does both. The arrow only goes forwards: a submitted curriculum never
// comes back to the Dean.
const STATUS_ORDER: Record<ProgramStatus, number> = {
  DRAFT:             0,
  AI_GENERATING:     0,
  GENERATION_FAILED: 0,
  PENDING_APPROVAL:  1,
  APPROVED:          2,
  PUBLISHED:         3,
}

interface Props {
  program: Program
  linkedAcadProgram?: AcadProgram
}

export function ApprovalPanel({ program, linkedAcadProgram }: Props) {
  const { bodyLabel } = useGovernance()
  const { data: versions = [], isLoading } = useProgramVersions(program.id)
  const { data: history = [] } = useApprovalHistory(program.id)

  const current = STATUS_ORDER[program.status]

  const steps = [
    { label: 'Prepared by Dean',           actor: 'Dean' },
    { label: `Under ${bodyLabel} Review`,  actor: bodyLabel },
    { label: 'Approved & Locked',          actor: bodyLabel },
    { label: 'Published',                  actor: 'Dean' },
  ]

  const sortedVersions = [...versions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )

  return (
    <div className="space-y-5">
      {/* Pipeline */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-bold text-black mb-5">Approval Pipeline</h3>
        <div className="flex items-start">
          {steps.map((step, idx) => {
            const isPast    = idx < current
            const isCurrent = idx === current
            return (
              <div key={step.label} className="flex items-start flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1.5 min-w-0">
                  {isPast ? (
                    <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
                  ) : isCurrent ? (
                    <div className="h-6 w-6 rounded-full border-2 border-black bg-black flex items-center justify-center shrink-0">
                      <div className="h-2 w-2 rounded-full bg-white" />
                    </div>
                  ) : (
                    <Circle className="h-6 w-6 text-gray-500 shrink-0" />
                  )}
                  <span
                    className={`text-xs text-center px-1 ${
                      isCurrent
                        ? 'font-bold text-black'
                        : isPast
                        ? 'text-emerald-700'
                        : 'text-gray-600'
                    }`}
                  >
                    {step.label}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-gray-600">
                    {step.actor}
                  </span>
                </div>
                {idx < steps.length - 1 && (
                  <div className={`flex-1 h-0.5 mt-3 mx-1 ${isPast ? 'bg-emerald-500' : 'bg-gray-200'}`} />
                )}
              </div>
            )
          })}
        </div>

        {program.status === 'PENDING_APPROVAL' && (
          <p className="mt-4 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
            The {bodyLabel} owns this curriculum now. They will review it, enhance it where the
            academics require, write the official syllabus for every subject, and approve it. It
            does not come back to the Dean for corrections.
          </p>
        )}
      </div>

      {/* Lock details */}
      {(program.status === 'APPROVED' || program.status === 'PUBLISHED') && program.locked_at && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
          <h3 className="flex items-center gap-1.5 text-base font-bold text-black mb-3">
            <Lock className="h-4 w-4 text-emerald-700" />
            Locked Curriculum
          </h3>
          <p className="text-sm text-emerald-900">
            Approved and locked by the {bodyLabel} on{' '}
            <span className="font-semibold">{new Date(program.locked_at).toLocaleString()}</span>.
            It cannot be edited by anyone. To change it, the Dean creates a new version.
          </p>
          {program.review_comment && (
            <p className="mt-2 text-sm text-emerald-900">
              <span className="font-semibold">Note: </span>
              {program.review_comment}
            </p>
          )}
        </div>
      )}

      {/* Academic Structure context */}
      {linkedAcadProgram && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">
            Linked Academic Program
          </h3>
          <p className="text-sm font-bold text-black">{linkedAcadProgram.name}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {linkedAcadProgram.code} · {linkedAcadProgram.degree_type} ·{' '}
            {linkedAcadProgram.duration_years} yr
          </p>
        </div>
      )}

      {/* Who reviewed, who modified, who approved, and when.
          The Board approves without a second signature, so the Dean — who cannot
          edit this curriculum and can only publish it — is owed a complete account
          of what was done to it, and by whom. */}
      <GovernanceTrail programId={program.id} />

      {/* Review cycles — every submit → decide handover, append-only */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-bold text-black mb-3">Review History</h3>
        {history.length === 0 ? (
          <p className="text-sm text-gray-500">
            This curriculum has not been submitted to the {bodyLabel} yet.
          </p>
        ) : (
          <ol className="space-y-3">
            {history.map((cycle) => (
              <li key={cycle.id} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="rounded bg-black px-1.5 py-0.5 text-xs font-bold text-white">
                    Cycle {cycle.cycle}
                  </span>
                  {cycle.status === 'PENDING' && (
                    <span className="text-xs font-semibold text-blue-700">Awaiting decision</span>
                  )}
                  {cycle.status === 'APPROVED' && (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Approved
                    </span>
                  )}
                </div>

                <p className="mt-1.5 flex items-center gap-1 text-xs text-gray-600">
                  <Send className="h-3 w-3" />
                  Submitted by{' '}
                  <span className="font-semibold text-black">
                    {cycle.submitted_by_name ?? 'the Dean'}
                  </span>{' '}
                  on {new Date(cycle.submitted_at).toLocaleDateString()}
                </p>
                {cycle.submission_note && (
                  <p className="mt-1 text-sm text-gray-700">“{cycle.submission_note}”</p>
                )}

                {cycle.decided_at && (
                  <p className="mt-1.5 text-xs text-gray-600">
                    Decided by{' '}
                    <span className="font-semibold text-black">
                      {cycle.decided_by_name ?? `the ${bodyLabel}`}
                    </span>{' '}
                    on {new Date(cycle.decided_at).toLocaleDateString()}
                  </p>
                )}
                {cycle.decision_comment && (
                  <p className="mt-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-800">
                    {cycle.decision_comment}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Version history */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-bold text-black mb-3">Version History</h3>
        {isLoading ? (
          <p className="text-sm text-gray-600">Loading…</p>
        ) : sortedVersions.length === 0 ? (
          <p className="text-sm text-gray-600">No version history available.</p>
        ) : (
          <div className="space-y-2">
            {sortedVersions.map((v) => (
              <div
                key={v.id}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                  v.id === program.id
                    ? 'border border-black bg-gray-50'
                    : 'border border-gray-100 bg-gray-50'
                }`}
              >
                <span className="font-bold shrink-0 text-black">v{v.version}</span>
                <ProgramStatusBadge status={v.status} />
                {v.parent_version_id && <span className="text-xs text-gray-500">↳ new version</span>}
                <span className="text-gray-500 ml-auto text-xs">
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
