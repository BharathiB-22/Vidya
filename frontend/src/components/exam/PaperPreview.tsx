// M08 Exam Setter — live preview of the paper being built.
//
// This mirrors backend/app/modules/m08_exam_setter/pdf_exporter.py `_render_template`:
// same section headers, same rule lines, same numbering, same "— OR —" separator,
// same a) b) c) sub-parts. What faculty read here is what prints.
//
// The questions themselves do not exist yet — the AI writes them from the specs
// this same template compiles to — so each position shows its brief instead: the
// units it will draw on, its marks, and any Bloom's / difficulty asked for.
import {
  compileSpecs,
  defaultRuleText,
  definitionShape,
  sectionTotals,
  stableId,
  templateTotals,
  type PaperSection,
} from '@/lib/paperTemplate'

interface Props {
  sections:     PaperSection[]
  units:        number[]
  title:        string
  courseLabel:  string | null
  durationMins: number
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

/** "A" -> "SECTION A"; "Part A" -> "PART A". Mirrors the exporter's
 *  `_section_header` — faculty type whatever their university calls it, and it
 *  prints once, not doubled. */
function sectionHeader(name: string): string {
  const n = (name || '').trim()
  if (!n) return 'SECTION'
  const up = n.toUpperCase()
  if (['SECTION', 'PART', 'MODULE', 'UNIT', 'GROUP'].some(p => up.startsWith(p))) return up
  return `SECTION ${up}`
}

export default function PaperPreview({ sections, units, title, courseLabel, durationMins }: Props) {
  const { printed, evaluation } = templateTotals({ version: 3, sections })
  const specs = compileSpecs({ version: 3, sections }, units)

  // The brief for each printed position, in printed order — the preview walks the
  // same shape the compiler emits, so a position here is a question there.
  let specIndex = 0
  const nextSpec = () => specs[specIndex++]

  let qNum = 1

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Paper head */}
      <div className="border-b-2 border-gray-800 px-6 py-4 text-center space-y-1">
        <p className="text-[11px] uppercase tracking-widest text-gray-600">Preview</p>
        <h3 className="text-base font-bold text-gray-900 uppercase">{title || 'Untitled Paper'}</h3>
        {courseLabel && <p className="text-sm text-gray-600">{courseLabel}</p>}
        <div className="flex justify-center gap-6 text-xs text-gray-500 pt-1">
          <span>Duration: {durationMins} min</span>
          <span>Max Marks: {fmt(evaluation)}</span>
        </div>
      </div>

      <div className="px-6 py-4 space-y-5">
        {sections.length === 0 && (
          <p className="text-sm text-gray-600 text-center py-6">
            Add a section to see the paper take shape.
          </p>
        )}

        {sections.map((sec, si) => {
          const totals = sectionTotals(sec)
          const secId = stableId(sec, 'sec', si)

          return (
            <div key={secId} className="space-y-2">
              <div className="border-b border-gray-300 pb-1">
                <p className="text-sm font-bold text-gray-900">
                  {sectionHeader(sec.name)}
                  {totals.evaluation > 0 && (
                    <span className="font-normal text-gray-500">
                      {'  '}({fmt(totals.evaluation)} Marks)
                    </span>
                  )}
                </p>
                <p className="text-xs italic text-gray-600">
                  {sec.instruction?.trim() || defaultRuleText(sec)}
                </p>
              </div>

              <div className="space-y-2.5 pt-1">
                {sec.definitions.map((qd, di) => (
                  <div key={qd.id ?? di} className="space-y-2.5">
                    {definitionShape(qd).map((entry, ei) => {
                      const n = qNum++

                      if (entry.parts === null) {
                        const alts = Array.from({ length: entry.alts }, () => nextSpec())
                        return (
                          <div key={ei} className="flex gap-3">
                            <span className="text-sm font-semibold text-gray-700 shrink-0">{n}.</span>
                            <div className="flex-1 space-y-1">
                              {alts.map((s, ai) => (
                                <div key={ai}>
                                  {ai > 0 && (
                                    <p className="text-xs font-semibold text-gray-600 text-center py-0.5">— OR —</p>
                                  )}
                                  <SpecLine spec={s} marks={entry.marks} />
                                </div>
                              ))}
                            </div>
                          </div>
                        )
                      }

                      const total = entry.parts.reduce((s, p) => s + p.marks, 0)
                      let letter = 0
                      return (
                        <div key={ei} className="flex gap-3">
                          <span className="text-sm font-semibold text-gray-700 shrink-0">{n}.</span>
                          <div className="flex-1 space-y-1">
                            <p className="text-xs text-gray-500">({fmt(total)} Marks)</p>
                            {entry.parts.map((p, pi) => {
                              const alts = Array.from({ length: p.alts }, () => nextSpec())
                              return (
                                <div key={pi} className="space-y-1">
                                  {alts.map((s, ai) => {
                                    const lbl = String.fromCharCode(97 + letter++)
                                    return (
                                      <div key={ai}>
                                        {ai > 0 && (
                                          <p className="text-xs font-semibold text-gray-600 text-center py-0.5">— OR —</p>
                                        )}
                                        <div className="flex gap-2 pl-3">
                                          <span className="text-xs font-semibold text-gray-500">{lbl})</span>
                                          <div className="flex-1">
                                            <SpecLine spec={s} marks={p.marks} />
                                          </div>
                                        </div>
                                      </div>
                                    )
                                  })}
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Totals strip — the two numbers that are never the same and always matter */}
      <div className="border-t border-gray-200 bg-gray-50 px-6 py-3 grid grid-cols-3 gap-3 text-center">
        <Stat label="Printed Marks" value={fmt(printed)} />
        <Stat label="Evaluation Marks" value={fmt(evaluation)} accent />
        <Stat label="Questions" value={String(specs.length)} />
      </div>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <p className={`text-lg font-bold ${accent ? 'text-indigo-700' : 'text-gray-800'}`}>{value}</p>
      <p className="text-[11px] uppercase tracking-wide text-gray-500">{label}</p>
    </div>
  )
}

/** One position's brief — what the AI is told to write, shown where the question
 *  text will land. */
function SpecLine({ spec, marks }: { spec: ReturnType<typeof compileSpecs>[number] | undefined; marks: number }) {
  const bits: string[] = []
  if (spec) {
    const us = spec.unit_numbers
    bits.push(us.length > 1 ? `Units ${us.join(' + ')}` : `Unit ${us[0]}`)
    if (spec.bloom) bits.push(spec.bloom.charAt(0) + spec.bloom.slice(1).toLowerCase())
    if (spec.difficulty) bits.push(spec.difficulty.charAt(0) + spec.difficulty.slice(1).toLowerCase())
  }
  return (
    <div className="flex items-start justify-between gap-3 rounded border border-dashed border-gray-200 bg-gray-50/60 px-2.5 py-1.5">
      <span className="text-xs text-gray-500 italic">
        {bits.length ? bits.join(' · ') : 'question'}
      </span>
      <span className="text-xs font-semibold text-gray-600 shrink-0">[{fmt(marks)}]</span>
    </div>
  )
}
