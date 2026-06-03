import api from '@/lib/api'

// ---------------------------------------------------------------------------
// Schools
// ---------------------------------------------------------------------------

export interface School {
  id: string
  code: string
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

// ---------------------------------------------------------------------------
// Enrollment types (M11-002)
// ---------------------------------------------------------------------------

export interface RosterStudent {
  enrollment_id: string
  student_id: string
  full_name: string
  email: string
  identifier: string | null
  enrolled_at: string
  is_active: boolean
}

export interface EnrollmentOut {
  id: string
  student_id: string
  section_id: string
  enrolled_at: string
  is_active: boolean
}

export interface StudentSummary {
  id: string
  full_name: string
  email: string
  identifier: string | null
  is_enrolled: boolean
}

export interface ProgramSummary {
  id: string
  name: string
  code: string
  degree_type: string
}

export interface DeptSummary {
  id: string
  name: string
  code: string
}

export interface BatchSummary {
  id: string
  name: string
  start_year: number
  end_year: number
}

export interface SemesterSummary {
  id: string
  number: number
  label: string | null
}

export interface SectionSummary {
  id: string
  name: string
}

export interface EnrollmentSummary {
  enrollment_id: string
  section: SectionSummary
  semester: SemesterSummary
}

export interface StudentProfile {
  student_id: string
  full_name: string
  email: string
  identifier: string | null
  usn: string | null
  admission_year: number | null
  program: ProgramSummary | null
  department: DeptSummary | null
  batch: BatchSummary | null
  enrollment: EnrollmentSummary | null
}

export interface DashboardCounts {
  schools: number
  departments: number
  programs: number
  active_batches: number
  semesters: number
  sections: number
  enrolled_students: number
  total_students: number
  total_faculty: number
}

// ---------------------------------------------------------------------------
// Directory types (H50)
// ---------------------------------------------------------------------------

export interface DirectoryPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface StudentDirectoryItem {
  user_id: string
  full_name: string
  email: string
  identifier: string | null
  usn: string | null
  admission_year: number | null
  program: { id: string; name: string; code: string; degree_type: string } | null
  department: { id: string; name: string; code: string } | null
  batch: { id: string; name: string; start_year: number; end_year: number } | null
  current_section: { id: string; name: string } | null
  is_active: boolean
}

export interface StudentDetailOut extends StudentDirectoryItem {
  date_of_birth: string | null
  phone: string | null
  address_line1: string | null
  address_city: string | null
  address_state: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  photo_url: string | null
  notes: string | null
  profile_created_at: string | null
  profile_updated_at: string | null
}

export interface FacultyDirectoryItem {
  user_id: string
  full_name: string
  email: string
  employee_id: string | null
  designation: string | null
  specialization: string | null
  primary_department: { id: string; name: string; code: string } | null
  photo_url: string | null
  is_active: boolean
}

export interface FacultyDetailOut extends FacultyDirectoryItem {
  identifier: string | null
  qualifications: string | null
  bio: string | null
  office_location: string | null
  phone: string | null
  joining_date: string | null
  active_assignments: {
    course: { id: string; name: string; code: string }
    semester_label: string
    role: string
  }[]
  profile_created_at: string | null
  profile_updated_at: string | null
}

export interface StudentProfileUpsert {
  usn?: string
  admission_year?: number
  date_of_birth?: string
  phone?: string
  address_line1?: string
  address_city?: string
  address_state?: string
  emergency_contact_name?: string
  emergency_contact_phone?: string
  photo_url?: string
  notes?: string
}

export interface FacultyProfileUpsert {
  employee_id: string
  designation?: string
  qualifications?: string
  bio?: string
  office_location?: string
  phone?: string
  joining_date?: string
  specialization?: string
  primary_department_id?: string
  photo_url?: string
}

// ---------------------------------------------------------------------------
// Bulk profile import (H53)
// ---------------------------------------------------------------------------

export interface ProfileImportRowResult {
  row_number:              number
  email:                   string
  student_name:            string | null
  student_id:              string | null
  usn:                     string | null
  admission_year:          number | null
  phone:                   string | null
  address_line1:           string | null
  address_city:            string | null
  address_state:           string | null
  emergency_contact_name:  string | null
  emergency_contact_phone: string | null
  is_valid:                boolean
  errors:                  string[]
}

export interface ProfileImportPreviewResponse {
  total_rows:               number
  valid_rows:               number
  invalid_rows:             number
  not_found_in_db:          number
  duplicate_email_in_file:  number
  duplicate_usn_in_file:    number
  duplicate_usn_in_db:      number
  rows:                     ProfileImportRowResult[]
}

export interface ProfileImportCommitResult {
  total:   number
  updated: number
  skipped: number
  errors:  string[]
}

// ---------------------------------------------------------------------------
// Attendance (H55)
// ---------------------------------------------------------------------------

export interface AttendanceSessionCreateIn {
  course_id:         string
  section_id:        string
  session_date:      string  // YYYY-MM-DD
  period_number?:    number
  duration_minutes?: number
  topic_covered?:    string
}

export interface AttendanceSessionUpdateIn {
  topic_covered?:    string
  period_number?:    number
  duration_minutes?: number
}

export interface AttendanceMarkEntry {
  student_id: string
  status:     'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
  remarks?:   string
}

export interface AttendanceMarkIn {
  records:      AttendanceMarkEntry[]
  edit_reason?: string
}

export interface AttendanceRecordEditIn {
  status:       'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
  remarks?:     string
  edit_reason?: string
}

export interface ReopenSessionIn {
  reason: string
}

export interface AttendanceSessionOut {
  id:                 string
  course_id:          string
  course_code:        string
  course_title:       string
  section_id:         string
  section_name:       string
  semester_number:    number
  faculty_user_id:    string
  faculty_name:       string
  session_date:       string
  period_number:      number | null
  duration_minutes:   number | null
  topic_covered:      string | null
  status:             'OPEN' | 'LOCKED'
  is_editable:        boolean
  minutes_until_lock: number | null
  first_marked_at:    string | null
  locked_at:          string | null
  reopened_by:        string | null
  reopened_at:        string | null
  reopen_reason:      string | null
  total_enrolled:     number
  present_count:      number
  absent_count:       number
  late_count:         number
  excused_count:      number
  attendance_pct:     number | null
  created_at:         string
  updated_at:         string | null
}

export interface AttendanceRecordOut {
  id:            string
  session_id:    string
  student_id:    string
  student_name:  string
  student_email: string
  usn:           string | null
  status:        'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
  remarks:       string | null
  marked_by:     string | null
  marked_at:     string | null
  edited_by:     string | null
  edited_at:     string | null
  edit_reason:   string | null
}

export interface AttendanceMarkResult {
  session_id:  string
  saved:       number
  first_marks: number
  edits:       number
}

export interface CourseAttendanceSummary {
  course_id:         string
  course_code:       string
  course_title:      string
  total_sessions:    number
  attended_sessions: number
  excused_sessions:  number
  total_countable:   number
  attendance_pct:    number | null
  is_at_risk:        boolean
}

export interface MyAttendanceSummary {
  student_id:   string
  student_name: string
  usn:          string | null
  overall_pct:  number | null
  courses:      CourseAttendanceSummary[]
}

export interface SessionRecordForStudent {
  session_id:     string
  session_date:   string
  period_number:  number | null
  topic_covered:  string | null
  status:         'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
  remarks:        string | null
}

export interface MyCourseAttendanceDetail {
  course_id:    string
  course_code:  string
  course_title: string
  summary:      CourseAttendanceSummary
  sessions:     SessionRecordForStudent[]
}

export interface SectionStudentAttendance {
  student_id:        string
  student_name:      string
  usn:               string | null
  total_sessions:    number
  attended_sessions: number
  total_countable:   number
  attendance_pct:    number | null
  is_at_risk:        boolean
}

export interface SectionAttendanceOut {
  section_id:         string
  section_name:       string
  semester_number:    number
  batch_name:         string
  program_name:       string
  total_sessions:     number
  avg_attendance_pct: number | null
  students:           SectionStudentAttendance[]
}

export interface ShortageStudentOut {
  student_id:        string
  student_name:      string
  usn:               string | null
  email:             string
  section_id:        string
  section_name:      string
  semester_number?:  number
  course_id:         string
  course_code:       string
  course_title:      string
  total_sessions:    number
  attended_sessions: number
  total_countable:   number
  attendance_pct:    number
}

export interface ShortageReportOut {
  threshold_pct:  number
  total_at_risk:  number
  finalized_only: boolean
  students:       ShortageStudentOut[]
}

// H56 — Faculty-scoped shortage
export interface FacultyCourseShortage {
  course_id:       string
  course_code:     string
  course_title:    string
  section_id:      string
  section_name:    string
  semester_number: number
  at_risk_count:   number
  total_enrolled:  number
  students:        ShortageStudentOut[]
}

export interface FacultyShortageReportOut {
  faculty_id:     string
  threshold_pct:  number
  finalized_only: boolean
  total_at_risk:  number
  courses:        FacultyCourseShortage[]
}

// H56 — Grouped shortage (Dean/Admin)
export interface ShortageSectionGroup {
  section_id:      string
  section_name:    string
  semester_number: number
  at_risk_count:   number
  avg_pct:         number | null
  students:        ShortageStudentOut[]
}

export interface ShortageCourseGroup {
  course_id:     string
  course_code:   string
  course_title:  string
  total_at_risk: number
  sections:      ShortageSectionGroup[]
}

export interface ShortageGroupedOut {
  threshold_pct:               number
  finalized_only:              boolean
  total_courses_with_shortage: number
  total_students_at_risk:      number
  courses:                     ShortageCourseGroup[]
}

export interface AttendanceDashboardOut {
  today_sessions:           number
  marked_today:             number
  pending_sessions:         number
  students_below_threshold: number
  threshold_pct:            number
}

// ---------------------------------------------------------------------------
// Semester rollover (H54)
// ---------------------------------------------------------------------------

export type RolloverScope = 'all_programs' | 'program' | 'batch' | 'semester'

export interface RolloverScopeIn {
  scope: RolloverScope
  program_id?:         string
  batch_id?:           string
  source_semester_id?: string
}

export interface RolloverRowOut {
  enrollment_id:           string
  student_id:              string
  student_name:            string
  student_email:           string
  current_section_id:      string
  current_section_name:    string
  current_semester_number: number
  batch_name:              string
  program_name:            string
  target_semester_number:  number | null
  target_section_id:       string | null
  target_section_name:     string | null
  status:                  'ready' | 'blocked'
  reason:                  string | null
}

export interface RolloverSummary {
  total:   number
  ready:   number
  blocked: number
}

export interface RolloverPreviewResponse {
  scope:   string
  summary: RolloverSummary
  rows:    RolloverRowOut[]
}

export interface RolloverCommitRowResult {
  enrollment_id:     string
  student_id:        string
  student_name:      string
  target_section_id: string | null
  outcome:           'moved' | 'skipped' | 'error'
  reason:            string | null
}

export interface RolloverCommitResult {
  moved:   number
  skipped: number
  errors:  number
  rows:    RolloverCommitRowResult[]
}

// Self-service schemas (H51) — narrower than admin upsert; excludes admin-only fields
export interface StudentSelfServiceUpdate {
  phone?: string
  address_line1?: string
  address_city?: string
  address_state?: string
  emergency_contact_name?: string
  emergency_contact_phone?: string
  photo_url?: string
}

export interface FacultySelfServiceUpdate {
  phone?: string
  office_location?: string
  bio?: string
  specialization?: string
  photo_url?: string
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const sisApi = {
  // Schools
  listSchools: (includeInactive = false) =>
    api.get<School[]>('/sis/schools', { params: { include_inactive: includeInactive } }).then(r => r.data),

  getSchool: (id: string) =>
    api.get<School>(`/sis/schools/${id}`).then(r => r.data),

  createSchool: (body: { code: string; name: string; description?: string }) =>
    api.post<School>('/sis/schools', body).then(r => r.data),

  updateSchool: (id: string, body: Partial<{ code: string; name: string; description: string; is_active: boolean }>) =>
    api.put<School>(`/sis/schools/${id}`, body).then(r => r.data),

  deleteSchool: (id: string) =>
    api.delete(`/sis/schools/${id}`).then(r => r.data),

  // Dashboard counts
  getDashboardCounts: () =>
    api.get<DashboardCounts>('/sis/dashboard/counts').then(r => r.data),

  // Section roster
  getRoster: (sectionId: string, includeInactive = false) =>
    api.get<RosterStudent[]>(`/sis/sections/${sectionId}/roster`, {
      params: { include_inactive: includeInactive },
    }).then(r => r.data),

  // Student list (enroll picker)
  listStudents: (search?: string) =>
    api.get<StudentSummary[]>('/sis/students', { params: search ? { search } : {} }).then(r => r.data),

  // Student academic profile
  getStudentProfile: (studentId: string) =>
    api.get<StudentProfile>(`/sis/students/${studentId}/profile`).then(r => r.data),

  // Enrollment mutations
  enrollStudent: (studentId: string, sectionId: string) =>
    api.post<EnrollmentOut>('/sis/enrollments', { student_id: studentId, section_id: sectionId }).then(r => r.data),

  unenrollStudent: (enrollmentId: string) =>
    api.delete(`/sis/enrollments/${enrollmentId}`).then(r => r.data),

  moveStudent: (enrollmentId: string, targetSectionId: string) =>
    api.post<EnrollmentOut>(`/sis/enrollments/${enrollmentId}/move`, { target_section_id: targetSectionId }).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Directory (H50)
  // ---------------------------------------------------------------------------

  listStudentDirectory: (params: {
    page?: number; page_size?: number; search?: string
    program_id?: string; batch_id?: string; section_id?: string; is_active?: boolean
  } = {}) =>
    api.get<DirectoryPage<StudentDirectoryItem>>('/sis/directory/students', { params }).then(r => r.data),

  getStudentDetail: (userId: string) =>
    api.get<StudentDetailOut>(`/sis/directory/students/${userId}`).then(r => r.data),

  upsertStudentProfile: (userId: string, body: StudentProfileUpsert) =>
    api.put<StudentDetailOut>(`/sis/directory/students/${userId}/profile`, body).then(r => r.data),

  listFacultyDirectory: (params: {
    page?: number; page_size?: number; search?: string
    department_id?: string; is_active?: boolean
  } = {}) =>
    api.get<DirectoryPage<FacultyDirectoryItem>>('/sis/directory/faculty', { params }).then(r => r.data),

  getFacultyDetail: (userId: string) =>
    api.get<FacultyDetailOut>(`/sis/directory/faculty/${userId}`).then(r => r.data),

  upsertFacultyProfile: (userId: string, body: FacultyProfileUpsert) =>
    api.put<FacultyDetailOut>(`/sis/directory/faculty/${userId}/profile`, body).then(r => r.data),

  listDepartmentFaculty: (deptId: string) =>
    api.get<DirectoryPage<FacultyDirectoryItem>>(`/sis/departments/${deptId}/faculty`).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Self-service (H51) — user edits own profile
  // ---------------------------------------------------------------------------

  getMyStudentProfile: () =>
    api.get<StudentDetailOut>('/sis/me/student-profile').then(r => r.data),

  updateMyStudentProfile: (body: StudentSelfServiceUpdate) =>
    api.put<StudentDetailOut>('/sis/me/student-profile', body).then(r => r.data),

  getMyFacultyProfile: () =>
    api.get<FacultyDetailOut>('/sis/me/faculty-profile').then(r => r.data),

  updateMyFacultyProfile: (body: FacultySelfServiceUpdate) =>
    api.put<FacultyDetailOut>('/sis/me/faculty-profile', body).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Bulk profile import (H53)
  // ---------------------------------------------------------------------------

  previewBulkProfileImport: (file: File): Promise<ProfileImportPreviewResponse> => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ProfileImportPreviewResponse>(
      '/sis/directory/students/import/preview',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    ).then(r => r.data)
  },

  commitBulkProfileImport: (file: File): Promise<ProfileImportCommitResult> => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ProfileImportCommitResult>(
      '/sis/directory/students/import/commit',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    ).then(r => r.data)
  },

  downloadBulkProfileTemplateCsv: (): Promise<void> =>
    api.get('/sis/directory/students/import/template.csv', { responseType: 'blob' }).then(r => {
      _triggerSisDownload(r.data, 'student_profiles_template.csv', 'text/csv')
    }),

  downloadBulkProfileTemplateXlsx: (): Promise<void> =>
    api.get('/sis/directory/students/import/template.xlsx', { responseType: 'blob' }).then(r => {
      _triggerSisDownload(
        r.data,
        'student_profiles_template.xlsx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      )
    }),

  // ---------------------------------------------------------------------------
  // Semester rollover (H54)
  // ---------------------------------------------------------------------------

  rolloverPreview: (body: RolloverScopeIn): Promise<RolloverPreviewResponse> =>
    api.post<RolloverPreviewResponse>('/sis/rollover/preview', body).then(r => r.data),

  rolloverCommit: (body: RolloverScopeIn): Promise<RolloverCommitResult> =>
    api.post<RolloverCommitResult>('/sis/rollover/commit', body).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Attendance (H55)
  // ---------------------------------------------------------------------------

  createAttendanceSession: (body: AttendanceSessionCreateIn): Promise<AttendanceSessionOut> =>
    api.post<AttendanceSessionOut>('/sis/attendance/sessions', body).then(r => r.data),

  listAttendanceSessions: (params: {
    course_id?: string; section_id?: string
    date_from?: string; date_to?: string; status?: string
  } = {}): Promise<AttendanceSessionOut[]> =>
    api.get<AttendanceSessionOut[]>('/sis/attendance/sessions', { params }).then(r => r.data),

  getAttendanceSession: (sessionId: string): Promise<AttendanceSessionOut> =>
    api.get<AttendanceSessionOut>(`/sis/attendance/sessions/${sessionId}`).then(r => r.data),

  updateAttendanceSession: (sessionId: string, body: AttendanceSessionUpdateIn): Promise<AttendanceSessionOut> =>
    api.put<AttendanceSessionOut>(`/sis/attendance/sessions/${sessionId}`, body).then(r => r.data),

  getSessionRecords: (sessionId: string): Promise<AttendanceRecordOut[]> =>
    api.get<AttendanceRecordOut[]>(`/sis/attendance/sessions/${sessionId}/records`).then(r => r.data),

  markAttendance: (sessionId: string, body: AttendanceMarkIn): Promise<AttendanceMarkResult> =>
    api.post<AttendanceMarkResult>(`/sis/attendance/sessions/${sessionId}/mark`, body).then(r => r.data),

  editAttendanceRecord: (sessionId: string, recordId: string, body: AttendanceRecordEditIn): Promise<AttendanceRecordOut> =>
    api.patch<AttendanceRecordOut>(`/sis/attendance/sessions/${sessionId}/records/${recordId}`, body).then(r => r.data),

  reopenAttendanceSession: (sessionId: string, body: ReopenSessionIn): Promise<AttendanceSessionOut> =>
    api.post<AttendanceSessionOut>(`/sis/attendance/sessions/${sessionId}/reopen`, body).then(r => r.data),

  getAttendanceDashboard: (params: { semester_id?: string; threshold?: number } = {}): Promise<AttendanceDashboardOut> =>
    api.get<AttendanceDashboardOut>('/sis/attendance/analytics/dashboard', { params }).then(r => r.data),

  getShortageReport: (params: {
    threshold?: number; semester_id?: string; section_id?: string; course_id?: string
    program_id?: string; batch_id?: string; finalized_only?: boolean
  } = {}): Promise<ShortageReportOut> =>
    api.get<ShortageReportOut>('/sis/attendance/analytics/shortage', { params }).then(r => r.data),

  getShortageGrouped: (params: {
    threshold?: number; semester_id?: string
    program_id?: string; batch_id?: string; finalized_only?: boolean
  } = {}): Promise<ShortageGroupedOut> =>
    api.get<ShortageGroupedOut>('/sis/attendance/analytics/shortage/grouped', { params }).then(r => r.data),

  getFacultyShortage: (params: {
    threshold?: number; course_id?: string; section_id?: string; finalized_only?: boolean
  } = {}): Promise<FacultyShortageReportOut> =>
    api.get<FacultyShortageReportOut>('/sis/attendance/shortage/my-courses', { params }).then(r => r.data),

  getSectionAttendance: (sectionId: string, threshold?: number): Promise<SectionAttendanceOut> =>
    api.get<SectionAttendanceOut>(`/sis/attendance/analytics/section/${sectionId}`, {
      params: threshold !== undefined ? { threshold } : {},
    }).then(r => r.data),

  getMyAttendance: (threshold?: number): Promise<MyAttendanceSummary> =>
    api.get<MyAttendanceSummary>('/sis/attendance/me', {
      params: threshold !== undefined ? { threshold } : {},
    }).then(r => r.data),

  getMyCourseAttendance: (courseId: string, threshold?: number): Promise<MyCourseAttendanceDetail> =>
    api.get<MyCourseAttendanceDetail>(`/sis/attendance/me/course/${courseId}`, {
      params: threshold !== undefined ? { threshold } : {},
    }).then(r => r.data),
}

function _triggerSisDownload(data: Blob, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
