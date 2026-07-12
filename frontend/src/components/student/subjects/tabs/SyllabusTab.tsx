import { FileText, Lock } from 'lucide-react'
import type { SubjectTabProps } from './types'

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']

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

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-sm">
        <span className="inline-flex items-center gap-1.5 font-semibold text-gray-800">
          <Lock className="h-3.5 w-3.5 text-gray-400" />
          Official Syllabus
        </span>
        <span className="text-gray-500">Version {subject.syllabus_version}</span>
      </div>

      <div className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 bg-white">
        {subject.units.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">No units published yet.</div>
        ) : (
          subject.units.map((u) => (
            <div key={u.unit_number} className="flex items-center justify-between px-5 py-3">
              <div className="min-w-0">
                <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Unit {ROMAN[u.unit_number - 1] ?? u.unit_number}
                </span>
                <span className="text-sm text-gray-800">{u.title}</span>
              </div>
              {u.hours != null && <span className="shrink-0 text-xs text-gray-400">{u.hours}h</span>}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
