import type { CourseInformation } from '@/types/syllabus'

/**
 * The Course Information block that opens an official university syllabus.
 *
 *     Course Code    : 1MCA1         Credits              : 4
 *     Course Name    : The Art …     L-T-P                : 4-0-0
 *     Category       : Core          Total Teaching Hours : 52
 *                                    No. of Hours / Week  : 04
 *
 * Most of it is DERIVED on the server from the course row — a stored copy of the
 * credits would be a second source of truth, and would quietly disagree with the
 * curriculum the moment the Dean adjusted the course during review.
 *
 * The teaching hours and the hours a week are the exception: they are the Board's,
 * they are typed, and nothing derives them from the L-T-P.
 */
export function CourseInformationHeader({ info }: { info: CourseInformation }) {
  const fields: Array<[string, string | number]> = [
    ['Course Code', info.course_code],
    ['Course Name', info.course_name],
    ['Credits', info.credits],
    ['L-T-P', info.ltp],
    ['Category', info.category],
    ['Total Teaching Hours', info.contact_hours],
    ['Hours / Week', info.hours_per_week],
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
