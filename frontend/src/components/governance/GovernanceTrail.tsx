import {
  CheckCircle2, Eye, FileText, Lock, Pencil, Rocket, Send, ShieldCheck,
} from 'lucide-react'
import { useGovernanceTrail } from '@/hooks/governance'
import { useGovernance } from '@/lib/governance'
import type { TrailCategory, TrailEntry } from '@/types/governance'

/**
 * Who reviewed, who modified, who approved, and when.
 *
 * This panel carries more weight than it looks like it should. There is no
 * separation of duties inside the Board: one member may receive a curriculum,
 * rewrite it, generate and edit the official syllabus, approve it and lock it —
 * alone, with no second signature. That is the intended model, because the Board
 * is one academic authority rather than a ladder of approval levels.
 *
 * The consequence is that this record is the ONLY thing standing between that
 * model and "nobody knows who did this". Accountability was traded from a
 * restriction to a record, so the record has to be visible, complete, and
 * impossible to quietly edit — it is read straight from the append-only audit
 * log.
 */
export function GovernanceTrail({ programId }: { programId: string }) {
  const { bodyLabel } = useGovernance()
  const { data: entries = [], isLoading } = useGovernanceTrail(programId)

  if (isLoading) return null

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <header className="mb-1 flex items-center gap-1.5">
        <ShieldCheck className="h-4 w-4 text-gray-500" />
        <h3 className="text-base font-bold text-black">Governance Trail</h3>
      </header>
      <p className="mb-4 text-xs text-gray-500">
        Every action taken on this curriculum, with who took it and when. Any member of the{' '}
        {bodyLabel} may review, modify, write the syllabus and approve — they are equal peers — so
        this record, not a restriction, is what makes them accountable. It is read from the
        append-only audit log and cannot be edited.
      </p>

      {entries.length === 0 ? (
        <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-6 text-center text-sm text-gray-500">
          Nothing has happened to this curriculum yet.
        </p>
      ) : (
        <ol className="space-y-0">
          {entries.map((entry, i) => (
            <TrailRow key={`${entry.event_type}-${entry.at}-${i}`} entry={entry} last={i === entries.length - 1} />
          ))}
        </ol>
      )}
    </section>
  )
}

const CATEGORY_STYLE: Record<TrailCategory, { icon: typeof Eye; className: string }> = {
  SUBMIT:   { icon: Send,        className: 'bg-blue-100 text-blue-700' },
  REVIEW:   { icon: Eye,         className: 'bg-gray-100 text-gray-600' },
  MODIFY:   { icon: Pencil,      className: 'bg-amber-100 text-amber-700' },
  SYLLABUS: { icon: FileText,    className: 'bg-violet-100 text-violet-700' },
  APPROVE:  { icon: CheckCircle2, className: 'bg-emerald-100 text-emerald-700' },
  PUBLISH:  { icon: Rocket,      className: 'bg-emerald-100 text-emerald-700' },
}

function TrailRow({ entry, last }: { entry: TrailEntry; last: boolean }) {
  const style = CATEGORY_STYLE[entry.category] ?? CATEGORY_STYLE.REVIEW
  const Icon = entry.event_type === 'CURRICULUM_LOCKED' ? Lock : style.icon

  return (
    <li className="flex gap-3">
      {/* Spine */}
      <div className="flex flex-col items-center">
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${style.className}`}>
          <Icon className="h-3.5 w-3.5" />
        </span>
        {!last && <span className="w-px flex-1 bg-gray-200" />}
      </div>

      <div className={`min-w-0 flex-1 ${last ? 'pb-0' : 'pb-4'}`}>
        <p className="text-sm font-semibold text-black">
          {entry.action}
          {entry.detail && (
            <span className="ml-1.5 font-normal text-gray-500">— {entry.detail}</span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-gray-500">
          <span className="font-medium text-gray-700">{entry.actor_name ?? 'Unknown'}</span>
          {entry.actor_role && (
            <span className="ml-1 rounded bg-gray-100 px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-600">
              {entry.actor_role}
            </span>
          )}
          <span className="mx-1.5 text-gray-300">·</span>
          {new Date(entry.at).toLocaleString()}
        </p>
      </div>
    </li>
  )
}
