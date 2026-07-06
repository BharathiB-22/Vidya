import { Mail, Phone, MapPin, User } from 'lucide-react'
import type { SubjectTabProps } from './types'

export function FacultyTab({ subject }: SubjectTabProps) {
  const faculty = subject.faculty
  if (!faculty) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <User className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No faculty assigned yet.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex items-start gap-4">
        {faculty.photo_url ? (
          <img src={faculty.photo_url} alt={faculty.name} className="h-16 w-16 rounded-full object-cover shrink-0" />
        ) : (
          <div className="h-16 w-16 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
            <User className="h-7 w-7 text-gray-300" />
          </div>
        )}
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-gray-900">{faculty.name}</h3>
          {faculty.designation && <p className="text-sm text-gray-500">{faculty.designation}</p>}
          <div className="mt-2 space-y-1 text-sm text-gray-600">
            {faculty.email && (
              <div className="flex items-center gap-1.5"><Mail className="h-3.5 w-3.5 text-gray-400" />{faculty.email}</div>
            )}
            {faculty.phone && (
              <div className="flex items-center gap-1.5"><Phone className="h-3.5 w-3.5 text-gray-400" />{faculty.phone}</div>
            )}
            {faculty.office_location && (
              <div className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5 text-gray-400" />{faculty.office_location}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
