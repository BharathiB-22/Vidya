import { Lock, Clock, CheckCircle2, AlertTriangle } from 'lucide-react'
import type { AttendanceSessionOut } from '@/lib/api/sis'

export function StatusBadge({ session }: { session: AttendanceSessionOut }) {
  if (session.status === 'LOCKED') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-gray-300 bg-gray-100 text-gray-700">
        <Lock size={10} /> Locked
      </span>
    )
  }
  if (!session.is_editable) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-800">
        <Clock size={10} /> Window closed
      </span>
    )
  }
  if (session.first_marked_at === null) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-red-300 bg-red-50 text-red-700">
        <AlertTriangle size={10} /> Pending
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border border-green-300 bg-green-50 text-green-700">
      <CheckCircle2 size={10} /> Open
    </span>
  )
}
