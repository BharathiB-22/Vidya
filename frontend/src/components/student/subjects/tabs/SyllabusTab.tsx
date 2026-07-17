import { useState } from 'react'
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Clock,
  ExternalLink,
  FileText,
  Lock,
  Presentation,
  Target,
} from 'lucide-react'
import type { SubjectSyllabusReferenceOut, SyllabusUnitOut } from '@/lib/api/sis'
import type { SubjectTabProps } from './types'

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']

/**
 * The bibliography sections a printed regulation ends with, and which ref_type
 * lands in each. Mirrors m02.formatting.BIBLIOGRAPHY_SECTIONS — the student sees
 * the same four headings the official document prints, in the same order.
 */
const REF_SECTIONS: { name: string; types: string[] }[] = [
  { name: 'Text Books', types: ['TEXTBOOK'] },
  { name: 'Reference Books', types: ['REFERENCE', 'JOURNAL'] },
  { name: 'Suggested Reading', types: ['SUGGESTED_READING'] },
  { name: 'Web Resources', types: ['WEB_RESOURCE', 'ONLINE'] },
]

function groupReferences(refs: SubjectSyllabusReferenceOut[]) {
  return REF_SECTIONS.map((section) => ({
    name: section.name,
    refs: refs.filter((r) => section.types.includes(r.ref_type)),
  })).filter((section) => section.refs.length > 0)
}

function citation(ref: SubjectSyllabusReferenceOut): string {
  return [ref.authors.join(', ') || null, ref.publisher, ref.year?.toString()]
    .filter(Boolean)
    .join(' · ')
}

/** A titled card. Renders nothing when there is nothing to say — an official
 *  syllabus omits an empty section rather than printing an empty heading. */
function ListCard({ title, icon, items }: { title: string; icon: React.ReactNode; items: string[] }) {
  if (items.length === 0) return null
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800">
        {icon}
        {title}
      </h3>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-gray-700">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function UnitAccordion({
  unit,
  isOpen,
  isRead,
  onToggle,
}: {
  unit: SyllabusUnitOut
  isOpen: boolean
  isRead: boolean
  onToggle: () => void
}) {
  const roman = ROMAN[unit.unit_number - 1] ?? unit.unit_number
  const hasBody = Boolean(unit.content) || unit.topics.length > 0 || Boolean(unit.pedagogy)

  return (
    <section className="overflow-hidden rounded-xl border border-gray-200 bg-white transition-shadow hover:shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-3 px-5 py-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-600">
              Unit {roman}
            </span>
            {isRead && (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" aria-label="Read" />
            )}
          </div>
          <h3 className="mt-0.5 text-sm font-semibold leading-snug text-gray-900">{unit.title}</h3>
        </div>

        {unit.hours != null && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600">
            <Clock className="h-3 w-3" />
            {unit.hours} hrs
          </span>
        )}
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-gray-400 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* 0fr -> 1fr animates to the content's natural height without measuring it. */}
      <div
        className={`grid transition-all duration-300 ease-in-out ${isOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}
      >
        <div className="overflow-hidden">
          <div className="space-y-5 border-t border-gray-100 px-5 py-4">
            {!hasBody && (
              <p className="text-sm text-gray-400">
                No further detail was published for this unit.
              </p>
            )}

            {unit.content && (
              <div>
                <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                  Description
                </h4>
                <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700">
                  {unit.content}
                </p>
              </div>
            )}

            {unit.topics.length > 0 && (
              <div>
                <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                  Topics
                </h4>
                <ol className="space-y-2.5">
                  {unit.topics.map((topic, i) => (
                    <li key={i} className="rounded-lg bg-gray-50 px-3.5 py-2.5">
                      <div className="flex items-start justify-between gap-3">
                        <span className="text-sm font-medium text-gray-800">
                          <span className="mr-1.5 text-gray-400">{unit.unit_number}.{i + 1}</span>
                          {topic.title}
                        </span>
                        {topic.hours_estimate != null && (
                          <span className="shrink-0 text-xs text-gray-400">
                            {topic.hours_estimate} hrs
                          </span>
                        )}
                      </div>
                      {topic.description && (
                        <p className="mt-1 text-sm leading-relaxed text-gray-600">
                          {topic.description}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {unit.pedagogy && (
              <div>
                <h4 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                  <Presentation className="h-3 w-3" />
                  Pedagogy
                </h4>
                <p className="text-sm leading-relaxed text-gray-700">{unit.pedagogy}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

/**
 * The official syllabus, as a student sees it: read-only, and only ever the
 * published one.
 *
 * Students never see a draft, a submitted, or an under-review curriculum — they
 * reach a syllabus only through a subject they are enrolled in, and enrolment
 * only exists for a published curriculum. What they get is the document the
 * university has actually committed to teaching them.
 */
export function SyllabusTab({ subject }: SubjectTabProps) {
  const [openUnit, setOpenUnit] = useState<number | null>(null)
  const [readUnits, setReadUnits] = useState<Set<number>>(new Set())

  if (!subject.syllabus_id) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <FileText className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">
          The official syllabus for this subject has not been published yet.
        </p>
      </div>
    )
  }

  const toggleUnit = (unitNumber: number) => {
    setOpenUnit((current) => (current === unitNumber ? null : unitNumber))
    setReadUnits((current) => new Set(current).add(unitNumber))
  }

  const referenceSections = groupReferences(subject.references)

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-1.5 font-semibold text-gray-800">
            <Lock className="h-3.5 w-3.5 text-gray-400" />
            Official Syllabus
          </span>
          <span className="text-gray-500">Version {subject.syllabus_version}</span>
        </div>
        {(subject.syllabus_teaching_hours != null ||
          subject.syllabus_hours_per_week != null ||
          subject.units.length > 0) && (
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 border-t border-gray-100 pt-3 text-xs text-gray-500">
            {subject.units.length > 0 && (
              <span>
                <span className="font-semibold text-gray-700">{subject.units.length}</span> units
              </span>
            )}
            {subject.syllabus_teaching_hours != null && (
              <span>
                <span className="font-semibold text-gray-700">{subject.syllabus_teaching_hours}</span>{' '}
                total teaching hours
              </span>
            )}
            {subject.syllabus_hours_per_week != null && (
              <span>
                <span className="font-semibold text-gray-700">{subject.syllabus_hours_per_week}</span>{' '}
                hours / week
              </span>
            )}
          </div>
        )}
      </div>

      <ListCard
        title="Course Objectives"
        icon={<Target className="h-3.5 w-3.5 text-gray-400" />}
        items={subject.objectives}
      />

      {subject.units.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-8 text-center text-sm text-gray-400">
          No units published yet.
        </div>
      ) : (
        <div className="space-y-2">
          {subject.units.map((unit) => (
            <UnitAccordion
              key={unit.unit_number}
              unit={unit}
              isOpen={openUnit === unit.unit_number}
              isRead={readUnits.has(unit.unit_number)}
              onToggle={() => toggleUnit(unit.unit_number)}
            />
          ))}
        </div>
      )}

      <ListCard
        title="Practical Components"
        icon={<Presentation className="h-3.5 w-3.5 text-gray-400" />}
        items={subject.practical_components}
      />
      <ListCard
        title="Internal Assessment"
        icon={<FileText className="h-3.5 w-3.5 text-gray-400" />}
        items={subject.internal_assessment}
      />

      {referenceSections.length > 0 && (
        <section className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800">
            <BookOpen className="h-3.5 w-3.5 text-gray-400" />
            References
          </h3>
          <div className="space-y-4">
            {referenceSections.map((section) => (
              <div key={section.name}>
                <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                  {section.name}
                </h4>
                <ol className="space-y-2">
                  {section.refs.map((ref, i) => (
                    <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
                      <span className="shrink-0 text-gray-400">{i + 1}.</span>
                      <span className="min-w-0">
                        <span className="text-gray-800">{ref.title}</span>
                        {citation(ref) && (
                          <span className="mt-0.5 block text-xs text-gray-500">{citation(ref)}</span>
                        )}
                        {ref.url && (
                          <a
                            href={ref.url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-0.5 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                          >
                            Open <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
