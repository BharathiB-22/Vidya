import { Info, Lock, Eye } from 'lucide-react'
import type { SubjectTabProps } from './types'

const STATUS_COLORS: Record<string, string> = {
  PUBLISHED: 'bg-green-50 text-green-700',
  LOCKED: 'bg-gray-100 text-gray-700',
}

export function InternalMarksTab({ subject }: SubjectTabProps) {
  const marks = subject.internal_marks
  if (!marks || marks.components.length === 0) {
    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 flex items-start gap-2">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        No published internal marks for this subject yet.
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-400">
          <tr>
            <th className="px-4 py-2 text-left">Component</th>
            <th className="px-4 py-2 text-left">Type</th>
            <th className="px-4 py-2 text-left">Score</th>
            <th className="px-4 py-2 text-center">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {marks.components.map((c) => (
            <tr key={c.component_id}>
              <td className="px-4 py-2 font-medium text-gray-800">{c.name}</td>
              <td className="px-4 py-2 text-gray-500">{c.component_type}</td>
              <td className="px-4 py-2 text-gray-800">
                {c.marks_obtained != null ? `${c.marks_obtained} / ${c.max_marks}` : '—'}
              </td>
              <td className="px-4 py-2 text-center">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[c.status]}`}>
                  {c.status === 'LOCKED'
                    ? <><Lock className="h-3 w-3 inline mr-1" />Locked</>
                    : <><Eye className="h-3 w-3 inline mr-1" />Published</>}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {marks.total_marks_obtained != null && marks.total_max_marks != null && (
        <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100 flex justify-between items-center text-sm font-medium text-gray-800">
          <span>Total</span>
          <span>{marks.total_marks_obtained} / {marks.total_max_marks}</span>
        </div>
      )}
    </div>
  )
}
