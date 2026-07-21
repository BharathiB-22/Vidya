import { useEffect, useState } from 'react'
import { Check, GripVertical, Pencil, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type {
  CourseDocument,
  Experiment,
  RubricRow,
} from '@/types/syllabus'
import type { CourseType } from '@/types/program'

/**
 * The official document of a course that has NO SYLLABUS.
 *
 * A Board of Studies does not write a syllabus for an internship. There is nothing
 * to lecture: the student is inside a company. What the Board writes instead is the
 * document that GOVERNS the internship — its guidelines, its duration, the rubric
 * the student is marked against, what the host company must provide, how the viva
 * runs. A laboratory gets a lab manual and an experiment list, not five units of
 * lectures it never delivers. A major project gets a handbook.
 *
 * So this renders whichever document the course's type actually has, and the Board
 * edits every line of it in place — because nothing the AI produced is final, and
 * the Board must be able to add, remove, reorder and rewrite any of it.
 *
 * The Dean may edit these too, but only after the Board has approved them, and only
 * for Internship / Mini Project / Major Project / Seminar — those depend on the
 * company, the supervisor and institutional policy, which the Board cannot settle
 * at approval time. A theory syllabus the Dean may never touch, and the API refuses
 * it rather than merely hiding the button.
 */

type SectionKind = 'lines' | 'rubric' | 'experiments' | 'text' | 'number'

interface SectionSpec {
  field: string
  heading: string
  kind: SectionKind
  /** Shown when the section is empty, so an empty section still says what belongs
   *  in it rather than just being absent. */
  hint?: string
}

/**
 * What each type's document contains, in the order it prints.
 *
 * Kept deliberately parallel to the backend's DOCUMENT_SCHEMAS (m02/schemas.py) and
 * to the readiness dashboard's required-section list: a field renamed in one and
 * not the others silently stops being rendered, stops being checked, or both.
 */
const DOCUMENT_SECTIONS: Record<Exclude<CourseType, 'THEORY'>, SectionSpec[]> = {
  LAB: [
    { field: 'manual_intro',          heading: 'Introduction',            kind: 'text',
      hint: 'What this laboratory practises, and how it relates to the theory taught.' },
    { field: 'experiments',           heading: 'List of Experiments',     kind: 'experiments',
      hint: 'The experiments performed at the bench, in the order they are performed.' },
    { field: 'equipment',             heading: 'Equipment Required',      kind: 'lines',
      hint: 'The hardware, instruments and bench apparatus the laboratory needs.' },
    { field: 'software',              heading: 'Software Required',       kind: 'lines',
      hint: 'The tools, compilers, simulators and licences required.' },
    { field: 'assessment_guidelines', heading: 'Assessment Guidelines',   kind: 'lines',
      hint: 'How the student’s laboratory work is marked.' },
  ],
  INTERNSHIP: [
    { field: 'guidelines',           heading: 'Internship Guidelines',   kind: 'lines' },
    { field: 'duration',             heading: 'Duration',                kind: 'text',
      hint: 'e.g. 8 weeks (minimum 240 hours), after the Semester VI examinations.' },
    { field: 'credits',              heading: 'Credits',                 kind: 'number' },
    { field: 'evaluation_rubric',    heading: 'Evaluation Rubric',       kind: 'rubric' },
    { field: 'weekly_activities',    heading: 'Weekly Activities',       kind: 'lines' },
    { field: 'company_requirements', heading: 'Company Requirements',    kind: 'lines',
      hint: 'What the host organisation must provide for the internship to count.' },
    { field: 'report_format',        heading: 'Report Format',           kind: 'lines' },
    { field: 'viva_guidelines',      heading: 'Viva Guidelines',         kind: 'lines' },
  ],
  MINI_PROJECT: [
    { field: 'guidelines',   heading: 'Project Guidelines', kind: 'lines' },
    { field: 'milestones',   heading: 'Milestones',         kind: 'lines' },
    { field: 'deliverables', heading: 'Deliverables',       kind: 'lines' },
    { field: 'reviews',      heading: 'Reviews',            kind: 'lines' },
    { field: 'rubrics',      heading: 'Rubrics',            kind: 'rubric' },
  ],
  MAJOR_PROJECT: [
    { field: 'handbook',            heading: 'Project Handbook',     kind: 'lines' },
    { field: 'proposal_format',     heading: 'Proposal Format',      kind: 'lines' },
    { field: 'timeline',            heading: 'Timeline',             kind: 'lines' },
    { field: 'reviews',             heading: 'Reviews',              kind: 'lines' },
    { field: 'rubrics',             heading: 'Rubrics',              kind: 'rubric' },
    { field: 'final_report_format', heading: 'Final Report Format',  kind: 'lines' },
    { field: 'demonstration',       heading: 'Demonstration',        kind: 'lines' },
    { field: 'viva',                heading: 'Viva Voce',            kind: 'lines' },
  ],
  SEMINAR: [
    { field: 'guidelines',          heading: 'Seminar Guidelines',   kind: 'lines' },
    { field: 'topic_selection',     heading: 'Topic Selection',      kind: 'lines' },
    { field: 'presentation_format', heading: 'Presentation Format',  kind: 'lines' },
    { field: 'evaluation_rubric',   heading: 'Evaluation Rubric',    kind: 'rubric' },
    { field: 'deliverables',        heading: 'Deliverables',         kind: 'lines' },
  ],
}

export function documentSectionsFor(docType: CourseType): SectionSpec[] {
  if (docType === 'THEORY') return []
  return DOCUMENT_SECTIONS[docType] ?? []
}

interface Props {
  docType: CourseType
  document: CourseDocument
  canEdit: boolean
  /** Persists the whole document. The Board edits through the normal syllabus
   *  update; the Dean, post-approval, through the dean-edit endpoint. The component
   *  does not know or care which — the page decides. */
  onSave: (document: CourseDocument) => void
  saving?: boolean
  /** Rewrite this whole document with AI. Omitted for a reader. */
  onRegenerate?: () => void
}

export function CourseDocumentSections({
  docType, document, canEdit, onSave, saving, onRegenerate,
}: Props) {
  const sections = documentSectionsFor(docType)
  if (!sections.length) return null

  const doc = (document ?? {}) as Record<string, unknown>

  function save(field: string, value: unknown) {
    onSave({ ...(doc as CourseDocument), [field]: value } as CourseDocument)
  }

  return (
    <section className="mt-8">
      {canEdit && onRegenerate && (
        <div className="mb-3 flex justify-end print:hidden">
          <Button variant="outline" size="sm" onClick={onRegenerate} disabled={saving}>
            <Sparkles className="mr-1 h-4 w-4" />
            Regenerate this document
          </Button>
        </div>
      )}

      {sections.map((spec) => (
        <DocumentSection
          key={spec.field}
          spec={spec}
          value={doc[spec.field]}
          canEdit={canEdit}
          saving={!!saving}
          onSave={(v) => save(spec.field, v)}
        />
      ))}
    </section>
  )
}

// ---------------------------------------------------------------------------
// One section
// ---------------------------------------------------------------------------

function DocumentSection({
  spec, value, canEdit, saving, onSave,
}: {
  spec: SectionSpec
  value: unknown
  canEdit: boolean
  saving: boolean
  onSave: (v: unknown) => void
}) {
  return (
    <div className="mt-6">
      <h2 className="border-b border-gray-400 pb-1 text-sm font-bold uppercase tracking-wide text-black">
        {spec.heading}
      </h2>

      {spec.kind === 'lines' && (
        <LineListEditor
          lines={Array.isArray(value) ? (value as string[]) : []}
          canEdit={canEdit}
          saving={saving}
          hint={spec.hint}
          onSave={onSave}
        />
      )}

      {spec.kind === 'text' && (
        <ProseEditor
          text={typeof value === 'string' ? value : ''}
          canEdit={canEdit}
          saving={saving}
          hint={spec.hint}
          onSave={onSave}
        />
      )}

      {spec.kind === 'number' && (
        <NumberEditor
          value={typeof value === 'number' ? value : null}
          canEdit={canEdit}
          saving={saving}
          onSave={onSave}
        />
      )}

      {spec.kind === 'rubric' && (
        <RubricEditor
          rows={Array.isArray(value) ? (value as RubricRow[]) : []}
          canEdit={canEdit}
          saving={saving}
          onSave={onSave}
        />
      )}

      {spec.kind === 'experiments' && (
        <ExperimentEditor
          experiments={Array.isArray(value) ? (value as Experiment[]) : []}
          canEdit={canEdit}
          saving={saving}
          onSave={onSave}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// A list of prose lines — guidelines, milestones, deliverables, equipment...
//
// The Board must be able to edit, add, remove and REORDER any of them. Reordering
// matters more than it looks: milestones and weekly activities are sequences, and a
// list you cannot reorder is a list you have to retype to fix.
// ---------------------------------------------------------------------------

function LineListEditor({
  lines, canEdit, saving, hint, onSave,
}: {
  lines: string[]
  canEdit: boolean
  saving: boolean
  hint?: string
  onSave: (lines: string[]) => void
}) {
  const [draft, setDraft] = useState<string[] | null>(null)
  const [adding, setAdding] = useState('')

  const editing = draft !== null
  const shown = draft ?? lines

  function commit(next: string[]) {
    const cleaned = next.map((l) => l.trim()).filter(Boolean)
    onSave(cleaned)
    setDraft(null)
    setAdding('')
  }

  if (!editing) {
    return (
      <div className="group relative">
        {lines.length === 0 ? (
          <p className="mt-2 text-sm italic text-gray-500">
            {hint ?? 'Nothing here yet.'}
          </p>
        ) : (
          <ol className="mt-2 space-y-1 text-sm leading-relaxed text-black">
            {lines.map((line, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 text-gray-500">{i + 1}.</span>
                <span>{line}</span>
              </li>
            ))}
          </ol>
        )}
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 opacity-0 transition-opacity group-hover:opacity-100 print:hidden"
            onClick={() => setDraft([...lines])}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="mt-2 space-y-2 print:hidden">
      {shown.map((line, i) => (
        <div key={i} className="flex items-start gap-2">
          <GripVertical className="mt-2 h-4 w-4 shrink-0 text-gray-500" />
          <Textarea
            value={line}
            rows={2}
            className="text-sm"
            onChange={(e) => {
              const next = [...shown]
              next[i] = e.target.value
              setDraft(next)
            }}
          />
          <div className="flex shrink-0 flex-col gap-1">
            <Button
              variant="ghost"
              size="sm"
              disabled={i === 0}
              title="Move up"
              onClick={() => {
                const next = [...shown]
                ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                setDraft(next)
              }}
            >
              ↑
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={i === shown.length - 1}
              title="Move down"
              onClick={() => {
                const next = [...shown]
                ;[next[i + 1], next[i]] = [next[i], next[i + 1]]
                setDraft(next)
              }}
            >
              ↓
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title="Remove"
              onClick={() => setDraft(shown.filter((_, j) => j !== i))}
            >
              <Trash2 className="h-3.5 w-3.5 text-red-600" />
            </Button>
          </div>
        </div>
      ))}

      <div className="flex gap-2">
        <Input
          value={adding}
          placeholder="Add a line…"
          className="text-sm"
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && adding.trim()) {
              e.preventDefault()
              setDraft([...shown, adding.trim()])
              setAdding('')
            }
          }}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={!adding.trim()}
          onClick={() => {
            setDraft([...shown, adding.trim()])
            setAdding('')
          }}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex gap-2">
        <Button size="sm" disabled={saving} onClick={() => commit(shown)}>
          <Check className="mr-1 h-4 w-4" />
          Save
        </Button>
        <Button variant="ghost" size="sm" onClick={() => { setDraft(null); setAdding('') }}>
          <X className="mr-1 h-4 w-4" />
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// A prose block — the lab manual's introduction, the internship's duration
// ---------------------------------------------------------------------------

function ProseEditor({
  text, canEdit, saving, hint, onSave,
}: {
  text: string
  canEdit: boolean
  saving: boolean
  hint?: string
  onSave: (text: string) => void
}) {
  const [draft, setDraft] = useState<string | null>(null)

  useEffect(() => { setDraft(null) }, [text])

  if (draft === null) {
    return (
      <div className="group relative">
        <p className={`mt-2 text-sm leading-relaxed ${text ? 'text-black' : 'italic text-gray-500'}`}>
          {text || hint || 'Nothing here yet.'}
        </p>
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 opacity-0 transition-opacity group-hover:opacity-100 print:hidden"
            onClick={() => setDraft(text)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="mt-2 space-y-2 print:hidden">
      <Textarea
        value={draft}
        rows={3}
        className="text-sm"
        onChange={(e) => setDraft(e.target.value)}
      />
      <div className="flex gap-2">
        <Button size="sm" disabled={saving} onClick={() => onSave(draft.trim())}>
          <Check className="mr-1 h-4 w-4" />
          Save
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
          <X className="mr-1 h-4 w-4" />
          Cancel
        </Button>
      </div>
    </div>
  )
}

function NumberEditor({
  value, canEdit, saving, onSave,
}: {
  value: number | null
  canEdit: boolean
  saving: boolean
  onSave: (v: number | null) => void
}) {
  const [draft, setDraft] = useState<string | null>(null)

  if (draft === null) {
    return (
      <div className="group relative">
        <p className={`mt-2 text-sm ${value != null ? 'text-black' : 'italic text-gray-500'}`}>
          {value != null ? value : 'Not set.'}
        </p>
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 opacity-0 transition-opacity group-hover:opacity-100 print:hidden"
            onClick={() => setDraft(value != null ? String(value) : '')}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="mt-2 flex gap-2 print:hidden">
      <Input
        type="number"
        min={0}
        value={draft}
        className="w-28 text-sm"
        onChange={(e) => setDraft(e.target.value)}
      />
      <Button
        size="sm"
        disabled={saving}
        onClick={() => {
          const n = parseInt(draft, 10)
          onSave(Number.isNaN(n) ? null : n)
          setDraft(null)
        }}
      >
        <Check className="mr-1 h-4 w-4" />
        Save
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
        <X className="mr-1 h-4 w-4" />
        Cancel
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The evaluation rubric — the table a student is actually marked against
//
// The weightages are totalled and shown, because a rubric that does not add to 100
// is the single most common defect in one, and it is invisible until somebody tries
// to award the marks.
// ---------------------------------------------------------------------------

function RubricEditor({
  rows, canEdit, saving, onSave,
}: {
  rows: RubricRow[]
  canEdit: boolean
  saving: boolean
  onSave: (rows: RubricRow[]) => void
}) {
  const [draft, setDraft] = useState<RubricRow[] | null>(null)
  const shown = draft ?? rows
  const total = shown.reduce((sum, r) => sum + (r.weightage ?? 0), 0)

  const totalNote =
    shown.length === 0 ? null : total === 100 ? (
      <span className="text-green-700">Weightages total 100%.</span>
    ) : (
      <span className="text-amber-700">
        Weightages total {total}% — a rubric should add up to 100.
      </span>
    )

  if (draft === null) {
    return (
      <div className="group relative">
        {rows.length === 0 ? (
          <p className="mt-2 text-sm italic text-gray-500">No rubric yet.</p>
        ) : (
          <>
            <table className="mt-2 w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th className="border border-gray-400 bg-gray-100 px-2 py-1 text-left font-semibold">
                    Criterion
                  </th>
                  <th className="w-24 border border-gray-400 bg-gray-100 px-2 py-1 text-left font-semibold">
                    Weightage
                  </th>
                  <th className="border border-gray-400 bg-gray-100 px-2 py-1 text-left font-semibold">
                    Descriptor
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td className="border border-gray-400 px-2 py-1">{r.criterion}</td>
                    <td className="border border-gray-400 px-2 py-1">
                      {r.weightage != null ? `${r.weightage}%` : '—'}
                    </td>
                    <td className="border border-gray-400 px-2 py-1 text-gray-700">
                      {r.descriptor ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs">{totalNote}</p>
          </>
        )}
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 opacity-0 transition-opacity group-hover:opacity-100 print:hidden"
            onClick={() => setDraft(rows.map((r) => ({ ...r })))}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }

  function set(i: number, patch: Partial<RubricRow>) {
    const next = [...shown]
    next[i] = { ...next[i], ...patch }
    setDraft(next)
  }

  return (
    <div className="mt-2 space-y-2 print:hidden">
      {shown.map((r, i) => (
        <div key={i} className="flex items-start gap-2">
          <Input
            value={r.criterion}
            placeholder="Criterion"
            className="flex-1 text-sm"
            onChange={(e) => set(i, { criterion: e.target.value })}
          />
          <Input
            type="number"
            min={0}
            max={100}
            value={r.weightage ?? ''}
            placeholder="%"
            className="w-20 text-sm"
            onChange={(e) => {
              const n = parseInt(e.target.value, 10)
              set(i, { weightage: Number.isNaN(n) ? null : n })
            }}
          />
          <Input
            value={r.descriptor ?? ''}
            placeholder="What earns it"
            className="flex-1 text-sm"
            onChange={(e) => set(i, { descriptor: e.target.value })}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDraft(shown.filter((_, j) => j !== i))}
          >
            <Trash2 className="h-3.5 w-3.5 text-red-600" />
          </Button>
        </div>
      ))}

      <p className="text-xs">{totalNote}</p>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDraft([...shown, { criterion: '', weightage: null, descriptor: '' }])}
        >
          <Plus className="mr-1 h-4 w-4" />
          Add row
        </Button>
        <Button
          size="sm"
          disabled={saving}
          onClick={() => {
            onSave(shown.filter((r) => r.criterion.trim()))
            setDraft(null)
          }}
        >
          <Check className="mr-1 h-4 w-4" />
          Save
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
          <X className="mr-1 h-4 w-4" />
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The experiment list — what a lab manual actually IS
//
// The equivalent of a theory unit's topic list: the thing that prints, and the
// thing a model will happily return four of. It is numbered because the order is
// the order they are performed in, roughly one per teaching week.
// ---------------------------------------------------------------------------

function ExperimentEditor({
  experiments, canEdit, saving, onSave,
}: {
  experiments: Experiment[]
  canEdit: boolean
  saving: boolean
  onSave: (experiments: Experiment[]) => void
}) {
  const [draft, setDraft] = useState<Experiment[] | null>(null)
  const shown = draft ?? experiments

  /** Numbers are POSITIONS, not data. Re-deriving them on every save means a
   *  removed or reordered experiment cannot leave a gap or a duplicate behind. */
  const renumber = (list: Experiment[]) => list.map((e, i) => ({ ...e, number: i + 1 }))

  if (draft === null) {
    return (
      <div className="group relative">
        {experiments.length === 0 ? (
          <p className="mt-2 text-sm italic text-gray-500">
            No experiments yet. Click the pencil and paste the list — one per line.
          </p>
        ) : (
          <ol className="mt-2 space-y-3 text-sm leading-relaxed text-black">
            {[...experiments]
              .sort((a, b) => a.number - b.number)
              .map((e) => (
                <li key={e.number} className="flex gap-2">
                  <span className="shrink-0 font-semibold">{e.number}.</span>
                  <div>
                    <p className="font-medium">{e.title}</p>
                    {e.aim && (
                      <p className="text-gray-700">
                        <span className="font-medium">Aim: </span>
                        {e.aim}
                      </p>
                    )}
                    {e.procedure && (
                      <p className="text-gray-700">
                        <span className="font-medium">Procedure: </span>
                        {e.procedure}
                      </p>
                    )}
                    {!!e.apparatus?.length && (
                      <p className="text-gray-700">
                        <span className="font-medium">Apparatus: </span>
                        {e.apparatus.join(', ')}
                      </p>
                    )}
                    {e.hours != null && (
                      <p className="text-gray-600">{e.hours} hours</p>
                    )}
                  </div>
                </li>
              ))}
          </ol>
        )}
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 top-0 opacity-0 transition-opacity group-hover:opacity-100 print:hidden"
            onClick={() => setDraft(experiments.map((e) => ({ ...e })))}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }

  /** The whole list, one experiment per line — which is how a Board has it: in a Word
   *  document, in an email, in the last regulation. Paste fifteen lines and there are
   *  fifteen experiments. */
  const lines = shown.map((e) => e.title).join('\n')

  /** Lines back into experiments, KEEPING the detail the old ones carried.
   *
   *  An experiment's aim, procedure, apparatus and hours are optional and are edited
   *  nowhere on this screen — so they are matched back by POSITION and preserved. A
   *  Board that fixes a typo in experiment 7's title must not thereby delete the aim it
   *  wrote for experiment 7 last week. */
  function parse(text: string): Experiment[] {
    return text
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((title, i) => {
        const prior = shown[i]
        return {
          number:    i + 1,
          title,
          aim:       prior?.aim ?? null,
          procedure: prior?.procedure ?? null,
          apparatus: prior?.apparatus ?? [],
          hours:     prior?.hours ?? null,
        }
      })
  }

  const count = lines.split('\n').filter((l) => l.trim()).length

  return (
    <div className="mt-2 space-y-2 print:hidden">
      <Textarea
        autoFocus
        rows={Math.max(8, count + 2)}
        value={lines}
        placeholder={
          'One experiment per line — paste the whole list at once:\n\n' +
          'Implement stack operations using arrays\n' +
          'Implement a singly linked list\n' +
          'Implement binary search on a sorted array'
        }
        className="text-sm leading-relaxed"
        onChange={(ev) => setDraft(parse(ev.target.value))}
      />
      <p className="text-xs text-gray-500">
        {count} experiment{count === 1 ? '' : 's'}. They are numbered by their order
        here. Aim, procedure and apparatus are optional and are kept as they were.
      </p>

      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={saving}
          onClick={() => {
            onSave(renumber(shown.filter((e) => e.title.trim())))
            setDraft(null)
          }}
        >
          <Check className="mr-1 h-4 w-4" />
          {saving ? 'Saving…' : 'Save'}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
          <X className="mr-1 h-4 w-4" />
          Cancel
        </Button>
      </div>
    </div>
  )
}
