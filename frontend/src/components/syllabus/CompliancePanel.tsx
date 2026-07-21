import { ShieldCheck, CircleDashed, Info, RefreshCw, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSyllabusCompliance } from '@/hooks/syllabuses'

/** Where the Board goes to fix a finding BY HAND, and what the button says.
 *
 * Every required section has one. The old panel named the defect and offered nothing —
 * so the only visible route out of "no Course Outcomes" was Regenerate with AI, which
 * spends tokens rewriting five outcomes when the Board wanted to type one. A compliance
 * report that states a problem and hides the fix is a report that pushes people toward
 * the expensive answer.
 *
 * The AI route stays exactly where it was — on the section itself, next to the content
 * it would rewrite. It is a choice here, never the only door.
 */
const FIXES: Record<string, { label: string; tab: string; anchor?: string }> = {
  UNITS_PENDING:       { label: 'Add Unit',            tab: 'document', anchor: 'section-units' },
  UNIT_HOURS_MISMATCH: { label: 'Adjust Unit Hours',   tab: 'document', anchor: 'section-units' },
  OBJECTIVES_MISSING:  { label: 'Add Objectives',      tab: 'document', anchor: 'section-objectives' },
  EXPERIMENTS_MISSING: { label: 'Add Experiments',     tab: 'document' },
  CO_MIN_NOT_MET:      { label: 'Add Course Outcome',  tab: 'outcomes' },
  CO_MISSING:          { label: 'Add Lab Outcome',     tab: 'outcomes' },
  BLOOM_DIVERSITY_LOW: { label: 'Review Outcomes',     tab: 'outcomes' },
  COPO_COVERAGE_LOW:   { label: 'Map COs to POs',      tab: 'matrix' },
  REFERENCES_PENDING:  { label: 'Add Reference',       tab: 'references' },
  DOCUMENT_EMPTY:      { label: 'Open the Document',   tab: 'document' },
}

interface Props {
  syllabusId: string
  /** Take the Board to the editor that fixes this finding. */
  onFix?: (tab: string, anchor?: string) => void
}

/**
 * What is left to do before this syllabus can be approved — and who has to do it.
 *
 * TWO KINDS OF FINDING, and the difference is the whole point of this panel:
 *
 *   PENDING COMPLETION  a required section the syllabus does not have yet. The Board
 *                       can write it, right now, in the tab it belongs to. That the AI
 *                       failed to draft it is not a fact about the Board's options; it
 *                       is a fact about a model's afternoon.
 *
 *   ADVISORY            worth knowing, never blocking. A missing web resource has
 *                       never been a reason to hold up a curriculum.
 *
 * A Pending Completion item BECOMES an Approval Blocker at the moment the Board presses
 * Approve with the section still empty — same rule, same content test, said at the point
 * where it actually bites. Nothing here is a judgement about the AI: the gate reads the
 * SYLLABUS, and a syllabus the Board typed by hand passes exactly as one the AI drafted.
 */
export function CompliancePanel({ syllabusId, onFix }: Props) {
  const { data, isLoading, isError, refetch, isFetching } = useSyllabusCompliance(syllabusId)

  /** The button that completes this section by hand. */
  function FixButton({ code }: { code: string }) {
    const fix = FIXES[code]
    if (!fix || !onFix) return null
    return (
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 bg-white"
        onClick={() => onFix(fix.tab, fix.anchor)}
      >
        {fix.label}
        <ArrowRight className="ml-1 h-3.5 w-3.5" />
      </Button>
    )
  }

  const pending  = data?.violations.filter((v) => v.severity === 'ERROR')  ?? []
  const advisory = data?.violations.filter((v) => v.severity !== 'ERROR') ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Compliance Check</h3>
        <Button
          size="sm"
          variant="outline"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
          {isFetching ? 'Checking…' : 'Run Check'}
        </Button>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-600 py-4 text-center">Running compliance check…</p>
      )}

      {isError && (
        <p className="text-sm text-red-500 py-4">Failed to load compliance results.</p>
      )}

      {data && (
        <div className="space-y-4">
          <div className={`flex items-center gap-2 rounded-lg px-4 py-3 border ${
            data.passed
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-amber-50 border-amber-200 text-amber-800'
          }`}>
            {data.passed
              ? <ShieldCheck className="h-5 w-5 shrink-0" />
              : <CircleDashed className="h-5 w-5 shrink-0" />}
            <span className="text-sm font-semibold">
              {data.passed
                ? 'Complete — this syllabus can be approved'
                : `${pending.length} section${pending.length !== 1 ? 's' : ''} pending completion`}
            </span>
          </div>

          {pending.length > 0 && (
            <section className="rounded-lg border border-amber-200">
              <header className="border-b border-amber-200 bg-amber-50 px-4 py-2">
                <h4 className="text-xs font-bold uppercase tracking-wide text-amber-800">
                  Pending Completion
                </h4>
                <p className="mt-0.5 text-xs text-amber-800">
                  Each button takes you straight to the editor for that section — write it
                  yourself, no AI call and no tokens. Regenerating is offered on the
                  section itself if you would rather; the syllabus is the same either way.
                  Approval is refused while any of these is still empty, and at that point
                  they are reported as Approval Blockers.
                </p>
              </header>
              <div className="divide-y divide-gray-100">
                {pending.map((v, i) => (
                  <div key={i} className="flex items-start gap-3 px-4 py-3">
                    <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                      Pending
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs text-gray-500">{v.code}</p>
                      <p className="text-sm text-gray-700">{v.message}</p>
                    </div>
                    <FixButton code={v.code} />
                  </div>
                ))}
              </div>
            </section>
          )}

          {advisory.length > 0 && (
            <section className="rounded-lg border border-gray-200">
              <header className="flex items-center gap-1.5 border-b border-gray-200 bg-gray-50 px-4 py-2">
                <Info className="h-3.5 w-3.5 text-gray-500" />
                <h4 className="text-xs font-bold uppercase tracking-wide text-gray-600">
                  Advisory — does not block approval
                </h4>
              </header>
              <div className="divide-y divide-gray-100">
                {advisory.map((v, i) => (
                  <div key={i} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs text-gray-500">{v.code}</p>
                      <p className="text-sm text-gray-600">{v.message}</p>
                    </div>
                    <FixButton code={v.code} />
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
