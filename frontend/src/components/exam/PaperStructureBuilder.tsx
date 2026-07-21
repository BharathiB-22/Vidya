// M08 Exam Setter — the paper structure builder.
//
// Faculty think in exactly two nouns, and this file offers exactly those two:
//
//     Section              "Part A — answer any FIVE"
//       └── Question Definition   "5 questions, 10 marks, units 2 & 5"
//
// There is no template "type" to pick, and no university named anywhere. Every
// pattern falls out of sections + rules + definitions, and THE COMPILER decides
// which unit each question lands on — faculty never write "Q1 Unit1, Q2 Unit2".
//
// Units are always the approved syllabus's own units, passed in by the page. This
// component never invents one.
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DIFFICULTIES,
  QUESTION_KINDS,
  BLOOM_LEVELS,
  defaultRuleText,
  definitionPrinted,
  definitionWeight,
  newDefinition,
  newPart,
  newSection,
  sectionTotals,
  sectionWeights,
  type PaperSection,
  type QuestionDefinition,
  type QuestionPart,
} from '@/lib/paperTemplate'
import { useState } from 'react'

/** A unit as the syllabus defines it — number and title. Never fabricated. */
export interface BuilderUnit {
  unit_number: number
  title:       string | null
}

/** A course outcome the paper may map questions to. */
export interface BuilderOutcome {
  id:   string
  code: string
}

interface Props {
  sections:  PaperSection[]
  onChange:  (sections: PaperSection[]) => void
  units:     BuilderUnit[]
  outcomes:  BuilderOutcome[]
}

const SELECT = 'border border-gray-200 rounded-lg px-2 py-1.5 text-sm bg-white ' +
  'focus:outline-none focus:ring-2 focus:ring-indigo-300'
const NUMBER = 'w-16 border border-gray-200 rounded-lg px-2 py-1.5 text-sm ' +
  'focus:outline-none focus:ring-2 focus:ring-indigo-300'

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

export default function PaperStructureBuilder({ sections, onChange, units, outcomes }: Props) {
  function updateSection(id: string, patch: Partial<PaperSection>) {
    onChange(sections.map(s => (s.id === id ? { ...s, ...patch } : s)))
  }
  function removeSection(id: string) {
    onChange(sections.filter(s => s.id !== id))
  }
  function addSection() {
    onChange([...sections, newSection(sections.length)])
  }

  return (
    <div className="space-y-4">
      {sections.length === 0 && (
        <p className="text-sm text-gray-500 bg-gray-50 border border-dashed border-gray-200 rounded-xl px-4 py-6 text-center">
          A paper is made of sections. Add the first one — then say how many
          questions it asks for, and the compiler does the rest.
        </p>
      )}

      {sections.map((sec, si) => (
        <SectionCard
          key={sec.id}
          section={sec}
          index={si}
          units={units}
          outcomes={outcomes}
          onChange={patch => updateSection(sec.id, patch)}
          onRemove={() => removeSection(sec.id)}
        />
      ))}

      <Button type="button" variant="outline" onClick={addSection} className="w-full">
        <Plus className="w-4 h-4 mr-1" /> Add Section
      </Button>
    </div>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────

function SectionCard({
  section, index, units, outcomes, onChange, onRemove,
}: {
  section:  PaperSection
  index:    number
  units:    BuilderUnit[]
  outcomes: BuilderOutcome[]
  onChange: (patch: Partial<PaperSection>) => void
  onRemove: () => void
}) {
  const weights = sectionWeights(section)
  const totals = sectionTotals(section)
  const isAnyK = section.answer_rule.mode === 'ANY_K'
  // k can never exceed the number of questions the section actually prints.
  const k = Math.max(0, Math.min(Number(section.answer_rule.k ?? weights.length), weights.length))

  function updateDefinition(id: string, patch: Partial<QuestionDefinition>) {
    onChange({ definitions: section.definitions.map(d => (d.id === id ? { ...d, ...patch } : d)) })
  }
  function removeDefinition(id: string) {
    onChange({ definitions: section.definitions.filter(d => d.id !== id) })
  }
  function addDefinition() {
    onChange({ definitions: [...section.definitions, newDefinition()] })
  }

  return (
    <div className="rounded-xl border-2 border-gray-200 bg-white overflow-hidden">
      {/* Section header — name and the rule that governs it */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Section</span>
          <input
            value={section.name}
            onChange={e => onChange({ name: e.target.value })}
            placeholder={`Section ${index + 1} name`}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-sm font-semibold
                       focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <Button type="button" variant="ghost" size="icon" onClick={onRemove}
                  aria-label="Remove section">
            <Trash2 className="w-4 h-4 text-gray-600" />
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-gray-500">Students answer</label>
          <select
            value={section.answer_rule.mode}
            onChange={e => onChange({
              answer_rule: e.target.value === 'ALL'
                ? { mode: 'ALL' }
                : { mode: 'ANY_K', k: Math.min(k || 1, weights.length || 1) },
            })}
            className={SELECT}
          >
            <option value="ALL">ALL questions</option>
            <option value="ANY_K">ANY…</option>
          </select>
          {isAnyK && (
            <>
              <input
                type="number" min={1} max={weights.length || 1}
                value={section.answer_rule.k ?? 1}
                onChange={e => onChange({
                  answer_rule: { mode: 'ANY_K', k: Number(e.target.value) },
                })}
                className={NUMBER}
              />
              <span className="text-xs text-gray-500">
                of the {weights.length} question{weights.length === 1 ? '' : 's'} printed
              </span>
            </>
          )}
          <span className="ml-auto text-xs text-gray-500">
            Printed <span className="font-semibold text-gray-700">{fmt(totals.printed)}</span>
            {' · '}Evaluated <span className="font-semibold text-indigo-700">{fmt(totals.evaluation)}</span>
          </span>
        </div>

        <input
          value={section.instruction}
          onChange={e => onChange({ instruction: e.target.value })}
          placeholder={defaultRuleText(section)}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-xs
                     focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <p className="text-[11px] text-gray-600">
          Printed verbatim under the section header. Leave blank to print the rule above.
        </p>
      </div>

      {/* Question definitions */}
      <div className="p-4 space-y-3">
        {section.definitions.map((qd, di) => (
          <DefinitionRow
            key={qd.id}
            definition={qd}
            index={di}
            units={units}
            outcomes={outcomes}
            onChange={patch => updateDefinition(qd.id, patch)}
            onRemove={() => removeDefinition(qd.id)}
          />
        ))}
        <Button type="button" variant="ghost" size="sm" onClick={addDefinition}
                className="text-indigo-600">
          <Plus className="w-4 h-4 mr-1" /> Add Question Definition
        </Button>
      </div>
    </div>
  )
}

// ── Question definition ─────────────────────────────────────────────────────

function DefinitionRow({
  definition: qd, index, units, outcomes, onChange, onRemove,
}: {
  definition: QuestionDefinition
  index:      number
  units:      BuilderUnit[]
  outcomes:   BuilderOutcome[]
  onChange:   (patch: Partial<QuestionDefinition>) => void
  onRemove:   () => void
}) {
  const [open, setOpen] = useState(false)
  const hasParts = qd.parts.length > 0
  // An empty pool means "every unit the paper covers" — the compiler resolves it.
  const pool = qd.units.length ? qd.units : units.map(u => u.unit_number)

  function toggleUnit(n: number) {
    onChange({ units: qd.units.includes(n) ? qd.units.filter(u => u !== n) : [...qd.units, n].sort((a, b) => a - b) })
  }
  function toggleCo(id: string) {
    onChange({ co_ids: qd.co_ids.includes(id) ? qd.co_ids.filter(c => c !== id) : [...qd.co_ids, id] })
  }
  function updatePart(i: number, patch: Partial<QuestionPart>) {
    onChange({ parts: qd.parts.map((p, idx) => (idx === i ? { ...p, ...patch } : p)) })
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50/50">
      {/* The one line that matters: how many, worth what, from where. */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
        <span className="text-xs font-semibold text-gray-600">#{index + 1}</span>

        <span className="text-xs text-gray-500">Generate</span>
        <input
          type="number" min={1} max={50} value={qd.count}
          onChange={e => onChange({ count: Number(e.target.value) })}
          className={NUMBER}
        />
        <span className="text-xs text-gray-500">question(s)</span>

        {!hasParts && (
          <>
            <span className="text-xs text-gray-500">·</span>
            <input
              type="number" min={0} step={0.5} value={qd.marks}
              onChange={e => onChange({ marks: Number(e.target.value) })}
              className={NUMBER}
            />
            <span className="text-xs text-gray-500">marks each</span>
          </>
        )}

        <select
          value={qd.type}
          onChange={e => onChange({ type: e.target.value as QuestionDefinition['type'] })}
          className={`${SELECT} ml-auto`}
        >
          {QUESTION_KINDS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>

        <Button type="button" variant="ghost" size="icon" onClick={() => setOpen(o => !o)}
                aria-label="More options">
          {open ? <ChevronDown className="w-4 h-4 text-gray-600" />
                : <ChevronRight className="w-4 h-4 text-gray-600" />}
        </Button>
        <Button type="button" variant="ghost" size="icon" onClick={onRemove}
                aria-label="Remove definition">
          <Trash2 className="w-4 h-4 text-gray-600" />
        </Button>
      </div>

      {/* Units — the pool the compiler distributes over. */}
      <div className="px-3 pb-2.5 flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500 mr-1">Units</span>
        {units.length === 0 && (
          <span className="text-xs text-amber-600">No syllabus units available.</span>
        )}
        {units.map(u => {
          const on = qd.units.includes(u.unit_number)
          return (
            <button
              key={u.unit_number} type="button"
              onClick={() => toggleUnit(u.unit_number)}
              title={u.title ?? undefined}
              className={`px-2 py-0.5 rounded-md text-xs border transition-colors ${
                on ? 'bg-indigo-600 text-white border-indigo-600'
                   : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
              }`}
            >
              U{u.unit_number}
            </button>
          )
        })}
        {qd.units.length === 0 && units.length > 0 && (
          <span className="text-[11px] text-gray-600 ml-1">
            none selected = all {units.length} units the paper covers
          </span>
        )}

        {pool.length > 1 && (
          <select
            value={qd.unit_mode}
            onChange={e => onChange({ unit_mode: e.target.value as QuestionDefinition['unit_mode'] })}
            className={`${SELECT} ml-2 text-xs`}
          >
            <option value="DISTRIBUTE">Spread questions across these units</option>
            <option value="INTEGRATE">Each question integrates all these units</option>
          </select>
        )}
      </div>

      {/* Everything else, folded away until asked for. */}
      {open && (
        <div className="border-t border-gray-200 px-3 py-3 space-y-3 bg-white">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-gray-600">
              Bloom's
              <select
                value={qd.bloom ?? ''}
                onChange={e => onChange({ bloom: (e.target.value || null) as QuestionDefinition['bloom'] })}
                className={SELECT}
              >
                <option value="">Inherit paper mix</option>
                {BLOOM_LEVELS.map(b => (
                  <option key={b} value={b}>{b.charAt(0) + b.slice(1).toLowerCase()}</option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-1.5 text-xs text-gray-600">
              Difficulty
              <select
                value={qd.difficulty ?? ''}
                onChange={e => onChange({ difficulty: (e.target.value || null) as QuestionDefinition['difficulty'] })}
                className={SELECT}
              >
                <option value="">Inherit</option>
                {DIFFICULTIES.map(d => (
                  <option key={d} value={d}>{d.charAt(0) + d.slice(1).toLowerCase()}</option>
                ))}
              </select>
            </label>

            {!hasParts && (
              <label className="flex items-center gap-1.5 text-xs text-gray-600">
                <input
                  type="checkbox" checked={qd.or_choice}
                  onChange={e => onChange({ or_choice: e.target.checked })}
                  className="accent-indigo-600 w-3.5 h-3.5"
                />
                OR question — print two alternatives, answer one
              </label>
            )}
          </div>

          {/* CO mapping */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs text-gray-600">
              CO mapping
              <select
                value={qd.co_mode}
                onChange={e => onChange({ co_mode: e.target.value as QuestionDefinition['co_mode'] })}
                className={SELECT}
              >
                <option value="AUTO">Auto — let the generator map</option>
                <option value="SPECIFIC">Specific COs</option>
              </select>
            </label>
            {qd.co_mode === 'SPECIFIC' && (
              <div className="flex flex-wrap gap-1.5">
                {outcomes.length === 0 && (
                  <span className="text-xs text-amber-600">
                    This syllabus defines no course outcomes.
                  </span>
                )}
                {outcomes.map(co => {
                  const on = qd.co_ids.includes(co.id)
                  return (
                    <button
                      key={co.id} type="button" onClick={() => toggleCo(co.id)}
                      className={`px-2 py-0.5 rounded-md text-xs border transition-colors ${
                        on ? 'bg-emerald-600 text-white border-emerald-600'
                           : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      {co.code}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* Sub-parts — "Q1 a) b) c)". Optional, and marks move to the parts. */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">
                Sub-parts {hasParts ? '' : '(optional)'}
              </span>
              <Button
                type="button" variant="ghost" size="sm"
                onClick={() => onChange({ parts: [...qd.parts, newPart()] })}
                className="text-indigo-600 h-7"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Add sub-part
              </Button>
            </div>

            {hasParts && (
              <p className="text-[11px] text-gray-600">
                Each generated question prints as one numbered question with these
                parts. Marks come from the parts, so the definition's own marks are
                ignored.
              </p>
            )}

            {qd.parts.map((p, pi) => (
              <div key={pi} className="flex flex-wrap items-center gap-2 rounded-md border border-gray-200 px-2 py-1.5">
                <span className="text-xs font-semibold text-gray-500">{String.fromCharCode(97 + pi)})</span>
                <input
                  type="number" min={0} step={0.5} value={p.marks}
                  onChange={e => updatePart(pi, { marks: Number(e.target.value) })}
                  className={NUMBER}
                />
                <span className="text-xs text-gray-500">marks</span>

                <div className="flex flex-wrap items-center gap-1">
                  {units.map(u => {
                    const on = p.units.includes(u.unit_number)
                    return (
                      <button
                        key={u.unit_number} type="button"
                        onClick={() => updatePart(pi, {
                          units: on ? p.units.filter(x => x !== u.unit_number)
                                    : [...p.units, u.unit_number].sort((a, b) => a - b),
                        })}
                        className={`px-1.5 py-0.5 rounded text-[11px] border transition-colors ${
                          on ? 'bg-indigo-600 text-white border-indigo-600'
                             : 'bg-white text-gray-500 border-gray-200'
                        }`}
                      >
                        U{u.unit_number}
                      </button>
                    )
                  })}
                  {p.units.length === 0 && (
                    <span className="text-[11px] text-gray-600 ml-1">inherit</span>
                  )}
                </div>

                <label className="flex items-center gap-1 text-[11px] text-gray-600 ml-auto">
                  <input
                    type="checkbox" checked={p.or_choice}
                    onChange={e => updatePart(pi, { or_choice: e.target.checked })}
                    className="accent-indigo-600 w-3.5 h-3.5"
                  />
                  OR
                </label>
                <Button
                  type="button" variant="ghost" size="icon"
                  onClick={() => onChange({ parts: qd.parts.filter((_, idx) => idx !== pi) })}
                  aria-label="Remove sub-part"
                >
                  <Trash2 className="w-3.5 h-3.5 text-gray-600" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* What this definition costs the paper. */}
      <div className="border-t border-gray-100 px-3 py-1.5 text-[11px] text-gray-500">
        {qd.count} × {fmt(definitionWeight(qd))} marks
        {qd.or_choice && !hasParts ? ' (two alternatives each)' : ''}
        {' · prints '}{fmt(definitionPrinted(qd))}
        {' · at most '}{fmt(qd.count * definitionWeight(qd))}{' evaluated'}
      </div>
    </div>
  )
}
