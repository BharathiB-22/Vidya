import { useEffect, useState } from 'react'
import {
  Check, Lock, Pencil, Plus, Printer, Sparkles, Trash2, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
  useAddUnit,
  useDeleteUnit,
  useRegenerateSection,
  useUpdateSyllabus,
  useUpdateUnit,
} from '@/hooks/syllabuses'
import { addToast } from '@/hooks/useToast'
import { CourseDocumentSections } from '@/components/syllabus/CourseDocumentSections'
import { regenerateLabel } from '@/types/syllabus'
import type {
  CourseDocument,
  CourseOutcome,
  RefType,
  RegenerateSection,
  Syllabus,
  SyllabusReference,
  SyllabusUnit,
} from '@/types/syllabus'

/**
 * The official university syllabus, as a document.
 *
 * This is not a form with a preview. It IS the regulation page — the thing that
 * goes into the university's handbook — and the Board edits it in place, the way
 * you would edit a document rather than fill in a record.
 *
 * A unit is its list of academic topics. An AICTE / Anna University / VTU unit runs
 * to 12–20 of them, and that list is what a lecturer reads to know what to teach
 * and what a student reads to know what they will be taught. So the topics are what
 * this page shows and what the Board edits, one line at a time.
 *
 * Nothing the AI produced is final. It writes the first draft; the Board rewrites
 * whatever it likes and approves — and only the approved version is published.
 */

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
const roman = (n: number) => ROMAN[n - 1] ?? String(n)

/** The four printed bibliography sections, and which ref types land in each. */
const BIBLIOGRAPHY: Array<{ heading: string; types: RefType[] }> = [
  { heading: 'Text Books',        types: ['TEXTBOOK'] },
  { heading: 'Reference Books',   types: ['REFERENCE', 'JOURNAL'] },
  { heading: 'Suggested Reading', types: ['SUGGESTED_READING'] },
  { heading: 'Web Resources',     types: ['WEB_RESOURCE', 'ONLINE'] },
]

/**
 * Below this a unit is an outline, not a regulation. Mirrors the AI's own floor
 * (MIN_TOPICS_PER_UNIT in m02/ai_provider.py) — the two must agree, or the document
 * warns about units the generator was perfectly happy to produce.
 *
 * A real unit runs to 12–15 topics, and that is what the AI is asked for. But a
 * dense unit on a narrow subject legitimately runs to 8, so 8 is where the warning
 * starts rather than where the ideal sits: quality is the bar, not a word count.
 */
const MIN_TOPICS = 8
const TARGET_TOPICS = 12

interface Props {
  syllabus: Syllabus
  outcomes: CourseOutcome[]
  units: SyllabusUnit[]
  references: SyllabusReference[]
  /** Board members edit; everyone else reads. */
  canEdit: boolean
  /**
   * Persist the type-specific document body. Optional: when omitted the Board's
   * normal syllabus update is used.
   *
   * The Dean passes their own saver here — post-approval they edit an Internship,
   * Project or Seminar document through a different endpoint, one that keeps the
   * Board's approval intact and stamps the row instead. The component does not need
   * to know which; the page decides who is editing.
   */
  onSaveDocument?: (document: CourseDocument) => void
  onSaveDocumentPending?: boolean
}

export function OfficialSyllabusDocument({
  syllabus, outcomes, units, references, canEdit,
  onSaveDocument, onSaveDocumentPending = false,
}: Props) {
  const info = syllabus.course_information
  const updateSyllabus = useUpdateSyllabus()
  const addUnit = useAddUnit(syllabus.id)
  const regenerate = useRegenerateSection(syllabus.id)

  // The document's OWN type, not the course's current one. If a Dean reclassified
  // the course after the Board approved a lab manual, this is still a lab manual.
  const isTheory = syllabus.doc_type === 'THEORY'

  const sortedUnits = [...units].sort((a, b) => a.unit_number - b.unit_number)
  const sortedOutcomes = [...outcomes].sort((a, b) => a.display_order - b.display_order)
  const totalHours = sortedUnits.reduce((sum, u) => sum + (u.total_hours || 0), 0)
  const confirmed = references.filter((r) => r.is_confirmed)

  function regen(section: RegenerateSection, unitId?: string) {
    regenerate.mutate(
      { section, unit_id: unitId },
      {
        onSuccess: () =>
          addToast(
            `${regenerateLabel(section, syllabus.doc_type)} — this runs in the background, ` +
              'and the rest of the document is untouched and still editable.',
            'success',
            9000,
          ),
      },
    )
  }

  return (
    <article className="mx-auto max-w-4xl">
      <div className="mb-4 flex justify-end print:hidden">
        <Button variant="outline" size="sm" onClick={() => window.print()}>
          <Printer className="mr-1 h-4 w-4" />
          Print / Save as PDF
        </Button>
      </div>

      <div className="rounded-xl border border-gray-300 bg-white p-8 shadow-sm print:border-0 print:p-0 print:shadow-none">
        {/* ── Title ─────────────────────────────────────────────────────── */}
        <header className="border-b-2 border-black pb-3 text-center">
          <h1 className="text-lg font-bold uppercase tracking-wide text-black">
            {info?.course_code} &nbsp;–&nbsp; {info?.course_name}
          </h1>
        </header>

        {/* ── Course Information ────────────────────────────────────────── */}
        {info && (
          <table className="mt-4 w-full border-collapse text-sm">
            <tbody>
              {[
                ['Course Code', info.course_code, 'Credits', String(info.credits)],
                ['Course Name', info.course_name, 'L-T-P', info.ltp],
                ['Category', info.category, 'Contact Hours', String(info.contact_hours)],
              ].map(([l1, v1, l2, v2]) => (
                <tr key={l1}>
                  <th className="w-32 border border-gray-400 bg-gray-100 px-2 py-1 text-left font-semibold">{l1}</th>
                  <td className="border border-gray-400 px-2 py-1">{v1}</td>
                  <th className="w-32 border border-gray-400 bg-gray-100 px-2 py-1 text-left font-semibold">{l2}</th>
                  <td className="w-28 border border-gray-400 px-2 py-1">{v2}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* ── Course Objectives ─────────────────────────────────────────── */}
        <EditableList
          heading="Course Objectives"
          items={syllabus.objectives}
          canEdit={canEdit}
          numbered
          placeholder="To introduce the mathematical foundations of machine learning."
          onSave={(objectives) =>
            updateSyllabus.mutate({ id: syllabus.id, payload: { objectives } })
          }
          onRegenerate={() => regen('OBJECTIVES')}
          isPending={updateSyllabus.isPending}
          isRegenerating={regenerate.isPending}
        />

        {/* ── Course Outcomes ───────────────────────────────────────────── */}
        {sortedOutcomes.length > 0 && (
          <section className="group mt-6">
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <SectionHeading>Course Outcomes</SectionHeading>
              </div>
              {canEdit && (
                <RegenerateButton
                  label="Rewrite the outcomes"
                  disabled={regenerate.isPending}
                  onClick={() => regen('OUTCOMES')}
                />
              )}
            </div>
            <p className="mb-2 text-sm text-gray-800">
              On successful completion of this course, the student will be able to:
            </p>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-gray-100">
                  <th className="w-14 border border-gray-400 px-2 py-1 font-semibold">CO</th>
                  <th className="border border-gray-400 px-2 py-1 text-left font-semibold">Course Outcome</th>
                  <th className="w-28 border border-gray-400 px-2 py-1 font-semibold">Bloom's Level</th>
                </tr>
              </thead>
              <tbody>
                {sortedOutcomes.map((co) => (
                  <tr key={co.id}>
                    <td className="border border-gray-400 px-2 py-1 text-center font-semibold">{co.code}</td>
                    <td className="border border-gray-400 px-2 py-1">{co.description}</td>
                    <td className="border border-gray-400 px-2 py-1 text-center capitalize">
                      {co.bloom_level?.toLowerCase() ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {canEdit && (
              <p className="mt-1 text-xs text-gray-500 print:hidden">
                Individual outcomes and their CO-PO mappings are edited on the Outcomes tab.
                Rewriting them here replaces all of them, and the mappings with them.
              </p>
            )}
          </section>
        )}

        {/*
          ── The body of the document ──────────────────────────────────────

          THEORY prints its units. Every other type prints the document its type
          actually has — a lab manual's experiment list, an internship's rubric and
          weekly activities, a project handbook's milestones and viva.

          A laboratory is not taught in five units and never was; an internship
          student is not in a classroom at all. Printing Unit I through Unit V for
          either of them would be a regulation promising teaching that nobody will
          ever deliver.
        */}
        {isTheory ? (
          <>
            {/* ── Units ─────────────────────────────────────────────────── */}
            <section className="mt-6">
              {sortedUnits.map((unit) => (
                <UnitBlock
                  key={unit.id}
                  syllabusId={syllabus.id}
                  unit={unit}
                  canEdit={canEdit}
                  onRegenerate={() => regen('UNIT', unit.id)}
                  isRegenerating={regenerate.isPending}
                />
              ))}

              {sortedUnits.length > 0 && (
                <p className="mt-3 border-t-2 border-black pt-2 text-right text-sm font-bold uppercase">
                  Total: {totalHours} Hours
                </p>
              )}

              {canEdit && (
                <div className="mt-3 print:hidden">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={addUnit.isPending}
                    onClick={() =>
                      addUnit.mutate({
                        unit_number: sortedUnits.length + 1,
                        title: `Unit ${sortedUnits.length + 1}`,
                        total_hours: 12,
                        topics: [],
                      })
                    }
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    Add Unit
                  </Button>
                  <span className="ml-2 text-xs text-gray-500">
                    Splitting a unit is: add one, then move topics across. Merging is the reverse.
                  </span>
                </div>
              )}
            </section>

            {/* ── Practical Components ──────────────────────────────────── */}
            <EditableList
              heading="Practical Components"
              items={syllabus.practical_components}
              canEdit={canEdit}
              numbered
              hideWhenEmpty
              placeholder="Implement a multi-layer perceptron and evaluate it on a benchmark dataset."
              onRegenerate={() => regen('PRACTICALS')}
              onSave={(practical_components) =>
                updateSyllabus.mutate({ id: syllabus.id, payload: { practical_components } })
              }
              isPending={updateSyllabus.isPending}
            />

            {/* ── Internal Assessment ───────────────────────────────────── */}
            <EditableList
              heading="Internal Assessment"
              items={syllabus.internal_assessment}
              canEdit={canEdit}
              hideWhenEmpty
              placeholder="Two internal assessment tests of 50 marks each, averaged to 20 marks."
              onSave={(internal_assessment) =>
                updateSyllabus.mutate({ id: syllabus.id, payload: { internal_assessment } })
              }
              isPending={updateSyllabus.isPending}
            />
          </>
        ) : (
          <CourseDocumentSections
            docType={syllabus.doc_type}
            document={syllabus.document}
            canEdit={canEdit}
            saving={updateSyllabus.isPending || onSaveDocumentPending}
            onRegenerate={() => regen('DOCUMENT')}
            onSave={(document) =>
              onSaveDocument
                ? onSaveDocument(document)
                : updateSyllabus.mutate({ id: syllabus.id, payload: { document } })
            }
          />
        )}

        {/*
          ── Bibliography ──────────────────────────────────────────────────

          Text Books and the rest are rewritten SEPARATELY. They are separate
          printed sections, and a Board unhappy with its textbook list has no reason
          to lose the web resources it was perfectly happy with — which is exactly
          what a single "rewrite the bibliography" button would do to them.
        */}
        {confirmed.length > 0 && canEdit && (
          <div className="mt-6 flex justify-end gap-2 print:hidden">
            <RegenerateButton
              label="Rewrite the Text Books"
              disabled={regenerate.isPending}
              onClick={() => regen('BOOKS')}
            />
            <RegenerateButton
              label="Rewrite the References"
              disabled={regenerate.isPending}
              onClick={() => regen('REFERENCES')}
            />
          </div>
        )}

        {BIBLIOGRAPHY.map(({ heading, types }) => {
          const refs = confirmed.filter((r) => types.includes(r.ref_type))
          if (refs.length === 0) return null
          return (
            <section key={heading} className="mt-4">
              <SectionHeading>{heading}</SectionHeading>
              <ol className="list-inside list-decimal space-y-1 text-sm text-gray-900">
                {refs.map((ref) => (
                  <li key={ref.id}>{formatReference(ref)}</li>
                ))}
              </ol>
            </section>
          )
        })}

        {canEdit && (
          <p className="mt-4 text-xs text-gray-500 print:hidden">
            References are added and confirmed on the References tab. Only confirmed references print
            — an unconfirmed one is a search result nobody has vouched for.
          </p>
        )}
      </div>
    </article>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 border-b border-gray-400 pb-1 text-sm font-bold uppercase tracking-wide text-black">
      {children}
    </h2>
  )
}

function RegenerateButton({
  label, onClick, disabled,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      className="mb-2 inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 px-1.5 py-0.5 text-xs text-gray-500 transition hover:border-blue-300 hover:text-blue-700 disabled:opacity-40 print:hidden"
    >
      <Sparkles className="h-3 w-3" />
      Rewrite with AI
    </button>
  )
}

/**
 * One unit: heading, hours, and the 12–20 academic topics that print beneath it.
 *
 * The topics are edited one per line — the Board adds, removes and reorders them.
 * A textarea rather than N inputs, because a Board member rewriting a unit is
 * writing a list, not administering rows: they want to paste, reorder and delete
 * freely, and every keystroke landing in a separate controlled input makes that
 * miserable.
 */
function UnitBlock({
  syllabusId, unit, canEdit, onRegenerate, isRegenerating,
}: {
  syllabusId: string
  unit: SyllabusUnit
  canEdit: boolean
  onRegenerate: () => void
  isRegenerating: boolean
}) {
  const update = useUpdateUnit(syllabusId)
  const remove = useDeleteUnit(syllabusId)

  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(unit.title)
  const [hours, setHours] = useState(String(unit.total_hours ?? ''))
  const [topicText, setTopicText] = useState('')

  const printed = topicLines(unit)

  useEffect(() => {
    if (!editing) {
      setTitle(unit.title)
      setHours(String(unit.total_hours ?? ''))
      setTopicText(topicLines(unit).join('\n'))
    }
  }, [editing, unit])

  function save() {
    const lines = topicText.split('\n').map((l) => l.trim()).filter(Boolean)
    update.mutate(
      {
        unitId: unit.id,
        payload: {
          title: title.trim() || unit.title,
          total_hours: Number(hours) || unit.total_hours,
          topics: lines.map((t) => ({ title: t })),
          // Keep the prose rendering in step with the topics, so a regulation that
          // prints paragraphs and one that prints bullets say the same thing.
          content: lines.join(', ') + (lines.length ? '.' : ''),
        },
      },
      { onSuccess: () => setEditing(false) },
    )
  }

  if (editing) {
    const count = topicText.split('\n').filter((l) => l.trim()).length
    return (
      <div className="mb-5 rounded-lg border-2 border-blue-300 bg-blue-50/40 p-3 print:hidden">
        <div className="mb-2 flex gap-2">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="font-semibold"
            placeholder="Unit title"
          />
          <Input
            type="number"
            min={1}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className="w-28"
            placeholder="Hours"
          />
        </div>
        <Textarea
          rows={Math.max(12, count + 2)}
          value={topicText}
          onChange={(e) => setTopicText(e.target.value)}
          placeholder={
            'Evolution of Computing\nCharacteristics of Computer Systems\nFunctional Units\n' +
            'Von Neumann Architecture\nHarvard Architecture\nCPU Organization\nInstruction Cycle\n' +
            'Memory Hierarchy\nCache Memory\nSecondary Storage\nInput–Output Organization\n' +
            'Performance Evaluation\nBenchmarking\nModern Applications'
          }
          className="font-mono text-sm"
        />
        <p
          className={`mt-1 text-xs ${
            count < MIN_TOPICS ? 'font-semibold text-amber-700' : 'text-gray-600'
          }`}
        >
          {count} topic{count === 1 ? '' : 's'}, one per line.
          {count < MIN_TOPICS && (
            <>
              {' '}An official unit runs to {TARGET_TOPICS}–15, and never fewer than{' '}
              {MIN_TOPICS} — below that it reads as an outline.
            </>
          )}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" onClick={save} disabled={update.isPending}>
            <Check className="mr-1 h-4 w-4" />
            {update.isPending ? 'Saving…' : 'Save Unit'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
            <X className="mr-1 h-4 w-4" />
            Cancel
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="ml-auto border-red-200 text-red-600 hover:bg-red-50"
            disabled={remove.isPending}
            onClick={() => remove.mutate(unit.id, { onSuccess: () => setEditing(false) })}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete Unit
          </Button>
        </div>
      </div>
    )
  }

  const thin = printed.length > 0 && printed.length < MIN_TOPICS

  return (
    <div className="group mb-5">
      <div className="flex items-baseline justify-between gap-3 border-b border-gray-400 pb-1">
        <h3 className="text-sm font-bold uppercase tracking-wide text-black">
          Unit {roman(unit.unit_number)} &nbsp;–&nbsp; {unit.title}
        </h3>
        <div className="flex shrink-0 items-baseline gap-2">
          <span className="text-sm font-semibold text-black">
            {unit.total_hours ? `${unit.total_hours} Hours` : ''}
          </span>
          {canEdit && (
            <span className="flex items-center gap-1 opacity-0 transition group-hover:opacity-100 print:hidden">
              <button
                onClick={onRegenerate}
                disabled={isRegenerating}
                title="Rewrite just this unit with AI — the rest of the syllabus is untouched"
                className="text-gray-400 hover:text-blue-700 disabled:opacity-40"
              >
                <Sparkles className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setEditing(true)}
                title="Edit this unit"
                className="text-gray-400 hover:text-black"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>
      </div>

      {printed.length > 0 ? (
        <ul className="mt-2 space-y-0.5 text-sm text-gray-900">
          {printed.map((topic, i) => (
            <li key={`${i}-${topic.slice(0, 20)}`} className="flex gap-2">
              <span className="text-gray-400">•</span>
              <span>{topic}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm italic text-red-600 print:hidden">
          This unit has no topics. It cannot be published like this.
        </p>
      )}

      {thin && canEdit && (
        <p className="mt-1 text-xs text-amber-700 print:hidden">
          Only {printed.length} topics — an official unit runs to {TARGET_TOPICS}–15, and never
          fewer than {MIN_TOPICS}. Rewrite it with AI, or add the rest by hand.
        </p>
      )}
    </div>
  )
}

/**
 * A unit's printed lines.
 *
 * Falls back to splitting the prose block for syllabi that predate the topic list —
 * they must still print as a document rather than as nothing.
 */
function topicLines(unit: SyllabusUnit): string[] {
  const titles = unit.topics.map((t) => t.title?.trim()).filter(Boolean) as string[]
  if (titles.length) return titles

  const prose = (unit.content ?? '').trim().replace(/\.$/, '')
  return prose ? prose.split(',').map((p) => p.trim()).filter(Boolean) : []
}

/**
 * A prose section that is a list of lines — objectives, practical components,
 * internal assessment. Edited as one block of text: the Board is writing a
 * section, not managing rows.
 */
function EditableList({
  heading, items, canEdit, onSave, onRegenerate, isPending, isRegenerating,
  numbered, hideWhenEmpty, placeholder,
}: {
  heading: string
  items: string[]
  canEdit: boolean
  onSave: (items: string[]) => void
  onRegenerate?: () => void
  isPending?: boolean
  isRegenerating?: boolean
  numbered?: boolean
  hideWhenEmpty?: boolean
  placeholder?: string
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(items.join('\n'))

  useEffect(() => {
    if (!editing) setText(items.join('\n'))
  }, [editing, items])

  if (items.length === 0 && hideWhenEmpty && !canEdit) return null
  if (items.length === 0 && hideWhenEmpty && canEdit && !editing) {
    return (
      <div className="mt-6 print:hidden">
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Add {heading}
        </Button>
      </div>
    )
  }

  if (editing) {
    return (
      <section className="mt-6 rounded-lg border-2 border-blue-300 bg-blue-50/40 p-3 print:hidden">
        <SectionHeading>{heading}</SectionHeading>
        <Textarea
          rows={Math.max(4, text.split('\n').length + 1)}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          className="text-sm"
        />
        <p className="mt-1 text-xs text-gray-600">One per line. Blank lines are discarded.</p>
        <div className="mt-2 flex gap-2">
          <Button
            size="sm"
            disabled={isPending}
            onClick={() => {
              onSave(text.split('\n').map((l) => l.trim()).filter(Boolean))
              setEditing(false)
            }}
          >
            <Check className="mr-1 h-4 w-4" />
            {isPending ? 'Saving…' : 'Save'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
            <X className="mr-1 h-4 w-4" />
            Cancel
          </Button>
        </div>
      </section>
    )
  }

  if (items.length === 0) return null

  const List = numbered ? 'ol' : 'ul'
  return (
    <section className="group mt-6">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <SectionHeading>{heading}</SectionHeading>
        </div>
        {canEdit && (
          <span className="mb-2 flex shrink-0 items-center gap-1 opacity-0 transition group-hover:opacity-100 print:hidden">
            {onRegenerate && (
              <RegenerateButton
                label={`Rewrite the ${heading.toLowerCase()}`}
                disabled={isRegenerating}
                onClick={onRegenerate}
              />
            )}
            <button
              onClick={() => setEditing(true)}
              className="text-gray-400 hover:text-black"
              title={`Edit ${heading}`}
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          </span>
        )}
      </div>
      <List
        className={`space-y-1 text-sm text-gray-900 ${
          numbered ? 'list-inside list-decimal' : 'list-inside list-disc'
        }`}
      >
        {items.map((item, i) => (
          <li key={`${i}-${item.slice(0, 24)}`}>{item}</li>
        ))}
      </List>
    </section>
  )
}

/** A reference as it prints in a regulation bibliography. */
function formatReference(ref: SyllabusReference): string {
  const parts: string[] = []
  if (ref.authors?.length) parts.push(ref.authors.join(', '))
  if (ref.year) parts.push(`(${ref.year})`)
  parts.push(ref.title)
  let line = parts.join(' ')
  if (ref.publisher) line += `, ${ref.publisher}`
  if (ref.isbn) line += `. ISBN: ${ref.isbn}`
  else if (ref.doi) line += `. DOI: ${ref.doi}`
  else if (ref.url) line += `. ${ref.url}`
  return line.endsWith('.') ? line : `${line}.`
}

/** Shown above the document while the curriculum is locked. */
export function LockedDocumentNotice() {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-800 print:hidden">
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
      <span>
        This is the <strong>official syllabus</strong> of an approved curriculum. It is locked
        permanently and cannot be edited — by anyone. Academic changes are made by creating a new
        curriculum version.
      </span>
    </div>
  )
}
