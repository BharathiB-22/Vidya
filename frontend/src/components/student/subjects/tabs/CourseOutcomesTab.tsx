import { Target } from 'lucide-react'
import type { SubjectTabProps } from './types'

export function CourseOutcomesTab({ subject }: SubjectTabProps) {
  const cos = subject.course_outcomes
  if (cos.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Target className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-600">No course outcomes published yet.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
      {cos.map((co) => (
        <div key={co.code} className="px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">{co.code}</span>
            {co.bloom_level && <span className="text-xs text-gray-600">{co.bloom_level}</span>}
          </div>
          <p className="text-sm text-gray-700 mt-1">{co.description}</p>
        </div>
      ))}
    </div>
  )
}
