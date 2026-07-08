import api from '@/lib/api'

export type CourseRoleInCourse = 'PRIMARY' | 'CO_FACULTY' | 'GUEST'

export interface CourseInfo {
  id: string
  code: string
  title: string
}

export interface SemesterInfo {
  id: string
  number: number
  label: string | null
}

export interface SectionInfo {
  id: string
  name: string
}

export interface FacultyInfo {
  id: string
  full_name: string
  email: string
}

export interface Assignment {
  id: string
  course_id: string
  faculty_user_id: string
  semester_id: string
  section_id: string | null
  assigned_by_user_id: string
  assigned_at: string
  is_active: boolean
  role_in_course: CourseRoleInCourse
  revoked_at: string | null
  revoked_by_user_id: string | null
  course: CourseInfo | null
  semester: SemesterInfo | null
  section: SectionInfo | null
  faculty: FacultyInfo | null
}

export interface AssignmentListResponse {
  total: number
  items: Assignment[]
}

export interface CreateAssignmentPayload {
  course_id: string
  faculty_user_id: string
  semester_id: string
  section_id?: string
  role_in_course: CourseRoleInCourse
}

export interface ValidSemester {
  id: string
  number: number
  label: string | null
  batch_id: string
  batch_name: string
  program_id: string
  program_name: string
  program_code: string
}

export interface ValidSemestersResponse {
  course_id: string
  program_id: string | null
  program_name: string | null
  scoped: boolean
  items: ValidSemester[]
}

export interface CourseWithAssignments {
  course_id: string
  code: string
  title: string
  assignments: Assignment[]
}

const B = '/course-assignments'

export const assignmentsApi = {
  create: (payload: CreateAssignmentPayload) =>
    api.post<Assignment>(B, payload).then(r => r.data),

  getValidSemesters: (courseId: string) =>
    api
      .get<ValidSemestersResponse>(`${B}/valid-semesters`, { params: { course_id: courseId } })
      .then(r => r.data),

  revoke: (assignmentId: string) =>
    api.post<Assignment>(`${B}/${assignmentId}/revoke`, {}).then(r => r.data),

  listByCourse: (courseId: string, semesterId?: string, includeInactive = false, sectionId?: string) =>
    api
      .get<AssignmentListResponse>(B, {
        params: {
          course_id: courseId,
          semester_id: semesterId || undefined,
          section_id: sectionId || undefined,
          include_inactive: includeInactive,
        },
      })
      .then(r => r.data),

  listMine: (includeInactive = false) =>
    api
      .get<AssignmentListResponse>(`${B}/mine`, {
        params: { include_inactive: includeInactive },
      })
      .then(r => r.data),

  listAll: (semesterId?: string, includeInactive = false, sectionId?: string) =>
    api
      .get<AssignmentListResponse>(B, {
        params: {
          semester_id:      semesterId || undefined,
          section_id:       sectionId || undefined,
          include_inactive: includeInactive,
          page_size:        500,
        },
      })
      .then(r => r.data),

  /** Every course in this operational semester's program, each with its
   * (possibly empty) assignments — a course with no faculty yet still
   * appears, unlike listAll() which only returns existing assignment rows. */
  listCoursesForSlot: (semesterId: string, sectionId?: string) =>
    api
      .get<CourseWithAssignments[]>(`${B}/courses-for-slot`, {
        params: { semester_id: semesterId, section_id: sectionId || undefined },
      })
      .then(r => r.data),
}
