import { FileText } from 'lucide-react'
import type { SubjectTabProps } from './types'

export function SyllabusTab({ subject }: SubjectTabProps) {
  if (!subject.syllabus_id) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <FileText className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">Syllabus not yet approved for this subject.</p>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-center justify-between text-sm">
        <span className="text-gray-500">Version {subject.syllabus_version}</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-700 font-medium">
          {subject.syllabus_status}
        </span>
      </div>
      <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
        {subject.units.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">No units published yet.</div>
        ) : (
          subject.units.map((u) => (
            <div key={u.unit_number} className="px-5 py-3 flex items-center justify-between">
              <div>
                <span className="text-xs text-gray-400 mr-2">Unit {u.unit_number}</span>
                <span className="text-sm text-gray-800">{u.title}</span>
              </div>
              {u.hours != null && <span className="text-xs text-gray-400">{u.hours}h</span>}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
