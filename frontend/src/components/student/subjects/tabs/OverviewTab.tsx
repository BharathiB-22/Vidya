import { User, FileText, Target, ClipboardCheck, Presentation, Library, CalendarCheck, ListChecks } from 'lucide-react'
import type { SubjectTabProps } from './types'

const QUICK_LINKS = [
  { key: 'faculty', label: 'Faculty', icon: User },
  { key: 'syllabus', label: 'Syllabus', icon: FileText },
  { key: 'course-outcomes', label: 'Course Outcomes', icon: Target },
  { key: 'internal-marks', label: 'Internal Marks', icon: ClipboardCheck },
  { key: 'course-kit', label: 'Course Kit', icon: Presentation },
  { key: 'learning-materials', label: 'Learning Materials', icon: Library },
  { key: 'attendance', label: 'Attendance', icon: CalendarCheck },
  { key: 'assignments', label: 'Assignments', icon: ListChecks },
]

export function OverviewTab({ subject, onNavigateTab }: SubjectTabProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-400">Credits</div>
            <div className="font-semibold text-gray-800">{subject.credits}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Semester</div>
            <div className="font-semibold text-gray-800">{subject.semester}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Section</div>
            <div className="font-semibold text-gray-800">{subject.section_name}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Type</div>
            <div className="font-semibold text-gray-800">
              {subject.is_elective ? 'Elective' : subject.course_type ?? 'Core'}
            </div>
          </div>
        </div>
        {subject.description && (
          <p className="text-sm text-gray-600 pt-2 border-t border-gray-100">{subject.description}</p>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Quick links</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {QUICK_LINKS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onNavigateTab(key)}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-sm text-gray-700 transition-colors"
            >
              <Icon className="h-4 w-4 text-gray-400" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
