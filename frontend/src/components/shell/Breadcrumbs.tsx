import { Link, useLocation } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

interface Crumb {
  label: string
  to?: string
}

const SEGMENT_LABELS: Record<string, string> = {
  dashboard:            'Dashboard',
  programs:             'Program Advisor',
  academics:            'Academic Structure',
  departments:          'Departments',
  semesters:            'Semesters',
  batches:              'Batches',
  sections:             'Sections',
  syllabuses:           'Syllabuses',
  'course-kits':        'Course Kits',
  'learning-packages':  'Learning Packages',
  curate:               'Curate',
  labs:                 'Lab Assignments',
  review:               'Review',
  student:              'Student',
  research:             'Research',
  problems:             'Problems',
  documents:            'Document',
  vivas:                'Viva',
  exams:                'Exam Papers',
  create:               'Create',
  board:                'Board',
  scripts:              'Scripts',
  upload:               'Upload',
  evaluate:             'Evaluate',
  'bell-curve':         'Bell Curve',
  reports:              'Fairness Report',
  ratify:               'Ratify',
  submissions:          'Submissions',
  result:               'Result',
  admin:                'Admin',
  tenants:              'Tenants',
  new:                  'New',
  pending:              'Pending',
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function labelForSegment(seg: string): string {
  if (SEGMENT_LABELS[seg]) return SEGMENT_LABELS[seg]
  if (UUID_RE.test(seg) || seg.length > 20) return 'Detail'
  return seg.charAt(0).toUpperCase() + seg.slice(1)
}

export function Breadcrumbs() {
  const location = useLocation()
  const segments = location.pathname.split('/').filter(Boolean)

  if (segments.length <= 1) return null

  const crumbs: Crumb[] = segments.map((seg, idx) => {
    const to = '/' + segments.slice(0, idx + 1).join('/')
    const isLast = idx === segments.length - 1
    return { label: labelForSegment(seg), to: isLast ? undefined : to }
  })

  return (
    <nav className="flex items-center gap-1 text-sm text-gray-500 min-w-0 overflow-hidden">
      {crumbs.map((crumb, idx) => (
        <span key={idx} className="flex items-center gap-1 min-w-0">
          {idx > 0 && (
            <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 text-gray-500" />
          )}
          {crumb.to ? (
            <Link
              to={crumb.to}
              className="hover:text-sv-primary transition-colors truncate max-w-[120px]"
            >
              {crumb.label}
            </Link>
          ) : (
            <span className="text-gray-800 font-medium truncate max-w-[160px]">
              {crumb.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  )
}
