import type { CourseInformation } from '@/types/syllabus'

/**
 * The Course Information block that opens an official university syllabus.
 *
 *     Course Code    : MCA201        Credits       : 4
 *     Course Name    : Machine …     L-T-P         : 3-1-2
 *     Category       : Core          Contact Hours : 90
 *
 * Every value here is DERIVED on the server from the course row — none of it is
 * stored on the syllabus and none of it is typed in by anyone. A stored copy of
 * the credits would be a second source of truth, and would quietly disagree with
 * the curriculum the moment the Board adjusted the course during review.
 */
export function CourseInformationHeader({ info }: { info: CourseInformation }) {
  const fields: Array<[string, string | number]> = [
    ['Course Code', info.course_code],
    ['Course Name', info.course_name],
    ['Credits', info.credits],
    ['L-T-P', info.ltp],
    ['Contact Hours', info.contact_hours],
    ['Category', info.category],
  ]

  return (
    <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="border-b border-gray-200 bg-gray-50 px-4 py-2.5">
        <h2 className="text-sm font-bold uppercase tracking-wide text-black">
          Course Information
        </h2>
      </header>
      <dl className="grid gap-x-8 gap-y-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2 min-w-0">
            <dt className="w-32 shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {label}
            </dt>
            <dd className="min-w-0 truncate text-sm font-semibold text-black">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
