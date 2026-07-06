import type { ComponentType } from 'react'
import {
  LayoutGrid,
  User,
  FileText,
  Target,
  ClipboardCheck,
  Presentation,
  Library,
  CalendarCheck,
  ListChecks,
  FlaskConical,
} from 'lucide-react'
import type { SubjectDetailOut } from '@/lib/api/sis'
import type { SubjectTabProps } from './tabs/types'
import { OverviewTab } from './tabs/OverviewTab'
import { FacultyTab } from './tabs/FacultyTab'
import { SyllabusTab } from './tabs/SyllabusTab'
import { CourseOutcomesTab } from './tabs/CourseOutcomesTab'
import { InternalMarksTab } from './tabs/InternalMarksTab'
import { CourseKitTab } from './tabs/CourseKitTab'
import { LearningMaterialsTab } from './tabs/LearningMaterialsTab'
import { AttendanceTab } from './tabs/AttendanceTab'
import { AssignmentsTab } from './tabs/AssignmentsTab'
import { LabsTab } from './tabs/LabsTab'

export interface SubjectTabDef {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  /** 'planned' tabs are reserved slots for a future phase — this is the extension point. */
  status: 'active' | 'planned'
  Component: ComponentType<SubjectTabProps>
  /** Omit for always-visible. Return false to hide the tab entirely for this subject. */
  isVisible?: (subject: SubjectDetailOut) => boolean
}

// Central tab registry for the Subject Details hub. Future phases add tabs
// here (e.g. Research-per-subject, Digital Exams-per-subject) without
// touching SubjectDetailsPage.tsx itself.
export const SUBJECT_TABS: SubjectTabDef[] = [
  { key: 'overview', label: 'Overview', icon: LayoutGrid, status: 'active', Component: OverviewTab },
  { key: 'faculty', label: 'Faculty', icon: User, status: 'active', Component: FacultyTab },
  { key: 'syllabus', label: 'Syllabus', icon: FileText, status: 'active', Component: SyllabusTab },
  { key: 'course-outcomes', label: 'Course Outcomes', icon: Target, status: 'active', Component: CourseOutcomesTab },
  { key: 'assignments', label: 'Assignments', icon: ListChecks, status: 'active', Component: AssignmentsTab },
  {
    key: 'labs',
    label: 'Labs',
    icon: FlaskConical,
    status: 'active',
    Component: LabsTab,
    // Course.hours_practical > 0 is the reliable existing proxy for "has a lab
    // component" (also true for course_type LAB/PROJECT, which typically carry
    // practical hours too) — courses with no lab component hide this tab entirely.
    isVisible: (subject) => (subject.hours_practical ?? 0) > 0,
  },
  { key: 'attendance', label: 'Attendance', icon: CalendarCheck, status: 'active', Component: AttendanceTab },
  { key: 'internal-marks', label: 'Internal Marks', icon: ClipboardCheck, status: 'active', Component: InternalMarksTab },
  { key: 'course-kit', label: 'Course Kit', icon: Presentation, status: 'active', Component: CourseKitTab },
  { key: 'learning-materials', label: 'Learning Materials', icon: Library, status: 'active', Component: LearningMaterialsTab },
]
