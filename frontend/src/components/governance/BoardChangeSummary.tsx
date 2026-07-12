import { CheckCircle2, ListChecks } from 'lucide-react'
import { useChangeSummary } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'

/**
 * What the Board changed while it held the Dean's curriculum.
 *
 * The Dean submits a plan and gets back something the Board may have revised
 * substantially — subjects added, semesters rearranged, credits adjusted,
 * syllabi written — and they cannot edit any of it. They can only publish it.
 *
 * So they are owed an answer to one question before they publish: what am I
 * publishing? This panel is that answer. Without it the handover is a black box,
 * and "the Board is the academic authority" starts to look like "the Dean's work
 * disappeared".
 *
 * Built from the audit log, so it costs no extra bookkeeping.
 */
export function BoardChangeSummary({ programId }: { programId: string }) {
  const { bodyLabel } = useGovernance()
  const { data, isLoading } = useChangeSummary(programId)

  if (isLoading || !data) return null

  return (
    <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
      <div className="flex gap-2">
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
        <div className="min-w-0">
          <p className="text-sm font-bold text-black">
            The {bodyLabel} has reviewed and finalized your curriculum.
          </p>

          {data.total_changes === 0 ? (
            <p className="mt-0.5 text-sm text-emerald-900">
              It was approved with no changes. Publish it when you are ready.
            </p>
          ) : (
            <>
              <p className="mt-0.5 text-sm text-emerald-900">
                They made {data.total_changes} change{data.total_changes === 1 ? '' : 's'} before
                approving. Review them, then publish.
              </p>
              <ul className="mt-2 space-y-1">
                {data.lines.map((line) => (
                  <li
                    key={line.label}
                    className="flex items-center gap-1.5 text-sm text-emerald-900"
                  >
                    <ListChecks className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                    <span>{line.label}</span>
                    {line.count > 1 && (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-semibold text-emerald-800">
                        ×{line.count}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="mt-2 text-xs text-emerald-800">
            This version is locked. Publishing releases it to Faculty and Students; it does not
            reopen editing. Any further academic change means a new curriculum version.
          </p>
        </div>
      </div>
    </div>
  )
}
