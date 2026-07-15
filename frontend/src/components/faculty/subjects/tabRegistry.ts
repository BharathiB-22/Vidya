import type { ComponentType } from 'react'
import {
  LayoutGrid,
  Users,
  ListChecks,
  FlaskConical,
  CalendarCheck,
  ClipboardCheck,
  Presentation,
  Library,
  Microscope,
  BarChart2,
} from 'lucide-react'
import type { FacultySubjectContext, FacultySubjectTabProps } from './tabs/types'
import { OverviewTab } from './tabs/OverviewTab'
import { StudentsTab } from './tabs/StudentsTab'
import { AssignmentsTab } from './tabs/AssignmentsTab'
import { LabsTab } from './tabs/LabsTab'
import { AttendanceTab } from './tabs/AttendanceTab'
import { MarksTab } from './tabs/MarksTab'
import { CourseKitTab } from './tabs/CourseKitTab'
import { LearningMaterialsTab } from './tabs/LearningMaterialsTab'
import { ResearchTab } from './tabs/ResearchTab'
import { AnalyticsTab } from './tabs/AnalyticsTab'

export interface FacultySubjectTabDef {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  Component: ComponentType<FacultySubjectTabProps>
  /** Optional visibility gate. When present and it returns false for the current
   * subject, the tab (its trigger AND its panel) is not rendered. Omitted ⇒ always
   * visible. This is a pure UI filter — it changes nothing about permissions or the
   * backend, which still authorize every action independently. */
  isVisible?: (ctx: FacultySubjectContext) => boolean
}

// Central tab registry for the Faculty Subject Workspace — mirrors
// components/student/subjects/tabRegistry.ts. Future tabs are added here
// without touching FacultySubjectWorkspacePage.tsx itself.
export const FACULTY_SUBJECT_TABS: FacultySubjectTabDef[] = [
  { key: 'overview', label: 'Overview', icon: LayoutGrid, Component: OverviewTab },
  { key: 'students', label: 'Students', icon: Users, Component: StudentsTab },
  { key: 'assignments', label: 'Assignments', icon: ListChecks, Component: AssignmentsTab },
  // Labs is shown only for subjects that actually have a laboratory component.
  // A theory subject hides it entirely; a lab (or combined theory+lab) subject
  // shows it. See FacultySubjectContext.hasLabComponent.
  { key: 'labs', label: 'Labs', icon: FlaskConical, Component: LabsTab, isVisible: (ctx) => ctx.hasLabComponent },
  { key: 'attendance', label: 'Attendance', icon: CalendarCheck, Component: AttendanceTab },
  { key: 'marks', label: 'Internal Marks', icon: ClipboardCheck, Component: MarksTab },
  { key: 'course-kit', label: 'Course Kits', icon: Presentation, Component: CourseKitTab },
  { key: 'learning-materials', label: 'Learning Materials', icon: Library, Component: LearningMaterialsTab },
  { key: 'research', label: 'Research', icon: Microscope, Component: ResearchTab },
  { key: 'analytics', label: 'Analytics', icon: BarChart2, Component: AnalyticsTab },
]
