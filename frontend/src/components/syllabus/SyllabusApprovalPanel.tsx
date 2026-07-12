import { useNavigate } from 'react-router-dom'
import { CheckCircle, Lock, FileText, GitFork, Bot, ExternalLink, UserCheck } from 'lucide-react'
import { useSyllabusVersions } from '@/hooks/syllabuses'
import { SyllabusStatusBadge } from './SyllabusStatusBadge'
import type { Syllabus } from '@/types/syllabus'

/**
 * The life of an official syllabus, in three steps.
 *
 * There is no "pending review" step, because the body that writes this document
 * is the body that approves it — there is nobody to submit it to. And the final
 * freeze is not a syllabus-level act: the syllabus locks when the CURRICULUM is
 * approved, together with the structure it describes.
 */
const STEPS = [
  { key: 'DRAFT',    label: 'Draft',    desc: 'Written by the board',            icon: FileText  },
  { key: 'APPROVED', label: 'Approved', desc: 'Signed off by a board member',    icon: UserCheck },
  { key: 'LOCKED',   label: 'Official', desc: 'Locked with the curriculum',      icon: Lock      },
] as const

const STATUS_STEP: Record<string, number> = {
  DRAFT:         0,
  AI_GENERATING: 0,
  APPROVED:      1,
  LOCKED:        2,
}

interface Props {
  syllabus:   Syllabus
  onTabChange?: (tab: string) => void
}

export function SyllabusApprovalPanel({ syllabus, onTabChange }: Props) {
  const navigate   = useNavigate()
  const { data: versions, isLoading } = useSyllabusVersions(syllabus.id)
  const currentStep = STATUS_STEP[syllabus.status] ?? 0

  return (
    <div className="space-y-8">

      {/* ── 3-step pipeline stepper ── */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-5">Approval Pipeline</h3>
        <div className="flex items-start">
          {STEPS.map((step, idx) => {
            const Icon = step.icon
            const done   = idx < currentStep
            const active = idx === currentStep
            return (
              <div key={step.key} className="flex items-start flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1 min-w-0">
                  <div className={`h-10 w-10 rounded-full flex items-center justify-center border-2 transition-colors shrink-0 ${
                    done   ? 'border-green-500 bg-green-50 text-green-600' :
                    active ? 'border-blue-500 bg-blue-50 text-blue-600' :
                             'border-gray-200 bg-white text-gray-300'
                  }`}>
                    {done ? <CheckCircle className="h-5 w-5" /> : <Icon className="h-4 w-4" />}
                  </div>
                  <span className={`text-xs font-semibold whitespace-nowrap ${
                    done   ? 'text-green-600' :
                    active ? 'text-blue-600' :
                             'text-gray-400'
                  }`}>
                    {step.label}
                  </span>
                  <span className="text-[10px] text-gray-400 text-center leading-tight px-1 hidden sm:block">
                    {step.desc}
                  </span>
                  {/* Timestamp under completed steps */}
                  {idx === 1 && syllabus.approved_at && (
                    <span className="text-[10px] text-green-600">
                      {new Date(syllabus.approved_at).toLocaleDateString()}
                    </span>
                  )}
                  {idx === 2 && syllabus.locked_at && (
                    <span className="text-[10px] text-green-600">
                      {new Date(syllabus.locked_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                {idx < STEPS.length - 1 && (
                  <div className={`flex-1 h-0.5 mx-2 mt-5 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
                )}
              </div>
            )
          })}
        </div>

        {/* AI Generating sub-state note */}
        {syllabus.status === 'AI_GENERATING' && (
          <div className="mt-4 flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <Bot className="h-4 w-4 shrink-0" />
            Writing the official syllabus. It returns to Draft for the board to review.
          </div>
        )}

        {/* APPROVED sub-state note */}
        {syllabus.status === 'APPROVED' && (
          <div className="mt-4 flex items-start gap-2 text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
            <CheckCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>
              Signed off. It becomes official — and permanently locked — when the curriculum is
              approved. Editing it before then returns it to draft for re-approval.
            </span>
          </div>
        )}

        {/* Compliance hint in DRAFT */}
        {syllabus.status === 'DRAFT' && onTabChange && (
          <div className="mt-4 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
            Before approving, run a{' '}
            <button
              type="button"
              onClick={() => onTabChange('compliance')}
              className="text-blue-600 underline underline-offset-2 hover:text-blue-700"
            >
              compliance check
            </button>
            {' '}to verify minimum COs, units, and CO-PO coverage.
          </div>
        )}
      </section>

      {/* ── Metadata card ── */}
      <section className="rounded-lg border border-gray-200 divide-y divide-gray-100">
        <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100">
          <MetaCell label="Status">
            <SyllabusStatusBadge status={syllabus.status} />
          </MetaCell>
          <MetaCell label="Version">
            <span className="text-sm font-semibold text-gray-800">Version {syllabus.version}</span>
          </MetaCell>
          <MetaCell label="Course Code">
            <span className="text-sm text-gray-700">{syllabus.course_code ?? '—'}</span>
          </MetaCell>
          <MetaCell label="Created">
            <span className="text-sm text-gray-700">
              {new Date(syllabus.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          </MetaCell>
        </div>
        {(syllabus.approved_at || syllabus.locked_at) && (
          <div className="px-4 py-2 flex items-center gap-6 text-xs text-gray-500 flex-wrap">
            {syllabus.approved_at && (
              <span>
                <span className="text-gray-400 font-medium">Dean approved: </span>
                {new Date(syllabus.approved_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}
              </span>
            )}
            {syllabus.locked_at && (
              <span>
                <span className="text-gray-400 font-medium">Locked for semester: </span>
                {new Date(syllabus.locked_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}
              </span>
            )}
          </div>
        )}
      </section>

      {/* ── Version history ── */}
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Version History</h3>

        {isLoading && (
          <p className="text-sm text-gray-400 text-center py-6">Loading versions…</p>
        )}

        {!isLoading && versions && versions.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-6">
            No other versions — this is the only revision.
          </p>
        )}

        {versions && versions.length > 0 && (
          <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
            {[...versions].reverse().map((v) => {
              const isCurrent = v.id === syllabus.id
              return (
                <button
                  key={v.id}
                  type="button"
                  disabled={isCurrent}
                  onClick={() => navigate(`/syllabuses/${v.id}`)}
                  className={`w-full text-left flex items-center gap-3 px-4 py-3 transition-colors ${
                    isCurrent
                      ? 'bg-blue-50 cursor-default'
                      : 'hover:bg-gray-50 cursor-pointer group'
                  }`}
                >
                  <GitFork className="h-4 w-4 text-gray-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-gray-700">v{v.version}</span>
                      <SyllabusStatusBadge status={v.status} />
                      {isCurrent && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                          current
                        </span>
                      )}
                    </div>
                    {v.change_note && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{v.change_note}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-gray-400">
                      {new Date(v.created_at).toLocaleDateString()}
                    </span>
                    {!isCurrent && (
                      <ExternalLink className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500" />
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {versions && versions.length > 1 && (
          <p className="text-xs text-gray-400 mt-2">
            Click a version to open it. Fork from an approved version to start a new revision.
          </p>
        )}
      </section>
    </div>
  )
}

function MetaCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      {children}
    </div>
  )
}
